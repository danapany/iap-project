# utils/statistics_db_manager.py - 원인유형 통계 지원 및 정규화된 데이터 형식 지원
import sqlite3
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
import re
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

def get_incident_db_path():
    """환경변수에서 인시던트 DB 경로 가져오기"""
    base_path = os.getenv('DB_BASE_PATH', 'data/db')
    return os.path.join(base_path, 'incident_data.db')

class StatisticsDBManager:
    """SQLite DB 기반 통계 조회 관리자"""
    
    # 자연어 → 실제 원인유형 매칭 맵
    CAUSE_TYPE_MAPPING = {
        # 제품/버그 관련
        '버그': '제품결함',
        'bug': '제품결함',
        '제품결함': '제품결함',
        '제품': '제품결함',
        '결함': '제품결함',
        
        # 작업/수행 관련
        '작업오류': '작업 오 수행',
        '작업실수': '수행 실수',
        '작업': '작업 오 수행',
        '수행실수': '수행 실수',
        '배치오류': '배치 오 수행',
        '배치': '배치 오 수행',
        
        # 설정 관련
        '환경설정': '환경설정오류',
        '설정오류': '환경설정오류',
        '설정': '환경설정오류',
        '사용자설정': '사용자 설정 오류',
        
        # 테스트 관련
        '테스트': '단위 테스트 미흡',
        '단위테스트': '단위 테스트 미흡',
        '통합테스트': '통합 테스트 미흡',
        '테스트미흡': '단위 테스트 미흡',
        
        # 설계 관련
        '설계오류': '로직 설계 오류',
        '로직오류': '로직 설계 오류',
        'db설계': 'DB 설계 오류',
        '인터페이스설계': '인터페이스 설계 오류',
        
        # 시스템 관련
        '과부하': '과부하',
        '부하': '과부하',
        '용량': '용량부족',
        '용량부족': '용량부족',
        
        # 외부 관련
        '외부시스템': '외부 연동시스템 오류',
        '외부연동': '외부 연동시스템 오류',
        '연동오류': '외부 연동시스템 오류',
        
        # 분석 관련
        '영향분석': '영향분석 오류',
        '분석오류': '영향분석 오류',
        
        # 데이터 관련
        '데이터': '데이터 조회 오류',
        '데이터조회': '데이터 조회 오류',
        
        # 협의/소통 관련
        '업무협의': '업무협의 부족',
        '정보공유': '정보공유 부족',
        '소통': '업무협의 부족',
        
        # 배포 관련
        '구버전': '구 버전 배포',
        '개발버전': '개발 버전 배포',
        '버전관리': '소스 버전 관리 미흡',
        
        # 기타
        '명령어': '명령어 오류',
        'sop': '작업 SOP 미준수',
        '점검': '운영환경 점검 오류',
        'ui': 'UI 구현 오류',
        '요구사항': '요구사항 분석 미흡',
    }
    
    # 실제 DB에 존재하는 원인유형 목록 (정확한 매칭용)
    ACTUAL_CAUSE_TYPES = [
        '작업 오 수행', '수행 실수', '환경설정오류', '대외 연관 테스트 미흡',
        '외부 연동시스템 오류', '업무협의 부족', '사용자 설정 오류', '배치 오 수행',
        'DB 설계 오류', '영향분석 오류', '로직 설계 오류', '제품결함', '과부하',
        '운영환경 점검 오류', '단위 테스트 미흡', '통합 테스트 미흡', '데이터 조회 오류',
        '인터페이스 설계 오류', '외부 모듈 영향분석 오류', '기준정보 설계 오류',
        '명령어 오류', '판단조건 오류', '예외처리 설계 누락', '내부 모듈 영향분석 오류',
        '소스 버전 관리 미흡', '사용자 입력 오류', '작업 SOP 미준수', '관제 오 동작',
        '과거데이타 영향분석 오류', '구 버전 배포', '인터페이스 사양 오류', '정보공유 부족',
        'UI 구현 오류', '작업 시간 미준수', '요구사항 분석 미흡', '개발 버전 배포',
        '인퍼테이스 정의 오류', '용량부족'
    ]
    
    def __init__(self, db_path: str = None):
        # db_path가 제공되지 않으면 환경변수에서 가져오기
        if db_path is None:
            db_path = get_incident_db_path()
        
        self.db_path = db_path
        self._ensure_db_exists()
        self.debug_mode = True
    
    def _ensure_db_exists(self):
        """DB 파일 존재 확인"""
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database not found: {self.db_path}")
    
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
            print(f"ERROR: Database query failed: {e}")
            print(f"Query: {query}")
            print(f"Params: {params}")
            return []
        finally:
            conn.close()
    
    def _match_cause_type(self, query_text: str) -> Optional[str]:
        """자연어 질의에서 원인유형 매칭"""
        if not query_text:
            return None
        
        query_lower = query_text.lower()
        
        # 1단계: 정확한 원인유형이 질의에 포함되어 있는지 확인
        for actual_cause in self.ACTUAL_CAUSE_TYPES:
            if actual_cause in query_text or actual_cause.lower() in query_lower:
                if self.debug_mode:
                    print(f"✓ Exact cause_type match found: '{actual_cause}'")
                return actual_cause
        
        # 2단계: 자연어 매핑 사전 활용
        for natural_lang, mapped_cause in self.CAUSE_TYPE_MAPPING.items():
            # 단어 경계를 고려한 매칭
            pattern = r'\b' + re.escape(natural_lang) + r'\b'
            if re.search(pattern, query_lower):
                if self.debug_mode:
                    print(f"✓ Mapped cause_type: '{natural_lang}' → '{mapped_cause}'")
                return mapped_cause
        
        # 3단계: 부분 문자열 매칭 (유사성 검사)
        for actual_cause in self.ACTUAL_CAUSE_TYPES:
            # 원인유형의 핵심 키워드 추출 (공백으로 분리)
            keywords = actual_cause.replace(' ', '').lower()
            
            # 질의에 해당 키워드가 포함되어 있는지 확인
            if len(keywords) >= 3 and keywords in query_lower.replace(' ', ''):
                if self.debug_mode:
                    print(f"✓ Partial match cause_type: '{actual_cause}'")
                return actual_cause
        
        return None
    
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
        
        # '요일' 제거
        return re.sub(r'요일$', '', week_input.strip())
    
    def _normalize_grade_query(self, grade_input: str) -> str:
        """장애등급 쿼리 정규화: '4등급' → '4'"""
        if not grade_input:
            return grade_input
        return re.sub(r'등급$', '', grade_input.strip())
    
    def parse_statistics_query(self, query: str) -> Dict[str, Any]:
        """자연어 쿼리에서 통계 조건 추출 - 독립적 조건 추출로 수정"""
        conditions = {
            'year': None,
            'months': [],
            'service_name': None,
            'daynight': None,
            'week': None,
            'incident_grade': None,
            'owner_depart': None,
            'cause_type': None,
            'group_by': [],
            'is_error_time_query': False
        }
        
        query_lower = query.lower()
        original_query = query
        
        if self.debug_mode:
            print(f"\n{'='*60}")
            print(f"📊 PARSING QUERY: '{query}'")
            print(f"{'='*60}")
        
        # 1. 쿼리 정규화 - 동의어 통합
        normalized_query = self._normalize_query_synonyms(query_lower)
        if self.debug_mode and normalized_query != query_lower:
            print(f"🔄 Normalized query: '{normalized_query}'")
        
        # 2. 연도 추출 (기존 패턴 유지)
        year_patterns = [
            r'\b(202[0-9]|201[0-9])년\b',
            r'\b(202[0-9]|201[0-9])년도\b', 
            r'\b(202[0-9]|201[0-9])\s*년\b',
            r'\b(202[0-9]|201[0-9])\b(?=.*(?:장애|건수|통계|현황|몇|개수))',
        ]
        
        for pattern in year_patterns:
            if year_match := re.search(pattern, normalized_query):
                conditions['year'] = self._normalize_year_query(year_match.group(1))
                if self.debug_mode:
                    print(f"✓ Extracted year: {conditions['year']}")
                break
        
        # 3. 장애등급 추출 (패턴 개선, 하지만 독립적으로 처리)
        grade_patterns = [
            r'(\d)등급\s*장애',           # "2등급 장애"
            r'장애\s*(\d)등급',           # "장애 2등급"  
            r'장애등급\s*(\d)',           # "장애등급 2"
            r'\b([1-4])등급\b(?!\s*월)',  # "2등급" (하지만 "2등급월" 제외)
            r'등급\s*([1-4])',           # "등급 2"
            r'([1-4])\s*등급(?=.*(?:장애|건수|통계))',  # "2 등급" + 장애 관련 키워드
        ]
        
        for pattern in grade_patterns:
            if grade_match := re.search(pattern, normalized_query):
                grade_num = grade_match.group(1)
                if grade_num in ['1', '2', '3', '4']:
                    # 연도와 혼동 방지 (2020년 등)
                    match_pos = grade_match.start()
                    before_text = normalized_query[max(0, match_pos-4):match_pos]
                    if not re.search(r'20\d{2}', before_text):  # 연도가 아닌 경우만
                        conditions['incident_grade'] = grade_num
                        if self.debug_mode:
                            print(f"✓ Extracted incident_grade: {conditions['incident_grade']}")
                        break
        
        # 4. 월 범위 추출 (더 정확한 패턴 사용)
        month_range_patterns = [
            r'(\d+)\s*~\s*(\d+)월',      # "1~6월"
            r'(\d+)월\s*~\s*(\d+)월',    # "1월~6월"
            r'(\d+)\s*-\s*(\d+)월',      # "1-6월" 
            r'(\d+)월\s*-\s*(\d+)월',    # "1월-6월"
            r'(\d+)\s*부터\s*(\d+)월',    # "1부터 6월"
            r'(\d+)월\s*부터\s*(\d+)월',  # "1월부터 6월"
        ]
        
        for pattern in month_range_patterns:
            if match := re.search(pattern, normalized_query):
                start, end = int(match.group(1)), int(match.group(2))
                if 1 <= start <= 12 and 1 <= end <= 12 and start <= end:
                    conditions['months'] = [str(m) for m in range(start, end + 1)]
                    if self.debug_mode:
                        print(f"✓ Extracted month range: {conditions['months']}")
                    break
        
        # 개별 월 추출 (핵심 수정: "월"이 명시적으로 있는 경우만)
        if not conditions['months']:
            # 🔥 "월"이 반드시 있어야 하고, 등급과 구분되도록 패턴 개선
            month_pattern = r'(?<!등급\s)(\d{1,2})월(?!\s*등급)'  # "등급 2월" 또는 "2월 등급" 제외
            month_matches = re.findall(month_pattern, normalized_query)
            if month_matches:
                valid_months = [str(int(m)) for m in month_matches if 1 <= int(m) <= 12]
                if valid_months:
                    conditions['months'] = valid_months
                    if self.debug_mode:
                        print(f"✓ Extracted months: {conditions['months']}")
        
        # 5. 원인유형 추출 (기존 로직 유지)
        conditions['cause_type'] = self._match_cause_type(original_query)
        if conditions['cause_type'] and self.debug_mode:
            print(f"✓ Extracted cause_type: {conditions['cause_type']}")
        
        # 6. 요일 추출 (더 정확한 패턴)
        week_patterns = {
            '월': [r'\b월요일\b', r'\b월요\b'],  # 명시적 요일만
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
                if self.debug_mode:
                    print(f"✓ Extracted week: {conditions['week']}")
                break
        
        # 평일/주말 처리
        if re.search(r'\b평일\b', normalized_query):
            conditions['week'] = '평일'
        elif re.search(r'\b주말\b', normalized_query):
            conditions['week'] = '주말'
        
        # 7. 시간대 추출 (기존 로직 유지)
        daynight_patterns = {
            '야간': [r'\b야간\b', r'\b밤\b', r'\b새벽\b', r'\b심야\b'],
            '주간': [r'\b주간\b', r'\b낮\b', r'\b오전\b', r'\b오후\b', r'\b업무시간\b']
        }
        
        for daynight_val, patterns in daynight_patterns.items():
            if any(re.search(pattern, normalized_query) for pattern in patterns):
                conditions['daynight'] = daynight_val
                if self.debug_mode:
                    print(f"✓ Extracted daynight: {conditions['daynight']}")
                break
        
        # 8. 서비스명 추출 (기존 로직 유지)
        service_patterns = [
            r'([A-Z가-힣][A-Z가-힣0-9\s]{1,20}(?:시스템|서비스|포털|앱|APP))',
            r'\b([A-Z]{2,10})\b(?=.*(장애|건수|통계|현황|몇))',
            r'(\w+)\s*(?:서비스|시스템).*?(?:장애|건수|통계|현황|몇)',
        ]
        
        for pattern in service_patterns:
            if service_match := re.search(pattern, original_query):
                service_name = service_match.group(1).strip()
                if service_name not in ['SELECT', 'FROM', 'WHERE', 'AND', 'OR', '년', '월', '일']:
                    conditions['service_name'] = service_name
                    if self.debug_mode:
                        print(f"✓ Extracted service_name: {service_name}")
                    break
        
        # 9. 장애시간 쿼리 여부
        error_time_keywords = [
            '장애시간', '장애 시간', 'error_time', '시간 합계', '시간 합산', '분', 
            '총 시간', '누적 시간', '전체 시간', '합계 시간'
        ]
        conditions['is_error_time_query'] = any(k in normalized_query for k in error_time_keywords)
        
        # 10. 그룹화 기준 추출
        groupby_keywords = {
            'year': ['연도별', '년도별', '년별', '연별', '해별'],
            'month': ['월별', '매월', '월간'],
            'incident_grade': ['등급별', '장애등급별', 'grade별'],
            'week': ['요일별', '주간별', '일별'],
            'daynight': ['시간대별', '주야별'],
            'owner_depart': ['부서별', '팀별', '조직별'],
            'service_name': ['서비스별', '시스템별'],
            'cause_type': ['원인별', '원인유형별', '원인타입별']
        }
        
        for group_field, keywords in groupby_keywords.items():
            if any(keyword in normalized_query for keyword in keywords):
                if group_field not in conditions['group_by']:
                    conditions['group_by'].append(group_field)
                    if self.debug_mode:
                        matched_keywords = [k for k in keywords if k in normalized_query]
                        print(f"✓ Added '{group_field}' to group_by (keyword: {matched_keywords})")
        
        # 11. 기본 그룹화 추론
        if not conditions['group_by']:
            has_specific_year = conditions['year'] is not None
            has_specific_month = len(conditions['months']) > 0
            has_specific_grade = conditions['incident_grade'] is not None
            
            # 특정 조건이 있으면서 그룹화 키워드가 없는 경우 기본 그룹화 추론
            if has_specific_grade and not has_specific_year and not has_specific_month:
                conditions['group_by'] = ['year']  # 등급이 지정되면 연도별로
            elif not any([has_specific_year, has_specific_month, has_specific_grade]):
                conditions['group_by'] = ['year']  # 아무 조건 없으면 연도별로
        
        if self.debug_mode:
            print(f"\n📋 FINAL PARSED CONDITIONS:")
            print(f"  Year: {conditions['year']}")
            print(f"  Months: {conditions['months']}")
            print(f"  Grade: {conditions['incident_grade']}")
            print(f"  Week: {conditions['week']}")
            print(f"  Daynight: {conditions['daynight']}")
            print(f"  Service: {conditions['service_name']}")
            print(f"  Cause Type: {conditions['cause_type']}")
            print(f"  Group By: {conditions['group_by']}")
            print(f"  Is Error Time Query: {conditions['is_error_time_query']}")
            print(f"{'='*60}\n")
        
        return conditions
    
    def build_sql_query(self, conditions: Dict[str, Any]) -> tuple:
        """조건에 따른 SQL 쿼리 생성 - 정규화된 데이터 형식 지원"""
        # SELECT 절
        if conditions['is_error_time_query']:
            select_fields = ['SUM(error_time) as total_value']
            value_label = 'total_error_time_minutes'
        else:
            select_fields = ['COUNT(*) as total_value']
            value_label = 'total_count'
        
        # GROUP BY 절
        group_fields = []
        for field in conditions['group_by']:
            if field in ['year', 'month', 'daynight', 'week', 'owner_depart', 
                        'service_name', 'incident_grade', 'cause_type']:
                group_fields.append(field)
                select_fields.insert(0, field)
        
        # WHERE 절
        where_clauses = []
        params = []
        
        # 연도 조건 (정규화된 형태로 비교)
        if conditions['year']:
            where_clauses.append("year = ?")
            params.append(conditions['year'])
            if self.debug_mode:
                print(f"WHERE: year = '{conditions['year']}'")
        
        # 월 조건 (정규화된 형태로 비교)
        if conditions['months']:
            if len(conditions['months']) == 1:
                where_clauses.append("month = ?")
                params.append(conditions['months'][0])
                if self.debug_mode:
                    print(f"WHERE: month = '{conditions['months'][0]}'")
            else:
                month_placeholders = ','.join(['?' for _ in conditions['months']])
                where_clauses.append(f"month IN ({month_placeholders})")
                params.extend(conditions['months'])
                if self.debug_mode:
                    print(f"WHERE: month IN {conditions['months']}")
        
        # 장애등급 조건 (정규화된 형태로 비교)
        if conditions['incident_grade']:
            where_clauses.append("incident_grade = ?")
            params.append(conditions['incident_grade'])
            if self.debug_mode:
                print(f"WHERE: incident_grade = '{conditions['incident_grade']}'")
        
        # 원인유형 조건
        if conditions['cause_type']:
            where_clauses.append("cause_type LIKE ?")
            params.append(f"%{conditions['cause_type']}%")
            if self.debug_mode:
                print(f"WHERE: cause_type LIKE '%{conditions['cause_type']}%'")
        
        # 요일 조건 (정규화된 형태로 비교)
        if conditions['week']:
            if conditions['week'] == '평일':
                where_clauses.append("week IN ('월', '화', '수', '목', '금')")
                if self.debug_mode:
                    print(f"WHERE: week IN (평일)")
            elif conditions['week'] == '주말':
                where_clauses.append("week IN ('토', '일')")
                if self.debug_mode:
                    print(f"WHERE: week IN (주말)")
            else:
                where_clauses.append("week = ?")
                params.append(conditions['week'])
                if self.debug_mode:
                    print(f"WHERE: week = '{conditions['week']}'")
        
        # 시간대 조건
        if conditions['daynight']:
            where_clauses.append("daynight = ?")
            params.append(conditions['daynight'])
            if self.debug_mode:
                print(f"WHERE: daynight = '{conditions['daynight']}'")
        
        # 서비스명 조건
        if conditions['service_name']:
            where_clauses.append("service_name LIKE ?")
            params.append(f"%{conditions['service_name']}%")
            if self.debug_mode:
                print(f"WHERE: service_name LIKE '%{conditions['service_name']}%'")
        
        # 부서 조건
        if conditions['owner_depart']:
            where_clauses.append("owner_depart LIKE ?")
            params.append(f"%{conditions['owner_depart']}%")
            if self.debug_mode:
                print(f"WHERE: owner_depart LIKE '%{conditions['owner_depart']}%'")
        
        # 쿼리 조합
        query = f"SELECT {', '.join(select_fields)} FROM incidents"
        
        if where_clauses:
            query += f" WHERE {' AND '.join(where_clauses)}"
        
        if group_fields:
            query += f" GROUP BY {', '.join(group_fields)}"
            # 정렬 (정규화된 데이터 고려)
            if 'year' in group_fields:
                query += " ORDER BY CAST(year AS INTEGER)"
            elif 'month' in group_fields:
                query += " ORDER BY CAST(month AS INTEGER)"
            elif 'incident_grade' in group_fields:
                query += " ORDER BY CAST(incident_grade AS INTEGER)"
            elif 'week' in group_fields:
                query += " ORDER BY CASE week WHEN '월' THEN 1 WHEN '화' THEN 2 WHEN '수' THEN 3 WHEN '목' THEN 4 WHEN '금' THEN 5 WHEN '토' THEN 6 WHEN '일' THEN 7 END"
            elif 'cause_type' in group_fields:
                query += " ORDER BY total_value DESC"
            else:
                query += f" ORDER BY {', '.join(group_fields)}"
        
        if self.debug_mode:
            print(f"\n{'='*60}")
            print(f"🔍 GENERATED SQL QUERY")
            print(f"{'='*60}")
            print(f"SQL: {query}")
            print(f"Params: {params}")
            print(f"{'='*60}\n")
        
        return query, tuple(params), value_label
    
    def get_statistics(self, query: str) -> Dict[str, Any]:
        """자연어 쿼리로 통계 조회"""
        if self.debug_mode:
            print(f"\n{'='*80}")
            print(f"📊 STATISTICS QUERY START")
            print(f"{'='*80}")
            print(f"User Query: '{query}'")
            print(f"{'='*80}\n")
        
        # 쿼리 파싱
        conditions = self.parse_statistics_query(query)
        
        # SQL 생성 및 실행
        sql_query, params, value_label = self.build_sql_query(conditions)
        results = self._execute_query(sql_query, params)
        
        if self.debug_mode:
            print(f"\n✅ Query returned {len(results)} rows")
            if results:
                print(f"First few results: {results[:5]}")
        
        # 결과 구조화
        statistics = {
            'query_conditions': conditions,
            'sql_query': sql_query,
            'sql_params': params,
            'results': results,
            'value_label': value_label,
            'is_error_time_query': conditions['is_error_time_query'],
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
                'parsed_conditions': conditions,
                'sql_query': sql_query,
                'sql_params': params,
                'result_count': len(results)
            }
        }
        
        # 결과 집계
        for row in results:
            value = row.get('total_value', 0) or 0
            statistics['total_value'] += value
            
            if 'year' in row and row['year']:
                year_key = row['year']
                statistics['yearly_stats'][year_key] = statistics['yearly_stats'].get(year_key, 0) + value
            
            if 'month' in row and row['month']:
                month_key = row['month']
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
                statistics['grade_stats'][row['incident_grade']] = value
            
            if 'cause_type' in row and row['cause_type']:
                statistics['cause_type_stats'][row['cause_type']] = value
        
        # 전체 건수
        if not conditions['group_by'] and results:
            statistics['total_count'] = results[0].get('total_value', 0)
            statistics['total_value'] = results[0].get('total_value', 0)
        else:
            if conditions['is_error_time_query']:
                statistics['total_count'] = len(results)
            else:
                statistics['total_count'] = statistics['total_value']
        
        if self.debug_mode:
            print(f"\n{'='*80}")
            print(f"📈 STATISTICS RESULT")
            print(f"{'='*80}")
            print(f"Total Value: {statistics['total_value']}")
            print(f"Total Count: {statistics['total_count']}")
            if statistics['yearly_stats']:
                print(f"Yearly Stats: {statistics['yearly_stats']}")
            if statistics['monthly_stats']:
                print(f"Monthly Stats: {statistics['monthly_stats']}")
            if statistics['grade_stats']:
                print(f"Grade Stats: {statistics['grade_stats']}")
            if statistics['cause_type_stats']:
                print(f"Cause Type Stats: {statistics['cause_type_stats']}")
            if statistics['time_stats']['daynight']:
                print(f"Daynight Stats: {statistics['time_stats']['daynight']}")
            if statistics['time_stats']['week']:
                print(f"Week Stats: {statistics['time_stats']['week']}")
            print(f"{'='*80}\n")
        
        return statistics
    
    def get_incident_details(self, conditions: Dict[str, Any], limit: int = 100) -> List[Dict[str, Any]]:
        """조건에 맞는 장애 상세 내역 조회 - 정규화된 데이터 형식 지원"""
        where_clauses = []
        params = []
        
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
        
        if conditions.get('cause_type'):
            where_clauses.append("cause_type LIKE ?")
            params.append(f"%{conditions['cause_type']}%")
        
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
        
        if conditions.get('service_name'):
            where_clauses.append("service_name LIKE ?")
            params.append(f"%{conditions['service_name']}%")
        
        if conditions.get('owner_depart'):
            where_clauses.append("owner_depart LIKE ?")
            params.append(f"%{conditions['owner_depart']}%")
        
        query = "SELECT * FROM incidents"
        if where_clauses:
            query += f" WHERE {' AND '.join(where_clauses)}"
        query += f" ORDER BY error_date DESC, error_time DESC LIMIT {limit}"
        
        if self.debug_mode:
            print(f"\n🔎 get_incident_details SQL: {query}")
            print(f"Params: {params}\n")
        
        return self._execute_query(query, tuple(params))
    
    def _normalize_query_synonyms(self, query: str) -> str:
        """쿼리의 동의어들을 표준 형태로 정규화"""
        # 동의어 매핑 사전 - 더 포괄적으로 확장
        synonym_mappings = {
            # 건수 관련 동의어
            '장애건수': '건수',
            '장애 건수': '건수', 
            '발생건수': '건수',
            '발생 건수': '건수',
            '장애 개수': '건수',
            '장애개수': '건수',
            
            # 질문 표현 정규화
            '몇건이야': '몇건',
            '몇건이니': '몇건',
            '몇건인가': '몇건',
            '몇건인지': '몇건',
            '몇건이나': '몇건',
            '몇개야': '몇건',
            '몇개인가': '몇건',
            '몇개인지': '몇건',
            '몇개나': '몇건',
            
            # 발생 관련 동의어
            '발생했어': '발생',
            '발생했나': '발생',
            '발생했는지': '발생',
            '발생한지': '발생',
            '생겼어': '발생',
            '생긴': '발생',
            '난': '발생',
            '일어난': '발생',
            '있어': '발생',
            '있나': '발생',
            '있는지': '발생',
            '있었어': '발생',
            
            # 요청 표현 정규화
            '알려줘': '알려주세요',
            '보여줘': '알려주세요',
            '말해줘': '알려주세요',
            '확인해줘': '알려주세요',
            '체크해줘': '알려주세요',
            
            # 정도 표현 정규화
            '얼마나': '몇',
            '어느정도': '몇',
            '어떻게': '몇',
            '어느': '몇',
            '어떤': '몇',
            
            # 수량 표현 정규화
            '몇번': '몇건',
            '몇차례': '몇건',
            '몇회': '몇건',
            '수량': '건수',
            '숫자': '건수',
            '개수': '건수',
            
            # 총합 표현 정규화
            '총': '전체',
            '총합': '전체',
            '모든': '전체',
            '모두': '전체',
            '누적': '전체',
            
            # 상황/현황 표현 정규화
            '상황': '현황',
            '현재': '현황',
            '지금까지': '현황',
            '정도': '현황',
            '수준': '현황',
            '범위': '현황',
            '규모': '현황',
        }
        
        normalized = query
        for old_term, new_term in synonym_mappings.items():
            normalized = normalized.replace(old_term, new_term)
        
        return normalized