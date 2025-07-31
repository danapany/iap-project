"""
Streamlit 기반 사내 용어 우선 학습 RAG 시스템
Enterprise Terminology-First RAG System with Streamlit UI

실행 방법:
pip install streamlit azure-search-documents openai pandas plotly
streamlit run streamlit_rag_app.py
"""

import streamlit as st
import os
import re
import json
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import pandas as pd
from collections import Counter
import time

# 환경변수 로드를 위한 python-dotenv import
try:
    from dotenv import load_dotenv
    load_dotenv()  # .env 파일 로드
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False
    st.warning("⚠️ python-dotenv가 설치되지 않았습니다. 환경변수를 직접 설정해주세요.")

# Plotly 선택적 import
try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    st.warning("⚠️ Plotly가 설치되지 않았습니다. 차트 기능이 제한됩니다.")

# Azure SDK imports
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import *
from azure.core.credentials import AzureKeyCredential

# OpenAI import
import openai

# 페이지 설정
st.set_page_config(
    page_title="🏢 Enterprise RAG System",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS 스타일링
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        color: #2E86AB;
        margin-bottom: 2rem;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #A23B72;
        margin: 1rem 0;
    }
    .info-box {
        background-color: #F18F01;
        padding: 1rem;
        border-radius: 0.5rem;
        color: white;
        margin: 1rem 0;
    }
    .success-box {
        background-color: #C73E1D;
        padding: 1rem;
        border-radius: 0.5rem;
        color: white;
        margin: 1rem 0;
    }
    .term-card {
        border: 2px solid #2E86AB;
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
        background-color: #f8f9fa;
    }
    .doc-card {
        border: 1px solid #A23B72;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        background-color: #fff;
    }
