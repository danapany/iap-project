import streamlit as st
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
import os
import json
import re
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()


# Streamlit 페이지 설정
st.set_page_config(
    page_title="트러블 체이서 챗봇",
    page_icon="🤖",
    layout="wide"
)

# 환경변수에서 Azure 설정 로드
azure_openai_endpoint = os.getenv("OPENAI_ENDPOINT")
azure_openai_key = os.getenv("OPENAI_KEY")
azure_openai_model = os.getenv("CHAT_MODEL", "iap-gpt-4o-mini")
azure_openai_api_version = os.getenv("OPENAI_API_VERSION", "2024-02-01")

search_endpoint = os.getenv("SEARCH_ENDPOINT")
search_key = os.getenv("SEARCH_API_KEY")
search_index = os.getenv("INDEX_SINGLE_NAME")

# Reranker 기반 검색 품질 향상을 위한 설정 - 수정된 임계값
SEARCH_SCORE_THRESHOLD = 0.3      # 0.5 → 0.3 (더 관대하게)
RERANKER_SCORE_THRESHOLD = 1.5    # 2.0 → 1.5 (더 관대하게)  
HYBRID_SCORE_THRESHOLD = 0.5      # 0.7 → 0.5 (더 관대하게)
MAX_INITIAL_RESULTS = 20          # 초기 검색 결과 수 (Reranker 입력용)
MAX_FINAL_RESULTS = 8             # 5 → 8 (최종 선별 문서 수 증가)

# 메인 페이지 제목
st.title("🤖 트러블 체이서 챗봇")
st.write("신속한 장애복구를 위해서 서비스정보를 입력하고 복구방법과 유사사례에 대한 이력을 확인해보세요!")

# 개선된 서비스명 추출 함수 (모든 특수문자 포함)
def extract_service_name_from_query(query):
    """쿼리에서 서비스명을 추출 - 스페이스바, 대시(-), 슬러쉬(/), 플러스(+), 괄호(), 언더스코어(_) 모두 지원"""
    import re
    
    # 개선된 서비스명 패턴들 (모든 특수문자 포함)
    service_patterns = [
        # 패턴 1: 서비스명 + 키워드 (모든 특수문자 조합)
        r'([A-Za-z][A-Za-z0-9_\-/\+\(\)\s]*[A-Za-z0-9_\-/\+\)])\s+(?:년도별|월별|건수|장애|현상|복구|서비스|통계|발생|이력)',
        
        # 패턴 2: "서비스" 키워드 뒤의 서비스명
        r'서비스.*?([A-Za-z][A-Za-z0-9_\-/\+\(\)\s]*[A-Za-z0-9_\-/\+\)])',
        
        # 패턴 3: 문장 시작 부분의 서비스명
        r'^([A-Za-z][A-Za-z0-9_\-/\+\(\)\s]*[A-Za-z0-9_\-/\+\)])\s+(?!으로|에서|에게|에|을|를|이|가)',
        
        # 패턴 4: 따옴표로 둘러싸인 서비스명
        r'["\']([A-Za-z][A-Za-z0-9_\-/\+\(\)\s]*[A-Za-z0-9_\-/\+\)])["\']',
        
        # 패턴 5: 괄호로 둘러싸인 서비스명
        r'\(([A-Za-z][A-Za-z0-9_\-/\+\s]*[A-Za-z0-9_\-/\+])\)',
        
        # 패턴 6: 슬러쉬로 구분된 서비스명 (path 형태)
        r'([A-Za-z][A-Za-z0-9_\-]*(?:/[A-Za-z0-9_\-]+)+)\s+(?:년도별|월별|건수|장애|현상|복구|서비스|통계|발생|이력)',
        
        # 패턴 7: 플러스로 연결된 서비스명
        r'([A-Za-z][A-Za-z0-9_\-]*(?:\+[A-Za-z0-9_\-]+)+)\s+(?:년도별|월별|건수|장애|현상|복구|서비스|통계|발생|이력)',
        
        # 패턴 8: 단독으로 나타나는 서비스명 (최소 3자 이상)
        r'\b([A-Za-z][A-Za-z0-9_\-/\+\(\)]{2,}(?:\s+[A-Za-z0-9_\-/\+\(\)]+)*)\b'
    ]
    
    for pattern in service_patterns:
        matches = re.findall(pattern, query, re.IGNORECASE)
        for match in matches:
            service_name = match.strip()
            
            # 서비스명 유효성 검증
            if is_valid_service_name(service_name):
                return service_name
    
    return None

def is_valid_service_name(service_name):
    """서비스명이 유효한지 검증"""
    # 기본 조건: 최소 길이 체크
    if len(service_name) < 3:
        return False
    
    # 영문자로 시작해야 함
    if not service_name[0].isalpha():
        return False
    
    # 괄호 검증: 열린 괄호와 닫힌 괄호 수가 일치해야 함
    if service_name.count('(') != service_name.count(')'):
        return False
    
    # 슬러쉬가 연속으로 나오지 않아야 함 (//)
    if '//' in service_name:
        return False
    
    # 플러스가 연속으로 나오지 않아야 함 (++)
    if '++' in service_name:
        return False
    
    # 특수문자로 끝나지 않아야 함 (단, 괄호 제외)
    if service_name[-1] in ['-', '/', '+'] and not service_name.endswith(')'):
        return False
    
    # 서비스명 특성 검증 (다음 중 하나라도 만족해야 함)
    validation_criteria = [
        '_' in service_name,                    # 언더스코어 포함
        '-' in service_name,                    # 하이픈 포함
        '/' in service_name,                    # 슬러쉬 포함
        '+' in service_name,                    # 플러스 포함
        '(' in service_name,                    # 괄호 포함
        any(c.isupper() for c in service_name), # 대문자 포함
        len(service_name) >= 5,                 # 5자 이상
        any(c.isdigit() for c in service_name), # 숫자 포함
        ' ' in service_name.strip(),            # 공백 포함 (양끝 제외)
    ]
    
    if not any(validation_criteria):
        return False
    
    # 제외할 일반적인 단어들
    excluded_words = [
        'service', 'system', 'server', 'client', 'application', 'app',
        'website', 'web', 'platform', 'portal', 'interface', 'api',
        'database', 'data', 'file', 'log', 'error', 'issue', 'problem',
        'http', 'https', 'www', 'com', 'org', 'net',
        '년도별', '월별', '건수', '장애', '현상', '복구', '통계', '발생'
    ]
    
    # 괄호, 슬러쉬, 플러스 등을 제외한 기본 이름 추출해서 검증
    clean_name = re.sub(r'[\(\)/\+_\-\s]', '', service_name).lower()
    if clean_name in excluded_words:
        return False
    
    # 한글이 포함된 경우 제외
    if any('\u3131' <= c <= '\u318E' or '\uAC00' <= c <= '\uD7A3' for c in service_name):
        return False
    
    return True

