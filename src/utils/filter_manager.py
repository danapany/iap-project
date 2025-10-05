# -*- coding: utf-8 -*-
# filter_manager.py - 통합 필터링 관리 시스템 (챗봇 구조 적용)
"""
통합 필터링 관리 시스템 - 챗봇 구조에 최적화

이 모듈은 모든 문서 필터링을 중앙에서 관리하여 일관된 결과를 보장합니다.
여러 곳에서 발생하던 필터링을 단일 파이프라인으로 통합했습니다.

주요 특징:
- 단일 진실의 원천 (Single Source of Truth)
- 완전한 추적성 (Full Traceability) 
- 통계 쿼리 특별 처리
- 단계별 필터링 파이프라인
- 챗봇 검색 시스템과 완전 통합
"""

import re
import time
from typing import List, Dict, Any, Tuple, Optional, Union
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json


class QueryType(Enum):
    """쿼리 타입 정의"""
    REPAIR = "repair"
    CAUSE = "cause" 
    SIMILAR = "similar"
    INQUIRY = "inquiry"
    STATISTICS = "statistics"
    DEFAULT = "default"


class FilterStage(Enum):
    """필터링 단계 정의"""
    NORMALIZATION = "normalization"
    DEDUPLICATION = "deduplication" 
    CONDITION_FILTERING = "condition_filtering"
    TIME_FILTERING = "time_filtering"
    DEPARTMENT_FILTERING = "department_filtering"
    SERVICE_FILTERING = "service_filtering"
    GRADE_FILTERING = "grade_filtering"
    SEMANTIC_FILTERING = "semantic_filtering"
    KEYWORD_FILTERING = "keyword_filtering"
    NEGATIVE_KEYWORD_FILTERING = "negative_keyword_filtering"
    LLM_VALIDATION = "llm_validation"
    QUALITY_SCORING = "quality_scoring"
    FINAL_SELECTION = "final_selection"


@dataclass
class FilterConditions:
    """필터링 조건을 담는 데이터 클래스 - 챗봇 구조 호환성"""
    # 시간 조건
    year: Optional[str] = None
    month: Optional[str] = None
    start_month: Optional[int] = None
    end_month: Optional[int] = None
    months: Optional[List[int]] = None  # 통합 월 조건
    daynight: Optional[str] = None
    week: Optional[str] = None
    
    # 서비스 조건
    service_name: Optional[str] = None
    target_service_name: Optional[str] = None  # 검색에서 추출된 서비스명
    is_common_service: bool = False
    
    # 조직 조건
    department: Optional[str] = None
    owner_depart: Optional[str] = None
    
    # 장애 등급 조건
    grade: Optional[str] = None
    incident_grade: Optional[str] = None
    specific_grade: Optional[str] = None
    has_grade_query: bool = False
    
    # 쿼리 특성
    query_type: QueryType = QueryType.DEFAULT
    original_query: str = ""
    is_statistics_query: bool = False
    is_range_query: bool = False
    is_error_time_query: bool = False
    is_time_query: bool = False
    is_department_query: bool = False
    
    # 필터링 설정
    should_skip_filtering: bool = False
    enable_deduplication: bool = True
    enable_llm_validation: bool = False
    enable_semantic_boost: bool = True
    enable_negative_keyword_filter: bool = True
    
    # 결과 제한
    max_results: Optional[int] = None
    quality_threshold: float = 0.0
    
    # 키워드
    extracted_keywords: List[str] = field(default_factory=list)
    service_keywords: List[str] = field(default_factory=list)
    symptom_keywords: List[str] = field(default_factory=list)
    
    # 검색 설정 (챗봇 구조와 연동)
    search_threshold: float = 0.20
    reranker_threshold: float = 1.8
    hybrid_threshold: float = 0.35
    semantic_threshold: float = 0.25
    
    def get(self, key: str, default=None):
        """딕셔너리 스타일 get() 메서드"""
        if hasattr(self, key):
            value = getattr(self, key)
            return value if value is not None else default
        return default
    
    def __getitem__(self, key: str):
        """딕셔너리 스타일 [] 접근"""
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(f"'{key}' not found in FilterConditions")
    
    def __setitem__(self, key: str, value):
        """딕셔너리 스타일 [] 할당"""
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            # 동적 속성 추가 허용 (기존 코드 호환성)
            setattr(self, key, value)
    
    def __contains__(self, key: str):
        """딕셔너리 스타일 in 연산자"""
        return hasattr(self, key)
    
    def keys(self):
        """딕셔너리 스타일 keys() 메서드"""
        return [field.name for field in self.__dataclass_fields__]
    
    def values(self):
        """딕셔너리 스타일 values() 메서드"""
        return [getattr(self, field.name) for field in self.__dataclass_fields__]
    
    def items(self):
        """딕셔너리 스타일 items() 메서드"""
        return [(field.name, getattr(self, field.name)) for field in self.__dataclass_fields__]
    
    def to_dict(self):
        """딕셔너리로 변환"""
        result = {}
        for field_info in self.__dataclass_fields__.values():
            value = getattr(self, field_info.name)
            if hasattr(value, 'value'):
                result[field_info.name] = value.value
            elif isinstance(value, list) and value and hasattr(value[0], 'value'):
                result[field_info.name] = [v.value for v in value]
            else:
                result[field_info.name] = value
        return result
    
    @classmethod
    def from_dict(cls, data: dict):
        """딕셔너리에서 FilterConditions 생성"""
        if 'query_type' in data and isinstance(data['query_type'], str):
            try:
                data['query_type'] = QueryType(data['query_type'])
            except ValueError:
                data['query_type'] = QueryType.DEFAULT
        
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class FilterResult:
    """필터링 결과를 담는 데이터 클래스"""
    documents: List[Dict[Any, Any]]
    stage: FilterStage
    original_count: int
    filtered_count: int
    filter_reason: str
    conditions_applied: FilterConditions
    debug_info: Dict[str, Any] = field(default_factory=dict)
    processing_time_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def removed_count(self):
        """제거된 문서 수"""
        return self.original_count - self.filtered_count
    
    @property
    def filter_rate(self):
        """필터링 비율"""
        return self.removed_count / self.original_count if self.original_count > 0 else 0.0


