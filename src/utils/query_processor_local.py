import streamlit as st
import re
import time
import os
from datetime import datetime
from config.prompts import SystemPrompts
from config.settings_local import AppConfigLocal
from utils.search_utils_local import SearchManagerLocal
from utils.ui_components_local import UIComponentsLocal
from utils.reprompting_db_manager import RepromptingDBManager
from utils.chart_utils import ChartManager
from utils.statistics_db_manager import StatisticsDBManager
from utils.filter_manager import DocumentFilterManager, QueryType

try:
    from utils.monitoring_manager import MonitoringManager
    MONITORING_AVAILABLE = True
except ImportError:
    MONITORING_AVAILABLE = False
    class MonitoringManager:
        def __init__(self, *args, **kwargs): pass
        def log_user_activity(self, *args, **kwargs): pass

class DataIntegrityNormalizer:
    """🚨 RAG 데이터 무결성 절대 보장 정규화 클래스"""
    
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
                        if parts[0].isdigit() and len(parts[0]) == 4 and not normalized_doc.get('year'):
                            normalized_doc['year'] = parts[0]
                        elif parts[0].isdigit() and len(parts[0]) == 2 and not normalized_doc.get('year'):
                            # 모든 2자리 연도를 2000년대로 처리
                            short_year = int(parts[0])
                            if 0 <= short_year <= 99:
                                normalized_doc['year'] = f"20{short_year:02d}"
                        if parts[1].isdigit():
                            month_num = int(parts[1])
                            if 1 <= month_num <= 12 and not normalized_doc.get('month'):
                                normalized_doc['month'] = str(month_num)
                elif len(error_date_str) >= 8 and error_date_str.isdigit():
                    if not normalized_doc.get('year'):
                        normalized_doc['year'] = error_date_str[:4]
                    try:
                        month_num = int(error_date_str[4:6])
                        if 1 <= month_num <= 12 and not normalized_doc.get('month'):
                            normalized_doc['month'] = str(month_num)
                    except (ValueError, TypeError):
                        pass
            except (ValueError, TypeError):
                pass
        
        return normalized_doc
    
    @staticmethod
    def preserve_original_fields(doc):
        preserved_doc = doc.copy()
        critical_fields = [
            'incident_id', 'service_name', 'symptom', 'root_cause', 
            'incident_repair', 'incident_plan', 'effect', 'error_date',
            'incident_grade', 'owner_depart', 'daynight', 'week',
            'cause_type', 'done_type'
        ]
        
        for field in critical_fields:
            original_value = doc.get(field)
            if original_value is not None:
                preserved_doc[field] = str(original_value).strip() if str(original_value).strip() else original_value
            else:
                preserved_doc[field] = ''
        
        return preserved_doc
    
    @classmethod
    def normalize_document_with_integrity(cls, doc):
        if doc is None: return None
        
        normalized_doc = cls.preserve_original_fields(doc)
        normalized_doc = cls.normalize_date_fields(normalized_doc)
        normalized_doc['error_time'] = cls.normalize_error_time(doc.get('error_time'))
        normalized_doc['_integrity_preserved'] = True
        normalized_doc['_normalized_timestamp'] = datetime.now().isoformat()
        
        return normalized_doc

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

class ImprovedStatisticsCalculator:
    def __init__(self, remove_duplicates=False):
        self.validator = StatisticsValidator()
        self.normalizer = DataIntegrityNormalizer()
        self.remove_duplicates = remove_duplicates
    
    def _extract_filter_conditions(self, query):
        conditions = {'year': None, 'month': None, 'start_month': None, 'end_month': None, 
                    'daynight': None, 'week': None, 'service_name': None, 'department': None, 'grade': None}
        if not query: return conditions
        
        query_lower = query.lower()
        
        # 연도 추출 - 4자리 연도 우선 
        year_match = re.search(r'\b(202[0-9]|201[0-9])년?\b', query_lower)
        if year_match: 
            conditions['year'] = year_match.group(1)
        else:
            # 2자리 연도 패턴 감지 (예: 22년, 20년)
            short_year_match = re.search(r'\b(\d{2})년\b', query_lower)
            if short_year_match:
                short_year = int(short_year_match.group(1))
                # 모든 2자리 연도를 2000년대로 변환
                if 0 <= short_year <= 99:
                    conditions['year'] = f"20{short_year:02d}"
        
        # 월 범위 처리
        month_patterns = [r'\b(\d+)\s*~\s*(\d+)월\b', r'\b(\d+)월\s*~\s*(\d+)월\b', 
                        r'\b(\d+)\s*-\s*(\d+)월\b', r'\b(\d+)월\s*-\s*(\d+)월\b']
        for pattern in month_patterns:
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
        
        # 시간대 처리
        if any(word in query_lower for word in ['야간', '밤', '새벽', '심야']):
            conditions['daynight'] = '야간'
        elif any(word in query_lower for word in ['주간', '낮', '오전', '오후']):
            conditions['daynight'] = '주간'
        
        # 요일 처리
        week_patterns = {'월': ['월요일', '월'], '화': ['화요일', '화'], '수': ['수요일', '수'], 
                        '목': ['목요일', '목'], '금': ['금요일', '금'], '토': ['토요일', '토'], '일': ['일요일', '일']}
        for week_key, patterns in week_patterns.items():
            if any(pattern in query_lower for pattern in patterns):
                conditions['week'] = week_key
                break
        
        if '평일' in query_lower: conditions['week'] = '평일'
        elif '주말' in query_lower: conditions['week'] = '주말'
        
        grade_match = re.search(r'(\d+)등급', query_lower)
        if grade_match: conditions['grade'] = f"{grade_match.group(1)}등급"
        
        return conditions
    
    def _validate_document_against_conditions(self, doc, conditions):
        if conditions['year'] and self._extract_year_from_document(doc) != conditions['year']:
            return False, "year mismatch"
        
        if conditions['start_month'] and conditions['end_month']:
            doc_month = self._extract_month_from_document(doc)
            if not doc_month: return False, "no month information"
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
        # year 필드에서 직접 추출 (4자리 또는 2자리)
        for key in ['year', 'extracted_year']:
            year = doc.get(key)
            if year:
                year_str = str(year).strip()
                if len(year_str) == 4 and year_str.isdigit():
                    return year_str
                elif len(year_str) == 2 and year_str.isdigit():
                    # 모든 2자리 연도를 2000년대로 변환
                    short_year = int(year_str)
                    if 0 <= short_year <= 99:
                        return f"20{short_year:02d}"
        
        # error_date에서 추출
        error_date = str(doc.get('error_date', '')).strip()
        if len(error_date) >= 4:
            if '-' in error_date:
                parts = error_date.split('-')
                if parts and len(parts[0]) == 4 and parts[0].isdigit():
                    return parts[0]
                elif parts and len(parts[0]) == 2 and parts[0].isdigit():
                    # 모든 2자리 연도를 2000년대로 처리
                    short_year = int(parts[0])
                    if 0 <= short_year <= 99:
                        return f"20{short_year:02d}"
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
        return {'total_count': 0, 'yearly_stats': {}, 'monthly_stats': {}, 
                'time_stats': {'daynight': {}, 'week': {}}, 'department_stats': {}, 
                'service_stats': {}, 'grade_stats': {}, 'is_error_time_query': False, 
                'validation': {'errors': [], 'warnings': [], 'is_valid': True}, 'primary_stat_type': None}
    
    def _is_error_time_query(self, query):
        return query and any(keyword in query.lower() for keyword in 
                           ['장애시간', '장애 시간', 'error_time', '시간 통계', '시간 합계', '시간 합산', '분'])
    
    def _determine_primary_stat_type(self, query, yearly_stats, monthly_stats, time_stats, service_stats, department_stats, grade_stats):
        if query:
            query_lower = query.lower()
            keywords = [('yearly', ['연도별', '년도별', '년별', '연별']), ('monthly', ['월별']), 
                       ('time', ['시간대별', '주간', '야간']), ('weekday', ['요일별']), 
                       ('department', ['부서별', '팀별']), ('service', ['서비스별']), ('grade', ['등급별'])]
            
            for stat_type, kws in keywords:
                if any(kw in query_lower for kw in kws):
                    return stat_type
            
            if re.search(r'\b\d+월\b', query_lower):
                return 'monthly'
        
        stat_counts = {'yearly': len(yearly_stats), 'monthly': len(monthly_stats), 
                      'service': len(service_stats), 'department': len(department_stats), 
                      'grade': len(grade_stats), 'time': len(time_stats.get('daynight', {})) + len(time_stats.get('week', {}))}
        return max(stat_counts.items(), key=lambda x: x[1])[0] if any(stat_counts.values()) else 'yearly'
    
    def _calculate_detailed_statistics(self, documents, conditions, is_error_time_query):
        stats = {'total_count': len(documents), 'yearly_stats': {}, 'monthly_stats': {}, 
                'time_stats': {'daynight': {}, 'week': {}}, 'department_stats': {}, 
                'service_stats': {}, 'grade_stats': {}, 'is_error_time_query': is_error_time_query, 
                'filter_conditions': conditions, 'calculation_details': {}}
        
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
        
        # 기타 통계 계산
        temp_dicts = {'daynight': {}, 'week': {}, 'department': {}, 'service': {}, 'grade': {}}
        field_mapping = {'daynight': 'daynight', 'week': 'week', 'department': 'owner_depart', 
                        'service': 'service_name', 'grade': 'incident_grade'}
        
        for doc in documents:
            error_time = doc.get('error_time', 0) if is_error_time_query else 1
            for stat_key, field_name in field_mapping.items():
                value = doc.get(field_name, '')
                if value:
                    temp_dicts[stat_key][value] = temp_dicts[stat_key].get(value, 0) + error_time
        
        # 시간대 통계
        for time_key in ['주간', '야간']:
            if time_key in temp_dicts['daynight']:
                stats['time_stats']['daynight'][time_key] = temp_dicts['daynight'][time_key]
        
        # 요일 통계
        for week_key in ['월', '화', '수', '목', '금', '토', '일', '평일', '주말']:
            if week_key in temp_dicts['week']:
                week_display = f"{week_key}요일" if week_key in ['월', '화', '수', '목', '금', '토', '일'] else week_key
                stats['time_stats']['week'][week_display] = temp_dicts['week'][week_key]
        
        stats['department_stats'] = dict(sorted(temp_dicts['department'].items(), key=lambda x: x[1], reverse=True)[:10])
        stats['service_stats'] = dict(sorted(temp_dicts['service'].items(), key=lambda x: x[1], reverse=True)[:10])
        
        # 등급 통계
        for grade_key in ['1등급', '2등급', '3등급', '4등급']:
            if grade_key in temp_dicts['grade']:
                stats['grade_stats'][grade_key] = temp_dicts['grade'][grade_key]
        for grade_key, value in sorted(temp_dicts['grade'].items()):
            if grade_key not in stats['grade_stats']:
                stats['grade_stats'][grade_key] = value
        
        total_error_time = sum(doc.get('error_time', 0) for doc in documents)
        stats['calculation_details'] = {
            'total_error_time_minutes': total_error_time,
            'total_error_time_hours': round(total_error_time / 60, 2),
            'average_error_time': round(total_error_time / len(documents), 2) if documents else 0,
            'max_error_time': max((doc.get('error_time', 0) for doc in documents), default=0),
            'min_error_time': min((doc.get('error_time', 0) for doc in documents), default=0),
            'documents_with_error_time': len([doc for doc in documents if doc.get('error_time', 0) > 0])
        }
        stats['primary_stat_type'] = None
        return stats
    
    def calculate_comprehensive_statistics(self, query, documents, query_type="default"):
        if not documents:
            return self._empty_statistics()
        
        normalized_docs, validation_errors, validation_warnings = [], [], []
        for i, doc in enumerate(documents):
            if doc is None: continue
            errors, warnings = self.validator.validate_document(doc, i)
            validation_errors.extend(errors)
            validation_warnings.extend(warnings)
            normalized_doc = self.normalizer.normalize_document_with_integrity(doc)
            normalized_docs.append(normalized_doc)
        
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
        is_stats_query = any(keyword in query.lower() for keyword in 
                           ['건수', '통계', '연도별', '월별', '현황', '분포', '알려줘', '몇건', '개수'])
        filtered_docs = clean_documents if is_stats_query else self._apply_filters(clean_documents, filter_conditions)
        
        is_error_time_query = self._is_error_time_query(query)
        stats = self._calculate_detailed_statistics(filtered_docs, filter_conditions, is_error_time_query)
        stats['primary_stat_type'] = self._determine_primary_stat_type(
            query, stats['yearly_stats'], stats['monthly_stats'], stats['time_stats'], 
            stats['service_stats'], stats['department_stats'], stats['grade_stats'])
        
        result_errors, result_warnings = self.validator.validate_statistics_result(stats, len(filtered_docs))
        validation_errors.extend(result_errors)
        validation_warnings.extend(result_warnings)
        stats['validation'] = {'errors': validation_errors, 'warnings': validation_warnings, 'is_valid': len(validation_errors) == 0}
        return stats