# 동적 임계값 시스템
def get_dynamic_thresholds(query_type, query_text):
    """쿼리 타입과 내용에 따라 동적으로 임계값 조정"""
    # 년도별, 통계성 쿼리 감지
    year_keywords = ['년도', '년', '월별', '기간', '현황', '통계', '건수', '발생', '발생일자', '언제']
    is_statistical_query = any(keyword in query_text for keyword in year_keywords)
    
    if is_statistical_query or query_type == "default":
        # 통계성 쿼리나 일반 쿼리는 더 관대한 기준 적용
        return {
            'search_threshold': 0.2,
            'reranker_threshold': 1.0,
            'hybrid_threshold': 0.4,
            'max_results': 10
        }
    elif query_type in ["repair", "similar"]:
        # 복구방법이나 유사사례는 품질 중심
        return {
            'search_threshold': 0.4,
            'reranker_threshold': 1.8,
            'hybrid_threshold': 0.6,
            'max_results': 5
        }
    else:
        # 기본값
        return {
            'search_threshold': 0.3,
            'reranker_threshold': 1.5,
            'hybrid_threshold': 0.5,
            'max_results': 8
        }

# Azure 클라이언트 초기화
@st.cache_resource
def init_clients(openai_endpoint, openai_key, openai_api_version, search_endpoint, search_key, search_index):
    try:
        # Azure OpenAI 클라이언트 설정 (새로운 방식)
        azure_openai_client = AzureOpenAI(
            azure_endpoint=openai_endpoint,
            api_key=openai_key,
            api_version=openai_api_version
        )
        
        # Azure AI Search 클라이언트 설정
        search_client = SearchClient(
            endpoint=search_endpoint,
            index_name=search_index,
            credential=AzureKeyCredential(search_key)
        )
        
        return azure_openai_client, search_client, True
    except Exception as e:
        st.error(f"클라이언트 초기화 실패: {str(e)}")
        return None, None, False

# 하이브리드 점수 계산 함수
def calculate_hybrid_score(search_score, reranker_score):
    """검색 점수와 Reranker 점수를 조합하여 하이브리드 점수 계산"""
    if reranker_score > 0:
        # Reranker 점수가 있는 경우: Reranker 점수를 주로 사용하되 검색 점수도 고려
        # Reranker 점수는 보통 0-4 범위이므로 0-1로 정규화
        normalized_reranker = min(reranker_score / 4.0, 1.0)
        # 검색 점수는 이미 0-1 범위
        normalized_search = min(search_score, 1.0)
        
        # 가중평균: Reranker 80%, 검색 점수 20%
        hybrid_score = (normalized_reranker * 0.8) + (normalized_search * 0.2)
    else:
        # Reranker 점수가 없는 경우: 검색 점수만 사용
        hybrid_score = min(search_score, 1.0)
    
    return hybrid_score