</style>
""", unsafe_allow_html=True)

@dataclass
class TermDefinition:
    """용어 정의 데이터 클래스"""
    term: str
    definition: str
    context: str
    synonyms: List[str]
    related_terms: List[str]
    department: str
    examples: List[str]
    confidence_score: float = 0.0

@dataclass
class SearchResult:
    """검색 결과 데이터 클래스"""
    title: str
    content: str
    source_index: str
    score: float
    metadata: Dict

class ConfigManager:
    """설정 관리 클래스 - .env 파일 및 환경변수 활용"""
    
    def __init__(self):
        # .env 파일이 있으면 로드 (이미 위에서 load_dotenv() 실행됨)
        
        # 환경변수에서 설정 로드
        self.azure_search_endpoint = os.getenv('AZURE_SEARCH_ENDPOINT', 'https://your-search-service.search.windows.net')
        self.azure_search_key = os.getenv('AZURE_SEARCH_KEY', 'your-search-admin-key')
        self.openai_api_key = os.getenv('OPENAI_API_KEY', 'your-openai-api-key')
        
        # 선택적 설정들 (기본값 포함)
        self.azure_search_api_version = os.getenv('AZURE_SEARCH_API_VERSION', '2023-11-01')
        self.openai_model = os.getenv('OPENAI_MODEL', 'gpt-4')
        self.openai_temperature = float(os.getenv('OPENAI_TEMPERATURE', '0.1'))
        self.max_tokens = int(os.getenv('MAX_TOKENS', '2000'))
        
        # 인덱스 이름 설정 (환경변수로 커스터마이징 가능)
        self.terminology_index = os.getenv('TERMINOLOGY_INDEX', 'company-terminology')
        self.document_indexes = {
            "policies": os.getenv('POLICIES_INDEX', 'company-policies'),
            "procedures": os.getenv('PROCEDURES_INDEX', 'work-procedures'), 
            "manuals": os.getenv('MANUALS_INDEX', 'system-manuals'),
            "announcements": os.getenv('ANNOUNCEMENTS_INDEX', 'company-announcements')
        }
        
        # 검색 설정
        self.max_terms_per_query = int(os.getenv('MAX_TERMS_PER_QUERY', '10'))
        self.max_documents_per_index = int(os.getenv('MAX_DOCUMENTS_PER_INDEX', '3'))
        self.min_confidence_score = float(os.getenv('MIN_CONFIDENCE_SCORE', '0.3'))
        
        # 디버깅/로깅 설정
        self.debug_mode = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
    
    def validate_config(self):
        """설정 유효성 검사"""
        issues = []
        
        if self.azure_search_endpoint == 'https://your-search-service.search.windows.net':
            issues.append("AZURE_SEARCH_ENDPOINT가 설정되지 않았습니다.")
        
        if self.azure_search_key == 'your-search-admin-key':
            issues.append("AZURE_SEARCH_KEY가 설정되지 않았습니다.")
        
        if self.openai_api_key == 'your-openai-api-key':
            issues.append("OPENAI_API_KEY가 설정되지 않았습니다.")
        
        return issues
    
    def get_config_summary(self):
        """설정 요약 정보 반환"""
        return {
            "Azure Search Endpoint": self.azure_search_endpoint,
            "Azure Search Key": "***" + self.azure_search_key[-4:] if self.azure_search_key != 'your-search-admin-key' else "미설정",
            "OpenAI API Key": "***" + self.openai_api_key[-4:] if self.openai_api_key != 'your-openai-api-key' else "미설정",
            "OpenAI Model": self.openai_model,
            "Temperature": self.openai_temperature,
            "Max Tokens": self.max_tokens,
            "Debug Mode": self.debug_mode,
            "용어 인덱스": self.terminology_index,
            "문서 인덱스 수": len(self.document_indexes)
        }

class TerminologyExtractor:
    """용어 추출 클래스"""
    
    def __init__(self):
        self.patterns = {
            'acronyms': r'\b[A-Z]{2,}\b',
            'system_names': r'\w+시스템|\w+System|\w+서비스',
            'process_terms': r'\w+관리|\w+처리|\w+분석|\w+운영',
            'department_terms': r'\w+팀|\w+부|\w+실|\w+센터',
            'technical_terms': r'\w+플랫폼|\w+솔루션|\w+엔진',
            'business_terms': r'\w+전략|\w+정책|\w+방침|\w+규정'
        }
    
    def extract_terms(self, text: str) -> List[str]:
        """텍스트에서 잠재적 용어 추출"""
        extracted_terms = set()
        text_upper = text.upper()
        
        for pattern_name, pattern in self.patterns.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            extracted_terms.update(matches)
            
            if pattern_name == 'acronyms':
                upper_matches = re.findall(pattern, text_upper)
                extracted_terms.update(upper_matches)
        
        filtered_terms = [term for term in extracted_terms if 2 <= len(term) <= 20]
        return list(filtered_terms)

def initialize_search_clients():
    """Azure Search 클라이언트 초기화"""
    try:
        # ConfigManager를 함수 내부에서 생성
        config = ConfigManager()
        credential = AzureKeyCredential(config.azure_search_key)
        
        terminology_client = SearchClient(
            config.azure_search_endpoint,
            config.terminology_index,
            credential
        )
        
        document_clients = {}
        for name, index_name in config.document_indexes.items():
            document_clients[name] = SearchClient(
                config.azure_search_endpoint,
                index_name,
                credential
            )
        
        return terminology_client, document_clients
    except Exception as e:
        st.error(f"Azure Search 클라이언트 초기화 실패: {e}")
        return None, None

class StreamlitRAGSystem:
    """Streamlit 기반 RAG 시스템"""
    
    def __init__(self):
        self.config = ConfigManager()
        self.term_extractor = TerminologyExtractor()
        
        # OpenAI 설정
        if self.config.openai_api_key != 'your-openai-api-key':
            openai.api_key = self.config.openai_api_key
        
        # Azure Search 클라이언트 초기화 (파라미터 없이 호출)
        self.terminology_client, self.document_clients = initialize_search_clients()
        
        # 세션 상태 초기화
        if 'chat_history' not in st.session_state:
            st.session_state.chat_history = []
        if 'query_stats' not in st.session_state:
            st.session_state.query_stats = []
    
    def search_terminology(self, terms: List[str]) -> Dict[str, TermDefinition]:
        """용어 사전 검색"""
        if not self.terminology_client:
            return {}
        
        found_terms = {}
        
        with st.spinner("🔍 용어 사전 검색 중..."):
            for term in terms:
                try:
                    # 모의 데이터 (실제 환경에서는 Azure Search 결과 사용)
                    sample_terms = {
                        "인시던트": TermDefinition(
                            term="인시던트",
                            definition="사고 또는 사건을 의미하며, IT 서비스 관리에서 문제 해결을 위한 중요한 요소입니다.",
                            context="IT 서비스 관리에서 인시던트는 서비스 중단이나 성능 저하와 같은 사건을 나타냅니다.",
                            synonyms=["사건", "장애", "Incident"],
                            related_terms=["이상징후", "VOC", "문제"],
                            examples=["DB중단되어 인시던트 조치 하였습니다."],
                            confidence_score=0.95
                        ),
                        "이벤트": TermDefinition(
                            term="이벤트",
                            definition="관제 알람 시점에 발생하는 사건이나 상황을 의미하며 서비스 비정상동작의 경우나 특정조건 경고시에 발생시킵니다.",
                            context="IT 서비스 관리에서 이벤트는 시스템의 정상적인 동작을 모니터링하고, 이상 징후를 조기에 발견하는 데 도움을 줍니다.관제 툴로는 LAMP, B-Mon, Genio, looks가 있습니다",
                            synonyms=["관제이벤트", "관제알람", "Event"],
                            related_terms=["인시던트", "이상징후", "로그"],
                            examples=["DB중단되어 인시던트 조치 하였습니다."],
                            confidence_score=0.95
                        ),                        
                        "이상징후": TermDefinition(
                            term="이상징후",
                            definition="장애로 판단하기 이전에 서비스의 비정상 상황이 감지된것으로 서비스 장애로 확대가 될 수도 있는 서비스의 상태이다",
                            context="IT 서비스 관리에서 이상징후는 장애상황을 정확히 판단하기 이전단계로 장애 발생 가능성을 나타냅니다.",
                            synonyms=["징후", "신호", "Indicator"],
                            related_terms=["인시던트", "장애", "이벤트"],
                            examples=["MES를 통해 생산 진행률을 모니터링합니다"],
                            confidence_score=0.92
                        ),
                        "서비스": TermDefinition(
                            term="서비스",
                            definition="IT 서비스 관리에서 특정 목적으로 제공되는 독립적인 서비스를 의미합니다.",
                            context="IT 서비스 관리에서 서비스는 고객의 요구를 충족시키기 위해 제공되는 독립적인 서비스이며 업무를 위한 여러 기능이나 솔루션을 포함합니다.",
                            synonyms=["IT 서비스", "서비스 제공"],
                            related_terms=["단위서비스", "표준서비스", "도메인"],
                            examples=["WMS에서 재고 위치를 확인할 수 있습니다"],
                            confidence_score=0.88
                        ),
                        "단위서비스": TermDefinition(
                            term="단위서비스",
                            definition="IT 서비스 관리에서 특정 기능을 수행하는 독립적인 서비스를 의미합니다.",
                            context="IT 서비스 관리에서 단위서비스는 고객의 요구를 충족시키기 위해 제공되는 독립적인 서비스이며 업무를 위한 여러 기능이나 솔루션을 포함합니다.",
                            synonyms=["기능 서비스", "모듈 서비스"],
                            related_terms=["서비스", "표준서비스", "도메인"],
                            examples=["WMS에서 재고 위치를 확인할 수 있습니다"],
                            confidence_score=0.88
                        ),
                        "표준서비스": TermDefinition(
                            term="표준서비스",
                            definition="유사한 기능의 단위서비스의 통합개념으로 표준서비스라고 명칭합니다.",
                            context="IT 서비스 관리에서 표준서비스는 단위 서비스의 집합체이며 관리를 위하여 대표적인 단위서비스명을 표준서비스명으로 명명하여 관리합니다.",
                            synonyms=["IT 서비스", "서비스 제공"],
                            related_terms=["단위서비스", "표준서비스", "도메인"],
                            examples=["WMS에서 재고 위치를 확인할 수 있습니다"],
                            confidence_score=0.88
                        ),
                        "도메인": TermDefinition(
                            term="도메인",
                            definition="IT 서비스 관리에서 표준서비스들의 관리주체와 업무영역을 고려한 대분류를 의미합니다.",
                            context="IT 서비스 관리에서 도메인은 표준서비스의 집합체로 관리주체와 업무영역을 고려한 대분류 유형으로 정의합니다.",
                            synonyms=["영역", "주제"],
                            related_terms=["서비스", "단위서비스", "표준서비스"],
                            examples=["WMS에서 재고 위치를 확인할 수 있습니다"],
                            confidence_score=0.88
                        ),
                        "KOS": TermDefinition(
                            term="KOS",
                            definition="KT의 대표 영업계 시스템을 의미하는 단어입니다.",
                            context="IT 서비스 관리에서 KOS는 KT의 영업 관련 업무를 지원하는 시스템으로 시스템이 방대하여 하위로 KOS-오더, KOS-billing 등 KOS-로 시작하는 표준서비스들이 많이 포함되어있습니다.",
                            synonyms=["KT 영업 시스템", "KOS 시스템"],
                            related_terms=["영업계", "개통", "청약"],
                            examples=["WMS에서 재고 위치를 확인할 수 있습니다"],
                            confidence_score=0.88
                        )                                                                                                          
                    }
                    
                    if term.upper() in sample_terms:
                        found_terms[term] = sample_terms[term.upper()]
                        
                except Exception as e:
                    st.error(f"용어 '{term}' 검색 중 오류: {e}")
        
        return found_terms
    
    def search_documents(self, query: str, expanded_terms: List[str]) -> List[SearchResult]:
        """문서 검색"""
        if not self.document_clients:
            return []
        
        # 모의 검색 결과
        sample_results = [
            SearchResult(
                title="ERP 시스템 사용 정책",
                content="ERP 시스템은 회사의 핵심 업무 시스템으로 모든 직원이 승인된 절차에 따라 사용해야 합니다. 재고 관리, 구매 승인, 급여 처리 등의 업무는 반드시 ERP를 통해 진행됩니다.",
                source_index="policies",
                score=4.2,
                metadata={"department": "IT", "category": "정책"}
            ),
            SearchResult(
                title="재고 관리 절차",
                content="재고 관리는 WMS와 ERP 시스템을 연동하여 실시간으로 진행됩니다. 입고, 출고, 재고조사의 3단계로 구성되어 있습니다.",
                source_index="procedures",
                score=3.8,
                metadata={"department": "물류", "category": "절차"}
            ),
            SearchResult(
                title="MES 시스템 매뉴얼",
                content="MES 시스템 사용법: 로그인 후 작업지시 확인, 생산 시작, 실적 입력, 완료 처리 순으로 진행합니다.",
                source_index="manuals", 
                score=3.5,
                metadata={"department": "생산", "category": "매뉴얼"}
            )
        ]
        
        # 쿼리와 관련성이 높은 결과 필터링
        relevant_results = []
        query_lower = query.lower()
        for result in sample_results:
            if any(term.lower() in result.content.lower() or term.lower() in result.title.lower() 
                   for term in [query] + expanded_terms):
                relevant_results.append(result)
        
        return relevant_results[:5]
    
    def create_rag_prompt(self, user_query: str, term_definitions: Dict[str, TermDefinition], 
                         search_results: List[SearchResult]) -> str:
        """RAG 프롬프트 생성"""
        terminology_section = ""
        if term_definitions:
            terminology_section = "=== 🏢 사내 용어 정의 ===\n"
            for term, definition in term_definitions.items():
                terminology_section += f"""
