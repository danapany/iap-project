import streamlit as st
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
import os
import json
import traceback
import datetime
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
# 장애 및 이상징후 인덱스 설정
incident_index = os.getenv("INDEX_SINGLE_NAME")  # 장애 인덱스
sign_index = os.getenv("INDEX_SIGN_NAME")        # 이상징후 인덱스

# Reranker 기반 검색 품질 향상을 위한 설정 - 수정된 임계값
SEARCH_SCORE_THRESHOLD = 0.3      # 0.5 → 0.3 (더 관대하게)
RERANKER_SCORE_THRESHOLD = 1.5    # 2.0 → 1.5 (더 관대하게)  
HYBRID_SCORE_THRESHOLD = 0.5      # 0.7 → 0.5 (더 관대하게)
MAX_INITIAL_RESULTS = 20          # 초기 검색 결과 수 (Reranker 입력용)
MAX_FINAL_RESULTS = 8             # 5 → 8 (최종 선별 문서 수 증가)

# 세션 상태 초기화 (토글 기본값 설정 및 오류 로그 추가)
if 'search_type' not in st.session_state:
    st.session_state.search_type = "장애"  # 기본값: 장애

if 'error_logs' not in st.session_state:
    st.session_state.error_logs = []

if 'show_error_logs' not in st.session_state:
    st.session_state.show_error_logs = False

# 오류 로깅 함수
def log_error(error_type, error_message, function_name="", additional_info=""):
    """오류를 세션 상태에 로그로 저장"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    error_log = {
        "timestamp": timestamp,
        "error_type": error_type,
        "error_message": str(error_message),
        "function_name": function_name,
        "additional_info": additional_info,
        "traceback": traceback.format_exc()
    }
    st.session_state.error_logs.append(error_log)
    
    # 최근 50개 로그만 유지
    if len(st.session_state.error_logs) > 50:
        st.session_state.error_logs = st.session_state.error_logs[-50:]

# 오류 로그 표시 함수
def display_error_logs():
    """오류 로그를 표시"""
    if not st.session_state.error_logs:
        st.info("📋 저장된 오류 로그가 없습니다.")
        return
    
    st.error(f"🚨 총 {len(st.session_state.error_logs)}개의 오류 로그가 있습니다.")
    
    for i, log in enumerate(reversed(st.session_state.error_logs)):
        with st.expander(f"❌ 오류 #{len(st.session_state.error_logs)-i}: {log['error_type']} ({log['timestamp']})", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**시간**: {log['timestamp']}")
                st.write(f"**함수**: {log['function_name']}")
                st.write(f"**타입**: {log['error_type']}")
            with col2:
                st.write(f"**추가정보**: {log['additional_info']}")
                
            st.write(f"**오류 메시지**:")
            st.code(log['error_message'], language="text")
            
            if log['traceback'].strip() != "NoneType: None":
                st.write(f"**상세 트레이스백**:")
                st.code(log['traceback'], language="python")

# 메인 페이지 제목
st.title("🤖 트러블 체이서 챗봇")
st.write("신속한 장애복구를 위해서 서비스정보를 입력하고 복구방법과 유사사례에 대한 이력을 확인해보세요!")

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
* 공지사항 : 공지사항(notice_text) 요약하지 않고 원본 그대로 테두리있는 텍스트박스 안에 내용을 출력해주세요
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
그리고 년도나 날짜 질문은 발생일자 기준으로 답변하여 요청한 날짜 기준에 포함되지 않는것은 반드시 제외되도록 날짜에 대한 부분을 천천히 잘 생각해서 답변하세요
답변은 한국어로 사용자가 알기쉽게 답변하여 관련 내역은 '출력형식'을 시각적으로 이해하기 쉽도록 하단에 항상포함해주세요
만약 제공된 문서에서 관련 정보를 찾을 수 없다면, 그렇게 명시해주세요.

## 출력형식
###### 답변 : 요청주신 질문의 답변을 요약하여 작성해주세요.
###### 장애내역 (필요시)
1. 장애 ID: INM23022026178
* 서비스명: KT AICC SaaS/PaaS
* 발생일자: 2023-01-20
* 장애현상: 로그인 시 토큰갱신 지연
* 장애원인: 비정상 동작으로 인한 토큰갱신 지연
* 복구방법: 과다 호출 특정 매장 사이트 차단 조치 후 정상화
* 장애등급: 4등급
'-- 주의: 답변은 AI 해석에 따른 오류가 포함될 수 있음을 감안하시고 활용부탁드립니다. --'
""",

}