class DocumentNormalizer:
    """문서 정규화 담당 클래스 - 챗봇 구조 최적화"""
    
    @staticmethod
    def normalize_error_time(error_time):
        """error_time 필드 정규화"""
        if error_time is None:
            return 0
        
        try:
            if isinstance(error_time, str):
                error_time = error_time.strip()
                if error_time == '' or error_time.lower() in ['null', 'none', 'n/a', '']:
                    return 0
                return int(float(error_time))
            
            return int(error_time)
            
        except (ValueError, TypeError):
            return 0
    
    @staticmethod
    def normalize_date_fields(doc):
        """날짜 관련 필드 정규화 - 챗봇 구조 맞춤"""
        normalized_doc = doc.copy()
        
        # error_date 필드 처리
        error_date = doc.get('error_date', '')
        if error_date:
            try:
                error_date_str = str(error_date).strip()
                
                # YYYY-MM-DD 형식
                if '-' in error_date_str and len(error_date_str) >= 7:
                    parts = error_date_str.split('-')
                    if len(parts) >= 2:
                        if parts[0].isdigit() and len(parts[0]) == 4:
                            normalized_doc['extracted_year'] = parts[0]
                            if not normalized_doc.get('year'):
                                normalized_doc['year'] = parts[0]
                        
                        if parts[1].isdigit():
                            month_num = int(parts[1])
                            if 1 <= month_num <= 12:
                                normalized_doc['extracted_month'] = str(month_num)
                                if not normalized_doc.get('month'):
                                    normalized_doc['month'] = str(month_num)
                
                # YYYYMMDD 형식
                elif len(error_date_str) >= 8 and error_date_str.isdigit():
                    normalized_doc['extracted_year'] = error_date_str[:4]
                    if not normalized_doc.get('year'):
                        normalized_doc['year'] = error_date_str[:4]
                    
                    month_str = error_date_str[4:6]
                    try:
                        month_num = int(month_str)
                        if 1 <= month_num <= 12:
                            normalized_doc['extracted_month'] = str(month_num)
                            if not normalized_doc.get('month'):
                                normalized_doc['month'] = str(month_num)
                    except (ValueError, TypeError):
                        pass
                
                # YYYY 형식
                elif len(error_date_str) >= 4 and error_date_str[:4].isdigit():
                    normalized_doc['extracted_year'] = error_date_str[:4]
                    if not normalized_doc.get('year'):
                        normalized_doc['year'] = error_date_str[:4]
                        
            except (ValueError, TypeError):
                pass
        
        return normalized_doc
    
    @staticmethod
    def normalize_string_fields(doc):
        """문자열 필드들 정규화"""
        normalized_doc = doc.copy()
        
        string_fields = [
            'service_name', 'incident_grade', 'owner_depart', 
            'daynight', 'week', 'symptom', 'root_cause', 
            'incident_repair', 'incident_plan', 'effect',
            'cause_type', 'done_type'
        ]
        
        for field in string_fields:
            value = normalized_doc.get(field)
            if value is not None:
                normalized_doc[field] = str(value).strip()
            else:
                normalized_doc[field] = ''
        
        return normalized_doc
    
    @classmethod
    def normalize_document(cls, doc):
        """문서 전체 정규화"""
        if doc is None:
            return None
        
        normalized_doc = cls.normalize_date_fields(doc)
        normalized_doc['error_time'] = cls.normalize_error_time(doc.get('error_time'))
        normalized_doc = cls.normalize_string_fields(normalized_doc)
        
        # 정규화 메타데이터 추가
        normalized_doc['_normalized'] = True
        normalized_doc['_normalized_timestamp'] = datetime.now().isoformat()
        
        return normalized_doc