# 질문 타입별 시스템 프롬프트 정의
SYSTEM_PROMPTS = {
   "repair": """
당신은 IT서비스 트러블슈팅 전문가입니다. 
입력받은 사용자의 서비스와 현상에 대한 복구방법을 가이드 해주는데,'대상선정원칙'에 따라 대상을 선정하고 복구방법(incident_repair)을 아래의 '출력형식' 대로 유사도가 높은건으로 선정하여 최대 Top 3개 출력하는데 90점이상 되는것중에 유사도가 가장높은건 순서로 Case1, Case2 로 표현해서 출력하는데 천천히 생각하면서 답변을 3회 출력없이 실행해보고 가장 일관성이 있는 답변으로 답변해주세요.

## 대상선정원칙
- 서비스명은 공지사항의 서비스명이 정확히 일치하는 건을 선정
- 접속불가, 접속지연, 처리불가, 처리지연의 검색요청시에는 장애유형(fail_type)을 참조
- 현상은 아래 우선순위를 기반으로 선정

### 우선순위
1. 공지사항(notice_text)에서 '현상'에 대한 내용을 참고
2. 공지사항(notice_text)에서 '영향도'를 참고  
3. 장애원인(incident_cause)에서 '현상 원인'을 참고

## 출력형식
유사 현상으로 발생했던 장애의 복구방법 입니다
Case1. ~~서비스의 ~~~ 장애현상에 대한 복구방법입니다
* 발생일시 : 발생일시(error_date) 출력 (예. 2023-10-01 12:00)
* 장애원인 : 장애원인(incident_cause) 내용을 요약하며 텍스트는 강조하지 마세요
* 장애현상 : '대상선정원칙'에서 참고한 현상으로 내용을 요약히지 원본 그대로 표현하며 텍스트는 강조하여 **텍스트** 로 표현해주세요
* 복구방법 : 복구방법(incident_repair) 내용을 최대 3줄로 요약하며 텍스트는  강조하여 **텍스트** 로 표현해주세요
* 후속과제 : 개선계획(incident_plan) 내용을 요약하며 텍스트는 강조하지 마세요
* 인시던트 ID : 장애 ID(incident_id) 출력
* 참조장애정보는 아래 사항을 표로 출력하는데 타이틀의 영문은 빼줘

| 장애 ID | 서비스명 | 발생일자 | 장애시간 | 장애원인 | 복구방법 | 후속과제 | 처리유형 | 담당부서 |
|---------|----------|---------------|-----------|----------|----------|----------|----------|----------|
""",   
    "similar": """당신은 유사 사례 추천 전문가입니다. 
사용자의 질문에 대해 제공된 장애 이력 문서를 기반으로 정확하고 유용한 답변을 제공해주세요.
답변은 한국어로 작성하며, 구체적인 해결방안이나 원인을 명시해주세요.
장애현상은 공지사항의 '현상'을 참고하고 없으면 '영향도'를 참고해서주세요
장애 ID, 서비스명, 원인, 복구방법 등의 구체적인 정보를 포함하는데 천천히 생각하면서 답변을 3회 출력없이 실행해보고 가장 일관성이 있는 답변을 아래 **출력형식** 으로 답변해주는데 현상관련 부분은 bold로 강조 주세요.
만약 제공된 문서에서 관련 정보를 찾을 수 없다면, 그렇게 명시해주세요.
만약 제공된 문서에서 관련 정보를 찾을 수 있다면 아래내용은 답변 하단에 항상포함해주세요

## 출력형식
### 1. 서비스명 : KT AICC SaaS/PaaS
* 장애 ID: INM23022026178
* 장애 현상: 상담정보 열람불가 (상담 및 웹페이지 접속은 정상) 로 표현
* 장애 원인: mecab 사전에 잘못 등록된 상품명(쌍따옴표")으로 인해 TA 분석 오류 발생. 로 표현
* 복구 방법: 오류 상품명 삭제 및 mecab 리빌드 조치. 로 표현
* 개선 계획: mecab 사전 백업 및 로그 처리, Skip 처리 진행 예정.
* 유사도점수 : 99.5
""",
    
    "default": """당신은 IT 시스템 트러블슈팅 전문가입니다. 
사용자의 질문에 대한 답만 데이터 기반으로 유용한 답변을 정확하고 아래 '출력형식'으로 답변제공해주세요.

## 중요한 필드 정의 (숫자 계산 시 필수 참조)
- error_time: 장애시간(분 단위). 예: 400이면 400분, 60이면 60분
- error_date: 발생일자. 예: 2025-01-15 (YYYY-MM-DD 형식)
- year: 발생년도. 예: 2020, 2021, 2022, 2023, 2024, 2025
- month: 발생월. 예: 1, 2, 12
- incident_grade: 장애등급. 예: 1등급, 2등급, 3등급, 4등급

## 중요! 년도별 집계 계산 원칙
1. **정확한 개수 세기**: 제공된 문서 개수를 정확히 세어야 합니다
2. **년도별 분류**: error_date 또는 year 필드를 기준으로 년도별로 분류
3. **중복 제거**: 동일한 incident_id는 한 번만 카운트
4. **검증**: 년도별 합계가 전체 문서 수와 일치하는지 반드시 확인
5. **실제 건수 우선**: 년도별 합계보다 실제 제공된 문서 수가 정확한 총 건수입니다

## 년도별 집계 검증 절차
1. 먼저 제공된 전체 문서 개수를 정확히 카운트
2. 각 문서의 년도를 확인하여 년도별로 분류
3. 년도별 건수를 합산하여 전체 건수와 일치하는지 확인
4. 불일치 시 문서를 다시 검토하여 정확한 집계 수행
5. 최종 답변에서 "총 N건 (검증 완료)" 형태로 명시

## 숫자 조건 처리 원칙
- "400분 이상"이라고 하면 error_time >= 400 인 건들만 선별하여 카운트
- "2025년"이라고 하면 year = 2025 또는 error_date가 2025년인 건들만 선별하여 년도별 sum으로 답변
- "몇건", "건수", "개수" 질문시에는 조건에 맞는 문서들을 정확히 카운트하고 구체적인 숫자로 답변하는 반드시 '최종 점수'가 높은건으로 선정해서 카운트하세요
- 날짜나 숫자 조건이 있으면 반드시 해당 필드값을 확인하고 조건에 맞지 않는 것은 제외
- 조건을 만족하는 각 건의 상세 정보도 함께 제공

그리고 년도나 날짜 질문은 발생일자 기준으로 답변하여 요청한 날짜 기준에 포함되지 않는것은 반드시 제외되도록 날짜에 대한 부분을 천천히 잘 생각해서 답변하세요
답변은 한국어로 사용자가 알기쉽게 답변하여 관련 내역은 '출력형식'을 시각적으로 이해하기 쉽도록 하단에 항상포함해주세요
만약 제공된 문서에서 관련 정보를 찾을 수 없다면, 그렇게 명시해주세요.

## 출력형식
###### 답변 : 요청주신 질문의 답변을 요약하여 작성해주세요. 
- 전체 건수를 먼저 명시: "총 N건"
- 년도별 건수를 정확히 계산하여 제시
- 년도별 합계가 전체 건수와 일치함을 확인하여 명시: "총 N건 (검증 완료)"

###### 조건에 맞는 장애내역 (필요시)
1. 장애 ID: INM23022026178
* 서비스명: KT AICC SaaS/PaaS
* 발생일자: 2023-01-20
* 장애시간: 400분
* 장애현상: 로그인 시 토큰갱신 지연
* 장애원인: 비정상 동작으로 인한 토큰갱신 지연
* 복구방법: 과다 호출 특정 매장 사이트 차단 조치 후 정상화
* 장애등급: 4등급

2. 장애 ID: INM23022026179
* 서비스명: 마이페이지
* 발생일자: 2025-02-10
* 장애시간: 500분
* 장애현상: 페이지 로딩 불가
* 장애원인: DB 커넥션 풀 고갈
* 복구방법: DB 재시작 및 커넥션 풀 재설정
* 장애등급: 2등급

'-- 주의: 답변은 AI 해석에 따른 오류가 포함될 수 있음을 감안하시고 활용부탁드립니다. --'
"""
}

