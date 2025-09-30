# -*- coding: utf-8 -*-
# query_processor_local.py
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
from utils.statistics_db_manager import StatisticsDBManager

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
        for field in ['incident_id', 'service_name', 'error_date']:
            if not doc.get(field):
                errors.append(f"Document {doc_index}: {field} field is empty")
        
        error_time = doc.get('error_time')
        if error_time is not None:
            try:
                error_time_int = int(error_time)
                if error_time_int < 0:
                    warnings.append(f"Document {doc_index}: error_time is negative")
                elif error_time_int > 10080:
                    warnings.append(f"Document {doc_index}: error_time is abnormally large")
            except (ValueError, TypeError):
                errors.append(f"Document {doc_index}: error_time format error")
        return errors, warnings
    
    def validate_statistics_result(self, stats, original_doc_count):
        errors, warnings = [], []
        if stats.get('total_count', 0) != original_doc_count:
            errors.append(f"Total count mismatch: calculated({stats.get('total_count', 0)}) != original({original_doc_count})")
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
        error_date = str(doc.get('error_date', '')).strip()
        
        if error_date:
            try:
                if '-' in error_date and len(error_date) >= 7:
                    parts = error_date.split('-')
                    if len(parts) >= 2:
                        if parts[0].isdigit() and len(parts[0]) == 4:
                            normalized_doc['extracted_year'] = parts[0]
                        if parts[1].isdigit() and 1 <= int(parts[1]) <= 12:
                            normalized_doc['extracted_month'] = str(int(parts[1]))
                elif len(error_date) >= 8 and error_date.isdigit():
                    normalized_doc['extracted_year'] = error_date[:4]
                    month_num = int(error_date[4:6])
                    if 1 <= month_num <= 12:
                        normalized_doc['extracted_month'] = str(month_num)
                elif len(error_date) >= 4 and error_date[:4].isdigit():
                    normalized_doc['extracted_year'] = error_date[:4]
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
                normalized_doc['month'] = str(month_val) if 1 <= month_val <= 12 else ''
            except (ValueError, TypeError):
                normalized_doc['month'] = ''
        
        return normalized_doc
    
    @staticmethod
    def normalize_document(doc):
        normalized_doc = DataNormalizer.normalize_date_fields(doc)
        normalized_doc['error_time'] = DataNormalizer.normalize_error_time(doc.get('error_time'))
        for field in ['service_name', 'incident_grade', 'owner_depart', 'daynight', 'week']:
            value = normalized_doc.get(field)
            normalized_doc[field] = str(value).strip() if value else ''
        return normalized_doc

class ImprovedStatisticsCalculator:
    def __init__(self, remove_duplicates=False):
        self.validator = StatisticsValidator()
        self.normalizer = DataNormalizer()
        self.remove_duplicates = remove_duplicates
    
    def _extract_filter_conditions(self, query):
        conditions = {'year': None, 'month': None, 'start_month': None, 'end_month': None, 'daynight': None, 'week': None, 'service_name': None, 'department': None, 'grade': None}
        if not query: return conditions
        query_lower = query.lower()
        
        year_match = re.search(r'\b(202[0-9]|201[0-9])\b', query_lower)
        if year_match:
            conditions['year'] = year_match.group(1)
        
        for pattern in [r'\b(\d+)\s*~\s*(\d+)월\b', r'\b(\d+)월\s*~\s*(\d+)월\b', r'\b(\d+)\s*-\s*(\d+)월\b', r'\b(\d+)월\s*-\s*(\d+)월\b']:
            month_range_match = re.search(pattern, query_lower)
            if month_range_match:
                start_month, end_month = int(month_range_match.group(1)), int(month_range_match.group(2))
                if 1 <= start_month <= 12 and 1 <= end_month <= 12 and start_month <= end_month:
                    conditions['start_month'], conditions['end_month'] = start_month, end_month
                    break
        
        if not conditions['start_month']:
            month_match = re.search(r'\b(\d{1,2})월\b', query_lower)
            if month_match and 1 <= int(month_match.group(1)) <= 12:
                conditions['month'] = str(int(month_match.group(1)))
        
        if any(word in query_lower for word in ['야간', '밤', '새벽', '심야']):
            conditions['daynight'] = '야간'
        elif any(word in query_lower for word in ['주간', '낮', '오전', '오후']):
            conditions['daynight'] = '주간'
        
        week_patterns = {'월': ['월요일', '월'], '화': ['화요일', '화'], '수': ['수요일', '수'], '목': ['목요일', '목'], '금': ['금요일', '금'], '토': ['토요일', '토'], '일': ['일요일', '일']}
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
        if conditions['year'] and self._extract_year_from_document(doc) != conditions['year']:
            return False, "year mismatch"
        
        if conditions['start_month'] and conditions['end_month']:
            doc_month = self._extract_month_from_document(doc)
            if not doc_month:
                return False, "no month information"
            try:
                if not (conditions['start_month'] <= int(doc_month) <= conditions['end_month']):
                    return False, "month not in range"
            except (ValueError, TypeError):
                return False, "invalid month format"
        elif conditions['month'] and str(self._extract_month_from_document(doc)) != conditions['month']:
            return False, "month mismatch"
        
        if conditions['daynight']:
            doc_daynight = doc.get('daynight', '').strip()
            if not doc_daynight or doc_daynight != conditions['daynight']:
                return False, "daynight mismatch"
        
        if conditions['week']:
            doc_week = doc.get('week', '').strip()
            required_week = conditions['week']
            if required_week == '평일':
                if doc_week not in ['월', '화', '수', '목', '금']:
                    return False, "not weekday"
            elif required_week == '주말':
                if doc_week not in ['토', '일']:
                    return False, "not weekend"
            elif not doc_week or doc_week != required_week:
                return False, "week mismatch"
        
        if conditions['grade'] and doc.get('incident_grade', '') != conditions['grade']:
            return False, "grade mismatch"
        
        return True, "passed"
    
    def _extract_year_from_document(self, doc):
        for key in ['year', 'extracted_year']:
            year = doc.get(key)
            if year:
                year_str = str(year).strip()
                if len(year_str) == 4 and year_str.isdigit():
                    return year_str
        
        error_date = str(doc.get('error_date', '')).strip()
        if len(error_date) >= 4:
            if '-' in error_date:
                parts = error_date.split('-')
                if parts and len(parts[0]) == 4 and parts[0].isdigit():
                    return parts[0]
            elif error_date[:4].isdigit():
                return error_date[:4]
        return None
    
    def _extract_month_from_document(self, doc):
        for key in ['month', 'extracted_month']:
            month = doc.get(key)
            if month:
                try:
                    month_num = int(month)
                    if 1 <= month_num <= 12:
                        return str(month_num)
                except (ValueError, TypeError):
                    pass
        
        error_date = str(doc.get('error_date', '')).strip()
        if '-' in error_date:
            parts = error_date.split('-')
            if len(parts) >= 2 and parts[1].isdigit():
                try:
                    month_num = int(parts[1])
                    if 1 <= month_num <= 12:
                        return str(month_num)
                except (ValueError, TypeError):
                    pass
        elif len(error_date) >= 6 and error_date.isdigit():
            try:
                month_num = int(error_date[4:6])
                if 1 <= month_num <= 12:
                    return str(month_num)
            except (ValueError, TypeError):
                pass
        return None
    
    def _apply_filters(self, documents, conditions):
        return [doc for doc in documents if self._validate_document_against_conditions(doc, conditions)[0]]
    
    def _empty_statistics(self):
        return {'total_count': 0, 'yearly_stats': {}, 'monthly_stats': {}, 'time_stats': {'daynight': {}, 'week': {}}, 'department_stats': {}, 'service_stats': {}, 'grade_stats': {}, 'is_error_time_query': False, 'validation': {'errors': [], 'warnings': [], 'is_valid': True}, 'primary_stat_type': None}
    
    def _is_error_time_query(self, query):
        return query and any(keyword in query.lower() for keyword in ['장애시간', '장애 시간', 'error_time', '시간 통계', '시간 합계', '시간 합산', '분'])
    
    def _determine_primary_stat_type(self, query, yearly_stats, monthly_stats, time_stats, service_stats, department_stats, grade_stats):
        if query:
            query_lower = query.lower()
            keywords = [('yearly', ['연도별', '년도별', '년별', '연별']), ('monthly', ['월별']), ('time', ['시간대별', '주간', '야간']), ('weekday', ['요일별']), ('department', ['부서별', '팀별']), ('service', ['서비스별']), ('grade', ['등급별'])]
            for stat_type, kws in keywords:
                if any(kw in query_lower for kw in kws):
                    return stat_type
            if re.search(r'\b\d+월\b', query_lower):
                return 'monthly'
        
        stat_counts = {'yearly': len(yearly_stats), 'monthly': len(monthly_stats), 'service': len(service_stats), 'department': len(department_stats), 'grade': len(grade_stats), 'time': len(time_stats.get('daynight', {})) + len(time_stats.get('week', {}))}
        return max(stat_counts.items(), key=lambda x: x[1])[0] if any(stat_counts.values()) else 'yearly'
    
    def _calculate_detailed_statistics(self, documents, conditions, is_error_time_query):
        stats = {'total_count': len(documents), 'yearly_stats': {}, 'monthly_stats': {}, 'time_stats': {'daynight': {}, 'week': {}}, 'department_stats': {}, 'service_stats': {}, 'grade_stats': {}, 'is_error_time_query': is_error_time_query, 'filter_conditions': conditions, 'calculation_details': {}}
        
        yearly_temp, monthly_temp = {}, {}
        for doc in documents:
            year = self._extract_year_from_document(doc)
            month = self._extract_month_from_document(doc)
            error_time = doc.get('error_time', 0) if is_error_time_query else 1
            
            if year:
                yearly_temp[year] = yearly_temp.get(year, 0) + error_time
            if month:
                try:
                    month_num = int(month)
                    if 1 <= month_num <= 12:
                        monthly_temp[month_num] = monthly_temp.get(month_num, 0) + error_time
                except (ValueError, TypeError):
                    pass
        
        for year in sorted(yearly_temp.keys()):
            stats['yearly_stats'][f"{year}년"] = yearly_temp[year]
        for month_num in sorted(monthly_temp.keys()):
            stats['monthly_stats'][f"{month_num}월"] = monthly_temp[month_num]
        
        daynight_temp, week_temp, department_temp, service_temp, grade_temp = {}, {}, {}, {}, {}
        for doc in documents:
            error_time = doc.get('error_time', 0) if is_error_time_query else 1
            for field, temp_dict in [('daynight', daynight_temp), ('week', week_temp), ('owner_depart', department_temp), ('service_name', service_temp), ('incident_grade', grade_temp)]:
                value = doc.get(field, '')
                if value:
                    temp_dict[value] = temp_dict.get(value, 0) + error_time
        
        for time_key in ['주간', '야간']:
            if time_key in daynight_temp:
                stats['time_stats']['daynight'][time_key] = daynight_temp[time_key]
        
        for week_key in ['월', '화', '수', '목', '금', '토', '일', '평일', '주말']:
            if week_key in week_temp:
                week_display = f"{week_key}요일" if week_key in ['월', '화', '수', '목', '금', '토', '일'] else week_key
                stats['time_stats']['week'][week_display] = week_temp[week_key]
        
        stats['department_stats'] = dict(sorted(department_temp.items(), key=lambda x: x[1], reverse=True)[:10])
        stats['service_stats'] = dict(sorted(service_temp.items(), key=lambda x: x[1], reverse=True)[:10])
        
        for grade_key in ['1등급', '2등급', '3등급', '4등급']:
            if grade_key in grade_temp:
                stats['grade_stats'][grade_key] = grade_temp[grade_key]
        for grade_key, value in sorted(grade_temp.items()):
            if grade_key not in stats['grade_stats']:
                stats['grade_stats'][grade_key] = value
        
        total_error_time = sum(doc.get('error_time', 0) for doc in documents)
        stats['calculation_details'] = {'total_error_time_minutes': total_error_time, 'total_error_time_hours': round(total_error_time / 60, 2), 'average_error_time': round(total_error_time / len(documents), 2) if documents else 0, 'max_error_time': max((doc.get('error_time', 0) for doc in documents), default=0), 'min_error_time': min((doc.get('error_time', 0) for doc in documents), default=0), 'documents_with_error_time': len([doc for doc in documents if doc.get('error_time', 0) > 0])}
        stats['primary_stat_type'] = None
        return stats
    
    def calculate_comprehensive_statistics(self, documents, query, query_type="default"):
        if not documents:
            return self._empty_statistics()
        
        normalized_docs, validation_errors, validation_warnings = [], [], []
        for i, doc in enumerate(documents):
            if doc is None: continue
            errors, warnings = self.validator.validate_document(doc, i)
            validation_errors.extend(errors)
            validation_warnings.extend(warnings)
            normalized_docs.append(self.normalizer.normalize_document(doc))
        
        if self.remove_duplicates:
            unique_docs = {}
            for doc in normalized_docs:
                incident_id = doc.get('incident_id', '')
                if incident_id and incident_id not in unique_docs:
                    unique_docs[incident_id] = doc
            clean_documents = list(unique_docs.values())
        else:
            clean_documents = normalized_docs
        
        filter_conditions = self._extract_filter_conditions(query)
        is_stats_query = any(keyword in query.lower() for keyword in ['건수', '통계', '연도별', '월별', '현황', '분포', '알려줘', '몇건', '개수'])
        filtered_docs = clean_documents if is_stats_query else self._apply_filters(clean_documents, filter_conditions)
        
        is_error_time_query = self._is_error_time_query(query)
        stats = self._calculate_detailed_statistics(filtered_docs, filter_conditions, is_error_time_query)
        stats['primary_stat_type'] = self._determine_primary_stat_type(query, stats['yearly_stats'], stats['monthly_stats'], stats['time_stats'], stats['service_stats'], stats['department_stats'], stats['grade_stats'])
        
        result_errors, result_warnings = self.validator.validate_statistics_result(stats, len(filtered_docs))
        validation_errors.extend(result_errors)
        validation_warnings.extend(result_warnings)
        stats['validation'] = {'errors': validation_errors, 'warnings': validation_warnings, 'is_valid': len(validation_errors) == 0}
        return stats