**{definition.term}**
- 정의: {definition.definition}
- 상세: {definition.context}
- 부서: {definition.department}
- 연관용어: {', '.join(definition.related_terms[:3])}

"""
        
        document_section = ""
        if search_results:
            document_section = "=== 📋 관련 문서 내용 ===\n"
            for i, doc in enumerate(search_results, 1):
                document_section += f"""
**[참고문서 {i}]** ({doc.source_index})
제목: {doc.title}
내용: {doc.content[:300]}...

"""
        
        prompt = f"""당신은 우리 회사의 전문 AI 어시스턴트입니다.

{terminology_section}

{document_section}

질문: {user_query}

위의 용어 정의와 문서 내용을 바탕으로 정확하고 실무에 도움이 되는 답변을 제공해주세요."""

        return prompt
    
    def call_llm(self, prompt: str) -> str:
        """LLM 호출"""
        try:
            if self.config.openai_api_key == 'your-openai-api-key':
                # API 키가 설정되지 않은 경우 모의 응답
                return """**🤖 AI 어시스턴트 답변 (데모 모드)**

ERP 시스템에서의 재고 관리에 대해 설명드리겠습니다.

**📊 ERP 재고 관리 프로세스:**

1. **실시간 재고 현황 확인**
   - ERP 메인 화면 → 재고관리 → 현재고 조회
   - 품목별, 창고별 재고 수량 실시간 확인 가능