# 동적 임계값 시스템
def get_dynamic_thresholds(query_type, query_text):
    """쿼리 타입과 내용에 따라 동적으로 임계값 조정"""
    try:
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
    except Exception as e:
        log_error("ThresholdError", e, "get_dynamic_thresholds", f"query_type: {query_type}, query_text: {query_text[:100]}...")
        # 기본값 반환
        return {
            'search_threshold': 0.3,
            'reranker_threshold': 1.5,
            'hybrid_threshold': 0.5,
            'max_results': 8
        }

# Azure 클라이언트 초기화 (두 개의 인덱스 지원)
@st.cache_resource
def init_clients(openai_endpoint, openai_key, openai_api_version, search_endpoint, search_key, incident_index, sign_index):
    try:
        # Azure OpenAI 클라이언트 설정 (새로운 방식)
        azure_openai_client = AzureOpenAI(
            azure_endpoint=openai_endpoint,
            api_key=openai_key,
            api_version=openai_api_version
        )
        
        # Azure AI Search 클라이언트 설정 (장애용)
        incident_search_client = SearchClient(
            endpoint=search_endpoint,
            index_name=incident_index,
            credential=AzureKeyCredential(search_key)
        )
        
        # Azure AI Search 클라이언트 설정 (이상징후용)
        sign_search_client = SearchClient(
            endpoint=search_endpoint,
            index_name=sign_index,
            credential=AzureKeyCredential(search_key)
        ) if sign_index else None
        
        return azure_openai_client, incident_search_client, sign_search_client, True
    except Exception as e:
        log_error("ClientInitError", e, "init_clients", f"endpoints: {openai_endpoint}, {search_endpoint}")
        st.error(f"클라이언트 초기화 실패: {str(e)}")
        return None, None, None, False

# 현재 선택된 타입에 따른 검색 클라이언트 반환
def get_current_search_client():
    """현재 선택된 검색 타입에 따른 클라이언트 반환"""
    try:
        if st.session_state.search_type == "장애":
            return incident_search_client
        else:  # 이상징후
            return sign_search_client
    except Exception as e:
        log_error("ClientSelectionError", e, "get_current_search_client", f"search_type: {st.session_state.search_type}")
        return None

# 하이브리드 점수 계산 함수
def calculate_hybrid_score(search_score, reranker_score):
    """검색 점수와 Reranker 점수를 조합하여 하이브리드 점수 계산"""
    try:
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
    except Exception as e:
        log_error("ScoreCalculationError", e, "calculate_hybrid_score", f"search_score: {search_score}, reranker_score: {reranker_score}")
        return search_score  # 오류 시 검색 점수만 반환

# 동적 임계값을 적용한 고급 문서 필터링 함수
def advanced_filter_documents(documents, query_type="default", query_text=""):
    """동적 임계값을 적용한 고급 필터링"""
    try:
        # 동적 임계값 획득
        thresholds = get_dynamic_thresholds(query_type, query_text)
        
        filtered_docs = []
        filter_stats = {
            'total': len(documents),
            'search_filtered': 0,
            'reranker_qualified': 0,
            'hybrid_qualified': 0,
            'final_selected': 0
        }
        
        for doc in documents:
            try:
                search_score = doc.get('score', 0)
                reranker_score = doc.get('reranker_score', 0)
                
                # 1단계: 기본 검색 점수 필터링 (동적 임계값 적용)
                if search_score < thresholds['search_threshold']:
                    continue
                filter_stats['search_filtered'] += 1
                
                # 2단계: Reranker 점수 우선 평가 (동적 임계값 적용)
                if reranker_score >= thresholds['reranker_threshold']:
                    filter_stats['reranker_qualified'] += 1
                    doc['filter_reason'] = f"Reranker 고품질 (점수: {reranker_score:.2f})"
                    doc['final_score'] = reranker_score
                    doc['quality_tier'] = 'Premium'
                    filtered_docs.append(doc)
                    filter_stats['final_selected'] += 1
                    continue
                
                # 3단계: 하이브리드 점수 평가 (동적 임계값 적용)
                hybrid_score = calculate_hybrid_score(search_score, reranker_score)
                if hybrid_score >= thresholds['hybrid_threshold']:
                    filter_stats['hybrid_qualified'] += 1
                    doc['filter_reason'] = f"하이브리드 점수 통과 (점수: {hybrid_score:.2f})"
                    doc['final_score'] = hybrid_score
                    doc['quality_tier'] = 'Standard'
                    filtered_docs.append(doc)
                    filter_stats['final_selected'] += 1
            except Exception as e:
                log_error("DocumentFilterError", e, "advanced_filter_documents", f"processing document: {doc.get('incident_id', 'unknown')}")
                continue
        
        # 점수 기준으로 정렬 (높은 점수 우선)
        try:
            filtered_docs.sort(key=lambda x: x.get('final_score', 0), reverse=True)
        except Exception as e:
            log_error("DocumentSortError", e, "advanced_filter_documents", "sorting filtered documents")
        
        # 최종 결과 수 제한 (동적 적용)
        final_docs = filtered_docs[:thresholds['max_results']]
        
        # 필터링 통계 표시 (임계값 정보 포함)
        st.info(f"""
        📊 **동적 임계값 기반 문서 필터링 결과** ({st.session_state.search_type})
        - 🎯 적용된 임계값: 검색({thresholds['search_threshold']}) | Reranker({thresholds['reranker_threshold']}) | 하이브리드({thresholds['hybrid_threshold']})
        - 🔍 전체 검색 결과: {filter_stats['total']}개
        - ✅ 기본 점수 통과: {filter_stats['search_filtered']}개
        - 🏆 Reranker 고품질: {filter_stats['reranker_qualified']}개
        - 🎯 하이브리드 통과: {filter_stats['hybrid_qualified']}개
        - 📋 최종 선별: {len(final_docs)}개
        """)
        
        return final_docs
    except Exception as e:
        log_error("FilteringError", e, "advanced_filter_documents", f"query_type: {query_type}, documents count: {len(documents) if documents else 0}")
        return documents[:8] if documents else []  # 오류 시 원본 문서 일부 반환

