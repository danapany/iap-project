import streamlit as st
import re
import time
import os
import json
from datetime import datetime
from config.prompts import SystemPrompts
from config.settings_local import AppConfigLocal
from utils.search_utils_local import SearchManagerLocal
from utils.ui_components_local import UIComponentsLocal
from utils.reprompting_db_manager import RepromptingDBManager
from utils.chart_utils import ChartManager

# MonitoringManager import
try:
    from utils.monitoring_manager import MonitoringManager
    MONITORING_AVAILABLE = True
except ImportError:
    MONITORING_AVAILABLE = False
    class MonitoringManager:
        def __init__(self, *args, **kwargs): pass
        def log_user_activity(self, *args, **kwargs): pass

LANGSMITH_ENABLED = os.getenv('LANGSMITH_TRACING', 'false').lower() == 'true'

if LANGSMITH_ENABLED:
    try:
        from langsmith import traceable, trace
        from langsmith.wrappers import wrap_openai
        LANGSMITH_AVAILABLE = True
    except ImportError:
        LANGSMITH_AVAILABLE = False
        LANGSMITH_ENABLED = False
        def traceable(name=None, **kwargs):
            def decorator(func): return func
            return decorator
        def trace(name=None, **kwargs):
            class DummyTrace:
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def update(self, **kwargs): pass
            return DummyTrace()
else:
    LANGSMITH_AVAILABLE = False
    def traceable(name=None, **kwargs):
        def decorator(func): return func
        return decorator
    def trace(name=None, **kwargs):
        class DummyTrace:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def update(self, **kwargs): pass
        return DummyTrace()

class StatisticsValidator:
    def __init__(self):
        self.validation_errors = []
        self.validation_warnings = []
    
    def validate_document(self, doc, doc_index):
        errors, warnings = [], []
        required_fields = ['incident_id', 'service_name', 'error_date']
        for field in required_fields:
            if not doc.get(field):
                errors.append(f"문서 {doc_index}: {field} 필드가 비어있음")
        
        error_time = doc.get('error_time')
        if error_time is not None:
            try:
                error_time_int = int(error_time)
                if error_time_int < 0:
                    warnings.append(f"문서 {doc_index}: error_time이 음수")
                elif error_time_int > 10080:
                    warnings.append(f"문서 {doc_index}: error_time이 비정상적으로 큼")
            except (ValueError, TypeError):
                errors.append(f"문서 {doc_index}: error_time 형식 오류")
        return errors, warnings
    
    def validate_statistics_result(self, stats, original_doc_count):
        errors, warnings = [], []
        total_count = stats.get('total_count', 0)
        if total_count != original_doc_count:
            errors.append(f"총 개수 불일치: 계산({total_count}) != 원본({original_doc_count})")
        return errors, warnings

class DataNormalizer:
    @staticmethod
    def normalize_error_time(error_time):
        if error_time is None: return 0
        try:
            if isinstance(error_time, str):
                error_time = error_time.strip()
                if error_time == '' or error_time.lower() in ['null', 'none', 'n/a']:
                    return 0
                return int(float(error_time))
            return int(error_time)
        except (ValueError, TypeError):
            return 0
    
    @staticmethod
    def normalize_date_fields(doc):
        normalized_doc = doc.copy()
        error_date = doc.get('error_date', '')
        
        if error_date:
            try:
                error_date_str = str(error_date).strip()
                if '-' in error_date_str and len(error_date_str) >= 7:
                    parts = error_date_str.split('-')
                    if len(parts) >= 2:
                        if parts[0].isdigit() and len(parts[0]) == 4:
                            normalized_doc['extracted_year'] = parts[0]
                        if parts[1].isdigit():
                            month_num = int(parts[1])
                            if 1 <= month_num <= 12:
                                normalized_doc['extracted_month'] = str(month_num)
                elif len(error_date_str) >= 8 and error_date_str.isdigit():
                    normalized_doc['extracted_year'] = error_date_str[:4]
                    month_str = error_date_str[4:6]
                    try:
                        month_num = int(month_str)
                        if 1 <= month_num <= 12:
                            normalized_doc['extracted_month'] = str(month_num)
                    except (ValueError, TypeError):
                        pass
                elif len(error_date_str) >= 4 and error_date_str[:4].isdigit():
                    normalized_doc['extracted_year'] = error_date_str[:4]
            except (ValueError, TypeError):
                pass
        
        if not normalized_doc.get('year') and normalized_doc.get('extracted_year'):
            normalized_doc['year'] = normalized_doc['extracted_year']
        if not normalized_doc.get('month') and normalized_doc.get('extracted_month'):
            normalized_doc['month'] = normalized_doc['extracted_month']
        
        if normalized_doc.get('year'):
            normalized_doc['year'] = str(normalized_doc['year']).strip()
        if normalized_doc.get('month'):
            try:
                month_val = int(normalized_doc['month'])
                if 1 <= month_val <= 12:
                    normalized_doc['month'] = str(month_val)
                else:
                    normalized_doc['month'] = ''
            except (ValueError, TypeError):
                normalized_doc['month'] = ''
        
        return normalized_doc
    
    @staticmethod
    def normalize_document(doc):
        normalized_doc = DataNormalizer.normalize_date_fields(doc)
        normalized_doc['error_time'] = DataNormalizer.normalize_error_time(doc.get('error_time'))
        
        string_fields = ['service_name', 'incident_grade', 'owner_depart', 'daynight', 'week']
        for field in string_fields:
            value = normalized_doc.get(field)
            normalized_doc[field] = str(value).strip() if value else ''
        
        return normalized_doc

