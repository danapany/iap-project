import streamlit as st
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
import os
import json
from dotenv import load_dotenv
import traceback

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
azure_openai_model = os.getenv("CHAT_MODEL2", "iap-gpt-4o-mini2")
azure_openai_api_version = os.getenv("OPENAI_API_VERSION", "2024-02-01")

search_endpoint = os.getenv("SEARCH_ENDPOINT")
search_key = os.getenv("SEARCH_API_KEY")
search_index = os.getenv("INDEX_REPORT_NAME")

# 메인 페이지 제목
st.title("🤖 트러블 체이서 챗봇")
st.write("2022년 1월~6월 (6개월간)의 장애보고서를 학습시킨 챗봇입니다. 토큰이 많이 사용될수있어서 공용석책임/김용빈선임 외에는 당분간 사용하지 말아주시기 바랍니다.")

# 세션 상태 초기화 (오류 로그용)
if 'error_logs' not in st.session_state:
    st.session_state.error_logs = []
if 'debug_logs' not in st.session_state:
    st.session_state.debug_logs = []

# 오류 로그 표시 함수
def add_error_log(error_msg, error_trace=None):
    timestamp = st.session_state.get('timestamp', 0) + 1
    st.session_state.timestamp = timestamp
    
    error_info = {
        'id': timestamp,
        'message': error_msg,
        'trace': error_trace,
        'timestamp': timestamp
    }
    st.session_state.error_logs.append(error_info)

# 디버그 로그 추가 함수
def add_debug_log(debug_msg):
    timestamp = st.session_state.get('timestamp', 0) + 1
    st.session_state.timestamp = timestamp
    
    debug_info = {
        'id': timestamp,
        'message': debug_msg,
        'timestamp': timestamp
    }
    st.session_state.debug_logs.append(debug_info)

# 오류 및 디버그 로그 표시
if st.session_state.error_logs or st.session_state.debug_logs:
    with st.expander("🚨 오류 및 디버그 로그 (지속 표시)", expanded=True):
        # 오류 로그 정리 버튼
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("🗑️ 로그 정리"):
                st.session_state.error_logs = []
                st.session_state.debug_logs = []
                st.rerun()
        
        # 오류 로그 표시
        if st.session_state.error_logs:
            st.error("**❌ 오류 로그:**")
            for error in st.session_state.error_logs:
                st.error(f"#{error['id']}: {error['message']}")
                if error['trace']:
                    with st.expander(f"스택 트레이스 #{error['id']}", expanded=False):
                        st.code(error['trace'])
        
        # 디버그 로그 표시
        if st.session_state.debug_logs:
            st.info("**ℹ️ 디버그 로그:**")
            for debug in st.session_state.debug_logs:
                st.info(f"#{debug['id']}: {debug['message']}")


# 질문 타입별 시스템 프롬프트 정의
SYSTEM_PROMPTS = {
    "repair": """
당신은 IT서비스 트러블슈팅 전문가입니다. 
제공된 문서는 장애 이력 데이터입니다.

사용자의 서비스와 현상에 대한 복구방법을 가이드 해주는데, 문서 내용에서 장애 정보를 추출하여 유사도가 높은 건으로 선정하여 최대 Top 3개 출력하세요.

## 출력형식
유사 현상으로 발생했던 장애의 복구방법입니다
Case1. 관련 서비스의 장애현상에 대한 복구방법입니다
* 제목 : title 출력
* 장애 내용 : 문서 내용에서 관련 정보 추출하여 요약
* 복구방법 : 문서 내용에서 복구방법 추출하여 **강조** 표시

참고: 실제 인덱스 구조에 맞춰 문서 내용을 분석하여 답변하세요.
""",   
    "similar": """
당신은 유사 사례 추천 전문가입니다.
제공된 문서는 장애 이력 데이터입니다.

사용자의 질문에 대해 문서 내용을 분석하여 유사한 사례를 찾아 답변하세요.

## 출력형식
### 1. 관련 사례
* 제목: title  
* 장애 현상: 문서 내용에서 현상 추출하여 **강조**
* 장애 원인: 문서 내용에서 원인 추출하여 **강조**
* 복구 방법: 문서 내용에서 복구방법 추출하여 **강조**
* 유사도 점수: 추정 점수

참고: 문서 내용을 상세히 분석하여 관련 정보를 추출하세요.
""",
    
    "default": """
당신은 IT 시스템 장애 전문가입니다. 
제공된 문서는 장애 이력 데이터입니다.
사용자의 질문에 대해 문서 내용을 분석하여 정확하고 유용한 답변을 제공해주세요.
답변은 한국어로 작성하며, 구체적인 해결방안이나 원인을 명시해주세요.

만약 제공된 문서에서 관련 정보를 찾을 수 없다면, 그렇게 명시해주세요.
만약 제공된 문서에서 관련 정보를 찾을 수 있다면 아래내용은 답변 하단에 항상포함해주세요
'-- 주의: 답변은 AI 해석에 따른 오류가 포함될 수 있음을 감안하시고 활용부탁드립니다. --'
"""
}