# 검색 필드 설정 (타입별로 다름)
def get_search_fields(search_type):
    """검색 타입에 따른 필드 설정"""
    try:
        if search_type == "장애":
            return {
                'select': [
                    "incident_id", "service_name", "error_time", "notice_text", 
                    "error_date", "week", "daynight", "incident_cause", "incident_repair", 
                    "incident_plan", "cause_type", "done_type", "incident_grade", 
                    "owner_depart", "fail_type", "year", "month"
                ],
                'search_fields': [
                    "notice_text", "error_date", "week", "daynight", "incident_cause", "incident_repair", 
                    "incident_plan", "service_name", "cause_type", 
                    "done_type", "owner_depart", "year", "month"
                ],
                'semantic_config': "iap-incident-single-meaning"
            }
        else:  # 이상징후 - 실제 인덱스 필드명에 맞게 수정
            return {
                'select': [
                    "incident_id", "service_name", "error_time", "notice_text", 
                    "error_date", "week", "daynight", "incident_cause", "incident_repair", 
                    "incident_plan", "cause_type", "done_type", "incident_grade", 
                    "owner_depart", "fail_type", "year", "month"
                ],
                'search_fields': [
                    "notice_text", "error_date", "week", "daynight", "incident_cause", "incident_repair", 
                    "incident_plan", "service_name", "cause_type", 
                    "done_type", "owner_depart", "year", "month"
                ],
                'semantic_config': "iap-incident-sign-meaning"  # 이상징후도 동일한 시맨틱 설정 사용
            }
    except Exception as e:
        log_error("FieldConfigError", e, "get_search_fields", f"search_type: {search_type}")
        # 기본 설정 반환
        return {
            'select': ["*"],
            'search_fields': ["*"],
            'semantic_config': "default"
        }