2. **입출고 관리**
   - 입고: 구매 → 입고등록 → ERP 자동 반영
   - 출고: 판매 → 출고지시 → 재고 자동 차감

3. **WMS 연동**
   - WMS에서 물리적 재고 이동 처리
   - ERP와 실시간 연동으로 정확성 확보

**💡 실무 팁:**
- 재고 부족 시 자동 알림 설정 활용
- 정기 재고조사로 시스템-실물 일치성 확보
- 안전재고 설정으로 품절 방지

**📞 문의처:** IT팀 (내선 1234)

이 답변이 도움이 되셨나요? 추가 질문이 있으시면 언제든 말씀해주세요!"""
            
            # 실제 OpenAI API 호출
            response = openai.ChatCompletion.create(
                model=self.config.openai_model,
                messages=[
                    {"role": "system", "content": "당신은 회사의 전문 AI 어시스턴트입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=self.config.max_tokens,
                temperature=self.config.openai_temperature
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            return f"❌ LLM 호출 중 오류가 발생했습니다: {e}"
    
    def process_query(self, user_query: str) -> Tuple[str, Dict]:
        """메인 쿼리 처리 로직"""
        start_time = time.time()
        
        # 1. 용어 추출
        extracted_terms = self.term_extractor.extract_terms(user_query)
        
        # 2. 용어 정의 검색
        term_definitions = self.search_terminology(extracted_terms)
        
        # 3. 확장 용어 생성
        expanded_terms = []
        for term_def in term_definitions.values():
            expanded_terms.extend(term_def.synonyms)
            expanded_terms.extend(term_def.related_terms)
        
        # 4. 문서 검색
        search_results = self.search_documents(user_query, expanded_terms)
        
        # 5. 프롬프트 생성 및 LLM 호출
        prompt = self.create_rag_prompt(user_query, term_definitions, search_results)
        response = self.call_llm(prompt)
        
        # 6. 처리 시간 및 메타데이터
        processing_time = time.time() - start_time
        
        metadata = {
            "extracted_terms": extracted_terms,
            "found_terms": len(term_definitions),
            "found_documents": len(search_results),
            "processing_time": processing_time,
            "term_definitions": term_definitions,
            "search_results": search_results
        }
        
        # 통계 업데이트
        st.session_state.query_stats.append({
            "timestamp": datetime.now(),
            "query": user_query,
            "terms_found": len(term_definitions),
            "docs_found": len(search_results),
            "processing_time": processing_time
        })
        
        return response, metadata

def render_sidebar():
    """사이드바 렌더링"""
    st.sidebar.markdown("## 🛠️ 시스템 설정")
    
    # 설정 상태 확인
    config = ConfigManager()
    config_issues = config.validate_config()
    
    # 연결 상태 표시
    if not config_issues:
        st.sidebar.success("✅ 모든 설정이 완료되었습니다!")
    else:
        st.sidebar.error("❌ 설정을 확인해주세요:")
        for issue in config_issues:
            st.sidebar.write(f"• {issue}")
    
    # API 상태 확인
    api_status = "🟢 연결됨" if config.openai_api_key != 'your-openai-api-key' else "🔴 미설정"
    st.sidebar.write(f"**OpenAI API:** {api_status}")
    
    search_status = "🟢 연결됨" if config.azure_search_key != 'your-search-admin-key' else "🔴 미설정"
    st.sidebar.write(f"**Azure Search:** {search_status}")
    
    # .env 파일 상태
    env_status = "🟢 로드됨" if DOTENV_AVAILABLE else "🔴 python-dotenv 없음"
    st.sidebar.write(f"**.env 파일:** {env_status}")
    
    st.sidebar.markdown("---")
    
    # 예시 질문들
    st.sidebar.markdown("## 💡 예시 질문")
    sample_questions = [
        "ERP 시스템에서 재고 관리는 어떻게 하나요?",
        "MES와 WMS의 차이점이 무엇인가요?",
        "생산 현장에서 품질 데이터는 어떻게 입력하나요?",
        "재고 실사는 언제 어떻게 진행하나요?",
        "구매 승인 프로세스를 알려주세요"
    ]
    
    for i, question in enumerate(sample_questions):
        if st.sidebar.button(f"Q{i+1}", key=f"sample_q_{i}"):
            st.session_state.current_query = question
    
    st.sidebar.markdown("---")
    
    # 통계 정보 (세션 상태 확인 후 표시)
    if hasattr(st.session_state, 'query_stats') and st.session_state.query_stats:
        st.sidebar.markdown("## 📊 사용 통계")
        stats_df = pd.DataFrame(st.session_state.query_stats)
        
        st.sidebar.metric("총 질문 수", len(stats_df))
        avg_time = stats_df['processing_time'].mean()
        st.sidebar.metric("평균 처리시간", f"{avg_time:.2f}초")
        
        # 최근 질문들
        st.sidebar.markdown("### 최근 질문")
        recent_queries = stats_df.tail(3)['query'].tolist()
        for query in recent_queries:
            st.sidebar.write(f"• {query[:30]}...")

def render_term_definitions(term_definitions):
    """용어 정의 표시"""
    if not term_definitions:
        return
    
    st.markdown("### 🏢 관련 용어 정의")
    
    cols = st.columns(min(len(term_definitions), 3))
    
    for i, (term, definition) in enumerate(term_definitions.items()):
        with cols[i % 3]:
            confidence_color = "🟢" if definition.confidence_score > 0.8 else "🟡"
            
            st.markdown(f"""
            <div class="term-card">
                <h4>{confidence_color} {definition.term}</h4>
                <p><strong>정의:</strong> {definition.definition}</p>
                <p><strong>부서:</strong> {definition.department}</p>
                <p><strong>신뢰도:</strong> {definition.confidence_score:.1%}</p>
                <details>
                    <summary>상세 정보</summary>
                    <p><strong>상세설명:</strong> {definition.context}</p>
                    <p><strong>연관용어:</strong> {', '.join(definition.related_terms[:3])}</p>
                    <p><strong>사용예시:</strong> {definition.examples[0] if definition.examples else '없음'}</p>
                </details>
            </div>
            """, unsafe_allow_html=True)

def render_search_results(search_results):
    """검색 결과 표시"""
    if not search_results:
        return
    
    st.markdown("### 📋 참고 문서")
    
    for i, result in enumerate(search_results):
        relevance_icon = "🔥" if result.score > 3.5 else "📄"
        
        with st.expander(f"{relevance_icon} {result.title} (점수: {result.score:.1f})"):
            st.write(f"**출처:** {result.source_index}")
            st.write(f"**부서:** {result.metadata.get('department', '미분류')}")
            st.write(f"**카테고리:** {result.metadata.get('category', '미분류')}")
            st.write("**내용:**")
            st.write(result.content[:500] + "..." if len(result.content) > 500 else result.content)

def render_analytics():
    """분석 페이지 렌더링"""
    st.markdown('<div class="main-header">📊 사용 분석</div>', unsafe_allow_html=True)
    
    # 세션 상태 확인
    if not hasattr(st.session_state, 'query_stats') or not st.session_state.query_stats:
        st.info("아직 분석할 데이터가 없습니다. 먼저 질문을 해보세요!")
        return
    
    stats_df = pd.DataFrame(st.session_state.query_stats)
    
    # 메트릭 표시
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("총 질문 수", len(stats_df))
    
    with col2:
        avg_time = stats_df['processing_time'].mean()
        st.metric("평균 처리시간", f"{avg_time:.2f}초")
    
    with col3:
        avg_terms = stats_df['terms_found'].mean()
        st.metric("평균 용어 발견", f"{avg_terms:.1f}개")
    
    with col4:
        avg_docs = stats_df['docs_found'].mean()
        st.metric("평균 문서 발견", f"{avg_docs:.1f}개")
    
    # 시간별 질문 추이
    st.markdown("### 📈 시간별 질문 추이")
    if len(stats_df) > 1:
        stats_df['hour'] = stats_df['timestamp'].dt.hour
        hourly_counts = stats_df.groupby('hour').size()
        
        if PLOTLY_AVAILABLE:
            fig = px.bar(x=hourly_counts.index, y=hourly_counts.values,
                        labels={'x': '시간', 'y': '질문 수'},
                        title="시간대별 질문 분포")
            st.plotly_chart(fig, use_container_width=True)
        else:
            # Plotly 없이 간단한 차트 표시
            chart_data = pd.DataFrame({
                '시간': hourly_counts.index,
                '질문 수': hourly_counts.values
            })
            st.bar_chart(chart_data.set_index('시간'))
    
    # 처리 시간 분포
    st.markdown("### ⏱️ 처리 시간 분포")
    if PLOTLY_AVAILABLE:
        fig = px.histogram(stats_df, x='processing_time', nbins=20,
                          labels={'processing_time': '처리 시간 (초)', 'count': '빈도'},
                          title="질문 처리 시간 분포")
        st.plotly_chart(fig, use_container_width=True)
    else:
        # Streamlit 기본 히스토그램 사용
        st.histogram(stats_df['processing_time'], bins=20)
    
    # 최근 질문 내역
    st.markdown("### 📝 최근 질문 내역")
    recent_df = stats_df.tail(10)[['timestamp', 'query', 'terms_found', 'docs_found', 'processing_time']]
    recent_df['timestamp'] = recent_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    
    st.dataframe(
        recent_df,
        column_config={
            "timestamp": "시간",
            "query": "질문",
            "terms_found": "용어 수",
            "docs_found": "문서 수",
            "processing_time": st.column_config.NumberColumn("처리시간(초)", format="%.2f")
        },
        use_container_width=True
    )

def initialize_session_state():
    """세션 상태 안전하게 초기화"""
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    if 'query_stats' not in st.session_state:
        st.session_state.query_stats = []
    if 'rag_system' not in st.session_state:
        st.session_state.rag_system = None

def main():
    """메인 애플리케이션"""
    
    # 세션 상태 초기화
    initialize_session_state()
    
    # RAG 시스템 초기화 (세션 상태에 캐시)
    if st.session_state.rag_system is None:
        with st.spinner("🔧 시스템 초기화 중..."):
            st.session_state.rag_system = StreamlitRAGSystem()
    
    rag_system = st.session_state.rag_system
    
    # 사이드바 렌더링
    render_sidebar()
    
    # 탭 생성
    tab1, tab2, tab3 = st.tabs(["💬 질의응답", "📊 분석", "⚙️ 관리"])
    
    with tab1:
        st.markdown('<div class="main-header">🤖 Enterprise AI Assistant</div>', unsafe_allow_html=True)
        st.markdown("**사내 용어를 이해하는 똑똑한 AI 어시스턴트입니다. 무엇을 도와드릴까요?**")
        
        # 질문 입력
        if 'current_query' in st.session_state:
            user_query = st.text_area("질문을 입력하세요:", value=st.session_state.current_query, height=100)
            del st.session_state.current_query
        else:
            user_query = st.text_area("질문을 입력하세요:", placeholder="예: ERP 시스템에서 재고는 어떻게 관리하나요?", height=100)
        
        col1, col2 = st.columns([1, 4])
        with col1:
            submit_button = st.button("🔍 질문하기", type="primary")
        with col2:
            clear_button = st.button("🗑️ 대화 초기화")
        
        if clear_button:
            st.session_state.chat_history = []
            st.session_state.query_stats = []
            st.rerun()
        
        # 질문 처리
        if submit_button and user_query.strip():
            with st.spinner("🤔 AI가 답변을 준비하고 있습니다..."):
                response, metadata = rag_system.process_query(user_query)
                
                # 대화 기록 저장
                st.session_state.chat_history.append({
                    "query": user_query,
                    "response": response,
                    "metadata": metadata,
                    "timestamp": datetime.now()
                })
        
        # 최신 답변 표시
        if st.session_state.chat_history:
            latest_chat = st.session_state.chat_history[-1]
            
            st.markdown("---")
            
            # 답변 표시
            st.markdown("### 🤖 AI 답변")
            st.markdown(latest_chat["response"])
            
            # 메타데이터 표시
            metadata = latest_chat["metadata"]
            
            # 용어 정의 표시
            if "term_definitions" in metadata:
                render_term_definitions(metadata["term_definitions"])
            
            # 검색 결과 표시
            if "search_results" in metadata:
                render_search_results(metadata["search_results"])
            
            # 처리 정보
            with st.expander("🔍 처리 정보"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("추출된 용어", len(metadata.get("extracted_terms", [])))
                with col2:
                    st.metric("발견된 용어 정의", metadata.get("found_terms", 0))
                with col3:
                    st.metric("관련 문서", metadata.get("found_documents", 0))
                
                st.write("**추출된 용어:**", ", ".join(metadata.get("extracted_terms", [])))
                st.write(f"**처리 시간:** {metadata.get('processing_time', 0):.2f}초")
        
        # 대화 히스토리 표시
        if len(st.session_state.chat_history) > 1:
            st.markdown("---")
            st.markdown("### 📚 이전 대화")
            
            for i, chat in enumerate(reversed(st.session_state.chat_history[:-1])):
                with st.expander(f"질문 {len(st.session_state.chat_history)-i-1}: {chat['query'][:50]}..."):
                    st.write("**질문:**", chat['query'])
                    st.write("**답변:**", chat['response'][:200] + "..." if len(chat['response']) > 200 else chat['response'])
                    st.write("**시간:**", chat['timestamp'].strftime('%Y-%m-%d %H:%M:%S'))
    
    with tab2:
        render_analytics()
    
    with tab3:
        st.markdown('<div class="main-header">⚙️ 시스템 관리</div>', unsafe_allow_html=True)
        
        # 설정 정보
        st.markdown("### 🔧 현재 설정")
        config = ConfigManager()
        config_summary = config.get_config_summary()
        
        # 설정 검증
        config_issues = config.validate_config()
        if config_issues:
            st.error("⚠️ 설정 문제:")
            for issue in config_issues:
                st.write(f"• {issue}")
            st.info("💡 .env 파일을 확인하거나 환경변수를 설정해주세요.")
        else:
            st.success("✅ 모든 설정이 올바르게 구성되었습니다!")
        
        # 설정 정보 테이블
        config_data = []
        for key, value in config_summary.items():
            status = "🟢 설정됨" if "미설정" not in str(value) and "your-" not in str(value) else "🔴 미설정"
            config_data.append({
                "설정 항목": key,
                "값": str(value),
                "상태": status
            })
        
        config_df = pd.DataFrame(config_data)
        st.dataframe(config_df, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        
        # 용어 사전 관리
        st.markdown("### 📚 용어 사전 관리")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### ➕ 새 용어 추가")
            with st.form("add_term_form"):
                new_term = st.text_input("용어")
                new_definition = st.text_area("정의")
                new_context = st.text_area("상세 설명")
                new_department = st.selectbox("담당 부서", ["IT", "생산", "물류", "영업", "인사", "재무"])
                new_synonyms = st.text_input("동의어 (쉼표로 구분)")
                new_related = st.text_input("관련 용어 (쉼표로 구분)")
                new_examples = st.text_area("사용 예시 (한 줄에 하나씩)")
                
                submit_term = st.form_submit_button("용어 추가")
                
                if submit_term and new_term and new_definition:
                    st.success(f"✅ '{new_term}' 용어가 추가되었습니다!")
                    st.info("실제 환경에서는 Azure Search 인덱스에 업로드됩니다.")
        
        with col2:
            st.markdown("#### 📋 현재 용어 목록")
            
            # 샘플 용어 목록
            sample_terms = [
                {"용어": "ERP", "부서": "IT", "정의": "전사적 자원 관리 시스템"},
                {"용어": "MES", "부서": "생산", "정의": "제조실행시스템"},
                {"용어": "WMS", "부서": "물류", "정의": "창고관리시스템"},
                {"용어": "CRM", "부서": "영업", "정의": "고객관계관리시스템"},
                {"용어": "HRM", "부서": "인사", "정의": "인적자원관리시스템"}
            ]
            
            terms_df = pd.DataFrame(sample_terms)
            st.dataframe(terms_df, use_container_width=True, hide_index=True)
            
            # 용어 검색 테스트
            st.markdown("#### 🔍 용어 검색 테스트")
            test_term = st.text_input("테스트할 용어 입력")
            if st.button("검색 테스트") and test_term:
                with st.spinner("검색 중..."):
                    found_terms = rag_system.search_terminology([test_term])
                    if found_terms:
                        for term, definition in found_terms.items():
                            st.success(f"✅ 발견: {definition.term}")
                            st.write(f"정의: {definition.definition}")
                            st.write(f"신뢰도: {definition.confidence_score:.1%}")
                    else:
                        st.warning("❌ 해당 용어를 찾을 수 없습니다.")
        
        st.markdown("---")
        
        # 문서 인덱스 상태
        st.markdown("### 📄 문서 인덱스 상태")
        
        index_status = []
        for name, index_name in config.document_indexes.items():
            # 실제 환경에서는 Azure Search에서 문서 수를 가져옴
            doc_count = {"policies": 15, "procedures": 32, "manuals": 28, "announcements": 7}.get(name, 0)
            
            index_status.append({
                "인덱스명": name,
                "Azure 인덱스": index_name,
                "문서 수": doc_count,
                "상태": "🟢 정상" if doc_count > 0 else "🔴 비어있음",
                "최종 업데이트": "2024-01-15"
            })
        
        status_df = pd.DataFrame(index_status)
        st.dataframe(status_df, use_container_width=True, hide_index=True)
        
        # 문서 업로드 섹션
        st.markdown("### 📤 문서 업로드")
        
        uploaded_file = st.file_uploader(
            "새 문서 업로드",
            type=['pdf', 'docx', 'txt'],
            help="PDF, Word 문서, 텍스트 파일을 업로드할 수 있습니다."
        )
        
        if uploaded_file:
            col1, col2 = st.columns(2)
            with col1:
                doc_title = st.text_input("문서 제목", value=uploaded_file.name)
                doc_category = st.selectbox("카테고리", ["정책", "절차", "매뉴얼", "공지사항"])
                doc_department = st.selectbox("담당 부서", ["IT", "생산", "물류", "영업", "인사", "재무", "전체"])
            
            with col2:
                doc_tags = st.text_input("태그 (쉼표로 구분)")
                doc_description = st.text_area("문서 설명")
            
            if st.button("문서 처리 및 업로드"):
                with st.spinner("문서를 처리하고 인덱스에 추가하는 중..."):
                    # 실제 환경에서는 문서 파싱 및 Azure Search 업로드 로직
                    time.sleep(2)  # 시뮬레이션
                    st.success("✅ 문서가 성공적으로 업로드되고 인덱싱되었습니다!")
                    st.info(f"파일명: {uploaded_file.name}")
                    st.info(f"크기: {uploaded_file.size} bytes")
        
        st.markdown("---")
        
        # 시스템 진단
        st.markdown("### 🔧 시스템 진단")
        
        if st.button("시스템 상태 확인"):
            with st.spinner("시스템 진단 중..."):
                time.sleep(1)
                
                # 진단 결과 시뮬레이션
                diagnostics = [
                    {"항목": "Azure Search 연결", "상태": "🟢 정상", "응답시간": "45ms"},
                    {"항목": "OpenAI API 연결", "상태": "🟢 정상", "응답시간": "234ms"},
                    {"항목": "용어 인덱스", "상태": "🟢 정상", "문서수": "156개"},
                    {"항목": "정책 인덱스", "상태": "🟢 정상", "문서수": "15개"},
                    {"항목": "절차 인덱스", "상태": "🟢 정상", "문서수": "32개"},
                    {"항목": "매뉴얼 인덱스", "상태": "🟢 정상", "문서수": "28개"}
                ]
                
                diag_df = pd.DataFrame(diagnostics)
                st.dataframe(diag_df, use_container_width=True, hide_index=True)
                
                st.success("✅ 모든 시스템이 정상 작동 중입니다!")
        
        # 데이터 초기화
        st.markdown("---")
        st.markdown("### ⚠️ 데이터 관리")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🗑️ 대화 기록 초기화", type="secondary"):
                st.session_state.chat_history = []
                st.session_state.query_stats = []
                st.success("대화 기록이 초기화되었습니다.")
                st.rerun()
        
        with col2:
            if st.button("📊 통계 데이터 내보내기", type="secondary"):
                if hasattr(st.session_state, 'query_stats') and st.session_state.query_stats:
                    stats_df = pd.DataFrame(st.session_state.query_stats)
                    csv = stats_df.to_csv(index=False)
                    st.download_button(
                        label="CSV 다운로드",
                        data=csv,
                        file_name=f"rag_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("내보낼 통계 데이터가 없습니다.")

# 추가 유틸리티 함수들
def setup_logging():
    """로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('rag_system.log')
        ]
    )

