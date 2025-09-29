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

# MonitoringManager import 추가
try:
    from utils.monitoring_manager import MonitoringManager
    MONITORING_AVAILABLE = True
except ImportError as e:
    print(f"DEBUG: MonitoringManager not available: {e}")
    MONITORING_AVAILABLE = False
    # 폴백을 위한 더미 클래스
    class MonitoringManager:
        def __init__(self, *args, **kwargs):
            pass
        def log_user_activity(self, *args, **kwargs):
            pass

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
            def decorator(func):
                return func
            return decorator
        
        def trace(name=None, **kwargs):
            class DummyTrace:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
                def update(self, **kwargs):
                    pass
            return DummyTrace()
else:
    LANGSMITH_AVAILABLE = False
    def traceable(name=None, **kwargs):
        def decorator(func):
            return func
        return decorator
    
    def trace(name=None, **kwargs):
        class DummyTrace:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def update(self, **kwargs):
                pass
        return DummyTrace()

class StatisticsValidator:
    """통계 계산 검증 클래스"""
    
    def __init__(self):
        self.validation_errors = []
        self.validation_warnings = []
    
    def validate_document(self, doc, doc_index):
        """개별 문서 데이터 검증"""
        errors = []
        warnings = []
        
        required_fields = ['incident_id', 'service_name', 'error_date']
        for field in required_fields:
            if not doc.get(field):
                errors.append(f"문서 {doc_index}: {field} 필드가 비어있음")
        
        error_time = doc.get('error_time')
        if error_time is not None:
            try:
                error_time_int = int(error_time)
                if error_time_int < 0:
                    warnings.append(f"문서 {doc_index}: error_time이 음수 ({error_time_int})")
                elif error_time_int > 10080:
                    warnings.append(f"문서 {doc_index}: error_time이 비정상적으로 큼 ({error_time_int}분)")
            except (ValueError, TypeError):
                errors.append(f"문서 {doc_index}: error_time 형식 오류 ({error_time})")
        
        error_date = doc.get('error_date')
        if error_date:
            try:
                if len(str(error_date)) >= 4:
                    year = int(str(error_date)[:4])
                    if year < 2000 or year > 2030:
                        warnings.append(f"문서 {doc_index}: 비정상적인 연도 ({year})")
            except (ValueError, TypeError):
                warnings.append(f"문서 {doc_index}: error_date 형식 검증 실패 ({error_date})")
        
        return errors, warnings
    
    def validate_statistics_result(self, stats, original_doc_count):
        """통계 결과 검증"""
        errors = []
        warnings = []
        
        total_count = stats.get('total_count', 0)
        if total_count != original_doc_count:
            errors.append(f"총 개수 불일치: 계산된 개수({total_count}) != 원본 개수({original_doc_count})")
        
        yearly_stats = stats.get('yearly_stats', {})
        if yearly_stats:
            yearly_total = sum(yearly_stats.values())
            if yearly_total > total_count:
                warnings.append(f"연도별 합계({yearly_total})가 총 개수({total_count})를 초과")
        
        monthly_stats = stats.get('monthly_stats', {})
        if monthly_stats:
            monthly_total = sum(monthly_stats.values())
            if stats.get('is_error_time_query', False):
                if monthly_total < 0:
                    errors.append(f"월별 장애시간 합계가 음수: {monthly_total}")
            else:
                if monthly_total > total_count:
                    warnings.append(f"월별 건수 합계({monthly_total})가 총 개수({total_count})를 초과")
        
        return errors, warnings

class DataNormalizer:
    """데이터 정규화 클래스 - 날짜 추출 로직 개선"""
    
    @staticmethod
    def normalize_error_time(error_time):
        """error_time 필드 정규화"""
        if error_time is None:
            return 0
        
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
        """날짜 관련 필드 정규화 - 추출 로직 개선"""
        normalized_doc = doc.copy()
        
        error_date = doc.get('error_date', '')
        print(f"DEBUG: Normalizing error_date: {error_date}")
        
        if error_date:
            try:
                error_date_str = str(error_date).strip()
                
                # YYYY-MM-DD 형식 처리
                if '-' in error_date_str and len(error_date_str) >= 7:
                    parts = error_date_str.split('-')
                    if len(parts) >= 2:
                        # 연도 추출
                        if parts[0].isdigit() and len(parts[0]) == 4:
                            normalized_doc['extracted_year'] = parts[0]
                            print(f"DEBUG: Extracted year from error_date: {parts[0]}")
                        
                        # 월 추출
                        if parts[1].isdigit():
                            month_num = int(parts[1])
                            if 1 <= month_num <= 12:
                                normalized_doc['extracted_month'] = str(month_num)
                                print(f"DEBUG: Extracted month from error_date: {month_num}")
                
                # YYYYMMDD 형식 처리
                elif len(error_date_str) >= 8 and error_date_str.isdigit():
                    normalized_doc['extracted_year'] = error_date_str[:4]
                    month_str = error_date_str[4:6]
                    try:
                        month_num = int(month_str)
                        if 1 <= month_num <= 12:
                            normalized_doc['extracted_month'] = str(month_num)
                            print(f"DEBUG: Extracted year/month from YYYYMMDD: {error_date_str[:4]}/{month_num}")
                    except (ValueError, TypeError):
                        pass
                
                # YYYY 형식만 있는 경우
                elif len(error_date_str) >= 4 and error_date_str[:4].isdigit():
                    normalized_doc['extracted_year'] = error_date_str[:4]
                    print(f"DEBUG: Extracted year only: {error_date_str[:4]}")
                    
            except (ValueError, TypeError) as e:
                print(f"DEBUG: Error parsing error_date {error_date}: {e}")
                pass
        
        # 기존 year/month 필드가 없으면 추출된 값으로 설정
        if not normalized_doc.get('year') and normalized_doc.get('extracted_year'):
            normalized_doc['year'] = normalized_doc['extracted_year']
            print(f"DEBUG: Set year field: {normalized_doc['year']}")
        
        if not normalized_doc.get('month') and normalized_doc.get('extracted_month'):
            normalized_doc['month'] = normalized_doc['extracted_month']
            print(f"DEBUG: Set month field: {normalized_doc['month']}")
        
        # 기존 필드 정규화
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
        """문서 전체 정규화"""
        print(f"DEBUG: Normalizing document with incident_id: {doc.get('incident_id', 'N/A')}")
        
        normalized_doc = DataNormalizer.normalize_date_fields(doc)
        normalized_doc['error_time'] = DataNormalizer.normalize_error_time(doc.get('error_time'))
        
        # 문자열 필드들 정규화
        string_fields = ['service_name', 'incident_grade', 'owner_depart', 'daynight', 'week']
        for field in string_fields:
            value = normalized_doc.get(field)
            if value:
                normalized_doc[field] = str(value).strip()
            else:
                normalized_doc[field] = ''
        
        print(f"DEBUG: Normalized document - year: {normalized_doc.get('year')}, month: {normalized_doc.get('month')}")
        return normalized_doc