class ConditionExtractor:
    """조건 추출 담당 클래스 - 챗봇 구조 연동"""
    
    STATS_KEYWORDS = [
        '건수', '통계', '내역', '월별', '연도별', '현황', '분석', '요약', 
        '일별', '개수', '분포', '합계', '합산', '총', '전체', '현재'
    ]
    
    ERROR_TIME_KEYWORDS = [
        '장애시간', '장애 시간', 'error_time', '시간 통계', '시간 합계', 
        '시간 합산', '분', '시간', '걸린', '소요'
    ]
    
    COMMON_TERM_SERVICES = {
        'OTP': ['otp', '일회용비밀번호', '원타임패스워드', '2차인증', '이중인증'],           
        '본인인증': ['실명인증', '신원확인'],
        'API': ['api', 'Application Programming Interface', 'REST API', 'API호출'],
        'SMS': ['sms', '문자', '단문', 'Short Message Service', '문자메시지'],
        'VPN': ['vpn', 'Virtual Private Network', '가상사설망'],
        'DNS': ['dns', 'Domain Name System', '도메인네임시스템'],
        'SSL': ['ssl', 'https', 'Secure Sockets Layer', '보안소켓계층'],
        'URL': ['url', 'link', '링크', 'Uniform Resource Locator']
    }
    
    @classmethod
    def extract_all_conditions(cls, query: str, query_type: QueryType, search_manager=None) -> FilterConditions:
        """쿼리에서 모든 필터링 조건을 한번에 추출 - 챗봇 구조 통합"""
        conditions = FilterConditions()
        
        if not query:
            return conditions
        
        query_lower = query.lower()
        conditions.original_query = query
        conditions.query_type = query_type
        
        # 통계 쿼리 판단
        conditions.is_statistics_query = any(
            keyword in query_lower for keyword in cls.STATS_KEYWORDS
        )
        
        # 에러 타임 쿼리 판단
        conditions.is_error_time_query = any(
            keyword in query_lower for keyword in cls.ERROR_TIME_KEYWORDS
        )
        
        # 키워드 추출
        conditions.extracted_keywords = cls._extract_keywords(query_lower)
        
        # 시간 조건 추출
        cls._extract_time_conditions(query_lower, conditions)
        
        # 서비스 조건 추출 (search_manager 연동)
        cls._extract_service_conditions(query_lower, conditions, search_manager)
        
        # 장애 등급 조건 추출
        cls._extract_grade_conditions(query_lower, conditions)
        
        # 부서 조건 추출
        cls._extract_department_conditions(query_lower, conditions)
        
        # 필터링 설정 결정
        cls._determine_filtering_settings(conditions)
        
        return conditions
    
    @classmethod
    def _extract_keywords(cls, query_lower: str) -> List[str]:
        """키워드 추출"""
        keyword_patterns = [
            r'\b([가-힣]{2,10})\b',
            r'\b([A-Za-z]{2,20})\b',
            r'\b(\d+등급)\b',
        ]
        
        keywords = []
        for pattern in keyword_patterns:
            matches = re.findall(pattern, query_lower)
            keywords.extend(matches)
        
        # 불용어 제거
        stop_words = [
            '장애', '현상', '원인', '복구', '통계', '건수', '내역', '알려줘', 
            '가르쳐', '보여줘', '확인', '검색', '찾아줘'
        ]
        
        filtered_keywords = [kw for kw in keywords if kw not in stop_words]
        return list(set(filtered_keywords))
    
    @classmethod 
    def _extract_time_conditions(cls, query_lower: str, conditions: FilterConditions):
        """시간 관련 조건 추출 - 통합 월 처리 - 명확한 경우에만 추출"""
        # 연도 추출
        year_match = re.search(r'\b(202[0-9]|201[0-9])\b', query_lower)
        if year_match:
            conditions.year = year_match.group(1)
        
        # ⭐ 통계 쿼리가 아니면 월 조건 자동 추출 중단
        stats_keywords = ['건수', '통계', '현황', '분포', '몇건', '개수', '~별', '년도별', '월별', '연도별']
        if not any(k in query_lower for k in stats_keywords):
            return  # 통계 쿼리가 아니면 월 조건 추출하지 않음
        
        # 월 범위 추출 (통계 쿼리인 경우에만)
        months_set = set()
        
        # 월 범위 패턴
        month_range_patterns = [
            r'\b(\d+)\s*~\s*(\d+)월\b',
            r'\b(\d+)월\s*~\s*(\d+)월\b',  
            r'\b(\d+)\s*-\s*(\d+)월\b',
            r'\b(\d+)월\s*-\s*(\d+)월\b',
            r'\b(\d+)\s*부터\s*(\d+)월\b',
            r'\b(\d+)월부터\s*(\d+)월\b'
        ]
        
        for pattern in month_range_patterns:
            match = re.search(pattern, query_lower)
            if match:
                start_month = int(match.group(1))
                end_month = int(match.group(2))
                if 1 <= start_month <= 12 and 1 <= end_month <= 12 and start_month <= end_month:
                    months_set.update(range(start_month, end_month + 1))
                    conditions.start_month = start_month
                    conditions.end_month = end_month
                    conditions.is_range_query = True
                    break
        
        # 개별 월 추출
        individual_months = re.findall(r'\b(\d{1,2})월\b', query_lower)
        for month_str in individual_months:
            month_num = int(month_str)
            if 1 <= month_num <= 12:
                months_set.add(month_num)
                if not conditions.is_range_query:
                    conditions.month = str(month_num)
        
        # 통합 월 목록 설정
        if months_set:
            conditions.months = sorted(list(months_set))
        
        # 시간대 추출
        daynight_patterns = {
            '야간': ['야간', '밤', '심야', '새벽', '야간시간'],
            '주간': ['주간', '낮', '오전', '오후', '낮시간', '일과시간', '업무시간']
        }
        
        for daynight_key, patterns in daynight_patterns.items():
            if any(pattern in query_lower for pattern in patterns):
                conditions.daynight = daynight_key
                conditions.is_time_query = True
                break
        
        # 요일 추출
        week_patterns = {
            '월': ['월요일', '월'], '화': ['화요일', '화'], '수': ['수요일', '수'],
            '목': ['목요일', '목'], '금': ['금요일', '금'], '토': ['토요일', '토'], 
            '일': ['일요일', '일']
        }
        
        for week_key, patterns in week_patterns.items():
            if any(pattern in query_lower for pattern in patterns):
                conditions.week = week_key
                conditions.is_time_query = True
                break
        
        if any(word in query_lower for word in ['평일', '주중']):
            conditions.week = '평일'
            conditions.is_time_query = True
        elif any(word in query_lower for word in ['주말', '토일', '휴일']):
            conditions.week = '주말'
            conditions.is_time_query = True
    
    @classmethod
    def _extract_service_conditions(cls, query_lower: str, conditions: FilterConditions, search_manager=None):
        """서비스 및 조직 관련 조건 추출 - 챗봇 search_manager 연동"""
        
        # 일반 용어 서비스 우선 체크
        for service_name, aliases in cls.COMMON_TERM_SERVICES.items():
            if any(alias in query_lower for alias in [service_name.lower()] + [a.lower() for a in aliases]):
                conditions.service_name = service_name
                conditions.target_service_name = service_name
                conditions.is_common_service = True
                break
        
        # search_manager를 통한 서비스명 추출 (있는 경우)
        if not conditions.service_name and search_manager:
            try:
                extracted_service = search_manager.extract_service_name_from_query(conditions.original_query)
                if extracted_service:
                    conditions.service_name = extracted_service
                    conditions.target_service_name = extracted_service
                    # 일반 용어인지 다시 확인
                    conditions.is_common_service = any(
                        extracted_service.lower() == service.lower() 
                        for service in cls.COMMON_TERM_SERVICES.keys()
                    )
            except Exception:
                pass
        
        # 패턴 기반 서비스명 추출 (fallback)
        if not conditions.service_name:
            service_patterns = [
                r'\b([A-Za-z][A-Za-z0-9_\-/\+\(\)]{1,20})\s+(?:장애|현상|서비스|시스템|오류|문제)',
                r'서비스\s*[:\：]?\s*([A-Za-z][A-Za-z0-9_\-/\+\(\)]{1,20})',
                r'\b([가-힣]{2,10})\s+(?:서비스|시스템|장애|현상)',
                r'^([A-Za-z][A-Za-z0-9_\-/\+\(\)]{2,20})\s+',
            ]
            
            for pattern in service_patterns:
                matches = re.findall(pattern, query_lower, re.IGNORECASE)
                if matches:
                    service_name = matches[0].strip()
                    if cls._is_valid_service_name(service_name):
                        conditions.service_name = service_name
                        conditions.target_service_name = service_name
                        break
        
        # 등급 추출
        grade_match = re.search(r'(\d+)등급', query_lower)
        if grade_match:
            conditions.grade = f"{grade_match.group(1)}등급"
    
    @classmethod
    def _extract_grade_conditions(cls, query_lower: str, conditions: FilterConditions):
        """장애 등급 조건 추출"""
        # 일반 등급 키워드
        grade_general_keywords = ['등급', '장애등급', '전파등급', 'grade', '심각도']
        if any(k in query_lower for k in grade_general_keywords):
            conditions.has_grade_query = True
        
        # 구체적인 등급 추출
        for pattern in [r'(\d+)등급', r'(\d+)급', r'(\d+)grade', r'등급.*?(\d+)', r'(\d+).*?등급']:
            if matches := re.findall(pattern, query_lower):
                conditions.specific_grade = f"{matches[0]}등급"
                conditions.grade = conditions.specific_grade
                conditions.incident_grade = conditions.specific_grade
                conditions.has_grade_query = True
                break
    
    @classmethod
    def _extract_department_conditions(cls, query_lower: str, conditions: FilterConditions):
        """부서 조건 추출"""
        dept_keywords = ['담당부서', '처리부서', '관리부서', '부서', '팀', '담당', '처리']
        if any(keyword in query_lower for keyword in dept_keywords):
            conditions.is_department_query = True
            
            dept_patterns = [
                r'\b(개발|운영|기술|시스템|네트워크|보안|DB|데이터베이스|인프라|플랫폼)(?:부서|팀|조)?\b',
                r'\b([가-힣]+)(?:부서|팀|조)\b',
                r'([가-힣]+)\s*담당',
                r'([가-힣]+)\s*처리'
            ]
            
            for pattern in dept_patterns:
                matches = re.findall(pattern, query_lower)
                if matches:
                    conditions.department = matches[0]
                    conditions.owner_depart = matches[0]
                    break
    
    @classmethod
    def _is_valid_service_name(cls, service_name: str) -> bool:
        """서비스명 유효성 검증"""
        if len(service_name) < 2:
            return False
        
        excluded_words = [
            'service', 'system', 'server', 'client', 'application', 'app',
            'website', 'web', 'platform', 'portal', 'interface', 'api',
            'database', 'data', 'file', 'log', 'error', 'issue', 'problem',
            'http', 'https', 'www', 'com', 'org', 'net',
            '장애', '현상', '복구', '통계', '발생', '서비스', '시스템'
        ]
        
        clean_name = re.sub(r'[\(\)/\+_\-\s]', '', service_name).lower()
        return clean_name not in excluded_words
    
    @classmethod
    def _determine_filtering_settings(cls, conditions: FilterConditions):
        """필터링 설정 결정"""
        
        # 구체적인 조건이 있는지 확인
        has_specific_conditions = any([
            conditions.year, 
            conditions.month, 
            conditions.months,
            conditions.start_month, 
            conditions.end_month,
            conditions.daynight, 
            conditions.week, 
            conditions.grade, 
            conditions.department,
            conditions.service_name
        ])
        
        # 필터링 건너뛸지 결정
        conditions.should_skip_filtering = (
            conditions.is_statistics_query and not has_specific_conditions
        )
        
        # LLM 검증 활성화
        conditions.enable_llm_validation = conditions.query_type in [
            QueryType.REPAIR, QueryType.CAUSE
        ]
        
        # 중복 제거 활성화
        conditions.enable_deduplication = not conditions.is_statistics_query
        
        # 의미적 부스팅 활성화
        conditions.enable_semantic_boost = conditions.query_type in [
            QueryType.SIMILAR, QueryType.DEFAULT
        ]
        
        # 네거티브 키워드 필터링 활성화
        conditions.enable_negative_keyword_filter = conditions.query_type in [
            QueryType.REPAIR, QueryType.CAUSE, QueryType.SIMILAR
        ]


