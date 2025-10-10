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
        
        # 연도 추출
        year_match = re.search(r'\b(202[0-9]|201[0-9])\b', query_lower)
        if year_match: conditions['year'] = year_match.group(1)
        
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
        self.statistics_db_manager = StatisticsDBManager()
        self.filter_manager = DocumentFilterManager(debug_mode=True)
        
        self.debug_mode = True
        self._decorator_logging_enabled = False
        self._manual_logging_enabled = True
    
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
        
        self.langsmith_enabled = LANGSMITH_ENABLED
        self._setup_langsmith()

    def generate_rag_response_with_data_integrity(self, query, documents, query_type="default", time_conditions=None, department_conditions=None, reprompting_info=None):
        """🚨 RAG 데이터 무결성을 절대 보장하는 응답 생성"""
        if not documents:
            return "검색된 문서가 없어서 답변을 제공할 수 없습니다."
        
        try:
            # 🚨 원본 데이터 보존을 위한 전처리
            integrity_documents = [self.normalizer.normalize_document_with_integrity(doc) for doc in documents]
            
            if self.debug_mode:
                print(f"DEBUG: Data integrity preserved for {len(integrity_documents)} documents")
            
            # 통계 계산 - statistics 쿼리타입에서만 차트 생성
            if query_type == "statistics":
                return self._generate_statistics_response_with_integrity(query, integrity_documents)
            
            # 정렬 적용
            sort_info = self.detect_sorting_requirements(query)
            processing_documents = self.apply_custom_sorting(integrity_documents, sort_info)
            
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
            # 1. DB 우선 조회 시도
            db_statistics = self.statistics_db_manager.get_statistics(query)
            
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

    def _format_db_statistics_with_integrity(self, db_stats, query):
        """DB 통계 결과를 데이터 무결성 보장하여 포맷팅"""
        try:
            conditions = db_stats['query_conditions']
            query_scope = self._determine_query_scope(conditions)
            
            # 무결성 보장 프롬프트
            integrity_prompt = f"""당신은 IT 통계 전문가입니다.

🚨 데이터 무결성 절대 보장 🚨
- 제공된 통계 수치를 절대 변경하지 마세요
- 계산하거나 추정하지 마세요
- 원본 수치 그대로 출력하세요

**요청 범위**: {query_scope}
**원본 통계 데이터** (절대 변경 금지):
{self._format_db_statistics_for_prompt_with_integrity(db_stats, conditions)}

위 원본 통계 수치를 정확히 그대로 사용하여 응답하세요."""

            response = self.azure_openai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": integrity_prompt},
                    {"role": "user", "content": f"사용자 질문: {query}\n\n위 원본 통계 데이터를 그대로 사용하여 답변하세요."}
                ],
                temperature=0.0,
                max_tokens=2000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"통계 포맷팅 중 오류: {str(e)}"
    
    def _format_db_statistics_for_prompt_with_integrity(self, db_stats, conditions):
        """DB 통계를 무결성 보장하여 프롬프트용 텍스트로 변환"""
        lines = []
        
        value_type = "장애시간(분)" if db_stats['is_error_time_query'] else "발생건수"
        lines.append(f"**데이터 유형**: {value_type}")
        lines.append(f"**이 {value_type}**: {db_stats['total_value']}")
        
        # 연도별 통계 (원본 수치 그대로)
        if db_stats['yearly_stats']:
            lines.append(f"\n**📅 연도별 {value_type}**:")
            for year, value in sorted(db_stats['yearly_stats'].items()):
                lines.append(f"* {year}: {value}건")
        
        # 월별 통계 (원본 수치 그대로)
        if db_stats['monthly_stats']:
            lines.append(f"\n**📅 월별 {value_type}**:")
            sorted_months = sorted(db_stats['monthly_stats'].items(), key=lambda x: int(x[0].replace('월', '')))
            for month, value in sorted_months:
                lines.append(f"* {month}: {value}건")
        
        # 기타 통계들도 원본 수치 그대로
        stat_types = [
            ('time_stats', '시간대별/요일별'),
            ('department_stats', '부서별'), 
            ('service_stats', '서비스별'),
            ('grade_stats', '등급별'),
            ('cause_type_stats', '원인유형별')
        ]
        
        for stat_key, title in stat_types:
            if stat_key == 'time_stats':
                # 시간대별
                if db_stats['time_stats']['daynight']:
                    lines.append(f"\n**🕘 시간대별 {value_type}**:")
                    for time, value in db_stats['time_stats']['daynight'].items():
                        lines.append(f"* {time}: {value}건")
                
                # 요일별  
                if db_stats['time_stats']['week']:
                    lines.append(f"\n**📅 요일별 {value_type}**:")
                    for day, value in db_stats['time_stats']['week'].items():
                        lines.append(f"* {day}: {value}건")
            
            elif db_stats.get(stat_key):
                lines.append(f"\n**{title} {value_type}**:")
                if stat_key == 'grade_stats':
                    # 등급 순서 보장
                    grade_order = ['1등급', '2등급', '3등급', '4등급']
                    for grade in grade_order:
                        if grade in db_stats[stat_key]:
                            lines.append(f"* {grade}: {db_stats[stat_key][grade]}건")
                else:
                    # 상위 10개
                    sorted_items = sorted(db_stats[stat_key].items(), key=lambda x: x[1], reverse=True)[:10]
                    for item, value in sorted_items:
                        lines.append(f"* {item}: {value}건")
        
        lines.append(f"\n⚠️ **중요**: 위 모든 수치는 원본 DB 데이터이므로 절대 변경하지 마세요.")
        
        return '\n'.join(lines)

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
        """통합 통계 계산 - 무결성 보장 계산기 사용"""
        return self.statistics_calculator._empty_statistics() if not documents else self.statistics_calculator.calculate_comprehensive_statistics(query, documents, query_type)

    @traceable(name="check_reprompting_question")
    def check_and_transform_query_with_reprompting(self, user_query):
        """개선된 리프롬프팅 - 강제 치환 추가"""
        if not user_query:
            return {'transformed': False, 'original_query': user_query, 'transformed_query': user_query, 'match_type': 'none'}
        
        force_replaced_query = self.force_replace_problematic_queries(user_query)
        
        with trace(name="reprompting_check", inputs={"user_query": user_query, "force_replaced": force_replaced_query}) as trace_context:
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

    @traceable(name="classify_query_type")
    def classify_query_type_with_llm(self, query):
        """LLM 기반 의미적 쿼리 분류 - 4가지 타입으로 단순화"""
        if not query:
            return 'default'
        
        print(f"DEBUG: Starting semantic query classification for: '{query}'")
        
        with trace(name="llm_semantic_classification", inputs={"query": query}) as trace_context:
            try:
                classification_prompt = f"""다음 사용자 질문을 의미적으로 분석하여 정확히 분류하세요.

**분류 카테고리:**

1. **repair**: 복구방법, 해결방법, 장애원인 분석, 유사사례 문의
   - 핵심 의도: 문제를 해결하거나 원인을 파악하려는 목적 
   - 예시: "로그인 불가 복구방법", "에러 해결방법", "장애원인 분석", "왜 발생했나", "유사한 장애", "어떻게 해결"

2. **inquiry**: 특정 조건의 장애 내역 조회 및 리스트 요청
   - 핵심 의도: 조건에 맞는 장애 목록이나 내역을 보고 싶은 목적 
   - 예시: "ERP 장애내역", "2025년 장애 목록", "야간 장애내역", "내역을 보여줘", "목록 제공"

3. **statistics**: 통계 데이터, 집계, 건수, 분포 등의 수치 정보 요청
   - 핵심 의도: 숫자나 통계로 현황을 파악하려는 목적 
   - 예시: "장애건수", "몇건이야", "통계", "분포", "연도별", "월별", "차트", "현황"

4. **default**: 위 세 카테고리에 해당하지 않는 일반적인 질문
   - 핵심 의도: 위 세 가지가 아닌 기타 문의

**분류 지침:**
- 질문의 전체적인 맥락과 사용자의 의도를 파악하세요
- 키워드보다는 질문의 목적과 기대하는 답변 형태를 고려하세요
- 애매한 경우, 사용자가 원하는 최종 결과물을 생각해보세요

**사용자 질문:** {query}

**응답 형식:** repair, inquiry, statistics, default 중 하나만 출력하세요."""

                response = self.azure_openai_client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "당신은 IT 질문을 의미적으로 분석하여 정확히 분류하는 전문가입니다. 사용자의 진정한 의도와 목적을 파악하여 분류하세요."},
                        {"role": "user", "content": classification_prompt}
                    ],
                    temperature=0.0,
                    max_tokens=50
                )
                
                query_type = response.choices[0].message.content.strip().lower()
                
                if query_type not in ['repair', 'inquiry', 'statistics', 'default']:
                    print(f"WARNING: Invalid query type '{query_type}', falling back to default")
                    query_type = 'default'
                
                print(f"DEBUG: LLM semantic classification result: {query_type}")
                
                confidence_score = self._calculate_classification_confidence(query, query_type)
                print(f"DEBUG: Classification confidence: {confidence_score:.2f}")
                
                return query_type
                    
            except Exception as e:
                print(f"ERROR: LLM semantic classification failed: {e}")
                return self._fallback_classification(query)

    def _calculate_classification_confidence(self, query, predicted_type):
        """분류 결과에 대한 신뢰도 계산"""
        try:
            query_lower = query.lower()
            
            strong_signals = {
                'repair': ['복구방법', '해결방법', '조치방법', '불가', '실패', '원인', '왜', '어떻게'],
                'inquiry': ['내역', '목록', '리스트', '조회', '보여줘', '알려줘'],
                'statistics': ['건수', '몇건', '통계', '현황', '분포', '차트', '연도별', '월별'],
                'default': []
            }
            
            predicted_signals = strong_signals.get(predicted_type, [])
            signal_count = sum(1 for signal in predicted_signals if signal in query_lower)
            
            conflicting_signals = 0
            for other_type, signals in strong_signals.items():
                if other_type != predicted_type:
                    conflicting_signals += sum(1 for signal in signals if signal in query_lower)
            
            confidence = 0.5
            if signal_count > 0:
                confidence += 0.3 * min(signal_count, 2) / 2
            if conflicting_signals > 0:
                confidence -= 0.2 * min(conflicting_signals, 2) / 2
            
            return max(0.0, min(1.0, confidence))
            
        except Exception:
            return 0.5

    def _fallback_classification(self, query):
        """LLM 실패시 간단한 fallback 분류"""
        if not query:
            return 'default'
        
        query_lower = query.lower()
        
        if any(word in query_lower for word in ['복구방법', '해결방법', '조치방법']):
            return 'repair'
        elif any(word in query_lower for word in ['내역', '목록', '리스트']):
            return 'inquiry'  
        elif any(word in query_lower for word in ['건수', '몇건', '통계', '현황']):
            return 'statistics'
        else:
            return 'default'

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

    def remove_text_charts_from_response(self, response_text):
        if not response_text:
            return response_text
        
        patterns = [r'각\s*월별.*?차트로\s*나타낼\s*수\s*있습니다:.*?(?=\n\n|\n[^월"\d]|$)', r'\d+월:\s*[▬▓▒▒▬\*\-\|]+.*?(?=\n\n|\n[^월"\d]|$)', r'\n.*[▬▓▒▒▬\*\-\|]{2,}.*\n', r'```[^`]*[▬▓▒▒▬\*\-\|]{2,}[^`]*```']
        cleaned_response = response_text
        for pattern in patterns:
            cleaned_response = re.sub(pattern, '', cleaned_response, flags=re.MULTILINE | re.DOTALL)
        return re.sub(r'\n{3,}', '\n\n', cleaned_response).strip()

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

    @traceable(name="process_user_query")
    def process_query(self, query, query_type=None):
        """메인 쿼리 처리"""
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
        
        if statistics_count >= 2 and any(word in response_lower for word in ['차트', '표', '이', '합계']):
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
            if hasattr(self, '_decorator_logging_enabled') and self._decorator_logging_enabled:
                print(f"DEBUG: 데코레이터 로깅이 활성화되어 수동 로깅을 건너뜁니다.")
                return
                
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

    def _calculate_statistics_with_integrity(self, documents, query):
        """문서 기반 통계 계산 - 데이터 무결성 보장"""
        try:
            stats = self.statistics_calculator.calculate_comprehensive_statistics(query, documents, "statistics")
            
            if not stats or stats.get('total_count', 0) == 0:
                return "조건에 맞는 장애 데이터를 찾을 수 없습니다."
            
            # 통계 응답 생성
            response_lines = []
            
            # 기본 통계 정보
            total_count = stats.get('total_count', 0)
            is_error_time = stats.get('is_error_time_query', False)
            value_type = "장애시간(분)" if is_error_time else "발생건수"
            
            response_lines.append(f"## 📊 통계 요약")
            response_lines.append(f"**이 {value_type}: {total_count}**")
            
            # 연도별 통계
            if stats.get('yearly_stats'):
                response_lines.append(f"\n## 📈 연도별 통계")
                for year, count in sorted(stats['yearly_stats'].items()):
                    response_lines.append(f"* **{year}: {count}건**")
                response_lines.append(f"\n**💡 이 합계: {sum(stats['yearly_stats'].values())}건**")
            
            # 월별 통계
            if stats.get('monthly_stats'):
                response_lines.append(f"\n## 📈 월별 통계")
                sorted_months = sorted(stats['monthly_stats'].items(), key=lambda x: int(x[0].replace('월', '')))
                for month, count in sorted_months:
                    response_lines.append(f"* **{month}: {count}건**")
                response_lines.append(f"\n**💡 이 합계: {sum(stats['monthly_stats'].values())}건**")
            
            # 등급별 통계
            if stats.get('grade_stats'):
                response_lines.append(f"\n## ⚠️ 장애등급별 통계")
                grade_order = ['1등급', '2등급', '3등급', '4등급']
                for grade in grade_order:
                    if grade in stats['grade_stats']:
                        response_lines.append(f"* **{grade}: {stats['grade_stats'][grade]}건**")
                response_lines.append(f"\n**💡 이 합계: {sum(stats['grade_stats'].values())}건**")
            
            # 서비스별 통계 (상위 10개)
            if stats.get('service_stats'):
                response_lines.append(f"\n## 💻 서비스별 통계 (상위 10개)")
                sorted_services = sorted(stats['service_stats'].items(), key=lambda x: x[1], reverse=True)[:10]
                for service, count in sorted_services:
                    response_lines.append(f"* **{service}: {count}건**")
                response_lines.append(f"\n**💡 상위 10개 합계: {sum(count for _, count in sorted_services)}건**")
            
            # 부서별 통계 (상위 10개)
            if stats.get('department_stats'):
                response_lines.append(f"\n## 🏢 부서별 통계 (상위 10개)")
                sorted_departments = sorted(stats['department_stats'].items(), key=lambda x: x[1], reverse=True)[:10]
                for dept, count in sorted_departments:
                    response_lines.append(f"* **{dept}: {count}건**")
                response_lines.append(f"\n**💡 상위 10개 합계: {sum(count for _, count in sorted_departments)}건**")
            
            # 시간대별 통계
            if stats.get('time_stats', {}).get('daynight'):
                response_lines.append(f"\n## 🕘 시간대별 통계")
                for time, count in stats['time_stats']['daynight'].items():
                    response_lines.append(f"* **{time}: {count}건**")
                response_lines.append(f"\n**💡 이 합계: {sum(stats['time_stats']['daynight'].values())}건**")
            
            # 요일별 통계
            if stats.get('time_stats', {}).get('week'):
                response_lines.append(f"\n## 📅 요일별 통계")
                for day, count in stats['time_stats']['week'].items():
                    response_lines.append(f"* **{day}: {count}건**")
                response_lines.append(f"\n**💡 이 합계: {sum(stats['time_stats']['week'].values())}건**")
            
            return '\n'.join(response_lines)
            
        except Exception as e:
            print(f"ERROR: 문서 기반 통계 계산 실패: {e}")
            import traceback
            traceback.print_exc()
            return f"통계 계산 중 오류가 발생했습니다: {str(e)}"

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
    
    def _format_db_statistics_for_prompt(self, db_stats, conditions):
        """DB 통계를 프롬프트용 텍스트로 변환"""
        lines = []
        
        value_type = "장애시간(분)" if db_stats['is_error_time_query'] else "발생건수"
        query_scope = self._determine_query_scope(conditions)
        
        lines.append(f"**요청 범위**: {query_scope}")
        lines.append(f"**데이터 유형**: {value_type}")
        lines.append(f"**총 {value_type}**: {db_stats['total_value']}")
        
        if db_stats['yearly_stats']:
            lines.append(f"\n**📅 연도별 {value_type}**:")
            for year, value in sorted(db_stats['yearly_stats'].items()):
                lines.append(f"* **{year}: {value}건**")
            lines.append(f"\n**💡 총 합계: {sum(db_stats['yearly_stats'].values())}건**")
        
        if db_stats['monthly_stats']:
            lines.append(f"\n**📅 월별 {value_type}**:")
            sorted_months = sorted(db_stats['monthly_stats'].items(), key=lambda x: int(x[0].replace('월', '')))
            for month, value in sorted_months:
                lines.append(f"* **{month}: {value}건**")
            lines.append(f"\n**💡 총 합계: {sum(db_stats['monthly_stats'].values())}건**")
        
        if db_stats['time_stats']['daynight']:
            lines.append(f"\n**🕘 시간대별 {value_type}**:")
            for time, value in db_stats['time_stats']['daynight'].items():
                lines.append(f"* **{time}: {value}건**")
            lines.append(f"\n**💡 총 합계: {sum(db_stats['time_stats']['daynight'].values())}건**")
        
        if db_stats['time_stats']['week']:
            lines.append(f"\n**📅 요일별 {value_type}**:")
            week_order = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']
            week_stats = db_stats['time_stats']['week']
            
            for day in week_order:
                if day in week_stats:
                    lines.append(f"* **{day}: {week_stats[day]}건**")
            
            if '평일' in week_stats:
                lines.append(f"* **평일: {week_stats['평일']}건**")
            if '주말' in week_stats:
                lines.append(f"* **주말: {week_stats['주말']}건**")
                
            lines.append(f"\n**💡 총 합계: {sum(week_stats.values())}건**")
        
        # 부서별, 서비스별, 등급별, 원인유형별 통계 처리
        stat_types = [
            ('department_stats', '🏢 부서별', 'department'),
            ('service_stats', '💻 서비스별', 'service'),
            ('grade_stats', '⚠️ 장애등급별', 'grade'),
            ('cause_type_stats', '🔍 원인유형별', 'cause')
        ]
        
        for stat_key, title, stat_type in stat_types:
            if db_stats.get(stat_key):
                lines.append(f"\n**{title} {value_type} (상위 10개)**:")
                if stat_type == 'grade':
                    grade_order = ['1등급', '2등급', '3등급', '4등급']
                    grade_stats = db_stats[stat_key]
                    
                    for grade in grade_order:
                        if grade in grade_stats:
                            lines.append(f"* **{grade}: {grade_stats[grade]}건**")
                    
                    for grade, value in sorted(grade_stats.items()):
                        if grade not in grade_order:
                            lines.append(f"* **{grade}: {value}건**")
                    
                    lines.append(f"\n**💡 총 합계: {sum(grade_stats.values())}건**")
                else:
                    sorted_items = sorted(db_stats[stat_key].items(), key=lambda x: x[1], reverse=True)[:10]
                    for item, value in sorted_items:
                        lines.append(f"* **{item}: {value}건**")
                    lines.append(f"\n**💡 상위 10개 합계: {sum(value for _, value in sorted_items)}건**")
        
        lines.append(f"\n⚠️ **중요**: 위 통계는 모두 '{query_scope}' 범위의 데이터입니다.")
        
        return '\n'.join(lines)
    
    def _format_incident_details_for_prompt(self, incidents):
        """장애 상세 내역을 프롬프트용 텍스트로 변환"""
        lines = []
        
        week_mapping = {'월': '월요일', '화': '화요일', '수': '수요일', '목': '목요일', '금': '금요일', '토': '토요일', '일': '일요일'}
        
        for i, incident in enumerate(incidents, 1):
            lines.append(f"### {i}. 장애 ID: {incident.get('incident_id', 'N/A')}")
            lines.append(f"- 서비스명: {incident.get('service_name', 'N/A')}")
            lines.append(f"- 발생일자: {incident.get('error_date', 'N/A')}")
            lines.append(f"- 장애시간: {incident.get('error_time', 0)}분")
            
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

    @traceable(name="process_user_query")
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
            if hasattr(self, '_decorator_logging_enabled') and self._decorator_logging_enabled:
                print(f"DEBUG: 데코레이터 로깅이 활성화되어 수동 로깅을 건너뜁니다.")
                return
                
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

    def _remove_all_box_markers(self, text):
        """모든 박스 마커 강화 제거"""
        import re
        
        # 복구방법 박스 마커 제거
        text = re.sub(r'\[REPAIR_BOX_START\].*?\[REPAIR_BOX_END\]', '', text, flags=re.DOTALL)
        
        # 기타 박스 마커들 제거
        text = re.sub(r'\[.*?_BOX_START\].*?\[.*?_BOX_END\]', '', text, flags=re.DOTALL)
        
        return text

    def _remove_repair_sections(self, text):
        """복구방법 관련 섹션 제거"""
        import re
        
        lines = text.split('\n')
        cleaned_lines = []
        skip_section = False
        
        for line in lines:
            line_lower = line.lower().strip()
            
            # 복구방법 섹션 시작 감지
            if any(keyword in line_lower for keyword in [
                '복구방법', '복구절차', '조치방법', '해결방법', '대응방법',
                'repair', 'recovery', 'solution'
            ]):
                skip_section = True
                continue
                
            # 다른 섹션 시작되면 스킵 해제
            if line.startswith('#') or line.startswith('##') or line.startswith('Case'):
                skip_section = False
                
            # 표 시작되면 스킵 해제
            if '|' in line and '장애 ID' in line:
                skip_section = False
                
            if not skip_section:
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)

    def _generate_statistics_response_from_db(self, query, documents):
        """DB 직접 조회를 통한 정확한 통계 응답 생성"""
        try:
            db_statistics = self.statistics_db_manager.get_statistics(query)
            
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
            
            conditions = db_statistics['query_conditions']
            filtered_statistics = self._filter_statistics_by_conditions(db_statistics, conditions)
            incident_details = self.statistics_db_manager.get_incident_details(conditions, limit=100)
            
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
            
            statistics_summary = self._format_db_statistics_for_prompt(filtered_statistics, conditions)
            incident_list = self._format_incident_details_for_prompt(incident_details[:50])
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