# 인덱스 스키마 확인 함수 추가
def check_index_schema(search_client):
    try:
        add_debug_log("🔍 인덱스 스키마 확인 중...")
        
        # 빈 검색으로 첫 번째 문서 가져오기
        results = search_client.search(
            search_text="*",
            top=1,
            include_total_count=True
        )
        
        for result in results:
            available_fields = list(result.keys())
            add_debug_log(f"✅ 사용 가능한 필드: {available_fields}")
            return available_fields
        
        add_debug_log("⚠️ 인덱스가 비어있거나 접근할 수 없습니다.")
        return []
        
    except Exception as e:
        error_msg = f"❌ 인덱스 스키마 확인 실패: {str(e)}"
        add_error_log(error_msg, traceback.format_exc())
        return []

# Azure 클라이언트 초기화 (디버깅 강화)
@st.cache_resource
def init_clients(openai_endpoint, openai_key, openai_api_version, search_endpoint, search_key, search_index):
    try:
        add_debug_log("🔄 Azure 클라이언트 초기화 시작")
        
        # Azure OpenAI 클라이언트 설정 (새로운 방식)
        try:
            azure_openai_client = AzureOpenAI(
                azure_endpoint=openai_endpoint,
                api_key=openai_key,
                api_version=openai_api_version
            )
            add_debug_log("✅ Azure OpenAI 클라이언트 초기화 성공!")
        except Exception as openai_error:
            error_msg = f"❌ Azure OpenAI 클라이언트 초기화 실패: {str(openai_error)}"
            add_error_log(error_msg, traceback.format_exc())
            return None, None, False
        
        # Azure AI Search 클라이언트 설정
        try:
            search_client = SearchClient(
                endpoint=search_endpoint,
                index_name=search_index,
                credential=AzureKeyCredential(search_key)
            )
            add_debug_log("✅ Azure Search 클라이언트 초기화 성공!")
        except Exception as search_error:
            error_msg = f"❌ Azure Search 클라이언트 초기화 실패: {str(search_error)}"
            add_error_log(error_msg, traceback.format_exc())
            return azure_openai_client, None, False
        
        add_debug_log("✅ 모든 Azure 클라이언트 초기화 완료")
        return azure_openai_client, search_client, True
        
    except Exception as e:
        error_msg = f"❌ 전체 클라이언트 초기화 실패: {str(e)}"
        add_error_log(error_msg, traceback.format_exc())
        return None, None, False

# 검색 함수 - 실제 인덱스 스키마에 맞게 수정
def search_documents(search_client, query, top_k=5):
    try:
        add_debug_log(f"🔍 일반 검색 실행: '{query}' (최대 {top_k}개 결과)")
        
        # 실제 인덱스 필드명에 맞게 수정 - 모든 필드 포함
        results = search_client.search(
            search_text=query,
            top=top_k,
            include_total_count=True
            # select와 search_fields 제거하여 모든 필드 자동 포함
        )
        
        documents = []
        for result in results:
            # 동적으로 모든 필드 처리
            doc = {}
            for key, value in result.items():
                if not key.startswith('@'):  # 메타데이터 필드 제외
                    doc[key] = value if value is not None else ""
            doc["score"] = result.get("@search.score", 0)
            documents.append(doc)
        
        add_debug_log(f"✅ 일반 검색 완료: {len(documents)}개 문서 발견")
        return documents
        
    except Exception as e:
        error_msg = f"❌ 일반 검색 실패: {str(e)}"
        add_error_log(error_msg, traceback.format_exc())
        return []