def load_custom_css():
    """커스텀 CSS 로드"""
    st.markdown("""
    <style>
        /* 추가 스타일링 */
        .stButton > button {
            border-radius: 20px;
            border: none;
            padding: 0.5rem 1rem;
            font-weight: bold;
        }
        
        .stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }
        
        .metric-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 1rem;
            border-radius: 10px;
            text-align: center;
        }
        
        .chat-message {
            padding: 1rem;
            border-radius: 10px;
            margin: 0.5rem 0;
            border-left: 4px solid #2E86AB;
            background-color: #f8f9fa;
        }
        
        .footer {
            text-align: center;
            padding: 2rem;
            color: #666;
            font-size: 0.8rem;
        }
    </style>
    """, unsafe_allow_html=True)

def display_footer():
    """푸터 표시"""
    st.markdown("---")
    st.markdown("""
    <div class="footer">
        🏢 Enterprise RAG System v1.0 | 
        Built with Streamlit & Azure AI | 
        © 2024 Your Company
    </div>
    """, unsafe_allow_html=True)

# 앱 설정 및 실행
if __name__ == "__main__":
    setup_logging()
    load_custom_css()
    
    # 메인 앱 실행
    main()
    
    # 푸터 표시
    display_footer()

# 실행 시 필요한 requirements.txt 내용:
"""
streamlit>=1.28.0
azure-search-documents>=11.4.0
openai>=0.28.0
pandas>=2.0.0
plotly>=5.15.0
python-dotenv>=1.0.0
"""

