# utils/statistics_db_manager.py - 원인유형 통계 지원 및 정규화된 데이터 형식 지원 (완전 수정)
import sqlite3
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
import re
from dotenv import load_dotenv

load_dotenv()

def get_incident_db_path():
    """환경변수에서 인시던트 DB 경로 가져오기"""
    base_path = os.getenv('DB_BASE_PATH', 'data/db')
    return os.path.join(base_path, 'incident_data.db')

class StatisticsDBManager:
    """SQLite DB 기반 통계 조회 관리자 - 원인유형별 통계 완전 지원"""
    
    # 자연어 → 실제 원인유형 매핑 맵 (확장)
    CAUSE_TYPE_MAPPING = {
        # 기존 매핑
        '버그': '제품결함', 'bug': '제품결함', '제품결함': '제품결함', '제품': '제품결함', '결함': '제품결함',
        '작업오류': '작업 오 수행', '작업실수': '수행 실수', '작업': '작업 오 수행', '수행실수': '수행 실수',
        '배치오류': '배치 오 수행', '배치': '배치 오 수행', '환경설정': '환경설정오류', '설정오류': '환경설정오류',
        '설정': '환경설정오류', '사용자설정': '사용자 설정 오류', '테스트': '단위 테스트 미흡', '단위테스트': '단위 테스트 미흡',
        '통합테스트': '통합 테스트 미흡', '테스트미흡': '단위 테스트 미흡', '설계오류': '로직 설계 오류',
        '로직오류': '로직 설계 오류', 'db설계': 'DB 설계 오류', '인터페이스설계': '인터페이스 설계 오류',
        '과부하': '과부하', '부하': '과부하', '용량': '용량부족', '용량부족': '용량부족',
        '외부시스템': '외부 연동시스템 오류', '외부연동': '외부 연동시스템 오류', '연동오류': '외부 연동시스템 오류',
        '영향분석': '영향분석 오류', '분석오류': '영향분석 오류', '데이터': '데이터 조회 오류', '데이터조회': '데이터 조회 오류',
        '업무협의': '업무협의 부족', '정보공유': '정보공유 부족', '소통': '업무협의 부족', '구버전': '구 버전 배포',
        '개발버전': '개발 버전 배포', '버전관리': '소스 버전 관리 미흡', '명령어': '명령어 오류', 'sop': '작업 SOP 미준수',
        '점검': '운영환경 점검 오류', 'ui': 'UI 구현 오류', '요구사항': '요구사항 분석 미흡',
        
        # 새로 추가된 매핑 (더 포괄적으로)
        '원인유형': '', '원인': '', '유형': '', '타입': '', 'type': '',
        '실수': '수행 실수', '오수행': '작업 오 수행', '미흡': '단위 테스트 미흡',
        '오류': '환경설정오류', '부족': '업무협의 부족', '연동': '외부 연동시스템 오류',
        '시스템': '외부 연동시스템 오류', '배포': '구 버전 배포', '관리': '소스 버전 관리 미흡',
        
        # 추가 자연어 매핑
        '네트워크': '외부 연동시스템 오류', '서버': '과부하', '메모리': '용량부족', '디스크': '용량부족',
        '코딩': '제품결함', '프로그래밍': '제품결함', '개발': '제품결함', '소스': '소스 버전 관리 미흡',
        '배치작업': '배치 오 수행', '스케줄': '배치 오 수행', '자동화': '배치 오 수행',
        '사용자': '사용자 설정 오류', '고객': '사용자 입력 오류', '입력': '사용자 입력 오류',
        '권한': '사용자 설정 오류', '인증': '사용자 설정 오류', '접근': '사용자 설정 오류'
    }
    
    # 실제 DB에 존재하는 원인유형 목록 (초기값)
    ACTUAL_CAUSE_TYPES = [
        '작업 오 수행', '수행 실수', '환경설정오류', '대외 연관 테스트 미흡', '외부 연동시스템 오류', '업무협의 부족',
        '사용자 설정 오류', '배치 오 수행', 'DB 설계 오류', '영향분석 오류', '로직 설계 오류', '제품결함', '과부하',
        '운영환경 점검 오류', '단위 테스트 미흡', '통합 테스트 미흡', '데이터 조회 오류', '인터페이스 설계 오류',
        '외부 모듈 영향분석 오류', '기준정보 설계 오류', '명령어 오류', '판단조건 오류', '예외처리 설계 누락',
        '내부 모듈 영향분석 오류', '소스 버전 관리 미흡', '사용자 입력 오류', '작업 SOP 미준수', '관제 오 동작',
        '과거데이타 영향분석 오류', '구 버전 배포', '인터페이스 사양 오류', '정보공유 부족', 'UI 구현 오류',
        '작업 시간 미준수', '요구사항 분석 미흡', '개발 버전 배포', '인퍼테이스 정의 오류', '용량부족'
    ]
    
    # 원인유형별 통계 키워드 (확장)
    CAUSE_TYPE_KEYWORDS = [
        '원인유형', '원인별', '원인유형별', '원인타입', '원인타입별', 'cause_type', 'causetype',
        '문제원인', '장애원인', '발생원인', '근본원인', '주요원인', '핵심원인', 'root_cause',
        '원인분석', '원인현황', '원인통계', '원인분포', '원인별통계', '원인별현황', '원인별분석',
        '유형별', '타입별', '종류별', '분류별', '카테고리별', 'type별', '원인분류',
        '원인별장애', '원인별발생', '원인별건수', '원인별현황', '원인별분포'
    ]
    
    # 원인유형 관련 동의어 (확장)
    CAUSE_TYPE_SYNONYMS = {
        '원인유형별': '원인유형', '원인별': '원인유형', '원인타입별': '원인유형',
        '문제유형': '원인유형', '장애유형': '원인유형', '발생유형': '원인유형',
        '원인분류': '원인유형', '원인종류': '원인유형', '원인카테고리': '원인유형'
    }
    
    def __init__(self, db_path: str = None):
        # 매칭 통계 초기화
        self.matching_stats = {
            'exact_matches': 0,
            'mapping_matches': 0,
            'partial_matches': 0,
            'keyword_matches': 0,
            'no_matches': 0
        }
        
        # DB 경로 설정
        if db_path is None: 
            db_path = get_incident_db_path()
        self.db_path = db_path
        
        # 서비스명 목록 로드
        self._load_service_names()
        
        # DB 존재 확인
        self._ensure_db_exists()
        
        # 실제 DB에서 존재하는 원인유형들을 동적으로 로드
        self._load_actual_cause_types_from_db()
    
    def _load_service_names(self):
        """service_names.txt 파일에서 서비스명 목록 로드"""
        self.service_names = []
        
        # 여러 경로에서 service_names.txt 파일 찾기
        possible_paths = [
            'config/service_names.txt',
            'service_names.txt',
            '/mnt/user-data/uploads/service_names.txt',
            os.path.join(os.path.dirname(self.db_path), 'service_names.txt'),
            os.path.join(os.path.dirname(__file__), 'service_names.txt'),
            os.path.join(os.path.dirname(__file__), '..', 'config', 'service_names.txt')
        ]
        
        for path in possible_paths:
            try:
                if os.path.exists(path):
                    with open(path, 'r', encoding='utf-8') as f:
                        self.service_names = [line.strip() for line in f if line.strip()]
                    
                    # 길이가 긴 서비스명부터 우선 매칭하도록 정렬
                    self.service_names.sort(key=len, reverse=True)
                    return
                    
            except Exception as e:
                continue
        
        self.service_names = []
    
    def _ensure_db_exists(self):
        """DB 파일 존재 확인"""
        try:
            if not os.path.exists(self.db_path):
                raise FileNotFoundError(f"Database not found: {self.db_path}")
            
            # DB 연결 테스트
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='incidents'")
            if not cursor.fetchone():
                raise ValueError("Table 'incidents' not found in database")
            conn.close()
                
        except Exception as e:
            raise
    
    def _load_actual_cause_types_from_db(self):
        """실제 DB에서 존재하는 원인유형들을 동적으로 로드"""
        try:
            query = """
            SELECT DISTINCT cause_type, COUNT(*) as count 
            FROM incidents 
            WHERE cause_type IS NOT NULL AND cause_type != '' AND cause_type != 'null'
            GROUP BY cause_type
            ORDER BY count DESC
            """
            results = self._execute_query(query)
            
            if results:
                actual_types = [row['cause_type'] for row in results if row['cause_type']]
                if actual_types:
                    self.ACTUAL_CAUSE_TYPES = actual_types
                    
        except Exception as e:
            pass
    
    def _execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """SQL 쿼리 실행 및 결과 반환"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute(query, params)
            results = [dict(row) for row in cursor.fetchall()]
            return results
            
        except Exception as e:
            return []
        finally: 
            conn.close()
    
    def _match_cause_type(self, query_text: str) -> Optional[str]:
        """자연어 질의에서 원인유형 매칭 (4단계 매칭 로직)"""
        if not query_text: 
            return None
        
        query_lower = query_text.lower()
        
        # 1단계: 정확한 원인유형이 질의에 포함되어 있는지 확인
        for actual_cause in self.ACTUAL_CAUSE_TYPES:
            if actual_cause in query_text or actual_cause.lower() in query_lower:
                self.matching_stats['exact_matches'] += 1
                return actual_cause
        
        # 2단계: 자연어 매핑 사전 활용
        for natural_lang, mapped_cause in self.CAUSE_TYPE_MAPPING.items():
            if not mapped_cause:  # 빈 문자열은 건너뛰기
                continue
            
            # 단어 경계를 고려한 정확한 매칭
            pattern = r'\b' + re.escape(natural_lang) + r'\b'
            if re.search(pattern, query_lower, re.IGNORECASE):
                self.matching_stats['mapping_matches'] += 1
                return mapped_cause
        
        # 3단계: 부분 문자열 매칭 (유사성 검사)
        for actual_cause in self.ACTUAL_CAUSE_TYPES:
            # 공백 제거하고 소문자로 변환하여 비교
            cause_normalized = actual_cause.replace(' ', '').lower()
            query_normalized = query_lower.replace(' ', '')
            
            # 3자 이상의 키워드가 포함되어 있는지 확인
            if len(cause_normalized) >= 3 and cause_normalized in query_normalized:
                self.matching_stats['partial_matches'] += 1
                return actual_cause
        
        # 4단계: 키워드 기반 매칭 (확장)
        cause_keywords_mapping = {
            '제품결함': ['버그', 'bug', '결함', '오류', 'error', '에러', '코딩', '프로그래밍', '개발오류'],
            '수행 실수': ['실수', '작업실수', '수행실수', '실행실수', '휴먼에러', '사람실수'],
            '환경설정오류': ['설정', '환경설정', 'config', '구성', '설정오류', '환경오류', '파라미터'],
            '외부 연동시스템 오류': ['연동', '외부', '시스템', '연계', '인터페이스', 'api', '통신'],
            '과부하': ['부하', 'load', '성능', 'performance', '트래픽', '용량초과', '부하증가'],
            '용량부족': ['용량', 'capacity', '디스크', 'disk', '메모리', 'memory', '저장공간'],
            '작업 오 수행': ['작업오류', '작업실패', '절차오류', '프로세스오류', '업무오류'],
            '배치 오 수행': ['배치', 'batch', '스케줄', '자동화', '배치작업', '배치처리'],
            '단위 테스트 미흡': ['테스트', 'test', '단위테스트', '유닛테스트', '테스트부족'],
            '통합 테스트 미흡': ['통합테스트', '연동테스트', '시스템테스트', '종합테스트'],
            'DB 설계 오류': ['데이터베이스', 'database', 'db설계', '스키마', '테이블설계'],
            '소스 버전 관리 미흡': ['버전', 'version', '소스관리', '형상관리', 'git', 'svn'],
            '사용자 설정 오류': ['사용자설정', '계정설정', '권한설정', '유저설정'],
            '사용자 입력 오류': ['입력오류', '사용자입력', '데이터입력', '잘못된입력']
        }
        
        for cause_type, keywords in cause_keywords_mapping.items():
            if any(keyword in query_lower for keyword in keywords):
                matched_keywords = [k for k in keywords if k in query_lower]
                self.matching_stats['keyword_matches'] += 1
                return cause_type
        
        self.matching_stats['no_matches'] += 1
        
        return None
    
    def _is_cause_type_query(self, query: str) -> bool:
        """원인유형별 통계 쿼리인지 간단하고 확실하게 판별"""
        if not query:
            return False
        
        query_lower = query.lower()
        
        # 동의어 정규화
        normalized_query = query_lower
        for synonym, standard in self.CAUSE_TYPE_SYNONYMS.items():
            normalized_query = normalized_query.replace(synonym, standard)
        
        # 1차: 직접적인 원인유형 키워드 확인
        for keyword in self.CAUSE_TYPE_KEYWORDS:
            if keyword in normalized_query:
                return True
        
        # 2차: 원인유형이 매칭되는지 확인
        matched_cause = self._match_cause_type(query)
        if matched_cause:
            return True
        
        # 3차: 원인 관련 패턴 확인
        cause_patterns = [
            r'원인.*?별.*?(?:통계|현황|건수|분석)',
            r'(?:통계|현황|건수|분석).*?원인.*?별',
            r'(?:제품결함|수행실수|환경설정|연동오류|과부하).*?(?:통계|현황|건수)',
            r'(?:버그|실수|설정|연동|부하).*?(?:별|유형|타입).*?(?:통계|현황|건수)'
        ]
        
        for pattern in cause_patterns:
            if re.search(pattern, normalized_query):
                return True
        
        return False
    
    def _normalize_year_query(self, year_input: str) -> str:
        """연도 쿼리 정규화: '2025년' → '2025'"""
        if not year_input: 
            return year_input
        return re.sub(r'년$', '', year_input.strip())
    
    def _normalize_month_query(self, month_input: str) -> str:
        """월 쿼리 정규화: '9월' → '9'"""
        if not month_input: 
            return month_input
        return re.sub(r'월$', '', month_input.strip())
    
    def _normalize_week_query(self, week_input: str) -> str:
        """요일 쿼리 정규화: '금요일' → '금'"""
        if not week_input: 
            return week_input
        week_mapping = {
            '월요일': '월', '화요일': '화', '수요일': '수', '목요일': '목', 
            '금요일': '금', '토요일': '토', '일요일': '일'
        }
        if week_input in week_mapping: 
            return week_mapping[week_input]
        return re.sub(r'요일$', '', week_input.strip())
    
    def _normalize_grade_query(self, grade_input: str) -> str:
        """장애등급 쿼리 정규화: '4등급' → '4'"""
        if not grade_input: 
            return grade_input
        return re.sub(r'등급$', '', grade_input.strip())

    def _get_current_year(self) -> str:
        """현재 연도를 반환하는 헬퍼 함수"""
        from datetime import datetime
        return str(datetime.now().year)
    
    def _extract_period_months(self, query: str) -> tuple:
        """분기/반기 표현 추출 및 월 리스트 반환 + 자동 연도 설정"""
        if not query:
            return ([], None)
        
        query_lower = query.lower()
        
        # 분기 매핑
        quarter_months = {
            '1분기': [1, 2, 3], 'q1': [1, 2, 3], '제1분기': [1, 2, 3], '1q': [1, 2, 3],
            '2분기': [4, 5, 6], 'q2': [4, 5, 6], '제2분기': [4, 5, 6], '2q': [4, 5, 6],
            '3분기': [7, 8, 9], 'q3': [7, 8, 9], '제3분기': [7, 8, 9], '3q': [7, 8, 9],
            '4분기': [10, 11, 12], 'q4': [10, 11, 12], '제4분기': [10, 11, 12], '4q': [10, 11, 12]
        }
        
        # 반기 매핑
        half_year_months = {
            '상반기': [1, 2, 3, 4, 5, 6], '전반기': [1, 2, 3, 4, 5, 6], 
            '1반기': [1, 2, 3, 4, 5, 6], 'h1': [1, 2, 3, 4, 5, 6],
            '하반기': [7, 8, 9, 10, 11, 12], '후반기': [7, 8, 9, 10, 11, 12], 
            '2반기': [7, 8, 9, 10, 11, 12], 'h2': [7, 8, 9, 10, 11, 12]
        }
        
        # 분기 체크
        for period_name, months in quarter_months.items():
            if period_name in query_lower:
                return (months, period_name)
        
        # 반기 체크
        for period_name, months in half_year_months.items():
            if period_name in query_lower:
                return (months, period_name)
        
        return ([], None)
    
    def parse_statistics_query(self, query: str) -> Dict[str, Any]:
        """
        자연어 쿼리에서 통계 조건 추출 - 분기/반기 처리 + 자동 연도 설정
        핵심 수정: '분' 키워드를 '장애시간' 맥락에서만 인식하도록 개선 
        """
        conditions = {
            'year': None, 'months': [], 'service_name': None, 'daynight': None, 'week': None,
            'incident_grade': None, 'owner_depart': None, 'cause_type': None, 'group_by': [],
            'is_error_time_query': False, 'is_cause_type_query': False, 'period_type': None,
            'auto_year_assigned': False
        }
        
        query_lower, original_query = query.lower(), query
        
        # 1. 쿼리 정규화 - 동의어 통합
        normalized_query = self._normalize_query_synonyms(query_lower)
        
        # 2. 원인유형 쿼리 여부 확인
        conditions['is_cause_type_query'] = self._is_cause_type_query(original_query)
        
        # 3. 연도 추출
        two_digit_year_patterns = [
            r'\b([0-9]{2})년\b',
            r'\b([0-9]{2})년도\b',
            r'\b([0-9]{2})\s*년\b'
        ]
        
        year_found = False
        for pattern in two_digit_year_patterns:
            if year_match := re.search(pattern, normalized_query):
                two_digit_year = year_match.group(1)
                year_int = int(two_digit_year)
                if 0 <= year_int <= 99:
                    full_year = f"20{two_digit_year}"
                    conditions['year'] = full_year
                    year_found = True
                    break
        
        if not year_found:
            four_digit_year_patterns = [
                r'\b(202[0-9]|201[0-9])년\b', 
                r'\b(202[0-9]|201[0-9])년도\b', 
                r'\b(202[0-9]|201[0-9])\s*년\b', 
                r'\b(202[0-9]|201[0-9])\b(?=.*(장애|건수|통계|현황|몇|개수|원인))',
            ]
            
            for pattern in four_digit_year_patterns:
                if year_match := re.search(pattern, normalized_query):
                    conditions['year'] = self._normalize_year_query(year_match.group(1))
                    break
        
        # 4. 장애등급 추출
        grade_patterns = [
            r'(\d)등급\s*장애', r'장애\s*(\d)등급', r'장애등급\s*(\d)', 
            r'\b([1-4])등급\b(?!\s*월)', r'등급\s*([1-4])', 
            r'([1-4])\s*등급(?=.*(장애|건수|통계))',
        ]
        
        for pattern in grade_patterns:
            if grade_match := re.search(pattern, normalized_query):
                grade_num = grade_match.group(1)
                if grade_num in ['1', '2', '3', '4']:
                    match_pos = grade_match.start()
                    before_text = normalized_query[max(0, match_pos-4):match_pos]
                    if not re.search(r'20\d{2}', before_text):
                        conditions['incident_grade'] = grade_num
                        break
        
        # 5. 분기/반기 추출 (우선 처리) + 자동 연도 설정
        period_months, period_type = self._extract_period_months(original_query)
        
        if period_months:
            conditions['months'] = [str(m) for m in period_months]
            conditions['period_type'] = period_type
            
            # 핵심: 연도가 없으면 현재 연도(2025년) 자동 설정
            if not conditions['year']:
                current_year = self._get_current_year()
                conditions['year'] = current_year
                conditions['auto_year_assigned'] = True
        
        # 6. 월 범위 추출 (분기/반기가 없는 경우에만)
        if not conditions['months']:
            month_range_patterns = [
                r'(\d+)\s*~\s*(\d+)월', r'(\d+)월\s*~\s*(\d+)월', 
                r'(\d+)\s*-\s*(\d+)월', r'(\d+)월\s*-\s*(\d+)월', 
                r'(\d+)\s*부터\s*(\d+)월', r'(\d+)월\s*부터\s*(\d+)월',
            ]
            
            for pattern in month_range_patterns:
                if match := re.search(pattern, normalized_query):
                    start, end = int(match.group(1)), int(match.group(2))
                    if 1 <= start <= 12 and 1 <= end <= 12 and start <= end:
                        conditions['months'] = [str(m) for m in range(start, end + 1)]
                        
                        # 월 범위도 연도 없으면 현재 연도 자동 설정
                        if not conditions['year']:
                            current_year = self._get_current_year()
                            conditions['year'] = current_year
                            conditions['auto_year_assigned'] = True
                        
                        break
        
        # 개별 월 추출 (분기/반기/월범위가 모두 없는 경우에만)
        if not conditions['months']:
            month_pattern = r'(?<!등급\s)(\d{1,2})월(?!\s*등급)'
            month_matches = re.findall(month_pattern, normalized_query)
            if month_matches:
                valid_months = [str(int(m)) for m in month_matches if 1 <= int(m) <= 12]
                if valid_months:
                    conditions['months'] = valid_months
        
        # 7. 서비스명 추출
        conditions['service_name'] = self._extract_service_name_enhanced(original_query)
        
        # 8. 원인유형 추출
        conditions['cause_type'] = self._match_cause_type(original_query)
        
        # 9. 요일 추출
        week_patterns = {
            '월': [r'\b월요일\b', r'\b월요\b'], 
            '화': [r'\b화요일\b', r'\b화요\b'], 
            '수': [r'\b수요일\b', r'\b수요\b'], 
            '목': [r'\b목요일\b', r'\b목요\b'], 
            '금': [r'\b금요일\b', r'\b금요\b'], 
            '토': [r'\b토요일\b', r'\b토요\b'],
            '일': [r'\b일요일\b', r'\b일요\b']
        }
        
        for day_val, day_patterns in week_patterns.items():
            if any(re.search(pattern, normalized_query) for pattern in day_patterns):
                conditions['week'] = day_val
                break
        
        if re.search(r'\b평일\b', normalized_query): 
            conditions['week'] = '평일'
        elif re.search(r'\b주말\b', normalized_query): 
            conditions['week'] = '주말'
        
        # 10. 시간대 추출
        daynight_patterns = {
            '야간': [r'\b야간\b', r'\b밤\b', r'\b새벽\b', r'\b심야\b'],
            '주간': [r'\b주간\b', r'\b낮\b', r'\b오전\b', r'\b오후\b', r'\b업무시간\b']
        }
        
        for daynight_val, patterns in daynight_patterns.items():
            if any(re.search(pattern, normalized_query) for pattern in patterns):
                conditions['daynight'] = daynight_val
                break
        
        # 핵심 수정 11. 장애시간 쿼리 여부 - '분' 키워드 처리 개선
        # '분기'가 포함된 경우는 제외하고, '장애시간'이나 '시간' 맥락에서만 '분'을 인식
        error_time_keywords_strict = [
            '장애시간', '장애 시간', 'error_time', '시간 합계', '시간 합산',
            '총 시간', '누적 시간', '전체 시간', '합계 시간', '시간통계'
        ]
        
        # 먼저 엄격한 키워드로 체크
        conditions['is_error_time_query'] = any(k in normalized_query for k in error_time_keywords_strict)
        
        # '분'이 포함되어 있다면, '분기'가 아닌 경우에만 장애시간 쿼리로 인식
        if not conditions['is_error_time_query'] and '분' in normalized_query:
            # '분기', '1분기', '2분기' 등이 포함되어 있으면 장애시간 쿼리가 아님
            if not any(quarter_term in normalized_query for quarter_term in ['1분기', '2분기', '3분기', '4분기', 'q1', 'q2', 'q3', 'q4', '분기']):
                # '장애', '시간', '합계', '통계' 등의 맥락 키워드와 함께 사용된 경우에만 장애시간 쿼리로 인식
                context_keywords = ['장애', '시간', '합계', '통계', '총', '누적', '전체']
                if any(ctx in normalized_query for ctx in context_keywords):
                    # '분' 앞뒤로 숫자가 있는지 확인 (예: "30분", "분석" 등 제외)
                    minute_pattern = r'\d+\s*분(?!\s*기)'  # "분기"가 아닌 "분"만
                    if re.search(minute_pattern, normalized_query):
                        conditions['is_error_time_query'] = True
        
        # 12. 그룹화 기준 추출
        groupby_keywords = {
            'year': ['연도별', '년도별', '년별', '연별', '해별'],
            'month': ['월별', '매월', '월간'],
            'incident_grade': ['등급별', '장애등급별', 'grade별'],
            'week': ['요일별', '주간별', '일별'],
            'daynight': ['시간대별', '주야별'],
            'owner_depart': ['부서별', '팀별', '조직별'],
            'service_name': ['서비스별', '시스템별'],
            'cause_type': self.CAUSE_TYPE_KEYWORDS
        }
        
        for group_field, keywords in groupby_keywords.items():
            if any(keyword in normalized_query for keyword in keywords):
                if group_field not in conditions['group_by']:
                    conditions['group_by'].append(group_field)
        
        # 13. 원인유형 쿼리인 경우 자동 그룹화 설정
        if conditions['is_cause_type_query'] and 'cause_type' not in conditions['group_by']:
            conditions['group_by'].append('cause_type')

        # 14. 기본 그룹화 추론
        if not conditions['group_by']:
            has_specific_year = conditions['year'] is not None
            has_specific_month = len(conditions['months']) > 0
            has_specific_grade = conditions['incident_grade'] is not None
            has_specific_cause = conditions['cause_type'] is not None
            has_period = conditions['period_type'] is not None
            
            # 핵심 수정: 분기/반기 쿼리는 명시적으로 "월별"이 없으면 GROUP BY 추가 안 함
            if has_period:
                # 분기/반기 쿼리인 경우, 전체 합계만 원하는 것으로 간주
                # "월별" 키워드가 명시되지 않았다면 GROUP BY 추가하지 않음
                pass
            elif has_specific_cause and not has_specific_year and not has_specific_month:
                conditions['group_by'] = ['year']
            elif has_specific_grade and not has_specific_year and not has_specific_month:
                conditions['group_by'] = ['year']
            elif not any([has_specific_year, has_specific_month, has_specific_grade, has_specific_cause]):
                # 아무 조건도 없으면 연도별로
                conditions['group_by'] = ['year']
            
            # 명시적으로 "월별" 키워드가 있는 경우에만 월별 그룹화
            if '월별' in query or '월간' in query or '매월' in query:
                if 'month' not in conditions['group_by']:
                    conditions['group_by'].append('month')
        
        return conditions

    def _extract_service_name_enhanced(self, query: str) -> Optional[str]:
        """향상된 서비스명 추출 로직 - service_names.txt 파일 참조"""
        if not query:
            return None
        
        # 원인유형 쿼리에서는 서비스명 추출을 더 신중하게
        if self._is_cause_type_query(query):
            pass
        
        # 1단계: service_names.txt 파일의 서비스명들과 직접 매칭 (길이순 정렬로 긴 이름부터)
        if hasattr(self, 'service_names') and self.service_names:
            for service_name in self.service_names:
                # 정확한 매칭
                if service_name in query:
                    return service_name
                
                # 대소문자 무시한 매칭
                if service_name.lower() in query.lower():
                    return service_name
            
            # 2단계: 부분 매칭 (3글자 이상)
            for service_name in self.service_names:
                if len(service_name) >= 3:
                    # 공백 제거 후 매칭
                    normalized_service = service_name.replace(' ', '').replace('-', '').lower()
                    normalized_query = query.replace(' ', '').replace('-', '').lower()
                    
                    if normalized_service in normalized_query:
                        return service_name
        
        # 3단계: 기존 패턴 매칭 (service_names.txt가 없거나 매칭 실패 시)
        service_patterns = [
            # "생체인증플랫폼", "네트워크보안범위관리" 등을 위한 긴 서비스명 패턴
            r'([가-힣]{4,20}(?:플랫폼|시스템|서비스|포털|앱|APP|관리|센터))\s*(?:년도별|연도별|월별|장애|건수|통계|현황|몇|개수)',
            
            # 기존 패턴들
            r'([A-Z가-힣][A-Z가-힣0-9\s]{1,20}(?:시스템|서비스|포털|앱|APP))\s*(?:년도별|연도별|월별|장애|건수|통계|현황|몇|개수)',
            r'\b([A-Z]{2,10})\b(?=.*(장애|건수|통계|현황|몇))(?!.*원인)',
            r'(\w+)\s*(?:서비스|시스템).*?(?:장애|건수|통계|현황|몇)',
            
            # 따옴표나 괄호로 감싸진 서비스명
            r'["\']([A-Za-z가-힣][A-Za-z0-9가-힣\s]{1,30})["\']',
            r'\(([A-Za-z가-힣][A-Za-z0-9가-힣\s]{1,30})\)',
            
            # 쿼리 맨 앞에 오는 서비스명 (원인유형 키워드가 없는 경우)
            r'^([A-Za-z가-힣][A-Za-z0-9가-힣\s\-_]{2,20})\s+(?:년도별|연도별|월별|장애|건수|통계|현황|몇|개수)',
        ]
        
        for i, pattern in enumerate(service_patterns):
            try:
                matches = re.findall(pattern, query, re.IGNORECASE)
                if matches:
                    for match in matches:
                        # 튜플인 경우 첫 번째 요소 사용, 문자열인 경우 그대로 사용
                        if isinstance(match, tuple):
                            service_name = match[0].strip() if match[0] else ""
                        else:
                            service_name = match.strip()
                        
                        # 제외할 키워드들 (원인유형 키워드 대폭 추가)
                        exclude_keywords = [
                            'SELECT', 'FROM', 'WHERE', 'AND', 'OR', '년', '월', '일', '등급',
                            '장애', '건수', '통계', '현황', '몇', '개수', '발생', '알려', '보여',
                            '연도별', '년도별', '월별', '요일별', '시간대별', '부서별', 
                            '원인', '원인유형', '원인별', '유형', '타입', 'type', '원인유형별', 
                            '원인타입별', '문제원인', '장애원인', '발생원인', '근본원인', 
                            '주요원인', '핵심원인', '원인분석', '원인현황', '원인통계', 
                            '원인분포', '원인별통계', '원인별현황', '원인분류'
                        ] + self.CAUSE_TYPE_KEYWORDS
                        
                        if (len(service_name) >= 2 and 
                            service_name.lower() not in [k.lower() for k in exclude_keywords] and
                            not service_name.isdigit() and
                            service_name not in self.ACTUAL_CAUSE_TYPES):
                            
                            return service_name
                            
            except Exception as e:
                continue
        
        return None

    def build_sql_query(self, conditions: Dict[str, Any]) -> tuple:
        """조건에 따른 SQL 쿼리 생성 - 원인유형 처리 완전 강화 + 월 타입 캐스팅 추가"""
        try:
            # SELECT 절
            if conditions.get('is_error_time_query', False):
                select_fields = ['SUM(error_time) as total_value']
                value_label = 'total_error_time_minutes'
            else:
                select_fields = ['COUNT(*) as total_value']
                value_label = 'total_count'
            
            # GROUP BY 절
            group_fields = []
            valid_group_fields = ['year', 'month', 'daynight', 'week', 'owner_depart', 'service_name', 'incident_grade', 'cause_type']
            
            for field in conditions.get('group_by', []):
                if field in valid_group_fields:
                    group_fields.append(field)
                    select_fields.insert(0, field)
            
            # WHERE 절 구성
            where_clauses = []
            params = []
            
            # 기본 데이터 품질 필터
            base_filters = [
                "incident_id IS NOT NULL",
                "incident_id != ''",
                "service_name IS NOT NULL", 
                "service_name != ''"
            ]
            where_clauses.extend(base_filters)
            
            # 연도 조건
            if conditions.get('year'):
                where_clauses.append("year = ?")
                params.append(conditions['year'])
            
            # 월 조건 (핵심 수정!) - 정수형 변환 및 조건 강화
            if conditions.get('months'):
                if len(conditions['months']) == 1:
                    # 단일 월: 정수 비교로 통일
                    where_clauses.append("CAST(month AS INTEGER) = ?")
                    params.append(int(conditions['months'][0]))
                else:
                    # 여러 월인 경우 (분기/반기 등) - 정수형 변환하여 비교
                    month_placeholders = ','.join(['?' for _ in conditions['months']])
                    where_clauses.append(f"CAST(month AS INTEGER) IN ({month_placeholders})")
                    # 정수형으로 변환하여 파라미터 전달
                    int_months = [int(m) for m in conditions['months']]
                    params.extend(int_months)
            
            # 장애등급 조건
            if conditions.get('incident_grade'):
                where_clauses.append("incident_grade = ?")
                params.append(conditions['incident_grade'])
            
            # 원인유형 조건 처리 (대폭 강화)
            if conditions.get('cause_type'):
                cause_conditions = []
                
                # 1. 정확한 매칭
                cause_conditions.append("cause_type = ?")
                params.append(conditions['cause_type'])
                
                # 2. 포함 매칭 (앞뒤로)
                cause_conditions.append("cause_type LIKE ?")
                params.append(f"%{conditions['cause_type']}%")
                
                # 3. 공백 제거 매칭
                normalized_cause = conditions['cause_type'].replace(' ', '')
                if normalized_cause != conditions['cause_type']:
                    cause_conditions.append("REPLACE(cause_type, ' ', '') LIKE ?")
                    params.append(f"%{normalized_cause}%")
                
                # 4. 키워드 분리 매칭
                cause_keywords = conditions['cause_type'].split()
                if len(cause_keywords) > 1:
                    for keyword in cause_keywords:
                        if len(keyword) >= 2:
                            cause_conditions.append("cause_type LIKE ?")
                            params.append(f"%{keyword}%")
                
                where_clauses.append(f"({' OR '.join(cause_conditions)})")
            
            # 원인유형 쿼리인 경우 원인유형 필드 필터링
            if conditions.get('is_cause_type_query', False) or 'cause_type' in group_fields:
                cause_filters = [
                    "cause_type IS NOT NULL", 
                    "cause_type != ''", 
                    "cause_type != 'null'"
                ]
                where_clauses.extend(cause_filters)
            
            # 요일 조건
            if conditions.get('week'):
                if conditions['week'] == '평일':
                    where_clauses.append("week IN ('월', '화', '수', '목', '금')")
                elif conditions['week'] == '주말':
                    where_clauses.append("week IN ('토', '일')")
                else:
                    where_clauses.append("week = ?")
                    params.append(conditions['week'])
            
            # 시간대 조건
            if conditions.get('daynight'):
                where_clauses.append("daynight = ?")
                params.append(conditions['daynight'])
            
            # 서비스명 조건 (개선)
            if conditions.get('service_name'):
                service_conditions = [
                    "service_name = ?",
                    "service_name LIKE ?"
                ]
                params.extend([
                    conditions['service_name'],
                    f"%{conditions['service_name']}%"
                ])
                where_clauses.append(f"({' OR '.join(service_conditions)})")
            
            # 부서 조건
            if conditions.get('owner_depart'):
                where_clauses.append("owner_depart LIKE ?")
                params.append(f"%{conditions['owner_depart']}%")
            
            # 최종 쿼리 조합
            query = f"SELECT {', '.join(select_fields)} FROM incidents"
            
            if where_clauses: 
                query += f" WHERE {' AND '.join(where_clauses)}"
            
            if group_fields:
                query += f" GROUP BY {', '.join(group_fields)}"
                
                # 정렬 (원인유형 정렬 강화)
                if 'cause_type' in group_fields: 
                    query += " ORDER BY total_value DESC, cause_type ASC"
                elif 'year' in group_fields: 
                    query += " ORDER BY CAST(year AS INTEGER) DESC"
                elif 'month' in group_fields: 
                    query += " ORDER BY CAST(month AS INTEGER)"
                elif 'incident_grade' in group_fields: 
                    query += " ORDER BY CAST(incident_grade AS INTEGER)"
                elif 'week' in group_fields:
                    query += " ORDER BY CASE week WHEN '월' THEN 1 WHEN '화' THEN 2 WHEN '수' THEN 3 WHEN '목' THEN 4 WHEN '금' THEN 5 WHEN '토' THEN 6 WHEN '일' THEN 7 END"
                else: 
                    query += f" ORDER BY {', '.join(group_fields)}"
            else:
                # GROUP BY가 없는 경우 최신 순 정렬
                query += " ORDER BY year DESC, month DESC"
            
            return query, tuple(params), value_label        
            
        except Exception as e:
            # 안전한 기본 쿼리 반환
            return "SELECT COUNT(*) as total_value FROM incidents WHERE incident_id IS NOT NULL", (), 'total_count'    

    def get_statistics(self, query: str) -> Dict[str, Any]:
        """자연어 쿼리로 통계 조회 - 원인유형 통계 완전 지원 + 예외 처리 개선"""
        # 기본 conditions 초기화 (예외 발생 전에 미리 생성)
        default_conditions = {
            'year': None, 'months': [], 'service_name': None, 'daynight': None, 'week': None,
            'incident_grade': None, 'owner_depart': None, 'cause_type': None, 'group_by': [],
            'is_error_time_query': False, 'is_cause_type_query': False, 'period_type': None,
            'auto_year_assigned': False
        }
        
        try:
            # 쿼리 파싱
            conditions = self.parse_statistics_query(query)
            
            # SQL 생성 및 실행
            sql_query, params, value_label = self.build_sql_query(conditions)
            results = self._execute_query(sql_query, params)
            
            # 결과 구조화
            statistics = {
                'query_conditions': conditions,
                'sql_query': sql_query,
                'sql_params': params,
                'results': results,
                'value_label': value_label,
                'is_error_time_query': conditions['is_error_time_query'],
                'is_cause_type_query': conditions['is_cause_type_query'],
                'total_count': 0,
                'total_value': 0,
                'yearly_stats': {},
                'monthly_stats': {},
                'time_stats': {'daynight': {}, 'week': {}},
                'department_stats': {},
                'service_stats': {},
                'grade_stats': {},
                'cause_type_stats': {},  # 원인유형 통계 필드
                'debug_info': {
                    'parsed_conditions': conditions,
                    'sql_query': sql_query,
                    'sql_params': params,
                    'result_count': len(results),
                    'available_cause_types': getattr(self, 'ACTUAL_CAUSE_TYPES', [])[:10],
                    'available_service_names': getattr(self, 'service_names', [])[:10],
                    'matching_stats': getattr(self, 'matching_stats', {}).copy(),
                    'has_group_by': len(conditions.get('group_by', [])) > 0
                }
            }
            
            # 핵심 수정: GROUP BY 여부에 따라 결과 집계 방식 분기
            has_group_by = len(conditions.get('group_by', [])) > 0
            
            if has_group_by:
                # GROUP BY가 있는 경우: 각 그룹별로 통계 집계
                statistics = self._aggregate_grouped_results(results, statistics, conditions)
            else:
                # GROUP BY가 없는 경우: 단일 집계값 처리
                statistics = self._aggregate_single_result(results, statistics, conditions)
            
            # 원인유형 통계 후처리
            if statistics['cause_type_stats']:
                # 원인유형별 통계를 건수 순으로 정렬
                sorted_cause_stats = dict(sorted(
                    statistics['cause_type_stats'].items(), 
                    key=lambda x: x[1], 
                    reverse=True
                ))
                statistics['cause_type_stats'] = sorted_cause_stats
            
            return statistics
            
        except Exception as e:
            # 안전한 기본 응답 반환
            return {
                'query_conditions': default_conditions,
                'sql_query': '',
                'sql_params': (),
                'results': [],
                'value_label': 'total_count',
                'is_error_time_query': False,
                'is_cause_type_query': False,
                'total_count': 0,
                'total_value': 0,
                'yearly_stats': {},
                'monthly_stats': {},
                'time_stats': {'daynight': {}, 'week': {}},
                'department_stats': {},
                'service_stats': {},
                'grade_stats': {},
                'cause_type_stats': {},
                'debug_info': {
                    'parsed_conditions': default_conditions,
                    'error': str(e),
                    'error_traceback': ''
                },
                'error': str(e)
            }

    def _aggregate_grouped_results(self, results, statistics, conditions):
        """GROUP BY가 있는 경우의 결과 집계 - 조건 검증 강화"""
        
        skipped_count = 0
        processed_count = 0
        
        for row in results:
            # 조건 검증: 월 필터 (정수 변환하여 비교)
            if conditions.get('months'):
                try:
                    row_month_raw = row.get('month', '')
                    # None이나 빈 값 처리
                    if row_month_raw is None or str(row_month_raw).strip() == '':
                        skipped_count += 1
                        continue
                    
                    row_month = int(row_month_raw)
                    expected_months = [int(m) for m in conditions['months']]
                    
                    if row_month not in expected_months:
                        skipped_count += 1
                        continue
                except (ValueError, TypeError) as e:
                    skipped_count += 1
                    continue
            
            # 조건 검증: 연도 필터
            if conditions.get('year'):
                row_year = str(row.get('year', '')).strip()
                expected_year = str(conditions['year'])
                
                if row_year and row_year != expected_year:
                    skipped_count += 1
                    continue
            
            # 조건 검증: 등급 필터
            if conditions.get('incident_grade'):
                row_grade = str(row.get('incident_grade', '')).strip()
                expected_grade = str(conditions['incident_grade'])
                
                if row_grade and row_grade != expected_grade:
                    skipped_count += 1
                    continue
            
            # 조건을 통과한 데이터만 집계
            processed_count += 1
            value = row.get('total_value', 0) or 0
            statistics['total_value'] += value
            
            # 각 분류별 통계 수집
            if 'year' in row and row['year']:
                year_key = str(row['year'])
                statistics['yearly_stats'][year_key] = statistics['yearly_stats'].get(year_key, 0) + value
            
            if 'month' in row and row['month']:
                month_key = str(row['month'])
                statistics['monthly_stats'][month_key] = statistics['monthly_stats'].get(month_key, 0) + value
            
            if 'daynight' in row and row['daynight']:
                statistics['time_stats']['daynight'][row['daynight']] = value
            
            if 'week' in row and row['week']:
                week_label = f"{row['week']}요일" if row['week'] not in ['평일', '주말'] else row['week']
                statistics['time_stats']['week'][week_label] = value
            
            if 'owner_depart' in row and row['owner_depart']:
                statistics['department_stats'][row['owner_depart']] = value
            
            if 'service_name' in row and row['service_name']:
                statistics['service_stats'][row['service_name']] = value
            
            if 'incident_grade' in row and row['incident_grade']:
                grade_key = f"{row['incident_grade']}등급"
                statistics['grade_stats'][grade_key] = value
            
            # 원인유형 통계 처리
            if 'cause_type' in row and row['cause_type']:
                cause_type = str(row['cause_type']).strip()
                if cause_type and cause_type.lower() not in ['null', 'none', '']:
                    statistics['cause_type_stats'][cause_type] = value
        
        # 전체 건수 계산
        if conditions.get('is_error_time_query'):
            statistics['total_count'] = processed_count
        else:
            statistics['total_count'] = statistics['total_value']
        
        return statistics

    def _aggregate_single_result(self, results, statistics, conditions):
        """GROUP BY가 없는 경우의 결과 집계 - 조건 검증 강화 + 0건 처리"""
        if not results or len(results) == 0:
            statistics['total_count'] = 0
            statistics['total_value'] = 0
            
            # 중요: 0건일 때도 조건이 있으면 해당 조건에 0으로 명시
            if conditions.get('year'):
                statistics['yearly_stats'][conditions['year']] = 0
            
            # 분기/반기 조건이 있으면 전체 0으로 표시 (월별로 분해하지 않음)
            if conditions.get('period_type'):
                pass
            elif conditions.get('months') and len(conditions['months']) == 1:
                # 단일 월 조건인 경우에만 월별 통계에 0 할당
                statistics['monthly_stats'][conditions['months'][0]] = 0
            
            return statistics
        
        # 단일 집계 결과 처리
        first_result = results[0]
        total_value = first_result.get('total_value', 0) or 0
        
        statistics['total_count'] = total_value
        statistics['total_value'] = total_value
        
        # 결과가 0인 경우 처리
        if total_value == 0:
            # 0건이어도 조건이 있으면 해당 조건에 0으로 명시
            if conditions.get('year'):
                statistics['yearly_stats'][conditions['year']] = 0
            
            return statistics
        
        # 결과가 0보다 큰 경우에만 통계 할당
        if total_value > 0:
            # 연도 조건이 명시되었고 결과가 있는 경우
            if conditions.get('year'):
                statistics['yearly_stats'][conditions['year']] = total_value
            
            # 중요: 분기/반기 조건의 경우, 전체 합계만 표시하고 월별로 분해하지 않음
            if conditions.get('period_type'):
                # 월별 통계를 만들지 않음 (전체 합계만 의미있음)
                pass
            
            # 단일 월 조건인 경우에만 월별 통계에 할당
            elif conditions.get('months') and len(conditions['months']) == 1:
                statistics['monthly_stats'][conditions['months'][0]] = total_value
        
        return statistics

    def get_incident_details(self, conditions: Dict[str, Any], limit: int = 100) -> List[Dict[str, Any]]:
        """조건에 맞는 장애 상세 내역 조회 - 원인유형 조건 완전 강화"""
        try:
            where_clauses = []
            params = []
            
            # 기본 품질 필터
            where_clauses.extend([
                "incident_id IS NOT NULL",
                "incident_id != ''",
                "service_name IS NOT NULL",
                "service_name != ''"
            ])
            
            if conditions.get('year'):
                where_clauses.append("year = ?")
                params.append(conditions['year'])
            
            if conditions.get('months'):
                if len(conditions['months']) == 1:
                    where_clauses.append("month = ?")
                    params.append(conditions['months'][0])
                else:
                    month_placeholders = ','.join(['?' for _ in conditions['months']])
                    where_clauses.append(f"month IN ({month_placeholders})")
                    params.extend(conditions['months'])
            
            if conditions.get('incident_grade'):
                where_clauses.append("incident_grade = ?")
                params.append(conditions['incident_grade'])
            
            # 원인유형 조건 (다중 매칭 전략)
            if conditions.get('cause_type'):
                cause_conditions = [
                    "cause_type = ?",
                    "cause_type LIKE ?",
                    "REPLACE(cause_type, ' ', '') LIKE ?"
                ]
                params.extend([
                    conditions['cause_type'],
                    f"%{conditions['cause_type']}%",
                    f"%{conditions['cause_type'].replace(' ', '')}%"
                ])
                where_clauses.append(f"({' OR '.join(cause_conditions)})")
            
            if conditions.get('week'):
                if conditions['week'] == '평일':
                    where_clauses.append("week IN ('월', '화', '수', '목', '금')")
                elif conditions['week'] == '주말':
                    where_clauses.append("week IN ('토', '일')")
                else:
                    where_clauses.append("week = ?")
                    params.append(conditions['week'])
            
            if conditions.get('daynight'):
                where_clauses.append("daynight = ?")
                params.append(conditions['daynight'])
            
            # 서비스명 조건 (정확한 매칭 + LIKE 매칭)
            if conditions.get('service_name'):
                service_conditions = [
                    "service_name = ?",
                    "service_name LIKE ?"
                ]
                params.extend([
                    conditions['service_name'],
                    f"%{conditions['service_name']}%"
                ])
                where_clauses.append(f"({' OR '.join(service_conditions)})")
            
            if conditions.get('owner_depart'):
                where_clauses.append("owner_depart LIKE ?")
                params.append(f"%{conditions['owner_depart']}%")
            
            query = "SELECT * FROM incidents"
            if where_clauses: 
                query += f" WHERE {' AND '.join(where_clauses)}"
            query += f" ORDER BY error_date DESC, error_time DESC LIMIT {limit}"
            
            return self._execute_query(query, tuple(params))
            
        except Exception as e:
            return []
    
    def _normalize_query_synonyms(self, query: str) -> str:
        """쿼리의 동의어들을 표준 형태로 정규화 (원인유형 동의어 추가)"""
        synonym_mappings = {
            # 기존 동의어
            '장애건수': '건수', '장애 건수': '건수', '발생건수': '건수', '발생 건수': '건수',
            '장애 개수': '건수', '장애개수': '건수', '몇건이야': '몇건', '몇건이니': '몇건',
            '몇건인가': '몇건', '몇건인지': '몇건', '몇건이나': '몇건', '몇개야': '몇건',
            '몇개인가': '몇건', '몇개인지': '몇건', '몇개나': '몇건', '발생했어': '발생',
            '발생했나': '발생', '발생했는지': '발생', '발생한지': '발생', '생겼어': '발생',
            '생긴': '발생', '난': '발생', '일어난': '발생', '있어': '발생', '있나': '발생',
            '있는지': '발생', '있었어': '발생', '알려줘': '알려주세요', '보여줘': '알려주세요',
            '말해줘': '알려주세요', '확인해줘': '알려주세요', '체크해줘': '알려주세요',
            '얼마나': '몇', '어느정도': '몇', '어떻게': '몇', '어느': '몇', '어떤': '몇',
            '몇번': '몇건', '몇차례': '몇건', '몇회': '몇건', '수량': '건수', '숫자': '건수',
            '개수': '건수', '총': '전체', '총합': '전체', '모든': '전체', '모두': '전체',
            '누적': '전체', '상황': '현황', '현재': '현황', '지금까지': '현황', '정도': '현황',
            '수준': '현황', '범위': '현황', '규모': '현황',
            
            # 원인유형 관련 동의어 추가
            '원인유형별': '원인유형', '원인별': '원인유형', '원인타입별': '원인유형',
            '문제유형': '원인유형', '장애유형': '원인유형', '발생유형': '원인유형',
            '원인분류': '원인유형', '원인종류': '원인유형', '원인카테고리': '원인유형',
            '원인타입': '원인유형', '타입별': '원인유형', '유형별': '원인유형',
            '분류별': '원인유형', '카테고리별': '원인유형'
        }
        
        normalized = query
        for old_term, new_term in synonym_mappings.items():
            normalized = normalized.replace(old_term, new_term)
        
        # 연속된 공백 정리
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    def test_cause_type_matching(self, test_queries: List[str] = None):
        """원인유형 매칭 테스트 함수 (완전한 디버깅용)"""
        if not test_queries:
            test_queries = [
                "원인유형별 통계",
                "원인별 장애건수", 
                "제품결함 통계",
                "작업실수 몇건",
                "설정오류 현황",
                "2025년 원인유형별 현황",
                "버그로 인한 장애",
                "환경설정 문제",
                "연동오류 통계",
                "과부하 장애",
                "원인분석 현황",
                "원인별 발생 건수",
                "장애 원인 통계",
                "문제 원인유형별 현황"
            ]
        
        # 매칭 통계 초기화
        self.matching_stats = {
            'exact_matches': 0,
            'mapping_matches': 0, 
            'partial_matches': 0,
            'keyword_matches': 0,
            'no_matches': 0
        }
        
        test_results = []
        
        for i, query in enumerate(test_queries, 1):
            # 원인유형 쿼리 여부 확인
            is_cause_query = self._is_cause_type_query(query)
            
            # 원인유형 매칭
            matched_cause = self._match_cause_type(query)
            
            # 전체 파싱 결과
            conditions = self.parse_statistics_query(query)
            
            # 실제 DB 쿼리 테스트
            try:
                stats_result = self.get_statistics(query)
                cause_stats = stats_result.get('cause_type_stats', {})
            except Exception as e:
                pass
            
            success = is_cause_query or matched_cause or conditions['is_cause_type_query']
            
            test_results.append({
                'query': query,
                'is_cause_query': is_cause_query,
                'matched_cause': matched_cause,
                'parsed_cause': conditions['cause_type'],
                'success': success
            })
        
        return test_results
    
    def get_cause_type_distribution(self) -> Dict[str, Any]:
        """DB에서 원인유형별 분포 현황 조회"""
        try:
            query = """
            SELECT 
                cause_type,
                COUNT(*) as count,
                ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM incidents WHERE cause_type IS NOT NULL AND cause_type != ''), 2) as percentage
            FROM incidents 
            WHERE cause_type IS NOT NULL AND cause_type != '' AND cause_type != 'null'
            GROUP BY cause_type
            ORDER BY count DESC
            """
            
            results = self._execute_query(query)
            
            distribution = {
                'total_incidents': sum(r['count'] for r in results),
                'unique_cause_types': len(results),
                'distribution': results
            }
            
            return distribution
            
        except Exception as e:
            return {
                'total_incidents': 0,
                'unique_cause_types': 0,
                'distribution': [],
                'error': str(e)
            }