class ImprovedStatisticsCalculator:
    """개선된 통계 계산 클래스 - 중복 제거 옵션 추가"""
    
    def __init__(self, remove_duplicates=False):
        self.validator = StatisticsValidator()
        self.normalizer = DataNormalizer()
        self.remove_duplicates = remove_duplicates  # 중복 제거 옵션
    
    def _extract_filter_conditions(self, query):
        """쿼리에서 필터링 조건 추출 - 정확성 개선"""
        conditions = {
            'year': None,
            'month': None,
            'start_month': None,
            'end_month': None,
            'daynight': None,
            'week': None,
            'service_name': None,
            'department': None,
            'grade': None
        }
        
        if not query:
            return conditions
        
        query_lower = query.lower()
        print(f"DEBUG: Extracting conditions from query: '{query}'")
        
        # 연도 추출
        year_match = re.search(r'\b(202[0-9]|201[0-9])\b', query_lower)
        if year_match:
            conditions['year'] = year_match.group(1)
            print(f"DEBUG: Extracted year condition: {conditions['year']}")
        
        # 월 범위 추출
        month_range_patterns = [
            r'\b(\d+)\s*~\s*(\d+)월\b',
            r'\b(\d+)월\s*~\s*(\d+)월\b',  
            r'\b(\d+)\s*-\s*(\d+)월\b',
            r'\b(\d+)월\s*-\s*(\d+)월\b'
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
                    print(f"DEBUG: Extracted month range condition: {start_month}~{end_month}")
                    break
        
        # 단일 월 추출 (월 범위가 없는 경우만)
        if not month_range_found:
            month_match = re.search(r'\b(\d{1,2})월\b', query_lower)
            if month_match:
                month_num = int(month_match.group(1))
                if 1 <= month_num <= 12:
                    conditions['month'] = str(month_num)
                    print(f"DEBUG: Extracted single month condition: {month_num}")
        
        # 시간대 조건
        if any(word in query_lower for word in ['야간', '밤', '새벽', '심야']):
            conditions['daynight'] = '야간'
        elif any(word in query_lower for word in ['주간', '낮', '오전', '오후']):
            conditions['daynight'] = '주간'
        
        # 요일 조건
        week_patterns = {
            '월': ['월요일', '월'],
            '화': ['화요일', '화'],
            '수': ['수요일', '수'],
            '목': ['목요일', '목'],
            '금': ['금요일', '금'],
            '토': ['토요일', '토'],
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
        
        # 등급 조건
        grade_match = re.search(r'(\d+)등급', query_lower)
        if grade_match:
            conditions['grade'] = f"{grade_match.group(1)}등급"
        
        return conditions
    
    def _validate_document_against_conditions(self, doc, conditions):
        """문서가 조건에 정확히 맞는지 엄격하게 검증"""
        incident_id = doc.get('incident_id', 'N/A')
        
        # 연도 조건 확인
        if conditions['year']:
            doc_year = self._extract_year_from_document(doc)
            if not doc_year or doc_year != conditions['year']:
                print(f"DEBUG: Document {incident_id} filtered out - year mismatch. Expected: {conditions['year']}, Got: {doc_year}")
                return False, f"year mismatch (expected: {conditions['year']}, got: {doc_year})"
        
        # 월 범위 조건 확인
        if conditions['start_month'] and conditions['end_month']:
            doc_month = self._extract_month_from_document(doc)
            if not doc_month:
                print(f"DEBUG: Document {incident_id} filtered out - no month info")
                return False, "no month information"
            
            try:
                month_num = int(doc_month)
                if not (conditions['start_month'] <= month_num <= conditions['end_month']):
                    print(f"DEBUG: Document {incident_id} filtered out - month {month_num} not in range {conditions['start_month']}~{conditions['end_month']}")
                    return False, f"month {month_num} not in range {conditions['start_month']}~{conditions['end_month']}"
            except (ValueError, TypeError):
                print(f"DEBUG: Document {incident_id} filtered out - invalid month format: {doc_month}")
                return False, f"invalid month format: {doc_month}"
        
        # 단일 월 조건 확인
        elif conditions['month']:
            doc_month = self._extract_month_from_document(doc)
            if not doc_month or str(doc_month) != conditions['month']:
                print(f"DEBUG: Document {incident_id} filtered out - month mismatch. Expected: {conditions['month']}, Got: {doc_month}")
                return False, f"month mismatch (expected: {conditions['month']}, got: {doc_month})"
        
        # 시간대 조건 확인
        if conditions['daynight']:
            doc_daynight = doc.get('daynight', '').strip()
            required_daynight = conditions['daynight']
            
            if not doc_daynight:
                return False, f"no daynight information"
            elif doc_daynight != required_daynight:
                return False, f"daynight mismatch (expected: {required_daynight}, got: {doc_daynight})"
        
        # 요일 조건 확인
        if conditions['week']:
            doc_week = doc.get('week', '').strip()
            required_week = conditions['week']
            
            if required_week == '평일':
                if doc_week not in ['월', '화', '수', '목', '금']:
                    return False, f"not weekday (got: {doc_week})"
            elif required_week == '주말':
                if doc_week not in ['토', '일']:
                    return False, f"not weekend (got: {doc_week})"
            else:
                if not doc_week:
                    return False, f"no week information"
                elif doc_week != required_week:
                    return False, f"week mismatch (expected: {required_week}, got: {doc_week})"
        
        # 등급 조건 확인
        if conditions['grade']:
            doc_grade = doc.get('incident_grade', '')
            if doc_grade != conditions['grade']:
                return False, f"grade mismatch (expected: {conditions['grade']}, got: {doc_grade})"
        
        print(f"DEBUG: Document {incident_id} passed all conditions")
        return True, "passed"
    
    def _extract_year_from_document(self, doc):
        """문서에서 연도 정보 추출"""
        # 1순위: year 필드
        year = doc.get('year')
        if year:
            year_str = str(year).strip()
            if len(year_str) == 4 and year_str.isdigit():
                return year_str
        
        # 2순위: extracted_year 필드  
        year = doc.get('extracted_year')
        if year:
            year_str = str(year).strip()
            if len(year_str) == 4 and year_str.isdigit():
                return year_str
        
        # 3순위: error_date에서 추출
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
        """문서에서 월 정보 추출"""
        # 1순위: month 필드
        month = doc.get('month')
        if month:
            try:
                month_num = int(month)
                if 1 <= month_num <= 12:
                    return str(month_num)
            except (ValueError, TypeError):
                pass
        
        # 2순위: extracted_month 필드
        month = doc.get('extracted_month')
        if month:
            try:
                month_num = int(month)
                if 1 <= month_num <= 12:
                    return str(month_num)
            except (ValueError, TypeError):
                pass
        
        # 3순위: error_date에서 추출
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
        """필터 조건에 따른 문서 필터링 - 엄격한 검증 추가"""
        filtered_docs = []
        filter_stats = {
            'total_input': len(documents),
            'passed': 0,
            'filtered_reasons': {}
        }
        
        print(f"DEBUG: Starting filtering with conditions: {conditions}")
        print(f"DEBUG: Input documents: {len(documents)}")
        
        for doc in documents:
            incident_id = doc.get('incident_id', 'N/A')
            error_date = doc.get('error_date', 'N/A')
            
            is_valid, reason = self._validate_document_against_conditions(doc, conditions)
            
            if is_valid:
                filtered_docs.append(doc)
                filter_stats['passed'] += 1
                print(f"DEBUG: ✓ INCLUDED - ID: {incident_id}, Date: {error_date}")
            else:
                filter_stats['filtered_reasons'][reason] = filter_stats['filtered_reasons'].get(reason, 0) + 1
                print(f"DEBUG: ✗ EXCLUDED - ID: {incident_id}, Date: {error_date}, Reason: {reason}")
        
        print(f"DEBUG: Filtering complete - {filter_stats['passed']}/{filter_stats['total_input']} documents passed")
        print(f"DEBUG: Filter reasons: {filter_stats['filtered_reasons']}")
        
        return filtered_docs
    
    def _matches_conditions(self, doc, conditions):
        """조건 매칭 확인 (하위 호환성을 위해 유지)"""
        is_valid, _ = self._validate_document_against_conditions(doc, conditions)
        return is_valid
    
    def _empty_statistics(self):
        """빈 통계 반환"""
        return {
            'total_count': 0,
            'yearly_stats': {},
            'monthly_stats': {},
            'time_stats': {'daynight': {}, 'week': {}},
            'department_stats': {},
            'service_stats': {},
            'grade_stats': {},
            'is_error_time_query': False,
            'validation': {'errors': [], 'warnings': [], 'is_valid': True}
        }
    
    def _is_error_time_query(self, query):
        """장애시간 관련 쿼리인지 확인"""
        if not query:
            return False
        
        error_time_keywords = ['장애시간', '장애 시간', 'error_time', '시간 통계', '시간 합계', '시간 합산', '분']
        return any(keyword in query.lower() for keyword in error_time_keywords)
    
    def _calculate_detailed_statistics(self, documents, conditions, is_error_time_query):
        """상세 통계 계산 - 중복 제거 없이 모든 문서 처리"""
        stats = {
            'total_count': len(documents),
            'yearly_stats': {},
            'monthly_stats': {},
            'time_stats': {'daynight': {}, 'week': {}},
            'department_stats': {},
            'service_stats': {},
            'grade_stats': {},
            'is_error_time_query': is_error_time_query,
            'filter_conditions': conditions,
            'calculation_details': {}
        }
        
        print(f"DEBUG: Calculating statistics for {len(documents)} documents (NO DEDUPLICATION)")
        print(f"DEBUG: Filter conditions: {conditions}")
        
        # 문서별 처리 상황을 디버깅으로 확인
        print("DEBUG: Processing each document for statistics:")
        
        # 연도별 통계 - 모든 문서 처리
        for i, doc in enumerate(documents):
            incident_id = doc.get('incident_id', 'N/A')
            error_date = doc.get('error_date', 'N/A')
            year = self._extract_year_from_document(doc)
            
            print(f"DEBUG: Doc {i+1}: ID={incident_id}, Date={error_date}, Extracted_Year={year}")
            
            if year:
                if is_error_time_query:
                    error_time = doc.get('error_time', 0)
                    stats['yearly_stats'][year] = stats['yearly_stats'].get(year, 0) + error_time
                    print(f"DEBUG: Added {error_time} minutes to year {year}, total now: {stats['yearly_stats'][year]}")
                else:
                    stats['yearly_stats'][year] = stats['yearly_stats'].get(year, 0) + 1
                    print(f"DEBUG: Added 1 count to year {year}, total now: {stats['yearly_stats'][year]}")
            else:
                print(f"DEBUG: No year extracted for document {incident_id}")
        
        print(f"DEBUG: Final yearly stats: {stats['yearly_stats']}")
        
        # 월별 통계 - 모든 문서 처리
        monthly_data = {}
        
        # 월 범위가 지정된 경우 해당 월들을 미리 초기화
        if conditions['start_month'] and conditions['end_month']:
            for month_num in range(conditions['start_month'], conditions['end_month'] + 1):
                month_key = f"{month_num}월"
                monthly_data[month_key] = 0
            print(f"DEBUG: Initialized months {conditions['start_month']}~{conditions['end_month']}")
        
        # 각 문서에 대해 월별 통계 계산
        print("DEBUG: Processing each document for monthly stats:")
        for i, doc in enumerate(documents):
            incident_id = doc.get('incident_id', 'N/A')
            month = self._extract_month_from_document(doc)
            
            print(f"DEBUG: Monthly Doc {i+1}: ID={incident_id}, Extracted_Month={month}")
            
            if month:
                try:
                    month_num = int(month)
                    if 1 <= month_num <= 12:
                        month_key = f"{month_num}월"
                        
                        if is_error_time_query:
                            error_time = doc.get('error_time', 0)
                            monthly_data[month_key] = monthly_data.get(month_key, 0) + error_time
                            print(f"DEBUG: Added {error_time} minutes to {month_key}, total now: {monthly_data[month_key]}")
                        else:
                            monthly_data[month_key] = monthly_data.get(month_key, 0) + 1
                            print(f"DEBUG: Added 1 count to {month_key}, total now: {monthly_data[month_key]}")
                except (ValueError, TypeError):
                    print(f"DEBUG: Invalid month format for document {incident_id}: {month}")
                    continue
            else:
                print(f"DEBUG: No month extracted for document {incident_id}")
        
        # 월 순서대로 정렬하여 stats에 저장
        month_order = [f"{i}월" for i in range(1, 13)]
        for month in month_order:
            if month in monthly_data:
                stats['monthly_stats'][month] = monthly_data[month]
        
        print(f"DEBUG: Final monthly stats: {stats['monthly_stats']}")
        
        # 시간대별 통계 - 모든 문서 처리
        print("DEBUG: Processing each document for time stats:")
        for i, doc in enumerate(documents):
            incident_id = doc.get('incident_id', 'N/A')
            daynight = doc.get('daynight', '')
            week = doc.get('week', '')
            
            print(f"DEBUG: Time Doc {i+1}: ID={incident_id}, daynight={daynight}, week={week}")
            
            if daynight:
                if is_error_time_query:
                    error_time = doc.get('error_time', 0)
                    stats['time_stats']['daynight'][daynight] = stats['time_stats']['daynight'].get(daynight, 0) + error_time
                else:
                    stats['time_stats']['daynight'][daynight] = stats['time_stats']['daynight'].get(daynight, 0) + 1
            
            if week:
                if is_error_time_query:
                    error_time = doc.get('error_time', 0)
                    stats['time_stats']['week'][week] = stats['time_stats']['week'].get(week, 0) + error_time
                else:
                    stats['time_stats']['week'][week] = stats['time_stats']['week'].get(week, 0) + 1
        
        # 부서별 통계 - 모든 문서 처리
        print("DEBUG: Processing each document for department stats:")
        for i, doc in enumerate(documents):
            incident_id = doc.get('incident_id', 'N/A')
            department = doc.get('owner_depart', '')
            
            print(f"DEBUG: Dept Doc {i+1}: ID={incident_id}, department={department}")
            
            if department:
                if is_error_time_query:
                    error_time = doc.get('error_time', 0)
                    stats['department_stats'][department] = stats['department_stats'].get(department, 0) + error_time
                    print(f"DEBUG: Added {error_time} minutes to department {department}")
                else:
                    stats['department_stats'][department] = stats['department_stats'].get(department, 0) + 1
                    print(f"DEBUG: Added 1 count to department {department}")
        
        # 서비스별 통계 - 모든 문서 처리
        print("DEBUG: Processing each document for service stats:")
        for i, doc in enumerate(documents):
            incident_id = doc.get('incident_id', 'N/A')
            service = doc.get('service_name', '')
            
            print(f"DEBUG: Service Doc {i+1}: ID={incident_id}, service={service}")
            
            if service:
                if is_error_time_query:
                    error_time = doc.get('error_time', 0)
                    stats['service_stats'][service] = stats['service_stats'].get(service, 0) + error_time
                    print(f"DEBUG: Added {error_time} minutes to service {service}")
                else:
                    stats['service_stats'][service] = stats['service_stats'].get(service, 0) + 1
                    print(f"DEBUG: Added 1 count to service {service}")
        
        # 등급별 통계 - 모든 문서 처리
        print("DEBUG: Processing each document for grade stats:")
        for i, doc in enumerate(documents):
            incident_id = doc.get('incident_id', 'N/A')
            grade = doc.get('incident_grade', '')
            
            print(f"DEBUG: Grade Doc {i+1}: ID={incident_id}, grade={grade}")
            
            if grade:
                if is_error_time_query:
                    error_time = doc.get('error_time', 0)
                    stats['grade_stats'][grade] = stats['grade_stats'].get(grade, 0) + error_time
                    print(f"DEBUG: Added {error_time} minutes to grade {grade}")
                else:
                    stats['grade_stats'][grade] = stats['grade_stats'].get(grade, 0) + 1
                    print(f"DEBUG: Added 1 count to grade {grade}")
        
        # 최종 통계 요약 출력
        print("DEBUG: === FINAL STATISTICS SUMMARY ===")
        print(f"DEBUG: Total documents processed: {len(documents)}")
        print(f"DEBUG: Yearly stats: {stats['yearly_stats']}")
        print(f"DEBUG: Monthly stats: {stats['monthly_stats']}")
        print(f"DEBUG: Service stats: {stats['service_stats']}")
        print(f"DEBUG: Grade stats: {stats['grade_stats']}")
        print(f"DEBUG: Department stats: {stats['department_stats']}")
        print(f"DEBUG: Time stats: {stats['time_stats']}")
        print("DEBUG: ===================================")
        
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
        
        return stats
    
    def calculate_comprehensive_statistics(self, documents, query, query_type="default"):
        """종합적인 통계 계산 - 중복 제거 옵션 적용 및 필터링 최소화"""
        if not documents:
            return self._empty_statistics()
        
        print(f"DEBUG: ============ STATISTICS CALCULATION START ============")
        print(f"DEBUG: Query: '{query}'")
        print(f"DEBUG: Input documents: {len(documents)}")
        print(f"DEBUG: Remove duplicates option: {self.remove_duplicates}")
        
        # 입력 문서 상태 확인
        for i, doc in enumerate(documents[:3]):  # 처음 3개만 로그
            incident_id = doc.get('incident_id', 'N/A')
            error_date = doc.get('error_date', 'N/A')
            year = doc.get('year', 'N/A')
            month = doc.get('month', 'N/A')
            print(f"DEBUG: Input doc {i+1}: ID={incident_id}, error_date={error_date}, year={year}, month={month}")
        
        # 문서 정규화 및 검증
        normalized_docs = []
        validation_errors = []
        validation_warnings = []
        
        for i, doc in enumerate(documents):
            if doc is None:
                continue
            
            errors, warnings = self.validator.validate_document(doc, i)
            validation_errors.extend(errors)
            validation_warnings.extend(warnings)
            
            normalized_doc = self.normalizer.normalize_document(doc)
            normalized_docs.append(normalized_doc)
        
        print(f"DEBUG: After normalization: {len(normalized_docs)} documents")
        
        # 정규화 후 상태 확인
        for i, doc in enumerate(normalized_docs[:3]):
            incident_id = doc.get('incident_id', 'N/A')
            error_date = doc.get('error_date', 'N/A')
            year = doc.get('year', 'N/A')
            month = doc.get('month', 'N/A')
            extracted_year = doc.get('extracted_year', 'N/A')
            extracted_month = doc.get('extracted_month', 'N/A')
            print(f"DEBUG: Normalized doc {i+1}: ID={incident_id}, error_date={error_date}, year={year}, month={month}, extracted_year={extracted_year}, extracted_month={extracted_month}")

        # 중복 제거 (옵션에 따라)
        if self.remove_duplicates:
            print("DEBUG: Applying duplicate removal")
            unique_docs = {}
            for doc in normalized_docs:
                incident_id = doc.get('incident_id', '')
                if incident_id and incident_id not in unique_docs:
                    unique_docs[incident_id] = doc
                elif not incident_id:
                    temp_id = f"temp_{len(unique_docs)}"
                    unique_docs[temp_id] = doc
            
            clean_documents = list(unique_docs.values())
            print(f"DEBUG: After deduplication: {len(clean_documents)} unique documents")
        else:
            print("DEBUG: Skipping duplicate removal - keeping all documents")
            clean_documents = normalized_docs
            print(f"DEBUG: Keeping all documents: {len(clean_documents)} documents")
        
        # 필터 조건 추출
        filter_conditions = self._extract_filter_conditions(query)
        print(f"DEBUG: Extracted filter conditions: {filter_conditions}")
        
        # 통계성 질문의 경우 필터링 최소화 - 서비스명 필터링도 비활성화
        is_stats_query = any(keyword in query.lower() for keyword in ['건수', '통계', '연도별', '월별', '현황', '분포', '알려줘', '몇건', '개수'])
        
        if is_stats_query:
            print("DEBUG: Statistics query detected - skipping ALL filtering to preserve all documents")
            print(f"DEBUG: Original filter conditions ignored: {filter_conditions}")
            # 통계성 질문에서는 모든 필터링 비활성화
            filtered_docs = clean_documents
        else:
            # 일반 질문에서만 문서 필터링 적용
            filtered_docs = self._apply_filters(clean_documents, filter_conditions)
            print(f"DEBUG: After filtering: {len(filtered_docs)} documents")
        
        # 최종 필터링된 문서들 확인
        print(f"DEBUG: ========== FINAL FILTERED DOCUMENTS ==========")
        for i, doc in enumerate(filtered_docs):
            incident_id = doc.get('incident_id', 'N/A')
            error_date = doc.get('error_date', 'N/A')
            year = doc.get('year', 'N/A')
            month = doc.get('month', 'N/A')
            print(f"DEBUG: Final doc {i+1}: ID={incident_id}, error_date={error_date}, year={year}, month={month}")

        # 장애시간 쿼리 여부 확인
        is_error_time_query = self._is_error_time_query(query)
        
        # 통계 계산
        stats = self._calculate_detailed_statistics(filtered_docs, filter_conditions, is_error_time_query)
        
        # 결과 검증
        result_errors, result_warnings = self.validator.validate_statistics_result(stats, len(filtered_docs))
        validation_errors.extend(result_errors)
        validation_warnings.extend(result_warnings)
        
        stats['validation'] = {
            'errors': validation_errors,
            'warnings': validation_warnings,
            'is_valid': len(validation_errors) == 0
        }
        
        print(f"DEBUG: ============ STATISTICS CALCULATION END ============")
        print(f"DEBUG: Final statistics: {stats}")
        
        return stats

class QueryProcessorLocal:
    """개선된 쿼리 처리 관리 클래스 + 모니터링 기능 추가"""
    
    def __init__(self, azure_openai_client, search_client, model_name, config=None):
        self.azure_openai_client = azure_openai_client
        self.search_client = search_client
        self.model_name = model_name
        self.config = config if config else AppConfigLocal()
        self.search_manager = SearchManagerLocal(search_client, self.config)
        self.ui_components = UIComponentsLocal()
        self.reprompting_db_manager = RepromptingDBManager()
        self.chart_manager = ChartManager()
        # 중복 제거 비활성화로 변경
        self.statistics_calculator = ImprovedStatisticsCalculator(remove_duplicates=False)
        self.debug_mode = True  # 디버깅 모드 활성화
        
        # 모니터링 매니저 초기화 추가
        if MONITORING_AVAILABLE:
            try:
                self.monitoring_manager = MonitoringManager()
                self.monitoring_enabled = True
                print("DEBUG: MonitoringManager initialized successfully")
            except Exception as e:
                print(f"DEBUG: Failed to initialize MonitoringManager: {e}")
                self.monitoring_manager = MonitoringManager()  # 더미 인스턴스
                self.monitoring_enabled = False
        else:
            self.monitoring_manager = MonitoringManager()  # 더미 인스턴스
            self.monitoring_enabled = False
            print("DEBUG: MonitoringManager not available, using dummy instance")
        
        self.langsmith_enabled = LANGSMITH_ENABLED
        self._setup_langsmith()
    
    def _get_client_ip(self):
        """클라이언트 IP 주소 가져오기"""
        try:
            # Streamlit에서 IP 주소 가져오기
            if hasattr(st, 'session_state') and hasattr(st.session_state, 'client_ip'):
                return st.session_state.client_ip
            
            # 헤더에서 IP 가져오기 시도
            headers = st.context.headers if hasattr(st, 'context') and hasattr(st.context, 'headers') else {}
            
            # 다양한 헤더에서 IP 추출 시도
            ip_headers = [
                'X-Forwarded-For',
                'X-Real-IP', 
                'X-Client-IP',
                'CF-Connecting-IP',  # Cloudflare
                'True-Client-IP'
            ]
            
            for header in ip_headers:
                if header in headers:
                    ip = headers[header].split(',')[0].strip()
                    if ip and ip != '127.0.0.1':
                        return ip
            
            # 기본값 반환
            return '127.0.0.1'
            
        except Exception as e:
            print(f"DEBUG: Error getting client IP: {e}")
            return '127.0.0.1'
    
    def _get_user_agent(self):
        """사용자 에이전트 가져오기"""
        try:
            if hasattr(st, 'context') and hasattr(st.context, 'headers'):
                return st.context.headers.get('User-Agent', 'Unknown')
            return 'Streamlit-App'
        except Exception as e:
            print(f"DEBUG: Error getting user agent: {e}")
            return 'Unknown'
    
    def _log_user_activity(self, question, query_type=None, response_time=None, 
                          document_count=None, success=True, error_message=None):
        """사용자 활동 로깅"""
        if not self.monitoring_enabled:
            return
            
        try:
            ip_address = self._get_client_ip()
            user_agent = self._get_user_agent()
            
            self.monitoring_manager.log_user_activity(
                ip_address=ip_address,
                question=question,
                query_type=query_type,
                user_agent=user_agent,
                response_time=response_time,
                document_count=document_count,
                success=success,
                error_message=error_message
            )
            
            if self.debug_mode:
                print(f"DEBUG: Logged user activity - IP: {ip_address}, Query: {question[:50]}...")
                
        except Exception as e:
            print(f"DEBUG: Error logging user activity: {e}")
    
    def safe_trace_update(self, trace_obj, **kwargs):
        """LangSmith trace 객체의 안전한 업데이트"""
        if not self.langsmith_enabled:
            return
            
        try:
            if hasattr(trace_obj, 'update'):
                trace_obj.update(**kwargs)
            elif hasattr(trace_obj, 'add_outputs'):
                if 'outputs' in kwargs:
                    trace_obj.add_outputs(kwargs['outputs'])
                if 'metadata' in kwargs:
                    trace_obj.add_metadata(kwargs['metadata'])
        except Exception as e:
            pass
    
    def _setup_langsmith(self):
        if not self.langsmith_enabled:
            return
            
        try:
            langsmith_status = self.config.get_langsmith_status()
            if langsmith_status['enabled'] and LANGSMITH_AVAILABLE:
                success = self.config.setup_langsmith()
                if success:
                    self.azure_openai_client = wrap_openai(self.azure_openai_client)
        except Exception as e:
            pass

    def calculate_unified_statistics(self, documents, query, query_type="default"):
        """개선된 통합 통계 계산"""
        if not documents:
            return self.statistics_calculator._empty_statistics()
        
        print(f"DEBUG: Using improved statistics calculator (no duplicates removal) for {len(documents)} documents")
        return self.statistics_calculator.calculate_comprehensive_statistics(documents, query, query_type)

    def extract_service_name_from_query_enhanced(self, query):
        """향상된 서비스명 추출"""
        if not query:
            return None
        
        service_patterns = [
            r'([A-Za-z][A-Za-z0-9_\-/\+\(\)\s]*[A-Za-z0-9_\-/\+\)])\s+(?:장애|현상|복구|서비스|오류|문제|불가)',
            r'서비스.*?([A-Za-z][A-Za-z0-9_\-/\+\(\)\s]*[A-Za-z0-9_\-/\+\)])',
            r'^([A-Za-z][A-Za-z0-9_\-/\+\(\)\s]*[A-Za-z0-9_\-/\+\)])\s+',
            r'["\']([A-Za-z][A-Za-z0-9_\-/\+\(\)\s]*[A-Za-z0-9_\-/\+\)])["\']',
            r'\(([A-Za-z][A-Za-z0-9_\-/\+\s]*[A-Za-z0-9_\-/\+])\)',
            r'\b([A-Za-z][A-Za-z0-9_\-/\+\(\)]{2,}(?:\s+[A-Za-z0-9_\-/\+\(\)]+)*)\b',
            r'([가-힣]{2,10})\s+(?:서비스|시스템|장애|현상|복구|오류|문제|불가)',
            r'서비스.*?([가-힣]{2,10})',
            r'^([가-힣]{2,10})\s+',
            r'([A-Za-z]+[가-힣]+|[가-힣]+[A-Za-z]+)(?:\s+(?:서비스|시스템|장애|현상|복구|오류|문제|불가))?',
        ]
        
        for pattern in service_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            for match in matches:
                service_name = match.strip()
                if self.is_valid_service_name_enhanced(service_name):
                    return service_name
        
        return None
    
    def is_valid_service_name_enhanced(self, service_name):
        """향상된 서비스명 유효성 검증"""
        if len(service_name) < 2:
            return False
        
        if not (service_name[0].isalpha() or ord('가') <= ord(service_name[0]) <= ord('힣')):
            return False
        
        excluded_words = [
            'service', 'system', 'server', 'client', 'application', 'app',
            'website', 'web', 'platform', 'portal', 'interface', 'api',
            'database', 'data', 'file', 'log', 'error', 'issue', 'problem',
            'http', 'https', 'www', 'com', 'org', 'net',
            '장애', '현상', '복구', '통계', '발생', '서비스', '시스템'
        ]
        
        clean_name = re.sub(r'[\(\)/\+_\-\s]', '', service_name).lower()
        if clean_name in excluded_words:
            return False
        
        return True

    def extract_keywords_from_query_enhanced(self, query):
        """향상된 키워드 추출"""
        tech_keywords = []
        
        tech_patterns = [
            r'\b(로그인|login)\b',
            r'\b(카카오|kakao|naver|네이버|google|구글)\b',
            r'\b(접속|연결|connection)\b',
            r'\b(인증|auth|authentication)\b',
            r'\b(API|api)\b',
            r'\b(데이터베이스|database|DB|db)\b',
            r'\b(서버|server)\b',
            r'\b(네트워크|network)\b',
            r'\b(메모리|memory)\b',
            r'\b(CPU|cpu)\b',
            r'\b(디스크|disk)\b',
            r'\b(보안|security)\b',
            r'\b(불가|실패|error|fail)\b',
            r'\b(느림|지연|slow|delay)\b',
            r'\b(중단|stop|halt)\b'
        ]
        
        for pattern in tech_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            tech_keywords.extend(matches)
        
        return list(set(tech_keywords))

    def build_enhanced_search_query_with_flexible_matching(self, user_query, service_name=None, keywords=None):
        """서비스명 유연 매칭을 위한 향상된 검색 쿼리 구성"""
        search_terms = []
        
        search_terms.append(user_query)
        
        if service_name:
            search_terms.append(service_name)
            
            for keyword in (keywords or []):
                search_terms.append(f"{service_name} {keyword}")
        
        if keywords:
            search_terms.extend(keywords)
        
        unique_terms = list(set(search_terms))
        search_query = " OR ".join(f'"{term}"' for term in unique_terms[:10])
        
        return search_query

    def perform_enhanced_search_with_flexible_service_matching(self, user_query, query_type="default"):
        """서비스명 유연 매칭이 적용된 향상된 검색 수행"""
        try:
            service_name = self.extract_service_name_from_query_enhanced(user_query)
            keywords = self.extract_keywords_from_query_enhanced(user_query)
            
            if self.debug_mode:
                st.info(f"🔍 DEBUG: 향상된 서비스명='{service_name}', 키워드={keywords}")
            
            thresholds = self.config.get_dynamic_thresholds(query_type, user_query)
            enhanced_query = self.build_enhanced_search_query_with_flexible_matching(user_query, service_name, keywords)
            
            if self.debug_mode:
                st.info(f"🔍 DEBUG: 향상된 검색 쿼리='{enhanced_query}'")
            
            search_results = self.search_client.search(
                search_text=enhanced_query,
                top=thresholds.get('max_results', 30),
                include_total_count=True,
                search_mode='any',
                query_type='semantic',
                semantic_configuration_name='default',
                search_fields=['incident_id', 'service_name', 'symptom', 'effect', 'root_cause', 'incident_repair'],
                select=['incident_id', 'service_name', 'symptom', 'effect', 'root_cause', 'incident_repair', 'incident_plan', 'error_date', 'error_time', 'incident_grade', 'owner_depart', 'daynight', 'week']
            )
            
            filtered_results = []
            search_threshold = max(0.10, thresholds.get('search_threshold', 0.15) - 0.05)
            
            for result in search_results:
                score = getattr(result, '@search.score', 0)
                
                service_bonus = 0
                if service_name and hasattr(result, 'service_name'):
                    result_service = result.service_name or ''
                    
                    if service_name.upper() in result_service.upper():
                        service_bonus = 0.15
                    elif any(keyword.upper() in (getattr(result, field, '') or '').upper() 
                           for field in ['symptom', 'effect', 'root_cause'] 
                           for keyword in ([service_name] + keywords)):
                        service_bonus = 0.08
                    elif keywords and any(keyword.upper() in (getattr(result, field, '') or '').upper()
                                        for field in ['service_name', 'symptom', 'effect', 'root_cause', 'incident_repair']
                                        for keyword in keywords):
                        service_bonus = 0.05
                
                final_score = score + service_bonus
                
                if final_score >= search_threshold:
                    result_dict = {
                        'incident_id': getattr(result, 'incident_id', ''),
                        'service_name': getattr(result, 'service_name', ''),
                        'symptom': getattr(result, 'symptom', ''),
                        'effect': getattr(result, 'effect', ''),
                        'root_cause': getattr(result, 'root_cause', ''),
                        'incident_repair': getattr(result, 'incident_repair', ''),
                        'incident_plan': getattr(result, 'incident_plan', ''),
                        'error_date': getattr(result, 'error_date', ''),
                        'error_time': getattr(result, 'error_time', ''),
                        'incident_grade': getattr(result, 'incident_grade', ''),
                        'owner_depart': getattr(result, 'owner_depart', ''),
                        'daynight': getattr(result, 'daynight', ''),
                        'week': getattr(result, 'week', ''),
                        'search_score': final_score,
                        'original_score': score,
                        'service_bonus': service_bonus,
                        'service_match_type': 'exact' if service_bonus >= 0.15 else 'partial' if service_bonus >= 0.05 else 'keyword'
                    }
                    filtered_results.append(result_dict)
            
            filtered_results.sort(key=lambda x: x['search_score'], reverse=True)
            
            if self.debug_mode:
                st.info(f"🔍 DEBUG: 유연 매칭 검색 결과 {len(filtered_results)}건 (임계값: {search_threshold})")
                if filtered_results:
                    st.write("상위 5개 결과:")
                    for i, result in enumerate(filtered_results[:5], 1):
                        st.write(f"{i}. {result['service_name']} - 점수: {result['search_score']:.3f} (보너스: +{result['service_bonus']:.3f})")
            
            return filtered_results
            
        except Exception as e:
            if self.debug_mode:
                st.error(f"🔍 DEBUG: 유연 매칭 검색 중 오류: {str(e)}")
            else:
                st.error("검색 중 오류가 발생했습니다.")
            return []

    @traceable(name="check_reprompting_question")
    def check_and_transform_query_with_reprompting(self, user_query):
        """사용자 질문을 Reprompting DB에서 확인하고 필요시 변환"""
        if not user_query:
            return {
                'transformed': False,
                'original_query': user_query,
                'transformed_query': user_query,
                'match_type': 'none'
            }
            
        start_time = time.time()
        
        with trace(name="reprompting_check", inputs={"user_query": user_query}) as trace_context:
            try:
                with trace(name="exact_match_check", inputs={"query": user_query}) as exact_trace:
                    exact_result = self.reprompting_db_manager.check_reprompting_question(user_query)
                    self.safe_trace_update(exact_trace, outputs={"exact_match_found": exact_result['exists']})
                
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
                    
                    self.safe_trace_update(trace_context,
                        outputs=result,
                        metadata={
                            "match_type": "exact",
                            "processing_time": time.time() - start_time,
                            "question_type": exact_result['question_type']
                        }
                    )
                    return result
                
                with trace(name="similar_match_search", inputs={"query": user_query, "threshold": 0.7}) as similar_trace:
                    similar_questions = self.reprompting_db_manager.find_similar_questions(
                        user_query, 
                        similarity_threshold=0.7,
                        limit=3
                    )
                    self.safe_trace_update(similar_trace, outputs={"similar_questions_count": len(similar_questions)})
                
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
                        st.info(f"📋 유사 질문 패턴을 감지하여 질문을 최적화했습니다. (유사도: {best_match['similarity']:.1%})")

                    self.safe_trace_update(trace_context,
                        outputs=result,
                        metadata={
                            "match_type": "similar",
                            "similarity_score": best_match['similarity'],
                            "processing_time": time.time() - start_time,
                            "question_type": best_match['question_type']
                        }
                    )
                    return result
                
                result = {
                    'transformed': False,
                    'original_query': user_query,
                    'transformed_query': user_query,
                    'match_type': 'none'
                }
                
                self.safe_trace_update(trace_context,
                    outputs=result,
                    metadata={
                        "match_type": "none",
                        "processing_time": time.time() - start_time
                    }
                )
                return result
                
            except Exception as e:
                result = {
                    'transformed': False,
                    'original_query': user_query,
                    'transformed_query': user_query,
                    'match_type': 'error',
                    'error': str(e)
                }
                
                self.safe_trace_update(trace_context,
                    outputs=result,
                    metadata={
                        "match_type": "error",
                        "error": str(e),
                        "processing_time": time.time() - start_time
                    }
                )
                return result
    
    def extract_time_conditions(self, query):
        """쿼리에서 시간대/요일 조건 추출"""
        if not query:
            return {
                'daynight': None,
                'week': None,
                'is_time_query': False
            }
            
        time_conditions = {
            'daynight': None,
            'week': None,
            'is_time_query': False
        }
        
        daynight_patterns = [
            r'\b(야간|밤|새벽|심야|야시간)\b',
            r'\b(주간|낮|오전|오후|주시간|일과시간)\b'
        ]
        
        for pattern in daynight_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                time_conditions['is_time_query'] = True
                for match in matches:
                    if match in ['야간', '밤', '새벽', '심야', '야시간']:
                        time_conditions['daynight'] = '야간'
                    elif match in ['주간', '낮', '오전', '오후', '주시간', '일과시간']:
                        time_conditions['daynight'] = '주간'
        
        week_patterns = [
            r'\b(월요일|월)\b',
            r'\b(화요일|화)\b', 
            r'\b(수요일|수)\b',
            r'\b(목요일|목)\b',
            r'\b(금요일|금)\b',
            r'\b(토요일|토)\b',
            r'\b(일요일|일)\b',
            r'\b(평일|주중)\b',
            r'\b(주말|토일)\b'
        ]
        
        for pattern in week_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                time_conditions['is_time_query'] = True
                for match in matches:
                    if match in ['월요일', '월']:
                        time_conditions['week'] = '월'
                    elif match in ['화요일', '화']:
                        time_conditions['week'] = '화'
                    elif match in ['수요일', '수']:
                        time_conditions['week'] = '수'
                    elif match in ['목요일', '목']:
                        time_conditions['week'] = '목'
                    elif match in ['금요일', '금']:
                        time_conditions['week'] = '금'
                    elif match in ['토요일', '토']:
                        time_conditions['week'] = '토'
                    elif match in ['일요일', '일']:
                        time_conditions['week'] = '일'
                    elif match in ['평일', '주중']:
                        time_conditions['week'] = '평일'
                    elif match in ['주말', '토일']:
                        time_conditions['week'] = '주말'
        
        return time_conditions
    
    def extract_department_conditions(self, query):
        """쿼리에서 부서 관련 조건 추출"""
        if not query:
            return {
                'owner_depart': None,
                'is_department_query': False
            }
            
        department_conditions = {
            'owner_depart': None,
            'is_department_query': False
        }
        
        department_keywords = [
            '담당부서', '조치부서', '처리부서', '책임부서', '관리부서',
            '부서', '팀', '조직', '담당', '처리', '조치', '관리'
        ]
        
        if any(keyword in query for keyword in department_keywords):
            department_conditions['is_department_query'] = True
        
        department_patterns = [
            r'\b(개발|운영|기술|시스템|네트워크|보안|DB|데이터베이스|인프라|클라우드)(?:부서|팀|파트)?\b',
            r'\b(고객|서비스|상담|지원|헬프데스크)(?:부서|팀|파트)?\b',
            r'\b(IT|정보시스템|정보기술|전산)(?:부서|팀|파트)?\b',
            r'\b([가-힣]+)(?:부서|팀|파트)\b'
        ]
        
        for pattern in department_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                department_conditions['owner_depart'] = matches[0]
                break
        
        return department_conditions
    
    @traceable(name="classify_query_type")
    def classify_query_type_with_llm(self, query):
        """LLM을 사용하여 쿼리 타입을 자동으로 분류 - statistics 타입 추가"""
        if not query:
            return 'default'
            
        with trace(name="llm_query_classification", inputs={"query": query, "model": self.model_name}) as trace_context:
            try:
                classification_prompt = f"""
다음 사용자 질문을 분석하여 적절한 카테고리를 선택해주세요.

**분류 기준:**
1. **repair**: 서비스명과 장애현상이 모두 포함된 복구방법 문의
   - 예: "ERP 접속불가 복구방법", "API_Link 응답지연 해결방법"
   
2. **cause**: 장애원인 분석이나 원인 파악을 요청하는 문의
   - 예: "ERP 접속불가 원인이 뭐야?", "API 응답지연 장애원인", "왜 장애가 발생했어?"
   
3. **similar**: 서비스명 없이 장애현상만으로 유사사례 문의
   - 예: "접속불가 현상 유사사례", "응답지연 동일현상 복구방법"
   
4. **inquiry**: 특정 조건(시간대, 요일, 년도, 월, 서비스, 부서, 등급 등)에 대한 장애 내역 조회
   - 예: "2025년 야간에 발생한 장애 알려줘", "2020년 토요일에 발생한 장애 알려줘"
   - 예: "2025년 주말에 발생한 장애가 뭐야?", "월요일에 발생한 ERP 장애 내역"
   - 특징: 시간/조건 + "발생한" + "장애" + ("알려줘"/"내역"/"뭐야"/"목록"/"어떤게" 등)
   
5. **statistics**: 통계 전용 질문 (건수, 통계, 현황, 분포, 월별/연도별 집계 등)
   - 예: "2025년 1~6월 장애 건수", "연도별 장애 통계", "서비스별 장애 현황"
   - 예: "월별 장애 분포", "부서별 장애 건수", "등급별 장애 통계"
   - 예: "2025년 장애시간 통계", "원인유형별 월별 현황"
   - 특징: "건수", "통계", "현황", "분포", "월별", "연도별", "몇건", "개수" 등의 키워드 포함
   
6. **default**: 그 외의 모든 경우 (일반적인 통계, 건수, 현황 문의, 단순한 장애등급 조회 등)
   - 예: "년도별 건수", "장애 통계", "서비스 현황", "장애등급 몇건", "ERP 장애가 몇건"

**중요 구분 포인트:**
- **inquiry vs statistics**: 
  - inquiry: 특정 조건의 "장애 내역/목록" 요청 ("2025년 야간에 발생한 장애 알려줘")
  - statistics: "건수/통계/현황" 집계 요청 ("2025년 야간 장애가 몇건?")
- **statistics vs default**:
  - statistics: 명확한 통계 집계 의도가 있는 질문 (월별, 연도별, 서비스별 등의 그룹화된 통계)
  - default: 단순 건수 질문이나 일반적인 현황 질문

**사용자 질문:** {query}

**응답 형식:** repair, cause, similar, inquiry, statistics, default 중 하나만 출력하세요.
"""

                response = self.azure_openai_client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "당신은 IT 질문을 분류하는 전문가입니다. 주어진 질문을 정확히 분석하여 적절한 카테고리를 선택해주세요."},
                        {"role": "user", "content": classification_prompt}
                    ],
                    temperature=0.1,
                    max_tokens=50
                )
                
                query_type = response.choices[0].message.content.strip().lower()
                
                # statistics 타입 유효성 검증
                if query_type not in ['repair', 'cause', 'similar', 'inquiry', 'statistics', 'default']:
                    query_type = 'default'
                
                self.safe_trace_update(trace_context,
                    outputs={"query_type": query_type},
                    metadata={
                        "model_used": self.model_name,
                        "temperature": 0.1,
                        "max_tokens": 50
                    }
                )
                
                return query_type
                
            except Exception as e:
                self.safe_trace_update(trace_context,
                    outputs={"query_type": "default"},
                    metadata={"error": str(e), "fallback_used": True}
                )
                return 'default'

    @traceable(name="validate_document_relevance")
    def validate_document_relevance_with_llm(self, query, documents):
        """LLM을 사용하여 검색 결과의 관련성을 재검증"""
        if not query or not documents:
            return []
            
        with trace(name="llm_document_validation", inputs={"query": query, "document_count": len(documents)}) as trace_context:
            try:
                if not documents:
                    self.safe_trace_update(trace_context, outputs={"validated_documents": []})
                    return []
                
                validation_prompt = f"""
사용자 질문: "{query}"

다음 검색된 문서들 중에서 사용자 질문과 실제로 관련성이 높은 문서만 선별해주세요.
각 문서에 대해 0-100점 사이의 관련성 점수를 매기고, 70점 이상인 문서만 선택하세요.

평가 기준:
1. 서비스명 일치도 (사용자가 특정 서비스를 언급한 경우)
2. 장애현상/증상 일치도  
3. 사용자가 요구한 정보 유형과의 일치도
4. 전체적인 맥락 일치도

"""

                for i, doc in enumerate(documents):
                    if doc is None:
                        continue
                    doc_info = f"""
문서 {i+1}:
- 서비스명: {doc.get('service_name', '')}
- 장애현상: {doc.get('symptom', '')}
- 영향도: {doc.get('effect', '')}
- 장애원인: {doc.get('root_cause', '')[:100]}...
- 복구방법: {doc.get('incident_repair', '')[:100]}...
"""
                    validation_prompt += doc_info

                validation_prompt += """

응답 형식 (JSON):
{
    "validated_documents": [
        {
            "document_index": 1,
            "relevance_score": 85,
            "reason": "서비스명과 장애현상이 정확히 일치함"
        },
        {
            "document_index": 3,
            "relevance_score": 72,
            "reason": "장애현상은 유사하지만 서비스명이 다름"
        }
    ]
}

70점 이상인 문서만 포함하세요.
"""

                response = self.azure_openai_client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "당신은 문서 관련성 평가 전문가입니다. 사용자 질문과 문서의 관련성을 정확하게 평가해주세요."},
                        {"role": "user", "content": validation_prompt}
                    ],
                    temperature=0.1,
                    max_tokens=800
                )
                
                response_content = response.choices[0].message.content.strip()
                
                try:
                    import json
                    json_start = response_content.find('{')
                    json_end = response_content.rfind('}') + 1
                    if json_start >= 0 and json_end > json_start:
                        json_content = response_content[json_start:json_end]
                        validation_result = json.loads(json_content)
                        
                        validated_docs = []
                        for validated_doc in validation_result.get('validated_documents', []):
                            doc_index = validated_doc.get('document_index', 1) - 1
                            if 0 <= doc_index < len(documents):
                                original_doc = documents[doc_index].copy()
                                original_doc['relevance_score'] = validated_doc.get('relevance_score', 0)
                                original_doc['validation_reason'] = validated_doc.get('reason', '검증됨')
                                validated_docs.append(original_doc)
                        
                        validated_docs.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
                        
                        self.safe_trace_update(trace_context,
                            outputs={
                                "validated_count": len(validated_docs),
                                "original_count": len(documents),
                                "filtered_out": len(documents) - len(validated_docs)
                            },
                            metadata={
                                "validation_threshold": 70,
                                "model_used": self.model_name
                            }
                        )
                        
                        return validated_docs
                        
                except (json.JSONDecodeError, KeyError) as e:
                    self.safe_trace_update(trace_context,
                        outputs={"validated_count": min(5, len(documents))},
                        metadata={"parsing_error": str(e), "fallback_used": True}
                    )
                    return documents[:5]
                    
            except Exception as e:
                self.safe_trace_update(trace_context,
                    outputs={"validated_count": min(5, len(documents))},
                    metadata={"validation_error": str(e), "fallback_used": True}
                )
                return documents[:5]
            
            return documents

    def validate_service_specific_documents(self, documents, target_service_name):
        """지정된 서비스명에 해당하는 문서만 필터링"""
        if not target_service_name or not documents:
            return documents
        
        is_common, _ = self.search_manager.is_common_term_service(target_service_name)
        
        validated_docs = []
        filter_stats = {
            'total': len(documents),
            'exact_matches': 0,
            'partial_matches': 0,
            'excluded': 0
        }
        
        for doc in documents:
            if doc is None:
                continue
                
            doc_service_name = doc.get('service_name', '').strip()
            
            if is_common:
                if doc_service_name.lower() == target_service_name.lower():
                    filter_stats['exact_matches'] += 1
                    validated_docs.append(doc)
                else:
                    filter_stats['excluded'] += 1
            else:
                if doc_service_name.lower() == target_service_name.lower():
                    filter_stats['exact_matches'] += 1
                    validated_docs.append(doc)
                elif target_service_name.lower() in doc_service_name.lower() or doc_service_name.lower() in target_service_name.lower():
                    filter_stats['partial_matches'] += 1
                    validated_docs.append(doc)
                else:
                    filter_stats['excluded'] += 1
        
        return validated_docs

    def _generate_chart_title(self, query, chart_type):
        """차트 제목 생성"""
        title_map = {
            'yearly': '연도별 장애 발생 현황',
            'monthly': '월별 장애 발생 현황',
            'time_period': '시간대별 장애 발생 분포',
            'weekday': '요일별 장애 발생 분포',
            'department': '부서별 장애 처리 현황',
            'service': '서비스별 장애 발생 현황',
            'grade': '장애등급별 발생 비율',
            'cause_type': '장애원인 유형별 분포',
            'general': '장애 발생 통계'
        }
        
        base_title = title_map.get(chart_type, '장애 통계')
        
        import re
        year_match = re.search(r'\b(202[0-9]|201[0-9])\b', query)
        if year_match:
            year = year_match.group(1)
            base_title = f"{year}년 {base_title}"
        
        if query:
            error_time_keywords = ['장애시간', '장애 시간', 'error_time', '시간 통계', '시간 합계', '시간 합산']
            is_error_time_query = any(keyword in query.lower() for keyword in error_time_keywords)
            if is_error_time_query:
                base_title = base_title.replace('발생', '시간')
        
        if '야간' in query:
            base_title += ' (야간)'
        elif '주간' in query:
            base_title += ' (주간)'
        
        if any(day in query for day in ['월요일', '화요일', '수요일', '목요일', '금요일']):
            base_title += ' (평일)'
        elif '주말' in query:
            base_title += ' (주말)'
            
        return base_title

    def detect_statistics_type(self, query):
        """질문에서 요청된 통계 유형 감지"""
        if not query:
            return {'type': 'all', 'keywords': []}
        
        query_lower = query.lower()
        
        stats_patterns = {
            'yearly': ['년도별', '연도별', '년별', '연별', '년도', '연도', '년', '연'],
            'monthly': ['월별', '월'],
            'time_period': ['시간대별', '주간', '야간', '낮', '밤'],
            'weekday': ['요일별', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일', '평일', '주말'],
            'department': ['부서별', '부서', '팀별', '팀', '담당부서', '처리부서'],
            'service': ['서비스별', '서비스'],
            'grade': ['등급별', '등급', '장애등급', '1등급', '2등급', '3등급', '4등급']
        }
        
        detected_types = []
        for stats_type, keywords in stats_patterns.items():
            if any(keyword in query_lower for keyword in keywords):
                detected_types.append(stats_type)
        
        if not detected_types:
            return {'type': 'all', 'keywords': []}
        
        return {'type': 'specific', 'types': detected_types, 'keywords': []}

    def _extract_incident_id_sort_key(self, incident_id):
        """장애 ID에서 정렬용 키 추출"""
        if not incident_id:
            return 999999999999999
        
        try:
            if incident_id.startswith('INM') and len(incident_id) > 3:
                number_part = incident_id[3:]
                result = int(number_part)
                print(f"DEBUG: ID {incident_id} -> key {result}")
                return result
            else:
                result = hash(incident_id) % 999999999999999
                print(f"DEBUG: ID {incident_id} (non-INM) -> key {result}")
                return result
                
        except (ValueError, TypeError) as e:
            result = hash(str(incident_id)) % 999999999999999
            print(f"DEBUG: ID {incident_id} (parse error) -> key {result}, error: {e}")
            return result

    def _test_incident_id_sorting(self, documents):
        """장애 ID 정렬 테스트 함수"""
        if not documents:
            return
        
        print("DEBUG: Testing incident ID sorting:")
        id_keys = []
        for doc in documents[:10]:
            incident_id = doc.get('incident_id', 'N/A')
            if incident_id != 'N/A':
                sort_key = self._extract_incident_id_sort_key(incident_id)
                id_keys.append((incident_id, sort_key))
        
        id_keys.sort(key=lambda x: x[1])
        
        print("DEBUG: Incident IDs sorted by key:")
        for i, (incident_id, sort_key) in enumerate(id_keys):
            print(f"  {i+1}. {incident_id} (key: {sort_key})")

    def _apply_default_sorting(self, documents):
        """기본 정렬 적용"""
        if not documents:
            return documents
        
        try:
            self._test_incident_id_sorting(documents)
            
            def default_sort_key(doc):
                error_date = doc.get('error_date', '1900-01-01')
                if not error_date:
                    error_date = '1900-01-01'
                
                error_time = doc.get('error_time', 0)
                try:
                    error_time_val = int(error_time) if error_time is not None else 0
                except (ValueError, TypeError):
                    error_time_val = 0
                
                incident_id = doc.get('incident_id', 'INM99999999999')
                incident_sort_key = self._extract_incident_id_sort_key(incident_id)
                
                return (
                    error_date,
                    error_time_val,
                    -incident_sort_key
                )
            
            documents.sort(key=default_sort_key, reverse=True)
            
            print("DEBUG: Applied default sorting - Final result:")
            for i, doc in enumerate(documents[:7]):
                incident_id = doc.get('incident_id', 'N/A')
                sort_key = self._extract_incident_id_sort_key(incident_id) if incident_id != 'N/A' else 'N/A'
                print(f"  {i+1}. ID: {incident_id} (key: {sort_key}), Date: {doc.get('error_date')}, Time: {doc.get('error_time')}분")
            
            dates = [doc.get('error_date') for doc in documents[:7]]
            times = [doc.get('error_time') for doc in documents[:7]]
            print(f"DEBUG: Dates: {dates}")
            print(f"DEBUG: Times: {times}")
            
            if len(set(dates)) <= 2 and len(set(times)) <= 2:
                print("DEBUG: Dates and times are similar, re-sorting by incident ID only")
                documents.sort(key=lambda doc: self._extract_incident_id_sort_key(doc.get('incident_id', 'INM99999999999')))
                
                print("DEBUG: After incident ID only sorting:")
                for i, doc in enumerate(documents[:7]):
                    incident_id = doc.get('incident_id', 'N/A')
                    sort_key = self._extract_incident_id_sort_key(incident_id) if incident_id != 'N/A' else 'N/A'
                    print(f"  {i+1}. ID: {incident_id} (key: {sort_key})")
                
        except Exception as e:
            print(f"DEBUG: Default sorting error: {e}")
            try:
                print("DEBUG: Fallback to incident ID only sorting")
                documents.sort(key=lambda doc: self._extract_incident_id_sort_key(doc.get('incident_id', 'INM99999999999')))
                
                print("DEBUG: Fallback sorting result:")
                for i, doc in enumerate(documents[:7]):
                    incident_id = doc.get('incident_id', 'N/A')
                    sort_key = self._extract_incident_id_sort_key(incident_id) if incident_id != 'N/A' else 'N/A'
                    print(f"  {i+1}. ID: {incident_id} (key: {sort_key})")
                    
            except Exception as fallback_error:
                print(f"DEBUG: Fallback sorting also failed: {fallback_error}")
                pass

    def detect_sorting_requirements(self, query):
        """쿼리에서 정렬 요구사항 감지"""
        sort_info = {
            'requires_custom_sort': False,
            'sort_field': None,
            'sort_direction': 'desc',
            'sort_type': None,
            'limit': None,
            'secondary_sort': 'default'
        }
        
        if not query:
            return sort_info
        
        query_lower = query.lower()
        
        error_time_patterns = [
            r'장애시간.*(?:가장.*?긴|긴.*?순|오래.*?걸린|최대|큰.*?순|많은.*?순)',
            r'(?:가장.*?긴|긴.*?순|오래.*?걸린|최대|큰.*?순|많은.*?순).*장애시간',
            r'장애시간.*(?:내림차순|큰.*?순서|높은.*?순서|많은.*?순서)',
            r'error_time.*(?:desc|내림차순|큰.*?순서)',
            r'(?:최장|최대|가장.*?오래).*장애',
            r'장애.*(?:최장|최대|가장.*?오래)',
            r'top.*\d+.*장애시간',
            r'상위.*\d+.*장애시간',
            r'장애시간.*(?:순서|정렬)',
            r'(?:순서|정렬).*장애시간'
        ]
        
        date_patterns = [
            r'발생일.*순서',
            r'날짜.*순서',
            r'시간.*순서.*발생',
            r'최근.*순서',
            r'과거.*순서',
            r'error_date.*(?:desc|asc|내림차순|오름차순)',
            r'최신.*장애',
            r'최근.*장애',
            r'예전.*장애',
            r'과거.*장애'
        ]
        
        top_patterns = [
            r'top\s*(\d+)',
            r'Top\s*(\d+)',            
            r'상위\s*(\d+)',
            r'첫\s*(\d+)',
            r'(\d+)개.*?순서',
            r'(\d+)건.*?순서',
            r'(\d+)개.*?정렬',
            r'(\d+)건.*?정렬'
        ]
        
        for pattern in error_time_patterns:
            if re.search(pattern, query_lower):
                sort_info['requires_custom_sort'] = True
                sort_info['sort_field'] = 'error_time'
                sort_info['sort_type'] = 'error_time'
                sort_info['sort_direction'] = 'desc'
                break
        
        if not sort_info['requires_custom_sort']:
            for pattern in date_patterns:
                match = re.search(pattern, query_lower)
                if match:
                    sort_info['requires_custom_sort'] = True
                    sort_info['sort_field'] = 'error_date'
                    sort_info['sort_type'] = 'error_date'
                    if any(keyword in query_lower for keyword in ['최근', '최신']):
                        sort_info['sort_direction'] = 'desc'
                    elif any(keyword in query_lower for keyword in ['과거', '예전']):
                        sort_info['sort_direction'] = 'asc'
                    else:
                        sort_info['sort_direction'] = 'desc'
                    break
        
        for pattern in top_patterns:
            match = re.search(pattern, query_lower)
            if match:
                try:
                    limit = int(match.group(1))
                    sort_info['limit'] = min(limit, 50)
                    if not sort_info['requires_custom_sort']:
                        sort_info['requires_custom_sort'] = True
                        sort_info['sort_field'] = 'error_time'
                        sort_info['sort_type'] = 'error_time'
                        sort_info['sort_direction'] = 'desc'
                except ValueError:
                    pass
                break
        
        if '시간순서' in query_lower and not sort_info['requires_custom_sort']:
            sort_info['requires_custom_sort'] = True
            sort_info['sort_field'] = 'error_date'
            sort_info['sort_type'] = 'error_date'
            sort_info['sort_direction'] = 'desc'
        
        return sort_info

    def apply_custom_sorting(self, documents, sort_info):
        """정렬 요구사항에 따른 문서 정렬 적용"""
        if not documents:
            return documents
        
        try:
            if sort_info['requires_custom_sort']:
                
                if sort_info['sort_type'] == 'error_time':
                    def error_time_sort_key(doc):
                        error_time = doc.get('error_time', 0)
                        if error_time is None:
                            error_time_val = 0
                        else:
                            try:
                                error_time_val = int(error_time)
                            except (ValueError, TypeError):
                                error_time_val = 0
                        
                        error_date = doc.get('error_date', '1900-01-01')
                        incident_id = doc.get('incident_id', 'INM99999999999')
                        incident_sort_key = self._extract_incident_id_sort_key(incident_id)
                        
                        if sort_info['sort_direction'] == 'desc':
                            return (-error_time_val, error_date, incident_sort_key)
                        else:
                            return (error_time_val, error_date, incident_sort_key)
                    
                    documents.sort(key=error_time_sort_key)
                    
                elif sort_info['sort_type'] == 'error_date':
                    def error_date_sort_key(doc):
                        error_date = doc.get('error_date', '1900-01-01')
                        if not error_date:
                            error_date = '1900-01-01'
                        
                        error_time = doc.get('error_time', 0)
                        try:
                            error_time_val = int(error_time) if error_time is not None else 0
                        except (ValueError, TypeError):
                            error_time_val = 0
                        
                        incident_id = doc.get('incident_id', 'INM99999999999')
                        incident_sort_key = self._extract_incident_id_sort_key(incident_id)
                        
                        if sort_info['sort_direction'] == 'desc':
                            return (error_date, -error_time_val, incident_sort_key)
                        else:
                            return (error_date, error_time_val, incident_sort_key)
                    
                    documents.sort(key=error_date_sort_key, reverse=(sort_info['sort_direction'] == 'desc'))
                
                if sort_info['limit']:
                    documents = documents[:sort_info['limit']]
            
            else:
                self._apply_default_sorting(documents)
            
            return documents
            
        except Exception as e:
            print(f"DEBUG: Sorting error: {e}")
            self._apply_default_sorting(documents)
            return documents

    def _validate_sorting_result(self, documents, sort_info):
        """정렬 결과 검증 및 로깅"""
        if not documents or len(documents) < 2:
            return True
        
        try:
            print(f"DEBUG: Sorting validation - Type: {sort_info.get('sort_type', 'default')}")
            
            if sort_info.get('sort_type') == 'error_time':
                for i in range(len(documents) - 1):
                    try:
                        current_time = int(documents[i].get('error_time', 0))
                        next_time = int(documents[i + 1].get('error_time', 0))
                        
                        if sort_info['sort_direction'] == 'desc' and current_time < next_time:
                            print(f"DEBUG: Error time sorting issue at index {i}: {current_time} < {next_time}")
                            return False
                        elif sort_info['sort_direction'] == 'asc' and current_time > next_time:
                            print(f"DEBUG: Error time sorting issue at index {i}: {current_time} > {next_time}")
                            return False
                    except (ValueError, TypeError):
                        continue
            
            elif sort_info.get('sort_type') == 'error_date':
                for i in range(len(documents) - 1):
                    current_date = documents[i].get('error_date', '1900-01-01')
                    next_date = documents[i + 1].get('error_date', '1900-01-01')
                    
                    if sort_info['sort_direction'] == 'desc' and current_date < next_date:
                        print(f"DEBUG: Error date sorting issue at index {i}: {current_date} < {next_date}")
                        return False
                    elif sort_info['sort_direction'] == 'asc' and current_date > next_date:
                        print(f"DEBUG: Error date sorting issue at index {i}: {current_date} > {next_date}")
                        return False
            
            else:
                print("DEBUG: Validating default sorting (Incident ID ascending):")
                for i in range(len(documents) - 1):
                    current_id = documents[i].get('incident_id', 'INM99999999999')
                    next_id = documents[i + 1].get('incident_id', 'INM99999999999')
                    current_id_key = self._extract_incident_id_sort_key(current_id)
                    next_id_key = self._extract_incident_id_sort_key(next_id)
                    
                    current_date = documents[i].get('error_date', '1900-01-01')
                    next_date = documents[i + 1].get('error_date', '1900-01-01')
                    current_time = documents[i].get('error_time', 0)
                    next_time = documents[i + 1].get('error_time', 0)
                    
                    if current_date == next_date and current_time == next_time:
                        if current_id_key > next_id_key:
                            print(f"DEBUG: Incident ID sorting issue at index {i}: {current_id}({current_id_key}) > {next_id}({next_id_key})")
                            return False
            
            print("DEBUG: Final sorting result:")
            for i, doc in enumerate(documents[:7]):
                incident_id = doc.get('incident_id', 'N/A')
                sort_key = self._extract_incident_id_sort_key(incident_id) if incident_id != 'N/A' else 'N/A'
                print(f"  {i+1}. ID: {incident_id} (key: {sort_key}), "
                      f"Date: {doc.get('error_date', 'N/A')}, "
                      f"Time: {doc.get('error_time', 'N/A')}분")
            
            return True
            
        except Exception as e:
            print(f"DEBUG: Sorting validation error: {e}")
            return False

    def _apply_improved_sorting_in_rag_response(self, processing_documents, sort_info):
        """RAG 응답 생성에서 개선된 정렬 적용"""
        if sort_info['requires_custom_sort']:
            with trace(name="custom_sorting", inputs=sort_info) as sort_trace:
                original_order = [doc.get('incident_id', '') for doc in processing_documents[:5]]
                
                processing_documents = self.apply_custom_sorting(processing_documents, sort_info)
                
                is_valid = self._validate_sorting_result(processing_documents, sort_info)
                if not is_valid:
                    print("DEBUG: Sorting validation failed, applying default sorting")
                    self._apply_default_sorting(processing_documents)
                
                new_order = [doc.get('incident_id', '') for doc in processing_documents[:5]]
                
                self.safe_trace_update(sort_trace, outputs={
                    "sort_type": sort_info['sort_type'],
                    "sort_direction": sort_info['sort_direction'],
                    "limit": sort_info['limit'],
                    "original_order": original_order,
                    "new_order": new_order,
                    "validation_passed": is_valid
                })
        else:
            print("DEBUG: Applying default sorting")
            self._apply_default_sorting(processing_documents)
            
            sample_order = [f"{doc.get('incident_id', 'N/A')}({doc.get('error_date', 'N/A')},{doc.get('error_time', 0)}분)" 
                          for doc in processing_documents[:3]]
            print(f"DEBUG: Default sorting applied - Sample: {sample_order}")
        
        return processing_documents

    def filter_negative_keywords(self, documents, query_type, query_text):
        """부적절한 키워드가 포함된 문서 제거"""
        
        if not documents or documents is None:
            return []
        
        negative_keywords = {
            'repair': {
                'strong': ['통계', '건수', '현황', '분석', '몇건', '개수', '이', '전체'],
                'weak': ['연도별', '월별', '시간대별', '요일별']
            },
            'cause': {
                'strong': ['복구방법', '해결방법', '조치방법', '대응방법'],
                'weak': ['통계', '건수', '현황', '분석']
            },
            'similar': {
                'strong': ['건수', '통계', '현황', '분석', '개수', '이'],
                'weak': ['연도별', '월별', '시간대별']
            },
            'default': {
                'strong': [],
                'weak': []
            }
        }
        
        keywords = negative_keywords.get(query_type, {'strong': [], 'weak': []})
        
        filtered_docs = []
        filter_stats = {'total': len(documents), 'strong_filtered': 0, 'weak_filtered': 0}
        
        for doc in documents:
            if doc is None:
                continue
                
            doc_text = f"{doc.get('symptom', '')} {doc.get('effect', '')} {doc.get('incident_repair', '')}".lower()
            
            strong_negative = any(keyword in doc_text for keyword in keywords['strong'])
            if strong_negative:
                filter_stats['strong_filtered'] += 1
                continue
            
            weak_negative_count = sum(1 for keyword in keywords['weak'] if keyword in doc_text)
            if weak_negative_count > 0:
                filter_stats['weak_filtered'] += 1
                original_score = doc.get('final_score', 0)
                penalty = weak_negative_count * 0.1
                doc['final_score'] = max(original_score - penalty, 0)
                doc['negative_penalty'] = penalty
            
            filtered_docs.append(doc)
        
        return filtered_docs

    def calculate_confidence_score(self, query, documents, query_type):
        """다중 요소 기반 신뢰도 점수 계산"""
        
        if not documents or documents is None:
            return 0.0
        
        confidence_factors = {
            'document_count': 0.2,
            'score_consistency': 0.25,
            'service_match_quality': 0.3,
            'query_clarity': 0.15,
            'temporal_alignment': 0.1
        }
        
        confidence_score = 0.0
        
        doc_count = len(documents)
        optimal_range = {'repair': (3, 8), 'cause': (3, 8), 'similar': (5, 15), 'statistics': (5, 50), 'default': (5, 20)}
        min_docs, max_docs = optimal_range.get(query_type, (3, 15))
        
        if min_docs <= doc_count <= max_docs:
            document_score = 1.0
        elif doc_count < min_docs:
            document_score = doc_count / min_docs
        else:
            document_score = max(0.3, max_docs / doc_count)
        
        confidence_score += document_score * confidence_factors['document_count']
        
        if documents:
            scores = [doc.get('final_score', 0) for doc in documents[:5]]
            if len(scores) > 1:
                score_std = self._calculate_std(scores)
                consistency_score = max(0, 1 - (score_std / max(scores) if max(scores) > 0 else 1))
            else:
                consistency_score = 1.0
        else:
            consistency_score = 0.0
        
        confidence_score += consistency_score * confidence_factors['score_consistency']
        
        if documents:
            exact_matches = sum(1 for doc in documents if doc.get('service_match_type') == 'exact')
            match_quality = exact_matches / len(documents)
        else:
            match_quality = 0.0
        
        confidence_score += match_quality * confidence_factors['service_match_quality']
        
        clarity_keywords = {
            'repair': ['복구방법', '해결방법', '조치방법'],
            'cause': ['원인', '이유', '왜'],
            'similar': ['유사', '비슷', '동일'],
            'statistics': ['건수', '통계', '현황', '분포', '월별', '연도별'],
            'default': ['건수', '통계', '현황', '몇', '등급']
        }
        
        if not query:
            clarity_score = 0.0
        else:
            query_lower = query.lower()
            relevant_keywords = clarity_keywords.get(query_type, [])
            clarity_score = min(1.0, sum(1 for keyword in relevant_keywords if keyword in query_lower) / max(len(relevant_keywords), 1))
        
        confidence_score += clarity_score * confidence_factors['query_clarity']
        
        time_keywords = ['야간', '주간', '요일', '월', '화', '수', '목', '금', '토', '일']
        has_time_condition = any(keyword in query.lower() for keyword in time_keywords) if query else False
        
        if has_time_condition and documents:
            time_matching_docs = sum(1 for doc in documents 
                                   if doc.get('daynight') or doc.get('week'))
            temporal_score = time_matching_docs / len(documents)
        else:
            temporal_score = 1.0 if not has_time_condition else 0.5
        
        confidence_score += temporal_score * confidence_factors['temporal_alignment']
        
        return min(confidence_score, 1.0)
    
    def _calculate_std(self, values):
        """표준편차 계산"""
        if not values:
            return 0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5

    def remove_text_charts_from_response(self, response_text):
        """응답에서 텍스트 기반 차트 제거"""
        if not response_text:
            return response_text
            
        import re
        
        # 텍스트 차트 패턴들
        text_chart_patterns = [
            # "각 월별 장애건수는 다음과 같이 차트로 나타낼 수 있습니다:" 형태
            r'각\s*월별.*?차트로\s*나타낼\s*수\s*있습니다:.*?(?=\n\n|\n[^월"\d]|$)',
            # "다음과 같이 그래프로 표시됩니다:" 형태  
            r'다음과\s*같이.*?그래프로\s*표시됩니다:.*?(?=\n\n|\n[^월"\d]|$)',
            # 월별 데이터 + █ 문자 패턴
            r'\d+월:\s*[█▓▒░▬\*\-\|]+.*?(?=\n\n|\n[^월"\d]|$)',
            # "이 통계는 제공된 문서의 내용을 기반으로" 형태
            r'이\s*통계는\s*제공된\s*문서의.*?결과입니다\.?',
            # 연속된 █ 문자가 포함된 라인들
            r'\n.*[█▓▒░▬]{2,}.*\n',
            # 차트 설명 문구들
            r'차트로\s*나타내[면며].*?:.*?(?=\n\n|\n[^월"\d]|$)',
            r'그래프로\s*표시하[면며].*?:.*?(?=\n\n|\n[^월"\d]|$)',
            # 바 차트나 텍스트 시각화 블록
            r'```[^`]*[█▓▒░▬\*\-\|]{2,}[^`]*```',
            # "차트로 나타내면", "그래프로 표시하면" 등의 문구와 이어지는 텍스트 차트
            r'(차트로|그래프로).*?(나타내|표시|보여).*?[:：]\s*\n.*?[█▓▒░▬\*\-\|]+.*?(?=\n\n|$)',
            # 연도별, 월별 데이터와 함께 나오는 텍스트 차트
            r'\d+[년월일].*?[█▓▒░▬\*\-\|]{3,}.*?(?=\n\n|$)',
        ]
        
        cleaned_response = response_text
        
        for pattern in text_chart_patterns:
            cleaned_response = re.sub(pattern, '', cleaned_response, flags=re.MULTILINE | re.DOTALL)
        
        # 중복된 줄바꿈 정리
        cleaned_response = re.sub(r'\n{3,}', '\n\n', cleaned_response)
        cleaned_response = cleaned_response.strip()
        
        return cleaned_response

    @traceable(name="generate_rag_response")
    def generate_rag_response_with_adaptive_processing(self, query, documents, query_type="default", time_conditions=None, department_conditions=None, reprompting_info=None):
        """개선된 RAG 응답 생성 - 중복 제거 비활성화 + statistics 타입 지원"""
        
        if documents is None:
            documents = []
        
        if not documents:
            return "검색된 문서가 없어서 답변을 제공할 수 없습니다. 다른 검색 조건을 시도해보세요."
        
        with trace(
            name="adaptive_rag_processing", 
            inputs={
                "query": query,
                "document_count": len(documents) if documents else 0,
                "query_type": query_type,
                "has_time_conditions": bool(time_conditions and time_conditions.get('is_time_query')),
                "has_department_conditions": bool(department_conditions and department_conditions.get('is_department_query')),
                "reprompting_applied": bool(reprompting_info and reprompting_info.get('transformed'))
            }
        ) as trace_context:
            try:
                start_time = time.time()

                # 통계 일관성 검증을 위한 추가 로깅
                if any(keyword in query.lower() for keyword in ['건수', '통계', '현황', '월']):
                    print(f"DEBUG: Statistics consistency check for query: '{query}'")
                    print(f"DEBUG: Input documents count: {len(documents)}")
                    
                    # 월별 분포 미리 확인
                    month_check = {}
                    for doc in documents:
                        month = doc.get('month', '')
                        error_date = doc.get('error_date', '')
                        if month:
                            month_check[month] = month_check.get(month, 0) + 1
                        elif error_date and len(error_date) >= 7:
                            try:
                                month_from_date = error_date.split('-')[1]
                                if month_from_date.isdigit():
                                    month_num = int(month_from_date)
                                    month_check[str(month_num)] = month_check.get(str(month_num), 0) + 1
                            except:
                                pass
                    print(f"DEBUG: Pre-calculation month distribution: {month_check}")

                print(f"DEBUG: Starting improved statistics calculation (no duplicate removal)")
                unified_stats = self.calculate_unified_statistics(documents, query, query_type)
                print(f"DEBUG: Improved stats calculated: {unified_stats}")

                # 통계 일관성 최종 검증
                if unified_stats.get('monthly_stats'):
                    monthly_total = sum(unified_stats['monthly_stats'].values())
                    total_count = unified_stats.get('total_count', 0)
                    print(f"DEBUG: Final consistency check - Monthly total: {monthly_total}, Document total: {total_count}")
                    
                    if monthly_total != total_count and not unified_stats.get('is_error_time_query', False):
                        print(f"WARNING: Statistics inconsistency detected!")
                        print(f"  - Monthly sum: {monthly_total}")
                        print(f"  - Document count: {total_count}")
                        print(f"  - Monthly breakdown: {unified_stats['monthly_stats']}")


                if not unified_stats.get('validation', {}).get('is_valid', True):
                    validation_errors = unified_stats.get('validation', {}).get('errors', [])
                    if validation_errors and self.debug_mode:
                        st.warning(f"통계 계산 검증 오류: {validation_errors}")
                
                print(f"DEBUG: Starting chart detection for query: {query}")
                
                chart_suitable, chart_type, chart_data = self.chart_manager.detect_chart_suitable_query(query, documents)
                chart_fig = None
                chart_info = None
                
                print(f"DEBUG: Chart detection result: suitable={chart_suitable}, type={chart_type}")
                
                if chart_suitable:
                    if chart_type and chart_data:
                        print(f"DEBUG: Using extracted chart data: {chart_data}")
                    else:
                        print("DEBUG: Chart manager failed, using improved unified stats")
                        
                        if 'monthly' in unified_stats and unified_stats['monthly_stats']:
                            chart_data = unified_stats['monthly_stats']
                            chart_type = 'line'
                            print(f"DEBUG: Using monthly stats: {chart_data}")
                        elif 'yearly' in unified_stats and unified_stats['yearly_stats']:
                            chart_data = unified_stats['yearly_stats']  
                            chart_type = 'line'
                            print(f"DEBUG: Using yearly stats: {chart_data}")
                        elif 'service' in unified_stats and unified_stats['service_stats']:
                            chart_data = unified_stats['service_stats']
                            chart_type = 'horizontal_bar'
                            print(f"DEBUG: Using service stats: {chart_data}")
                        elif 'grade' in unified_stats and unified_stats['grade_stats']:
                            chart_data = unified_stats['grade_stats']
                            chart_type = 'pie'
                            print(f"DEBUG: Using grade stats: {chart_data}")
                        else:
                            chart_data = {'전체 장애': unified_stats['total_count']}
                            chart_type = 'bar'
                            print(f"DEBUG: Using total count: {chart_data}")
                    
                    if chart_data:
                        chart_title = self._generate_chart_title(query, chart_type)
                        print(f"DEBUG: Generating chart with title: {chart_title}")
                        
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
                                print("DEBUG: Chart created successfully")
                            else:
                                print("DEBUG: Chart creation returned None")
                                
                        except Exception as chart_error:
                            print(f"DEBUG: Chart creation error: {chart_error}")
                            chart_info = None
                
                sort_info = self.detect_sorting_requirements(query)
                documents = self.filter_negative_keywords(documents, query_type, query)
                
                if time_conditions and time_conditions.get('is_time_query'):
                    with trace(name="time_filtering", inputs=time_conditions) as time_trace:
                        original_count = len(documents)
                        documents = self.search_manager.filter_documents_by_time_conditions(documents, time_conditions)
                        self.safe_trace_update(time_trace, outputs={
                            "original_count": original_count,
                            "filtered_count": len(documents)
                        })
                        
                        if not documents:
                            time_desc = []
                            if time_conditions.get('daynight'):
                                time_desc.append(f"{time_conditions['daynight']}")
                            if time_conditions.get('week'):
                                time_desc.append(f"{time_conditions['week']}")
                            
                            result = f"{''.join(time_desc)} 조건에 해당하는 장애 내역을 찾을 수 없습니다. 다른 검색 조건을 시도해보세요."
                            self.safe_trace_update(trace_context,
                                outputs={"response": result, "no_results_reason": "time_filter"}
                            )
                            return result
                
                
                if department_conditions and department_conditions.get('is_department_query'):
                    with trace(name="department_filtering", inputs=department_conditions) as dept_trace:
                        original_count = len(documents)
                        documents = self.search_manager.filter_documents_by_department_conditions(documents, department_conditions)
                        self.safe_trace_update(dept_trace, outputs={
                            "original_count": original_count,
                            "filtered_count": len(documents)
                        })
                        
                        if not documents:
                            dept_desc = department_conditions.get('owner_depart', '해당 부서')
                            result = f"{dept_desc} 조건에 해당하는 장애 내역을 찾을 수 없습니다. 다른 검색 조건을 시도해보세요."
                            self.safe_trace_update(trace_context,
                                outputs={"response": result, "no_results_reason": "department_filter"}
                            )
                            return result
                
                confidence_score = self.calculate_confidence_score(query, documents, query_type)
                use_llm_validation = query_type in ['repair', 'cause']
                
                if use_llm_validation:
                    with trace(name="llm_validation_step") as validation_trace:
                        validated_documents = self.validate_document_relevance_with_llm(query, documents)
                        self.safe_trace_update(validation_trace, outputs={
                            "original_count": len(documents),
                            "validated_count": len(validated_documents)
                        })
                    
                    if not validated_documents:
                        result = "검색된 문서들이 사용자 질문과 관련성이 낮아 적절한 답변을 제공할 수 없습니다. 다른 검색어나 더 구체적인 질문을 시도해보세요."
                        self.safe_trace_update(trace_context,
                            outputs={"response": result, "no_results_reason": "low_relevance"}
                        )
                        return result
                    
                    processing_documents = validated_documents
                else:
                    processing_documents = documents

                processing_documents = self._apply_improved_sorting_in_rag_response(processing_documents, sort_info)
                
                # 중복 제거 로직 제거 - 모든 문서 유지
                print(f"DEBUG: Keeping all documents without deduplication: {len(processing_documents)} documents")
                total_count = len(processing_documents)
                
                yearly_stats = unified_stats.get('yearly_stats', {})
                monthly_stats = unified_stats.get('monthly_stats', {})
                time_stats = unified_stats.get('time_stats', {'daynight': {}, 'week': {}})
                department_stats = unified_stats.get('department_stats', {})
                service_stats = unified_stats.get('service_stats', {})
                grade_stats = unified_stats.get('grade_stats', {})
                is_error_time_query = unified_stats.get('is_error_time_query', False)
                calculation_details = unified_stats.get('calculation_details', {})
                
                yearly_total = sum(yearly_stats.values())
                monthly_total = sum(monthly_stats.values())
                
                context_parts = []
                
                stats_info = f"""
=== 정확한 집계 정보 ===
전체 문서 수: {total_count}건 (제공된 모든 문서 기준으로 통계 계산)"""
                
                if yearly_stats:
                    stats_info += f"\n연도별 분포: {dict(sorted(yearly_stats.items()))}"
                    stats_info += f"\n연도별 합계: {yearly_total}{'분' if is_error_time_query else '건'}"
                
                if monthly_stats:
                    stats_info += f"\n월별 분포: {monthly_stats}"
                    stats_info += f"\n월별 합계: {monthly_total}{'분' if is_error_time_query else '건'}"
                    if is_error_time_query:
                        stats_info += f"\n데이터 유형: 장애시간 합산(분 단위)"
                        if calculation_details:
                            stats_info += f"\n총 장애시간: {calculation_details.get('total_error_time_minutes', 0)}분 ({calculation_details.get('total_error_time_hours', 0)}시간)"
                            stats_info += f"\n평균 장애시간: {calculation_details.get('average_error_time', 0)}분"
                            stats_info += f"\n최대 장애시간: {calculation_details.get('max_error_time', 0)}분"
                    else:
                        stats_info += f"\n데이터 유형: 발생 건수"
                
                if service_stats:
                    stats_info += f"\n서비스별 분포: {dict(sorted(service_stats.items(), key=lambda x: x[1], reverse=True))}"
                
                if grade_stats:
                    stats_info += f"\n장애등급별 분포: {dict(sorted(grade_stats.items(), key=lambda x: int(x[0][0]) if x[0] and x[0][0].isdigit() else 999))}"
                
                if time_stats['daynight']:
                    stats_info += f"\n시간대별 분포: {time_stats['daynight']}"
                
                if time_stats['week']:
                    stats_info += f"\n요일별 분포: {time_stats['week']}"
                
                if department_stats:
                    stats_info += f"\n부서별 분포: {department_stats}"
                
                if sort_info['requires_custom_sort']:
                    sort_desc = ""
                    if sort_info['sort_type'] == 'error_time':
                        sort_desc = f"장애시간 기준 {'내림차순(긴 순서)' if sort_info['sort_direction'] == 'desc' else '오름차순(짧은 순서)'} 정렬"
                    elif sort_info['sort_type'] == 'error_date':
                        sort_desc = f"발생일자 기준 {'내림차순(최근 순)' if sort_info['sort_direction'] == 'desc' else '오름차순(과거 순)'} 정렬"
                    
                    if sort_info['limit']:
                        sort_desc += f", 상위 {sort_info['limit']}개 제한"
                    
                    stats_info += f"\n정렬 정보: {sort_desc}"
                else:
                    stats_info += f"\n정렬 정보: 기본 정렬(발생일자 최신순 → 장애시간 큰순 → 장애ID 순)"
                
                if self.debug_mode and unified_stats.get('validation'):
                    validation = unified_stats['validation']
                    if validation.get('warnings'):
                        stats_info += f"\n검증 경고: {len(validation['warnings'])}개"
                
                stats_info += "\n=========================="
                
                context_parts.append(stats_info)
                
                for i, doc in enumerate(processing_documents):
                    final_score = doc.get('final_score', 0) if doc.get('final_score') is not None else 0.0
                    quality_tier = doc.get('quality_tier', 'Standard')
                    filter_reason = doc.get('filter_reason', '기본 선별')
                    service_match_type = doc.get('service_match_type', 'unknown')
                    relevance_score = doc.get('relevance_score', 0) if use_llm_validation else "N/A"
                    validation_reason = doc.get('validation_reason', '검증됨') if use_llm_validation else "포괄적 처리"
                    negative_penalty = doc.get('negative_penalty', 0)
                    
                    validation_info = f" - 관련성: {relevance_score}점 ({validation_reason})" if use_llm_validation else " - 포괄적 검색"
                    penalty_info = f" - 네거티브 감점: {negative_penalty:.1f}" if negative_penalty > 0 else ""
                    
                    time_info = ""
                    if doc.get('daynight'):
                        time_info += f" - 시간대: {doc.get('daynight')}"
                    if doc.get('week'):
                        time_info += f" - 요일: {doc.get('week')}"
                    
                    department_info = ""
                    if doc.get('owner_depart'):
                        department_info += f" - 담당부서: {doc.get('owner_depart')}"
                    
                    grade_info = ""
                    if doc.get('incident_grade'):
                        grade_info += f" - 장애등급: {doc.get('incident_grade')}"
                    
                    sort_info_text = ""
                    if sort_info['requires_custom_sort']:
                        if sort_info['sort_type'] == 'error_time':
                            error_time = doc.get('error_time', 0)
                            sort_info_text = f" - 장애시간: {error_time}분 (정렬기준)"
                        elif sort_info['sort_type'] == 'error_date':
                            error_date = doc.get('error_date', '')
                            sort_info_text = f" - 발생일자: {error_date} (정렬기준)"
                    
                    incident_repair = doc.get('incident_repair', '').strip()
                    incident_plan = doc.get('incident_plan', '').strip()
                    
                    if incident_repair and incident_plan:
                        if incident_plan in incident_repair:
                            incident_repair = incident_repair.replace(incident_plan, '').strip()
                        
                    context_part = f"""문서 {i+1} [{quality_tier}급 - {filter_reason} - {service_match_type} 매칭{validation_info}{penalty_info}{time_info}{department_info}{grade_info}{sort_info_text}]:
장애 ID: {doc['incident_id']}
서비스명: {doc['service_name']}
장애시간: {doc['error_time']}
영향도: {doc['effect']}
현상: {doc['symptom']}
복구공지: {doc['repair_notice']}
발생일자: {doc['error_date']}
요일: {doc['week']}
시간대: {doc['daynight']}
장애원인: {doc['root_cause']}
복구방법(incident_repair): {incident_repair}
개선계획(incident_plan): {incident_plan}
원인유형: {doc['cause_type']}
처리유형: {doc['done_type']}
장애등급: {doc['incident_grade']}
담당부서: {doc['owner_depart']}
연도: {doc['year']}
월: {doc['month']}
품질점수: {final_score:.2f}
"""
                    if use_llm_validation:
                        context_part += f"관련성점수: {relevance_score}점 \n"
                    
                    context_parts.append(context_part)
                
                context = "\n\n".join(context_parts)
                
                system_prompt = SystemPrompts.get_prompt(query_type)
                final_query = reprompting_info.get('transformed_query', query) if reprompting_info and reprompting_info.get('transformed') else query

                sorting_instruction = ""
                if sort_info.get('requires_custom_sort'):
                    sort_type_kr = ""
                    if sort_info.get('sort_type') == 'error_time':
                        sort_type_kr = "장애시간이 긴 순서"
                    elif sort_info.get('sort_type') == 'error_date':
                        sort_type_kr = "최신 발생일자 순서"
                    
                    if sort_type_kr:
                        sorting_instruction = f"""
**중요! 정렬 순서 준수:**
- 아래 문서들은 사용자의 요청에 따라 '{sort_type_kr}'으로 이미 정렬되어 있습니다.
- **반드시 이 순서를 그대로 유지하여 답변을 생성해야 합니다.** 순서를 절대 변경하지 마세요.
"""

                time_stats_instruction = ""
                if is_error_time_query:
                    time_stats_instruction = f"""
**중요! 장애시간 통계 처리:**
- 이 질문은 장애시간 합산 통계에 관한 질문입니다.
- 월별 통계: {monthly_stats} (단위: 분)
- 답변 시 "건"이 아닌 "분" 단위로 표시해주세요.
- 차트가 함께 제공되는 경우 차트의 단위와 일치시켜주세요.
- 총 장애시간: {calculation_details.get('total_error_time_minutes', 0)}분 ({calculation_details.get('total_error_time_hours', 0)}시간)
- 평균 장애시간: {calculation_details.get('average_error_time', 0)}분
- 평균 장애시간: {calculation_details.get('average_error_time', 0)}분
"""

                chart_instruction = ""
                if chart_suitable and chart_data:
                    chart_instruction = """
**중요! 차트 시각화 처리:**
- 이 질문에는 자동으로 시각화 차트가 제공됩니다
- 답변에서 텍스트 기반 차트(█, *, -, | 등의 문자를 사용한 시각화)를 생성하지 마세요
- "차트로 나타내면", "그래프로 표시하면" 등의 문구 사용 금지
- 숫자 데이터와 분석 결과만 제공하고, 별도의 텍스트 시각화는 생략하세요
- 차트는 시스템에서 자동으로 생성되어 별도로 표시됩니다
"""

                user_prompt = f"""
다음 장애 이력 문서들을 참고하여 질문에 답변해주세요.
{sorting_instruction}
{time_stats_instruction}
{chart_instruction}
**중요! 복구방법 관련 답변 시 필수사항:**
- 복구방법 질문에는 반드시 incident_repair 필드의 데이터만 사용하세요
- incident_plan(개선계획)은 복구방법에 포함하지 말고 별도 참고용으로만 제공하세요
- 복구방법과 개선계획을 명확히 구분하여 답변하세요

**중요! 정확한 집계 검증 필수사항:**
- 실제 제공된 문서 수: {total_count}건 (중복 제거 완료)
- 연도별 건수: {dict(sorted(yearly_stats.items()))} (연도별 합계: {yearly_total}{'분' if is_error_time_query else '건'})
- 월별 건수: {monthly_stats} (월별 합계: {monthly_total}{'분' if is_error_time_query else '건'})
- 서비스별 분포: {dict(sorted(service_stats.items(), key=lambda x: x[1], reverse=True)) if service_stats else '정보없음'}
- 장애등급별 분포: {dict(sorted(grade_stats.items(), key=lambda x: int(x[0][0]) if x[0] and x[0][0].isdigit() else 999)) if grade_stats else '정보없음'}
- **답변 시 반드시 실제 문서 수({total_count}건)와 일치해야 함**
- **표시하는 내역 수와 총 건수가 반드시 일치해야 함**
- **불일치 시 반드시 재계산하여 정확한 수치로 답변할 것**
{"- **통계 단위: 장애시간 합산(분)**" if is_error_time_query else "- **통계 단위: 발생 건수**"}

{context}

질문: {final_query}

답변:"""

                if query_type == 'inquiry':
                    max_tokens_initial = 2500
                    temperature = 0.0
                elif query_type == 'cause':
                    max_tokens_initial = 3000
                    temperature = 0.0
                else:
                    max_tokens_initial = 1500
                    temperature = 0.0

                with trace(name="final_response_generation", inputs={"model": self.model_name, "query": final_query, "query_type": query_type}) as final_trace:
                    response = self.azure_openai_client.chat.completions.create(
                        model=self.model_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=temperature,
                        max_tokens=max_tokens_initial
                    )
                    
                    final_answer = response.choices[0].message.content
                    
                    self.safe_trace_update(final_trace, outputs={
                        "response_length": len(final_answer),
                        "tokens_used": response.usage.total_tokens if hasattr(response, 'usage') else None,
                        "query_type": query_type,
                        "max_tokens_used": max_tokens_initial,
                        "custom_sort_applied": sort_info['requires_custom_sort'],
                        "chart_generated": chart_suitable and chart_fig is not None,
                        "is_error_time_query": is_error_time_query,
                        "improved_statistics_used": True
                    })
                
                processing_time = time.time() - start_time
                
                self.safe_trace_update(trace_context,
                    outputs={
                        "response": final_answer,
                        "document_count_processed": total_count,
                        "processing_time": processing_time,
                        "query_type": query_type,
                        "use_llm_validation": use_llm_validation,
                        "improvements_applied": True,
                        "max_tokens_initial": max_tokens_initial,
                        "custom_sort_applied": sort_info['requires_custom_sort'],
                        "chart_generated": chart_suitable and chart_fig is not None,
                        "is_error_time_query": is_error_time_query,
                        "statistics_validation_passed": unified_stats.get('validation', {}).get('is_valid', True)
                    },
                    metadata={
                        "yearly_stats": yearly_stats,
                        "monthly_stats": monthly_stats,
                        "service_stats": service_stats,
                        "time_stats": time_stats,
                        "department_stats": department_stats,
                        "grade_stats": grade_stats,
                        "reprompting_applied": bool(reprompting_info and reprompting_info.get('transformed')),
                        "improvements_applied": ["improved_statistics_calculator", "data_normalization", "validation_system", "negative_keyword_filtering", "confidence_scoring", "enhanced_prompting", "inquiry_optimization", "custom_sorting", "repair_plan_separation", "chart_generation", "error_time_support"],
                        "sort_info": sort_info,
                        "chart_info": chart_info,
                        "unified_stats": unified_stats,
                        "calculation_details": calculation_details
                    }
                )
                
                if chart_info:
                    print("DEBUG: Returning response with chart info")
                    return final_answer, chart_info
                else:
                    print("DEBUG: Returning response without chart")
                    return final_answer
            
            except Exception as e:
                error_msg = f"응답 생성 실패: {str(e)}"
                st.error(error_msg)
                
                self.safe_trace_update(trace_context,
                    outputs={"error": error_msg},
                    metadata={"error_type": type(e).__name__}
                )
                
                return "죄송합니다. 응답을 생성하는 중 오류가 발생했습니다."

    def _display_response_with_marker_conversion(self, response, chart_info=None):
        """현재 답변의 마커를 HTML로 변환하여 표시 - 텍스트 차트 제거"""
        if not response:
            st.write("응답이 없습니다.")
            return
            
        if isinstance(response, tuple):
            response_text, chart_info = response
        else:
            response_text = response
        
        # 차트가 제공될 때 텍스트 차트 제거
        if chart_info and chart_info.get('chart'):
            response_text = self.remove_text_charts_from_response(response_text)
            
        converted_content = response_text
        html_converted = False
        
        if '[REPAIR_BOX_START]' in converted_content and '[REPAIR_BOX_END]' in converted_content:
            converted_content, has_repair_html = self.ui_components.convert_repair_box_to_html(converted_content)
            if has_repair_html:
                html_converted = True
        
        if '[CAUSE_BOX_START]' in converted_content and '[CAUSE_BOX_END]' in converted_content:
            converted_content, has_cause_html = self.ui_components.convert_cause_box_to_html(converted_content)
            if has_cause_html:
                html_converted = True
        
        if html_converted or ('<div style=' in response_text and ('장애원인' in response_text or '복구방법' in response_text)):
            st.markdown(converted_content, unsafe_allow_html=True)
        else:
            st.write(converted_content)
        
        print(f"DEBUG: Chart display check - chart_info exists: {chart_info is not None}")
        if chart_info and chart_info.get('chart'):
            print("DEBUG: Displaying chart")
            st.markdown("---")
            
            try:
                self.chart_manager.display_chart_with_data(
                    chart_info['chart'],
                    chart_info['chart_data'],
                    chart_info['chart_type'],
                    chart_info.get('query', '')
                )
                
                if self.debug_mode:
                    st.success(f"✅ {chart_info['chart_type']} 차트가 성공적으로 생성되었습니다.")
                    
            except Exception as e:
                print(f"DEBUG: Chart display error: {str(e)}")
                st.error(f"차트 표시 중 오류 발생: {str(e)}")
                
                if self.debug_mode:
                    st.write("차트 데이터:", chart_info.get('chart_data', {}))
                    st.write("차트 타입:", chart_info.get('chart_type', 'unknown'))
        
        elif chart_info is None and self.debug_mode:
            print("DEBUG: No chart info available")
            st.info("📊 이 질문에는 차트 생성이 적용되지 않았습니다.")

    @traceable(name="process_user_query")
    def process_query(self, query, query_type=None):
        """개선된 메인 쿼리 처리 - 통계 일관성 검증 강화"""
        
        if not query:
            st.error("질문을 입력해주세요.")
            return
        
        with st.chat_message("assistant"):
            start_time = time.time()
            
            try:
                print(f"DEBUG: Processing query: {query}")
                
                # 쿼리 파싱 결과 상세 로깅 추가
                reprompting_info = self.check_and_transform_query_with_reprompting(query)
                processing_query = reprompting_info.get('transformed_query', query)
                
                # 시간 조건 추출 및 로깅 강화
                time_conditions = self.extract_time_conditions(processing_query)
                print(f"DEBUG: Time conditions extracted: {time_conditions}")
                
                # 월 관련 쿼리인지 특별히 확인
                if '월' in processing_query:
                    print(f"DEBUG: Month-related query detected: '{processing_query}'")
                    # 개별 월 나열 패턴 확인
                    individual_months = re.findall(r'\b(\d{1,2})월\b', processing_query)
                    if len(individual_months) > 1:
                        print(f"DEBUG: Individual months detected: {individual_months}")
                        print(f"DEBUG: This should be treated as month range: {min(individual_months)}~{max(individual_months)}")
                
                department_conditions = self.extract_department_conditions(processing_query)
                
                if query_type is None:
                    with st.spinner("🔍 질문 분석 중..."):
                        query_type = self.classify_query_type_with_llm(processing_query)
                
                print(f"DEBUG: Query type classified as: {query_type}")
                
                target_service_name = self.search_manager.extract_service_name_from_query(processing_query)
                
                with st.spinner("📄 문서 검색 중..."):
                    documents = self.search_manager.semantic_search_with_adaptive_filtering(
                        processing_query, target_service_name, query_type
                    )
                    
                    print(f"DEBUG: Found {len(documents) if documents else 0} documents")
                    
                    # 통계성 질문의 경우 추가 검증 로깅
                    if any(keyword in processing_query.lower() for keyword in ['건수', '통계', '현황', '분포']):
                        print(f"DEBUG: Statistics query detected - ensuring consistency")
                        if documents:
                            # 월별 분포 확인
                            month_dist = {}
                            for doc in documents:
                                month = doc.get('month', '')
                                if month:
                                    month_dist[month] = month_dist.get(month, 0) + 1
                            print(f"DEBUG: Month distribution in results: {month_dist}")
                    
                    if documents is None:
                        documents = []
                    
                    if documents and len(documents) > 0:
                        with st.expander("📄 매칭된 문서 상세 보기"):
                            self.ui_components.display_documents_with_quality_info(documents)
                        
                        with st.spinner("🤖 AI 답변 생성 중..."):
                            response = self.generate_rag_response_with_adaptive_processing(
                                query, documents, query_type, time_conditions, department_conditions, reprompting_info
                            )
                            
                            print(f"DEBUG: Generated response type: {type(response)}")
                            
                            if response is None:
                                response = "죄송합니다. 응답을 생성할 수 없습니다."
                            
                            if isinstance(response, tuple):
                                response_text, chart_info = response
                                print(f"DEBUG: Response includes chart info: {chart_info is not None}")
                                self._display_response_with_marker_conversion(response_text, chart_info)
                                st.session_state.messages.append({"role": "assistant", "content": response_text})
                            else:
                                print("DEBUG: Regular text response")
                                self._display_response_with_marker_conversion(response)
                                st.session_state.messages.append({"role": "assistant", "content": response})
                            
                    else:
                        with st.spinner("📄 추가 검색 중..."):
                            fallback_documents = self.search_manager.search_documents_fallback(processing_query, target_service_name)
                            
                            if fallback_documents and len(fallback_documents) > 0:
                                response = self.generate_rag_response_with_adaptive_processing(
                                    query, fallback_documents, query_type, time_conditions, department_conditions, reprompting_info
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
                                self._show_no_results_message(target_service_name, query_type, time_conditions)
            
            except Exception as e:
                error_msg = f"쿼리 처리 중 오류가 발생했습니다: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
                
                if self.debug_mode:
                    import traceback
                    st.error("상세 오류 정보:")
                    st.code(traceback.format_exc())

    
    def _show_no_results_message(self, target_service_name, query_type, time_conditions=None):
        """검색 결과가 없을 때 개선 방안 제시"""
        time_condition_desc = ""
        if time_conditions and time_conditions.get('is_time_query'):
            time_desc = []
            if time_conditions.get('daynight'):
                time_desc.append(f"시간대: {time_conditions['daynight']}")
            if time_conditions.get('week'):
                time_desc.append(f"요일: {time_conditions['week']}")
            time_condition_desc = f" ({', '.join(time_desc)} 조건)"
        
        error_msg = f"""
        '{target_service_name or '해당 조건'}{time_condition_desc}'에 해당하는 문서를 찾을 수 없습니다.
        
        **🔧 개선 방안:**
        - 서비스명의 일부만 입력해보세요 (예: 'API' 대신 'API_Link')
        - 다른 검색어를 시도해보세요
        - 전체 검색을 원하시면 서비스명을 제외하고 검색해주세요
        - 더 일반적인 키워드를 사용해보세요
        
        **시간 조건 관련 개선 방안:**
        - 시간대 조건을 제거해보세요 (주간/야간)
        - 요일 조건을 제거해보세요
        - 더 넓은 시간 범위로 검색해보세요
        
        **장애등급 관련 개선 방안:**
        - 등급 조건을 제거하고 전체 등급으로 검색해보세요
        - '장애등급' 키워드만으로 검색해보세요
        - 특정 등급 대신 '등급' 키워드만 사용해보세요
        
        **💡 {query_type.upper()} 쿼리 최적화 팁:**
        """
        
        if query_type == 'repair':
            error_msg += """
        - 서비스명과 장애현상을 모두 포함하세요
        - 구체적인 오류 증상을 명시하세요
        - 'incident_repair 필드 기준으로만 복구방법을 제공합니다'
        """
        elif query_type == 'cause':
            error_msg += """
        - '원인', '이유', 'cause' 등의 키워드를 포함하세요
        - 장애 현상을 구체적으로 설명하세요
        """
        elif query_type == 'similar':
            error_msg += """
        - '유사', '비슷한', 'similar' 키워드를 포함하세요
        - 핵심 장애 현상만 간결하게 기술하세요
        """
        else:
            error_msg += """
        - 통계나 현황 조회 시 기간을 명시하세요
        - 구체적인 서비스명이나 조건을 포함하세요
        - '건수', '통계', '현황' 등의 키워드를 활용하세요
        - 시간대별(주간/야간) 또는 요일별 집계도 가능합니다
        
        **복구방법 관련 참고:**
        - 복구방법 질문 시 incident_repair 필드만 사용됩니다
        - 개선계획(incident_plan)은 별도 참고용으로만 제공됩니다
        """
        
        st.write(error_msg)
        st.session_state.messages.append({"role": "assistant", "content": error_msg})