# 시맨틱 검색 함수 - 실제 인덱스 스키마에 맞게 수정
def semantic_search_documents(search_client, query, top_k=5):
    try:
        add_debug_log(f"🧠 시맨틱 검색 실행: '{query}' (최대 {top_k}개 결과)")
        
        # 시맨틱 검색 시도
        try:
            results = search_client.search(
                search_text=query,
                top=top_k,
                query_type="semantic",
                semantic_configuration_name="iap-incident-report-index-semantic-configuration",
                include_total_count=True
                # select 제거하여 모든 필드 자동 포함
            )
        except Exception as semantic_error:
            # 시맨틱 검색 실패 시 일반 검색으로 대체
            add_debug_log(f"⚠️ 시맨틱 검색 설정 문제, 일반 검색으로 대체: {str(semantic_error)}")
            return search_documents(search_client, query, top_k)
        
        documents = []
        for result in results:
            # 동적으로 모든 필드 처리
            doc = {}
            for key, value in result.items():
                if not key.startswith('@'):  # 메타데이터 필드 제외
                    doc[key] = value if value is not None else ""
            doc["score"] = result.get("@search.score", 0)
            doc["reranker_score"] = result.get("@search.reranker_score", 0)
            documents.append(doc)
        
        add_debug_log(f"✅ 시맨틱 검색 완료: {len(documents)}개 문서 발견")
        return documents
        
    except Exception as e:
        error_msg = f"⚠️ 시맨틱 검색 실패, 일반 검색으로 대체: {str(e)}"
        add_error_log(error_msg, traceback.format_exc())
        return search_documents(search_client, query, top_k)

# RAG 응답 생성 - 동적 필드 처리로 수정
def generate_rag_response(azure_openai_client, query, documents, model_name, query_type="default"):
    try:
        add_debug_log(f"🤖 AI 응답 생성 시작... (모델: {model_name}, 타입: {query_type})")
        
        # 검색된 문서들을 컨텍스트로 구성 (동적 필드명 사용)
        context_parts = []
        for i, doc in enumerate(documents):
            context_part = f"문서 {i+1}:\n"
            
            # 동적으로 모든 필드 출력 (실제 인덱스 구조에 맞게)
            for key, value in doc.items():
                if key not in ['score', 'reranker_score'] and value:  # 점수 필드와 빈 값 제외
                    context_part += f"{key}: {value}\n"
            
            context_parts.append(context_part)
        
        context = "\n\n".join(context_parts)
        
        # 질문 타입에 따른 시스템 프롬프트 선택 (실제 인덱스 구조에 맞게 수정)
        system_prompt_updated = SYSTEM_PROMPTS.get(query_type, SYSTEM_PROMPTS["default"])

        user_prompt = f"""
다음 장애 이력 문서들을 참고하여 질문에 답변해주세요:

{context}

질문: {query}

답변:"""

        # Azure OpenAI API 호출
        try:
            add_debug_log("📡 Azure OpenAI API 호출 중...")
            response = azure_openai_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt_updated},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=1500  # 토큰 수 증가
            )
            
            add_debug_log("✅ AI 응답 생성 완료!")
            return response.choices[0].message.content
            
        except Exception as api_error:
            error_msg = f"❌ Azure OpenAI API 호출 실패: {str(api_error)}"
            add_error_log(error_msg, traceback.format_exc())
            return f"API 호출 중 오류가 발생했습니다: {str(api_error)}"
    
    except Exception as e:
        error_msg = f"❌ 응답 생성 실패: {str(e)}"
        add_error_log(error_msg, traceback.format_exc())
        return f"응답 생성 중 오류가 발생했습니다: {str(e)}"