class QueryProcessorLocal:
    def __init__(self, azure_openai_client, search_client, model_name, config=None):
        self.azure_openai_client = azure_openai_client
        self.search_client = search_client
        self.model_name = model_name
        self.config = config or AppConfigLocal()
        self.search_manager = SearchManagerLocal(search_client, self.config)
        self.ui_components = UIComponentsLocal()
        self.reprompting_db_manager = RepromptingDBManager()
        self.chart_manager = ChartManager()
        self.statistics_calculator = ImprovedStatisticsCalculator(remove_duplicates=False)
        self.statistics_db_manager = StatisticsDBManager()
        self.debug_mode = True
        
        # 중복 로깅 방지를 위한 플래그들 추가
        self._decorator_logging_enabled = False  # 데코레이터 로깅 비활성화
        self._manual_logging_enabled = True      # 수동 로깅 활성화
        
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
                if self.config.setup_langsmith():
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
        return self.statistics_calculator._empty_statistics() if not documents else self.statistics_calculator.calculate_comprehensive_statistics(documents, query, query_type)

    @traceable(name="check_reprompting_question")
    def check_and_transform_query_with_reprompting(self, user_query):
        """개선된 리프롬프팅 - 강제 치환 추가"""
        if not user_query:
            return {'transformed': False, 'original_query': user_query, 'transformed_query': user_query, 'match_type': 'none'}
        
        # 1단계: 강제 치환 먼저 적용
        force_replaced_query = self.force_replace_problematic_queries(user_query)
        
        with trace(name="reprompting_check", inputs={"user_query": user_query, "force_replaced": force_replaced_query}) as trace_context:
            try:
                # 강제 치환이 발생한 경우
                if force_replaced_query != user_query:
                    if not self.debug_mode:
                        st.success("✅ 맞춤형 프롬프트를 적용하여 더 정확한 답변을 제공합니다.")
                    return {
                        'transformed': True, 
                        'original_query': user_query, 
                        'transformed_query': force_replaced_query, 
                        'question_type': 'statistics',
                        'wrong_answer_summary': '동의어 표현 최적화',
                        'match_type': 'force_replacement'
                    }
                
                # 2단계: 기존 리프롬프팅 로직 실행
                exact_result = self.reprompting_db_manager.check_reprompting_question(user_query)
                if exact_result['exists']:
                    if not self.debug_mode:
                        st.success("✅ 맞춤형 프롬프트를 적용하여 더 정확한 답변을 제공합니다.")
                    return {
                        'transformed': True, 
                        'original_query': user_query, 
                        'transformed_query': exact_result['custom_prompt'], 
                        'question_type': exact_result['question_type'], 
                        'wrong_answer_summary': exact_result['wrong_answer_summary'], 
                        'match_type': 'exact'
                    }
                
                # 3단계: 유사 질문 검색
                similar_questions = self.reprompting_db_manager.find_similar_questions(user_query, similarity_threshold=0.7, limit=3)
                if similar_questions:
                    best_match = similar_questions[0]
                    try:
                        transformed_query = re.sub(re.escape(best_match['question']), best_match['custom_prompt'], user_query, flags=re.IGNORECASE)
                    except:
                        transformed_query = user_query.replace(best_match['question'], best_match['custom_prompt'])
                    
                    is_transformed = transformed_query != user_query
                    if is_transformed and not self.debug_mode:
                        st.info("📋 유사 질문 패턴을 감지하여 질문을 최적화했습니다.")
                    return {
                        'transformed': is_transformed, 
                        'original_query': user_query, 
                        'transformed_query': transformed_query, 
                        'question_type': best_match['question_type'], 
                        'wrong_answer_summary': best_match['wrong_answer_summary'], 
                        'similarity': best_match['similarity'], 
                        'similar_question': best_match['question'], 
                        'match_type': 'similar'
                    }
                
                return {'transformed': False, 'original_query': user_query, 'transformed_query': user_query, 'match_type': 'none'}
                
            except Exception as e:
                return {'transformed': False, 'original_query': user_query, 'transformed_query': user_query, 'match_type': 'error', 'error': str(e)}
    
    def extract_time_conditions(self, query):
        if not query:
            return {'daynight': None, 'week': None, 'is_time_query': False}
        
        time_conditions = {'daynight': None, 'week': None, 'is_time_query': False}
        if any(keyword in query.lower() for keyword in ['야간', '밤', '새벽', '심야']):
            time_conditions.update({'is_time_query': True, 'daynight': '야간'})
        elif any(keyword in query.lower() for keyword in ['주간', '낮', '오전', '오후']):
            time_conditions.update({'is_time_query': True, 'daynight': '주간'})
        
        week_map = {'월요일': '월', '화요일': '화', '수요일': '수', '목요일': '목', '금요일': '금', '토요일': '토', '일요일': '일', '평일': '평일', '주말': '주말'}
        for keyword, value in week_map.items():
            if keyword in query.lower():
                time_conditions.update({'is_time_query': True, 'week': value})
                break
        
        return time_conditions
    
    def extract_department_conditions(self, query):
        if not query:
            return {'owner_depart': None, 'is_department_query': False}
        return {'owner_depart': None, 'is_department_query': any(keyword in query for keyword in ['담당부서', '조치부서', '처리부서', '책임부서', '관리부서', '부서', '팀', '조직'])}
    
    @traceable(name="classify_query_type")
    def classify_query_type_with_llm(self, query):
        if not query:
            return 'default'
        
        query_lower = query.lower()
        
        # 🔥 0단계: 통계성 '~별' 패턴 최우선 체크 (새로 추가)
        statistics_by_patterns = [
            r'원인유형별\s*.*(건수|통계|현황|분포|몇|개수|시간|분)',
            r'장애원인별\s*.*(건수|통계|현황|분포|몇|개수|시간|분)', 
            r'원인별\s*.*(건수|통계|현황|분포|몇|개수|시간|분)',
            r'(연도|년도|월|요일|시간대|등급|부서|서비스)별\s*.*(건수|통계|현황|분포|몇|개수|시간|분)',
            r'.*(건수|통계|현황|분포|몇|개수|시간|분)\s*.*(연도|년도|월|요일|시간대|등급|부서|서비스|원인유형|장애원인|원인)별',
            r'\w*별\s*\w*(건수|시간|분수|통계|현황|분포)',
            r'(건수|시간|분수|통계|현황|분포)\s*\w*별',
        ]
        
        for pattern in statistics_by_patterns:
            if re.search(pattern, query_lower):
                if self.debug_mode:
                    print(f"DEBUG: 통계성 '~별' 패턴 감지됨 - 즉시 statistics로 분류: {pattern}")
                return 'statistics'
        
        # 1단계: 명확한 비통계 키워드 우선 체크 (수정됨 - 원인 관련 예외 추가)
        non_statistics_keywords = [
            # 복구/해결 관련
            '복구방법', '해결방법', '조치방법', '대응방법', '복구절차', '해결절차',
            '복구', '해결', '조치', '대응', '수정', '개선', '처리방법',
            
            # 문제/장애 상황 관련 (원인 제외 - 통계에서 자주 사용됨)
            '불가', '실패', '안됨', '안돼', '되지않', '오류', '에러', 'error', 
            '문제', '장애', '이슈', 'issue', '버그', 'bug',
            
            # 🔥 원인 관련은 '~별' 패턴이 없을 때만 비통계로 처리 (조건부 제거)
            # '원인', '이유', '왜' - 이 키워드들은 아래에서 별도 처리
            
            # 유사사례 관련  
            '유사', '비슷한', '같은', '동일한', '비교',
            
            # 상세내역 조회 관련
            '내역', '목록', '리스트', '상세', '세부', '전체내역',
            
            # 증상/현상 관련
            '증상', '현상', '상황', '상태', '조건'
        ]
        
        # 🔥 원인 관련 키워드는 '~별' 패턴이 없을 때만 비통계로 판단
        cause_related_keywords = ['원인', '이유', '왜', 'why', '분석', '진단']
        has_cause_keyword = any(keyword in query_lower for keyword in cause_related_keywords)
        has_by_pattern = re.search(r'\w*별\s', query_lower) or re.search(r'\s\w*별', query_lower)
        
        # 원인 키워드가 있지만 '~별' 패턴도 있으면 통계로 우선 처리
        if has_cause_keyword and has_by_pattern:
            if self.debug_mode:
                print(f"DEBUG: 원인 키워드 + ~별 패턴 감지 - 통계 우선 처리")
            # 통계 패턴으로 넘어가서 추가 검증
        elif has_cause_keyword:
            if self.debug_mode:
                print(f"DEBUG: 원인 키워드 감지 (별 패턴 없음) - 비통계로 분류")
            return self._classify_non_statistics_query(query_lower)
        
        # 기존 비통계 키워드 체크
        if any(keyword in query_lower for keyword in non_statistics_keywords):
            if self.debug_mode:
                print(f"DEBUG: Non-statistics keyword detected, classified as non-statistics")
            return self._classify_non_statistics_query(query_lower)
        
        # 2단계: 명확한 통계 키워드 체크 (강화됨)
        clear_statistics_keywords = [
            # 명확한 통계 지시어
            '건수', '통계', '현황', '분포', '개수', '몇건', '몇개', 
            '연도별', '월별', '등급별', '장애등급별', '요일별', '시간대별',
            '부서별', '서비스별', '원인별', '원인유형별', '장애원인별',  # 🔥 추가
            
            # 집계 관련
            '합계', '총', '전체', '이합', '누적', '평균',
            
            # 차트/시각화 관련
            '차트', '그래프', '시각화', '그려', '그려줘', '보여줘'
        ]
        
        # 3단계: 통계 패턴 강화 검증 (개선됨)
        strong_statistics_patterns = [
            r'\b\d+년\s*.*(건수|통계|현황|분포|몇건|개수)',  # "2025년 건수"
            r'(건수|통계|현황|분포|몇건|개수)\s*.*\b\d+년',  # "건수 2025년"
            r'(연도별|월별|등급별|요일별|시간대별|부서별|서비스별|원인별|원인유형별|장애원인별)\s*.*(건수|통계|현황|분포)', # 🔥 강화
            r'(건수|통계|현황|분포)\s*.*(연도별|월별|등급별|요일별|시간대별|부서별|서비스별|원인별|원인유형별|장애원인별)', # 🔥 강화
            r'차트|그래프|시각화|그려|파이차트|막대차트|선차트',
            r'몇건\s*이야|몇건\s*인가|몇건\s*이니|몇건\s*이나|얼마나.*발생',
            r'\b\d+등급.*건수|\b\d+등급.*통계',
            r'\w+별\s*\w*(건수|시간|분수|통계|현황|분포)',  # 🔥 새로 추가
            r'(건수|시간|분수|통계|현황|분포)\s*\w+별',      # 🔥 새로 추가
        ]
        
        has_clear_statistics = any(keyword in query_lower for keyword in clear_statistics_keywords)
        has_statistics_pattern = any(re.search(pattern, query_lower) for pattern in strong_statistics_patterns)
        
        # 통계 키워드나 패턴이 있으면 통계로 분류
        if has_clear_statistics or has_statistics_pattern:
            if self.debug_mode:
                print(f"DEBUG: Strong statistics indicators found, classified as statistics")
                if has_clear_statistics:
                    found_keywords = [k for k in clear_statistics_keywords if k in query_lower]
                    print(f"DEBUG: Found statistics keywords: {found_keywords}")
                if has_statistics_pattern:
                    found_patterns = [p for p in strong_statistics_patterns if re.search(p, query_lower)]
                    print(f"DEBUG: Found statistics patterns: {found_patterns}")
            return 'statistics'
        
        # 4단계: LLM 기반 세밀한 분류 (더 보수적으로 통계 분류)
        with trace(name="llm_query_classification", inputs={"query": query}) as trace_context:
            try:
                # 강화된 분류 프롬프트
                classification_prompt = f"""다음 사용자 질문을 정확히 분류하세요.

중요: 통계(statistics) 분류는 매우 엄격하게 적용하세요.

분류 카테고리:
1. repair: 복구방법, 해결방법, 조치방법 문의 (예: "로그인 불가 복구방법", "에러 해결방법")
2. cause: 장애원인, 문제원인 분석 문의 (예: "장애원인 분석", "왜 발생했나") - 단, '~별' 패턴 제외  
3. similar: 유사사례, 비슷한 현상 문의 (예: "유사한 장애", "비슷한 문제")
4. inquiry: 특정 조건의 장애 내역 조회 (예: "ERP 장애내역", "2025년 장애 목록")
5. statistics: 순수 통계/집계 전용 - 🔥 다음 조건을 모두 고려하세요:
   - 명확한 통계 키워드: "건수", "통계", "현황", "분포", "몇건", "개수", "차트" 등
   - '~별' 패턴: "연도별", "월별", "원인유형별", "장애원인별", "부서별" 등
   - 집계 의도: 여러 데이터를 모아서 계산하거나 분석하려는 의도
6. default: 기타

🔥 중요한 statistics 분류 기준:
- "원인유형별 건수" = statistics (원인 분석이 아닌 통계 집계)
- "장애원인별 현황" = statistics (원인 분석이 아닌 통계 집계)  
- "원인별 분포" = statistics (원인 분석이 아닌 통계 집계)
- "2025년 원인유형별 장애건수" = statistics (명확한 통계 의도)

비통계 우선 원칙:
- "복구", "해결", "조치", "불가", "실패", "문제", "장애" 등이 있으면서 '~별' 패턴이 없으면 statistics 제외
- "원인", "이유", "왜" 등이 있지만 '~별' 패턴도 있으면 statistics 우선 고려
- "내역", "목록", "상세" 등 단순 조회는 inquiry로 분류
- 확실하지 않으면 default로 분류

사용자 질문: {query}

응답 형식: repair, cause, similar, inquiry, statistics, default 중 하나만 출력하세요."""

                response = self.azure_openai_client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "당신은 IT 질문을 매우 정확하게 분류하는 전문가입니다. 통계 분류는 엄격하게 적용하고, 확실하지 않으면 보수적으로 분류하세요. '~별' 패턴이 있는 질문은 통계성이 매우 높습니다."},
                        {"role": "user", "content": classification_prompt}
                    ],
                    temperature=0.0,  # 더 일관된 분류를 위해 temperature 낮춤
                    max_tokens=50
                )
                
                query_type = response.choices[0].message.content.strip().lower()
                
                # 5단계: 최종 검증 - 통계로 분류되었지만 비통계 키워드가 있는 경우 재분류
                if query_type == 'statistics':
                    # 재검증: 복구/문제해결 키워드가 있으면서 '~별' 패턴이 없는 경우 재분류
                    problem_keywords = ['불가', '실패', '안됨', '안돼', '오류', '에러', '문제', '장애현상', '증상']
                    has_problem_keywords = any(keyword in query_lower for keyword in problem_keywords)
                    
                    if has_problem_keywords and not has_by_pattern:
                        if self.debug_mode:
                            print(f"DEBUG: Statistics classification overridden due to problem keywords (no ~별 pattern)")
                        return self._classify_non_statistics_query(query_lower)
                
                # 🔥 추가 검증: '~별' 패턴이 있으면 강제로 statistics
                if has_by_pattern and any(stat_word in query_lower for stat_word in ['건수', '통계', '현황', '분포', '몇', '개수', '시간']):
                    if self.debug_mode:
                        print(f"DEBUG: '~별' 패턴 + 통계 키워드 감지 - 강제로 statistics 분류")
                    return 'statistics'
                
                if self.debug_mode:
                    print(f"DEBUG: LLM classified query as: {query_type}")
                
                return query_type if query_type in ['repair', 'cause', 'similar', 'inquiry', 'statistics', 'default'] else 'default'
                
            except Exception as e:
                print(f"ERROR: Query classification failed: {e}")
                # 오류 시 보수적으로 분류
                return self._classify_fallback(query_lower)

    def _classify_non_statistics_query(self, query_lower):
        """비통계 쿼리의 세부 분류 - 원인 관련 처리 개선"""
        if any(keyword in query_lower for keyword in ['복구', '해결', '조치', '대응', '복구방법', '해결방법']):
            return 'repair'
        elif any(keyword in query_lower for keyword in ['원인', '이유', '왜', '분석', '진단']):
            # 🔥 '~별' 패턴이 있으면 여기서도 statistics로 재분류
            if re.search(r'\w*별\s', query_lower) or re.search(r'\s\w*별', query_lower):
                return 'statistics'  # 원인 + ~별 = 통계
            return 'cause'  
        elif any(keyword in query_lower for keyword in ['유사', '비슷', '같은', '동일']):
            return 'similar'
        elif any(keyword in query_lower for keyword in ['내역', '목록', '리스트', '상세', '조회']):
            return 'inquiry'
        else:
            return 'default'

    def _classify_fallback(self, query_lower):
        """폴백 분류 로직 - 원인 관련 처리 개선"""
        # 폴백에서는 절대 statistics로 분류하지 않음
        if any(keyword in query_lower for keyword in ['복구', '해결', '불가', '실패', '문제']):
            return 'repair'
        elif any(keyword in query_lower for keyword in ['원인', '이유', '왜']):
            # 🔥 폴백에서도 '~별' 패턴 체크
            if re.search(r'\w*별\s', query_lower) or re.search(r'\s\w*별', query_lower):
                return 'default'  # 폴백에서는 statistics 대신 default
            return 'cause'
        else:
            return 'default'

    def _extract_chart_type_from_query(self, query):
        """쿼리에서 명시적으로 요청된 차트 타입 추출"""
        if not query:
            return None
        
        query_lower = query.lower()
        
        chart_type_keywords = {
            'horizontal_bar': [
                '가로막대', '가로 막대', '가로막대차트', '가로 막대 차트', '가로막대그래프', 
                'horizontal bar', 'barh', '가로바', '가로 바', '가로형 막대', '가로형'
            ],
            'bar': [
                '세로막대', '세로 막대', '세로막대차트', '세로 막대 차트', '막대차트', 
                '막대 차트', '막대그래프', 'bar chart', 'vertical bar', '바차트', '바 차트', '세로형'
            ],
            'line': [
                '선차트', '선 차트', '선그래프', '선 그래프', '라인차트', '라인 차트', 
                'line chart', 'line graph', '꺾은선', '꺾은선그래프', '추이', '트렌드'
            ],
            'pie': [
                '파이차트', '파이 차트', '원형차트', '원형 차트', '원그래프', 
                'pie chart', '파이그래프', '비율차트', '비율 차트', '원형'
            ]
        }
        
        for chart_type, keywords in chart_type_keywords.items():
            for keyword in keywords:
                if keyword in query_lower:
                    print(f"DEBUG: Detected chart type '{chart_type}' from keyword '{keyword}'")
                    return chart_type
        
        return None

    def _generate_chart_title(self, query, stats):
        primary_type = stats.get('primary_stat_type', 'general')
        title_map = {'yearly': '연도별 장애 발생 현황', 'monthly': '월별 장애 발생 현황', 'time': '시간대별 장애 발생 분포', 'weekday': '요일별 장애 발생 분포', 'department': '부서별 장애 처리 현황', 'service': '서비스별 장애 발생 현황', 'grade': '장애등급별 발생 비율', 'general': '장애 발생 통계'}
        base_title = title_map.get(primary_type, '장애 통계')
        
        if stats.get('is_error_time_query'):
            base_title = base_title.replace('발생', '시간').replace('건수', '시간')
        
        if query:
            year_match = re.search(r'\b(202[0-9])\b', query)
            if year_match:
                base_title = f"{year_match.group(1)}년 {base_title}"
        return base_title

    def _get_chart_data_from_stats(self, stats, requested_chart_type=None):
        """통계에서 차트 데이터 추출 - 사용자 요청 차트 타입 우선 처리"""
        primary_type = stats.get('primary_stat_type')
        if not primary_type:
            return None, None
        
        data_map = {
            'yearly': (stats.get('yearly_stats', {}), 'line'),
            'monthly': (stats.get('monthly_stats', {}), 'line'),
            'time': (stats.get('time_stats', {}).get('daynight', {}) or stats.get('time_stats', {}).get('week', {}), 'bar'),
            'weekday': (stats.get('time_stats', {}).get('week', {}), 'bar'),
            'department': (dict(sorted(stats.get('department_stats', {}).items(), key=lambda x: x[1], reverse=True)[:10]), 'horizontal_bar'),
            'service': (dict(sorted(stats.get('service_stats', {}).items(), key=lambda x: x[1], reverse=True)[:10]), 'horizontal_bar'),
            'grade': (stats.get('grade_stats', {}), 'pie')
        }
        
        data, default_chart_type = data_map.get(primary_type, (stats.get('yearly_stats', {}), 'line'))
        
        if requested_chart_type:
            chart_type = requested_chart_type
            print(f"DEBUG: Using user-requested chart type: {chart_type}")
        else:
            chart_type = default_chart_type
            if primary_type in ['yearly', 'monthly'] and len(data) == 1:
                chart_type = 'bar'
            print(f"DEBUG: Using default chart type: {chart_type}")
        
        return data, chart_type

    def remove_text_charts_from_response(self, response_text):
        if not response_text:
            return response_text
        
        patterns = [r'각\s*월별.*?차트로\s*나타낼\s*수\s*있습니다:.*?(?=\n\n|\n[^월"\d]|$)', r'\d+월:\s*[█▓▒░▬\*\-\|]+.*?(?=\n\n|\n[^월"\d]|$)', r'\n.*[█▓▒░▬\*\-\|]{2,}.*\n', r'```[^`]*[█▓▒░▬\*\-\|]{2,}[^`]*```']
        cleaned_response = response_text
        for pattern in patterns:
            cleaned_response = re.sub(pattern, '', cleaned_response, flags=re.MULTILINE | re.DOTALL)
        return re.sub(r'\n{3,}', '\n\n', cleaned_response).strip()

    def _extract_incident_id_sort_key(self, incident_id):
        if not incident_id:
            return 999999999999999
        try:
            return int(incident_id[3:]) if incident_id.startswith('INM') and len(incident_id) > 3 else hash(incident_id) % 999999999999999
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
                return (error_date, error_time_val, -self._extract_incident_id_sort_key(doc.get('incident_id', 'INM99999999999')))
            documents.sort(key=default_sort_key, reverse=True)
        except Exception:
            pass
        return documents

    def detect_sorting_requirements(self, query):
        sort_info = {'requires_custom_sort': False, 'sort_field': None, 'sort_direction': 'desc', 'sort_type': None, 'limit': None, 'secondary_sort': 'default'}
        if not query:
            return sort_info
        
        query_lower = query.lower()
        for pattern in [r'장애시간.*(?:가장.*?긴|긴.*?순|오래.*?걸린|최대|큰.*?순)', r'(?:최장|최대|가장.*?오래).*장애', r'top.*\d+.*장애시간']:
            if re.search(pattern, query_lower):
                sort_info.update({'requires_custom_sort': True, 'sort_field': 'error_time', 'sort_type': 'error_time', 'sort_direction': 'desc'})
                break
        
        top_match = re.search(r'top\s*(\d+)|상위\s*(\d+)', query_lower)
        if top_match:
            sort_info['limit'] = min(int(top_match.group(1) or top_match.group(2)), 50)
            if not sort_info['requires_custom_sort']:
                sort_info.update({'requires_custom_sort': True, 'sort_field': 'error_time', 'sort_type': 'error_time'})
        return sort_info

    def apply_custom_sorting(self, documents, sort_info):
        if not documents:
            return documents
        try:
            if sort_info['requires_custom_sort'] and sort_info['sort_type'] == 'error_time':
                def error_time_sort_key(doc):
                    try:
                        error_time_val = int(doc.get('error_time', 0) or 0)
                    except (ValueError, TypeError):
                        error_time_val = 0
                    error_date = doc.get('error_date', '1900-01-01')
                    incident_sort_key = self._extract_incident_id_sort_key(doc.get('incident_id', 'INM99999999999'))
                    return (-error_time_val, error_date, incident_sort_key) if sort_info['sort_direction'] == 'desc' else (error_time_val, error_date, incident_sort_key)
                documents.sort(key=error_time_sort_key)
                if sort_info['limit']:
                    documents = documents[:sort_info['limit']]
            else:
                self._apply_default_sorting(documents)
            return documents
        except Exception:
            return self._apply_default_sorting(documents)

    @traceable(name="generate_rag_response")
    def generate_rag_response_with_adaptive_processing(self, query, documents, query_type="default", time_conditions=None, department_conditions=None, reprompting_info=None):
        if not documents:
            return "검색된 문서가 없어서 답변을 제공할 수 없습니다."
        
        with trace(name="adaptive_rag_processing", inputs={"query": query, "document_count": len(documents)}) as trace_context:
            try:
                # 통계 쿼리인 경우 DB 직접 조회
                if query_type == "statistics":
                    return self._generate_statistics_response_from_db(query, documents)
                
                # 기존 처리 방식 (repair, cause, similar 등)
                unified_stats = self.calculate_unified_statistics(documents, query, query_type)
                chart_fig, chart_info = None, None
                
                requested_chart_type = self._extract_chart_type_from_query(query)
                print(f"DEBUG: Requested chart type from query: {requested_chart_type}")
                
                chart_keywords = ['차트', '그래프', '시각화', '그려', '그려줘', '보여줘', '시각적으로', '도표', '도식화']
                if any(keyword in query.lower() for keyword in chart_keywords) and unified_stats.get('total_count', 0) > 0:
                    chart_data, chart_type = self._get_chart_data_from_stats(unified_stats, requested_chart_type)
                    
                    print(f"DEBUG: Final chart_type selected: {chart_type}")
                    print(f"DEBUG: Chart data: {chart_data}")
                    
                    if chart_data and len(chart_data) > 0:
                        try:
                            chart_fig = self.chart_manager.create_chart(chart_type, chart_data, self._generate_chart_title(query, unified_stats))
                            if chart_fig:
                                chart_info = {'chart': chart_fig, 'chart_type': chart_type, 'chart_data': chart_data, 'chart_title': self._generate_chart_title(query, unified_stats), 'query': query, 'is_error_time_query': unified_stats.get('is_error_time_query', False)}
                                print(f"DEBUG: Chart created successfully with type: {chart_type}")
                        except Exception as e:
                            print(f"DEBUG: Chart creation failed: {e}")
                            import traceback
                            print(f"DEBUG: Traceback: {traceback.format_exc()}")
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
                final_query = reprompting_info.get('transformed_query', query) if reprompting_info and reprompting_info.get('transformed') else query
                
                context_parts = [f"""전체 문서 수: {len(processing_documents)}건
연도별 분포: {dict(sorted(unified_stats['yearly_stats'].items()))}
월별 분포: {unified_stats['monthly_stats']}""" + (f"\n데이터 유형: 장애시간 합산(분 단위)" if unified_stats['is_error_time_query'] else "")]
                
                for i, doc in enumerate(processing_documents[:30]):
                    context_parts.append(f"""문서 {i+1}:
장애 ID: {doc['incident_id']}
서비스명: {doc['service_name']}
장애시간: {doc['error_time']}
증상: {doc['symptom']}
복구방법: {doc['incident_repair']}
발생일자: {doc['error_date']}
""")
                
                user_prompt = f"""다음 장애 이력 문서들을 참고하여 질문에 답변해주세요.

**중요! 복구방법 관련:**
- 복구방법 질문에는 incident_repair 필드 데이터만 사용하세요
- incident_plan은 별도 참고용으로만 제공하세요

**중요! 정확한 집계:**
- 실제 제공된 문서 수: {len(processing_documents)}건
- 연도별: {dict(sorted(unified_stats['yearly_stats'].items()))}
- 월별: {unified_stats['monthly_stats']}
- 답변 시 실제 문서 수와 일치해야 함

{chr(10).join(context_parts)}

질문: {final_query}

답변:"""
                max_tokens = 2500 if query_type == 'inquiry' else 3000 if query_type == 'cause' else 1500
                response = self.azure_openai_client.chat.completions.create(model=self.model_name, messages=[{"role": "system", "content": SystemPrompts.get_prompt(query_type)}, {"role": "user", "content": user_prompt}], temperature=0.0, max_tokens=max_tokens)
                
                final_answer = response.choices[0].message.content
                return (final_answer, chart_info) if chart_info else final_answer
            except Exception as e:
                st.error(f"응답 생성 실패: {str(e)}")
                return "죄송합니다. 응답을 생성하는 중 오류가 발생했습니다."

    def _generate_statistics_response_from_db(self, query, documents):
        """DB 직접 조회를 통한 정확한 통계 응답 생성 - 가독성 개선된 형식 적용"""
        try:
            # 1. DB에서 정확한 통계 조회
            db_statistics = self.statistics_db_manager.get_statistics(query)
            
            # 디버그 모드에서 SQL 쿼리 정보 표시
            if self.debug_mode and db_statistics.get('debug_info'):
                debug_info = db_statistics['debug_info']
                
                with st.expander("🔍 SQL 쿼리 디버그 정보", expanded=False):
                    st.markdown("### 🔍 파싱된 조건")
                    st.json(debug_info['parsed_conditions'])
                    
                    st.markdown("### 💾 실행된 SQL 쿼리")
                    st.code(debug_info['sql_query'], language='sql')
                    
                    st.markdown("### 🔢 SQL 파라미터")
                    st.json(list(debug_info['sql_params']))
                    
                    st.markdown("### 📊 쿼리 결과")
                    st.info(f"총 {debug_info['result_count']}개의 결과 반환")
                    
                    if db_statistics.get('results'):
                        st.markdown("#### 결과 샘플 (최대 5개)")
                        st.json(db_statistics['results'][:5])
            
            # 2. 조건 분석
            conditions = db_statistics['query_conditions']
            
            # 3. 필터링된 데이터만 사용하도록 통계 재구성
            filtered_statistics = self._filter_statistics_by_conditions(db_statistics, conditions)
            
            # 4. 조건에 맞는 상세 문서 조회
            incident_details = self.statistics_db_manager.get_incident_details(conditions, limit=100)
            
            # 5. 차트 생성
            chart_fig, chart_info = None, None
            requested_chart_type = self._extract_chart_type_from_query(query)
            
            chart_keywords = ['차트', '그래프', '시각화', '그려', '그려줘', '보여줘', '시각적으로', '도표', '도식화']
            if any(keyword in query.lower() for keyword in chart_keywords):
                chart_data, chart_type = self._get_chart_data_from_db_stats(filtered_statistics, requested_chart_type)
                
                if chart_data and len(chart_data) > 0:
                    try:
                        chart_fig = self.chart_manager.create_chart(
                            chart_type, 
                            chart_data, 
                            self._generate_chart_title_from_db_stats(query, filtered_statistics)
                        )
                        if chart_fig:
                            chart_info = {
                                'chart': chart_fig,
                                'chart_type': chart_type,
                                'chart_data': chart_data,
                                'chart_title': self._generate_chart_title_from_db_stats(query, filtered_statistics),
                                'query': query,
                                'is_error_time_query': filtered_statistics['is_error_time_query']
                            }
                    except Exception as e:
                        print(f"차트 생성 실패: {e}")
            
            # 6. LLM에 전달할 프롬프트 구성 - 개선된 포맷 사용
            statistics_summary = self._format_db_statistics_for_prompt(filtered_statistics, conditions)
            incident_list = self._format_incident_details_for_prompt(incident_details[:50])
            
            # 7. 요청 범위를 명확히 파악
            query_scope = self._determine_query_scope(conditions)
            
            system_prompt = f"""당신은 IT 시스템 장애 통계 전문가입니다.
    사용자의 질문 범위를 정확히 파악하여 **요청된 범위의 데이터만** 답변하세요.

    ## 🎯 사용자 요청 범위
    {query_scope}

    ## 📊 가독성 있는 통계 표시 형식 지침
    사용자가 요청한 통계 유형에 따라 다음 형식을 정확히 따르세요:

    **연도별 통계:**
    * **2020년: 37건**
    * **2021년: 58건**
    * **2022년: 60건**
    **💡 총 합계: 316건**

    **월별 통계:**
    * **1월: X건**
    * **2월: Y건**
    * **3월: Z건**
    **💡 총 합계: N건**

    **요일별 통계:**
    * **월요일: X건**
    * **화요일: Y건**
    * **수요일: Z건**
    **💡 총 합계: N건**

    **원인유형별 통계:**
    * **제품결함: X건**
    * **수행 실수: Y건**
    * **환경설정오류: Z건**
    **💡 총 합계: N건**

    **서비스별 통계:**
    * **ERP: X건**
    * **KOS-오더: Y건**
    * **API_Link: Z건**
    **💡 총 합계: N건**

    ## 절대 규칙
    1. **사용자가 요청한 범위의 데이터만 답변하세요**
    2. 요청하지 않은 연도나 기간의 데이터는 절대 포함하지 마세요
    3. 제공된 통계 수치를 절대 변경하지 마세요
    4. 추가 계산이나 추정을 하지 마세요
    5. **리스트 형태로 통계를 표시하고 총 합계를 명확히 표시하세요**

    ## 응답 형식
    1. **📊 {query_scope} 통계 요약** (2-3문장)
    2. **📈 상세 통계** (위 형식에 따른 리스트 표시)
    3. **📋 근거 문서 내역**

    답변은 명확하고 구조화된 형식으로 작성하되, 제공된 수치를 정확히 인용하세요.
    """

            user_prompt = f"""## 사용자 질문
    {query}

    ## 요청 범위: {query_scope}

    ## 정확하게 계산된 통계 데이터 ({query_scope} 범위만)
    {statistics_summary}

    ## 근거가 되는 장애 문서 상세 내역 (총 {len(incident_details)}건)
    {incident_list}

    위 데이터를 바탕으로 **{query_scope} 범위만** 명확하고 친절하게 답변하세요.
    반드시 다음 구조를 따르세요:

    1. **📊 {query_scope} 통계 요약**
    - 핵심 수치와 인사이트 (2-3문장)

    2. **📈 상세 통계**
    [위에서 지정한 리스트 형식에 따라 표시]
    **💡 총 합계: [전체 합계]**

    3. **📋 근거 문서 내역 (총 {len(incident_details)}건)**

    아래는 통계로 집계된 장애 건들입니다:

    [모든 문서를 번호 순서대로 상세히 나열]

    ⚠️ 중요: 요청하지 않은 연도나 기간의 통계는 절대 포함하지 마세요.
    """

            # 8. LLM 호출
            response = self.azure_openai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0,
                max_tokens=5000
            )
            
            final_answer = response.choices[0].message.content
            
            return (final_answer, chart_info) if chart_info else final_answer
            
        except Exception as e:
            print(f"ERROR: 통계 응답 생성 실패: {e}")
            import traceback
            traceback.print_exc()
            return f"통계 조회 중 오류가 발생했습니다: {str(e)}"
    
    def _filter_statistics_by_conditions(self, db_stats, conditions):
        """조건에 맞는 통계만 필터링"""
        filtered_stats = db_stats.copy()
        
        # 연도 필터링
        if conditions.get('year'):
            requested_year = conditions['year']
            
            if filtered_stats['yearly_stats']:
                filtered_stats['yearly_stats'] = {
                    k: v for k, v in filtered_stats['yearly_stats'].items() 
                    if requested_year in k
                }
            
            if requested_year in str(filtered_stats.get('yearly_stats', {})):
                year_key = f"{requested_year}"
                if year_key in filtered_stats.get('yearly_stats', {}):
                    filtered_stats['total_value'] = filtered_stats['yearly_stats'][year_key]
        
        # 월 필터링
        if conditions.get('months'):
            requested_months = conditions['months']
            
            if filtered_stats['monthly_stats']:
                filtered_stats['monthly_stats'] = {
                    k: v for k, v in filtered_stats['monthly_stats'].items()
                    if k in requested_months
                }
            
            if filtered_stats['monthly_stats']:
                filtered_stats['total_value'] = sum(filtered_stats['monthly_stats'].values())
        
        return filtered_stats
    
    def _determine_query_scope(self, conditions):
        """사용자 요청 범위 결정"""
        scope_parts = []
        
        if conditions.get('year'):
            scope_parts.append(conditions['year'])
        
        if conditions.get('months'):
            months = [m.replace('월', '') for m in conditions['months']]
            if len(months) == 1:
                scope_parts.append(f"{months[0]}월")
            elif len(months) > 1:
                scope_parts.append(f"{months[0]}~{months[-1]}월")
        
        if conditions.get('daynight'):
            scope_parts.append(conditions['daynight'])
        
        if conditions.get('week'):
            week_val = conditions['week']
            if week_val not in ['평일', '주말']:
                scope_parts.append(f"{week_val}요일")
            else:
                scope_parts.append(week_val)
        
        if conditions.get('incident_grade'):
            scope_parts.append(conditions['incident_grade'])
        
        if conditions.get('service_name'):
            scope_parts.append(f"'{conditions['service_name']}' 서비스")
        
        if conditions.get('owner_depart'):
            scope_parts.append(f"'{conditions['owner_depart']}' 부서")
        
        return ' '.join(scope_parts) if scope_parts else "전체 기간"
    
    def _format_db_statistics_for_prompt(self, db_stats, conditions):
        """DB 통계를 프롬프트용 텍스트로 변환 - 가독성 있는 리스트 형태로 개선"""
        lines = []
        
        value_type = "장애시간(분)" if db_stats['is_error_time_query'] else "발생건수"
        query_scope = self._determine_query_scope(conditions)
        
        lines.append(f"**요청 범위**: {query_scope}")
        lines.append(f"**데이터 유형**: {value_type}")
        lines.append(f"**총 {value_type}**: {db_stats['total_value']}")
        
        # 연도별 통계 - 가독성 있는 형태로 표시
        if db_stats['yearly_stats']:
            lines.append(f"\n**📅 연도별 {value_type}**:")
            for year, value in sorted(db_stats['yearly_stats'].items()):
                lines.append(f"* **{year}: {value}건**")
            lines.append(f"\n**💡 총 합계: {sum(db_stats['yearly_stats'].values())}건**")
        
        # 월별 통계 - 가독성 있는 형태로 표시
        if db_stats['monthly_stats']:
            lines.append(f"\n**📅 월별 {value_type}**:")
            # 월 순서대로 정렬
            sorted_months = sorted(db_stats['monthly_stats'].items(), key=lambda x: int(x[0].replace('월', '')))
            for month, value in sorted_months:
                lines.append(f"* **{month}: {value}건**")
            lines.append(f"\n**💡 총 합계: {sum(db_stats['monthly_stats'].values())}건**")
        
        # 시간대별 통계
        if db_stats['time_stats']['daynight']:
            lines.append(f"\n**🕐 시간대별 {value_type}**:")
            for time, value in db_stats['time_stats']['daynight'].items():
                lines.append(f"* **{time}: {value}건**")
            lines.append(f"\n**💡 총 합계: {sum(db_stats['time_stats']['daynight'].values())}건**")
        
        # 요일별 통계 - 요일 순서대로 정렬
        if db_stats['time_stats']['week']:
            lines.append(f"\n**📅 요일별 {value_type}**:")
            # 요일 순서 정의
            week_order = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']
            week_stats = db_stats['time_stats']['week']
            
            # 순서대로 표시
            for day in week_order:
                if day in week_stats:
                    lines.append(f"* **{day}: {week_stats[day]}건**")
            
            # 평일/주말이 있는 경우 추가
            if '평일' in week_stats:
                lines.append(f"* **평일: {week_stats['평일']}건**")
            if '주말' in week_stats:
                lines.append(f"* **주말: {week_stats['주말']}건**")
                
            lines.append(f"\n**💡 총 합계: {sum(week_stats.values())}건**")
        
        # 부서별 통계 - 상위 10개
        if db_stats['department_stats']:
            lines.append(f"\n**🏢 부서별 {value_type} (상위 10개)**:")
            sorted_depts = sorted(db_stats['department_stats'].items(), key=lambda x: x[1], reverse=True)[:10]
            for dept, value in sorted_depts:
                lines.append(f"* **{dept}: {value}건**")
            lines.append(f"\n**💡 상위 10개 합계: {sum(value for _, value in sorted_depts)}건**")
        
        # 서비스별 통계 - 상위 10개
        if db_stats['service_stats']:
            lines.append(f"\n**💻 서비스별 {value_type} (상위 10개)**:")
            sorted_services = sorted(db_stats['service_stats'].items(), key=lambda x: x[1], reverse=True)[:10]
            for service, value in sorted_services:
                lines.append(f"* **{service}: {value}건**")
            lines.append(f"\n**💡 상위 10개 합계: {sum(value for _, value in sorted_services)}건**")
        
        # 등급별 통계 - 등급 순서대로
        if db_stats['grade_stats']:
            lines.append(f"\n**⚠️ 장애등급별 {value_type}**:")
            grade_order = ['1등급', '2등급', '3등급', '4등급']
            grade_stats = db_stats['grade_stats']
            
            for grade in grade_order:
                if grade in grade_stats:
                    lines.append(f"* **{grade}: {grade_stats[grade]}건**")
            
            # 다른 등급이 있는 경우 추가
            for grade, value in sorted(grade_stats.items()):
                if grade not in grade_order:
                    lines.append(f"* **{grade}: {value}건**")
                    
            lines.append(f"\n**💡 총 합계: {sum(grade_stats.values())}건**")
        
        # 원인유형별 통계 - 상위 10개, 많은 순서로
        if db_stats['cause_type_stats']:
            lines.append(f"\n**🔍 원인유형별 {value_type} (상위 10개)**:")
            sorted_causes = sorted(db_stats['cause_type_stats'].items(), key=lambda x: x[1], reverse=True)[:10]
            for cause, value in sorted_causes:
                lines.append(f"* **{cause}: {value}건**")
            lines.append(f"\n**💡 상위 10개 합계: {sum(value for _, value in sorted_causes)}건**")
        
        lines.append(f"\n⚠️ **중요**: 위 통계는 모두 '{query_scope}' 범위의 데이터입니다.")
        
        return '\n'.join(lines)
    
    def _format_incident_details_for_prompt(self, incidents):
        """장애 상세 내역을 프롬프트용 텍스트로 변환 - 등급과 요일 형식 개선"""
        lines = []
        
        # 요일 매핑
        week_mapping = {
            '월': '월요일',
            '화': '화요일', 
            '수': '수요일',
            '목': '목요일',
            '금': '금요일',
            '토': '토요일',
            '일': '일요일'
        }
        
        for i, incident in enumerate(incidents, 1):
            lines.append(f"### {i}. 장애 ID: {incident.get('incident_id', 'N/A')}")
            lines.append(f"- 서비스명: {incident.get('service_name', 'N/A')}")
            lines.append(f"- 발생일자: {incident.get('error_date', 'N/A')}")
            lines.append(f"- 장애시간: {incident.get('error_time', 0)}분")
            
            # 장애등급 포맷팅 (숫자에 "등급" 추가)
            incident_grade = incident.get('incident_grade', 'N/A')
            if incident_grade and incident_grade != 'N/A':
                if incident_grade.isdigit():
                    formatted_grade = f"{incident_grade}등급"
                elif '등급' not in incident_grade:
                    formatted_grade = f"{incident_grade}등급"
                else:
                    formatted_grade = incident_grade
            else:
                formatted_grade = 'N/A'
            lines.append(f"- 장애등급: {formatted_grade}")
            
            lines.append(f"- 담당부서: {incident.get('owner_depart', 'N/A')}")
            
            if incident.get('daynight'):
                lines.append(f"- 시간대: {incident.get('daynight')}")
                
            # 요일 포맷팅 (단축형을 전체형으로 변환)
            if incident.get('week'):
                week_value = incident.get('week')
                formatted_week = week_mapping.get(week_value, week_value)
                lines.append(f"- 요일: {formatted_week}")
            
            symptom = incident.get('symptom', '')
            if symptom:
                lines.append(f"- 장애현상: {symptom[:150]}...")
            
            root_cause = incident.get('root_cause', '')
            if root_cause:
                lines.append(f"- 장애원인: {root_cause[:150]}...")
            
            lines.append("")
        
        return '\n'.join(lines)
    
    def _get_chart_data_from_db_stats(self, db_stats, requested_chart_type=None):
        """DB 통계에서 차트 데이터 추출"""
        conditions = db_stats['query_conditions']
        group_by = conditions.get('group_by', [])
        
        if 'year' in group_by and db_stats['yearly_stats']:
            data = db_stats['yearly_stats']
            default_chart_type = 'line'
        elif 'month' in group_by and db_stats['monthly_stats']:
            data = db_stats['monthly_stats']
            default_chart_type = 'line'
        elif 'daynight' in group_by and db_stats['time_stats']['daynight']:
            data = db_stats['time_stats']['daynight']
            default_chart_type = 'bar'
        elif 'week' in group_by and db_stats['time_stats']['week']:
            data = db_stats['time_stats']['week']
            default_chart_type = 'bar'
        elif 'owner_depart' in group_by and db_stats['department_stats']:
            data = dict(sorted(db_stats['department_stats'].items(), key=lambda x: x[1], reverse=True)[:10])
            default_chart_type = 'horizontal_bar'
        elif 'service_name' in group_by and db_stats['service_stats']:
            data = dict(sorted(db_stats['service_stats'].items(), key=lambda x: x[1], reverse=True)[:10])
            default_chart_type = 'horizontal_bar'
        elif 'incident_grade' in group_by and db_stats['grade_stats']:
            data = db_stats['grade_stats']
            default_chart_type = 'pie'
        elif 'cause_type' in group_by and db_stats['cause_type_stats']:
            data = dict(sorted(db_stats['cause_type_stats'].items(), key=lambda x: x[1], reverse=True)[:10])
            default_chart_type = 'horizontal_bar'
        else:
            data = db_stats['yearly_stats'] or db_stats['monthly_stats']
            default_chart_type = 'line'
        
        chart_type = requested_chart_type or default_chart_type
        
        if default_chart_type == 'line' and len(data) == 1:
            chart_type = 'bar'
        
        return data, chart_type
    
    def _generate_chart_title_from_db_stats(self, query, db_stats):
        """DB 통계 기반 차트 제목 생성"""
        conditions = db_stats['query_conditions']
        group_by = conditions.get('group_by', [])
        
        title_parts = []
        
        if conditions.get('year'):
            title_parts.append(conditions['year'])
        
        if 'year' in group_by:
            title_parts.append("연도별")
        elif 'month' in group_by:
            title_parts.append("월별")
        elif 'daynight' in group_by:
            title_parts.append("시간대별")
        elif 'week' in group_by:
            title_parts.append("요일별")
        elif 'owner_depart' in group_by:
            title_parts.append("부서별")
        elif 'service_name' in group_by:
            title_parts.append("서비스별")
        elif 'incident_grade' in group_by:
            title_parts.append("등급별")
        elif 'cause_type' in group_by:
            title_parts.append("원인유형별")
        
        if db_stats['is_error_time_query']:
            title_parts.append("장애시간")
        else:
            title_parts.append("장애 발생 현황")
        
        return ' '.join(title_parts)

    def _display_response_with_marker_conversion(self, response, chart_info=None):
        if not response:
            st.write("응답이 없습니다.")
            return
        
        response_text, chart_info = response if isinstance(response, tuple) else (response, chart_info)
        if chart_info and chart_info.get('chart'):
            response_text = self.remove_text_charts_from_response(response_text)
        
        converted_content, html_converted = response_text, False
        if '[REPAIR_BOX_START]' in converted_content:
            converted_content, has_html = self.ui_components.convert_repair_box_to_html(converted_content)
            html_converted = html_converted or has_html
        if '[CAUSE_BOX_START]' in converted_content:
            converted_content, has_html = self.ui_components.convert_cause_box_to_html(converted_content)
            html_converted = html_converted or has_html
        
        if html_converted:
            st.markdown(converted_content, unsafe_allow_html=True)
        else:
            st.write(converted_content)
        
        if chart_info and chart_info.get('chart'):
            st.markdown("---")
            try:
                self.chart_manager.display_chart_with_data(chart_info['chart'], chart_info['chart_data'], chart_info['chart_type'], chart_info.get('query', ''))
            except Exception as e:
                st.error(f"차트 표시 중 오류: {str(e)}")

    @traceable(name="process_user_query")
    def process_query(self, query, query_type=None):
        if not query:
            st.error("질문을 입력해주세요.")
            return
        
        # 새로운 쿼리 시작 시 로깅 플래그 초기화 (중복 로깅 방지)
        if not hasattr(st.session_state, 'current_query_logged'):
            st.session_state.current_query_logged = False
        st.session_state.current_query_logged = False
        
        start_time = time.time()
        response_text = None
        document_count = 0
        error_message = None
        success = False
        
        with st.chat_message("assistant"):
            try:
                # 🔥 1단계: 강제 치환 먼저 적용 🔥
                original_query = query
                force_replaced_query = self.force_replace_problematic_queries(query)
                
                # 강제 치환이 발생한 경우 알림
                if force_replaced_query != original_query:
                    if self.debug_mode:
                        st.info(f"🔄 쿼리 강제 치환: '{original_query}' → '{force_replaced_query}'")
                    # 치환된 쿼리로 계속 진행
                    query = force_replaced_query
                
                # 2단계: 리프롬프팅 체크 (강제 치환 결과 포함)
                reprompting_info = self.check_and_transform_query_with_reprompting(query)
                processing_query = reprompting_info.get('transformed_query', query)
                
                # 3단계: 나머지 처리 로직 (기존과 동일)
                time_conditions = self.extract_time_conditions(processing_query)
                department_conditions = self.extract_department_conditions(processing_query)
                
                if query_type is None:
                    with st.spinner("🔍 질문 분석 중..."):
                        query_type = self.classify_query_type_with_llm(processing_query)
                
                target_service_name = self.search_manager.extract_service_name_from_query(processing_query)
                
                with st.spinner("📄 문서 검색 중..."):
                    documents = self.search_manager.semantic_search_with_adaptive_filtering(processing_query, target_service_name, query_type) or []
                    document_count = len(documents)
                    
                    if documents:
                        with st.expander("📄 매칭된 문서 상세 보기"):
                            self.ui_components.display_documents_with_quality_info(documents)
                        
                        with st.spinner("🤖 AI 답변 생성 중..."):
                            response = self.generate_rag_response_with_adaptive_processing(query, documents, query_type, time_conditions, department_conditions, reprompting_info)
                            
                            if response:
                                response_text = response[0] if isinstance(response, tuple) else response
                                
                                # 답변 성공 여부 판단
                                success = self._is_successful_response(response_text, document_count)
                                if not success:
                                    error_message = self._get_failure_reason(response_text, document_count)
                                
                                self._display_response_with_marker_conversion(response)
                                st.session_state.messages.append({"role": "assistant", "content": response_text})
                            else:
                                response_text = "죄송합니다. 응답을 생성할 수 없습니다."
                                success = False
                                error_message = "응답 생성 실패"
                                st.write(response_text)
                                st.session_state.messages.append({"role": "assistant", "content": response_text})
                    else:
                        with st.spinner("📄 추가 검색 중..."):
                            fallback_documents = self.search_manager.search_documents_fallback(processing_query, target_service_name)
                            document_count = len(fallback_documents)
                            
                            if fallback_documents:
                                response = self.generate_rag_response_with_adaptive_processing(query, fallback_documents, query_type, time_conditions, department_conditions, reprompting_info)
                                response_text = response[0] if isinstance(response, tuple) else response
                                
                                success = self._is_successful_response(response_text, document_count)
                                if not success:
                                    error_message = self._get_failure_reason(response_text, document_count)
                                
                                self._display_response_with_marker_conversion(response)
                                st.session_state.messages.append({"role": "assistant", "content": response_text})
                            else:
                                response_text = f"'{target_service_name or '해당 조건'}'에 해당하는 문서를 찾을 수 없습니다."
                                success = False
                                error_message = "관련 문서 검색 실패"
                                st.write(response_text)
                                st.session_state.messages.append({"role": "assistant", "content": response_text})
                                
            except Exception as e:
                response_time = time.time() - start_time
                error_message = str(e)[:50] + ("..." if len(str(e)) > 50 else "")
                success = False
                response_text = f"쿼리 처리 중 오류가 발생했습니다: {str(e)}"
                st.error(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
                
                # 예외 발생 시 중복 로깅 방지하여 로깅
                if not st.session_state.current_query_logged and self.monitoring_enabled and self._manual_logging_enabled:
                    self._log_query_activity(
                        query=query,
                        query_type=query_type,
                        response_time=response_time,
                        document_count=document_count,
                        success=success,
                        error_message=error_message,
                        response_content=response_text
                    )
                    st.session_state.current_query_logged = True
                return
            
            # 정상 처리 완료 시 중복 로깅 방지하여 로깅
            response_time = time.time() - start_time
            if not st.session_state.current_query_logged and self.monitoring_enabled and self._manual_logging_enabled:
                self._log_query_activity(
                    query=query,
                    query_type=query_type,
                    response_time=response_time,
                    document_count=document_count,
                    success=success,
                    error_message=error_message,
                    response_content=response_text
                )
                st.session_state.current_query_logged = True

    def _is_successful_response(self, response_text: str, document_count: int) -> bool:
        """응답이 성공적인지 판단 (RAG 기반 답변 여부 포함)"""
        if not response_text or response_text.strip() == "":
            return False
        
        # 실패 패턴 검사
        failure_patterns = [
            r"해당.*조건.*문서.*찾을 수 없습니다",
            r"검색된 문서가 없어서 답변을 제공할 수 없습니다",
            r"관련 정보를 찾을 수 없습니다",
            r"문서를 찾을 수 없습니다",
            r"답변을 생성할 수 없습니다",
            r"죄송합니다.*오류가 발생했습니다",
            r"처리 중 오류가 발생했습니다",
            r"연결에 실패했습니다",
            r"서비스를 이용할 수 없습니다",
            r"오류가 발생했습니다"
        ]
        
        for pattern in failure_patterns:
            if re.search(pattern, response_text, re.IGNORECASE):
                return False
        
        # 응답이 너무 짧은 경우
        if len(response_text.strip()) < 10:
            return False
        
        # 문서 수가 0인 경우
        if document_count == 0:
            return False
        
        # RAG 기반 답변인지 판단 (핵심 추가 검증)
        if not self._is_rag_based_response(response_text, document_count):
            return False
        
        return True

    def _is_rag_based_response(self, response_text: str, document_count: int = None) -> bool:
        """RAG 원천 데이터 기반 답변인지 판단"""
        
        if not response_text:
            return False
        
        response_lower = response_text.lower()
        
        # 1. 문서 수가 매우 적은 경우 (2개 미만)
        if document_count is not None and document_count < 2:
            return False
        
        # 2. RAG 기반 답변의 특징적 마커들 확인
        rag_markers = [
            '[repair_box_start]', '[cause_box_start]', 
            'case1', 'case2', 'case3',
            '장애 id', 'incident_id', 'service_name',
            '복구방법:', '장애원인:', '서비스명:',
            '발생일시:', '장애시간:', '담당부서:',
            '참조장애정보', '장애등급:', 'inm2'
        ]
        
        rag_marker_count = sum(1 for marker in rag_markers if marker in response_lower)
        
        # 3. RAG 기반 답변에 자주 나타나는 패턴들
        rag_patterns = [
            r'장애\s*id\s*:\s*inm\d+',  # INM으로 시작하는 장애 ID
            r'서비스명\s*:\s*\w+',       # 서비스명: 패턴
            r'발생일[시자]\s*:\s*\d{4}', # 발생일시: 년도 패턴
            r'장애시간\s*:\s*\d+분',     # 장애시간: 숫자분 패턴
            r'복구방법\s*:\s*',          # 복구방법: 패턴
            r'장애원인\s*:\s*',          # 장애원인: 패턴
            r'\d+등급',                 # X등급 패턴
            r'incident_repair',         # incident_repair 필드 언급
            r'error_date',              # error_date 필드 언급
            r'case\d+\.',               # Case1. Case2. 패턴
        ]
        
        rag_pattern_count = sum(1 for pattern in rag_patterns if re.search(pattern, response_lower))
        
        # 4. 일반적인 답변 패턴들 (RAG가 아닌 일반 지식 기반)
        general_patterns = [
            r'일반적으로\s+',
            r'보통\s+',
            r'대부분\s+',
            r'흔히\s+',
            r'주로\s+',
            r'다음과\s+같은\s+방법',
            r'다음\s+단계',
            r'기본적인\s+',
            r'표준적인\s+',
            r'권장사항',
            r'best\s+practice',
            r'모범\s+사례',
            r'다음과\s+같이\s+접근',
            r'시스템\s+관리자',
            r'네트워크\s+관리',
            r'서버\s+관리',
        ]
        
        general_pattern_count = sum(1 for pattern in general_patterns if re.search(pattern, response_lower))
        
        # 5. RAG 답변에서 흔히 사용되지 않는 일반적 표현들
        non_rag_keywords = [
            '일반적으로', '보통', '대부분', '흔히', '주로',
            '기본적으로', '표준적으로', '권장사항', '모범사례',
            '다음과 같은 방법', '다음 단계', '기본적인 점검',
            '시스템 관리', '네트워크 관리', '서버 관리',
            '일반적인 해결책', '표준 절차', '기본 원칙',
            '다음과 같은 조치', '기본적인 순서'
        ]
        
        non_rag_keyword_count = sum(1 for keyword in non_rag_keywords if keyword in response_lower)
        
        # 6. 특정 질문 유형별 RAG 기반 판단
        statistics_indicators = ['건수', '통계', '현황', '분포', '년도별', '월별', '차트']
        statistics_count = sum(1 for indicator in statistics_indicators if indicator in response_lower)
        
        # 7. 판단 로직
        print(f"DEBUG RAG 판단: rag_markers={rag_marker_count}, rag_patterns={rag_pattern_count}, general_patterns={general_pattern_count}, non_rag_keywords={non_rag_keyword_count}")
        
        # RAG 마커나 패턴이 충분히 있으면 RAG 기반으로 판단
        if rag_marker_count >= 3 or rag_pattern_count >= 2:
            return True
        
        # 통계 관련 답변이고 통계 지표가 있으면 RAG 기반으로 판단
        if statistics_count >= 2 and any(word in response_lower for word in ['차트', '표', '이', '합계']):
            return True
        
        # 일반적 표현이 많고 RAG 특징이 적으면 일반 답변으로 판단
        if general_pattern_count >= 2 or non_rag_keyword_count >= 3:
            if rag_marker_count == 0 and rag_pattern_count == 0:
                print(f"DEBUG: 일반적 답변으로 판단됨 (general_pattern_count={general_pattern_count}, non_rag_keyword_count={non_rag_keyword_count})")
                return False
        
        # RAG 마커가 하나라도 있으면 RAG 기반으로 판단
        if rag_marker_count > 0 or rag_pattern_count > 0:
            return True
        
        # 응답이 길고 구체적이면서 문서가 충분히 있으면 RAG 기반으로 판단
        if len(response_text) > 200 and document_count and document_count >= 3:
            # 하지만 일반적 표현이 너무 많으면 제외
            if non_rag_keyword_count < 2:
                return True
        
        # 기본적으로 일반 답변으로 판단
        print(f"DEBUG: 기본적으로 일반 답변으로 판단됨")
        return False

    def _get_failure_reason(self, response_text: str, document_count: int) -> str:
        """실패 원인 분석 (RAG 기반 여부 포함)"""
        if not response_text or response_text.strip() == "":
            return "응답 내용 없음"
        
        if document_count == 0:
            return "관련 문서 검색 실패"
        
        if len(response_text.strip()) < 10:
            return "응답 길이 부족"
        
        # 특정 실패 패턴 매칭
        if re.search(r"해당.*조건.*문서.*찾을 수 없습니다", response_text, re.IGNORECASE):
            return "조건 맞는 문서 없음"
        
        if re.search(r"검색된 문서가 없어서", response_text, re.IGNORECASE):
            return "검색 결과 없음"
        
        if re.search(r"오류가 발생했습니다", response_text, re.IGNORECASE):
            return "시스템 오류 발생"
        
        if re.search(r"답변을 생성할 수 없습니다", response_text, re.IGNORECASE):
            return "답변 생성 실패"
        
        # RAG 기반이 아닌 일반 답변인 경우 (핵심 추가 검증)
        if not self._is_rag_based_response(response_text, document_count):
            return "RAG 기반 답변 아님"
        
        return "적절한 답변 생성 실패"
    
    def _log_query_activity(self, query: str, query_type: str = None, response_time: float = None,
                        document_count: int = None, success: bool = None, 
                        error_message: str = None, response_content: str = None):
        """쿼리 활동 로깅 - 중복 방지 기능 추가"""
        try:
            # 중복 로깅 방지: 데코레이터 로깅이 활성화된 경우 수동 로깅 스킵
            if hasattr(self, '_decorator_logging_enabled') and self._decorator_logging_enabled:
                print(f"DEBUG: 데코레이터 로깅이 활성화되어 수동 로깅을 건너뜁니다.")
                return
                
            # 수동 로깅이 비활성화된 경우 스킵
            if hasattr(self, '_manual_logging_enabled') and not self._manual_logging_enabled:
                print(f"DEBUG: 수동 로깅이 비활성화되어 로깅을 건너뜁니다.")
                return
            
            # 세션 기반 중복 로깅 방지
            if hasattr(st.session_state, 'current_query_logged') and st.session_state.current_query_logged:
                print(f"DEBUG: 현재 쿼리가 이미 로깅되어 중복 로깅을 방지합니다.")
                return
                
            if self.monitoring_manager:
                # IP 주소 가져오기 (세션에서 설정된 경우 사용, 없으면 기본값)
                ip_address = getattr(st.session_state, 'client_ip', '127.0.0.1')
                
                self.monitoring_manager.log_user_activity(
                    ip_address=ip_address,
                    question=query,
                    query_type=query_type,
                    user_agent="Streamlit/ChatBot",
                    response_time=response_time,
                    document_count=document_count,
                    success=success,
                    error_message=error_message,
                    response_content=response_content
                )
                
                # 로깅 완료 표시
                if hasattr(st.session_state, 'current_query_logged'):
                    st.session_state.current_query_logged = True
                    
                print(f"DEBUG: 쿼리 로깅 완료 - Query: {query[:50]}..., Success: {success}")
                
        except Exception as e:
            print(f"모니터링 로그 실패: {str(e)}")  # 로깅 실패해도 메인 기능에는 영향 없음

    def force_replace_problematic_queries(self, query):
        """문제가 되는 표현들을 정상 작동하는 표현으로 강제 치환 - 복구방법 질문 보호"""
        if not query:
            return query
        
        original_query = query
        query_lower = query.lower()
        
        # 1단계: 복구방법/문제해결 관련 질문은 치환하지 않음 (보호)
        protection_keywords = [
            '복구방법', '해결방법', '조치방법', '대응방법', '복구절차',
            '복구', '해결', '조치', '대응', '수정', '개선',
            '불가', '실패', '안됨', '안되', '되지않', '오류', '에러', 
            '문제', '장애', '이슈', '버그', '원인', '이유', '왜',
            '유사', '비슷한', '같은', '동일한'
        ]
        
        is_protected = any(keyword in query_lower for keyword in protection_keywords)
        if is_protected:
            if self.debug_mode:
                print(f"🔒 PROTECTED QUERY: 복구/문제해결 관련 질문으로 판단되어 치환하지 않음")
            return query
        
        # 2단계: 순수 통계 질문만 치환 적용
        pure_statistics_indicators = [
            '건수', '통계', '현황', '분포', '몇건', '개수', 
            '연도별', '월별', '등급별', '요일별', '시간대별',
            '알려줘', '보여줘', '말해줘', '확인해줘'
        ]
        
        has_statistics_intent = any(indicator in query_lower for indicator in pure_statistics_indicators)
        if not has_statistics_intent:
            if self.debug_mode:
                print(f"📋 NON-STATISTICS QUERY: 통계 의도가 없어 치환하지 않음")
            return query
        
        # 3단계: 기존 강제 치환 규칙 적용 (통계 질문만)
        # ... (기존 replacement_rules 코드 동일) ...
        
        # 나머지 기존 코드와 동일
        # (서비스명, 연도, 월, 시간대, 요일 정보 보존 로직)
        
        return modified_query