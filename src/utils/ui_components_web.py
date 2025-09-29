import streamlit as st

class UIComponents:
    """웹 검색 기반 UI 컴포넌트 관리 클래스 - 세션 분리 지원"""
    
    def render_main_ui(self):
        """웹 검색 전용 메인 UI 렌더링"""
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
            
            .web-search-container {
                background: linear-gradient(180deg, #e6f3ff 0%, #b3d9ff 100%);
                padding: 60px 40px;
                border-radius: 25px;
                margin: 20px 0;
                position: relative;
                min-height: 350px;
                overflow: hidden;
                max-width: 1000px;
                box-shadow: 0 20px 60px rgba(30, 144, 255, 0.2);
            }
            
            .search-icon {
                position: absolute;
                color: rgba(30, 144, 255, 0.6);
                font-size: 20px;
                animation: float-search 6s ease-in-out infinite;
            }
            
            .search1 {
                top: 20px;
                left: 10%;
                animation-delay: 0s;
            }
            
            .search2 {
                top: 30px;
                right: 15%;
                animation-delay: -2s;
            }
            
            .search3 {
                bottom: 40px;
                left: 20%;
                animation-delay: -4s;
            }
            
            @keyframes float-search {
                0%, 100% { 
                    transform: translateY(0px) rotate(0deg); 
                    opacity: 0.6; 
                }
                33% { 
                    transform: translateY(-10px) rotate(5deg); 
                    opacity: 1; 
                }
                66% { 
                    transform: translateY(5px) rotate(-3deg); 
                    opacity: 0.8; 
                }
            }
            
            .title {
                text-align: center;
                color: #1e3a8a;
                font-size: 24px;
                font-weight: 500;
                margin-bottom: 50px;
                font-family: 'Arial', sans-serif;
                letter-spacing: 1px;
            }
            
            .web-journey-path {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 40px;
                position: relative;
                flex-wrap: wrap;
            }
            
            .web-step-circle {
                width: 85px;
                height: 85px;
                background: rgba(255, 255, 255, 0.95);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 30px;
                box-shadow: 0 10px 30px rgba(30, 144, 255, 0.3);
                transition: all 0.4s ease;
                position: relative;
                animation: web-breathe 5s ease-in-out infinite;
                border: 3px solid rgba(30, 144, 255, 0.2);
            }
            
            .web-step-circle:nth-child(1) { animation-delay: 0s; }
            .web-step-circle:nth-child(3) { animation-delay: 1s; }
            .web-step-circle:nth-child(5) { animation-delay: 2s; }
            .web-step-circle:nth-child(7) { animation-delay: 3s; }
            
            @keyframes web-breathe {
                0%, 100% { 
                    transform: scale(1); 
                    box-shadow: 0 10px 30px rgba(30, 144, 255, 0.3); 
                }
                50% { 
                    transform: scale(1.08); 
                    box-shadow: 0 15px 40px rgba(30, 144, 255, 0.5); 
                }
            }
            
            .web-step-circle:hover {
                transform: scale(1.15) translateY(-8px);
                box-shadow: 0 20px 50px rgba(30, 144, 255, 0.6);
            }
            
            .web-step-label {
                position: absolute;
                bottom: -40px;
                left: 50%;
                transform: translateX(-50%);
                font-size: 13px;
                color: #1e3a8a;
                white-space: nowrap;
                font-weight: 400;
                letter-spacing: 0.5px;
            }
            
            .web-path-line {
                width: 35px;
                height: 3px;
                background: linear-gradient(90deg, #1e90ff, #4169e1);
                border-radius: 2px;
                position: relative;
                animation: web-flow 4s ease-in-out infinite;
            }
            
            @keyframes web-flow {
                0%, 100% { 
                    opacity: 0.7; 
                    transform: scaleX(1); 
                }
                50% { 
                    opacity: 1; 
                    transform: scaleX(1.1); 
                }
            }
            
            .web-path-line::before {
                content: '';
                position: absolute;
                right: -4px;
                top: -2px;
                width: 0;
                height: 0;
                border-left: 5px solid #1e90ff;
                border-top: 3px solid transparent;
                border-bottom: 3px solid transparent;
            }
            
            .web-subtitle {
                text-align: center;
                margin-top: 70px;
                color: #4682b4;
                font-size: 15px;
                font-weight: 300;
                letter-spacing: 1px;
                font-style: italic;
            }
            
            .web-decoration {
                position: absolute;
                color: rgba(30, 144, 255, 0.5);
                font-size: 14px;
                animation: web-twinkle 4s ease-in-out infinite;
            }
            
            @keyframes web-twinkle {
                0%, 100% { 
                    opacity: 0.3; 
                    transform: scale(0.9); 
                }
                50% { 
                    opacity: 1; 
                    transform: scale(1.3); 
                }
            }
            
            .web-deco1 { top: 50px; left: 8%; animation-delay: 0s; }
            .web-deco2 { top: 90px; right: 10%; animation-delay: 2s; }
            .web-deco3 { bottom: 60px; left: 15%; animation-delay: 4s; }
            
            @media (max-width: 768px) {
                .web-journey-path {
                    flex-direction: column;
                    gap: 30px;
                }
                
                .web-path-line {
                    width: 3px;
                    height: 30px;
                    transform: rotate(90deg);
                }
                
                .web-path-line::before {
                    right: -2px;
                    top: -4px;
                    border-left: 3px solid transparent;
                    border-right: 3px solid transparent;
                    border-top: 5px solid #1e90ff;
                }
                
                .web-search-container {
                    padding: 40px 20px;
                    min-height: 700px;
                    margin: 20px 0;
                }
                
                .title {
                    font-size: 20px;
                }
                
                .web-step-circle {
                    width: 75px;
                    height: 75px;
                    font-size: 26px;
                }
            }
        </style>
        <div class="web-search-container">
            <div class="search-icon search1">🔍</div>
            <div class="search-icon search2">🌐</div>
            <div class="search-icon search3">📊</div>
            <div class="web-decoration web-deco1">✦</div>
            <div class="web-decoration web-deco2">✧</div>
            <div class="web-decoration web-deco3">✦</div>
            <div class="title">웹 검색을 통해 IT 문제 해결에 도움을 받아보세요!</div>
            <div class="web-journey-path">
                <div class="web-step-circle">
                    🔧
                    <div class="web-step-label"><b>문제해결</b></div>
                </div>
                <div class="web-path-line"></div>
                <div class="web-step-circle">
                    🔍
                    <div class="web-step-label"><b>복구절차</b></div>
                </div>
                <div class="web-path-line"></div>
                <div class="web-step-circle">
                    📋
                    <div class="web-step-label"><b>설정가이드</b></div>
                </div>
                <div class="web-path-line"></div>
                <div class="web-step-circle">
                    💡
                    <div class="web-step-label"><b>일반문의</b></div>
                </div>
            </div>
        </div>
        <div>
        <h4>💬 질문예시 (웹 검색 기반)</h4>
        <h6>* Azure 환경 WEB 서비스 장애 시 긴급 복구 절차는?<br>
        * 오라클 DB 백업 파일에서 데이터베이스를 복원하는 방법은?<br>
        * 서버나 웹 서비스가 갑자기 다운됐을 때 초기 점검 순서는?<br>
        * Docker 컨테이너 설정 방법에 대해 설명해줘<br>
        * Kubernetes 클러스터 모니터링 모범 사례 알려줘
        
        </h6>
        </div>
        """
        
        st.markdown(html_code, unsafe_allow_html=True)
    
    def show_config_error(self, env_status):
        """웹 검색 전용 설정 오류 표시"""
        st.error("환경변수 설정이 필요합니다.")
        st.info("""
        **웹 검색 기반 챗봇 설정 방법:**
        
        **필수 환경변수:**
        - OPENAI_ENDPOINT: Azure OpenAI 엔드포인트 URL
        - OPENAI_KEY: Azure OpenAI API 키
        - SERPAPI_API_KEY: SerpApi 키 (Google 검색용)

        **.env 파일 예시:**
        ```
        OPENAI_ENDPOINT=https://your-openai-resource.openai.azure.com/
        OPENAI_KEY=your-openai-api-key
        OPENAI_API_VERSION=2024-02-01
        CHAT_MODEL=gpt-4o-mini
        SERPAPI_API_KEY=your-serpapi-key
        ```
        
        **SerpApi 설정 방법:**
        1. https://serpapi.com 에서 무료 계정 생성
        2. API 키 발급 (월 100회 무료)
        3. .env 파일에 SERPAPI_API_KEY 추가
        
        **주의사항:**
        - SerpApi는 웹 검색 기반 챗봇의 핵심 기능으로 필수입니다
        - Azure AI Search 관련 설정은 더 이상 필요하지 않습니다
        """)
        
        st.write("**환경변수 상태:**")
        for var, status in env_status.items():
            st.write(f"{status} {var}")
    
    def show_connection_error(self):
        """웹 검색 전용 연결 오류 표시"""
        st.error("Azure OpenAI 서비스 연결에 실패했습니다. 환경변수를 확인해주세요.")
        st.info("""
        **웹 검색 기반 챗봇 필요 환경변수:**
        - OPENAI_ENDPOINT: Azure OpenAI 엔드포인트
        - OPENAI_KEY: Azure OpenAI API 키
        - OPENAI_API_VERSION: API 버전 (기본값: 2024-02-01)
        - CHAT_MODEL: 모델명 (기본값: gpt-4o-mini)
        - SERPAPI_API_KEY: SerpApi 키 (Google 검색용, 필수)
        
        **참고:**
        - 이 버전은 웹 검색 전용으로 Azure AI Search는 사용하지 않습니다
        - SerpApi를 통한 Google 검색만 사용합니다
        """)
    
    def display_chat_messages(self, messages_key="messages"):
        """채팅 메시지 표시 - 세션 키 지원"""
        chat_container = st.container()
        
        with chat_container:
            # 지정된 세션 키의 이전 메시지 표시
            messages = st.session_state.get(messages_key, [])
            
            for message in messages:
                with st.chat_message(message["role"]):
                    if message["role"] == "assistant":
                        with st.expander("🤖 AI 답변 보기", expanded=True):
                            st.write(message["content"])
                    else:
                        st.write(message["content"])
    
    def display_search_results(self, search_results, query_type="default"):
        """웹 검색 결과 표시"""
        if not search_results:
            st.warning("검색 결과가 없습니다.")
            return
        
        # 쿼리 타입에 따른 제목 설정
        type_titles = {
            'repair': '🔧 문제 해결 관련 웹 검색 결과',
            'cause': '🔍 원인 분석 관련 웹 검색 결과',
            'similar': '📋 유사 사례 관련 웹 검색 결과',
            'default': '🌐 관련 웹 검색 결과'
        }
        
        st.markdown(f"### {type_titles.get(query_type, type_titles['default'])}")
        
        for i, result in enumerate(search_results, 1):
            with st.expander(f"🔗 검색 결과 {i}: {result.get('title', 'No Title')}", expanded=False):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.markdown(f"**출처:** {result.get('source', 'Unknown')}")
                    st.markdown(f"**내용:** {result.get('snippet', 'No description available')}")
                
                with col2:
                    if result.get('link'):
                        st.link_button("바로가기", result['link'])
                
                st.markdown("---")
    
    def show_web_search_status(self, status_type, message=""):
        """웹 검색 상태 표시"""
        if status_type == "searching":
            st.info(f"🔍 웹에서 검색 중... {message}")
        elif status_type == "found":
            st.success(f"✅ 검색 완료! {message}")
        elif status_type == "not_found":
            st.warning(f"⚠️ 검색 결과 없음: {message}")
        elif status_type == "error":
            st.error(f"❌ 검색 오류: {message}")
        elif status_type == "analyzing":
            st.info(f"🤖 AI 분석 중... {message}")
    
    def show_serpapi_setup_guide(self):
        """SerpApi 설정 가이드 표시"""
        with st.expander("🔧 SerpApi 설정 가이드", expanded=False):
            st.markdown("""
            ### SerpApi 무료 설정 방법
            
            1. **계정 생성**
               - https://serpapi.com 방문
               - 무료 계정 생성 (월 100회 검색 무료)
            
            2. **API 키 발급**
               - 대시보드에서 API Key 복사
               - 예: `abc123def456ghi789...`
            
            3. **환경변수 설정**
               ```
               SERPAPI_API_KEY=your-api-key-here
               ```
            
            4. **앱 재시작**
               - 환경변수 설정 후 앱 재시작
            
            ### 사용량 관리
            - 무료 계정: 월 100회 검색
            - 사용량 확인: SerpApi 대시보드
            - 필요시 유료 플랜 업그레이드 가능
            """)
    
    def display_reliability_assessment(self, assessment):
        """검색 결과 신뢰성 평가 표시"""
        reliability_level = assessment.get('reliability_level', 'unknown')
        reliability_score = assessment.get('reliability_score', 0)
        assessment_reason = assessment.get('assessment_reason', '평가 정보 없음')
        
        # 신뢰성 수준에 따른 색상과 아이콘
        if reliability_level == 'high':
            st.success(f"🟢 **높은 신뢰성** ({reliability_score}/100점)")
            st.info(f"📋 평가 근거: {assessment_reason}")
        elif reliability_level == 'medium':
            st.info(f"🟡 **보통 신뢰성** ({reliability_score}/100점)")
            st.warning(f"📋 평가 근거: {assessment_reason}")
        elif reliability_level == 'low':
            st.warning(f"🟠 **낮은 신뢰성** ({reliability_score}/100점)")
            st.warning(f"📋 평가 근거: {assessment_reason}")
        else:
            st.error(f"🔴 **신뢰성 부족** ({reliability_score}/100점)")
            st.error(f"📋 평가 근거: {assessment_reason}")
        
        # 권장사항 표시
        if reliability_level in ['low', 'unreliable']:
            st.info("💡 **권장사항**: 추가적인 공식 문서 확인이나 전문가 상담을 받으시기 바랍니다.")
        elif reliability_level == 'medium':
            st.info("💡 **권장사항**: 실제 적용 전 테스트 환경에서 검증해보시기 바랍니다.")

    def show_session_info(self, session_key, debug_mode=False):
        """세션 정보 표시 (디버그 모드에서만)"""
        if not debug_mode:
            return
            
        with st.expander("🔑 세션 정보 (DEBUG)", expanded=False):
            st.info(f"**현재 세션**: {session_key}")
            st.info(f"**메시지 키**: {session_key}_messages")
            
            # 현재 세션의 메시지 수 표시
            messages_key = f"{session_key}_messages"
            message_count = len(st.session_state.get(messages_key, []))
            st.info(f"**저장된 메시지**: {message_count}개")
            
            # 세션 상태 키 목록 (웹 버전 관련만)
            web_keys = [key for key in st.session_state.keys() if key.startswith(session_key)]
            if web_keys:
                st.info(f"**웹 세션 상태 키**: {len(web_keys)}개")
                for key in web_keys[:5]:  # 최대 5개만 표시
                    st.text(f"  - {key}")
                if len(web_keys) > 5:
                    st.text(f"  ... 및 {len(web_keys) - 5}개 더")

    def show_web_search_improvements(self, debug_mode=False):
        """웹 검색 개선사항 표시 (디버그 모드에서만)"""
        if not debug_mode:
            return
            
        with st.expander("🚀 웹 검색 챗봇 개선사항 (DEBUG)", expanded=False):
            st.markdown("""
            ### 🔄 세션 분리
            - ✅ 웹 버전 전용 세션 키 (`web_chatbot`)
            - ✅ 로컬 버전과 독립적인 메시지 관리
            - ✅ 웹 검색 상태 별도 관리
            
            ### 🧠 지능적 질문 처리
            - ✅ IT 관련 질문 자동 필터링
            - ✅ 쿼리 타입 자동 분류 (repair/cause/similar/default)
            - ✅ 서비스명 자동 추출
            
            ### 🌐 고급 웹 검색
            - ✅ SerpApi 기반 실시간 Google 검색
            - ✅ 검색 결과 품질 평가
            - ✅ 신뢰성 기반 답변 생성
            
            ### 🛡️ 오류 처리 및 대안
            - ✅ 웹 검색 실패 시 일반 IT 지식 제공
            - ✅ SerpApi 미설정 시 안내 메시지
            - ✅ 단계적 오류 복구 시스템
            
            ### 📊 사용자 경험
            - ✅ 질문 길이 제한 및 안내
            - ✅ 처리 상태별 스피너 표시
            - ✅ DEBUG 모드 지원
            """)

    def clear_web_session(self, session_key):
        """웹 세션 데이터 초기화"""
        messages_key = f"{session_key}_messages"
        last_query_key = f"{session_key}_last_query"
        
        # 웹 세션 관련 모든 키 찾기
        web_keys = [key for key in st.session_state.keys() if key.startswith(session_key)]
        
        # 웹 세션 데이터 초기화
        for key in web_keys:
            if key in st.session_state:
                del st.session_state[key]
        
        # 기본 세션 키 재설정
        st.session_state[messages_key] = []
        st.session_state[last_query_key] = ""
        st.session_state[session_key] = True
        
        st.success("🔄 웹 검색 챗봇 세션이 초기화되었습니다.")

    def show_clear_session_button(self, session_key, debug_mode=False):
        """세션 초기화 버튼 표시 (디버그 모드에서만)"""
        if not debug_mode:
            return
            
        with st.expander("🔄 세션 관리 (DEBUG)", expanded=False):
            if st.button("웹 세션 초기화", key=f"clear_{session_key}"):
                self.clear_web_session(session_key)
                st.experimental_rerun()

    def show_query_validation_info(self, validation_result, debug_mode=False):
        """질문 검증 결과 표시 (디버그 모드에서만)"""
        if not debug_mode or not validation_result:
            return
            
        with st.expander("🔍 질문 검증 결과 (DEBUG)", expanded=False):
            if validation_result.get('is_it_related'):
                st.success("✅ IT 기술 관련 질문으로 확인됨")
            else:
                st.warning("⚠️ IT 기술과 관련이 없는 질문")
            
            if validation_result.get('extracted_service'):
                st.info(f"🎯 추출된 서비스명: {validation_result['extracted_service']}")
            
            if validation_result.get('query_type'):
                st.info(f"📋 분류된 쿼리 타입: {validation_result['query_type']}")
            
            if validation_result.get('confidence_score'):
                st.metric("신뢰도 점수", f"{validation_result['confidence_score']:.2f}")

    def show_search_metrics(self, search_metrics, debug_mode=False):
        """검색 성능 메트릭 표시 (디버그 모드에서만)"""
        if not debug_mode or not search_metrics:
            return
            
        with st.expander("📊 검색 성능 메트릭 (DEBUG)", expanded=False):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if 'search_time' in search_metrics:
                    st.metric("검색 시간", f"{search_metrics['search_time']:.2f}초")
                if 'total_results' in search_metrics:
                    st.metric("총 검색 결과", f"{search_metrics['total_results']}개")
            
            with col2:
                if 'filtered_results' in search_metrics:
                    st.metric("필터링된 결과", f"{search_metrics['filtered_results']}개")
                if 'reliability_score' in search_metrics:
                    st.metric("신뢰성 점수", f"{search_metrics['reliability_score']}/100")
            
            with col3:
                if 'response_time' in search_metrics:
                    st.metric("응답 생성 시간", f"{search_metrics['response_time']:.2f}초")
                if 'tokens_used' in search_metrics:
                    st.metric("사용된 토큰", f"{search_metrics['tokens_used']:,}")

    def show_advanced_debug_info(self, debug_info, debug_mode=False):
        """고급 디버그 정보 표시 (디버그 모드에서만)"""
        if not debug_mode or not debug_info:
            return
            
        with st.expander("🔧 고급 디버그 정보 (DEBUG)", expanded=False):
            if debug_info.get('search_keywords'):
                st.text_area("검색 키워드", debug_info['search_keywords'], height=50)
            
            if debug_info.get('llm_prompts'):
                for i, prompt in enumerate(debug_info['llm_prompts']):
                    st.text_area(f"LLM 프롬프트 {i+1}", prompt[:500] + "...", height=100)
            
            if debug_info.get('processing_steps'):
                st.markdown("**처리 단계:**")
                for step in debug_info['processing_steps']:
                    st.text(f"• {step}")
            
            if debug_info.get('error_logs'):
                st.markdown("**오류 로그:**")
                for error in debug_info['error_logs']:
                    st.error(error)