import streamlit as st
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
import os
import json
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
azure_openai_model = os.getenv("CHAT_MODEL", "gpt-4o-mini")
azure_openai_api_version = os.getenv("OPENAI_API_VERSION", "2024-02-01")

search_endpoint = os.getenv("SEARCH_ENDPOINT")
search_key = os.getenv("SEARCH_API_KEY")
search_index = os.getenv("INDEX_NAME")

# 메인 페이지
st.title("🤖 트러블 체이서 챗봇")
st.write("Azure AI Search를 활용한 RAG 방식 질의응답 시스템")

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

# 검색 함수 - 실제 인덱스 스키마에 맞게 수정
def search_documents(search_client, query, top_k=5):
    try:
        # 실제 인덱스 필드명에 맞게 수정
        results = search_client.search(
            search_text=query,
            top=top_k,
            include_total_count=True,
            # 실제 인덱스에 있는 필드명 사용
            select=[
                "incident_id", "domain_name", "service_name", "service_grade",
                "error_range", "error_time", "subject", "notice_text", 
                "error_date", "week", "incident_cause", "incident_repair", 
                "incident_plan", "cause_type", "done_type", "incident_grade", 
                "owner_depart"
            ],
            # 검색 가능한 필드들로 제한
            search_fields=[
                "subject", "notice_text", "incident_cause", "incident_repair", 
                "incident_plan", "domain_name", "service_name", "cause_type", 
                "done_type", "owner_depart"
            ]
        )
        
        documents = []
        for result in results:
            documents.append({
                "incident_id": result.get("incident_id", ""),
                "domain_name": result.get("domain_name", ""),
                "service_name": result.get("service_name", ""),
                "service_grade": result.get("service_grade", ""),
                "error_range": result.get("error_range", ""),
                "error_time": result.get("error_time", ""),
                "subject": result.get("subject", ""),
                "notice_text": result.get("notice_text", ""),
                "error_date": result.get("error_date", ""),
                "week": result.get("week", ""),
                "incident_cause": result.get("incident_cause", ""),
                "incident_repair": result.get("incident_repair", ""),
                "incident_plan": result.get("incident_plan", ""),
                "cause_type": result.get("cause_type", ""),
                "done_type": result.get("done_type", ""),
                "incident_grade": result.get("incident_grade", ""),
                "owner_depart": result.get("owner_depart", ""),
                "score": result.get("@search.score", 0)
            })
        
        return documents
    except Exception as e:
        st.error(f"검색 실패: {str(e)}")
        return []

# 시맨틱 검색 함수 추가
def semantic_search_documents(search_client, query, top_k=5):
    try:
        # 시맨틱 검색 사용 (인덱스에 semantic 설정이 있는 경우)
        results = search_client.search(
            search_text=query,
            top=top_k,
            query_type="semantic",
            semantic_configuration_name="iap-incident-meaning",  # 인덱스 스키마에 정의된 이름
            include_total_count=True,
            select=[
                "incident_id", "domain_name", "service_name", "service_grade",
                "error_range", "error_time", "subject", "notice_text", 
                "error_date", "week", "incident_cause", "incident_repair", 
                "incident_plan", "cause_type", "done_type", "incident_grade", 
                "owner_depart"
            ]
        )
        
        documents = []
        for result in results:
            documents.append({
                "incident_id": result.get("incident_id", ""),
                "domain_name": result.get("domain_name", ""),
                "service_name": result.get("service_name", ""),
                "service_grade": result.get("service_grade", ""),
                "error_range": result.get("error_range", ""),
                "error_time": result.get("error_time", ""),
                "subject": result.get("subject", ""),
                "notice_text": result.get("notice_text", ""),
                "error_date": result.get("error_date", ""),
                "week": result.get("week", ""),
                "incident_cause": result.get("incident_cause", ""),
                "incident_repair": result.get("incident_repair", ""),
                "incident_plan": result.get("incident_plan", ""),
                "cause_type": result.get("cause_type", ""),
                "done_type": result.get("done_type", ""),
                "incident_grade": result.get("incident_grade", ""),
                "owner_depart": result.get("owner_depart", ""),
                "score": result.get("@search.score", 0),
                "reranker_score": result.get("@search.reranker_score", 0)
            })
        
        return documents
    except Exception as e:
        st.warning(f"시맨틱 검색 실패, 일반 검색으로 대체: {str(e)}")
        return search_documents(search_client, query, top_k)