**부서별 통계:**
* **재무DX개발팀: X건**
* **시스템운영팀: Y건**
* **보안침해대응팀: Z건**
**💡 총 합계: N건**

## 절대 규칙
1. **사용자가 요청한 범위의 데이터만 답변하세요**
2. 요청하지 않은 연도나 기간의 데이터는 절대 포함하지 마세요
3. 제공된 통계 수치를 절대 변경하지 마세요
4. 추가 계산이나 추정을 하지 마세요
5. **리스트 형태로 통계를 표시하고 총 합계를 명확히 표시하세요**
6. **근거 문서 내역은 절대 답변에 포함하지 마세요**

## 응답 형식
1. **📊 {query_scope} 통계 요약** (2-3문장)
2. **📈 상세 통계** (위 형식에 따른 리스트 표시)

답변은 명확하고 구조화된 형식으로 작성하되, 제공된 수치를 정확히 인용하세요.
근거 문서 내역은 별도로 처리되므로 답변에 포함하지 마세요.
"""

            user_prompt = f"""## 사용자 질문
{query}

## 요청 범위: {query_scope}

## 정확하게 계산된 통계 데이터 ({query_scope} 범위만)
{statistics_summary}

위 데이터를 바탕으로 **{query_scope} 범위만** 명확하고 친절하게 답변하세요.
반드시 다음 구조를 따르세요:

1. **📊 {query_scope} 통계 요약**
- 핵심 수치와 인사이트 (2-3문장)

2. **📈 상세 통계**
[위에서 지정한 리스트 형식에 따라 표시]
**💡 총 합계: [전체 합계]**

⚠️ 중요: 요청하지 않은 연도나 기간의 통계는 절대 포함하지 마세요.
근거 문서 내역은 답변에 포함하지 마세요.
"""

            response = self.azure_openai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0,
                max_tokens=3000
            )
            
            final_answer = response.choices[0].message.content
            
            # 근거 문서 내역을 st.expander로 표시
            if incident_details and len(incident_details) > 0:
                with st.expander(f"📋 근거 문서 내역 (총 {len(incident_details)}건)", expanded=False):
                    
                    week_mapping = {'월': '월요일', '화': '화요일', '수': '수요일', '목': '목요일', '금': '금요일', '토': '토요일', '일': '일요일'}
                    
                    if len(incident_details) >= 15:
                        st.markdown("### 📋 통계로 집계된 장애 내역 (요약)")
                        st.markdown("*문서가 많아 요약 형태로 제공됩니다*")
                        
                        for i, incident in enumerate(incident_details, 1):
                            # 등급 포맷팅
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
                            
                            # 요일 포맷팅
                            week_value = incident.get('week', '')
                            formatted_week = week_mapping.get(week_value, week_value) if week_value else ''
                            
                            # 장애현상 요약
                            symptom = incident.get('symptom', '')[:50] + '...' if len(incident.get('symptom', '')) > 50 else incident.get('symptom', '')
                            
                            summary_line = f"**{i}.** `{incident.get('incident_id', 'N/A')}` | " \
                                        f"{incident.get('service_name', 'N/A')} | " \
                                        f"{incident.get('error_date', 'N/A')} | " \
                                        f"{incident.get('error_time', 0)}분 | " \
                                        f"{formatted_grade}"
                            
                            time_info = []
                            if incident.get('daynight'):
                                time_info.append(incident.get('daynight'))
                            if formatted_week:
                                time_info.append(formatted_week)
                            
                            if time_info:
                                summary_line += f" | {'/'.join(time_info)}"
                            
                            if symptom:
                                summary_line += f"\n   🔍 *{symptom}*"
                            
                            st.markdown(summary_line)
                            
                            if i % 10 == 0 and i < len(incident_details):
                                st.markdown("---")
                    
                    else:
                        st.markdown("### 📋 통계로 집계된 장애 내역 (상세)")
                        
                        for i, incident in enumerate(incident_details, 1):
                            st.markdown(f"#### {i}. 장애 ID: {incident.get('incident_id', 'N/A')}")
                            
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.write(f"- 서비스명: {incident.get('service_name', 'N/A')}")
                                st.write(f"- 발생일자: {incident.get('error_date', 'N/A')}")
                                st.write(f"- 장애시간: {incident.get('error_time', 0)}분")
                                
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
                                st.write(f"- 장애등급: {formatted_grade}")
                                
                                st.write(f"- 담당부서: {incident.get('owner_depart', 'N/A')}")
                            
                            with col2:
                                if incident.get('daynight'):
                                    st.write(f"- 시간대: {incident.get('daynight')}")
                                    
                                if incident.get('week'):
                                    week_value = incident.get('week')
                                    formatted_week = week_mapping.get(week_value, week_value)
                                    st.write(f"- 요일: {formatted_week}")
                                    
                                if incident.get('cause_type'):
                                    st.write(f"- 원인유형: {incident.get('cause_type')}")
                            
                            symptom = incident.get('symptom', '')
                            if symptom:
                                st.write(f"- 장애현상: {symptom[:150]}...")
                            
                            root_cause = incident.get('root_cause', '')
                            if root_cause:
                                st.write(f"- 장애원인: {root_cause[:150]}...")
                            
                            if i < len(incident_details):
                                st.markdown("---")
            
            return (final_answer, chart_info) if chart_info else final_answer
            
        except Exception as e:
            print(f"ERROR: 통계 응답 생성 실패: {e}")
            import traceback
            traceback.print_exc()
            return f"통계 조회 중 오류가 발생했습니다: {str(e)}"

    def _calculate_statistics_with_integrity(self, documents, query):
        """문서 기반 통계 계산 - 데이터 무결성 보장"""
        try:
            # 무결성 보장 통계 계산기를 사용하여 통계 계산
            stats = self.statistics_calculator.calculate_comprehensive_statistics(query, documents, "statistics")
            
            if not stats or stats.get('total_count', 0) == 0:
                return "조건에 맞는 장애 데이터를 찾을 수 없습니다."
            
            # 통계 응답 생성
            response_lines = []
            
            # 기본 통계 정보
            total_count = stats.get('total_count', 0)
            is_error_time = stats.get('is_error_time_query', False)
            value_type = "장애시간(분)" if is_error_time else "발생건수"
            
            response_lines.append(f"## 📊 통계 요약")
            response_lines.append(f"**총 {value_type}: {total_count}**")
            
            # 연도별 통계
            if stats.get('yearly_stats'):
                response_lines.append(f"\n## 📈 연도별 통계")
                for year, count in sorted(stats['yearly_stats'].items()):
                    response_lines.append(f"* **{year}: {count}건**")
                response_lines.append(f"\n**💡 총 합계: {sum(stats['yearly_stats'].values())}건**")
            
            # 월별 통계
            if stats.get('monthly_stats'):
                response_lines.append(f"\n## 📈 월별 통계")
                sorted_months = sorted(stats['monthly_stats'].items(), key=lambda x: int(x[0].replace('월', '')))
                for month, count in sorted_months:
                    response_lines.append(f"* **{month}: {count}건**")
                response_lines.append(f"\n**💡 총 합계: {sum(stats['monthly_stats'].values())}건**")
            
            # 등급별 통계
            if stats.get('grade_stats'):
                response_lines.append(f"\n## ⚠️ 장애등급별 통계")
                grade_order = ['1등급', '2등급', '3등급', '4등급']
                for grade in grade_order:
                    if grade in stats['grade_stats']:
                        response_lines.append(f"* **{grade}: {stats['grade_stats'][grade]}건**")
                response_lines.append(f"\n**💡 총 합계: {sum(stats['grade_stats'].values())}건**")
            
            # 서비스별 통계 (상위 10개)
            if stats.get('service_stats'):
                response_lines.append(f"\n## 💻 서비스별 통계 (상위 10개)")
                sorted_services = sorted(stats['service_stats'].items(), key=lambda x: x[1], reverse=True)[:10]
                for service, count in sorted_services:
                    response_lines.append(f"* **{service}: {count}건**")
                response_lines.append(f"\n**💡 상위 10개 합계: {sum(count for _, count in sorted_services)}건**")
            
            # 부서별 통계 (상위 10개)
            if stats.get('department_stats'):
                response_lines.append(f"\n## 🏢 부서별 통계 (상위 10개)")
                sorted_departments = sorted(stats['department_stats'].items(), key=lambda x: x[1], reverse=True)[:10]
                for dept, count in sorted_departments:
                    response_lines.append(f"* **{dept}: {count}건**")
                response_lines.append(f"\n**💡 상위 10개 합계: {sum(count for _, count in sorted_departments)}건**")
            
            # 시간대별 통계
            if stats.get('time_stats', {}).get('daynight'):
                response_lines.append(f"\n## 🕘 시간대별 통계")
                for time, count in stats['time_stats']['daynight'].items():
                    response_lines.append(f"* **{time}: {count}건**")
                response_lines.append(f"\n**💡 총 합계: {sum(stats['time_stats']['daynight'].values())}건**")
            
            # 요일별 통계
            if stats.get('time_stats', {}).get('week'):
                response_lines.append(f"\n## 📅 요일별 통계")
                for day, count in stats['time_stats']['week'].items():
                    response_lines.append(f"* **{day}: {count}건**")
                response_lines.append(f"\n**💡 총 합계: {sum(stats['time_stats']['week'].values())}건**")
            
            return '\n'.join(response_lines)
            
        except Exception as e:
            print(f"ERROR: 문서 기반 통계 계산 실패: {e}")
            import traceback
            traceback.print_exc()
            return f"통계 계산 중 오류가 발생했습니다: {str(e)}"        

    def _verify_service_name_in_db(self, service_name):
        """DB에서 서비스명 존재 여부 및 유사 서비스 검증"""
        try:
            # 정확한 매치 확인
            exact_query = f"SELECT DISTINCT service_name FROM incidents WHERE service_name = ? LIMIT 1"
            exact_result = self.statistics_db_manager._execute_query(exact_query, (service_name,))
            
            if exact_result:
                return {'exists': True, 'exact_match': service_name, 'similar_services': []}
            
            # 부분 매치 확인
            partial_query = f"SELECT DISTINCT service_name FROM incidents WHERE service_name LIKE ? LIMIT 5"
            partial_result = self.statistics_db_manager._execute_query(partial_query, (f"%{service_name}%",))
            
            similar_services = [row['service_name'] for row in partial_result]
            
            return {
                'exists': len(similar_services) > 0,
                'exact_match': None,
                'similar_services': similar_services
            }
            
        except Exception as e:
            print(f"ERROR: Service name verification failed: {e}")
            return {'exists': False, 'exact_match': None, 'similar_services': []}

    def _get_total_count_without_service_filter(self, query):
        """서비스 필터 없이 전체 건수 조회 (검증용)"""
        try:
            # 서비스명을 제외한 조건으로 쿼리 생성
            test_conditions = self.statistics_db_manager.parse_statistics_query(query)
            test_conditions['service_name'] = None  # 서비스명 조건 제거
            
            sql_query, params, _ = self.statistics_db_manager.build_sql_query(test_conditions)
            results = self.statistics_db_manager._execute_query(sql_query, params)
            
            if results and not test_conditions['group_by']:
                return results[0].get('total_value', 0)
            elif results:
                return sum(row.get('total_value', 0) for row in results)
            
            return 0
        except:
            return 0

    def _add_explicit_service_condition(self, query, service_name):
        """쿼리에 명시적으로 서비스명 조건 추가 - 안전한 문자열 처리"""
        if not service_name:
            return query
        
        # service_name이 튜플인 경우 처리
        if isinstance(service_name, tuple):
            service_name = service_name[0] if service_name else ""
        
        # 문자열로 변환 및 정리
        service_name = str(service_name).strip()
        
        if not service_name:
            return query
        
        # 이미 서비스명이 포함되어 있는지 확인
        if service_name.lower() in query.lower():
            return query
        
        # 서비스명을 쿼리 앞에 추가
        return f"{service_name} {query}"