class ImprovedStatisticsCalculator:
    def __init__(self, remove_duplicates=False):
        self.validator = StatisticsValidator()
        self.normalizer = DataNormalizer()
        self.remove_duplicates = remove_duplicates
    
    def _extract_filter_conditions(self, query):
        conditions = {
            'year': None, 'month': None, 'start_month': None, 'end_month': None,
            'daynight': None, 'week': None, 'service_name': None, 'department': None, 'grade': None
        }
        
        if not query: return conditions
        query_lower = query.lower()
        
        year_match = re.search(r'\b(202[0-9]|201[0-9])\b', query_lower)
        if year_match:
            conditions['year'] = year_match.group(1)
        
        month_range_patterns = [
            r'\b(\d+)\s*~\s*(\d+)월\b', r'\b(\d+)월\s*~\s*(\d+)월\b',
            r'\b(\d+)\s*-\s*(\d+)월\b', r'\b(\d+)월\s*-\s*(\d+)월\b'
        ]
        
        month_range_found = False
        for pattern in month_range_patterns:
            month_range_match = re.search(pattern, query_lower)
            if month_range_match:
                start_month = int(month_range_match.group(1))
                end_month = int(month_range_match.group(2))
                if 1 <= start_month <= 12 and 1 <= end_month <= 12 and start_month <= end_month:
                    conditions['start_month'] = start_month
                    conditions['end_month'] = end_month
                    month_range_found = True
                    break
        
        if not month_range_found:
            month_match = re.search(r'\b(\d{1,2})월\b', query_lower)
            if month_match:
                month_num = int(month_match.group(1))
                if 1 <= month_num <= 12:
                    conditions['month'] = str(month_num)
        
        if any(word in query_lower for word in ['야간', '밤', '새벽', '심야']):
            conditions['daynight'] = '야간'
        elif any(word in query_lower for word in ['주간', '낮', '오전', '오후']):
            conditions['daynight'] = '주간'
        
        week_patterns = {
            '월': ['월요일', '월'], '화': ['화요일', '화'], '수': ['수요일', '수'],
            '목': ['목요일', '목'], '금': ['금요일', '금'], '토': ['토요일', '토'],
            '일': ['일요일', '일']
        }
        
        for week_key, patterns in week_patterns.items():
            if any(pattern in query_lower for pattern in patterns):
                conditions['week'] = week_key
                break
        
        if '평일' in query_lower:
            conditions['week'] = '평일'
        elif '주말' in query_lower:
            conditions['week'] = '주말'
        
        grade_match = re.search(r'(\d+)등급', query_lower)
        if grade_match:
            conditions['grade'] = f"{grade_match.group(1)}등급"
        
        return conditions
    
    def _validate_document_against_conditions(self, doc, conditions):
        incident_id = doc.get('incident_id', 'N/A')
        
        if conditions['year']:
            doc_year = self._extract_year_from_document(doc)
            if not doc_year or doc_year != conditions['year']:
                return False, f"year mismatch"
        
        if conditions['start_month'] and conditions['end_month']:
            doc_month = self._extract_month_from_document(doc)
            if not doc_month:
                return False, "no month information"
            try:
                month_num = int(doc_month)
                if not (conditions['start_month'] <= month_num <= conditions['end_month']):
                    return False, f"month not in range"
            except (ValueError, TypeError):
                return False, f"invalid month format"
        elif conditions['month']:
            doc_month = self._extract_month_from_document(doc)
            if not doc_month or str(doc_month) != conditions['month']:
                return False, f"month mismatch"
        
        if conditions['daynight']:
            doc_daynight = doc.get('daynight', '').strip()
            if not doc_daynight or doc_daynight != conditions['daynight']:
                return False, f"daynight mismatch"
        
        if conditions['week']:
            doc_week = doc.get('week', '').strip()
            required_week = conditions['week']
            if required_week == '평일':
                if doc_week not in ['월', '화', '수', '목', '금']:
                    return False, f"not weekday"
            elif required_week == '주말':
                if doc_week not in ['토', '일']:
                    return False, f"not weekend"
            else:
                if not doc_week or doc_week != required_week:
                    return False, f"week mismatch"
        
        if conditions['grade']:
            doc_grade = doc.get('incident_grade', '')
            if doc_grade != conditions['grade']:
                return False, f"grade mismatch"
        
        return True, "passed"
    
    def _extract_year_from_document(self, doc):
        year = doc.get('year')
        if year:
            year_str = str(year).strip()
            if len(year_str) == 4 and year_str.isdigit():
                return year_str
        
        year = doc.get('extracted_year')
        if year:
            year_str = str(year).strip()
            if len(year_str) == 4 and year_str.isdigit():
                return year_str
        
        error_date = doc.get('error_date', '')
        if error_date:
            error_date_str = str(error_date).strip()
            if len(error_date_str) >= 4:
                if '-' in error_date_str:
                    parts = error_date_str.split('-')
                    if len(parts) > 0 and len(parts[0]) == 4 and parts[0].isdigit():
                        return parts[0]
                elif len(error_date_str) >= 8 and error_date_str[:4].isdigit():
                    return error_date_str[:4]
                elif len(error_date_str) >= 4 and error_date_str[:4].isdigit():
                    return error_date_str[:4]
        return None
    
    def _extract_month_from_document(self, doc):
        month = doc.get('month')
        if month:
            try:
                month_num = int(month)
                if 1 <= month_num <= 12:
                    return str(month_num)
            except (ValueError, TypeError):
                pass
        
        month = doc.get('extracted_month')
        if month:
            try:
                month_num = int(month)
                if 1 <= month_num <= 12:
                    return str(month_num)
            except (ValueError, TypeError):
                pass
        
        error_date = doc.get('error_date', '')
        if error_date:
            error_date_str = str(error_date).strip()
            if '-' in error_date_str:
                parts = error_date_str.split('-')
                if len(parts) >= 2 and parts[1].isdigit():
                    try:
                        month_num = int(parts[1])
                        if 1 <= month_num <= 12:
                            return str(month_num)
                    except (ValueError, TypeError):
                        pass
            elif len(error_date_str) >= 6 and error_date_str.isdigit():
                try:
                    month_num = int(error_date_str[4:6])
                    if 1 <= month_num <= 12:
                        return str(month_num)
                except (ValueError, TypeError):
                    pass
        return None
    
    def _apply_filters(self, documents, conditions):
        filtered_docs = []
        for doc in documents:
            is_valid, reason = self._validate_document_against_conditions(doc, conditions)
            if is_valid:
                filtered_docs.append(doc)
        return filtered_docs
    
    def _empty_statistics(self):
        return {
            'total_count': 0, 'yearly_stats': {}, 'monthly_stats': {},
            'time_stats': {'daynight': {}, 'week': {}}, 'department_stats': {},
            'service_stats': {}, 'grade_stats': {}, 'is_error_time_query': False,
            'validation': {'errors': [], 'warnings': [], 'is_valid': True},
            'primary_stat_type': None
        }
    
    def _is_error_time_query(self, query):
        if not query: return False
        error_time_keywords = ['장애시간', '장애 시간', 'error_time', '시간 통계', '시간 합계', '시간 합산', '분']
        return any(keyword in query.lower() for keyword in error_time_keywords)
    
    def _determine_primary_stat_type(self, query, yearly_stats, monthly_stats, time_stats, service_stats, department_stats, grade_stats):
        """쿼리를 분석하여 주요 통계 유형 결정"""
        if not query:
            # 쿼리가 없으면 데이터가 가장 많은 통계 사용
            stat_counts = {
                'yearly': len(yearly_stats),
                'monthly': len(monthly_stats),
                'service': len(service_stats),
                'department': len(department_stats),
                'grade': len(grade_stats),
                'time': len(time_stats.get('daynight', {})) + len(time_stats.get('week', {}))
            }
            return max(stat_counts.items(), key=lambda x: x[1])[0] if any(stat_counts.values()) else None
        
        query_lower = query.lower()
        
        # 명시적 키워드 확인 (우선순위 순서)
        if any(kw in query_lower for kw in ['연도별', '년도별', '년별', '연별']):
            return 'yearly'
        elif any(kw in query_lower for kw in ['월별']) or re.search(r'\b\d+월\b', query_lower):
            return 'monthly'
        elif any(kw in query_lower for kw in ['시간대별', '주간', '야간']):
            return 'time'
        elif any(kw in query_lower for kw in ['요일별']):
            return 'weekday'
        elif any(kw in query_lower for kw in ['부서별', '팀별']):
            return 'department'
        elif any(kw in query_lower for kw in ['서비스별']):
            return 'service'
        elif any(kw in query_lower for kw in ['등급별']):
            return 'grade'
        
        # 키워드가 없으면 데이터가 가장 많은 통계 사용
        stat_counts = {
            'yearly': len(yearly_stats),
            'monthly': len(monthly_stats),
            'service': len(service_stats),
            'department': len(department_stats),
            'grade': len(grade_stats),
            'time': len(time_stats.get('daynight', {})) + len(time_stats.get('week', {}))
        }
        return max(stat_counts.items(), key=lambda x: x[1])[0] if any(stat_counts.values()) else 'yearly'
    
    def _calculate_detailed_statistics(self, documents, conditions, is_error_time_query):
        stats = {
            'total_count': len(documents), 'yearly_stats': {}, 'monthly_stats': {},
            'time_stats': {'daynight': {}, 'week': {}}, 'department_stats': {},
            'service_stats': {}, 'grade_stats': {}, 'is_error_time_query': is_error_time_query,
            'filter_conditions': conditions, 'calculation_details': {}
        }
        
        # 연도별 통계 (정렬을 위해 임시 딕셔너리 사용)
        yearly_temp = {}
        for doc in documents:
            year = self._extract_year_from_document(doc)
            if year:
                if is_error_time_query:
                    error_time = doc.get('error_time', 0)
                    yearly_temp[year] = yearly_temp.get(year, 0) + error_time
                else:
                    yearly_temp[year] = yearly_temp.get(year, 0) + 1
        
        # 연도 오름차순 정렬
        for year in sorted(yearly_temp.keys()):
            stats['yearly_stats'][f"{year}년"] = yearly_temp[year]
        
        # 월별 통계 (1월~12월 순서 보장)
        monthly_temp = {}
        for doc in documents:
            month = self._extract_month_from_document(doc)
            if month:
                try:
                    month_num = int(month)
                    if 1 <= month_num <= 12:
                        if is_error_time_query:
                            error_time = doc.get('error_time', 0)
                            monthly_temp[month_num] = monthly_temp.get(month_num, 0) + error_time
                        else:
                            monthly_temp[month_num] = monthly_temp.get(month_num, 0) + 1
                except (ValueError, TypeError):
                    continue
        
        # 월 오름차순 정렬 (1월부터 12월까지)
        for month_num in sorted(monthly_temp.keys()):
            stats['monthly_stats'][f"{month_num}월"] = monthly_temp[month_num]
        
        # 시간대/요일/부서/서비스/등급별 통계
        daynight_temp = {}
        week_temp = {}
        department_temp = {}
        service_temp = {}
        grade_temp = {}
        
        for doc in documents:
            daynight = doc.get('daynight', '')
            week = doc.get('week', '')
            department = doc.get('owner_depart', '')
            service = doc.get('service_name', '')
            grade = doc.get('incident_grade', '')
            error_time = doc.get('error_time', 0) if is_error_time_query else 1
            
            if daynight:
                daynight_temp[daynight] = daynight_temp.get(daynight, 0) + error_time
            if week:
                week_temp[week] = week_temp.get(week, 0) + error_time
            if department:
                department_temp[department] = department_temp.get(department, 0) + error_time
            if service:
                service_temp[service] = service_temp.get(service, 0) + error_time
            if grade:
                grade_temp[grade] = grade_temp.get(grade, 0) + error_time
        
        # 시간대 정렬 (주간 먼저)
        time_order = ['주간', '야간']
        for time_key in time_order:
            if time_key in daynight_temp:
                stats['time_stats']['daynight'][time_key] = daynight_temp[time_key]
        
        # 요일 정렬 (월화수목금토일 순서)
        week_order = ['월', '화', '수', '목', '금', '토', '일', '평일', '주말']
        for week_key in week_order:
            if week_key in week_temp:
                week_display = f"{week_key}요일" if week_key in ['월', '화', '수', '목', '금', '토', '일'] else week_key
                stats['time_stats']['week'][week_display] = week_temp[week_key]
        
        # 부서별 정렬 (값 내림차순, 상위 10개)
        sorted_departments = sorted(department_temp.items(), key=lambda x: x[1], reverse=True)[:10]
        stats['department_stats'] = dict(sorted_departments)
        
        # 서비스별 정렬 (값 내림차순, 상위 10개)
        sorted_services = sorted(service_temp.items(), key=lambda x: x[1], reverse=True)[:10]
        stats['service_stats'] = dict(sorted_services)
        
        # 등급별 정렬 (1등급, 2등급, 3등급, 4등급 순서)
        grade_order = ['1등급', '2등급', '3등급', '4등급']
        for grade_key in grade_order:
            if grade_key in grade_temp:
                stats['grade_stats'][grade_key] = grade_temp[grade_key]
        # 그 외 등급
        for grade_key, value in sorted(grade_temp.items()):
            if grade_key not in stats['grade_stats']:
                stats['grade_stats'][grade_key] = value
        
        # 계산 세부사항
        total_error_time = sum(doc.get('error_time', 0) for doc in documents)
        stats['calculation_details'] = {
            'total_error_time_minutes': total_error_time,
            'total_error_time_hours': round(total_error_time / 60, 2),
            'average_error_time': round(total_error_time / len(documents), 2) if documents else 0,
            'max_error_time': max((doc.get('error_time', 0) for doc in documents), default=0),
            'min_error_time': min((doc.get('error_time', 0) for doc in documents), default=0),
            'documents_with_error_time': len([doc for doc in documents if doc.get('error_time', 0) > 0])
        }
        
        # 주요 통계 유형 결정 - 쿼리 내용 전달 필요
        stats['primary_stat_type'] = None  # 나중에 쿼리와 함께 결정
        
        return stats
    
    def calculate_comprehensive_statistics(self, documents, query, query_type="default"):
        if not documents:
            return self._empty_statistics()
        
        # 문서 정규화
        normalized_docs = []
        validation_errors = []
        validation_warnings = []
        
        for i, doc in enumerate(documents):
            if doc is None: continue
            errors, warnings = self.validator.validate_document(doc, i)
            validation_errors.extend(errors)
            validation_warnings.extend(warnings)
            normalized_doc = self.normalizer.normalize_document(doc)
            normalized_docs.append(normalized_doc)
        
        # 중복 제거 (옵션)
        if self.remove_duplicates:
            unique_docs = {}
            for doc in normalized_docs:
                incident_id = doc.get('incident_id', '')
                if incident_id and incident_id not in unique_docs:
                    unique_docs[incident_id] = doc
            clean_documents = list(unique_docs.values())
        else:
            clean_documents = normalized_docs
        
        # 필터 조건 추출
        filter_conditions = self._extract_filter_conditions(query)
        
        # 통계성 질문의 경우 필터링 최소화
        is_stats_query = any(keyword in query.lower() for keyword in ['건수', '통계', '연도별', '월별', '현황', '분포', '알려줘', '몇건', '개수'])
        
        if is_stats_query:
            filtered_docs = clean_documents
        else:
            filtered_docs = self._apply_filters(clean_documents, filter_conditions)
        
        # 장애시간 쿼리 여부 확인
        is_error_time_query = self._is_error_time_query(query)
        
        # 통계 계산
        stats = self._calculate_detailed_statistics(filtered_docs, filter_conditions, is_error_time_query)
        
        # 주요 통계 유형 결정
        stats['primary_stat_type'] = self._determine_primary_stat_type(
            query, 
            stats['yearly_stats'], 
            stats['monthly_stats'], 
            stats['time_stats'], 
            stats['service_stats'], 
            stats['department_stats'], 
            stats['grade_stats']
        )
        
        # 결과 검증
        result_errors, result_warnings = self.validator.validate_statistics_result(stats, len(filtered_docs))
        validation_errors.extend(result_errors)
        validation_warnings.extend(result_warnings)
        
        stats['validation'] = {
            'errors': validation_errors,
            'warnings': validation_warnings,
            'is_valid': len(validation_errors) == 0
        }
        
        return stats