# RAG 응답 생성 - 새로운 OpenAI API 방식 사용
def generate_rag_response(azure_openai_client, query, documents, model_name):
    try:
        # 검색된 문서들을 컨텍스트로 구성 (실제 필드명 사용)
        context_parts = []
        for i, doc in enumerate(documents):
            context_part = f"""문서 {i+1}:
장애 ID: {doc['incident_id']}
도메인: {doc['domain_name']}
서비스명: {doc['service_name']}
서비스 등급: {doc['service_grade']}
장애 범위: {doc['error_range']}
제목: {doc['subject']}
공지사항: {doc['notice_text']}
장애 원인: {doc['incident_cause']}
복구 방법: {doc['incident_repair']}
개선 계획: {doc['incident_plan']}
원인 유형: {doc['cause_type']}
처리 유형: {doc['done_type']}
장애 등급: {doc['incident_grade']}
담당 부서: {doc['owner_depart']}
"""
            context_parts.append(context_part)
        
        context = "\n\n".join(context_parts)
        
        # 프롬프트 구성
        system_prompt = """당신은 IT 시스템 장애 전문가입니다. 
사용자의 질문에 대해 제공된 장애 이력 문서를 기반으로 정확하고 유용한 답변을 제공해주세요.
답변은 한국어로 작성하며, 구체적인 해결방안이나 원인을 명시해주세요.
장애 ID, 서비스명, 원인, 복구방법 등의 구체적인 정보를 포함해주세요.
만약 제공된 문서에서 관련 정보를 찾을 수 없다면, 그렇게 명시해주세요."""

        user_prompt = f"""
다음 장애 이력 문서들을 참고하여 질문에 답변해주세요:

{context}

질문: {query}

답변:"""

        # Azure OpenAI API 호출 (새로운 방식)
        response = azure_openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        return response.choices[0].message.content
    
    except Exception as e:
        st.error(f"응답 생성 실패: {str(e)}")
        return "죄송합니다. 응답을 생성하는 중 오류가 발생했습니다."

# 문서 표시 함수 개선
def display_documents(documents):
    for i, doc in enumerate(documents):
        st.write(f"**문서 {i+1}** (검색 점수: {doc['score']:.2f})")
        
        # 주요 정보만 표시
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**장애 ID**: {doc['incident_id']}")
            st.write(f"**도메인**: {doc['domain_name']}")
            st.write(f"**서비스명**: {doc['service_name']}")
            st.write(f"**장애 등급**: {doc['incident_grade']}")
            
        with col2:
            st.write(f"**원인 유형**: {doc['cause_type']}")
            st.write(f"**처리 유형**: {doc['done_type']}")
            st.write(f"**담당 부서**: {doc['owner_depart']}")
            st.write(f"**장애 범위**: {doc['error_range']}")
        
        st.write(f"**제목**: {doc['subject']}")
        if doc['notice_text']:
            st.write(f"**공지사항**: {doc['notice_text'][:200]}...")
        if doc['incident_cause']:
            st.write(f"**장애 원인**: {doc['incident_cause'][:200]}...")
        if doc['incident_repair']:
            st.write(f"**복구 방법**: {doc['incident_repair'][:200]}...")
        
        st.write("---")