# 서비스명 포함 매칭을 지원하는 개선된 필터링 함수
def advanced_filter_documents_v3(documents, query_type="default", query_text="", target_service_name=None):
    """서비스명 포함 매칭을 지원하는 개선된 필터링"""
    
    # 동적 임계값 획득
    thresholds = get_dynamic_thresholds(query_type, query_text)
    
    filtered_docs = []
    filter_stats = {
        'total': len(documents),
        'search_filtered': 0,
        'service_exact_match': 0,
        'service_partial_match': 0,
        'service_filtered': 0,
        'reranker_qualified': 0,
        'hybrid_qualified': 0,
        'final_selected': 0
    }
    
    excluded_docs = []  # 제외된 문서 추적
    
    for doc in documents:
        search_score = doc.get('score', 0)
        reranker_score = doc.get('reranker_score', 0)
        
        # 1단계: 기본 검색 점수 필터링 (동적 임계값 적용)
        if search_score < thresholds['search_threshold']:
            continue
        filter_stats['search_filtered'] += 1
        
        # 2단계: 서비스명 포함 매칭 (개선된 방식)
        if target_service_name:
            doc_service_name = doc.get('service_name', '').strip()
            
            # 정확한 매칭 우선 확인
            if doc_service_name.lower() == target_service_name.lower():
                filter_stats['service_exact_match'] += 1
                doc['service_match_type'] = 'exact'
            # 포함 매칭 확인
            elif target_service_name.lower() in doc_service_name.lower() or doc_service_name.lower() in target_service_name.lower():
                filter_stats['service_partial_match'] += 1
                doc['service_match_type'] = 'partial'
            else:
                excluded_docs.append({
                    'incident_id': doc.get('incident_id', ''),
                    'service_name': doc_service_name,
                    'expected_service': target_service_name,
                    'reason': '서비스명 불일치 (정확/포함 모두 해당없음)'
                })
                continue
        else:
            doc['service_match_type'] = 'all'
            
        filter_stats['service_filtered'] += 1
        
        # 3단계: Reranker 점수 우선 평가 (동적 임계값 적용)
        if reranker_score >= thresholds['reranker_threshold']:
            filter_stats['reranker_qualified'] += 1
            match_type = doc.get('service_match_type', 'unknown')
            doc['filter_reason'] = f"서비스명 {match_type} 매칭 + Reranker 고품질 (점수: {reranker_score:.2f})"
            doc['final_score'] = reranker_score
            doc['quality_tier'] = 'Premium'
            filtered_docs.append(doc)
            filter_stats['final_selected'] += 1
            continue
        
        # 4단계: 하이브리드 점수 평가 (동적 임계값 적용)
        hybrid_score = calculate_hybrid_score(search_score, reranker_score)
        if hybrid_score >= thresholds['hybrid_threshold']:
            filter_stats['hybrid_qualified'] += 1
            match_type = doc.get('service_match_type', 'unknown')
            doc['filter_reason'] = f"서비스명 {match_type} 매칭 + 하이브리드 점수 통과 (점수: {hybrid_score:.2f})"
            doc['final_score'] = hybrid_score
            doc['quality_tier'] = 'Standard'
            filtered_docs.append(doc)
            filter_stats['final_selected'] += 1
    
    # 정확한 매칭을 우선으로 정렬 (exact > partial), 그 다음 점수순
    def sort_key(doc):
        match_priority = {'exact': 3, 'partial': 2, 'all': 1}
        return (match_priority.get(doc.get('service_match_type', 'all'), 0), doc['final_score'])
    
    filtered_docs.sort(key=sort_key, reverse=True)
    
    # 최종 결과 수 제한 (동적 적용)
    final_docs = filtered_docs[:thresholds['max_results']]
   
    # 개선된 필터링 통계 표시 (포함 매칭 정보 포함)
    st.info(f"""
    📊 **서비스명 포함 매칭 기반 문서 필터링 결과**
    - 🎯 대상 서비스: {target_service_name or '전체 서비스'}
    - 🎯 적용된 임계값: 검색({thresholds['search_threshold']}) | Reranker({thresholds['reranker_threshold']}) | 하이브리드({thresholds['hybrid_threshold']})
    - 🔍 전체 검색 결과: {filter_stats['total']}개
    - ✅ 기본 점수 통과: {filter_stats['search_filtered']}개
    - 🎯 서비스명 정확 매칭: {filter_stats['service_exact_match']}개
    - 🔍 서비스명 포함 매칭: {filter_stats['service_partial_match']}개
    - ✅ 총 서비스명 매칭: {filter_stats['service_filtered']}개
    - 🏆 Reranker 고품질: {filter_stats['reranker_qualified']}개
    - 🎯 하이브리드 통과: {filter_stats['hybrid_qualified']}개
    - 📋 최종 선별: {len(final_docs)}개
    """)
    
    return final_docs

# 서비스명 포함 검색을 지원하는 개선된 시맨틱 검색 함수
def semantic_search_with_service_filter(search_client, query, target_service_name=None, query_type="default", top_k=MAX_INITIAL_RESULTS):
    """서비스명 포함 검색을 지원하는 개선된 시맨틱 검색"""
    try:
        # 서비스명 포함 검색을 위한 검색 쿼리 구성
        if target_service_name:
            # 정확한 매칭과 포함 검색을 모두 지원
            enhanced_query = f'(service_name:"{target_service_name}" OR service_name:*{target_service_name}*)'
            if query != target_service_name:  # 원래 쿼리에 추가 조건이 있는 경우
                enhanced_query += f" AND ({query})"
            st.info(f"🎯 서비스명 포함 검색: {enhanced_query}")
        else:
            enhanced_query = query
            
        st.info(f"🔄 1단계: {top_k}개 초기 검색 결과 수집 중...")
        
        # 시맨틱 검색 실행
        results = search_client.search(
            search_text=enhanced_query,
            top=top_k,
            query_type="semantic",
            semantic_configuration_name="iap-incident-single-meaning",
            include_total_count=True,
            select=[
                "incident_id", "service_name", "error_time", "notice_text", 
                "error_date", "week", "daynight", "incident_cause", "incident_repair", 
                "incident_plan", "cause_type", "done_type", "incident_grade", 
                "owner_depart", "fail_type", "year", "month"
            ]
        )
        
        documents = []
        for result in results:
            documents.append({
                "incident_id": result.get("incident_id", ""),
                "service_name": result.get("service_name", ""),
                "error_time": result.get("error_time", 0),
                "notice_text": result.get("notice_text", ""),
                "error_date": result.get("error_date", ""),
                "week": result.get("week", ""),
                "daynight": result.get("daynight", ""),
                "incident_cause": result.get("incident_cause", ""),
                "incident_repair": result.get("incident_repair", ""),
                "incident_plan": result.get("incident_plan", ""),
                "cause_type": result.get("cause_type", ""),
                "done_type": result.get("done_type", ""),
                "incident_grade": result.get("incident_grade", ""),
                "owner_depart": result.get("owner_depart", ""),
                "fail_type": result.get("fail_type", ""),
                "year": result.get("year", ""),
                "month": result.get("month", ""),
                "score": result.get("@search.score", 0),
                "reranker_score": result.get("@search.reranker_score", 0)
            })
        
        st.info(f"🎯 2단계: 서비스명 포함 매칭 + 동적 임계값 기반 고품질 문서 선별 중...")
        
        # 개선된 필터링 적용 (서비스명 포함 매칭)
        filtered_documents = advanced_filter_documents_v3(documents, query_type, query, target_service_name)
        
        return filtered_documents
        
    except Exception as e:
        st.warning(f"시맨틱 검색 실패, 일반 검색으로 대체: {str(e)}")
        return search_documents_with_service_filter(search_client, query, target_service_name, query_type, top_k)