class DocumentValidator:
    """문서 검증 담당 클래스 - 챗봇 구조 연동"""
    
    @staticmethod
    def validate_document_conditions(doc: Dict[Any, Any], conditions: FilterConditions) -> Tuple[bool, str]:
        """문서가 조건에 부합하는지 검증"""
        
        incident_id = doc.get('incident_id', 'N/A')
        
        # 연도 검증
        if conditions.year:
            doc_year = DocumentValidator._extract_year(doc)
            if not doc_year or doc_year != conditions.year:
                return False, f"year_mismatch_expected_{conditions.year}_got_{doc_year}"
        
        # 월 검증 (통합 처리)
        if conditions.months:
            doc_month = DocumentValidator._extract_month(doc)
            if not doc_month:
                return False, "no_month_info"
            try:
                month_num = int(doc_month)
                if month_num not in conditions.months:
                    return False, f"month_not_in_list_{conditions.months}_got_{month_num}"
            except (ValueError, TypeError):
                return False, f"invalid_month_format_{doc_month}"
        
        elif conditions.start_month and conditions.end_month:
            doc_month = DocumentValidator._extract_month(doc)
            if not doc_month:
                return False, "no_month_info"
            try:
                month_num = int(doc_month)
                if not (conditions.start_month <= month_num <= conditions.end_month):
                    return False, f"month_out_of_range_{conditions.start_month}_{conditions.end_month}_got_{month_num}"
            except (ValueError, TypeError):
                return False, f"invalid_month_format_{doc_month}"
        
        elif conditions.month:
            doc_month = DocumentValidator._extract_month(doc)
            if not doc_month or str(doc_month) != conditions.month:
                return False, f"month_mismatch_expected_{conditions.month}_got_{doc_month}"
        
        # 시간대 검증
        if conditions.daynight:
            doc_daynight = doc.get('daynight', '').strip()
            if not doc_daynight or doc_daynight != conditions.daynight:
                return False, f"daynight_mismatch_expected_{conditions.daynight}_got_{doc_daynight}"
        
        # 요일 검증
        if conditions.week:
            doc_week = doc.get('week', '').strip()
            
            if conditions.week == '평일':
                if doc_week not in ['월', '화', '수', '목', '금']:
                    return False, f"not_weekday_got_{doc_week}"
            elif conditions.week == '주말':
                if doc_week not in ['토', '일']:
                    return False, f"not_weekend_got_{doc_week}"
            else:
                if not doc_week or doc_week != conditions.week:
                    return False, f"week_mismatch_expected_{conditions.week}_got_{doc_week}"
        
        # 등급 검증
        if conditions.grade:
            doc_grade = doc.get('incident_grade', '').strip()
            if doc_grade != conditions.grade:
                return False, f"grade_mismatch_expected_{conditions.grade}_got_{doc_grade}"
        
        # 부서 검증
        if conditions.department:
            doc_dept = doc.get('owner_depart', '').strip()
            if not doc_dept or conditions.department not in doc_dept:
                return False, f"department_mismatch_expected_{conditions.department}_got_{doc_dept}"
        
        # 서비스명 검증
        if conditions.service_name:
            doc_service = doc.get('service_name', '').strip()
            
            if conditions.is_common_service:
                # 일반 용어는 정확히 일치해야 함
                if doc_service.lower() != conditions.service_name.lower():
                    return False, f"service_exact_mismatch_expected_{conditions.service_name}_got_{doc_service}"
            else:
                # 일반 서비스는 부분 일치 허용
                service_match = (
                    conditions.service_name.lower() in doc_service.lower() or
                    doc_service.lower() in conditions.service_name.lower() or
                    conditions.service_name.lower() == doc_service.lower()
                )
                if not service_match:
                    return False, f"service_mismatch_expected_{conditions.service_name}_got_{doc_service}"
        
        return True, "passed_all_conditions"
    
    @staticmethod
    def _extract_year(doc: Dict[Any, Any]) -> Optional[str]:
        """문서에서 연도 추출"""
        # year 필드 우선
        year = doc.get('year')
        if year:
            year_str = str(year).strip()
            if len(year_str) == 4 and year_str.isdigit():
                return year_str
        
        # extracted_year 필드
        year = doc.get('extracted_year')
        if year:
            year_str = str(year).strip()
            if len(year_str) == 4 and year_str.isdigit():
                return year_str
        
        # error_date에서 추출
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
    
    @staticmethod
    def _extract_month(doc: Dict[Any, Any]) -> Optional[str]:
        """문서에서 월 추출"""
        # month 필드 우선
        month = doc.get('month')
        if month:
            try:
                month_num = int(month)
                if 1 <= month_num <= 12:
                    return str(month_num)
            except (ValueError, TypeError):
                pass
        
        # extracted_month 필드
        month = doc.get('extracted_month')
        if month:
            try:
                month_num = int(month)
                if 1 <= month_num <= 12:
                    return str(month_num)
            except (ValueError, TypeError):
                pass
        
        # error_date에서 추출
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