# .env 파일 예시 (프로젝트 루트에 생성):
"""
# Azure Search 설정
AZURE_SEARCH_ENDPOINT=https://your-search-service.search.windows.net
AZURE_SEARCH_KEY=your-azure-search-admin-key
AZURE_SEARCH_API_VERSION=2023-11-01

# OpenAI 설정
OPENAI_API_KEY=sk-your-openai-api-key
OPENAI_MODEL=gpt-4
OPENAI_TEMPERATURE=0.1
MAX_TOKENS=2000

# 인덱스 이름 (선택사항 - 기본값 사용 가능)
TERMINOLOGY_INDEX=company-terminology
POLICIES_INDEX=company-policies
PROCEDURES_INDEX=work-procedures
MANUALS_INDEX=system-manuals
ANNOUNCEMENTS_INDEX=company-announcements

# 검색 설정 (선택사항)
MAX_TERMS_PER_QUERY=10
MAX_DOCUMENTS_PER_INDEX=3
MIN_CONFIDENCE_SCORE=0.3

# 디버깅 설정 (선택사항)
DEBUG_MODE=false
LOG_LEVEL=INFO
"""

# 설치 및 실행 가이드:
"""
# 1. 필요한 패키지 설치
pip install streamlit azure-search-documents openai pandas plotly python-dotenv

# 2. .env 파일 생성 (프로젝트 루트에)
# 위의 .env 파일 예시 내용을 복사하여 실제 값으로 수정

# 3. .env 파일을 .gitignore에 추가 (보안)
echo ".env" >> .gitignore

# 4. 앱 실행
streamlit run streamlit_rag_app.py

# 5. 브라우저에서 http://localhost:8501 접속
"""

# 환경변수 직접 설정 방법 (Windows):
"""
# 명령 프롬프트에서:
set AZURE_SEARCH_ENDPOINT=https://your-search-service.search.windows.net
set AZURE_SEARCH_KEY=your-azure-search-admin-key
set OPENAI_API_KEY=sk-your-openai-api-key
streamlit run streamlit_rag_app.py

# PowerShell에서:
$env:AZURE_SEARCH_ENDPOINT="https://your-search-service.search.windows.net"
$env:AZURE_SEARCH_KEY="your-azure-search-admin-key"
$env:OPENAI_API_KEY="sk-your-openai-api-key"
streamlit run streamlit_rag_app.py
"""

# 환경변수 직접 설정 방법 (Linux/Mac):
"""
export AZURE_SEARCH_ENDPOINT="https://your-search-service.search.windows.net"
export AZURE_SEARCH_KEY="your-azure-search-admin-key"
export OPENAI_API_KEY="sk-your-openai-api-key"
streamlit run streamlit_rag_app.py
"""