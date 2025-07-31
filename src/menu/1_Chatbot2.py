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
search_index = os.getenv("INDEX_ADDCOL_NAME")

# Reranker 기반 검색 품질 향상을 위한 설정
SEARCH_SCORE_THRESHOLD = 0.5      # 초기 검색 점수 임계값 (낮게 설정하여 더 많은 후보 확보)
RERANKER_SCORE_THRESHOLD = 2.0    # Reranker 점수 임계값 (높은 품질 보장)
HYBRID_SCORE_THRESHOLD = 0.75     # 하이브리드 점수 임계값
MAX_INITIAL_RESULTS = 20          # 초기 검색 결과 수 (Reranker 입력용)
MAX_FINAL_RESULTS = 5             # 최종 선별 문서 수

# 메인 페이지 제목
st.title("🤖 트러블 체이서 챗봇 (Reranker 강화)")
st.write("🎯 Reranker 기술로 답변 정확도를 대폭 향상시킨 고품질 장애복구 지원 시스템")

# 질문 타입별 시스템 프롬프트 정의
SYSTEM_PROMPTS = {
    "repair": """
당신은 IT서비스 트러블슈팅 전문가입니다. 
입력받은 사용자의 서비스와 현상에 대한 복구방법을 가이드 해주는데, RAG한 데이터에서 복합장애여부(multifail_yn)에서의 복합장애 건은 제외하고 **아래의 제외 조건도 반드시 확인한 후** '대상선정원칙'에 따라 대상을 선정하고 복구방법(incident_repair)을 아래의 '출력형식' 대로 유사도가 높은건으로 선정하여 최대 Top 3개 출력하는데 90점이상 되는것중에 유사도가 가장높은건 순서로 Case1, Case2 로 표현해서 출력하는데 천천히 생각하면서 답변을 3회 출력없이 실행해보고 가장 일관성이 있는 답변으로 답변해주세요.

## 제외 조건 (검색 결과에서 반드시 제외할 것)
1. **복합장애여부(multifail_yn)에 '복합장애' 단어가 포함된 건**  
2. **복합장애여부(multifail_yn)에 '복합' 단어가 포함된 건**  
3. **공지사항(notice_text)에 '복합' 단어가 포함된 건**  
4. **장애원인(incident_cause)에 '복합' 단어가 포함된 건**
5. **복구방법(incident_repair)에 '복합' 단어가 포함된 건**

## 대상선정원칙
**위의 제외 조건을 모두 통과한 건들 중에서만** 아래 기준으로 선정:
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
* 장애발생일시 : 장애 발생일시(error_date) 출력 (예. 2023-10-01 12:00)
* 장애원인 : 장애 원인(incident_cause) 내용을 요약하며 텍스트는 강조하지 마세요
* 장애현상 : '대상선정원칙'에서 참고한 현상으로 내용을 요약히지 원본 그대로 표현하며 텍스트는 강조하여 **텍스트** 로 표현해주세요
* 복구방법 : 복구 방법(incident_repair) 내용을 최대 3줄로 요약하며 텍스트는  강조하여 **텍스트** 로 표현해주세요
* 후속과제 : 개선계획(incident_plan) 내용을 요약하며 텍스트는 강조하지 마세요
* 인시던트 ID : 장애 ID(incident_id) 출력
* 참조장애정보는 아래 사항을 표로 출력하는데 타이틀의 영문은 빼줘

| 장애 ID | 서비스명 | 장애발생일자 | 장애시간 | 장애원인 | 복구방법 | 후속과제 | 처리유형 | 담당부서 |
|---------|----------|---------------|-----------|----------|----------|----------|----------|----------|
* 공지사항 : 공지사항(notice_text) 요약하지 않고 원본 그대로 테두리있는 텍스트박스 안에 내용을 출력해주세요
  """,   
    "similar": """당신은 유사 사례 추천 전문가입니다. 
사용자의 질문에 대해 제공된 장애 이력 문서를 기반으로 정확하고 유용한 답변을 제공해주세요.
답변은 한국어로 작성하며, 구체적인 해결방안이나 원인을 명시해주세요.
장애현상은 공지사항의 '현상'을 참고하고 없으면 '영향도'를 참고해서주세요
RAG한 데이터에서 복합장애여부(multifail_yn)에서의 복합장애 건은 제외하고 유사도가 높은건으로 선정하여 99점이상 되는것중에 유사도가 높은것만 출력해주시고
장애 ID, 서비스명, 원인, 복구방법 등의 구체적인 정보를 포함하는데 **아래의 제외 조건을 반드시 확인한 후** 천천히 생각하면서 답변을 3회 출력없이 실행해보고 가장 일관성이 있는 답변을 아래 **출력형식** 으로 답변해주세요.
만약 제공된 문서에서 관련 정보를 찾을 수 없다면, 그렇게 명시해주세요.
만약 제공된 문서에서 관련 정보를 찾을 수 있다면 아래내용은 답변 하단에 항상포함해주세요

## 제외 조건 (검색 결과에서 반드시 제외할 것)
1. **서비스명에 '00종' 또는 '외 00종'이 포함된 건**
2. **공지사항(notice_text)에 '복합' 단어가 포함된 건**  
3. **장애원인(incident_cause)에 '복합' 단어가 포함된 건**
4. **복구방법(incident_repair)에 '복합' 단어가 포함된 건**

## 출력형식
### 1. 서비스명 : KT AICC SaaS/PaaS
* 장애 ID: INM23022026178
* 장애 현상: 상담정보 열람불가 (상담 및 웹페이지 접속은 정상) 로 표현하며 텍스트는 강조하여 **텍스트** 로 표현해주세요
* 장애 원인: mecab 사전에 잘못 등록된 상품명(쌍따옴표")으로 인해 TA 분석 오류 발생. 로 표현하며 텍스트는 강조하여 **텍스트** 로 표현해주세요
* 복구 방법: 오류 상품명 삭제 및 mecab 리빌드 조치. 로 표현하며 텍스트는 강조하여 **텍스트** 로 표현해주세요
* 개선 계획: mecab 사전 백업 및 로그 처리, Skip 처리 진행 예정.
* 유사도점수 : 99.5
""",
    
    "default": """당신은 IT 시스템 장애 전문가입니다. 
사용자의 질문에 대해 제공된 장애 이력 문서를 기반으로 정확하고 유용한 답변을 제공해주세요.
답변은 한국어로 작성하며, 구체적인 해결방안이나 원인을 명시해주세요.
장애현상은 공지사항의 '현상'을 참고하고 없으면 '영향도'를 참고해서주세요
RAG한 데이터에서 복합장애여부(multifail_yn)에서의 복합장애 건은 제외하고 유사도가 높은건으로 선정하여 99점이상 되는것중에 유사도가 높은것만 출력해주시고
장애 ID, 서비스명, 원인, 복구방법 등의 구체적인 정보를 포함하는데 **아래의 제외 조건을 반드시 확인한 후** 천천히 생각하면서 답변을 3회 출력없이 실행해보고 가장 일관성이 있는 답변으로 답변해주세요.
만약 제공된 문서에서 관련 정보를 찾을 수 없다면, 그렇게 명시해주세요.
만약 제공된 문서에서 관련 정보를 찾을 수 있다면 아래내용은 답변 하단에 항상포함해주세요
'-- 주의: 답변은 AI 해석에 따른 오류가 포함될 수 있음을 감안하시고 활용부탁드립니다. --'

## 제외 조건 (검색 결과에서 반드시 제외할 것)
1. **서비스명에 '00종' 또는 '외 00종'이 포함된 건**
2. **공지사항(notice_text)에 '복합' 단어가 포함된 건**  
3. **장애원인(incident_cause)에 '복합' 단어가 포함된 건**
4. **복구방법(incident_repair)에 '복합' 단어가 포함된 건**

"""
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

# Reranker 기반 고급 문서 필터링 함수
def advanced_filter_documents(documents):
    """Reranker 점수와 하이브리드 점수를 활용한 고급 필터링"""
    filtered_docs = []
    filter_stats = {
        'total': len(documents),
        'search_filtered': 0,
        'reranker_qualified': 0,
        'hybrid_qualified': 0,
        'final_selected': 0
    }
    
    for doc in documents:
        search_score = doc.get('score', 0)
        reranker_score = doc.get('reranker_score', 0)
        
        # 1단계: 기본 검색 점수 필터링
        if search_score < SEARCH_SCORE_THRESHOLD:
            continue
        filter_stats['search_filtered'] += 1
        
        # 2단계: Reranker 점수 우선 평가
        if reranker_score >= RERANKER_SCORE_THRESHOLD:
            filter_stats['reranker_qualified'] += 1
            doc['filter_reason'] = f"Reranker 고품질 (점수: {reranker_score:.2f})"
            doc['final_score'] = reranker_score
            doc['quality_tier'] = 'Premium'
            filtered_docs.append(doc)
            filter_stats['final_selected'] += 1
            continue
        
        # 3단계: 하이브리드 점수 평가
        hybrid_score = calculate_hybrid_score(search_score, reranker_score)
        if hybrid_score >= HYBRID_SCORE_THRESHOLD:
            filter_stats['hybrid_qualified'] += 1
            doc['filter_reason'] = f"하이브리드 점수 통과 (점수: {hybrid_score:.2f})"
            doc['final_score'] = hybrid_score
            doc['quality_tier'] = 'Standard'
            filtered_docs.append(doc)
            filter_stats['final_selected'] += 1
    
    # 점수 기준으로 정렬 (높은 점수 우선)
    filtered_docs.sort(key=lambda x: x['final_score'], reverse=True)
    
    # 최종 결과 수 제한
    final_docs = filtered_docs[:MAX_FINAL_RESULTS]
    
    # 필터링 통계 표시
    st.info(f"""
    📊 **Reranker 기반 문서 필터링 결과**
    - 🔍 전체 검색 결과: {filter_stats['total']}개
    - ✅ 기본 점수 통과: {filter_stats['search_filtered']}개 (≥{SEARCH_SCORE_THRESHOLD})
    - 🏆 Reranker 고품질: {filter_stats['reranker_qualified']}개 (≥{RERANKER_SCORE_THRESHOLD})
    - 🎯 하이브리드 통과: {filter_stats['hybrid_qualified']}개 (≥{HYBRID_SCORE_THRESHOLD})
    - 📋 최종 선별: {len(final_docs)}개 (상위 {MAX_FINAL_RESULTS}개)
    """)
    
    return final_docs

# Reranker 지원 시맨틱 검색 함수
def semantic_search_with_reranker(search_client, query, top_k=MAX_INITIAL_RESULTS):
    """Reranker를 활용한 고품질 시맨틱 검색"""
    try:
        st.info(f"🔄 1단계: {top_k}개 초기 검색 결과 수집 중...")
        
        # 시맨틱 검색 실행 (더 많은 후보 확보)
        results = search_client.search(
            search_text=query,
            top=top_k,
            query_type="semantic",
            semantic_configuration_name="iap-incident-addcol-meaning",
            include_total_count=True,
            select=[
                "incident_id", "domain_name", "service_name", "service_grade",
                "error_range", "error_time", "subject", "notice_text", 
                "error_date", "week", "incident_cause", "incident_repair", 
                "incident_plan", "cause_type", "done_type", "incident_grade", 
                "owner_depart", "multifail_yn", "fail_type"
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
                "multifail_yn": result.get("multifail_yn", ""),
                "fail_type": result.get("fail_type", ""),
                "score": result.get("@search.score", 0),
                "reranker_score": result.get("@search.reranker_score", 0)
            })
        
        st.info(f"🎯 2단계: Reranker 기반 고품질 문서 선별 중...")
        
        # Reranker 기반 고급 필터링 적용
        filtered_documents = advanced_filter_documents(documents)
        
        return filtered_documents
        
    except Exception as e:
        st.warning(f"시맨틱 검색 실패, 일반 검색으로 대체: {str(e)}")
        return search_documents_with_reranker(search_client, query, top_k)

# 일반 검색도 Reranker 원리 적용
def search_documents_with_reranker(search_client, query, top_k=MAX_INITIAL_RESULTS):
    """일반 검색에 Reranker 원리 적용"""
    try:
        st.info(f"🔄 1단계: {top_k}개 초기 검색 결과 수집 중...")
        
        results = search_client.search(
            search_text=query,
            top=top_k,
            include_total_count=True,
            select=[
                "incident_id", "domain_name", "service_name", "service_grade",
                "error_range", "error_time", "subject", "notice_text", 
                "error_date", "week", "incident_cause", "incident_repair", 
                "incident_plan", "cause_type", "done_type", "incident_grade", 
                "owner_depart", "multifail_yn", "fail_type"
            ],
            search_fields=[
                "subject", "notice_text", "error_date", "week","incident_cause", "incident_repair", 
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
                "multifail_yn": result.get("multifail_yn", ""),
                "fail_type": result.get("fail_type", ""),
                "score": result.get("@search.score", 0),
                "reranker_score": 0  # 일반 검색에서는 0
            })
        
        st.info(f"🎯 2단계: 검색 점수 기반 고품질 문서 선별 중...")
        
        # 점수 기반 필터링 적용
        filtered_documents = advanced_filter_documents(documents)
        
        return filtered_documents
        
    except Exception as e:
        st.error(f"검색 실패: {str(e)}")
        return []

# RAG 응답 생성 - Reranker 정보 포함
def generate_rag_response_with_reranker(azure_openai_client, query, documents, model_name, query_type="default"):
    try:
        # 검색된 문서들을 컨텍스트로 구성 (품질 정보 포함)
        context_parts = []
        for i, doc in enumerate(documents):
            final_score = doc.get('final_score', 0)
            quality_tier = doc.get('quality_tier', 'Standard')
            filter_reason = doc.get('filter_reason', '기본 선별')
            
            context_part = f"""문서 {i+1} [{quality_tier}급 - {filter_reason}]:
장애 ID: {doc['incident_id']}
도메인: {doc['domain_name']}
서비스명: {doc['service_name']}
서비스등급: {doc['service_grade']}
장애범위: {doc['error_range']}
장애시간: {doc['error_time']}
제목: {doc['subject']}
공지사항: {doc['notice_text']}
장애발생일자: {doc['error_date']}
장애발생요일: {doc['week']}
장애원인: {doc['incident_cause']}
복구방법: {doc['incident_repair']}
개선계획: {doc['incident_plan']}
원인유형: {doc['cause_type']}
처리유형: {doc['done_type']}
장애등급: {doc['incident_grade']}
담당부서: {doc['owner_depart']}
복합장애여부: {doc['multifail_yn']}
장애유형: {doc['fail_type']}
품질점수: {final_score:.2f}
"""
            context_parts.append(context_part)
        
        context = "\n\n".join(context_parts)
        
        # 질문 타입에 따른 시스템 프롬프트 선택
        system_prompt = SYSTEM_PROMPTS.get(query_type, SYSTEM_PROMPTS["default"])

        user_prompt = f"""
다음 장애 이력 문서들을 참고하여 질문에 답변해주세요.
(모든 문서는 Reranker 기반 고품질 필터링을 통과한 최고 품질의 검색 결과입니다):

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
        st.error(f"응답 생성 실패: {str(e)}")
        return "죄송합니다. 응답을 생성하는 중 오류가 발생했습니다."

# 고급 문서 표시 함수
def display_documents_with_quality_info(documents):
    """품질 정보와 함께 문서 표시"""
    for i, doc in enumerate(documents):
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
        
        # 주요 정보 표시
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
        # st.success("Azure 서비스 연결 성공!")
        
        # =================== 상단 고정 영역 시작 ===================
        with st.container():
            # Reranker 설정 정보를 사이드바에 표시
            st.sidebar.header("🎯 Reranker 품질 설정")
            st.sidebar.markdown(f"""
            **다단계 품질 필터링**
            - 🔍 초기 검색: {MAX_INITIAL_RESULTS}개
            - ✅ 기본 임계값: {SEARCH_SCORE_THRESHOLD}
            - 🏆 Reranker 임계값: {RERANKER_SCORE_THRESHOLD}
            - 🎯 하이브리드 임계값: {HYBRID_SCORE_THRESHOLD}
            - 📋 최종 선별: {MAX_FINAL_RESULTS}개
            """)
            
            st.sidebar.info("💡 Reranker가 의미적 유사도를 정확히 평가하여 최고 품질 문서만 선별합니다.")
            
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
                if st.button("🔄 타 서비스에 동일 현상에 대한 복구 방법 참조", key="similar_btn"):
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
                        with st.expander("🤖 AI 답변 보기 (Reranker 강화)", expanded=True):
                            st.write(message["content"])
                    else:
                        st.write(message["content"])
        
        # 검색 및 응답 처리 함수 (Reranker 적용)
        def process_query_with_reranker(query, query_type="default"):
            with st.chat_message("assistant"):
                with st.spinner("🎯 Reranker 기반 고품질 검색 중..."):
                    # 시맨틱 검색 우선 사용 (Reranker 지원)
                    documents = semantic_search_with_reranker(search_client, query)
                    
                    if documents:
                        premium_count = sum(1 for doc in documents if doc.get('quality_tier') == 'Premium')
                        standard_count = len(documents) - premium_count
                        
                        st.success(f"🏆 {len(documents)}개의 최고품질 문서 선별 완료! (Premium: {premium_count}개, Standard: {standard_count}개)")
                        
                        # 검색된 문서 표시
                        with st.expander("🔍 선별된 고품질 문서 보기"):
                            display_documents_with_quality_info(documents)
                        
                        # RAG 응답 생성 (Reranker 정보 포함)
                        with st.spinner("💡 Reranker 기반 정확한 답변 생성 중..."):
                            response = generate_rag_response_with_reranker(
                                azure_openai_client, query, documents, azure_openai_model, query_type
                            )
                            
                            with st.expander("🤖 AI 답변 보기 (Reranker 강화)", expanded=True):
                                st.write(response)
                                st.info("✨ 이 답변은 Reranker 기술로 선별된 최고품질 문서를 바탕으로 생성되었습니다.")
                            
                            st.session_state.messages.append({"role": "assistant", "content": response})
                    else:
                        error_msg = f"""
                        🔍 Reranker 기반 검색 결과가 없습니다.
                        
                        **원인 분석:**
                        - 검색 점수가 {SEARCH_SCORE_THRESHOLD} 미만
                        - Reranker 점수가 {RERANKER_SCORE_THRESHOLD} 미만
                        - 하이브리드 점수가 {HYBRID_SCORE_THRESHOLD} 미만
                        
                        **개선 방안:**
                        - 더 구체적인 키워드 사용
                        - 서비스명과 현상을 명확히 입력
                        - 다른 표현으로 재검색
                        """
                        
                        with st.expander("🤖 AI 답변 보기 (Reranker 강화)", expanded=True):
                            st.write(error_msg)
                        st.session_state.messages.append({"role": "assistant", "content": error_msg})
        
        # 사용자 입력
        user_query = st.chat_input("질문을 입력하세요 (예: 마이페이지 최근 장애 발생일자와 장애원인 알려줘)")
        
        if user_query:
            st.session_state.messages.append({"role": "user", "content": user_query})
            
            with st.chat_message("user"):
                st.write(user_query)
            
            process_query_with_reranker(user_query, "default")

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
            
            process_query_with_reranker(query, query_type)
            st.rerun()

else:
    st.error("환경변수 설정이 필요합니다.")
    st.write("필요한 환경변수:")
    st.write("- OPENAI_ENDPOINT")
    st.write("- OPENAI_KEY")  
    st.write("- SEARCH_ENDPOINT")
    st.write("- SEARCH_API_KEY")
    st.write("- INDEX_ADDCOL_NAME")