# 문서 표시 함수 - chunk_id, parent_id 제거
def display_documents(documents):
    for i, doc in enumerate(documents):
        st.write(f"**문서 {i+1}** (검색 점수: {doc.get('score', 0):.2f})")
        
        # 실제 인덱스 필드에 맞게 표시
        col1, col2 = st.columns(2)
        
        with col1:
            if doc.get('title'):
                st.write(f"**제목**: {doc['title']}")
                
        with col2:
            if doc.get('reranker_score'):
                st.write(f"**재순위 점수**: {doc['reranker_score']:.2f}")
        
        # chunk 내용 표시 (긴 내용은 일부만)
        if doc.get('chunk'):
            chunk_content = doc['chunk']
            if len(chunk_content) > 500:
                st.write(f"**내용**: {chunk_content[:500]}...")
                with st.expander("전체 내용 보기"):
                    st.write(chunk_content)
            else:
                st.write(f"**내용**: {chunk_content}")
        
        # 기타 필드들 동적 표시 (chunk_id, parent_id 제외)
        other_fields = {k: v for k, v in doc.items() 
                       if k not in ['title', 'chunk', 'score', 'reranker_score'] 
                       and v and str(v).strip()}
        
        if other_fields:
            st.write("**기타 정보:**")
            for key, value in other_fields.items():
                if len(str(value)) > 100:
                    st.write(f"- **{key}**: {str(value)[:100]}...")
                else:
                    st.write(f"- **{key}**: {value}")
        
        st.write("---")

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
        # 컨테이너를 사용하여 상단 고정 영역 구성
        with st.container():
            # 서비스 정보 입력 섹션
            st.header("📝 서비스 정보 입력")
            
            # 서비스명과 장애현상 입력
            input_col1, input_col2 = st.columns(2)
            
            with input_col1:
                service_name = st.text_input("서비스명을 입력하세요", placeholder="예: 마이페이지, 패밀리박스, 통합쿠폰플랫폼")
            
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
                    font-size: 40px;   /* 글자 크기 */
                    height: 40px;      /* 높이 */
                }
                 
                div.stButton > button:first-child {
                    font-size: 40px;      /* 글자 크기 */
                    height: 60px;         /* 버튼 높이 */
                    width: 450px;         /* 버튼 너비 */
                    background-color: #4CAF50; /* 버튼 배경색 (옵션) */
                    color: white;         /* 글자색 */
                    border-radius: 10px;   /* 버튼 둥글기 */
                }
                </style>
            """, unsafe_allow_html=True)

            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("🔧 서비스와 현상에 대해 복구 방법 안내", key="repair_btn"):
                    if validate_inputs(service_name, incident_symptom):
                        search_query = build_search_query(service_name, incident_symptom)
                        st.session_state.sample_query = f"{search_query}에 대한 복구방법 안내"
                        st.session_state.query_type = "repair"
                
            with col2:
                if st.button("🔄 타 서비스에 동일 현상에 대한 복구 방법 참조 (최대5건)", key="similar_btn"):
                    if validate_inputs(service_name, incident_symptom):
                        search_query = build_search_query("", incident_symptom)  # 타 서비스이므로 서비스명 제외
                        st.session_state.sample_query = f" {incident_symptom} 동일 현상에 대한 장애현상, 장애원인, 복구방법 알려주세요"
                        st.session_state.query_type = "similar"

            # 검색 옵션 설정 (숨김 처리)
            search_type = 0     #시맨틱 검색 (일반검색보다 답변품질높음)
            search_count = 5    #검색 결과 수 :5 (10으로하면 오데이터가 같이 포함되어 품질 저하됨)

        # =================== 상단 고정 영역 끝 ===================
        
        # 세션 상태 초기화
        if 'messages' not in st.session_state:
            st.session_state.messages = []
        
        # 채팅 메시지 표시 영역 (스크롤 가능)
        chat_container = st.container()
        
        with chat_container:
            # 이전 메시지 표시
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    # AI 답변과 사용자 메시지 모두 직접 표시 (expander 중첩 문제 해결)
                    st.write(message["content"])
        
        # 검색 및 응답 처리 함수 (디버깅 강화)
        def process_query(query, query_type="default"):
            with st.chat_message("assistant"):
                try:
                    add_debug_log(f"🔍 쿼리 처리 시작: '{query}' (타입: {query_type})")
                    
                    with st.spinner("검색 중..."):
                        # 검색 방식에 따라 다른 함수 호출
                        if search_type == 0:  # 시맨틱 검색
                            documents = semantic_search_documents(search_client, query, search_count)
                        else:
                            documents = search_documents(search_client, query, search_count)
                        
                        st.write(f"📄 {len(documents)}개의 관련 문서를 찾았습니다.")
                        
                        if documents:
                            # 검색된 문서 표시 (중첩 expander 문제 해결)
                            st.write("**📄 검색된 문서:**")
                            display_documents(documents)
                            
                            # RAG 응답 생성 (질문 타입 포함)
                            with st.spinner("답변 생성 중..."):
                                response = generate_rag_response(azure_openai_client, query, documents, azure_openai_model, query_type)
                                
                                # AI 답변 표시 (expander 중첩 문제 해결)
                                st.write("**🤖 AI 답변:**")
                                st.write(response)
                                
                                # 응답을 세션에 저장
                                st.session_state.messages.append({"role": "assistant", "content": response})
                                add_debug_log("✅ 쿼리 처리 완료")
                        else:
                            error_msg = "관련 문서를 찾을 수 없습니다. 다른 키워드로 검색해보세요."
                            st.write("**🤖 AI 답변:**")
                            st.write(error_msg)
                            st.session_state.messages.append({"role": "assistant", "content": error_msg})
                            
                except Exception as e:
                    error_msg = f"❌ 쿼리 처리 중 오류 발생: {str(e)}"
                    add_error_log(error_msg, traceback.format_exc())
                    st.write("**🤖 AI 답변:**")
                    st.write(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})
        
        # 사용자 입력 (하단 고정)
        user_query = st.chat_input("질문을 입력하세요 (예: 마이페이지 최근 장애 발생일자와 장애원인 알려줘)")
        
        if user_query:
            # 사용자 메시지 추가
            st.session_state.messages.append({"role": "user", "content": user_query})
            
            with st.chat_message("user"):
                st.write(user_query)
            
            # 검색 및 응답 생성 (일반 질문은 기본 타입)
            process_query(user_query, "default")

        # 주요 질문 처리
        if 'sample_query' in st.session_state:
            query = st.session_state.sample_query
            query_type = st.session_state.get('query_type', 'default')
            
            # 세션 상태에서 제거
            del st.session_state.sample_query
            if 'query_type' in st.session_state:
                del st.session_state.query_type
            
            # 자동으로 질문 처리
            st.session_state.messages.append({"role": "user", "content": query})
            
            with st.chat_message("user"):
                st.write(query)
            
            # 검색 및 응답 생성 (질문 타입 포함)
            process_query(query, query_type)
            
            st.rerun()

    else:
        error_msg = "❌ Azure 클라이언트 초기화에 실패했습니다. 위의 오류 로그를 확인하세요."
        add_error_log(error_msg)

else:
    error_msg = "❌ 환경변수 설정이 필요합니다."
    add_error_log(error_msg)
    
    missing_vars = []
    if not azure_openai_endpoint:
        missing_vars.append("OPENAI_ENDPOINT")
    if not azure_openai_key:
        missing_vars.append("OPENAI_KEY")
    if not search_endpoint:
        missing_vars.append("SEARCH_ENDPOINT")
    if not search_key:
        missing_vars.append("SEARCH_API_KEY")
    if not search_index:
        missing_vars.append("INDEX_REPORT_NAME")
    
    st.error("**필요한 환경변수:**")
    for var in missing_vars:
        st.write(f"❌ {var}")
        add_error_log(f"환경변수 누락: {var}")
    
    if not missing_vars:
        st.write("✅ 모든 환경변수가 설정되었습니다.")
    else:
        error_summary = f"총 {len(missing_vars)}개의 환경변수가 누락되었습니다: {', '.join(missing_vars)}"
        st.write(f"\n**{error_summary}**")
        add_error_log(error_summary)