# 일반 검색에 서비스명 포함 필터링 적용
def search_documents_with_service_filter(search_client, query, target_service_name=None, query_type="default", top_k=MAX_INITIAL_RESULTS):
    """일반 검색에 서비스명 포함 필터링 적용"""
    try:
        # 서비스명 포함 검색을 위한 검색 쿼리 구성
        if target_service_name:
            enhanced_query = f'(service_name:"{target_service_name}" OR service_name:*{target_service_name}*)'
            if query != target_service_name:
                enhanced_query += f" AND ({query})"
        else:
            enhanced_query = query
            
        st.info(f"🔄 1단계: {top_k}개 초기 검색 결과 수집 중...")
        
        results = search_client.search(
            search_text=enhanced_query,
            top=top_k,
            include_total_count=True,
            select=[
                "incident_id", "service_name", "error_time", "notice_text", 
                "error_date", "week", "daynight", "incident_cause", "incident_repair", 
                "incident_plan", "cause_type", "done_type", "incident_grade", 
                "owner_depart", "fail_type", "year", "month"
            ],
            search_fields=[
                "notice_text", "error_date", "week", "daynight", "incident_cause", "incident_repair", 
                "incident_plan", "service_name", "cause_type", 
                "done_type", "owner_depart", "year", "month"
            ]
        )
        
        documents = []
        for result in results:
            documents.append({
                "incident_id": result.get("incident_id", ""),
                "service_name": result.get("service_name", ""),
                "error_time": result.get("error_time", 0),
                "notice_text": result.get("notice_text", ""),
                "error_date": result.get("error_date", ""),
                "week": result.get("week", ""),
                "daynight": result.get("daynight", ""),
                "incident_cause": result.get("incident_cause", ""),
                "incident_repair": result.get("incident_repair", ""),
                "incident_plan": result.get("incident_plan", ""),
                "cause_type": result.get("cause_type", ""),
                "done_type": result.get("done_type", ""),
                "incident_grade": result.get("incident_grade", ""),
                "owner_depart": result.get("owner_depart", ""),
                "fail_type": result.get("fail_type", ""),
                "year": result.get("year", ""),
                "month": result.get("month", ""),
                "score": result.get("@search.score", 0),
                "reranker_score": 0  # 일반 검색에서는 0
            })
        
        st.info(f"🎯 2단계: 서비스명 포함 매칭 + 동적 임계값 기반 고품질 문서 선별 중...")
        
        # 개선된 필터링 적용 (서비스명 포함 매칭)
        filtered_documents = advanced_filter_documents_v3(documents, query_type, query, target_service_name)
        
        return filtered_documents
        
    except Exception as e:
        st.error(f"검색 실패: {str(e)}")
        return []

# 대체 검색 함수 (매우 관대한 기준, 포함 매칭 지원)
def search_documents_fallback(search_client, query, target_service_name=None, top_k=15):
    """매우 관대한 기준의 대체 검색 (포함 매칭 지원)"""
    try:
        # 서비스명 포함 검색을 위한 검색 쿼리 구성
        if target_service_name:
            enhanced_query = f'(service_name:"{target_service_name}" OR service_name:*{target_service_name}*)'
            if query != target_service_name:
                enhanced_query += f" AND ({query})"
        else:
            enhanced_query = query
            
        results = search_client.search(
            search_text=enhanced_query,
            top=top_k,
            include_total_count=True,
            select=[
                "incident_id", "service_name", "error_time", "notice_text", 
                "error_date", "week", "daynight", "incident_cause", "incident_repair", 
                "incident_plan", "cause_type", "done_type", "incident_grade", 
                "owner_depart", "fail_type", "year", "month"
            ]
        )
        
        documents = []
        for result in results:
            score = result.get("@search.score", 0)
            if score >= 0.1:  # 매우 낮은 기준
                doc_service_name = result.get("service_name", "").strip()
                
                # 서비스명 포함 필터링 (대체 검색에서도 적용)
                if target_service_name:
                    if not (doc_service_name.lower() == target_service_name.lower() or 
                           target_service_name.lower() in doc_service_name.lower() or 
                           doc_service_name.lower() in target_service_name.lower()):
                        continue
                    
                documents.append({
                    "incident_id": result.get("incident_id", ""),
                    "service_name": doc_service_name,
                    "error_time": result.get("error_time", 0),
                    "notice_text": result.get("notice_text", ""),
                    "error_date": result.get("error_date", ""),
                    "week": result.get("week", ""),
                    "daynight": result.get("daynight", ""),
                    "incident_cause": result.get("incident_cause", ""),
                    "incident_repair": result.get("incident_repair", ""),
                    "incident_plan": result.get("incident_plan", ""),
                    "cause_type": result.get("cause_type", ""),
                    "done_type": result.get("done_type", ""),
                    "incident_grade": result.get("incident_grade", ""),
                    "owner_depart": result.get("owner_depart", ""),
                    "fail_type": result.get("fail_type", ""),
                    "year": result.get("year", ""),
                    "month": result.get("month", ""),
                    "score": score,
                    "reranker_score": 0,
                    "final_score": score,
                    "quality_tier": "Basic",
                    "filter_reason": "대체 검색 통과 (포함 매칭)",
                    "service_match_type": "partial" if target_service_name else "all"
                })
        
        return documents[:8]  # 최대 8개까지
        
    except Exception as e:
        st.error(f"대체 검색 실패: {str(e)}")
        return []