# 동적 임계값을 적용한 시맨틱 검색 함수
def semantic_search_with_reranker(search_client, query, query_type="default", top_k=MAX_INITIAL_RESULTS):
    """동적 임계값을 적용한 고품질 시맨틱 검색"""
    try:
        st.info(f"🔄 1단계: {top_k}개 초기 검색 결과 수집 중... ({st.session_state.search_type})")
        
        # 검색 필드 설정
        fields_config = get_search_fields(st.session_state.search_type)
        
        # 시맨틱 검색 실행 (더 많은 후보 확보)
        results = search_client.search(
            search_text=query,
            top=top_k,
            query_type="semantic",
            semantic_configuration_name=fields_config['semantic_config'],
            include_total_count=True,
            select=fields_config['select']
        )
        
        documents = []
        for result in results:
            try:
                # 장애와 이상징후 모두 동일한 필드명 사용
                documents.append({
                    "incident_id": result.get("incident_id", ""),
                    "service_name": result.get("service_name", ""),
                    "error_time": result.get("error_time", ""),
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
            except Exception as e:
                log_error("DocumentParsingError", e, "semantic_search_with_reranker", f"parsing result: {result}")
                continue
        
        st.info(f"🎯 2단계: 동적 임계값 기반 고품질 문서 선별 중...")
        
        # 동적 임계값 기반 필터링 적용
        filtered_documents = advanced_filter_documents(documents, query_type, query)
        
        return filtered_documents
        
    except Exception as e:
        log_error("SemanticSearchError", e, "semantic_search_with_reranker", f"query: {query[:100]}..., query_type: {query_type}")
        st.warning(f"시맨틱 검색 실패, 일반 검색으로 대체: {str(e)}")
        return search_documents_with_reranker(search_client, query, query_type, top_k)

# 일반 검색도 동적 임계값 적용
def search_documents_with_reranker(search_client, query, query_type="default", top_k=MAX_INITIAL_RESULTS):
    """일반 검색에 동적 임계값 적용"""
    try:
        st.info(f"🔄 1단계: {top_k}개 초기 검색 결과 수집 중... ({st.session_state.search_type})")
        
        # 검색 필드 설정
        fields_config = get_search_fields(st.session_state.search_type)
        
        results = search_client.search(
            search_text=query,
            top=top_k,
            include_total_count=True,
            select=fields_config['select'],
            search_fields=fields_config['search_fields']
        )
        
        documents = []
        for result in results:
            try:
                # 장애와 이상징후 모두 동일한 필드명 사용
                documents.append({
                    "incident_id": result.get("incident_id", ""),
                    "service_name": result.get("service_name", ""),
                    "error_time": result.get("error_time", ""),
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
            except Exception as e:
                log_error("DocumentParsingError", e, "search_documents_with_reranker", f"parsing result: {result}")
                continue
        
        st.info(f"🎯 2단계: 동적 임계값 기반 고품질 문서 선별 중...")
        
        # 동적 임계값 기반 필터링 적용
        filtered_documents = advanced_filter_documents(documents, query_type, query)
        
        return filtered_documents
        
    except Exception as e:
        log_error("SearchError", e, "search_documents_with_reranker", f"query: {query[:100]}..., query_type: {query_type}")
        st.error(f"검색 실패: {str(e)}")
        return []

# 대체 검색 함수 (매우 관대한 기준)
def search_documents_fallback(search_client, query, top_k=15):
    """매우 관대한 기준의 대체 검색"""
    try:
        # 검색 필드 설정
        fields_config = get_search_fields(st.session_state.search_type)
        
        results = search_client.search(
            search_text=query,
            top=top_k,
            include_total_count=True,
            select=fields_config['select']
        )
        
        documents = []
        for result in results:
            try:
                score = result.get("@search.score", 0)
                if score >= 0.1:  # 매우 낮은 기준
                    # 장애와 이상징후 모두 동일한 필드명 사용
                    documents.append({
                        "incident_id": result.get("incident_id", ""),
                        "service_name": result.get("service_name", ""),
                        "error_time": result.get("error_time", ""),
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
                        "filter_reason": "대체 검색 통과"
                    })
            except Exception as e:
                log_error("FallbackDocumentParsingError", e, "search_documents_fallback", f"parsing result: {result}")
                continue
        
        return documents[:8]  # 최대 8개까지
        
    except Exception as e:
        log_error("FallbackSearchError", e, "search_documents_fallback", f"query: {query[:100]}...")
        st.error(f"대체 검색 실패: {str(e)}")
        return []

# RAG 응답 생성 - Reranker 정보 포함
def generate_rag_response_with_reranker(azure_openai_client, query, documents, model_name, query_type="default"):
    try:
        # 검색된 문서들을 컨텍스트로 구성 (품질 정보 포함)
        context_parts = []
        for i, doc in enumerate(documents):
            try:
                final_score = doc.get('final_score', 0)
                quality_tier = doc.get('quality_tier', 'Standard')
                filter_reason = doc.get('filter_reason', '기본 선별')
                
                if st.session_state.search_type == "장애":
                    context_part = f"""문서 {i+1} [{quality_tier}급 - {filter_reason}]:
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
                else:  # 이상징후
                    context_part = f"""문서 {i+1} [{quality_tier}급 - {filter_reason}]:
징후 ID: {doc['incident_id']}
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
            except Exception as e:
                log_error("ContextBuildingError", e, "generate_rag_response_with_reranker", f"processing document {i}: {doc.get('incident_id', 'unknown')}")
                continue
        
        context = "\n\n".join(context_parts)
        
        # 질문 타입에 따른 시스템 프롬프트 선택 (이상징후도 동일한 프롬프트 사용)
        system_prompt = SYSTEM_PROMPTS.get(query_type, SYSTEM_PROMPTS["default"])

        user_prompt = f"""
다음 {'장애' if st.session_state.search_type == '장애' else '이상징후'} 이력 문서들을 참고하여 질문에 답변해주세요.
(모든 문서는 동적 임계값 기반 고품질 필터링을 통과한 최고 품질의 검색 결과입니다):

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
            temperature=0.3,
            max_tokens=1500
        )
        
        return response.choices[0].message.content
    
    except Exception as e:
        log_error("RAGResponseError", e, "generate_rag_response_with_reranker", f"query: {query[:100]}..., model: {model_name}")
        error_msg = f"죄송합니다. 응답을 생성하는 중 오류가 발생했습니다: {str(e)}"
        st.error(error_msg)
        return error_msg

# 고급 문서 표시 함수
def display_documents_with_quality_info(documents):
    """품질 정보와 함께 문서 표시"""
    try:
        for i, doc in enumerate(documents):
            try:
                quality_tier = doc.get('quality_tier', 'Standard')
                filter_reason = doc.get('filter_reason', '기본 선별')
                search_score = doc.get('score', 0)
                reranker_score = doc.get('reranker_score', 0)
                final_score = doc.get('final_score', 0)
                
                # 품질 등급에 따른 이모지와 색상
                if quality_tier == 'Premium':
                    tier_emoji = "🏆"
                    tier_color = "🟢"
                else:
                    tier_emoji = "🎯"
                    tier_color = "🟡"
                
                st.markdown(f"### {tier_emoji} **문서 {i+1}** - {quality_tier}급 {tier_color}")
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
                
                # 주요 정보 표시 (타입별 다름)
                col1, col2 = st.columns(2)
                with col1:
                    if st.session_state.search_type == "장애":
                        st.write(f"**장애 ID**: {doc.get('incident_id', '')}")
                        st.write(f"**서비스명**: {doc.get('service_name', '')}")
                        st.write(f"**장애 등급**: {doc.get('incident_grade', '')}")
                    else:  # 이상징후
                        st.write(f"**징후 ID**: {doc.get('incident_id', '')}")
                        st.write(f"**서비스명**: {doc.get('service_name', '')}")
                        st.write(f"**장애 등급**: {doc.get('incident_grade', '')}")
                
                with col2:
                        st.write(f"**원인 유형**: {doc.get('cause_type', '')}")
                        st.write(f"**처리 유형**: {doc.get('done_type', '')}")
                        st.write(f"**담당 부서**: {doc.get('owner_depart', '')}")

                
                # 세부 정보 표시 (타입별 다름)
                if st.session_state.search_type == "장애":
                    if doc.get('notice_text'):
                        st.write(f"**공지사항**: {doc['notice_text'][:200]}...")
                    if doc.get('incident_cause'):
                        st.write(f"**장애 원인**: {doc['incident_cause'][:200]}...")
                    if doc.get('incident_repair'):
                        st.write(f"**복구 방법**: {doc['incident_repair'][:200]}...")
                else:  # 이상징후
                    if doc.get('notice_text'):
                        st.write(f"**징후 설명**: {doc['notice_text'][:200]}...")
                    if doc.get('incident_cause'):
                        st.write(f"**징후 원인**: {doc['incident_cause'][:200]}...")
                    if doc.get('incident_repair'):
                        st.write(f"**대응 조치**: {doc['incident_repair'][:200]}...")
                
                st.markdown("---")
            except Exception as e:
                log_error("DocumentDisplayError", e, "display_documents_with_quality_info", f"displaying document {i}: {doc.get('incident_id', 'unknown')}")
                st.error(f"문서 {i+1} 표시 중 오류 발생")
                continue
    except Exception as e:
        log_error("DisplayError", e, "display_documents_with_quality_info", f"documents count: {len(documents) if documents else 0}")
        st.error("문서 표시 중 오류가 발생했습니다.")

# 입력 검증 함수
def validate_inputs(service_name, incident_symptom):
    """서비스명, 장애현상 입력 검증"""
    try:
        if not service_name or not service_name.strip():
            st.error("❌ 서비스명을 입력해주세요!")
            return False
        if not incident_symptom or not incident_symptom.strip():
            symptom_type = "장애현상" if st.session_state.search_type == "장애" else "이상징후"
            st.error(f"❌ {symptom_type}을 입력해주세요!")
            return False
        return True
    except Exception as e:
        log_error("ValidationError", e, "validate_inputs", f"service_name: {service_name}, incident_symptom: {incident_symptom}")
        return False

# 검색 쿼리 구성 함수
def build_search_query(service_name, incident_symptom):
    """기본 검색 쿼리를 구성"""
    try:
        return f"{service_name} {incident_symptom}"
    except Exception as e:
        log_error("QueryBuildError", e, "build_search_query", f"service_name: {service_name}, incident_symptom: {incident_symptom}")
        return f"{service_name or ''} {incident_symptom or ''}".strip()

# 메인 애플리케이션 로직
if all([azure_openai_endpoint, azure_openai_key, search_endpoint, search_key, incident_index]):
    # 클라이언트 초기화
    azure_openai_client, incident_search_client, sign_search_client, init_success = init_clients(
        azure_openai_endpoint, azure_openai_key, azure_openai_api_version,
        search_endpoint, search_key, incident_index, sign_index
    )
    
    if init_success:
        # st.success("Azure 서비스 연결 성공!")
        
        # =================== 상단 고정 영역 시작 ===================
        with st.container():
           
            # 서비스 정보 입력 섹션
            st.header("📝 서비스 정보 입력")
            
            # 서비스명과 장애현상 입력
            input_col1, input_col2 = st.columns(2)
            
            with input_col1:
                service_name = st.text_input("서비스명을 입력하세요", placeholder="예: 마이페이지, 패밀리박스, 통합쿠폰플랫폼")
            
            with input_col2:
                if st.session_state.search_type == "장애":
                    incident_symptom = st.text_input("장애현상을 입력하세요", placeholder="예: 접속불가, 응답지연, 오류발생")
                else:  # 이상징후
                    incident_symptom = st.text_input("이상징후를 입력하세요", placeholder="예: 응답시간 증가, CPU 사용률 급증, 메모리 누수")
            
            # 입력된 정보 확인 및 표시
            if service_name and incident_symptom:
                symptom_type = "장애현상" if st.session_state.search_type == "장애" else "이상징후"
                st.success(f"서비스: {service_name} | {symptom_type}: {incident_symptom}")
            elif service_name or incident_symptom:
                missing = []
                if not service_name:
                    missing.append("서비스명")
                if not incident_symptom:
                    symptom_type = "장애현상" if st.session_state.search_type == "장애" else "이상징후"
                    missing.append(symptom_type)
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
                    try:
                        if validate_inputs(service_name, incident_symptom):
                            search_query = build_search_query(service_name, incident_symptom)
                            if st.session_state.search_type == "장애":
                                st.session_state.sample_query = f"{search_query}에 대한 장애를 해소하기 위한 근본적인 복구방법만 표기해서 복구방법 안내"
                            else:  # 이상징후
                                st.session_state.sample_query = f"{search_query}에 대한 해소하기 위한 근본적인 복구방법만 표기해서 복구방법 안내"
                            st.session_state.query_type = "repair"
                    except Exception as e:
                        log_error("RepairButtonError", e, "repair_btn", f"service: {service_name}, symptom: {incident_symptom}")
                
            with col2:
                if st.button("🔄 동일 현상에 대한 복구 방법 참조", key="similar_btn"):
                    try:
                        if validate_inputs(service_name, incident_symptom):
                            search_query = build_search_query("", incident_symptom)
                            if st.session_state.search_type == "장애":
                                st.session_state.sample_query = f"{incident_symptom} 동일 현상에 대한 장애를 해소하기 위한 근본적인 복구방법만 표기해서 복구방법 안내"
                            else:  # 이상징후
                                st.session_state.sample_query = f"{incident_symptom} 동일 현상에 대해 해소를 위한 근본적인 복구방법만 표기해서 복구방법 안내"
                            st.session_state.query_type = "similar"
                    except Exception as e:
                        log_error("SimilarButtonError", e, "similar_btn", f"service: {service_name}, symptom: {incident_symptom}")

            # 장애/이상징후 토글 버튼 추가
            st.header("📊 검색 타입 선택")
            
            toggle_col1, toggle_col2 = st.columns(2)
            
            with toggle_col1:
                if st.button("🚨 장애", key="incident_toggle", 
                           help="장애 관련 정보 검색",
                           type="primary" if st.session_state.search_type == "장애" else "secondary"):
                    try:
                        st.session_state.search_type = "장애"
                        st.rerun()
                    except Exception as e:
                        log_error("ToggleError", e, "incident_toggle", "switching to 장애 mode")
            
            with toggle_col2:
                if sign_search_client:  # 이상징후 인덱스가 설정되어 있을 때만 표시
                    if st.button("⚠️ 이상징후", key="sign_toggle", 
                               help="이상징후 관련 정보 검색",
                               type="primary" if st.session_state.search_type == "이상징후" else "secondary"):
                        try:
                            st.session_state.search_type = "이상징후"
                            st.rerun()
                        except Exception as e:
                            log_error("ToggleError", e, "sign_toggle", "switching to 이상징후 mode")
                else:
                    st.button("⚠️ 이상징후", key="sign_toggle_disabled", 
                             help="이상징후 인덱스가 설정되지 않았습니다",
                             disabled=True)
            
            # 현재 선택된 타입 표시
            type_emoji = "🚨" if st.session_state.search_type == "장애" else "⚠️"
            st.info(f"{type_emoji} 현재 선택: **{st.session_state.search_type}** 검색 모드")

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
        
        # 검색 및 응답 처리 함수 (동적 임계값 적용)
        def process_query_with_reranker(query, query_type="default"):
            try:
                # 현재 선택된 검색 클라이언트 가져오기
                current_search_client = get_current_search_client()
                
                if not current_search_client:
                    error_msg = f"❌ {st.session_state.search_type} 검색 클라이언트가 초기화되지 않았습니다."
                    st.error(error_msg)
                    log_error("ClientNotFoundError", error_msg, "process_query_with_reranker", f"search_type: {st.session_state.search_type}")
                    return
                    
                with st.chat_message("assistant"):
                    with st.spinner(f"🎯 동적 임계값 기반 고품질 {st.session_state.search_type} 검색 중..."):
                        # query_type을 검색 함수에 전달
                        documents = semantic_search_with_reranker(current_search_client, query, query_type)
                        
                        if documents:
                            premium_count = sum(1 for doc in documents if doc.get('quality_tier') == 'Premium')
                            standard_count = len(documents) - premium_count
                            basic_count = sum(1 for doc in documents if doc.get('quality_tier') == 'Basic')
                            
                            st.success(f"🏆 {len(documents)}개의 최고품질 {st.session_state.search_type} 문서 선별 완료! (Premium: {premium_count}개, Standard: {standard_count}개, Basic: {basic_count}개)")
                            
                            # 검색된 문서 표시
                            with st.expander(f"🔍 선별된 고품질 {st.session_state.search_type} 문서 보기"):
                                display_documents_with_quality_info(documents)
                            
                            # RAG 응답 생성
                            with st.spinner(f"💡 동적 품질 기반 정확한 {st.session_state.search_type} 답변 생성 중..."):
                                response = generate_rag_response_with_reranker(
                                    azure_openai_client, query, documents, azure_openai_model, query_type
                                )
                                
                                with st.expander(f"🤖 AI {st.session_state.search_type} 답변 보기 (동적 품질 강화)", expanded=True):
                                    st.write(response)
                                    st.info(f"✨ 이 답변은 {st.session_state.search_type} 쿼리 특성에 맞는 동적 품질 기준으로 선별된 문서를 바탕으로 생성되었습니다.")
                                
                                st.session_state.messages.append({"role": "assistant", "content": response})
                        else:
                            # 대체 검색 시도
                            st.warning(f"🔄 동적 임계값으로도 {st.session_state.search_type} 결과가 없어 더 관대한 기준으로 재검색 중...")
                            
                            # 매우 관대한 기준으로 재검색
                            fallback_documents = search_documents_fallback(current_search_client, query)
                            
                            if fallback_documents:
                                st.info(f"📋 대체 검색으로 {len(fallback_documents)}개 {st.session_state.search_type} 문서 발견")
                                response = generate_rag_response_with_reranker(
                                    azure_openai_client, query, fallback_documents, azure_openai_model, query_type
                                )
                                with st.expander(f"🤖 AI {st.session_state.search_type} 답변 보기 (대체 검색)", expanded=True):
                                    st.write(response)
                                    st.warning("⚠️ 이 답변은 관대한 기준으로 선별된 문서를 바탕으로 생성되었습니다.")
                                st.session_state.messages.append({"role": "assistant", "content": response})
                            else:
                                error_msg = f"""
                                🔍 모든 검색 기준으로도 관련 {st.session_state.search_type} 문서를 찾을 수 없습니다.
                                
                                **개선 방안:**
                                - 더 구체적인 키워드 사용
                                - 다른 표현으로 재검색
                                - 검색 범위 확대
                                - 다른 검색 타입({('이상징후' if st.session_state.search_type == '장애' else '장애')}) 시도
                                """
                                with st.expander("🤖 AI 답변 보기", expanded=True):
                                    st.write(error_msg)
                                st.session_state.messages.append({"role": "assistant", "content": error_msg})
                                log_error("NoDocumentsFoundError", "No documents found after all search attempts", "process_query_with_reranker", f"query: {query[:100]}...")
            except Exception as e:
                log_error("ProcessQueryError", e, "process_query_with_reranker", f"query: {query[:100]}..., query_type: {query_type}")
                error_msg = f"🚨 쿼리 처리 중 심각한 오류가 발생했습니다: {str(e)}"
                st.error(error_msg)
                with st.chat_message("assistant"):
                    with st.expander("🤖 AI 답변 보기", expanded=True):
                        st.write(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
        
        # 사용자 입력
        placeholder_text = "질문을 입력하세요 (예: " + (
            "마이페이지 최근 장애 발생일자와 장애원인 알려줘)" if st.session_state.search_type == "장애" 
            else "마이페이지 최근 이상징후와 대응방법 알려줘)"
        )
        user_query = st.chat_input(placeholder_text)
        
        if user_query:
            try:
                st.session_state.messages.append({"role": "user", "content": user_query})
                
                with st.chat_message("user"):
                    st.write(user_query)
                
                process_query_with_reranker(user_query, "default")
            except Exception as e:
                log_error("UserInputError", e, "user_query_processing", f"user_query: {user_query[:100]}...")
                st.error(f"사용자 입력 처리 중 오류 발생: {str(e)}")

        # 주요 질문 처리
        if 'sample_query' in st.session_state:
            try:
                query = st.session_state.sample_query
                query_type = st.session_state.get('query_type', 'default')
                
                del st.session_state.sample_query
                if 'query_type' in st.session_state:
                    del st.session_state.query_type
                
                st.session_state.messages.append({"role": "user", "content": query})
                
                with st.chat_message("user"):
                    st.write(query)
                
                process_query_with_reranker(query, query_type)
                st.rerun()
            except Exception as e:
                log_error("SampleQueryError", e, "sample_query_processing", f"sample_query: {st.session_state.get('sample_query', 'unknown')[:100]}...")
                st.error(f"주요 질문 처리 중 오류 발생: {str(e)}")

    else:
        error_msg = "❌ Azure 서비스 초기화에 실패했습니다. 오류 로그를 확인해주세요."
        st.error(error_msg)
        log_error("InitializationError", "Failed to initialize Azure services", "main", "Check environment variables and credentials")

else:
    missing_vars = []
    if not azure_openai_endpoint: missing_vars.append("OPENAI_ENDPOINT")
    if not azure_openai_key: missing_vars.append("OPENAI_KEY")
    if not search_endpoint: missing_vars.append("SEARCH_ENDPOINT")
    if not search_key: missing_vars.append("SEARCH_API_KEY")
    if not incident_index: missing_vars.append("INDEX_SINGLE_NAME")
    
    error_msg = f"환경변수 설정이 필요합니다: {', '.join(missing_vars)}"
    st.error(error_msg)
    log_error("EnvironmentError", error_msg, "main", f"Missing variables: {missing_vars}")

# 하단에 오류 로그 요약 정보 표시 (사이드바)
if st.session_state.error_logs:
    with st.sidebar:
        st.header("🚨 오류 모니터링")
        recent_errors = st.session_state.error_logs[-5:]  # 최근 5개만
        
        for i, log in enumerate(reversed(recent_errors)):
            st.error(f"**{log['error_type']}** ({log['timestamp'][-8:]})")
            if st.button(f"상세보기 #{len(recent_errors)-i}", key=f"sidebar_error_{len(recent_errors)-i}"):
                st.session_state.show_error_logs = True
                st.rerun()
        
        if len(st.session_state.error_logs) > 5:
            st.info(f"+ {len(st.session_state.error_logs) - 5}개 더 있음")
            
        # 오류 통계
        error_types = {}
        for log in st.session_state.error_logs:
            error_type = log['error_type']
            error_types[error_type] = error_types.get(error_type, 0) + 1
        
        st.write("**오류 통계:**")
        for error_type, count in error_types.items():
            st.write(f"- {error_type}: {count}회")
            
        # 오류 로그 빠른 액션
        if st.button("🔄 페이지 새로고침", key="sidebar_refresh"):
            st.rerun()
            
        if st.button("📋 전체 로그 보기", key="sidebar_show_all"):
            st.session_state.show_error_logs = True
            st.rerun()
            
        if st.button("🗑️ 로그 초기화", key="sidebar_clear"):
            st.session_state.error_logs = []
            st.success("✅ 로그 초기화됨")
            st.rerun()

# 오류 로그 표시 영역 (메인 화면에 추가)
if st.session_state.show_error_logs:
    with st.container():
        st.header("🚨 오류 로그 상세보기")
        
        # 닫기 버튼 추가
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("❌ 닫기", key="close_error_logs"):
                st.session_state.show_error_logs = False
                st.rerun()
        
        display_error_logs()
        st.markdown("---")