# 메인 애플리케이션 로직
if all([azure_openai_endpoint, azure_openai_key, search_endpoint, search_key, search_index]):
    # 클라이언트 초기화
    azure_openai_client, search_client, init_success = init_clients(
        azure_openai_endpoint, azure_openai_key, azure_openai_api_version,
        search_endpoint, search_key, search_index
    )
    
    if init_success:
        st.success("Azure 서비스 연결 성공!")
        
        # 세션 상태 초기화
        if 'messages' not in st.session_state:
            st.session_state.messages = []
        
        # 이전 메시지 표시
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])
        
        # 사용자 입력
        user_query = st.chat_input("질문을 입력하세요 (예: 마이페이지 장애원인 알려줘)")
        
        # 검색 및 응답 처리 함수
        def process_query(query):
            with st.chat_message("assistant"):
                with st.spinner("검색 중..."):
                    # 검색 방식에 따라 다른 함수 호출
                    if search_type == "시맨틱 검색 (권장)":
                        documents = semantic_search_documents(search_client, query, search_count)
                    else:
                        documents = search_documents(search_client, query, search_count)
                    
                    if documents:
                        st.write(f"📄 {len(documents)}개의 관련 문서를 찾았습니다.")
                        
                        # 검색된 문서 표시 (접을 수 있는 형태)
                        with st.expander("검색된 문서 보기"):
                            display_documents(documents)
                        
                        # RAG 응답 생성
                        with st.spinner("답변 생성 중..."):
                            response = generate_rag_response(azure_openai_client, query, documents, azure_openai_model)
                            st.write(response)
                            
                            # 응답을 세션에 저장
                            st.session_state.messages.append({"role": "assistant", "content": response})
                    else:
                        error_msg = "관련 문서를 찾을 수 없습니다."
                        st.write(error_msg)
                        st.session_state.messages.append({"role": "assistant", "content": error_msg})
        
        if user_query:
            # 사용자 메시지 추가
            st.session_state.messages.append({"role": "user", "content": user_query})
            
            with st.chat_message("user"):
                st.write(user_query)
            
            # 검색 및 응답 생성
            process_query(user_query)
        
        # 서비스명과 장애현상 입력
        st.header("📝 서비스 정보 입력")
        input_col1, input_col2 = st.columns(2)
        
        with input_col1:
            service_name = st.text_input("서비스명을 입력하세요", placeholder="예: 마이페이지, 로그인, 결제시스템")
        
        with input_col2:
            incident_symptom = st.text_input("장애현상을 입력하세요", placeholder="예: 접속불가, 응답지연, 오류발생")
        
        # 주요 질문 버튼들
        st.header("🔍 주요 질문")
        
        # 서비스명과 장애현상이 입력되었는지 확인
        if service_name and incident_symptom:
            st.success(f"서비스: {service_name} | 장애현상: {incident_symptom}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("서비스와 현상에 대해 대응가이드 안내"):
                if service_name and incident_symptom:
                    st.session_state.sample_query = f"{service_name} {incident_symptom}에 대한 대응가이드 안내"
                else:
                    st.session_state.sample_query = "서비스와 현상에 대해 대응가이드 안내"
            
            if st.button("현상에 대한 대표 원인 안내"):
                if service_name and incident_symptom:
                    st.session_state.sample_query = f"{service_name} {incident_symptom} 현상에 대한 대표 원인 안내"
                else:
                    st.session_state.sample_query = "현상에 대한 대표 원인 안내"
        
        with col2:
            if st.button("서비스와 현상에 대한 과거 대응방법"):
                if service_name and incident_symptom:
                    st.session_state.sample_query = f"{service_name} {incident_symptom}에 대한 과거 대응방법"
                else:
                    st.session_state.sample_query = "서비스와 현상에 대한 과거 대응방법"
            
            if st.button("타 서비스에 동일 현상에 대한 대응이력조회"):
                if service_name and incident_symptom:
                    st.session_state.sample_query = f"타 서비스에서 {incident_symptom} 동일 현상에 대한 대응이력조회"
                else:
                    st.session_state.sample_query = "타 서비스에 동일 현상에 대한 대응이력조회"

        # 검색 옵션 설정을 먼저 배치
        col_search1, col_search2 = st.columns(2)
        
        with col_search1:
            search_type = st.selectbox(
                "검색 방식",
                ["시맨틱 검색 (권장)", "일반 검색"],
                index=0
            )
        
        with col_search2:
            search_count = st.slider("검색 결과 수", 1, 10, 5)

        # 주요 질문 처리
        if 'sample_query' in st.session_state:
            query = st.session_state.sample_query
            del st.session_state.sample_query
            
            # 자동으로 질문 처리
            st.session_state.messages.append({"role": "user", "content": query})
            
            with st.chat_message("user"):
                st.write(query)
            
            # 검색 및 응답 생성
            process_query(query)
            
            st.rerun()

else:
    st.error("환경변수 설정이 필요합니다.")
    st.write("필요한 환경변수:")
    st.write("- OPENAI_ENDPOINT")
    st.write("- OPENAI_KEY")  
    st.write("- SEARCH_ENDPOINT")
    st.write("- SEARCH_API_KEY")
    st.write("- INDEX_NAME")