# 개선된 RAG 응답 생성 - 정확한 집계 정보 포함
def generate_rag_response_with_accurate_count(azure_openai_client, query, documents, model_name, query_type="default"):
    try:
        # 문서 개수 및 년도별 집계 미리 계산
        total_count = len(documents)
        yearly_stats = {}
        
        # 년도별 집계 계산
        for doc in documents:
            # error_date에서 년도 추출 (YYYY-MM-DD 형태)
            error_date = doc.get('error_date', '')
            year_from_date = None
            if error_date and len(error_date) >= 4:
                try:
                    year_from_date = int(error_date[:4])
                except:
                    pass
            
            # year 필드도 확인
            year_from_field = doc.get('year', '')
            if year_from_field:
                try:
                    year_from_field = int(year_from_field)
                except:
                    year_from_field = None
            
            # 우선순위: error_date > year 필드
            final_year = year_from_date or year_from_field
            
            if final_year:
                yearly_stats[final_year] = yearly_stats.get(final_year, 0) + 1
        
        # 집계 검증
        yearly_total = sum(yearly_stats.values())
        
        # 검색된 문서들을 컨텍스트로 구성 (품질 정보 + 집계 정보 포함)
        context_parts = []
        
        # 집계 정보를 컨텍스트 상단에 추가
        stats_info = f"""
=== 정확한 집계 정보 ===
전체 문서 수: {total_count}건
년도별 분포: {dict(sorted(yearly_stats.items()))}
년도별 합계: {yearly_total}건
집계 검증: {'일치' if yearly_total == total_count else '불일치 - 재계산 필요'}
===========================
"""
        context_parts.append(stats_info)
        
        for i, doc in enumerate(documents):
            final_score = doc.get('final_score', 0)
            quality_tier = doc.get('quality_tier', 'Standard')
            filter_reason = doc.get('filter_reason', '기본 선별')
            service_match_type = doc.get('service_match_type', 'unknown')
            
            context_part = f"""문서 {i+1} [{quality_tier}급 - {filter_reason} - {service_match_type} 매칭]:
장애 ID: {doc['incident_id']}
서비스명: {doc['service_name']}
장애시간: {doc['error_time']}
공지사항: {doc['notice_text']}
발생일자: {doc['error_date']}
요일: {doc['week']}
시간대: {doc['daynight']}
장애원인: {doc['incident_cause']}
복구방법: {doc['incident_repair']}
개선계획: {doc['incident_plan']}
원인유형: {doc['cause_type']}
처리유형: {doc['done_type']}
장애등급: {doc['incident_grade']}
담당부서: {doc['owner_depart']}
장애유형: {doc['fail_type']}
년도: {doc['year']}
월: {doc['month']}
품질점수: {final_score:.2f}
"""
            context_parts.append(context_part)
        
        context = "\n\n".join(context_parts)
        
        # 질문 타입에 따른 시스템 프롬프트 선택
        system_prompt = SYSTEM_PROMPTS.get(query_type, SYSTEM_PROMPTS["default"])

        user_prompt = f"""
다음 장애 이력 문서들을 참고하여 질문에 답변해주세요.
(모든 문서는 서비스명 포함 매칭 + 동적 임계값 기반 고품질 필터링을 통과한 검색 결과입니다):

중요! 집계 관련 질문인 경우 위의 "정확한 집계 정보" 섹션을 참조하여 정확한 숫자를 제공하세요.
- 전체 건수: {total_count}건
- 년도별 건수: {dict(sorted(yearly_stats.items()))}
- 반드시 년도별 합계가 전체 건수와 일치하는지 확인하세요.

{context}

질문: {query}

답변:"""

        # Azure OpenAI API 호출
        response = azure_openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,  # 정확한 집계를 위해 temperature 낮춤
            max_tokens=1500
        )
        
        return response.choices[0].message.content
    
    except Exception as e:
        st.error(f"응답 생성 실패: {str(e)}")
        return "죄송합니다. 응답을 생성하는 중 오류가 발생했습니다."