class DocumentFilterManager:
    """통합 문서 필터링 관리자 - 챗봇 구조 완전 통합"""
    
    def __init__(self, debug_mode: bool = False, search_manager=None, config=None):
        self.debug_mode = debug_mode
        self.search_manager = search_manager
        self.config = config
        self.filter_history: List[FilterResult] = []
        self.normalizer = DocumentNormalizer()
        self.condition_extractor = ConditionExtractor()
        self.validator = DocumentValidator()
        
        # 네거티브 키워드 정의
        self.negative_keywords = {
            QueryType.REPAIR: {
                'strong': ['통계', '건수', '현황', '분석', '몇건', '개수', '총', '전체'],
                'weak': ['연도별', '월별', '시간대별', '요일별']
            },
            QueryType.CAUSE: {
                'strong': ['복구방법', '해결방법', '조치방법', '대응방법'],
                'weak': ['통계', '건수', '현황', '분석']
            },
            QueryType.SIMILAR: {
                'strong': ['건수', '통계', '현황', '분석', '개수', '총'],
                'weak': ['연도별', '월별', '시간대별']
            },
            QueryType.DEFAULT: {'strong': [], 'weak': []},
            QueryType.INQUIRY: {'strong': [], 'weak': []},
            QueryType.STATISTICS: {'strong': [], 'weak': []}
        }
        
    def extract_all_conditions(self, query: str, query_type: QueryType) -> FilterConditions:
        """조건 추출 위임 - search_manager 연동"""
        return self.condition_extractor.extract_all_conditions(query, query_type, self.search_manager)
    
    def apply_comprehensive_filtering(
        self, 
        documents: List[Dict[Any, Any]], 
        query: str, 
        query_type: QueryType,
        enable_llm_validation: bool = False,
        conditions: FilterConditions = None
    ) -> Tuple[List[Dict[Any, Any]], List[FilterResult]]:
        """통합 필터링 파이프라인 실행 - 챗봇 구조 최적화"""
        
        start_time = time.time()
        self.filter_history.clear()
        
        if not documents:
            return [], self.filter_history
        
        current_docs = documents[:]
        
        # 조건 추출 (전달받은 조건이 있으면 사용)
        if conditions is None:
            conditions = self.extract_all_conditions(query, query_type)
        
        if enable_llm_validation:
            conditions.enable_llm_validation = True
        
        if self.debug_mode:
            print(f"DEBUG: === COMPREHENSIVE FILTERING PIPELINE START ===")
            print(f"DEBUG: Query: '{query}'")
            print(f"DEBUG: Query Type: {query_type.value}")
            print(f"DEBUG: Initial Count: {len(current_docs)}")
            print(f"DEBUG: Conditions: {self._format_conditions(conditions)}")
            print(f"DEBUG: Skip Filtering: {conditions.should_skip_filtering}")
        
        try:
            # 1단계: 문서 정규화
            current_docs = self._apply_normalization(current_docs, conditions)
            
            # 2단계: 중복 제거
            current_docs = self._apply_deduplication(current_docs, conditions)
            
            # 3단계: 조건 필터링
            if conditions.should_skip_filtering:
                self._record_skip_filtering(current_docs, conditions)
            else:
                current_docs = self._apply_condition_filtering(current_docs, conditions)
            
            # 4단계: 서비스 필터링
            current_docs = self._apply_service_filtering(current_docs, conditions)
            
            # 5단계: 장애 등급 필터링
            current_docs = self._apply_grade_filtering(current_docs, conditions)
            
            # 6단계: 의미적 유사성 부스팅
            if conditions.enable_semantic_boost:
                current_docs = self._apply_semantic_filtering(current_docs, conditions)
            
            # 7단계: 키워드 관련성 채점
            current_docs = self._apply_keyword_filtering(current_docs, conditions)
            
            # 8단계: 네거티브 키워드 필터링
            if conditions.enable_negative_keyword_filter:
                current_docs = self._apply_negative_keyword_filtering(current_docs, conditions)
            
            # 9단계: LLM 검증 (활성화된 경우)
            if conditions.enable_llm_validation and current_docs:
                current_docs = self._apply_llm_validation(current_docs, query, conditions)
            
            # 10단계: 품질 점수 계산
            current_docs = self._apply_quality_scoring(current_docs, conditions)
            
            # 11단계: 최종 선택
            current_docs = self._apply_final_selection(current_docs, conditions)
            
            total_time = (time.time() - start_time) * 1000
            
            if self.debug_mode:
                print(f"DEBUG: === COMPREHENSIVE FILTERING PIPELINE END ===")
                print(f"DEBUG: Final Count: {len(current_docs)}")
                print(f"DEBUG: Total Processing Time: {total_time:.2f}ms")
                self._print_detailed_summary()
            
        except Exception as e:
            if self.debug_mode:
                print(f"DEBUG: Error in filtering pipeline: {str(e)}")
            current_docs = documents[:]
            self._record_error("pipeline_error", str(e), current_docs, conditions)
        
        return current_docs, self.filter_history
    
    def _apply_normalization(self, documents: List[Dict[Any, Any]], conditions: FilterConditions) -> List[Dict[Any, Any]]:
        """1단계: 문서 정규화"""
        start_time = time.time()
        normalized_docs = []
        
        for doc in documents:
            if doc is None:
                continue
            try:
                normalized_doc = self.normalizer.normalize_document(doc)
                if normalized_doc:
                    normalized_docs.append(normalized_doc)
            except Exception as e:
                if self.debug_mode:
                    print(f"DEBUG: Normalization error for doc {doc.get('incident_id', 'N/A')}: {str(e)}")
                normalized_docs.append(doc)
        
        processing_time = (time.time() - start_time) * 1000
        
        self._record_filter_result(
            normalized_docs, FilterStage.NORMALIZATION, len(documents), len(normalized_docs),
            f"Document normalization completed", conditions,
            {'processing_time_ms': processing_time, 'errors': len(documents) - len(normalized_docs)},
            processing_time
        )
        
        return normalized_docs
    
    def _apply_deduplication(self, documents: List[Dict[Any, Any]], conditions: FilterConditions) -> List[Dict[Any, Any]]:
        """2단계: 중복 제거"""
        start_time = time.time()
        
        if not conditions.enable_deduplication:
            processing_time = (time.time() - start_time) * 1000
            self._record_filter_result(
                documents, FilterStage.DEDUPLICATION, len(documents), len(documents),
                "Statistics query - deduplication skipped for accurate count", conditions,
                {'reason': 'statistics_query'}, processing_time
            )
            return documents
        
        unique_docs = {}
        duplicate_count = 0
        
        for doc in documents:
            incident_id = doc.get('incident_id', '')
            if incident_id:
                if incident_id not in unique_docs:
                    unique_docs[incident_id] = doc
                else:
                    duplicate_count += 1
            else:
                temp_id = f"temp_{len(unique_docs)}"
                unique_docs[temp_id] = doc
        
        deduped_docs = list(unique_docs.values())
        processing_time = (time.time() - start_time) * 1000
        
        self._record_filter_result(
            deduped_docs, FilterStage.DEDUPLICATION, len(documents), len(deduped_docs),
            f"Removed {duplicate_count} duplicate documents", conditions,
            {'duplicates_removed': duplicate_count}, processing_time
        )
        
        return deduped_docs
    
    def _apply_condition_filtering(self, documents: List[Dict[Any, Any]], conditions: FilterConditions) -> List[Dict[Any, Any]]:
        """3단계: 조건 기반 필터링 - 조건이 명확한 경우에만 적용"""
        start_time = time.time()
        
        # ⭐ 조건이 하나도 없으면 모든 문서 통과
        has_any_condition = any([
            conditions.year,
            conditions.month,
            conditions.months,
            conditions.start_month,
            conditions.end_month,
            conditions.daynight,
            conditions.week,
            conditions.service_name,
            conditions.department,
            conditions.grade
        ])
        
        if not has_any_condition:
            processing_time = (time.time() - start_time) * 1000
            self._record_filter_result(
                documents, FilterStage.CONDITION_FILTERING, len(documents), len(documents),
                "No specific conditions - all documents passed", conditions,
                {'reason': 'no_conditions'}, processing_time
            )
            return documents
        
        # ⭐ 통계 쿼리이고 특정 조건이 없으면 모든 문서 통과
        if conditions.should_skip_filtering:
            processing_time = (time.time() - start_time) * 1000
            self._record_filter_result(
                documents, FilterStage.CONDITION_FILTERING, len(documents), len(documents),
                "Statistics query without specific conditions - skipped", conditions,
                {'reason': 'statistics_no_conditions'}, processing_time
            )
            return documents
        
        filtered_docs = []
        filter_reasons = {}
        
        for doc in documents:
            try:
                is_valid, reason = self.validator.validate_document_conditions(doc, conditions)
                
                if is_valid:
                    filtered_docs.append(doc)
                else:
                    filter_reasons[reason] = filter_reasons.get(reason, 0) + 1
                    if self.debug_mode:
                        incident_id = doc.get('incident_id', 'N/A')
                        print(f"DEBUG: Filtered out {incident_id}: {reason}")
            except Exception as e:
                if self.debug_mode:
                    print(f"DEBUG: Error validating document {doc.get('incident_id', 'N/A')}: {str(e)}")
                # ⭐ 오류 발생 시 문서 포함 (제외하지 않음)
                filtered_docs.append(doc)
        
        # ⭐ 필터링 결과가 0건이면 경고하고 원본 반환
        if len(filtered_docs) == 0 and len(documents) > 0:
            print(f"WARNING: All documents filtered out! Returning original documents.")
            print(f"WARNING: Filter reasons: {filter_reasons}")
            processing_time = (time.time() - start_time) * 1000
            self._record_filter_result(
                documents, FilterStage.CONDITION_FILTERING, len(documents), len(documents),
                f"All documents filtered - returning original ({filter_reasons})", conditions,
                {'filter_reasons': dict(filter_reasons), 'warning': 'all_filtered'}, processing_time
            )
            return documents
        
        processing_time = (time.time() - start_time) * 1000
        reason_summary = f"Applied condition filters" + (f": {dict(filter_reasons)}" if filter_reasons else " - all documents passed")
        
        self._record_filter_result(
            filtered_docs, FilterStage.CONDITION_FILTERING, len(documents), len(filtered_docs),
            reason_summary, conditions, 
            {'filter_reasons': dict(filter_reasons), 'conditions_checked': self._get_active_conditions(conditions)},
            processing_time
        )
        
        return filtered_docs
    
    def _apply_service_filtering(self, documents: List[Dict[Any, Any]], conditions: FilterConditions) -> List[Dict[Any, Any]]:
        """4단계: 서비스명 기반 필터링"""
        start_time = time.time()
        
        if not conditions.service_name:
            processing_time = (time.time() - start_time) * 1000
            self._record_filter_result(
                documents, FilterStage.SERVICE_FILTERING, len(documents), len(documents),
                "No service name condition - skipped", conditions, {}, processing_time
            )
            return documents
        
        filtered_docs = []
        match_types = {'exact': 0, 'partial': 0, 'keyword': 0}
        
        for doc in documents:
            doc_service = doc.get('service_name', '').strip()
            service_match = False
            match_type = 'none'
            
            if conditions.is_common_service:
                # 일반 용어는 정확한 일치만 허용
                if conditions.service_name.lower() == doc_service.lower():
                    service_match = True
                    match_type = 'exact'
            else:
                # 일반 서비스는 유연한 매칭
                if conditions.service_name.lower() == doc_service.lower():
                    service_match = True
                    match_type = 'exact'
                elif (conditions.service_name.lower() in doc_service.lower() or 
                      doc_service.lower() in conditions.service_name.lower()):
                    service_match = True
                    match_type = 'partial'
                else:
                    # 텍스트 필드에서 키워드 검색
                    text_fields = ['symptom', 'effect', 'root_cause', 'incident_repair']
                    combined_text = ' '.join([doc.get(field, '') for field in text_fields]).lower()
                    if conditions.service_name.lower() in combined_text:
                        service_match = True
                        match_type = 'keyword'
            
            if service_match:
                doc['service_match_type'] = match_type
                filtered_docs.append(doc)
                match_types[match_type] += 1
        
        processing_time = (time.time() - start_time) * 1000
        
        self._record_filter_result(
            filtered_docs, FilterStage.SERVICE_FILTERING, len(documents), len(filtered_docs),
            f"Service filtering for '{conditions.service_name}' completed", conditions,
            {'service_name': conditions.service_name, 'match_types': match_types, 'is_common_service': conditions.is_common_service}, processing_time
        )
        
        return filtered_docs
    
    def _apply_grade_filtering(self, documents: List[Dict[Any, Any]], conditions: FilterConditions) -> List[Dict[Any, Any]]:
        """5단계: 장애 등급 필터링"""
        start_time = time.time()
        
        if not conditions.has_grade_query:
            processing_time = (time.time() - start_time) * 1000
            self._record_filter_result(
                documents, FilterStage.GRADE_FILTERING, len(documents), len(documents),
                "No grade condition - skipped", conditions, {}, processing_time
            )
            return documents
        
        filtered_docs = []
        grade_matches = {'exact': 0, 'general': 0}
        
        for doc in documents:
            doc_grade = doc.get('incident_grade', '').strip()
            
            if conditions.specific_grade:
                # 구체적인 등급 지정된 경우
                if doc_grade == conditions.specific_grade:
                    doc['grade_match_type'] = 'exact'
                    filtered_docs.append(doc)
                    grade_matches['exact'] += 1
            elif doc_grade:
                # 일반적인 등급 쿼리
                doc['grade_match_type'] = 'general'
                filtered_docs.append(doc)
                grade_matches['general'] += 1
        
        # 등급 순서로 정렬 (1등급이 가장 중요)
        grade_order = {'1등급': 1, '2등급': 2, '3등급': 3, '4등급': 4}
        filtered_docs.sort(key=lambda d: next((v for k, v in grade_order.items() if k in d.get('incident_grade', '')), 999))
        
        processing_time = (time.time() - start_time) * 1000
        
        self._record_filter_result(
            filtered_docs, FilterStage.GRADE_FILTERING, len(documents), len(filtered_docs),
            f"Grade filtering completed", conditions,
            {'specific_grade': conditions.specific_grade, 'grade_matches': grade_matches}, processing_time
        )
        
        return filtered_docs
    
    def _apply_semantic_filtering(self, documents: List[Dict[Any, Any]], conditions: FilterConditions) -> List[Dict[Any, Any]]:
        """6단계: 의미적 유사성 부스팅 (search_manager 연동)"""
        start_time = time.time()
        
        # search_manager의 의미적 부스팅 활용
        if self.search_manager and hasattr(self.search_manager, '_boost_semantic_documents'):
            try:
                boosted_docs = self.search_manager._boost_semantic_documents(documents, conditions.original_query)
            except Exception as e:
                if self.debug_mode:
                    print(f"DEBUG: Semantic boosting error: {e}")
                boosted_docs = documents
        else:
            boosted_docs = documents
        
        processing_time = (time.time() - start_time) * 1000
        
        semantic_count = len([doc for doc in boosted_docs if doc.get('semantic_similarity', 0) > 0])
        
        self._record_filter_result(
            boosted_docs, FilterStage.SEMANTIC_FILTERING, len(documents), len(boosted_docs),
            f"Semantic similarity boosting applied", conditions,
            {'semantically_boosted': semantic_count}, processing_time
        )
        
        return boosted_docs
    
    def _apply_keyword_filtering(self, documents: List[Dict[Any, Any]], conditions: FilterConditions) -> List[Dict[Any, Any]]:
        """7단계: 키워드 관련성 채점 (search_manager 연동)"""
        start_time = time.time()
        
        # search_manager의 키워드 관련성 스코어링 활용
        if self.search_manager and hasattr(self.search_manager, 'calculate_keyword_relevance_score'):
            try:
                for doc in documents:
                    keyword_score = self.search_manager.calculate_keyword_relevance_score(conditions.original_query, doc)
                    if keyword_score > 0:
                        doc['keyword_relevance_score'] = keyword_score
                        # 기존 점수에 키워드 점수 반영
                        original_score = doc.get('final_score', doc.get('score', 0)) or 0
                        doc['final_score'] = original_score + keyword_score * 0.01
            except Exception as e:
                if self.debug_mode:
                    print(f"DEBUG: Keyword scoring error: {e}")
        
        processing_time = (time.time() - start_time) * 1000
        
        keyword_scored_count = len([doc for doc in documents if doc.get('keyword_relevance_score', 0) > 0])
        
        self._record_filter_result(
            documents, FilterStage.KEYWORD_FILTERING, len(documents), len(documents),
            f"Keyword relevance scoring applied", conditions,
            {'keyword_scored_documents': keyword_scored_count}, processing_time
        )
        
        return documents
    
    def _apply_negative_keyword_filtering(self, documents: List[Dict[Any, Any]], conditions: FilterConditions) -> List[Dict[Any, Any]]:
        """8단계: 네거티브 키워드 필터링"""
        start_time = time.time()
        
        keywords = self.negative_keywords.get(conditions.query_type, {'strong': [], 'weak': []})
        
        if not keywords['strong'] and not keywords['weak']:
            processing_time = (time.time() - start_time) * 1000
            self._record_filter_result(
                documents, FilterStage.NEGATIVE_KEYWORD_FILTERING, len(documents), len(documents),
                f"No negative keywords for {conditions.query_type.value} - skipped", conditions, {}, processing_time
            )
            return documents
        
        filtered_docs = []
        filter_stats = {'strong_filtered': 0, 'weak_filtered': 0, 'penalty_applied': 0}
        
        for doc in documents:
            doc_text = f"{doc.get('symptom', '')} {doc.get('effect', '')} {doc.get('incident_repair', '')}".lower()
            
            # 강한 네거티브 키워드 체크 (완전 제외)
            strong_negative = any(keyword in doc_text for keyword in keywords['strong'])
            if strong_negative:
                filter_stats['strong_filtered'] += 1
                continue
            
            # 약한 네거티브 키워드 체크 (점수 페널티)
            weak_negative_count = sum(1 for keyword in keywords['weak'] if keyword in doc_text)
            if weak_negative_count > 0:
                filter_stats['weak_filtered'] += 1
                filter_stats['penalty_applied'] += 1
                
                original_score = doc.get('final_score', 0) if doc.get('final_score') is not None else 0
                penalty = weak_negative_count * 0.1
                doc['final_score'] = max(original_score - penalty, 0)
                doc['negative_penalty'] = penalty
            
            filtered_docs.append(doc)
        
        processing_time = (time.time() - start_time) * 1000
        
        self._record_filter_result(
            filtered_docs, FilterStage.NEGATIVE_KEYWORD_FILTERING, len(documents), len(filtered_docs),
            f"Negative keyword filtering applied", conditions, filter_stats, processing_time
        )
        
        return filtered_docs
    
    def _apply_llm_validation(self, documents: List[Dict[Any, Any]], query: str, conditions: FilterConditions) -> List[Dict[Any, Any]]:
        """9단계: LLM 관련성 검증 (placeholder)"""
        start_time = time.time()
        
        # 실제 LLM 검증 로직은 별도 구현 필요
        validated_docs = documents[:]
        
        for doc in validated_docs:
            doc['llm_validated'] = True
            doc['validation_score'] = 0.8
            doc['validation_reason'] = 'LLM validation passed'
        
        processing_time = (time.time() - start_time) * 1000
        
        self._record_filter_result(
            validated_docs, FilterStage.LLM_VALIDATION, len(documents), len(validated_docs),
            f"LLM validation completed", conditions, 
            {'validation_method': 'placeholder', 'threshold': 0.7}, processing_time
        )
        
        return validated_docs
    
    def _apply_quality_scoring(self, documents: List[Dict[Any, Any]], conditions: FilterConditions) -> List[Dict[Any, Any]]:
        """10단계: 품질 점수 계산"""
        start_time = time.time()
        
        for doc in documents:
            quality_score = 0
            quality_factors = []
            
            # 기본 검색 점수
            search_score = doc.get('score', 0) or 0
            reranker_score = doc.get('reranker_score', 0) or 0
            
            if reranker_score > 0:
                quality_score += reranker_score * 0.4
                quality_factors.append(f"reranker({reranker_score:.2f})")
            
            quality_score += search_score * 0.3
            quality_factors.append(f"search({search_score:.2f})")
            
            # 서비스 매칭 보너스
            if doc.get('service_match_type') == 'exact':
                quality_score += 0.5
                quality_factors.append("exact_service")
            elif doc.get('service_match_type') == 'partial':
                quality_score += 0.3
                quality_factors.append("partial_service")
            
            # 등급 매칭 보너스
            if doc.get('grade_match_type') == 'exact':
                quality_score += 0.3
                quality_factors.append("exact_grade")
            
            # 의미적 유사성 보너스
            semantic_similarity = doc.get('semantic_similarity', 0) or 0
            if semantic_similarity > 0:
                quality_score += semantic_similarity * 0.2
                quality_factors.append(f"semantic({semantic_similarity:.2f})")
            
            # 키워드 관련성 보너스
            keyword_relevance = doc.get('keyword_relevance_score', 0) or 0
            if keyword_relevance > 0:
                quality_score += keyword_relevance * 0.01
                quality_factors.append(f"keywords({keyword_relevance})")
            
            # 페널티 적용
            negative_penalty = doc.get('negative_penalty', 0) or 0
            if negative_penalty > 0:
                quality_score -= negative_penalty
                quality_factors.append(f"penalty(-{negative_penalty:.2f})")
            
            doc['quality_score'] = quality_score
            doc['quality_factors'] = quality_factors
            
            # final_score 업데이트
            if 'final_score' not in doc or doc['final_score'] == 0:
                doc['final_score'] = quality_score
        
        processing_time = (time.time() - start_time) * 1000
        
        avg_quality = sum(doc.get('quality_score', 0) for doc in documents) / len(documents) if documents else 0
        
        self._record_filter_result(
            documents, FilterStage.QUALITY_SCORING, len(documents), len(documents),
            f"Quality scoring completed", conditions,
            {'average_quality_score': avg_quality}, processing_time
        )
        
        return documents
    
    def _apply_final_selection(self, documents: List[Dict[Any, Any]], conditions: FilterConditions) -> List[Dict[Any, Any]]:
        """11단계: 최종 선택"""
        start_time = time.time()
        
        final_docs = documents[:]
        
        # 품질 임계값 적용
        if conditions.quality_threshold > 0:
            final_docs = [doc for doc in final_docs if doc.get('quality_score', 0) >= conditions.quality_threshold]
        
        # 결과 수 제한
        if conditions.max_results and len(final_docs) > conditions.max_results:
            # 품질 점수순으로 정렬
            final_docs.sort(key=lambda x: (
                x.get('quality_score', 0),
                x.get('final_score', 0),
                x.get('score', 0)
            ), reverse=True)
            final_docs = final_docs[:conditions.max_results]
        
        # 최종 메타데이터 추가
        for i, doc in enumerate(final_docs):
            doc['final_rank'] = i + 1
            doc['filter_pipeline_completed'] = True
            doc['pipeline_timestamp'] = datetime.now().isoformat()
        
        processing_time = (time.time() - start_time) * 1000
        
        self._record_filter_result(
            final_docs, FilterStage.FINAL_SELECTION, len(documents), len(final_docs),
            f"Final selection completed", conditions, 
            {
                'max_results_applied': bool(conditions.max_results),
                'quality_threshold_applied': conditions.quality_threshold > 0,
                'final_average_quality': sum(doc.get('quality_score', 0) for doc in final_docs) / len(final_docs) if final_docs else 0
            }, processing_time
        )
        
        return final_docs
    
    def _record_skip_filtering(self, documents: List[Dict[Any, Any]], conditions: FilterConditions):
        """필터링 건너뛰기 기록"""
        self._record_filter_result(
            documents, FilterStage.CONDITION_FILTERING, len(documents), len(documents),
            f"Statistics query without specific conditions - filtering skipped for accurate count", 
            conditions,
            {
                'reason': 'statistics_query_general',
                'is_statistics_query': conditions.is_statistics_query,
                'has_specific_conditions': False,
                'conditions_summary': self._get_active_conditions(conditions)
            },
            0.0
        )
    
    def _record_filter_result(
        self, 
        documents: List[Dict[Any, Any]], 
        stage: FilterStage, 
        original_count: int, 
        filtered_count: int,
        reason: str, 
        conditions: FilterConditions,
        debug_info: Dict[str, Any] = None,
        processing_time_ms: float = 0.0
    ):
        """필터링 결과 기록"""
        result = FilterResult(
            documents=documents,
            stage=stage,
            original_count=original_count,
            filtered_count=filtered_count,
            filter_reason=reason,
            conditions_applied=conditions,
            debug_info=debug_info or {},
            processing_time_ms=processing_time_ms,
            timestamp=datetime.now()
        )
        self.filter_history.append(result)
        
        if self.debug_mode:
            removed = original_count - filtered_count
            print(f"DEBUG: {stage.value} - {original_count} -> {filtered_count} (removed: {removed}) [{processing_time_ms:.1f}ms] - {reason}")
    
    def _record_error(self, stage: str, error_msg: str, documents: List[Dict[Any, Any]], conditions: FilterConditions):
        """오류 기록"""
        error_result = FilterResult(
            documents=documents,
            stage=FilterStage.FINAL_SELECTION,
            original_count=len(documents),
            filtered_count=len(documents),
            filter_reason=f"Error in {stage}: {error_msg}",
            conditions_applied=conditions,
            debug_info={'error': True, 'stage': stage, 'message': error_msg},
            processing_time_ms=0.0,
            timestamp=datetime.now()
        )
        self.filter_history.append(error_result)
    
    def _format_conditions(self, conditions: FilterConditions) -> str:
        """조건을 읽기 쉽게 포맷"""
        active = []
        
        if conditions.year:
            active.append(f"year={conditions.year}")
        if conditions.month:
            active.append(f"month={conditions.month}")
        if conditions.months:
            active.append(f"months={conditions.months}")
        if conditions.start_month and conditions.end_month:
            active.append(f"months={conditions.start_month}-{conditions.end_month}")
        if conditions.daynight:
            active.append(f"daynight={conditions.daynight}")
        if conditions.week:
            active.append(f"week={conditions.week}")
        if conditions.service_name:
            active.append(f"service={conditions.service_name}")
        if conditions.department:
            active.append(f"dept={conditions.department}")
        if conditions.grade:
            active.append(f"grade={conditions.grade}")
        
        flags = []
        if conditions.is_statistics_query:
            flags.append("stats")
        if conditions.is_range_query:
            flags.append("range")
        if conditions.is_error_time_query:
            flags.append("error_time")
        if conditions.should_skip_filtering:
            flags.append("skip_filter")
        if conditions.is_common_service:
            flags.append("common_service")
        
        result = ", ".join(active) if active else "none"
        if flags:
            result += f" | flags: {','.join(flags)}"
        
        return result
    
    def _get_active_conditions(self, conditions: FilterConditions) -> List[str]:
        """활성 조건 목록 반환"""
        active = []
        
        if conditions.year:
            active.append(f"year={conditions.year}")
        if conditions.month:
            active.append(f"month={conditions.month}")
        if conditions.months:
            active.append(f"months={conditions.months}")
        if conditions.start_month and conditions.end_month:
            active.append(f"month_range={conditions.start_month}-{conditions.end_month}")
        if conditions.daynight:
            active.append(f"daynight={conditions.daynight}")
        if conditions.week:
            active.append(f"week={conditions.week}")
        if conditions.service_name:
            active.append(f"service={conditions.service_name}")
        if conditions.department:
            active.append(f"department={conditions.department}")
        if conditions.grade:
            active.append(f"grade={conditions.grade}")
        
        return active
    
    def _print_detailed_summary(self):
        """상세한 필터링 요약 출력"""
        if not self.filter_history:
            return
        
        print("DEBUG: === DETAILED FILTERING SUMMARY ===")
        
        initial_count = self.filter_history[0].original_count
        final_count = self.filter_history[-1].filtered_count
        total_removed = initial_count - final_count
        total_time = sum(result.processing_time_ms for result in self.filter_history)
        
        print(f"DEBUG: Pipeline Summary:")
        print(f"DEBUG:   Initial count: {initial_count}")
        print(f"DEBUG:   Final count: {final_count}")
        print(f"DEBUG:   Total removed: {total_removed}")
        print(f"DEBUG:   Total processing time: {total_time:.2f}ms")
        print(f"DEBUG:   Stages completed: {len(self.filter_history)}")
        
        print(f"DEBUG: Stage Details:")
        for i, result in enumerate(self.filter_history, 1):
            removed = result.original_count - result.filtered_count
            print(f"DEBUG:   {i}. {result.stage.value}:")
            print(f"DEBUG:      Input: {result.original_count}")
            print(f"DEBUG:      Output: {result.filtered_count}")
            print(f"DEBUG:      Removed: {removed}")
            print(f"DEBUG:      Time: {result.processing_time_ms:.1f}ms")
            print(f"DEBUG:      Reason: {result.filter_reason}")
            
            if result.debug_info:
                print(f"DEBUG:      Details: {result.debug_info}")
        
        print("DEBUG: =====================================")
    
    def get_filter_summary(self) -> Dict[str, Any]:
        """필터링 결과 요약 반환"""
        if not self.filter_history:
            return {'error': 'No filter history available'}
        
        initial_count = self.filter_history[0].original_count
        final_count = self.filter_history[-1].filtered_count
        total_time = sum(result.processing_time_ms for result in self.filter_history)
        
        return {
            'pipeline_summary': {
                'total_stages': len(self.filter_history),
                'initial_count': initial_count,
                'final_count': final_count,
                'total_removed': initial_count - final_count,
                'filter_rate': (initial_count - final_count) / initial_count if initial_count > 0 else 0,
                'total_processing_time_ms': total_time,
                'completion_timestamp': self.filter_history[-1].timestamp.isoformat()
            },
            'stages': [
                {
                    'stage': result.stage.value,
                    'original_count': result.original_count,
                    'filtered_count': result.filtered_count,
                    'removed_count': result.removed_count,
                    'filter_rate': result.filter_rate,
                    'processing_time_ms': result.processing_time_ms,
                    'reason': result.filter_reason,
                    'debug_info': result.debug_info,
                    'timestamp': result.timestamp.isoformat()
                }
                for result in self.filter_history
            ],
            'conditions_applied': {
                'original_query': self.filter_history[0].conditions_applied.original_query,
                'query_type': self.filter_history[0].conditions_applied.query_type.value,
                'is_statistics_query': self.filter_history[0].conditions_applied.is_statistics_query,
                'should_skip_filtering': self.filter_history[0].conditions_applied.should_skip_filtering,
                'active_conditions': self._get_active_conditions(self.filter_history[0].conditions_applied)
            }
        }
    
    def export_filter_history(self, filepath: Optional[str] = None) -> str:
        """필터링 히스토리를 JSON으로 내보내기"""
        summary = self.get_filter_summary()
        
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(summary, f, ensure_ascii=False, indent=2)
                return f"Filter history exported to {filepath}"
            except Exception as e:
                return f"Export failed: {str(e)}"
        else:
            return json.dumps(summary, ensure_ascii=False, indent=2)
    
    def reset_history(self):
        """필터링 히스토리 초기화"""
        self.filter_history.clear()
    
    def get_last_result(self) -> Optional[FilterResult]:
        """마지막 필터링 결과 반환"""
        return self.filter_history[-1] if self.filter_history else None
    
    def set_search_manager(self, search_manager):
        """SearchManager 설정 (런타임 주입)"""
        self.search_manager = search_manager
    
    def set_config(self, config):
        """Configuration 설정 (런타임 주입)"""
        self.config = config
    
    # 챗봇 구조와의 호환성을 위한 wrapper 메서드들
    def filter_documents_by_time_conditions(self, documents, time_conditions):
        """시간 조건 기반 필터링 (호환성)"""
        conditions = FilterConditions()
        if time_conditions.get('daynight'):
            conditions.daynight = time_conditions['daynight']
        if time_conditions.get('week'):
            conditions.week = time_conditions['week']
        if time_conditions.get('year'):
            conditions.year = time_conditions['year']
        if time_conditions.get('month'):
            conditions.month = time_conditions['month']
        
        filtered_docs = []
        for doc in documents:
            is_valid, _ = self.validator.validate_document_conditions(doc, conditions)
            if is_valid:
                filtered_docs.append(doc)
        
        return filtered_docs
    
    def filter_documents_by_department_conditions(self, documents, department_conditions):
        """부서 조건 기반 필터링 (호환성)"""
        conditions = FilterConditions()
        if department_conditions.get('owner_depart'):
            conditions.department = department_conditions['owner_depart']
        
        filtered_docs = []
        for doc in documents:
            is_valid, _ = self.validator.validate_document_conditions(doc, conditions)
            if is_valid:
                filtered_docs.append(doc)
        
        return filtered_docs


