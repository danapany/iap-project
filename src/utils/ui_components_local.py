import streamlit as st

class UIComponentsLocal:
    """UI 컴포넌트 관리 클래스 - 시간대/요일 정보 표시 지원 추가"""
    
    def __init__(self):
        # 디버그 모드 설정 (개발 시에만 True로 설정)
        self.debug_mode = False
    
    def render_main_ui(self):
        """메인 UI 렌더링 - 적응형 처리 정보 포함"""
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
        * 유사사례 : 문자발송 실패 현상에 대한 조치방법 알려줘<br>
        * 장애이력 : 블록체인기반지역화폐 야간에 발생한 장애내역 알려줘<br>
        * 장애건수 : 2025년 ERP 장애가 몇건이야?<p>

        <font color="red"> ※ 서비스명을 정확히 입력하시고 같이 검색하시면 보다 더 정확한 답변을 얻을 수 있습니다<br>
        ※ 대량조회가 안되도록 임계치 설정이 있으므로 통계성 질문은 일부 다를수있다는 점 양해 부탁드립니다.
        </font>
        </h6>
        </div>
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
                        # 간단하게 표시 (expander 제거)
                        st.write(message["content"])
                    else:
                        st.write(message["content"])
    
    def display_documents_with_quality_info(self, documents):
        """품질 정보와 처리 방식 정보를 포함한 향상된 문서 표시 - 시간 정보 추가"""
        for i, doc in enumerate(documents):
            quality_tier = doc.get('quality_tier', 'Standard')
            filter_reason = doc.get('filter_reason', '기본 선별')
            service_match_type = doc.get('service_match_type', 'unknown')
            search_score = doc.get('score', 0)
            reranker_score = doc.get('reranker_score', 0)
            final_score = doc.get('final_score', 0)
            relevance_score = doc.get('relevance_score', None)
            keyword_relevance = doc.get('keyword_relevance_score', None)
            semantic_similarity = doc.get('semantic_similarity', None)
            
            # 시간 정보
            daynight = doc.get('daynight', '')
            week = doc.get('week', '')
            
            # 품질 등급에 따른 표시
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
            match_emoji = {"exact": "🎯", "partial": "🔍", "all": "📋", "fallback": "🔄"}.get(service_match_type, "❓")
            match_label = {
                "exact": "정확 매칭", 
                "partial": "포함 매칭", 
                "all": "전체", 
                "fallback": "대체 검색",
                "unknown": "알 수 없음"
            }.get(service_match_type, "알 수 없음")
            
            # 시간 정보 표시
            time_info = ""
            if daynight:
                time_emoji = "🌞" if daynight == "주간" else "🌙"
                time_info += f" {time_emoji} {daynight}"
            if week:
                time_info += f" 📅 {week}요일" if week not in ['평일', '주말'] else f" 📅 {week}"
            
            # 디버그 모드에서만 상세 정보 표시
            if self.debug_mode:
                st.markdown(f"### {tier_emoji} **문서 {i+1}** - {quality_tier}급 {tier_color} {match_emoji} {match_label}{time_info}")
                st.markdown(f"**선별 기준**: {filter_reason}")
                
                # 점수 정보 표시 (확장된 메트릭 포함)
                score_cols = st.columns(4 if relevance_score or keyword_relevance or semantic_similarity else 3)
                
                with score_cols[0]:
                    st.metric("검색 점수", f"{search_score:.2f}")
                with score_cols[1]:
                    if reranker_score > 0:
                        st.metric("Reranker 점수", f"{reranker_score:.2f}")
                    else:
                        st.metric("Reranker 점수", "N/A")
                with score_cols[2]:
                    st.metric("최종 점수", f"{final_score:.2f}")
                
                # 추가 점수 정보 (적응형 처리에서 계산된 경우)
                if len(score_cols) > 3:
                    with score_cols[3]:
                        if relevance_score is not None:
                            st.metric("관련성 점수", f"{relevance_score}점")
                        elif keyword_relevance is not None:
                            st.metric("키워드 점수", f"{keyword_relevance}점")
                        elif semantic_similarity is not None:
                            st.metric("의미 유사성", f"{semantic_similarity:.2f}")
                        else:
                            st.metric("추가 메트릭", "N/A")
                
                # 향상된 점수 정보 표시
                if any([relevance_score, keyword_relevance, semantic_similarity]):
                    with st.expander("상세 점수 분석"):
                        if relevance_score is not None:
                            st.write(f"**LLM 관련성 점수**: {relevance_score}점 (70점 이상 통과)")
                            validation_reason = doc.get('validation_reason', '검증됨')
                            st.write(f"**검증 사유**: {validation_reason}")
                        
                        if keyword_relevance is not None:
                            st.write(f"**키워드 관련성 점수**: {keyword_relevance}점 (30점 이상 관련)")
                        
                        if semantic_similarity is not None:
                            st.write(f"**의미적 유사성**: {semantic_similarity:.2f} (0.3 이상 유사)")
            else:
                # 일반 모드에서는 간단한 제목만 표시
                st.markdown(f"### {tier_emoji} **문서 {i+1}**{time_info}")
            
            # 주요 정보 표시 - 시간 정보 포함
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**장애 ID**: {doc['incident_id']}")
                st.write(f"**서비스명**: {doc['service_name']}")
                st.write(f"**발생일자**: {doc['error_date']}")
                if daynight:  # 시간대 정보가 있는 경우에만 표시
                    st.write(f"**발생시간대**: {daynight}")
                if week:  # 요일 정보가 있는 경우에만 표시
                    st.write(f"**발생요일**: {week}")
                st.write(f"**장애시간**: {doc['error_time']}분")
                st.write(f"**영향도**: {doc['effect']}")

            with col2:
                st.write(f"**현상**: {doc['symptom']}")
                st.write(f"**장애등급**: {doc['incident_grade']}")
                st.write(f"**장애원인**: {doc['root_cause']}")
                st.write(f"**원인유형**: {doc['cause_type']}")
                st.write(f"**처리유형**: {doc['done_type']}")
                st.write(f"**담당부서**: {doc['owner_depart']}")
            
            # 상세 정보 표시 (축약된 형태)
            if doc['root_cause']:
                st.write(f"**장애원인**: {doc['root_cause'][:200]}...")
            if doc['incident_repair']:
                st.write(f"**복구방법**: {doc['incident_repair'][:200]}...")
            if doc['repair_notice']:
                st.write(f"**복구공지**: {doc['repair_notice'][:200]}...")
            
            st.markdown("---")
    
    def display_processing_mode_info(self, query_type, processing_mode):
        """처리 모드 정보 표시 (디버그 모드에서만)"""
        if not self.debug_mode:
            return
            
        mode_info = {
            'accuracy_first': {
                'name': '정확성 우선',
                'color': '#ff6b6b',
                'icon': '🎯',
                'description': 'LLM 관련성 검증을 통한 최고 정확도 제공'
            },
            'coverage_first': {
                'name': '포괄성 우선',
                'color': '#4ecdc4',
                'icon': '📋',
                'description': '의미적 유사성 기반 광범위한 검색 결과 제공'
            },
            'balanced': {
                'name': '균형 처리',
                'color': '#45b7d1',
                'icon': '⚖️',
                'description': '정확성과 포괄성의 최적 균형'
            }
        }
        
        info = mode_info.get(processing_mode, mode_info['balanced'])
        
        st.markdown(f"""
        <div style="
            background-color: {info['color']}15;
            border-left: 4px solid {info['color']};
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
        ">
            <strong>{info['icon']} {info['name']} ({query_type.upper()})</strong><br>
            <small>{info['description']}</small>
        </div>
        """, unsafe_allow_html=True)
    
    def display_performance_metrics(self, metrics):
        """성능 메트릭 표시 (디버그 모드에서만)"""
        if not metrics or not self.debug_mode:
            return
        
        with st.expander("처리 성능 메트릭"):
            cols = st.columns(len(metrics))
            for i, (metric_name, value) in enumerate(metrics.items()):
                with cols[i]:
                    st.metric(metric_name.replace('_', ' ').title(), value)
    
    def show_query_optimization_tips(self, query_type):
        """쿼리 타입별 최적화 팁 표시 - 시간 관련 팁 추가 (선택적 표시)"""
        tips = {
            'repair': [
                "서비스명과 장애현상을 모두 포함하세요",
                "구체적인 오류 증상을 명시하세요",
                "'복구방법', '해결방법' 키워드를 포함하세요",
                "시간대나 요일을 명시하면 더 정확한 결과를 얻을 수 있습니다"
            ],
            'cause': [
                "장애 현상을 구체적으로 설명하세요",
                "'원인', '이유', '왜' 등의 키워드를 포함하세요",
                "발생 시점이나 조건을 명시하세요",
                "시간대(주간/야간)나 요일을 지정하면 더 정확한 분석이 가능합니다"
            ],
            'similar': [
                "핵심 장애 현상만 간결하게 기술하세요",
                "'유사', '비슷한', '동일한' 키워드를 포함하세요",
                "서비스명이 불확실할 때 유용합니다",
                "특정 시간대나 요일에 발생한 유사 사례도 검색 가능합니다"
            ],
            'default': [
                "통계나 현황 조회 시 기간을 명시하세요",
                "구체적인 서비스명이나 조건을 포함하세요",
                "'건수', '통계', '현황' 등의 키워드를 활용하세요",
                "시간대별(주간/야간) 또는 요일별 집계도 가능합니다"
            ]
        }
        
        query_tips = tips.get(query_type, tips['default'])
        
        # 선택적으로만 표시 (사용자가 확장해서 볼 수 있도록)
        with st.expander(f"{query_type.upper()} 쿼리 최적화 팁"):
            for tip in query_tips:
                st.write(f"• {tip}")
            
            # 시간 관련 예시 추가
            st.write("\n**시간 관련 질문 예시:**")
            time_examples = [
                "야간에 발생한 ERP 장애 현황",
                "월요일에 발생한 API 오류 몇건?",
                "주간에 발생한 보험가입 실패 복구방법",
                "주말 SMS 발송 장애 원인 분석"
            ]
            for example in time_examples:
                st.write(f"  - {example}")
    
    def display_time_filter_info(self, time_conditions):
        """시간 조건 필터링 정보 표시 (디버그 모드에서만)"""
        if not time_conditions or not time_conditions.get('is_time_query') or not self.debug_mode:
            return
        
        time_desc = []
        if time_conditions.get('daynight'):
            time_emoji = "🌞" if time_conditions['daynight'] == "주간" else "🌙"
            time_desc.append(f"{time_emoji} 시간대: {time_conditions['daynight']}")
        
        if time_conditions.get('week'):
            week_emoji = "📅"
            week_desc = f"{time_conditions['week']}"
            if time_conditions['week'] not in ['평일', '주말']:
                week_desc += "요일"
            time_desc.append(f"{week_emoji} {week_desc}")
        
        if time_desc:
            st.info(f"⏰ 시간 조건 필터링 적용: {', '.join(time_desc)}")
    
    def display_validation_results(self, validation_result):
        """쿼리 처리 검증 결과 표시 (디버그 모드에서만)"""
        if not validation_result or not self.debug_mode:
            return
        
        if not validation_result['is_valid']:
            st.warning("처리 결과에 주의사항이 있습니다.")
        
        if validation_result['warnings']:
            with st.expander("경고사항"):
                for warning in validation_result['warnings']:
                    st.warning(warning)
        
        if validation_result['recommendations']:
            with st.expander("개선 권장사항"):
                for recommendation in validation_result['recommendations']:
                    st.info(recommendation)
    
    def show_time_statistics(self, documents):
        """시간대/요일별 통계 정보 표시 (선택적)"""
        if not documents:
            return
        
        # 시간대별 통계
        daynight_stats = {}
        week_stats = {}
        
        for doc in documents:
            daynight = doc.get('daynight', '')
            week = doc.get('week', '')
            
            if daynight:
                daynight_stats[daynight] = daynight_stats.get(daynight, 0) + 1
            
            if week:
                week_stats[week] = week_stats.get(week, 0) + 1
        
        if daynight_stats or week_stats:
            with st.expander("시간별 통계 정보"):
                col1, col2 = st.columns(2)
                
                with col1:
                    if daynight_stats:
                        st.write("**시간대별 분포:**")
                        for time_period, count in sorted(daynight_stats.items()):
                            time_emoji = "🌞" if time_period == "주간" else "🌙"
                            st.write(f"  {time_emoji} {time_period}: {count}건")
                
                with col2:
                    if week_stats:
                        st.write("**요일별 분포:**")
                        # 요일 순서 정의
                        week_order = ['월', '화', '수', '목', '금', '토', '일', '평일', '주말']
                        sorted_weeks = sorted(week_stats.items(), 
                                            key=lambda x: week_order.index(x[0]) if x[0] in week_order else 999)
                        
                        for week_day, count in sorted_weeks:
                            week_desc = f"{week_day}요일" if week_day not in ['평일', '주말'] else week_day
                            st.write(f"  📅 {week_desc}: {count}건")
    
    def show_department_statistics(self, documents):
        """부서별 통계 정보 표시 (선택적)"""
        if not documents:
            return
        
        # 부서별 통계
        department_stats = {}
        
        for doc in documents:
            owner_depart = doc.get('owner_depart', '')
            
            if owner_depart:
                department_stats[owner_depart] = department_stats.get(owner_depart, 0) + 1
        
        if department_stats:
            with st.expander("부서별 통계 정보"):
                st.write("**담당부서별 분포:**")
                # 건수별로 내림차순 정렬
                sorted_departments = sorted(department_stats.items(), 
                                          key=lambda x: x[1], reverse=True)
                
                for department, count in sorted_departments:
                    st.write(f"  🏢 {department}: {count}건")
    
    def show_comprehensive_statistics(self, documents):
        """시간대/요일/부서별 종합 통계 정보 표시 (선택적)"""
        if not documents:
            return
        
        # 모든 통계 정보 수집
        daynight_stats = {}
        week_stats = {}
        department_stats = {}
        
        for doc in documents:
            daynight = doc.get('daynight', '')
            week = doc.get('week', '')
            owner_depart = doc.get('owner_depart', '')
            
            if daynight:
                daynight_stats[daynight] = daynight_stats.get(daynight, 0) + 1
            
            if week:
                week_stats[week] = week_stats.get(week, 0) + 1
            
            if owner_depart:
                department_stats[owner_depart] = department_stats.get(owner_depart, 0) + 1
        
        # 통계 정보가 있는 경우에만 표시
        if daynight_stats or week_stats or department_stats:
            with st.expander("종합 통계 정보"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if daynight_stats:
                        st.write("**시간대별 분포:**")
                        for time_period, count in sorted(daynight_stats.items()):
                            time_emoji = "🌞" if time_period == "주간" else "🌙"
                            st.write(f"  {time_emoji} {time_period}: {count}건")
                
                with col2:
                    if week_stats:
                        st.write("**요일별 분포:**")
                        # 요일 순서 정의
                        week_order = ['월', '화', '수', '목', '금', '토', '일', '평일', '주말']
                        sorted_weeks = sorted(week_stats.items(), 
                                            key=lambda x: week_order.index(x[0]) if x[0] in week_order else 999)
                        
                        for week_day, count in sorted_weeks:
                            week_desc = f"{week_day}요일" if week_day not in ['평일', '주말'] else week_day
                            st.write(f"  📅 {week_desc}: {count}건")
                
                with col3:
                    if department_stats:
                        st.write("**담당부서별 분포:**")
                        # 상위 5개 부서만 표시
                        sorted_departments = sorted(department_stats.items(), 
                                                  key=lambda x: x[1], reverse=True)[:5]
                        
                        for department, count in sorted_departments:
                            st.write(f"  🏢 {department}: {count}건")