# 서비스명 포함 검색을 지원하는 개선된 쿼리 처리 함수
def process_query_with_enhanced_filtering(query, query_type="default"):
    """서비스명 포함 검색을 지원하는 개선된 쿼리 처리"""
    with st.chat_message("assistant"):
        # 서비스명 추출
        target_service_name = extract_service_name_from_query(query)
        
        if target_service_name:
            st.success(f"🎯 감지된 대상 서비스: **{target_service_name}** (정확/포함 매칭 모두 지원)")
        
        with st.spinner("🎯 서비스명 포함 매칭 + 동적 임계값 기반 고품질 검색 중..."):
            # 개선된 검색 함수 호출
            documents = semantic_search_with_service_filter(
                search_client, query, target_service_name, query_type
            )
            
            if documents:
                # 서비스명 매칭 검증 및 분류
                exact_matches = [doc for doc in documents if doc.get('service_match_type') == 'exact']
                partial_matches = [doc for doc in documents if doc.get('service_match_type') == 'partial']
                
                if exact_matches and partial_matches:
                    st.success(f"✅ '{target_service_name}' 서비스: 정확 매칭 {len(exact_matches)}개, 포함 매칭 {len(partial_matches)}개")
                elif exact_matches:
                    st.success(f"✅ '{target_service_name}' 서비스: 정확 매칭 {len(exact_matches)}개")
                elif partial_matches:
                    st.info(f"📋 '{target_service_name}' 서비스: 포함 매칭 {len(partial_matches)}개")
                elif target_service_name:
                    st.info(f"📋 '{target_service_name}' 관련 {len(documents)}개 문서가 선별되었습니다.")
                
                premium_count = sum(1 for doc in documents if doc.get('quality_tier') == 'Premium')
                standard_count = sum(1 for doc in documents if doc.get('quality_tier') == 'Standard')
                basic_count = sum(1 for doc in documents if doc.get('quality_tier') == 'Basic')
                
                # 집계 관련 질문인지 확인
                is_count_query = any(keyword in query.lower() for keyword in ['건수', '개수', '몇건', '년도별', '월별', '통계', '현황'])
                
                # 집계 미리보기 (집계 관련 질문인 경우)
                if is_count_query:
                    yearly_stats = {}
                    for doc in documents:
                        error_date = doc.get('error_date', '')
                        year_from_date = None
                        if error_date and len(error_date) >= 4:
                            try:
                                year_from_date = int(error_date[:4])
                            except:
                                pass
                        
                        year_from_field = doc.get('year', '')
                        if year_from_field:
                            try:
                                year_from_field = int(year_from_field)
                            except:
                                year_from_field = None
                        
                        final_year = year_from_date or year_from_field
                        if final_year:
                            yearly_stats[final_year] = yearly_stats.get(final_year, 0) + 1
                    
                    yearly_total = sum(yearly_stats.values())
                    st.info(f"""
                    📊 **집계 미리보기**
                    - 전체 건수: {len(documents)}건
                    - 년도별 분포: {dict(sorted(yearly_stats.items()))}
                    - 년도별 합계: {yearly_total}건
                    - 검증 상태: {'✅ 일치' if yearly_total == len(documents) else '❌ 불일치'}
                    """)
                
                st.success(f"🏆 {len(documents)}개의 매칭 문서 선별 완료! (Premium: {premium_count}개, Standard: {standard_count}개, Basic: {basic_count}개)")
                
                # 검색된 문서 표시
                with st.expander("🔍 매칭된 문서 보기"):
                    display_documents_with_quality_info(documents)
                
                # RAG 응답 생성
                with st.spinner("💡 포함 매칭 기반 답변 생성 중..."):
                    response = generate_rag_response_with_accurate_count(
                        azure_openai_client, query, documents, azure_openai_model, query_type
                    )
                    
                    with st.expander("🤖 AI 답변 보기 (포함 매칭 지원)", expanded=True):
                        st.write(response)
                        match_info = "정확/포함 매칭" if exact_matches and partial_matches else "정확 매칭" if exact_matches else "포함 매칭"
                        st.info(f"✨ 이 답변은 '{target_service_name or '모든 서비스'}'에 {match_info}된 문서를 바탕으로 생성되었습니다.")
                    
                    st.session_state.messages.append({"role": "assistant", "content": response})
            else:
                # 대체 검색 시도
                st.warning("🔄 포함 매칭으로도 결과가 없어 더 관대한 기준으로 재검색 중...")
                
                # 매우 관대한 기준으로 재검색 (서비스명 포함 필터링 유지)
                fallback_documents = search_documents_fallback(search_client, query, target_service_name)
                
                if fallback_documents:
                    st.info(f"📋 대체 검색으로 {len(fallback_documents)}개 문서 발견")
                    
                    response = generate_rag_response_with_accurate_count(
                        azure_openai_client, query, fallback_documents, azure_openai_model, query_type
                    )
                    with st.expander("🤖 AI 답변 보기 (대체 검색)", expanded=True):
                        st.write(response)
                        st.warning(f"⚠️ 이 답변은 '{target_service_name or '해당 조건'}'에 대한 관대한 기준의 검색 결과를 바탕으로 생성되었습니다.")
                    st.session_state.messages.append({"role": "assistant", "content": response})
                else:
                    error_msg = f"""
                    🔍 '{target_service_name or '해당 조건'}'에 해당하는 문서를 찾을 수 없습니다.
                    
                    **개선 방안:**
                    - 서비스명의 일부만 입력해보세요 (예: 'API' 대신 'API_Link')
                    - 다른 검색어를 시도해보세요
                    - 전체 검색을 원하시면 서비스명을 제외하고 검색해주세요
                    
                    **참고**: 현재 시스템은 서비스명 정확 매칭과 포함 매칭을 모두 지원합니다.
                    """
                    with st.expander("🤖 AI 답변 보기", expanded=True):
                        st.write(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})

# 고급 문서 표시 함수 (서비스 매칭 타입 정보 포함)
def display_documents_with_quality_info(documents):
    """품질 정보와 서비스 매칭 타입과 함께 문서 표시"""
    for i, doc in enumerate(documents):
        quality_tier = doc.get('quality_tier', 'Standard')
        filter_reason = doc.get('filter_reason', '기본 선별')
        service_match_type = doc.get('service_match_type', 'unknown')
        search_score = doc.get('score', 0)
        reranker_score = doc.get('reranker_score', 0)
        final_score = doc.get('final_score', 0)
        
        # 품질 등급에 따른 이모지와 색상
        if quality_tier == 'Premium':
            tier_emoji = "🏆"
            tier_color = "🟢"
        elif quality_tier == 'Standard':
            tier_emoji = "🎯"
            tier_color = "🟡"
        else:
            tier_emoji = "📋"
            tier_color = "🔵"
        
        # 서비스 매칭 타입에 따른 표시
        match_emoji = {"exact": "🎯", "partial": "🔍", "all": "📋"}.get(service_match_type, "❓")
        match_label = {"exact": "정확 매칭", "partial": "포함 매칭", "all": "전체", "unknown": "알 수 없음"}.get(service_match_type, "알 수 없음")
        
        st.markdown(f"### {tier_emoji} **문서 {i+1}** - {quality_tier}급 {tier_color} {match_emoji} {match_label}")
        st.markdown(f"**선별 기준**: {filter_reason}")
        
        # 점수 정보 표시
        score_col1, score_col2, score_col3 = st.columns(3)
        with score_col1:
            st.metric("검색 점수", f"{search_score:.2f}")
        with score_col2:
            if reranker_score > 0:
                st.metric("Reranker 점수", f"{reranker_score:.2f}")
            else:
                st.metric("Reranker 점수", "N/A")
        with score_col3:
            st.metric("최종 점수", f"{final_score:.2f}")
        
        # 주요 정보 표시
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**장애 ID**: {doc['incident_id']}")
            st.write(f"**서비스명**: {doc['service_name']}")
            st.write(f"**발생일자**: {doc['error_date']}")
            st.write(f"**장애시간**: {doc['error_time']}분")
            
        with col2:
            st.write(f"**장애 등급**: {doc['incident_grade']}")
            st.write(f"**원인 유형**: {doc['cause_type']}")
            st.write(f"**처리 유형**: {doc['done_type']}")
            st.write(f"**담당 부서**: {doc['owner_depart']}")
        
        if doc['notice_text']:
            st.write(f"**공지사항**: {doc['notice_text'][:200]}...")
        if doc['incident_cause']:
            st.write(f"**장애 원인**: {doc['incident_cause'][:200]}...")
        if doc['incident_repair']:
            st.write(f"**복구 방법**: {doc['incident_repair'][:200]}...")
        
        st.markdown("---")

# 입력 검증 함수
def validate_inputs(service_name, incident_symptom):
    """서비스명, 장애현상 입력 검증"""
    if not service_name or not service_name.strip():
        st.error("❌ 서비스명을 입력해주세요!")
        return False
    if not incident_symptom or not incident_symptom.strip():
        st.error("❌ 장애현상을 입력해주세요!")
        return False
    return True

# 검색 쿼리 구성 함수
def build_search_query(service_name, incident_symptom):
    """기본 검색 쿼리를 구성"""
    return f"{service_name} {incident_symptom}"