class QueryProcessorLocal:
    def __init__(self, azure_openai_client, search_client, model_name, config=None):
        self.azure_openai_client = azure_openai_client
        self.search_client = search_client
        self.model_name = model_name
        self.config = config if config else AppConfigLocal()
        self.search_manager = SearchManagerLocal(search_client, self.config)
        self.ui_components = UIComponentsLocal()
        self.reprompting_db_manager = RepromptingDBManager()
        self.chart_manager = ChartManager()
        self.statistics_calculator = ImprovedStatisticsCalculator(remove_duplicates=False)
        self.debug_mode = True
        
        if MONITORING_AVAILABLE:
            try:
                self.monitoring_manager = MonitoringManager()
                self.monitoring_enabled = True
            except Exception:
                self.monitoring_manager = MonitoringManager()
                self.monitoring_enabled = False
        else:
            self.monitoring_manager = MonitoringManager()
            self.monitoring_enabled = False
        
        self.langsmith_enabled = LANGSMITH_ENABLED
        self._setup_langsmith()
    
    def _setup_langsmith(self):
        if not self.langsmith_enabled: return
        try:
            langsmith_status = self.config.get_langsmith_status()
            if langsmith_status['enabled'] and LANGSMITH_AVAILABLE:
                success = self.config.setup_langsmith()
                if success:
                    self.azure_openai_client = wrap_openai(self.azure_openai_client)
        except Exception:
            pass

    def safe_trace_update(self, trace_obj, **kwargs):
        if not self.langsmith_enabled: return
        try:
            if hasattr(trace_obj, 'update'):
                trace_obj.update(**kwargs)
            elif hasattr(trace_obj, 'add_outputs'):
                if 'outputs' in kwargs:
                    trace_obj.add_outputs(kwargs['outputs'])
                if 'metadata' in kwargs:
                    trace_obj.add_metadata(kwargs['metadata'])
        except Exception:
            pass

    def calculate_unified_statistics(self, documents, query, query_type="default"):
        if not documents:
            return self.statistics_calculator._empty_statistics()
        return self.statistics_calculator.calculate_comprehensive_statistics(documents, query, query_type)

    @traceable(name="check_reprompting_question")
    def check_and_transform_query_with_reprompting(self, user_query):
        if not user_query:
            return {'transformed': False, 'original_query': user_query, 'transformed_query': user_query, 'match_type': 'none'}
        
        start_time = time.time()
        
        with trace(name="reprompting_check", inputs={"user_query": user_query}) as trace_context:
            try:
                exact_result = self.reprompting_db_manager.check_reprompting_question(user_query)
                
                if exact_result['exists']:
                    result = {
                        'transformed': True,
                        'original_query': user_query,
                        'transformed_query': exact_result['custom_prompt'],
                        'question_type': exact_result['question_type'],
                        'wrong_answer_summary': exact_result['wrong_answer_summary'],
                        'match_type': 'exact'
                    }
                    if not self.debug_mode:
                        st.success("✅ 맞춤형 프롬프트를 적용하여 더 정확한 답변을 제공합니다.")
                    return result
                
                similar_questions = self.reprompting_db_manager.find_similar_questions(user_query, similarity_threshold=0.7, limit=3)
                
                if similar_questions:
                    best_match = similar_questions[0]
                    db_question = best_match['question']
                    custom_prompt_for_part = best_match['custom_prompt']
                    
                    try:
                        transformed_query = re.sub(re.escape(db_question), custom_prompt_for_part, user_query, flags=re.IGNORECASE)
                    except:
                        transformed_query = user_query.replace(db_question, custom_prompt_for_part)
                    
                    is_transformed = transformed_query != user_query
                    
                    result = {
                        'transformed': is_transformed,
                        'original_query': user_query,
                        'transformed_query': transformed_query,
                        'question_type': best_match['question_type'],
                        'wrong_answer_summary': best_match['wrong_answer_summary'],
                        'similarity': best_match['similarity'],
                        'similar_question': best_match['question'],
                        'match_type': 'similar'
                    }
                    
                    if is_transformed and not self.debug_mode:
                        st.info(f"📋 유사 질문 패턴을 감지하여 질문을 최적화했습니다.")
                    return result
                
                return {'transformed': False, 'original_query': user_query, 'transformed_query': user_query, 'match_type': 'none'}
                
            except Exception as e:
                return {'transformed': False, 'original_query': user_query, 'transformed_query': user_query, 'match_type': 'error', 'error': str(e)}
    
    def extract_time_conditions(self, query):
        if not query:
            return {'daynight': None, 'week': None, 'is_time_query': False}
        
        time_conditions = {'daynight': None, 'week': None, 'is_time_query': False}
        
        if any(keyword in query.lower() for keyword in ['야간', '밤', '새벽', '심야']):
            time_conditions['is_time_query'] = True
            time_conditions['daynight'] = '야간'
        elif any(keyword in query.lower() for keyword in ['주간', '낮', '오전', '오후']):
            time_conditions['is_time_query'] = True
            time_conditions['daynight'] = '주간'
        
        week_map = {
            '월요일': '월', '화요일': '화', '수요일': '수', '목요일': '목',
            '금요일': '금', '토요일': '토', '일요일': '일', '평일': '평일', '주말': '주말'
        }
        
        for keyword, value in week_map.items():
            if keyword in query.lower():
                time_conditions['is_time_query'] = True
                time_conditions['week'] = value
                break
        
        return time_conditions
    
    def extract_department_conditions(self, query):
        if not query:
            return {'owner_depart': None, 'is_department_query': False}
        
        department_conditions = {'owner_depart': None, 'is_department_query': False}
        
        department_keywords = ['담당부서', '조치부서', '처리부서', '책임부서', '관리부서', '부서', '팀', '조직']
        
        if any(keyword in query for keyword in department_keywords):
            department_conditions['is_department_query'] = True
        
        return department_conditions
    
    @traceable(name="classify_query_type")
    def classify_query_type_with_llm(self, query):
        if not query:
            return 'default'
        
        with trace(name="llm_query_classification", inputs={"query": query}) as trace_context:
            try:
                classification_prompt = f"""다음 사용자 질문을 분류하세요.

분류 카테고리:
1. repair: 서비스명과 장애현상이 포함된 복구방법 문의
2. cause: 장애원인 분석 문의
3. similar: 서비스명 없이 장애현상만으로 유사사례 문의
4. inquiry: 특정 조건의 장애 내역 조회
5. statistics: 통계 전용 질문 (건수, 통계, 현황, 분포 등)
6. default: 그 외

사용자 질문: {query}

응답 형식: repair, cause, similar, inquiry, statistics, default 중 하나만 출력하세요."""

                response = self.azure_openai_client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "당신은 IT 질문을 분류하는 전문가입니다."},
                        {"role": "user", "content": classification_prompt}
                    ],
                    temperature=0.1,
                    max_tokens=50
                )
                
                query_type = response.choices[0].message.content.strip().lower()
                
                if query_type not in ['repair', 'cause', 'similar', 'inquiry', 'statistics', 'default']:
                    query_type = 'default'
                
                return query_type
                
            except Exception:
                return 'default'

    def _generate_chart_title(self, query, stats):
        """통계 데이터를 기반으로 차트 제목 생성"""
        primary_type = stats.get('primary_stat_type', 'general')
        is_error_time = stats.get('is_error_time_query', False)
        
        title_map = {
            'yearly': '연도별 장애 발생 현황',
            'monthly': '월별 장애 발생 현황',
            'time': '시간대별 장애 발생 분포',
            'weekday': '요일별 장애 발생 분포',
            'department': '부서별 장애 처리 현황',
            'service': '서비스별 장애 발생 현황',
            'grade': '장애등급별 발생 비율',
            'general': '장애 발생 통계'
        }
        
        base_title = title_map.get(primary_type, '장애 통계')
        
        # 장애시간 쿼리면 제목 수정
        if is_error_time:
            base_title = base_title.replace('발생', '시간').replace('건수', '시간')
        
        # 쿼리에서 연도 추출
        if query:
            year_match = re.search(r'\b(202[0-9])\b', query)
            if year_match:
                base_title = f"{year_match.group(1)}년 {base_title}"
        
        return base_title

    def _get_chart_data_from_stats(self, stats):
        """통계 데이터에서 차트 데이터와 타입 결정"""
        primary_type = stats.get('primary_stat_type')
        
        if not primary_type:
            return None, None
        
        # 통계 유형에 따라 적절한 데이터와 차트 타입 선택
        if primary_type == 'yearly':
            data = stats.get('yearly_stats', {})
            chart_type = 'line' if len(data) > 1 else 'bar'
        elif primary_type == 'monthly':
            data = stats.get('monthly_stats', {})
            chart_type = 'line' if len(data) > 1 else 'bar'
        elif primary_type == 'time':
            time_stats = stats.get('time_stats', {})
            data = time_stats.get('daynight', {}) or time_stats.get('week', {})
            chart_type = 'bar'
        elif primary_type == 'weekday':
            data = stats.get('time_stats', {}).get('week', {})
            chart_type = 'bar'
        elif primary_type == 'department':
            data = stats.get('department_stats', {})
            # 상위 10개만
            sorted_data = dict(sorted(data.items(), key=lambda x: x[1], reverse=True)[:10])
            data = sorted_data
            chart_type = 'horizontal_bar'
        elif primary_type == 'service':
            data = stats.get('service_stats', {})
            # 상위 10개만
            sorted_data = dict(sorted(data.items(), key=lambda x: x[1], reverse=True)[:10])
            data = sorted_data
            chart_type = 'horizontal_bar'
        elif primary_type == 'grade':
            data = stats.get('grade_stats', {})
            chart_type = 'pie'
        else:
            # fallback
            data = stats.get('yearly_stats', {})
            chart_type = 'line'
        
        return data, chart_type

    def remove_text_charts_from_response(self, response_text):
        if not response_text:
            return response_text
        
        text_chart_patterns = [
            r'각\s*월별.*?차트로\s*나타낼\s*수\s*있습니다:.*?(?=\n\n|\n[^월"\d]|$)',
            r'\d+월:\s*[█▓▒░▬\*\-\|]+.*?(?=\n\n|\n[^월"\d]|$)',
            r'\n.*[█▓▒░▬]{2,}.*\n',
            r'```[^`]*[█▓▒░▬\*\-\|]{2,}[^`]*```',
        ]
        
        cleaned_response = response_text
        for pattern in text_chart_patterns:
            cleaned_response = re.sub(pattern, '', cleaned_response, flags=re.MULTILINE | re.DOTALL)
        
        cleaned_response = re.sub(r'\n{3,}', '\n\n', cleaned_response)
        return cleaned_response.strip()

    def _extract_incident_id_sort_key(self, incident_id):
        if not incident_id:
            return 999999999999999
        try:
            if incident_id.startswith('INM') and len(incident_id) > 3:
                return int(incident_id[3:])
            return hash(incident_id) % 999999999999999
        except (ValueError, TypeError):
            return hash(str(incident_id)) % 999999999999999

    def _apply_default_sorting(self, documents):
        if not documents:
            return documents
        try:
            def default_sort_key(doc):
                error_date = doc.get('error_date', '1900-01-01') or '1900-01-01'
                try:
                    error_time_val = int(doc.get('error_time', 0) or 0)
                except (ValueError, TypeError):
                    error_time_val = 0
                incident_sort_key = self._extract_incident_id_sort_key(doc.get('incident_id', 'INM99999999999'))
                return (error_date, error_time_val, -incident_sort_key)
            
            documents.sort(key=default_sort_key, reverse=True)
        except Exception:
            pass
        return documents

    def detect_sorting_requirements(self, query):
        sort_info = {
            'requires_custom_sort': False, 'sort_field': None,
            'sort_direction': 'desc', 'sort_type': None,
            'limit': None, 'secondary_sort': 'default'
        }
        
        if not query:
            return sort_info
        
        query_lower = query.lower()
        
        error_time_patterns = [
            r'장애시간.*(?:가장.*?긴|긴.*?순|오래.*?걸린|최대|큰.*?순)',
            r'(?:최장|최대|가장.*?오래).*장애',
            r'top.*\d+.*장애시간',
        ]
        
        for pattern in error_time_patterns:
            if re.search(pattern, query_lower):
                sort_info['requires_custom_sort'] = True
                sort_info['sort_field'] = 'error_time'
                sort_info['sort_type'] = 'error_time'
                sort_info['sort_direction'] = 'desc'
                break
        
        top_match = re.search(r'top\s*(\d+)|상위\s*(\d+)', query_lower)
        if top_match:
            limit = int(top_match.group(1) or top_match.group(2))
            sort_info['limit'] = min(limit, 50)
            if not sort_info['requires_custom_sort']:
                sort_info['requires_custom_sort'] = True
                sort_info['sort_field'] = 'error_time'
                sort_info['sort_type'] = 'error_time'
        
        return sort_info

    def apply_custom_sorting(self, documents, sort_info):
        if not documents:
            return documents
        
        try:
            if sort_info['requires_custom_sort']:
                if sort_info['sort_type'] == 'error_time':
                    def error_time_sort_key(doc):
                        try:
                            error_time_val = int(doc.get('error_time', 0) or 0)
                        except (ValueError, TypeError):
                            error_time_val = 0
                        
                        error_date = doc.get('error_date', '1900-01-01')
                        incident_sort_key = self._extract_incident_id_sort_key(doc.get('incident_id', 'INM99999999999'))
                        
                        if sort_info['sort_direction'] == 'desc':
                            return (-error_time_val, error_date, incident_sort_key)
                        return (error_time_val, error_date, incident_sort_key)
                    
                    documents.sort(key=error_time_sort_key)
                
                if sort_info['limit']:
                    documents = documents[:sort_info['limit']]
            else:
                self._apply_default_sorting(documents)
            
            return documents
        except Exception:
            self._apply_default_sorting(documents)
            return documents

    @traceable(name="generate_rag_response")
    def generate_rag_response_with_adaptive_processing(self, query, documents, query_type="default", time_conditions=None, department_conditions=None, reprompting_info=None):
        if documents is None:
            documents = []
        
        if not documents:
            return "검색된 문서가 없어서 답변을 제공할 수 없습니다."
        
        with trace(name="adaptive_rag_processing", inputs={"query": query, "document_count": len(documents)}) as trace_context:
            try:
                start_time = time.time()

                # 통계 계산
                unified_stats = self.calculate_unified_statistics(documents, query, query_type)

                # 차트 생성 - 통계 데이터 직접 사용
                chart_fig = None
                chart_info = None
                
                # 명시적 차트 요청 확인
                chart_keywords = ['차트', '그래프', '시각화', '그려', '그려줘', '보여줘', '시각적으로', '도표', '도식화']
                has_explicit_chart_request = any(keyword in query.lower() for keyword in chart_keywords)
                
                if has_explicit_chart_request and unified_stats.get('total_count', 0) > 0:
                    # 통계 데이터에서 차트 데이터와 타입 가져오기
                    chart_data, chart_type = self._get_chart_data_from_stats(unified_stats)
                    
                    if chart_data and len(chart_data) > 0:
                        chart_title = self._generate_chart_title(query, unified_stats)
                        try:
                            chart_fig = self.chart_manager.create_chart(chart_type, chart_data, chart_title)
                            if chart_fig:
                                chart_info = {
                                    'chart': chart_fig, 
                                    'chart_type': chart_type,
                                    'chart_data': chart_data, 
                                    'chart_title': chart_title,
                                    'query': query, 
                                    'is_error_time_query': unified_stats.get('is_error_time_query', False)
                                }
                                print(f"DEBUG: Chart created - type: {chart_type}, data: {chart_data}")
                        except Exception as e:
                            print(f"DEBUG: Chart creation failed: {e}")
                            chart_info = None
                
                sort_info = self.detect_sorting_requirements(query)
                
                if time_conditions and time_conditions.get('is_time_query'):
                    documents = self.search_manager.filter_documents_by_time_conditions(documents, time_conditions)
                    if not documents:
                        return "해당 시간대 조건에 맞는 장애 내역을 찾을 수 없습니다."
                
                if department_conditions and department_conditions.get('is_department_query'):
                    documents = self.search_manager.filter_documents_by_department_conditions(documents, department_conditions)
                    if not documents:
                        return "해당 부서 조건에 맞는 장애 내역을 찾을 수 없습니다."
                
                processing_documents = self.apply_custom_sorting(documents, sort_info)
                
                total_count = len(processing_documents)
                yearly_stats = unified_stats.get('yearly_stats', {})
                monthly_stats = unified_stats.get('monthly_stats', {})
                is_error_time_query = unified_stats.get('is_error_time_query', False)
                
                # 🆕 통계 쿼리인 경우 특별 처리
                if query_type == "statistics":
                    context_parts = []
                    
                    # 통계 정보 요약
                    stats_summary = f"""## 📊 통계 집계 정보

    **전체 문서 수**: {unified_stats['total_count']}건
    **연도별 분포**: {dict(sorted(unified_stats['yearly_stats'].items()))}
    **월별 분포**: {unified_stats['monthly_stats']}
    **데이터 타입**: {'장애시간 합산 (분 단위)' if unified_stats['is_error_time_query'] else '발생 건수 집계'}

    ---
    """
                    context_parts.append(stats_summary)
                    
                    # 🆕 모든 문서 내역을 context에 상세히 추가
                    doc_details_header = """## 📋 통계 근거가 되는 실제 장애 문서 내역

    **아래는 위 통계에 실제로 집계된 모든 장애 건들입니다:**
    **이 문서들을 그대로 답변 하단에 출력해야 합니다!**

    """
                    context_parts.append(doc_details_header)
                    
                    for i, doc in enumerate(processing_documents, 1):
                        doc_detail = f"""### 문서 {i}:
    - **장애 ID**: {doc.get('incident_id', 'N/A')}
    - **서비스명**: {doc.get('service_name', 'N/A')}
    - **발생일자**: {doc.get('error_date', 'N/A')}
    - **발생년도**: {doc.get('year', 'N/A')}
    - **발생월**: {doc.get('month', 'N/A')}
    - **장애시간**: {doc.get('error_time', 0)}분
    - **장애등급**: {doc.get('incident_grade', 'N/A')}
    - **담당부서**: {doc.get('owner_depart', 'N/A')}
    - **시간대**: {doc.get('daynight', 'N/A')}
    - **요일**: {doc.get('week', 'N/A')}
    - **장애현상**: {doc.get('symptom', '')[:150]}{'...' if len(doc.get('symptom', '')) > 150 else ''}
    - **장애원인**: {doc.get('root_cause', '')[:150]}{'...' if len(doc.get('root_cause', '')) > 150 else ''}

    ---
    """
                        context_parts.append(doc_detail)
                    
                    context = "\n".join(context_parts)
                    
                    # 시스템 프롬프트 - 통계 전용
                    system_prompt = SystemPrompts.get_prompt(query_type)
                    final_query = reprompting_info.get('transformed_query', query) if reprompting_info and reprompting_info.get('transformed') else query
                    
                    user_prompt = f"""다음 장애 이력 문서들을 참고하여 통계 질문에 답변해주세요.

    {context}

    **🚨 절대 준수사항 - 반드시 확인하세요:**

    1. **문서 개수 일치성 검증**:
    - 제공된 실제 문서 수: {unified_stats['total_count']}건
    - 통계 집계 결과와 반드시 일치해야 함
    - 월별 합계 = 전체 합계 일치 확인

    2. **데이터 무결성 보장**:
    - 모든 발생일자(error_date)는 원본 그대로
    - 모든 장애시간(error_time)은 원본 그대로
    - 절대로 데이터를 변경하거나 추정하지 마세요

    3. **⭐ 근거 문서 내역 필수 출력 ⭐**:
    - 통계 답변 하단에 반드시 "## 🔍 통계 근거 문서 내역 (총 N건)" 섹션 포함
    - 위에 제공된 모든 문서({unified_stats['total_count']}건)를 번호 순서대로 출력
    - 각 문서마다 장애ID, 서비스명, 발생일자, 장애시간, 장애현상, 장애원인 포함
    - 근거 문서 개수와 통계 집계 건수가 일치하는지 확인

    4. **답변 구조**:
    ```
    [질문에 대한 통계 요약]
    
    📊 상세 통계:
    - 항목1: X건
    - 항목2: Y건
    ...
    
    📈 총 합계: N건
    
    ---
    
    ## 🔍 통계 근거 문서 내역 (총 N건)
    
    **아래는 위 통계에 실제로 집계된 장애 건들입니다:**
    
    ### 1. 장애 ID: [ID]
    - 서비스명: [서비스명]
    - 발생일자: [날짜]
    - 장애시간: [시간]분
    - 장애현상: [현상]
    - 장애원인: [원인]
    
    ### 2. 장애 ID: [ID]
    ...
    
    (모든 문서를 이 형식으로 출력)
    ```

    **질문**: {final_query}

    **답변을 시작하세요:**
    """

                    # 통계 전용 max_tokens 증가
                    max_tokens_for_stats = 5000
                    
                    response = self.azure_openai_client.chat.completions.create(
                        model=self.model_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.0,
                        max_tokens=max_tokens_for_stats
                    )
                    
                    final_answer = response.choices[0].message.content
                    
                    # 차트가 있는 경우 함께 반환
                    if chart_info:
                        return final_answer, chart_info
                    return final_answer
                
                # 일반 쿼리 처리 (repair, cause, similar, inquiry, default)
                else:
                    context_parts = []
                    
                    stats_info = f"""전체 문서 수: {total_count}건
    연도별 분포: {dict(sorted(yearly_stats.items()))}
    월별 분포: {monthly_stats}"""
                    
                    if is_error_time_query:
                        stats_info += f"\n데이터 유형: 장애시간 합산(분 단위)"
                    
                    context_parts.append(stats_info)
                    
                    for i, doc in enumerate(processing_documents[:30]):  # 최대 30개만
                        context_part = f"""문서 {i+1}:
    장애 ID: {doc['incident_id']}
    서비스명: {doc['service_name']}
    장애시간: {doc['error_time']}
    증상: {doc['symptom']}
    복구방법: {doc['incident_repair']}
    발생일자: {doc['error_date']}
    """
                        context_parts.append(context_part)
                    
                    context = "\n\n".join(context_parts)
                    
                    system_prompt = SystemPrompts.get_prompt(query_type)
                    final_query = reprompting_info.get('transformed_query', query) if reprompting_info and reprompting_info.get('transformed') else query

                    user_prompt = f"""다음 장애 이력 문서들을 참고하여 질문에 답변해주세요.

    **중요! 복구방법 관련:**
    - 복구방법 질문에는 incident_repair 필드 데이터만 사용하세요
    - incident_plan은 별도 참고용으로만 제공하세요

    **중요! 정확한 집계:**
    - 실제 제공된 문서 수: {total_count}건
    - 연도별: {dict(sorted(yearly_stats.items()))}
    - 월별: {monthly_stats}
    - 답변 시 실제 문서 수와 일치해야 함

    {context}

    질문: {final_query}

    답변:"""

                    max_tokens_initial = 2500 if query_type == 'inquiry' else 3000 if query_type == 'cause' else 1500

                    response = self.azure_openai_client.chat.completions.create(
                        model=self.model_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.0,
                        max_tokens=max_tokens_initial
                    )
                    
                    final_answer = response.choices[0].message.content
                    
                    if chart_info:
                        return final_answer, chart_info
                    return final_answer
            
            except Exception as e:
                st.error(f"응답 생성 실패: {str(e)}")
                return "죄송합니다. 응답을 생성하는 중 오류가 발생했습니다."

    def _display_response_with_marker_conversion(self, response, chart_info=None):
        if not response:
            st.write("응답이 없습니다.")
            return
            
        if isinstance(response, tuple):
            response_text, chart_info = response
        else:
            response_text = response
        
        if chart_info and chart_info.get('chart'):
            response_text = self.remove_text_charts_from_response(response_text)
            
        converted_content = response_text
        html_converted = False
        
        if '[REPAIR_BOX_START]' in converted_content:
            converted_content, has_repair_html = self.ui_components.convert_repair_box_to_html(converted_content)
            if has_repair_html:
                html_converted = True
        
        if '[CAUSE_BOX_START]' in converted_content:
            converted_content, has_cause_html = self.ui_components.convert_cause_box_to_html(converted_content)
            if has_cause_html:
                html_converted = True
        
        if html_converted:
            st.markdown(converted_content, unsafe_allow_html=True)
        else:
            st.write(converted_content)
        
        if chart_info and chart_info.get('chart'):
            st.markdown("---")
            try:
                self.chart_manager.display_chart_with_data(
                    chart_info['chart'], chart_info['chart_data'],
                    chart_info['chart_type'], chart_info.get('query', '')
                )
            except Exception as e:
                st.error(f"차트 표시 중 오류: {str(e)}")

    @traceable(name="process_user_query")
    def process_query(self, query, query_type=None):
        if not query:
            st.error("질문을 입력해주세요.")
            return
        
        with st.chat_message("assistant"):
            start_time = time.time()
            
            try:
                reprompting_info = self.check_and_transform_query_with_reprompting(query)
                processing_query = reprompting_info.get('transformed_query', query)
                
                time_conditions = self.extract_time_conditions(processing_query)
                department_conditions = self.extract_department_conditions(processing_query)
                
                if query_type is None:
                    with st.spinner("🔍 질문 분석 중..."):
                        query_type = self.classify_query_type_with_llm(processing_query)
                
                target_service_name = self.search_manager.extract_service_name_from_query(processing_query)
                
                with st.spinner("📄 문서 검색 중..."):
                    documents = self.search_manager.semantic_search_with_adaptive_filtering(
                        processing_query, target_service_name, query_type
                    )
                    
                    if documents is None:
                        documents = []
                    
                    if documents and len(documents) > 0:
                        with st.expander("📄 매칭된 문서 상세 보기"):
                            self.ui_components.display_documents_with_quality_info(documents)
                        
                        with st.spinner("🤖 AI 답변 생성 중..."):
                            response = self.generate_rag_response_with_adaptive_processing(
                                query, documents, query_type, time_conditions, department_conditions, reprompting_info
                            )
                            
                            if response is None:
                                response = "죄송합니다. 응답을 생성할 수 없습니다."
                            
                            if isinstance(response, tuple):
                                response_text, chart_info = response
                                self._display_response_with_marker_conversion(response_text, chart_info)
                                st.session_state.messages.append({"role": "assistant", "content": response_text})
                            else:
                                self._display_response_with_marker_conversion(response)
                                st.session_state.messages.append({"role": "assistant", "content": response})
                    else:
                        with st.spinner("📄 추가 검색 중..."):
                            fallback_documents = self.search_manager.search_documents_fallback(processing_query, target_service_name)
                            
                            if fallback_documents and len(fallback_documents) > 0:
                                response = self.generate_rag_response_with_adaptive_processing(
                                    query, fallback_documents, query_type, time_conditions, department_conditions, reprompting_info
                                )
                                
                                if isinstance(response, tuple):
                                    response_text, chart_info = response
                                    self._display_response_with_marker_conversion(response_text, chart_info)
                                    st.session_state.messages.append({"role": "assistant", "content": response_text})
                                else:
                                    self._display_response_with_marker_conversion(response)
                                    st.session_state.messages.append({"role": "assistant", "content": response})
                            else:
                                error_msg = f"'{target_service_name or '해당 조건'}'에 해당하는 문서를 찾을 수 없습니다."
                                st.write(error_msg)
                                st.session_state.messages.append({"role": "assistant", "content": error_msg})
            
            except Exception as e:
                error_msg = f"쿼리 처리 중 오류가 발생했습니다: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})