class QueryProcessorLocal:
    def __init__(self, azure_openai_client, search_client, model_name, config=None, embedding_client=None):
        self.azure_openai_client = azure_openai_client
        self.search_client = search_client
        self.model_name = model_name
        self.config = config or AppConfigLocal()
        self.embedding_client = embedding_client
        
        # 컴포넌트 초기화
        self.search_manager = SearchManagerLocal(search_client, embedding_client, self.config)
        self.ui_components = UIComponentsLocal()
        self.reprompting_db_manager = RepromptingDBManager()
        self.chart_manager = ChartManager()
        self.normalizer = DataIntegrityNormalizer()
        self.statistics_calculator = ImprovedStatisticsCalculator(remove_duplicates=False)
        
        # ✅ StatisticsDBManager는 lazy initialization으로 변경
        self._statistics_db_manager = None  # 초기에는 None
        
        self.filter_manager = DocumentFilterManager(debug_mode=True)
        
        self.debug_mode = True
        self._manual_logging_enabled = True

        # 통계 관련 키워드 대폭 확장
        self.statistics_keywords = {
            'basic_stats': [
                '건수', '개수', '수량', '숫자', '몇건', '몇개', '얼마나', '어느정도', 
                '얼마', '어떻게', '어느', '어떤', '몇번', '몇차례', '몇회'
            ],
            'stats_verbs': [
                '알려줘', '보여줘', '말해줘', '확인해줘', '체크해줘', '조회해줘',
                '검색해줘', '찾아줘', '가져와줘', '추출해줘', '분석해줘'
            ],
            'stats_nouns': [
                '통계', '현황', '분포', '집계', '합계', '이합', '누적', '전체',
                '요약', '개요', '상황', '정도', '수준', '범위', '규모', '실적'
            ],
            'time_keywords': [
                '연도별', '년도별', '년별', '연별', '해별', '월별', '매월', '월간',
                '요일별', '주간별', '일별', '시간대별', '주야별', '기간별'
            ],
            'category_keywords': [
                '등급별', '장애등급별', 'grade별', '부서별', '팀별', '조직별',
                '서비스별', '시스템별', '원인별', '원인유형별', '유형별', '타입별'
            ],
            'service_patterns': [
                r'\b([A-Z]{2,10})\s+(?:연도별|월별|장애|건수|통계|현황)',
                r'([가-힣]{2,20}(?:플랫폼|시스템|서비스|포털|앱|관리|센터))\s+(?:연도별|월별|장애|건수|통계)',
                r'(?:알려|보여|확인).*?([A-Z가-힣][A-Z가-힣0-9\s]{1,20}).*?(?:연도별|월별|장애|건수|통계)'
            ]
        }

        # 모니터링 매니저 초기화
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
    
    @property
    def statistics_db_manager(self):
        """✅ Lazy initialization property for StatisticsDBManager"""
        if self._statistics_db_manager is None:
            if self.debug_mode:
                print("📄 Initializing StatisticsDBManager (lazy loading)...")
            self._statistics_db_manager = StatisticsDBManager()
        return self._statistics_db_manager

    def _validate_documents_against_query_conditions(self, query, documents):
        """🚨 핵심 개선: 쿼리 조건과 문서 일치성 검증"""
        if not query or not documents:
            return []
        
        # 쿼리에서 조건 추출
        extracted_service = self.search_manager.extract_service_name_from_query(query)
        extracted_year = self._extract_year_from_query(query)
        extracted_months = self._extract_months_from_query(query)
        time_conditions = self.extract_time_conditions(query)  # ✅ 추가
        
        if self.debug_mode:
            print(f"DEBUG: Query conditions - Service: {extracted_service}, Year: {extracted_year}, Months: {extracted_months}, TimeConditions: {time_conditions}")
        
        validated_documents = []
        
        for doc in documents:
            is_valid = True
            validation_reasons = []
            
            # 서비스명 검증 (기존)
            if extracted_service:
                doc_service = doc.get('service_name', '').strip()
                if not self._is_service_match(extracted_service, doc_service):
                    is_valid = False
                    validation_reasons.append(f"Service mismatch: expected '{extracted_service}', got '{doc_service}'")
            
            # 연도 검증 (기존)
            if extracted_year:
                doc_year = self._extract_year_from_document(doc)
                if not doc_year or doc_year != extracted_year:
                    is_valid = False
                    validation_reasons.append(f"Year mismatch: expected '{extracted_year}', got '{doc_year}'")
            
            # 월 검증 (기존)
            if extracted_months:
                doc_month = self._extract_month_from_document(doc)
                if doc_month and int(doc_month) not in extracted_months:
                    is_valid = False
                    validation_reasons.append(f"Month mismatch: expected {extracted_months}, got '{doc_month}'")
            
            # ✅ 시간대 검증 추가
            if time_conditions.get('is_time_query') and time_conditions.get('daynight'):
                doc_daynight = doc.get('daynight', '').strip()
                if not doc_daynight or doc_daynight != time_conditions['daynight']:
                    is_valid = False
                    validation_reasons.append(f"Daynight mismatch: expected '{time_conditions['daynight']}', got '{doc_daynight}'")
            
            # ✅ 요일 검증 추가
            if time_conditions.get('is_time_query') and time_conditions.get('week'):
                doc_week = doc.get('week', '').strip()
                expected_week = time_conditions['week']
                
                # 평일/주말 특별 처리
                if expected_week == '평일':
                    if doc_week not in ['월', '화', '수', '목', '금']:
                        is_valid = False
                        validation_reasons.append(f"Week mismatch: expected weekday, got '{doc_week}'")
                elif expected_week == '주말':
                    if doc_week not in ['토', '일']:
                        is_valid = False
                        validation_reasons.append(f"Week mismatch: expected weekend, got '{doc_week}'")
                else:
                    if not doc_week or doc_week != expected_week:
                        is_valid = False
                        validation_reasons.append(f"Week mismatch: expected '{expected_week}', got '{doc_week}'")
            
            if is_valid:
                validated_documents.append(doc)
                if self.debug_mode:
                    print(f"DEBUG: Document {doc.get('incident_id', 'Unknown')} validated successfully")
            else:
                if self.debug_mode:
                    print(f"DEBUG: Document {doc.get('incident_id', 'Unknown')} rejected: {', '.join(validation_reasons)}")
        
        return validated_documents
    
    def _is_service_match(self, query_service, doc_service):
        """서비스명 매칭 로직 - 정확한 매칭과 유연한 매칭 모두 고려"""
        if not query_service or not doc_service:
            return False
        
        query_service_lower = query_service.lower().strip()
        doc_service_lower = doc_service.lower().strip()
        
        # 1. 정확한 매칭
        if query_service_lower == doc_service_lower:
            return True
        
        # 2. 포함 관계 매칭
        if query_service_lower in doc_service_lower or doc_service_lower in query_service_lower:
            return True
        
        # 3. 공백 제거 후 매칭
        query_no_space = re.sub(r'\s+', '', query_service_lower)
        doc_no_space = re.sub(r'\s+', '', doc_service_lower)
        if query_no_space == doc_no_space:
            return True
        
        # 4. 토큰 기반 매칭 (부분 일치)
        query_tokens = set(re.findall(r'[a-z가-힣0-9]+', query_service_lower))
        doc_tokens = set(re.findall(r'[a-z가-힣0-9]+', doc_service_lower))
        
        if query_tokens and doc_tokens:
            intersection = len(query_tokens.intersection(doc_tokens))
            union = len(query_tokens.union(doc_tokens))
            similarity = intersection / union if union > 0 else 0
            
            # 유사도 70% 이상이면 매칭으로 간주
            if similarity >= 0.7:
                return True
        
        return False
    
    def _extract_year_from_query(self, query):
        """쿼리에서 연도 추출"""
        if not query:
            return None
        
        # 4자리 연도 패턴
        year_patterns = [r'\b(\d{4})년\b', r'\b(\d{4})\s*년도\b', r'\b(\d{4})년도\b', r'\b(202[0-9]|201[0-9])\b']
        
        for pattern in year_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                year = matches[-1]  # 가장 마지막 매칭된 연도 사용
                if year.isdigit() and len(year) == 4:
                    return year
        
        # 2자리 연도 패턴
        short_year_match = re.search(r'\b(\d{2})년\b', query)
        if short_year_match:
            short_year = int(short_year_match.group(1))
            # 모든 2자리 연도를 2000년대로 변환
            if 0 <= short_year <= 99:
                return f"20{short_year:02d}"
        
        return None
    
    def _extract_months_from_query(self, query):
        """쿼리에서 월 추출"""
        if not query:
            return []
        
        months = []
        
        # 월 범위 패턴 (예: 1~6월, 1월~6월)
        range_patterns = [r'\b(\d+)\s*~\s*(\d+)월\b', r'\b(\d+)월\s*~\s*(\d+)월\b']
        for pattern in range_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            for match in matches:
                start_month, end_month = int(match[0]), int(match[1])
                if 1 <= start_month <= 12 and 1 <= end_month <= 12 and start_month <= end_month:
                    months.extend(range(start_month, end_month + 1))
        
        # 개별 월 패턴 (예: 1월, 2월)
        if not months:  # 범위가 없는 경우에만
            month_matches = re.findall(r'\b(\d{1,2})월\b', query)
            for match in month_matches:
                month_num = int(match)
                if 1 <= month_num <= 12:
                    months.append(month_num)
        
        return list(set(months))  # 중복 제거
    
    def _extract_year_from_document(self, doc):
        """문서에서 연도 추출"""
        # year 필드에서 직접 추출
        for key in ['year', 'extracted_year']:
            year = doc.get(key)
            if year:
                year_str = str(year).strip()
                if len(year_str) == 4 and year_str.isdigit():
                    return year_str
        
        # error_date에서 추출
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
        """문서에서 월 추출"""
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

    def generate_rag_response_with_data_integrity(self, query, documents, query_type="default", time_conditions=None, department_conditions=None, reprompting_info=None):
        """🚨 RAG 데이터 무결성을 절대 보장하는 응답 생성 - 조건 검증 강화"""
        if not documents:
            return "검색된 문서가 없어서 답변을 제공할 수 없습니다."
        
        try:
            # 🚨 원본 데이터 보존을 위한 전처리
            integrity_documents = [self.normalizer.normalize_document_with_integrity(doc) for doc in documents]
            
            if self.debug_mode:
                print(f"DEBUG: Data integrity preserved for {len(integrity_documents)} documents")
            
            # ⚠️ 핵심 개선: 조건 매칭 재검증 - 사용자 질문과 문서 일치성 확인
            validated_documents = self._validate_documents_against_query_conditions(query, integrity_documents)
            
            if not validated_documents:
                # 검색된 문서가 있지만 조건에 맞지 않는 경우
                extracted_service = self.search_manager.extract_service_name_from_query(query)
                extracted_year = self._extract_year_from_query(query)
                
                if extracted_service and extracted_year:
                    return f"제공된 데이터에서 '{extracted_service}'와 관련된 {extracted_year}년도 장애 내역은 없습니다."
                elif extracted_service:
                    return f"제공된 데이터에서 '{extracted_service}' 서비스와 관련된 장애 내역은 없습니다."
                elif extracted_year:
                    return f"제공된 데이터에서 {extracted_year}년도 장애 내역은 없습니다."
                else:
                    return "검색된 문서가 요청하신 조건과 일치하지 않습니다."
            
            if self.debug_mode:
                print(f"DEBUG: Validated {len(validated_documents)}/{len(integrity_documents)} documents match query conditions")
            
            # 검증된 문서로 응답 생성 진행
            final_documents = validated_documents
            
            # 통계 계산 - statistics 쿼리타입에서만 차트 생성
            if query_type == "statistics":
                return self._generate_statistics_response_with_integrity(query, final_documents)
            
            # 정렬 적용
            sort_info = self.detect_sorting_requirements(query)
            processing_documents = self.apply_custom_sorting(final_documents, sort_info)
            
            final_query = reprompting_info.get('transformed_query', query) if reprompting_info and reprompting_info.get('transformed') else query
            
            # 컨텍스트 구성 - 원본 데이터만 사용
            context_parts = [f"""전체 문서 수: {len(processing_documents)}건
    ⚠️ 중요: 아래 모든 필드값은 원본 RAG 데이터이므로 절대 변경하거나 요약하지 마세요."""]
            
            for i, doc in enumerate(processing_documents[:30]):
                context_parts.append(f"""문서 {i+1}:
    장애 ID: {doc.get('incident_id', '')}
    서비스명: {doc.get('service_name', '')}
    장애시간: {doc.get('error_time', 0)}분
    장애현상: {doc.get('symptom', '')}
    장애원인: {doc.get('root_cause', '')}
    복구방법: {doc.get('incident_repair', '')}
    개선계획: {doc.get('incident_plan', '')}
    처리유형: {doc.get('done_type', '')}
    발생일자: {doc.get('error_date', '')}
    장애등급: {doc.get('incident_grade', '')}
    담당부서: {doc.get('owner_depart', '')}
    시간대: {doc.get('daynight', '')}
    요일: {doc.get('week', '')}
    """)
            
            # 데이터 무결성 보장 프롬프트 사용
            integrity_prompt = self._get_data_integrity_prompt(query_type)
            
            user_prompt = f"""{integrity_prompt}

    **원본 RAG 데이터 (절대 변경 금지):**
    {chr(10).join(context_parts)}

    **사용자 질문:** {final_query}

    **응답 지침:**
    1. 위 원본 데이터의 모든 필드값을 정확히 그대로 출력하세요
    2. 절대 요약하거나 변경하지 마세요
    3. '해당 정보없음' 같은 임의의 값을 생성하지 마세요
    4. 빈 필드는 빈 상태로 두거나 원본 그대로 출력하세요

    답변:"""

            max_tokens = 2500 if query_type == 'inquiry' else 3000 if query_type == 'repair' else 1500
            response = self.azure_openai_client.chat.completions.create(
                model=self.model_name, 
                messages=[
                    {"role": "system", "content": integrity_prompt}, 
                    {"role": "user", "content": user_prompt}
                ], 
                temperature=0.0, 
                max_tokens=max_tokens
            )
            
            final_answer = response.choices[0].message.content
            return final_answer
            
        except Exception as e:
            st.error(f"응답 생성 실패: {str(e)}")
            import traceback
            traceback.print_exc()
            return "죄송합니다. 응답을 생성하는 중 오류가 발생했습니다."
    
    def _get_data_integrity_prompt(self, query_type):
        """데이터 무결성 보장 전용 프롬프트"""
        base_prompt = f"""당신은 IT 시스템 장애 분석 전문가입니다.

🚨 절대 최우선 규칙 - 데이터 무결성 보장 🚨
**제공된 RAG 데이터의 어떤 정보도 절대 변경하거나 수정하지 마세요**

### 1. 원본 데이터 보존 원칙
- **모든 필드값을 원본 RAG 데이터 그대로 출력하세요**
- **절대 요약하거나 의역하지 마세요**
- **"해당 정보없음", "N/A", "정보 없음" 등의 임의 값 생성 금지**
- **빈 필드는 빈 상태로 두거나 원본 그대로 출력하세요**

### 2. 필드별 출력 원칙
- **incident_id**: 원본 ID 그대로 (예: INM25011031275)
- **service_name**: 원본 서비스명 그대로
- **symptom**: 원본 장애현상 전체 내용 그대로
- **root_cause**: 원본 장애원인 전체 내용 그대로  
- **incident_repair**: 원본 복구방법 전체 내용 그대로
- **error_date**: 원본 날짜 그대로 (예: 2025-01-10)
- **error_time**: 원본 시간 그대로 (예: 94분)
- **incident_grade**: 원본 등급 그대로 (예: 3등급)
- **owner_depart**: 원본 부서명 그대로
- **daynight**: 원본 시간대 그대로 (주간/야간)
- **week**: 원본 요일 그대로

### 3. 금지 사항
- ❌ 내용 요약 금지
- ❌ 의역 금지  
- ❌ 생략 금지
- ❌ 임의 값 생성 금지
- ❌ "약 XX분", "대략 XX" 등의 표현 금지
- ❌ "주요 내용:", "핵심:", "요약:" 등의 접두사 금지

### 4. 허용 사항
- ✅ 원본 데이터 그대로 복사
- ✅ 구조화된 형태로 정리 (내용 변경 없이)
- ✅ 필드명 명시 (값은 원본 그대로)

{SystemPrompts.get_prompt(query_type)}"""
        
        return base_prompt
    
    def _generate_statistics_response_with_integrity(self, query, documents):
        """데이터 무결성을 보장하는 통계 응답 생성 - 원인유형 처리 강화"""
        try:
            # ✅ 1. DB 우선 조회 시도 (lazy initialization)
            db_statistics = self.statistics_db_manager.get_statistics(query)
            
            if self.debug_mode and db_statistics.get('debug_info'):
                debug_info = db_statistics['debug_info']
                
                with st.expander("🔍 SQL 쿼리 디버그 정보", expanded=False):
                    st.markdown("### 🔍 파싱된 조건")
                    st.json(debug_info['parsed_conditions'])
                    
                    st.markdown("### 💾 실행된 SQL 쿼리")
                    st.code(debug_info['sql_query'], language='sql')
                    
                    st.markdown("### 📢 SQL 파라미터")
                    st.json(list(debug_info['sql_params']))
                    
                    st.markdown("### 📊 쿼리 결과")
                    st.info(f"총 {debug_info['result_count']}개의 결과 반환")
                    
                    if db_statistics.get('results'):
                        st.markdown("#### 결과 샘플 (최대 5개)")
                        st.json(db_statistics['results'][:5])
            
            # 2. DB에서 통계 결과가 있는지 확인
            if (db_statistics and 
                db_statistics.get('results') and 
                (db_statistics.get('total_value', 0) > 0 or 
                db_statistics.get('cause_type_stats', {}) or
                db_statistics.get('yearly_stats', {}) or
                db_statistics.get('monthly_stats', {}))):
                
                return self._format_db_statistics_with_chart_support(db_statistics, query)
            else:
                # 3. DB에서 결과가 없으면 문서 기반 통계로 fallback
                if self.debug_mode:
                    print("DB statistics returned no results, falling back to document-based statistics")
                return self._calculate_statistics_with_chart_support(documents, query)
                
        except Exception as e:
            print(f"ERROR: 통계 응답 생성 실패: {e}")
            import traceback
            traceback.print_exc()
            return f"통계 조회 중 오류가 발생했습니다: {str(e)}"

    def _calculate_statistics_with_chart_support(self, documents, query):
        """문서 기반 통계 계산 - 차트 포함"""
        try:
            stats = self.statistics_calculator.calculate_comprehensive_statistics(query, documents, "statistics")
            
            if not stats or stats.get('total_count', 0) == 0:
                return "조건에 맞는 장애 데이터를 찾을 수 없습니다."
            
            # 차트 생성 로직
            chart_fig, chart_info = None, None
            requested_chart_type = self._extract_chart_type_from_query(query)
            
            chart_keywords = ['차트', '그래프', '시각화', '그려', '그려줘', '보여줘', '시각적으로', '도표', '도식화']
            has_chart_request = any(keyword in query.lower() for keyword in chart_keywords)
            
            if has_chart_request or requested_chart_type:
                chart_data, chart_type = self._get_chart_data_from_stats(stats, requested_chart_type)
                
                if chart_data and len(chart_data) > 0:
                    try:
                        chart_title = self._generate_chart_title(query, stats)
                        chart_fig = self.chart_manager.create_chart(chart_type, chart_data, chart_title)
                        
                        if chart_fig:
                            chart_info = {
                                'chart': chart_fig,
                                'chart_type': chart_type,
                                'chart_data': chart_data,
                                'chart_title': chart_title,
                                'query': query,
                                'is_error_time_query': stats.get('is_error_time_query', False)
                            }
                            print(f"DEBUG: Chart created successfully - type: {chart_type}")
                    except Exception as e:
                        print(f"DEBUG: Chart creation failed: {e}")
                        chart_info = None
            
            # 통계 응답 생성
            response_lines = []
            total_count = stats.get('total_count', 0)
            is_error_time = stats.get('is_error_time_query', False)
            value_type = "장애시간(분)" if is_error_time else "발생건수"
            
            response_lines.append(f"## 📊 통계 요약")
            response_lines.append(f"**총 {value_type}: {total_count}**")
            
            # 각종 통계 추가 (기존 로직 유지)
            if stats.get('yearly_stats'):
                response_lines.append(f"\n## 📈 연도별 통계")
                for year, count in sorted(stats['yearly_stats'].items()):
                    response_lines.append(f"* **{year}: {count}건**")
                response_lines.append(f"\n**💡 총 합계: {sum(stats['yearly_stats'].values())}건**")
            
            if stats.get('monthly_stats'):
                response_lines.append(f"\n## 📈 월별 통계")
                sorted_months = sorted(stats['monthly_stats'].items(), key=lambda x: int(x[0].replace('월', '')))
                for month, count in sorted_months:
                    response_lines.append(f"* **{month}: {count}건**")
                response_lines.append(f"\n**💡 총 합계: {sum(stats['monthly_stats'].values())}건**")
            
            # 기타 통계들도 동일하게 추가...
            
            final_answer = '\n'.join(response_lines)
            
            # 차트와 함께 반환
            if chart_info:
                return (final_answer, chart_info)
            return final_answer
            
        except Exception as e:
            print(f"ERROR: 문서 기반 통계 계산 실패: {e}")
            import traceback
            traceback.print_exc()
            return f"통계 계산 중 오류가 발생했습니다: {str(e)}"

    def _format_db_statistics_with_chart_support(self, db_stats, query):
        """DB 통계 결과를 차트와 함께 포맷팅 - 원인유형 처리 강화"""
        try:
            conditions = db_stats['query_conditions']
            
            # 차트 생성 로직
            chart_fig, chart_info = None, None
            requested_chart_type = self._extract_chart_type_from_query(query)
            
            chart_keywords = ['차트', '그래프', '시각화', '그려', '그려줘', '보여줘', '시각적으로', '도표', '도식화']
            has_chart_request = any(keyword in query.lower() for keyword in chart_keywords)
            
            if has_chart_request or requested_chart_type:
                chart_data, chart_type = self._get_chart_data_from_db_stats(db_stats, requested_chart_type)
                
                if chart_data and len(chart_data) > 0:
                    try:
                        chart_title = self._generate_chart_title_from_db_stats(query, db_stats)
                        chart_fig = self.chart_manager.create_chart(chart_type, chart_data, chart_title)
                        
                        if chart_fig:
                            chart_info = {
                                'chart': chart_fig,
                                'chart_type': chart_type,
                                'chart_data': chart_data,
                                'chart_title': chart_title,
                                'query': query,
                                'is_error_time_query': db_stats['is_error_time_query']
                            }
                            print(f"DEBUG: Chart created successfully - type: {chart_type}")
                    except Exception as e:
                        print(f"DEBUG: Chart creation failed: {e}")
                        chart_info = None
            
            # 통계 응답 생성 (원인유형 특별 처리)
            response_lines = []
            total_value = db_stats.get('total_value', 0)
            is_error_time = db_stats.get('is_error_time_query', False)
            is_cause_type_query = db_stats.get('is_cause_type_query', False)
            value_type = "장애시간(분)" if is_error_time else "발생건수"
            
            # 기본 요약
            response_lines.append(f"## 📊 통계 요약")
            response_lines.append(f"**총 {value_type}: {total_value}**")
            
            # 원인유형별 통계 (우선 표시)
            if is_cause_type_query and db_stats.get('cause_type_stats'):
                response_lines.append(f"\n## 🔍 원인유형별 {value_type}")
                cause_stats = db_stats['cause_type_stats']
                
                for cause_type, count in cause_stats.items():
                    response_lines.append(f"* **{cause_type}: {count}건**")
                
                response_lines.append(f"\n**💡 총 원인유형 수: {len(cause_stats)}개**")
                response_lines.append(f"**💡 총 합계: {sum(cause_stats.values())}건**")
            
            # 연도별 통계
            if db_stats.get('yearly_stats'):
                response_lines.append(f"\n## 📈 연도별 통계")
                for year, count in sorted(db_stats['yearly_stats'].items()):
                    response_lines.append(f"* **{year}: {count}건**")
                response_lines.append(f"\n**💡 총 합계: {sum(db_stats['yearly_stats'].values())}건**")
            
            # 월별 통계
            if db_stats.get('monthly_stats'):
                response_lines.append(f"\n## 📈 월별 통계")
                sorted_months = sorted(db_stats['monthly_stats'].items(), key=lambda x: int(x[0].replace('월', '')))
                for month, count in sorted_months:
                    response_lines.append(f"* **{month}: {count}건**")
                response_lines.append(f"\n**💡 총 합계: {sum(db_stats['monthly_stats'].values())}건**")
            
            # 등급별 통계
            if db_stats.get('grade_stats'):
                response_lines.append(f"\n## ⚠️ 장애등급별 통계")
                grade_order = ['1등급', '2등급', '3등급', '4등급']
                grade_stats = db_stats['grade_stats']
                
                for grade in grade_order:
                    if grade in grade_stats:
                        response_lines.append(f"* **{grade}: {grade_stats[grade]}건**")
                
                response_lines.append(f"\n**💡 총 합계: {sum(grade_stats.values())}건**")
            
            # 서비스별 통계 (상위 10개)
            if db_stats.get('service_stats'):
                response_lines.append(f"\n## 💻 서비스별 통계 (상위 10개)")
                sorted_services = sorted(db_stats['service_stats'].items(), key=lambda x: x[1], reverse=True)[:10]
                for service, count in sorted_services:
                    response_lines.append(f"* **{service}: {count}건**")
                response_lines.append(f"\n**💡 상위 10개 합계: {sum(count for _, count in sorted_services)}건**")
            
            # 부서별 통계 (상위 10개)
            if db_stats.get('department_stats'):
                response_lines.append(f"\n## 🏢 부서별 통계 (상위 10개)")
                sorted_departments = sorted(db_stats['department_stats'].items(), key=lambda x: x[1], reverse=True)[:10]
                for dept, count in sorted_departments:
                    response_lines.append(f"* **{dept}: {count}건**")
                response_lines.append(f"\n**💡 상위 10개 합계: {sum(count for _, count in sorted_departments)}건**")
            
            # 시간대별 통계
            if db_stats.get('time_stats', {}).get('daynight'):
                response_lines.append(f"\n## 🕘 시간대별 통계")
                for time, count in db_stats['time_stats']['daynight'].items():
                    response_lines.append(f"* **{time}: {count}건**")
                response_lines.append(f"\n**💡 총 합계: {sum(db_stats['time_stats']['daynight'].values())}건**")
            
            # 요일별 통계
            if db_stats.get('time_stats', {}).get('week'):
                response_lines.append(f"\n## 📅 요일별 통계")
                for day, count in db_stats['time_stats']['week'].items():
                    response_lines.append(f"* **{day}: {count}건**")
                response_lines.append(f"\n**💡 총 합계: {sum(db_stats['time_stats']['week'].values())}건**")
            
            final_answer = '\n'.join(response_lines)
            
            # 차트와 함께 반환
            if chart_info:
                return (final_answer, chart_info)
            return final_answer
            
        except Exception as e:
            return f"통계 포맷팅 중 오류: {str(e)}"

    # 기존 메서드들 유지 (다른 개선된 버전에서 가져온 메서드들 추가)
    def check_and_transform_query_with_reprompting(self, user_query):
        """개선된 리프롬프팅 - 강제 치환 추가"""
        if not user_query:
            return {'transformed': False, 'original_query': user_query, 'transformed_query': user_query, 'match_type': 'none'}
        
        force_replaced_query = self.force_replace_problematic_queries(user_query)
        
        try:
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
        query_lower = query.lower()
        
        if any(keyword in query_lower for keyword in ['야간', '밤', '새벽', '심야']):
            time_conditions.update({'is_time_query': True, 'daynight': '야간'})
        elif any(keyword in query_lower for keyword in ['주간', '낮', '오전', '오후']):
            time_conditions.update({'is_time_query': True, 'daynight': '주간'})
        
        week_map = {'월요일': '월', '화요일': '화', '수요일': '수', '목요일': '목', '금요일': '금', '토요일': '토', '일요일': '일', '평일': '평일', '주말': '주말'}
        for keyword, value in week_map.items():
            if keyword in query_lower:
                time_conditions.update({'is_time_query': True, 'week': value})
                break
        
        return time_conditions
    
    def extract_department_conditions(self, query):
        if not query:
            return {'owner_depart': None, 'is_department_query': False}
        return {'owner_depart': None, 'is_department_query': any(keyword in query for keyword in ['담당부서', '조치부서', '처리부서', '책임부서', '관리부서', '부서', '팀', '조직'])}

    def classify_query_type_with_llm(self, query):
        """개선된 LLM 기반 의미적 쿼리 분류 - 통계 키워드 인식 강화"""
        if not query:
            return 'default'
        
        print(f"DEBUG: Starting enhanced semantic query classification for: '{query}'")
        
        # 1단계: 사전 키워드 기반 필터링 (강화)
        pre_classification = self._pre_classify_by_keywords(query)
        if pre_classification != 'unknown':
            print(f"DEBUG: Pre-classified as '{pre_classification}' by keyword matching")
            return pre_classification
        
        try:
            # 개선된 분류 프롬프트
            classification_prompt = f"""다음 사용자 질문을 의미적으로 분석하여 정확히 분류하세요.

**🚨 핵심 원칙: 증상/조건은 무시하고 사용자의 의도만 파악하세요**

**분류 카테고리:**

1. **inquiry**: 장애 내역/목록/리스트를 보고 싶은 의도
   - 의도 키워드: "내역", "목록", "리스트", "이력", "조회" + "알려줘/보여줘/말해줘"
   - ✅ 예시: "접속불가 장애내역 알려줘" → inquiry (접속불가는 조건일뿐)
   - ✅ 예시: "로그인 실패 목록 보여줘" → inquiry (로그인 실패는 조건일뿐)
   - ✅ 예시: "ERP 장애내역" → inquiry
   - ✅ 예시: "야간 발생한 내역" → inquiry

2. **repair**: 복구방법, 해결방법, 원인 파악을 원하는 의도
   - 의도 키워드: "복구방법", "해결방법", "조치방법", "원인", "왜", "어떻게"
   - ✅ 예시: "접속불가 복구방법" → repair
   - ✅ 예시: "로그인 실패 어떻게 해결" → repair
   - ✅ 예시: "장애 원인 분석" → repair

3. **statistics**: 건수, 통계, 수치 정보를 원하는 의도
   - 의도 키워드: "건수", "몇건", "몇개", "얼마나", "통계", "연도별", "월별"
   - ✅ 예시: "접속불가 몇건" → statistics (접속불가는 조건일뿐)
   - ✅ 예시: "ERP 장애건수" → statistics
   - ✅ 예시: "연도별 통계" → statistics

4. **default**: 위 세 가지 의도가 없는 일반 질문

**🚨 분류 규칙:**
- "접속불가", "로그인 실패", "오류 발생" 등은 **조건/증상**이므로 분류에 영향 없음
- 오직 **사용자가 원하는 결과물의 형태**로만 판단:
  - 내역/목록을 원함 → inquiry
  - 해결책/원인을 원함 → repair
  - 숫자/통계를 원함 → statistics

**사용자 질문:** {query}

**응답 형식:** repair, inquiry, statistics, default 중 하나만 출력하세요."""

            response = self.azure_openai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "당신은 IT 질문을 의미적으로 분석하여 정확히 분류하는 전문가입니다. 특히 통계 관련 질문을 놓치지 않고 정확히 인식해야 합니다."},
                    {"role": "user", "content": classification_prompt}
                ],
                temperature=0.0,
                max_tokens=50
            )
            
            query_type = response.choices[0].message.content.strip().lower()
            
            if query_type not in ['repair', 'inquiry', 'statistics', 'default']:
                print(f"WARNING: Invalid query type '{query_type}', applying fallback classification")
                query_type = self._enhanced_fallback_classification(query)
            
            print(f"DEBUG: LLM semantic classification result: {query_type}")
            
            confidence_score = self._calculate_enhanced_classification_confidence(query, query_type)
            print(f"DEBUG: Classification confidence: {confidence_score:.2f}")
            
            # 신뢰도가 낮으면 fallback 사용
            if confidence_score < 0.6:
                fallback_type = self._enhanced_fallback_classification(query)
                print(f"DEBUG: Low confidence, using fallback: {fallback_type}")
                return fallback_type
            
            return query_type
                
        except Exception as e:
            print(f"ERROR: LLM semantic classification failed: {e}")
            return self._enhanced_fallback_classification(query)

    def _pre_classify_by_keywords(self, query):
        """키워드 기반 사전 분류 - 의도만 파악, 증상은 무시"""
        if not query:
            return 'unknown'
        
        query_lower = query.lower()
        
        # 🔥 1순위: inquiry 명시적 의도 체크
        explicit_inquiry_patterns = [
            r'(?:내역|목록|리스트|이력).*(?:알려줘|보여줘|말해줘|확인|체크|조회)',
            r'(?:알려줘|보여줘|말해줘).*(?:내역|목록|리스트|이력)',
        ]
        
        for pattern in explicit_inquiry_patterns:
            if re.search(pattern, query_lower):
                print(f"DEBUG: ✅ Explicit inquiry intent detected: {pattern}")
                return 'inquiry'
        
        # 🔥 2순위: 강력한 통계 신호 체크
        strong_stats_patterns = [
            r'\b[A-Z가-힣][A-Z0-9가-힣\s]{1,20}\s+(?:연도별|월별|년도별|년별)\s*(?:장애)?\s*건수',
            r'\b(?:몇건|몇개|얼마나|어느정도|몇번|몇차례)\b',
            r'(?:건수|개수|수량|통계|현황|분포)\s*(?:알려|보여|말해|확인|체크|조회)',
            r'\b(?:연도별|년도별|월별|등급별|부서별|서비스별)\s+\w+',
            r'\b[A-Z]{2,10}\s+(?:연도별|월별|년도별|통계|현황|건수)'
        ]
        
        for pattern in strong_stats_patterns:
            if re.search(pattern, query_lower):
                print(f"DEBUG: Strong statistics pattern detected: {pattern}")
                return 'statistics'
        
        # 🔥 3순위: 복합 키워드 점수 - 증상은 제외, 의도만 평가
        stats_score = 0
        repair_score = 0
        inquiry_score = 0
        
        # 통계 의도 키워드
        for category, keywords in self.statistics_keywords.items():
            for keyword in keywords:
                if keyword in query_lower:
                    if category == 'basic_stats':
                        stats_score += 3
                    elif category == 'time_keywords':
                        stats_score += 2
                    else:
                        stats_score += 1
        
        # 🔥 FIXED: repair는 행동 요청만 (증상 키워드 제거)
        repair_intent_keywords = ['복구방법', '해결방법', '조치방법', '원인', '왜', '어떻게', '해결', '조치', '대응']
        for keyword in repair_intent_keywords:
            if keyword in query_lower:
                repair_score += 3  # 명확한 의도이므로 높은 점수
        
        # 🔥 inquiry 의도 키워드
        inquiry_intent_keywords = ['내역', '목록', '리스트', '조회', '이력', '건들', '사례들', '발생한것', '있는지']
        for keyword in inquiry_intent_keywords:
            if keyword in query_lower:
                inquiry_score += 3
        
        print(f"DEBUG: Intent scores - inquiry: {inquiry_score}, stats: {stats_score}, repair: {repair_score}")
        
        # 🔥 CHANGED: 우선순위 명확화
        if inquiry_score >= 3:
            return 'inquiry'
        elif stats_score >= 3:
            return 'statistics'
        elif repair_score >= 3:
            return 'repair'
        
        return 'unknown'

    def _enhanced_fallback_classification(self, query):
        """강화된 fallback 분류 로직 - 의도 중심"""
        if not query:
            return 'default'
        
        query_lower = query.lower()
        
        # 1순위: inquiry 의도
        inquiry_intent = ['내역', '목록', '리스트', '이력', '조회']
        inquiry_verbs = ['알려줘', '보여줘', '말해줘', '확인', '체크']
        
        has_inquiry_noun = any(word in query_lower for word in inquiry_intent)
        has_inquiry_verb = any(word in query_lower for word in inquiry_verbs)
        
        if has_inquiry_noun and has_inquiry_verb:
            return 'inquiry'
        
        # 2순위: 통계 의도
        if any(keyword in query_lower for keyword in ['연도별', '년도별', '월별', '등급별']):
            return 'statistics'
        
        if any(keyword in query_lower for keyword in ['몇건', '몇개', '얼마나', '건수', '개수']):
            return 'statistics'
        
        # 3순위: repair 의도 (행동 요청만)
        if any(word in query_lower for word in ['복구방법', '해결방법', '조치방법', '원인', '왜', '어떻게']):
            return 'repair'
        
        # 4순위: 기본값
        return 'default'

    def _calculate_enhanced_classification_confidence(self, query, predicted_type):
        """강화된 분류 신뢰도 계산"""
        try:
            query_lower = query.lower()
            
            # 각 타입별 강력한 신호
            strong_signals = {
                'statistics': [
                    '몇건', '몇개', '얼마나', '건수', '개수', '통계', '현황', '분포',
                    '연도별', '월별', '등급별', '부서별', '서비스별'
                ],
                'repair': ['복구방법', '해결방법', '조치방법', '불가', '실패', '원인', '왜'],
                'inquiry': ['내역', '목록', '리스트', '조회', '보여줘'],
                'default': []
            }
            
            predicted_signals = strong_signals.get(predicted_type, [])
            signal_count = sum(1 for signal in predicted_signals if signal in query_lower)
            
            # 충돌하는 신호 체크
            conflicting_signals = 0
            for other_type, signals in strong_signals.items():
                if other_type != predicted_type:
                    conflicting_signals += sum(1 for signal in signals if signal in query_lower)
            
            # 기본 신뢰도
            confidence = 0.5
            
            # 신호 강도에 따른 가점
            if signal_count > 0:
                confidence += 0.4 * min(signal_count, 3) / 3
            
            # 충돌 신호에 따른 감점
            if conflicting_signals > 0:
                confidence -= 0.3 * min(conflicting_signals, 2) / 2
            
            # 통계 쿼리의 특별 처리 (우선순위 부여)
            if predicted_type == 'statistics':
                # 통계 관련 강력한 패턴이 있으면 신뢰도 증가
                stats_patterns = [
                    r'\b[A-Z]{2,10}\s+(?:연도별|월별|통계|현황|건수)',
                    r'(?:몇건|몇개|얼마나|건수)\b',
                    r'(?:연도별|월별|등급별)\s+\w+'
                ]
                
                for pattern in stats_patterns:
                    if re.search(pattern, query_lower):
                        confidence += 0.2
                        break
            
            return max(0.0, min(1.0, confidence))
            
        except Exception:
            return 0.5

    def _extract_chart_type_from_query(self, query):
        """쿼리에서 명시적으로 요청된 차트 타입 추출"""
        if not query:
            return None
        
        query_lower = query.lower()
        
        chart_type_keywords = {
            'horizontal_bar': ['가로막대', '가로 막대', '가로막대차트', '가로 막대 차트', 'horizontal bar', 'barh', '가로바', '가로 바', '가로형 막대', '가로형'],
            'bar': ['세로막대', '세로 막대', '세로막대차트', '세로 막대 차트', '막대차트', '막대 차트', 'bar chart', 'vertical bar', '바차트', '바 차트', '세로형'],
            'line': ['선차트', '선 차트', '선그래프', '선 그래프', '라인차트', '라인 차트', 'line chart', 'line graph', '꺾은선', '꺾은선그래프', '추이', '트렌드'],
            'pie': ['파이차트', '파이 차트', '원형차트', '원형 차트', '원그래프', 'pie chart', '파이그래프', '비율차트', '비율 차트', '원형']
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
        """통계에서 차트 데이터 추출"""
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
        
        chart_type = requested_chart_type or default_chart_type
        if default_chart_type == 'line' and len(data) == 1:
            chart_type = 'bar'
        
        print(f"DEBUG: Using {'user-requested' if requested_chart_type else 'default'} chart type: {chart_type}")
        
        return data, chart_type

    def _extract_incident_id_sort_key(self, incident_id):
        """Incident ID 정렬 키 추출"""
        if not incident_id:
            return 99999999999999
        try:
            return int(incident_id[3:]) if incident_id.startswith('INM') and len(incident_id) > 3 else hash(incident_id) % 999999999999999
        except (ValueError, TypeError):
            return hash(str(incident_id)) % 99999999999999

    def _apply_default_sorting(self, documents):
        """기본 정렬 적용"""
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
        """정렬 요구사항 감지"""
        sort_info = {'requires_custom_sort': False, 'sort_field': None, 'sort_direction': 'desc', 'sort_type': None, 'limit': None, 'secondary_sort': 'default'}
        if not query:
            return sort_info
        
        query_lower = query.lower()
        
        # 장애시간 관련 정렬 패턴
        error_time_patterns = [r'장애시간.*(?:가장.*?긴|긴.*?순|오래.*?걸린|최대|큰.*?순)', r'(?:최장|최대|가장.*?오래).*장애', r'top.*\d+.*장애시간']
        for pattern in error_time_patterns:
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
        """커스텀 정렬 적용"""
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

    def _display_response_with_marker_conversion(self, response, chart_info=None, query_type="default"):
        """UI 컴포넌트에 모든 처리를 위임하는 단순화된 버전"""
        if not response:
            st.write("응답이 없습니다.")
            return
        
        response_text, chart_info = response if isinstance(response, tuple) else (response, chart_info)
        
        print(f"PROCESSOR_DEBUG: Query type 전달: {query_type}")
        print(f"PROCESSOR_DEBUG: Response 길이: {len(response_text)}")
        print(f"PROCESSOR_DEBUG: REPAIR_BOX 포함 여부: {'[REPAIR_BOX_START]' in response_text}")
        
        self.ui_components.display_response_with_query_type_awareness(
            response, 
            query_type=query_type, 
            chart_info=chart_info
        )

    def process_query(self, query, query_type=None):
        """🚨 메인 쿼리 처리 - RAG 데이터 무결성 절대 보장"""
        if not query:
            st.error("질문을 입력해주세요.")
            return
        
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
                original_query = query
                force_replaced_query = self.force_replace_problematic_queries(query)
                
                if force_replaced_query != original_query:
                    if self.debug_mode:
                        st.info(f"🔄 쿼리 강제 치환: '{original_query}' → '{force_replaced_query}'")
                    query = force_replaced_query
                
                reprompting_info = self.check_and_transform_query_with_reprompting(query)
                processing_query = reprompting_info.get('transformed_query', query)
                
                time_conditions = self.extract_time_conditions(processing_query)
                department_conditions = self.extract_department_conditions(processing_query)
                
                if query_type is None:
                    with st.spinner("🔍 질문 분석 중..."):
                        query_type = self.classify_query_type_with_llm(processing_query)
                
                if self.debug_mode and query_type.lower() == 'inquiry':
                    st.info("📋 장애 내역 조회 모드로 분기되었습니다. 복구방법 박스 없이 깔끔한 목록을 제공합니다.")
                
                target_service_name = self.search_manager.extract_service_name_from_query(processing_query)
                
                with st.spinner("📄 문서 검색 중..."):
                    documents = self.search_manager.semantic_search_with_adaptive_filtering(processing_query, target_service_name, query_type) or []
                    document_count = len(documents)
                    
                    if documents:
                        with st.expander("📄 매칭된 문서 상세 보기"):
                            self.ui_components.display_documents_with_quality_info(documents)
                        
                        with st.spinner("🤖 AI 답변 생성 중..."):
                            # 🚨 무결성 보장 응답 생성 메서드만 사용
                            response = self.generate_rag_response_with_data_integrity(
                                query, documents, query_type, time_conditions, department_conditions, reprompting_info
                            )
                            
                            if response:
                                response_text = response[0] if isinstance(response, tuple) else response
                                
                                success = self._is_successful_response(response_text, document_count)
                                if not success:
                                    error_message = self._get_failure_reason(response_text, document_count)
                                
                                self._display_response_with_marker_conversion(response, query_type=query_type)
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
                                # 🚨 무결성 보장 응답 생성 메서드만 사용
                                response = self.generate_rag_response_with_data_integrity(
                                    query, fallback_documents, query_type, time_conditions, department_conditions, reprompting_info
                                )
                                response_text = response[0] if isinstance(response, tuple) else response
                                
                                success = self._is_successful_response(response_text, document_count)
                                if not success:
                                    error_message = self._get_failure_reason(response_text, document_count)
                                
                                self._display_response_with_marker_conversion(response, query_type=query_type)
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

    # 기타 필수 메서드들
    def _is_successful_response(self, response_text: str, document_count: int) -> bool:
        """응답이 성공적인지 판단"""
        if not response_text or response_text.strip() == "":
            return False
        
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
        
        if len(response_text.strip()) < 10:
            return False
        
        if document_count == 0:
            return False
        
        if not self._is_rag_based_response(response_text, document_count):
            return False
        
        return True

    def _is_rag_based_response(self, response_text: str, document_count: int = None) -> bool:
        """RAG 원천 데이터 기반 답변인지 판단"""
        
        if not response_text:
            return False
        
        response_lower = response_text.lower()
        
        if document_count is not None and document_count < 2:
            return False
        
        rag_markers = ['[repair_box_start]', '[cause_box_start]', 'case1', 'case2', 'case3', '장애 id', 'incident_id', 'service_name', '복구방법:', '장애원인:', '서비스명:', '발생일시:', '장애시간:', '담당부서:', '참조장애정보', '장애등급:', 'inm2']
        rag_marker_count = sum(1 for marker in rag_markers if marker in response_lower)
        
        rag_patterns = [r'장애\s*id\s*:\s*inm\d+', r'서비스명\s*:\s*\w+', r'발생일[시자]\s*:\s*\d{4}', r'장애시간\s*:\s*\d+분', r'복구방법\s*:\s*', r'장애원인\s*:\s*', r'\d+등급', r'incident_repair', r'error_date', r'case\d+\.']
        rag_pattern_count = sum(1 for pattern in rag_patterns if re.search(pattern, response_lower))
        
        general_patterns = [r'일반적으로\s+', r'보통\s+', r'대부분\s+', r'흔히\s+', r'주로\s+', r'다음과\s+같은\s+방법', r'다음\s+단계', r'기본적인\s+', r'표준적인\s+', r'권장사항', r'best\s+practice', r'모범\s+사례', r'다음과\s+같이\s+접근', r'시스템\s+관리자', r'네트워크\s+관리', r'서버\s+관리']
        general_pattern_count = sum(1 for pattern in general_patterns if re.search(pattern, response_lower))
        
        non_rag_keywords = ['일반적으로', '보통', '대부분', '흔히', '주로', '기본적으로', '표준적으로', '권장사항', '모범사례', '다음과 같은 방법', '다음 단계', '기본적인 점검', '시스템 관리', '네트워크 관리', '서버 관리', '일반적인 해결책', '표준 절차', '기본 원칙', '다음과 같은 조치', '기본적인 순서']
        non_rag_keyword_count = sum(1 for keyword in non_rag_keywords if keyword in response_lower)
        
        statistics_indicators = ['건수', '통계', '현황', '분포', '연도별', '월별', '차트']
        statistics_count = sum(1 for indicator in statistics_indicators if indicator in response_lower)
        
        print(f"DEBUG RAG 판단: rag_markers={rag_marker_count}, rag_patterns={rag_pattern_count}, general_patterns={general_pattern_count}, non_rag_keywords={non_rag_keyword_count}")
        
        if rag_marker_count >= 3 or rag_pattern_count >= 2:
            return True
        
        if statistics_count >= 2 and any(word in response_lower for word in ['차트', '표', '총', '합계']):
            return True
        
        if general_pattern_count >= 2 or non_rag_keyword_count >= 3:
            if rag_marker_count == 0 and rag_pattern_count == 0:
                print(f"DEBUG: 일반적 답변으로 판단됨 (general_pattern_count={general_pattern_count}, non_rag_keyword_count={non_rag_keyword_count})")
                return False
        
        if rag_marker_count > 0 or rag_pattern_count > 0:
            return True
        
        if len(response_text) > 200 and document_count and document_count >= 3:
            if non_rag_keyword_count < 2:
                return True
        
        print(f"DEBUG: 기본적으로 일반 답변으로 판단됨")
        return False

    def _get_failure_reason(self, response_text: str, document_count: int) -> str:
        """실패 원인 분석"""
        if not response_text or response_text.strip() == "":
            return "응답 내용 없음"
        
        if document_count == 0:
            return "관련 문서 검색 실패"
        
        if len(response_text.strip()) < 10:
            return "응답 길이 부족"
        
        failure_reasons = {
            r"해당.*조건.*문서.*찾을 수 없습니다": "조건 맞는 문서 없음",
            r"검색된 문서가 없어서": "검색 결과 없음",
            r"오류가 발생했습니다": "시스템 오류 발생",
            r"답변을 생성할 수 없습니다": "답변 생성 실패"
        }
        
        for pattern, reason in failure_reasons.items():
            if re.search(pattern, response_text, re.IGNORECASE):
                return reason
        
        if not self._is_rag_based_response(response_text, document_count):
            return "RAG 기반 답변 아님"
        
        return "적절한 답변 생성 실패"
    
    def _log_query_activity(self, query: str, query_type: str = None, response_time: float = None,
                        document_count: int = None, success: bool = None, 
                        error_message: str = None, response_content: str = None):
        """쿼리 활동 로깅"""
        try:
            if hasattr(self, '_manual_logging_enabled') and not self._manual_logging_enabled:
                print(f"DEBUG: 수동 로깅이 비활성화되어 로깅을 건너뜁니다.")
                return
            
            if hasattr(st.session_state, 'current_query_logged') and st.session_state.current_query_logged:
                print(f"DEBUG: 현재 쿼리가 이미 로깅되어 중복 로깅을 방지합니다.")
                return
                
            if self.monitoring_manager:
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
                
                if hasattr(st.session_state, 'current_query_logged'):
                    st.session_state.current_query_logged = True
                    
                print(f"DEBUG: 쿼리 로깅 완료 - Query: {query[:50]}..., Success: {success}")
                
        except Exception as e:
            print(f"모니터링 로그 실패: {str(e)}")

    def force_replace_problematic_queries(self, query):
        """문제 쿼리 치환 로직 단순화"""
        if not query:
            return query
        
        query_lower = query.lower()
        
        simple_replacements = {
            '몇건이야': '몇건',
            '몇건이니': '몇건', 
            '몇건인가': '몇건',
            '알려줘': '',
            '보여줘': '',
            '말해줘': ''
        }
        
        normalized_query = query
        for old, new in simple_replacements.items():
            normalized_query = normalized_query.replace(old, new)
        
        return normalized_query.strip()

    # 기타 필수 메서드들 유지
    def _convert_to_query_type_enum(self, query_type_str):
        mapping = {
            'repair': QueryType.REPAIR,
            'inquiry': QueryType.INQUIRY, 
            'statistics': QueryType.STATISTICS,
            'default': QueryType.DEFAULT
        }
        return mapping.get(query_type_str, QueryType.DEFAULT)

    def _determine_query_scope(self, conditions):
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
    
    def _get_chart_data_from_db_stats(self, db_stats, requested_chart_type=None):
        """DB 통계에서 차트 데이터 추출 - 원인유형 우선 처리"""
        conditions = db_stats['query_conditions']
        
        # 원인유형 쿼리인 경우 원인유형 차트 데이터 우선 반환
        if db_stats.get('is_cause_type_query', False) and db_stats.get('cause_type_stats'):
            cause_stats = db_stats['cause_type_stats']
            # 상위 10개만 차트로 표시
            top_causes = dict(list(cause_stats.items())[:10])
            chart_type = requested_chart_type or 'horizontal_bar'
            return top_causes, chart_type
        
        # 기존 로직
        group_by = conditions.get('group_by', [])
        
        data_map = {
            'year': ('yearly_stats', 'line'),
            'month': ('monthly_stats', 'line'),
            'daynight': ('time_stats', 'bar', 'daynight'),
            'week': ('time_stats', 'bar', 'week'),
            'owner_depart': ('department_stats', 'horizontal_bar'),
            'service_name': ('service_stats', 'horizontal_bar'),
            'incident_grade': ('grade_stats', 'pie'),
            'cause_type': ('cause_type_stats', 'horizontal_bar')
        }
        
        for group_type in group_by:
            if group_type in data_map:
                mapping = data_map[group_type]
                if len(mapping) == 3:  # time_stats case
                    data = db_stats[mapping[0]].get(mapping[2], {})
                    default_chart_type = mapping[1]
                else:
                    data = db_stats.get(mapping[0], {})
                    default_chart_type = mapping[1]
                
                if group_type in ['owner_depart', 'service_name', 'cause_type']:
                    data = dict(sorted(data.items(), key=lambda x: x[1], reverse=True)[:10])
                
                break
        else:
            data = db_stats.get('yearly_stats', {}) or db_stats.get('monthly_stats', {})
            default_chart_type = 'line'
        
        chart_type = requested_chart_type or default_chart_type
        
        if default_chart_type == 'line' and len(data) == 1:
            chart_type = 'bar'
        
        return data, chart_type
    
    def _generate_chart_title_from_db_stats(self, query, db_stats):
        """DB 통계 기반 차트 제목 생성 - 원인유형 처리"""
        conditions = db_stats['query_conditions']
        
        # 원인유형 쿼리인 경우 특별 처리
        if db_stats.get('is_cause_type_query', False):
            title_parts = ["원인유형별"]
            
            if conditions.get('year'):
                title_parts.insert(0, f"{conditions['year']}년")
            
            if db_stats['is_error_time_query']:
                title_parts.append("장애시간 분포")
            else:
                title_parts.append("장애 발생 현황")
            
            return ' '.join(title_parts)
        
        # 기존 로직
        group_by = conditions.get('group_by', [])
        title_parts = []
        
        if conditions.get('year'):
            title_parts.append(conditions['year'])
        
        group_titles = {
            'year': "연도별",
            'month': "월별",
            'daynight': "시간대별",
            'week': "요일별",
            'owner_depart': "부서별",
            'service_name': "서비스별",
            'incident_grade': "등급별",
            'cause_type': "원인유형별"
        }
        
        for group_type in group_by:
            if group_type in group_titles:
                title_parts.append(group_titles[group_type])
                break
        
        if db_stats['is_error_time_query']:
            title_parts.append("장애시간")
        else:
            title_parts.append("장애 발생 현황")
        
        return ' '.join(title_parts)

    def calculate_unified_statistics(self, documents, query, query_type="default"):
        """통합 통계 계산 - 무결성 보장 계산기 사용"""
        return self.statistics_calculator._empty_statistics() if not documents else self.statistics_calculator.calculate_comprehensive_statistics(query, documents, query_type)