# 메인 애플리케이션 로직
if all([azure_openai_endpoint, azure_openai_key, search_endpoint, search_key, search_index]):
    # 클라이언트 초기화
    azure_openai_client, search_client, init_success = init_clients(
        azure_openai_endpoint, azure_openai_key, azure_openai_api_version,
        search_endpoint, search_key, search_index
    )
    
    if init_success:
        # =================== 상단 고정 영역 시작 ===================
        with st.container():
           
            # 서비스 정보 입력 섹션
            st.header("📝 서비스 정보 입력")
            
            # 서비스명과 장애현상 입력
            input_col1, input_col2 = st.columns(2)
            
            with input_col1:
                service_name = st.text_input("서비스명을 입력하세요", placeholder="예: API_Link_GW, 마이페이지, 패밀리박스")
            
            with input_col2:
                incident_symptom = st.text_input("장애현상을 입력하세요", placeholder="예: 접속불가, 응답지연, 오류발생")
            
            # 입력된 정보 확인 및 표시
            if service_name and incident_symptom:
                st.success(f"서비스: {service_name} | 장애현상: {incident_symptom}")
            elif service_name or incident_symptom:
                missing = []
                if not service_name:
                    missing.append("서비스명")
                if not incident_symptom:
                    missing.append("장애현상")
                st.info(f"⚠️ {', '.join(missing)}을(를) 입력해주세요.")
            
            # 주요 질문 버튼들
            st.header("🔍 주요 질문")

            # 스타일 CSS 추가
            st.markdown("""
                <style>
                div[data-baseweb="input"] > div {
                    font-size: 40px;
                    height: 40px;
                }
                 
                div.stButton > button:first-child {
                    font-size: 40px;
                    height: 60px;
                    width: 450px;
                    background-color: #4CAF50;
                    color: white;
                    border-radius: 10px;
                }
                </style>
            """, unsafe_allow_html=True)

            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("🔧 서비스와 현상에 대해 복구 방법 안내", key="repair_btn"):
                    if validate_inputs(service_name, incident_symptom):
                        search_query = build_search_query(service_name, incident_symptom)
                        st.session_state.sample_query = f"{search_query}에 대한 장애를 해소하기 위한 근본적인 복구방법만 표기해서 복구방법 안내"
                        st.session_state.query_type = "repair"
                
            with col2:
                if st.button("🔄 동일 현상에 대한 복구 방법 참조", key="similar_btn"):
                    if validate_inputs(service_name, incident_symptom):
                        search_query = build_search_query("", incident_symptom)
                        st.session_state.sample_query = f"{incident_symptom} 동일 현상에 대한 장애를 해소하기 위한 근본적인 복구방법만 표기해서 복구방법 안내"
                        st.session_state.query_type = "similar"

        # =================== 상단 고정 영역 끝 ===================
        
        # 세션 상태 초기화
        if 'messages' not in st.session_state:
            st.session_state.messages = []
        
        # 채팅 메시지 표시 영역
        chat_container = st.container()
        
        with chat_container:
            # 이전 메시지 표시
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    if message["role"] == "assistant":
                        with st.expander("🤖 AI 답변 보기", expanded=True):
                            st.write(message["content"])
                    else:
                        st.write(message["content"])
        
        # 사용자 입력
        user_query = st.chat_input("질문을 입력하세요 (예: API_Link_GW 년도별 건수 알려줘)")
        
        if user_query:
            st.session_state.messages.append({"role": "user", "content": user_query})
            
            with st.chat_message("user"):
                st.write(user_query)
            
            process_query_with_enhanced_filtering(user_query, "default")

        # 주요 질문 처리
        if 'sample_query' in st.session_state:
            query = st.session_state.sample_query
            query_type = st.session_state.get('query_type', 'default')
            
            del st.session_state.sample_query
            if 'query_type' in st.session_state:
                del st.session_state.query_type
            
            st.session_state.messages.append({"role": "user", "content": query})
            
            with st.chat_message("user"):
                st.write(query)
            
            process_query_with_enhanced_filtering(query, query_type)
            st.rerun()

    else:
        st.error("Azure 서비스 연결에 실패했습니다. 환경변수를 확인해주세요.")
        st.info("""
        **필요한 환경변수:**
        - OPENAI_ENDPOINT: Azure OpenAI 엔드포인트
        - OPENAI_KEY: Azure OpenAI API 키
        - OPENAI_API_VERSION: API 버전 (기본값: 2024-02-01)
        - CHAT_MODEL: 모델명 (기본값: iap-gpt-4o-mini)
        - SEARCH_ENDPOINT: Azure AI Search 엔드포인트
        - SEARCH_API_KEY: Azure AI Search API 키
        - INDEX_SINGLE_NAME: 검색 인덱스명
        """)
        
        # 환경변수 상태 표시
        env_status = {
            "OPENAI_ENDPOINT": "✅" if azure_openai_endpoint else "❌",
            "OPENAI_KEY": "✅" if azure_openai_key else "❌", 
            "SEARCH_ENDPOINT": "✅" if search_endpoint else "❌",
            "SEARCH_API_KEY": "✅" if search_key else "❌",
            "INDEX_SINGLE_NAME": "✅" if search_index else "❌"
        }
        
        st.write("**환경변수 상태:**")
        for var, status in env_status.items():
            st.write(f"{status} {var}")

else:
    st.error("환경변수 설정이 필요합니다.")
    st.info("""
    **설정해야 할 환경변수:**
    - OPENAI_ENDPOINT: Azure OpenAI 엔드포인트 URL
    - OPENAI_KEY: Azure OpenAI API 키
    - SEARCH_ENDPOINT: Azure AI Search 엔드포인트 URL  
    - SEARCH_API_KEY: Azure AI Search API 키
    - INDEX_SINGLE_NAME: 검색할 인덱스명
    
    **.env 파일 예시:**
    ```
    OPENAI_ENDPOINT=https://your-openai-resource.openai.azure.com/
    OPENAI_KEY=your-openai-api-key
    OPENAI_API_VERSION=2024-02-01
    CHAT_MODEL=iap-gpt-4o-mini
    SEARCH_ENDPOINT=https://your-search-service.search.windows.net
    SEARCH_API_KEY=your-search-api-key
    INDEX_SINGLE_NAME=your-index-name
    ```
    """)