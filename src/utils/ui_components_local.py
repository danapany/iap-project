import streamlit as st

class UIComponentsLocal:
    """UI 컴포넌트 관리 클래스"""
    
    def render_main_ui(self):
        """메인 UI 렌더링"""
        html_code = """
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                background: #f0f8ff;
                font-family: 'Arial', sans-serif;
                padding: 20px;
            }
            
            .ghibli-container {
                background: linear-gradient(180deg, #e8f4fd 0%, #c3e9ff 100%);
                padding: 60px 40px;
                border-radius: 25px;
                margin: 20px 0;
                position: relative;
                min-height: 350px;
                overflow: hidden;
                max-width: 1000px;
                box-shadow: 0 20px 60px rgba(135, 206, 250, 0.2);
            }
            
            .cloud {
                position: absolute;
                background: rgba(255, 255, 255, 0.7);
                border-radius: 50px;
                opacity: 0.8;
                animation: float-gentle 8s ease-in-out infinite;
            }
            
            .cloud1 {
                width: 100px;
                height: 40px;
                top: 20px;
                left: 10%;
            }
            
            .cloud2 {
                width: 80px;
                height: 35px;
                top: 15px;
                right: 15%;
                animation-delay: -2s;
            }
            
            .cloud3 {
                width: 60px;
                height: 25px;
                bottom: 30px;
                left: 20%;
                animation-delay: -4s;
            }
            
            @keyframes float-gentle {
                0%, 100% { transform: translateY(0px) translateX(0px); }
                33% { transform: translateY(-8px) translateX(5px); }
                66% { transform: translateY(3px) translateX(-3px); }
            }
            
            .title {
                text-align: center;
                color: #2c3e50;
                font-size: 22px;
                font-weight: 400;
                margin-bottom: 50px;
                font-family: 'Arial', sans-serif;
                letter-spacing: 1px;
            }
            
            .journey-path {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 40px;
                position: relative;
                flex-wrap: wrap;
            }
            
            .step-circle {
                width: 80px;
                height: 80px;
                background: rgba(255, 255, 255, 0.95);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 28px;
                box-shadow: 0 8px 25px rgba(135, 206, 250, 0.3);
                transition: all 0.4s ease;
                position: relative;
                animation: breathe 4s ease-in-out infinite;
                border: 2px solid rgba(135, 206, 250, 0.2);
            }
            
            .step-circle:nth-child(1) { animation-delay: 0s; }
            .step-circle:nth-child(3) { animation-delay: 0.8s; }
            .step-circle:nth-child(5) { animation-delay: 1.6s; }
            .step-circle:nth-child(7) { animation-delay: 2.4s; }
            .step-circle:nth-child(9) { animation-delay: 3.2s; }
            
            @keyframes breathe {
                0%, 100% { transform: scale(1); box-shadow: 0 8px 25px rgba(135, 206, 250, 0.3); }
                50% { transform: scale(1.05); box-shadow: 0 12px 35px rgba(135, 206, 250, 0.5); }
            }
            
            .step-circle:hover {
                transform: scale(1.1) translateY(-5px);
                box-shadow: 0 15px 40px rgba(135, 206, 250, 0.6);
            }
            
            .step-label {
                position: absolute;
                bottom: -35px;
                left: 50%;
                transform: translateX(-50%);
                font-size: 12px;
                color: #34495e;
                white-space: nowrap;
                font-weight: 300;
                letter-spacing: 0.5px;
            }
            
            .path-line {
                width: 30px;
                height: 2px;
                background: linear-gradient(90deg, #87ceeb, #add8e6);
                border-radius: 1px;
                position: relative;
                animation: flow 3s ease-in-out infinite;
            }
            
            @keyframes flow {
                0%, 100% { opacity: 0.6; }
                50% { opacity: 1; }
            }
            
            .path-line::before {
                content: '';
                position: absolute;
                right: -3px;
                top: -1px;
                width: 0;
                height: 0;
                border-left: 4px solid #87ceeb;
                border-top: 2px solid transparent;
                border-bottom: 2px solid transparent;
            }
            
            .subtitle {
                text-align: center;
                margin-top: 60px;
                color: #5d6d7e;
                font-size: 14px;
                font-weight: 300;
                letter-spacing: 1px;
                font-style: italic;
            }
            
            .decoration {
                position: absolute;
                color: rgba(135, 206, 250, 0.6);
                font-size: 12px;
                animation: twinkle 3s ease-in-out infinite;
            }
            
            @keyframes twinkle {
                0%, 100% { opacity: 0.3; transform: scale(0.8); }
                50% { opacity: 1; transform: scale(1.2); }
            }
            
            .deco1 { top: 40px; left: 5%; animation-delay: 0s; }
            .deco2 { top: 80px; right: 8%; animation-delay: 1.5s; }
            .deco3 { bottom: 50px; left: 12%; animation-delay: 3s; }
            
            @media (max-width: 768px) {
                .journey-path {
                    flex-direction: column;
                    gap: 25px;
                }
                
                .path-line {
                    width: 2px;
                    height: 25px;
                    transform: rotate(90deg);
                }
                
                .path-line::before {
                    right: -1px;
                    top: -3px;
                    border-left: 2px solid transparent;
                    border-right: 2px solid transparent;
                    border-top: 4px solid #87ceeb;
                }
                
                .ghibli-container {
                    padding: 40px 20px;
                    min-height: 600px;
                    margin: 20px 0;
                }
            }

        </style>
        <div class="ghibli-container">
            <div class="decoration deco1">✦</div>
            <div class="decoration deco2">✧</div>
            <div class="decoration deco3">✦</div>
            <div class="title">AI를 활용하여 신속한 장애복구에 활용해보세요!</div>
            <div class="journey-path">
                <div class="step-circle">
                    🤔
                    <div class="step-label"><b>복구방법</b></div>
                </div>
                <div class="path-line"></div>
                <div class="step-circle">
                    🎯
                    <div class="step-label"><b>장애원인</b></div>
                </div>
                <div class="path-line"></div>
                <div class="step-circle">
                    💡
                    <div class="step-label"><b>장애현상</b></div>
                </div>
                <div class="path-line"></div>
                <div class="step-circle">
                    ⚖️
                    <div class="step-label"><b>이력조회</b></div>
                </div>
                <div class="path-line"></div>
                <div class="step-circle">
                    ✨
                    <div class="step-label"><b>장애건수</b></div>
                </div>
            </div>
        </div>
        <div>
        <h4>💬 질문예시</h4>
        <h6>* 복구방법 : 마이페이지 보험가입불가 현상 복구방법 알려줘<br>
        * 장애원인 : ERP EP업무 처리시 간헐적 접속불가현상에 대한 장애원인이 뭐야?<br>
        * 장애현상 : 문자발송 불가 현상에 대한 과거 조치방법 알려줘<br>
        * 장애이력 : 야간에 발생한 블록체인기반지역화폐 장애내역 알려줘<br>
        * 장애건수 : 2025년 ERP 장애가 몇건이야? 
        </h6>
        </div>
        """
        
        st.markdown(html_code, unsafe_allow_html=True)
    
    def show_config_error(self, env_status):
        """설정 오류 표시"""
        st.error("환경변수 설정이 필요합니다.")
        st.info("""
        **설정해야 할 환경변수:**
        - OPENAI_ENDPOINT: Azure OpenAI 엔드포인트 URL
        - OPENAI_KEY: Azure OpenAI API 키
        - SEARCH_ENDPOINT: Azure AI Search 엔드포인트 URL  
        - SEARCH_API_KEY: Azure AI Search API 키
        - INDEX_REBUILD_NAME: 검색할 인덱스명

        **.env 파일 예시:**
        ```
        OPENAI_ENDPOINT=https://your-openai-resource.openai.azure.com/
        OPENAI_KEY=your-openai-api-key
        OPENAI_API_VERSION=2024-02-01
        CHAT_MODEL=iap-gpt-4o-mini
        SEARCH_ENDPOINT=https://your-search-service.search.windows.net
        SEARCH_API_KEY=your-search-api-key
        INDEX_REBUILD_NAME=your-index-name
        ```
        
        **참고**: 로컬 검색 전용 버전에서는 SERPAPI_API_KEY가 필요하지 않습니다.
        """)
        
        st.write("**환경변수 상태:**")
        for var, status in env_status.items():
            st.write(f"{status} {var}")
    
    def show_connection_error(self):
        """연결 오류 표시"""
        st.error("Azure 서비스 연결에 실패했습니다. 환경변수를 확인해주세요.")
        st.info("""
        **필요한 환경변수:**
        - OPENAI_ENDPOINT: Azure OpenAI 엔드포인트
        - OPENAI_KEY: Azure OpenAI API 키
        - OPENAI_API_VERSION: API 버전 (기본값: 2024-02-01)
        - CHAT_MODEL: 모델명 (기본값: iap-gpt-4o-mini)
        - SEARCH_ENDPOINT: Azure AI Search 엔드포인트
        - SEARCH_API_KEY: Azure AI Search API 키
        - INDEX_REBUILD_NAME: 검색 인덱스명
        """)
    
    def display_chat_messages(self):
        """채팅 메시지 표시"""
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
    
    def display_documents_with_quality_info(self, documents):
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
            
            st.markdown(f"### {tier_emoji} **문서 {i+1}** - {quality_tier}급 {tier_color} {match_emoji} {match_label} ")
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
                st.write(f"**영향도**: {doc['effect']}")
                st.write(f"**현상**: {doc['symptom']}")

            with col2:
                st.write(f"**장애등급**: {doc['incident_grade']}")
                st.write(f"**장애원인**: {doc['root_cause']}")
                st.write(f"**원인유형**: {doc['cause_type']}")
                st.write(f"**처리유형**: {doc['done_type']}")
                st.write(f"**담당부서**: {doc['owner_depart']}")
            
            if doc['root_cause']:
                st.write(f"**장애원인**: {doc['root_cause'][:200]}...")
            if doc['incident_repair']:
                st.write(f"**복구방법**: {doc['incident_repair'][:200]}...")
            if doc['repair_notice']:
                st.write(f"**복구공지**: {doc['repair_notice'][:200]}...")
            
            st.markdown("---")