def test_filter_manager():
    """필터 매니저 테스트 함수"""
    
    test_documents = [
        {
            'incident_id': 'INM25011031275',
            'service_name': '블록체인기반지역화폐',
            'error_date': '2025-01-10',
            'error_time': 94,
            'incident_grade': '3등급',
            'daynight': '주간',
            'week': '금',
            'owner_depart': '보안침해대응팀',
            'symptom': '온누리 상품권 앱 접속 및 충전 불가',
            'root_cause': '웹방화벽(vWAF)에서 프로모션으로 인한 트래픽 급증',
            'incident_repair': '트래픽 분산 및 서버 스케일링'
        },
        {
            'incident_id': 'INM25011731327',
            'service_name': '케이티 커뮤니스',
            'error_date': '2025-01-17',
            'error_time': 876,
            'incident_grade': '2등급',
            'daynight': '야간',
            'week': '목',
            'owner_depart': '시스템관리팀',
            'symptom': '서비스 접속 불가',
            'root_cause': 'JSON 라이브러리 오류',
            'incident_repair': '라이브러리 재설치 및 서비스 재시작'
        },
        {
            'incident_id': 'INM25012045678',
            'service_name': 'ERP',
            'error_date': '2025-02-15',
            'error_time': 120,
            'incident_grade': '1등급',
            'daynight': '주간',
            'week': '월',
            'owner_depart': '개발팀',
            'symptom': '로그인 불가',
            'root_cause': '데이터베이스 연결 실패',
            'incident_repair': 'DB 커넥션 풀 재설정'
        }
    ]
    
    filter_manager = DocumentFilterManager(debug_mode=True)
    
    print("\n=== TEST 1: 2025년 1월 통계 쿼리 ===")
    filtered_docs, history = filter_manager.apply_comprehensive_filtering(
        test_documents, "2025년 1월 장애건수 통계", QueryType.STATISTICS
    )
    print(f"Results: {len(filtered_docs)} documents")
    
    print("\n=== TEST 2: ERP 서비스 복구방법 쿼리 ===")
    filter_manager.reset_history()
    filtered_docs, history = filter_manager.apply_comprehensive_filtering(
        test_documents, "ERP 로그인 불가 복구방법", QueryType.REPAIR
    )
    print(f"Results: {len(filtered_docs)} documents")
    
    print("\n=== TEST 3: 1등급 장애 조회 ===")
    filter_manager.reset_history()
    filtered_docs, history = filter_manager.apply_comprehensive_filtering(
        test_documents, "1등급 장애 내역", QueryType.INQUIRY
    )
    print(f"Results: {len(filtered_docs)} documents")
    
    summary = filter_manager.get_filter_summary()
    print(f"\nFilter Summary: {json.dumps(summary, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    test_filter_manager()