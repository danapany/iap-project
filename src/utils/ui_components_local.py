import streamlit as st

class UIComponentsLocal:
    """UI 컴포넌트 관리 클래스"""
    
    def __init__(self):
        self.debug_mode = False
    
    def convert_cause_box_to_html(self, text):
        """장애원인 마커를 HTML로 변환"""
        if '[CAUSE_BOX_START]' not in text or '[CAUSE_BOX_END]' not in text:
            return text, False
        
        start_marker = '[CAUSE_BOX_START]'
        end_marker = '[CAUSE_BOX_END]'
        
        start_idx = text.find(start_marker)
        end_idx = text.find(end_marker)
        
        if start_idx == -1 or end_idx == -1:
            return text, False
        
        cause_content = text[start_idx + len(start_marker):end_idx].strip()
        
        import re
        cause_pattern = r'원인(\d+):\s*([^\n원]*(?:\n(?!원인\d+:)[^\n]*)*)'
        matches = re.findall(cause_pattern, cause_content, re.MULTILINE)
        
        formatted_causes = []
        
        if matches:
            for i, (num, content) in enumerate(matches[:3]):
                clean_content = content.strip()
                if clean_content:
                    clean_content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', clean_content)
                    formatted_causes.append(
                        f'<li style="margin-bottom: 8px; line-height: 1.5;"><strong>원인{num}:</strong> {clean_content}</li>'
                    )
        else:
            lines = [line.strip() for line in cause_content.split('\n') if line.strip()]
            
            bullet_lines = []
            for line in lines:
                if line.startswith('•') or line.startswith('-') or line.startswith('*'):
                    content = line[1:].strip()
                    if content:
                        bullet_lines.append(content)
                elif line:
                    bullet_lines.append(line)
                
                if len(bullet_lines) >= 3:
                    break
            
            if not bullet_lines:
                bullet_lines = [cause_content]
            
            for i, content in enumerate(bullet_lines[:3]):
                content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
                formatted_causes.append(
                    f'<li style="margin-bottom: 8px; line-height: 1.5;"><strong>원인{i+1}:</strong> {content}</li>'
                )
        
        cause_html = f'<ul style="margin: 0; padding-left: 20px; list-style-type: none;">{"".join(formatted_causes)}</ul>'
        
        html_box = f"""
<div style="background: #e8f5e8; border: 1px solid #10b981; border-radius: 8px; padding: 15px; margin: 15px 0; display: flex; align-items: flex-start; gap: 12px;">
    <div style="background: #10b981; border-radius: 50%; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; color: white; font-size: 16px; flex-shrink: 0; margin-top: 2px;">📋</div>
    <div style="flex: 1;">
        <h4 style="color: #065f46; margin: 0 0 8px 0; font-size: 16px; font-weight: bold;">장애원인</h4>
        <div style="color: #065f46; line-height: 1.5; font-size: 14px;">
            {cause_html}
        </div>
    </div>
</div>
"""
        
        result = text[:start_idx] + html_box + text[end_idx + len(end_marker):]
        return result, True

    def convert_repair_box_to_html(self, text):
        """복구방법 마커를 HTML로 변환"""
        if '[REPAIR_BOX_START]' not in text or '[REPAIR_BOX_END]' not in text:
            return text, False
        
        start_marker = '[REPAIR_BOX_START]'
        end_marker = '[REPAIR_BOX_END]'
        
        start_idx = text.find(start_marker)
        end_idx = text.find(end_marker)
        
        if start_idx == -1 or end_idx == -1:
            return text, False
        
        repair_content = text[start_idx + len(start_marker):end_idx].strip()
        repair_content = repair_content.replace('**', '<strong>').replace('**', '</strong>')
        
        html_box = f"""
<div style="background: #e8f5e8; border: 1px solid #10b981; border-radius: 8px; padding: 15px; margin: 15px 0; display: flex; align-items: flex-start; gap: 12px;">
    <div style="background: #10b981; border-radius: 50%; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; color: white; font-size: 16px; flex-shrink: 0; margin-top: 2px;">🤖</div>
    <div style="flex: 1;">
        <h4 style="color: #065f46; margin: 0 0 8px 0; font-size: 16px; font-weight: bold;">복구방법 (incident_repair 기준)</h4>
        <div style="color: #065f46; line-height: 1.5; font-size: 14px;">
            {repair_content}
        </div>
    </div>
</div>
"""
        
        result = text[:start_idx] + html_box + text[end_idx + len(end_marker):]
        return result, True
    
    def render_main_ui(self):
        """메인 UI 렌더링 - 좌측정렬로 수정"""
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
                margin: 20px 0; /* 좌측 정렬을 위해 margin: auto 제거 */
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
                text-align: center; /* 중앙정렬에서 좌측정렬로 변경 */
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
                text-align: left; /* 중앙정렬에서 좌측정렬로 변경 */
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
            
            @media (max-width: 1024px) {
                .web-search-container {
                    max-width: 950px;
                }
                
                .web-journey-path {
                    gap: 25px;
                }
                
                .web-step-circle {
                    width: 70px;
                    height: 70px;
                    font-size: 24px;
                }
                
                .web-path-line {
                    width: 20px;
                }
            }
            
            @media (max-width: 768px) {
                .web-journey-path {
                    flex-direction: column;
                    gap: 30px;
                    align-items: flex-start; /* 모바일에서도 좌측정렬 */
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
            <div class="search-icon search1">🤔</div>
            <div class="search-icon search2">🎯</div>
            <div class="search-icon search3">💡</div>
            <div class="web-decoration web-deco1">✦</div>
            <div class="web-decoration web-deco2">✧</div>
            <div class="web-decoration web-deco3">✦</div>
            <div class="title">AI를 활용하여 신속한 장애복구에 활용해보세요!</div>
            <div class="web-journey-path">
                <div class="web-step-circle">
                    🤔
                    <div class="web-step-label"><b>복구방법</b></div>
                </div>
                <div class="web-path-line"></div>
                <div class="web-step-circle">
                    🎯
                    <div class="web-step-label"><b>장애원인</b></div>
                </div>
                <div class="web-path-line"></div>
                <div class="web-step-circle">
                    💡
                    <div class="web-step-label"><b>장애현상</b></div>
                </div>
                <div class="web-path-line"></div>
                <div class="web-step-circle">
                    ⚖️
                    <div class="web-step-label"><b>이력조회</b></div>
                </div>
            </div>
        </div>
        <div style="text-align: left;"> <!-- 질문예시 부분도 좌측정렬 -->
        <h4>💬 질문예시</h4>
        <h6>* 복구방법 : 마이페이지 보험가입불가 현상 복구방법 알려줘<br>
        * 장애원인 : ERP EP업무 처리시 간헐적 접속불가현상에 대한 장애원인이 뭐야?<br>
        * 유사사례 : 문자발송 실패 현상에 대한 조치방법 알려줘<br>
        * 장애이력 : 블록체인기반지역화폐 야간에 발생한 장애내역 알려줘<br>
        * 장애건수 : 2025년 ERP 장애가 몇건이야?<br>
        * 차트분석 : ERP 년도별 장애건수 차트로 그려줘    ※ 제공가능: 가로/세로 막대차트, 선 차트, 파이 차트<p>

        <font color="red"> ※ 서비스명을 정확히 입력하시고 같이 검색하시면 보다 더 정확한 답변을 얻을 수 있습니다<br>
        ※ 대량조회가 안되도록 임계치 설정 및 일부 인시던트는 학습데이터에서 제외되어 통계성 질문은 일부 부정확 할 수있다는 점 양해 부탁드립니다.<br>
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
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    if message["role"] == "assistant":
                        content = message["content"]
                        
                        converted_content = content
                        html_converted = False
                        
                        if '[REPAIR_BOX_START]' in converted_content and '[REPAIR_BOX_END]' in converted_content:
                            converted_content, has_repair_html = self.convert_repair_box_to_html(converted_content)
                            if has_repair_html:
                                html_converted = True
                        
                        if '[CAUSE_BOX_START]' in converted_content and '[CAUSE_BOX_END]' in converted_content:
                            converted_content, has_cause_html = self.convert_cause_box_to_html(converted_content)
                            if has_cause_html:
                                html_converted = True
                        
                        if html_converted or ('<div style=' in content and ('장애원인' in content or '복구방법' in content)):
                            st.markdown(converted_content, unsafe_allow_html=True)
                        else:
                            st.write(converted_content)
                    else:
                        st.write(message["content"])
    
    # 나머지 메서드들은 기존 코드와 동일하므로 생략...
    
    def display_documents_with_quality_info(self, documents):
        """품질 정보와 처리 방식 정보를 포함한 문서 표시"""
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
            
            daynight = doc.get('daynight', '')
            week = doc.get('week', '')
            
            if quality_tier == 'Premium':
                tier_emoji = "🆔"
                tier_color = "🟢"
            elif quality_tier == 'Standard':
                tier_emoji = "🎯"
                tier_color = "🟡"
            else:
                tier_emoji = "📋"
                tier_color = "🔵"
            
            match_emoji = {"exact": "🎯", "partial": "🔍", "all": "📋", "fallback": "🔄"}.get(service_match_type, "❓")
            match_label = {
                "exact": "정확 매칭", 
                "partial": "포함 매칭", 
                "all": "전체", 
                "fallback": "대체 검색",
                "unknown": "알 수 없음"
            }.get(service_match_type, "알 수 없음")
            
            time_info = ""
            if daynight:
                time_emoji = "🌞" if daynight == "주간" else "🌙"
                time_info += f" {time_emoji} {daynight}"
            if week:
                time_info += f" 📅 {week}요일" if week not in ['평일', '주말'] else f" 📅 {week}"
            
            if self.debug_mode:
                st.markdown(f"### {tier_emoji} **문서 {i+1}** - {quality_tier}급 {tier_color} {match_emoji} {match_label}{time_info}")
                st.markdown(f"**선별 기준**: {filter_reason}")
                
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
                st.markdown(f"### {tier_emoji} **문서 {i+1}**{time_info}")
            
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**장애 ID**: {doc['incident_id']}")
                st.write(f"**서비스명**: {doc['service_name']}")
                st.write(f"**발생일자**: {doc['error_date']}")
                if daynight:
                    st.write(f"**발생시간대**: {daynight}")
                if week:
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
            
            incident_repair = doc.get('incident_repair', '').strip()
            incident_plan = doc.get('incident_plan', '').strip()
            
            if incident_repair:
                st.write("**복구방법 (incident_repair)**:")
                if incident_plan and incident_plan in incident_repair:
                    clean_repair = incident_repair.replace(incident_plan, '').strip()
                    if clean_repair:
                        st.write(f"  {clean_repair[:300]}...")
                    else:
                        st.write(f"  {incident_repair[:300]}...")
                else:
                    st.write(f"  {incident_repair[:300]}...")
            
            if incident_plan:
                st.write("**개선계획 (incident_plan) - 참고용**:")
                st.write(f"  {incident_plan[:300]}...")
            
            if doc.get('repair_notice'):
                st.write(f"**복구공지**: {doc['repair_notice'][:200]}...")
            
            st.markdown("---")
    
    def display_processing_mode_info(self, query_type, processing_mode):
        """처리 모드 정보 표시"""
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
        """성능 메트릭 표시"""
        if not metrics or not self.debug_mode:
            return
        
        with st.expander("처리 성능 메트릭"):
            cols = st.columns(len(metrics))
            for i, (metric_name, value) in enumerate(metrics.items()):
                with cols[i]:
                    st.metric(metric_name.replace('_', ' ').title(), value)
    
    def show_query_optimization_tips(self, query_type):
        """쿼리 타입별 최적화 팁 표시"""
        tips = {
            'repair': [
                "서비스명과 장애현상을 모두 포함하세요",
                "구체적인 오류 증상을 명시하세요",
                "'복구방법', '해결방법' 키워드를 포함하세요",
                "시간대나 요일을 명시하면 더 정확한 결과를 얻을 수 있습니다",
                "※ 복구방법은 incident_repair 필드 기준으로만 제공됩니다"
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
                "시간대별(주간/야간) 또는 요일별 집계도 가능합니다",
                "통계성 질문 시 자동으로 차트가 생성됩니다"
            ]
        }
        
        query_tips = tips.get(query_type, tips['default'])
        
        with st.expander(f"{query_type.upper()} 쿼리 최적화 팁"):
            for tip in query_tips:
                st.write(f"• {tip}")
            
            st.write("\n**시간 관련 질문 예시:**")
            time_examples = [
                "야간에 발생한 ERP 장애 현황",
                "월요일에 발생한 API 오류 몇건?",
                "주간에 발생한 보험가입 실패 복구방법",
                "주말 SMS 발송 장애 원인 분석"
            ]
            for example in time_examples:
                st.write(f"  - {example}")
            
            if query_type == 'default':
                st.write("\n**📊 자동 차트 생성 예시:**")
                chart_examples = [
                    "2024년 연도별 장애 통계 → 연도별 선 그래프",
                    "부서별 장애 처리 현황 → 부서별 가로 막대 그래프", 
                    "시간대별 장애 발생 분포 → 시간대별 세로 막대 그래프",
                    "장애등급별 발생 비율 → 등급별 원형 그래프",
                    "월별 장애 발생 추이 → 월별 선 그래프"
                ]
                for example in chart_examples:
                    st.write(f"  - {example}")
            
            if query_type == 'repair':
                st.write("\n**복구방법 관련 중요 안내:**")
                st.write("• 복구방법은 incident_repair 필드 데이터만 사용됩니다")
                st.write("• 개선계획(incident_plan)은 별도 참고용으로 제공됩니다")
                st.write("• 두 정보는 명확히 구분되어 표시됩니다")
    
    def display_time_filter_info(self, time_conditions):
        """시간 조건 필터링 정보 표시"""
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
        """쿼리 처리 검증 결과 표시"""
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
        """시간대/요일별 통계 정보 표시"""
        if not documents:
            return
        
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
                        week_order = ['월', '화', '수', '목', '금', '토', '일', '평일', '주말']
                        sorted_weeks = sorted(week_stats.items(), 
                                            key=lambda x: week_order.index(x[0]) if x[0] in week_order else 999)
                        
                        for week_day, count in sorted_weeks:
                            week_desc = f"{week_day}요일" if week_day not in ['평일', '주말'] else week_day
                            st.write(f"  📅 {week_desc}: {count}건")
    
    def show_department_statistics(self, documents):
        """부서별 통계 정보 표시"""
        if not documents:
            return
        
        department_stats = {}
        
        for doc in documents:
            owner_depart = doc.get('owner_depart', '')
            
            if owner_depart:
                department_stats[owner_depart] = department_stats.get(owner_depart, 0) + 1
        
        if department_stats:
            with st.expander("부서별 통계 정보"):
                st.write("**담당부서별 분포:**")
                sorted_departments = sorted(department_stats.items(), 
                                          key=lambda x: x[1], reverse=True)
                
                for department, count in sorted_departments:
                    st.write(f"  🏢 {department}: {count}건")
    
    def show_comprehensive_statistics(self, documents):
        """시간대/요일/부서별 종합 통계 정보 표시"""
        if not documents:
            return
        
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
                        week_order = ['월', '화', '수', '목', '금', '토', '일', '평일', '주말']
                        sorted_weeks = sorted(week_stats.items(), 
                                            key=lambda x: week_order.index(x[0]) if x[0] in week_order else 999)
                        
                        for week_day, count in sorted_weeks:
                            week_desc = f"{week_day}요일" if week_day not in ['평일', '주말'] else week_day
                            st.write(f"  📅 {week_desc}: {count}건")
                
                with col3:
                    if department_stats:
                        st.write("**담당부서별 분포:**")
                        sorted_departments = sorted(department_stats.items(), 
                                                  key=lambda x: x[1], reverse=True)[:5]
                        
                        for department, count in sorted_departments:
                            st.write(f"  🏢 {department}: {count}건")
    
    def show_repair_plan_distinction_info(self):
        """복구방법과 개선계획 구분 안내 정보"""
        with st.expander("📋 복구방법과 개선계획 구분 안내"):
            st.markdown("""
            **🔧 복구방법 (incident_repair):**
            - 장애 발생 시 즉시 적용할 수 있는 구체적인 조치 방법
            - 시스템을 정상 상태로 복원하기 위한 단계별 절차
            - 복구방법 질문에 대한 핵심 답변으로 제공
            
            **📈 개선계획 (incident_plan):**
            - 유사한 장애의 재발 방지를 위한 장기적 개선 방안
            - 시스템 또는 프로세스 개선을 위한 계획
            - 참고용으로만 별도 제공
            
            **💡 구분 이유:**
            - 복구방법 질문 시 즉시 필요한 정보만 명확히 제공
            - 장기적 개선사항과 즉시 복구 조치를 혼동하지 않도록 구분
            - 사용자가 상황에 맞는 적절한 정보를 선택적으로 활용 가능
            
            **🎯 사용 방법:**
            - 긴급 상황: incident_repair 필드의 복구방법을 우선 참고
            - 장기적 개선: incident_plan 필드의 개선계획을 추가 검토
            """)
    
    def show_chart_feature_info(self):
        """차트 기능 안내 정보"""
        with st.expander("📊 차트 시각화 기능 안내"):
            st.markdown("""
            **🚀 자동 차트 생성:**
            - 통계성 질문 시 자동으로 적절한 차트를 생성합니다
            - 텍스트 답변과 함께 시각적 분석을 제공합니다
            
            **📈 지원되는 차트 타입:**
            - **연도별/월별**: 선 그래프로 시간 추이 표시
            - **시간대별/요일별**: 막대 그래프로 분포 표시  
            - **부서별/서비스별**: 가로 막대 그래프로 순위 표시
            - **장애등급별**: 원형 그래프로 비율 표시
            - **원인유형별**: 가로 막대 그래프로 분포 표시
            
            **💡 차트 생성 조건:**
            - 통계 관련 키워드 포함 (건수, 통계, 현황, 분포 등)
            - 분류 관련 키워드 포함 (년도별, 부서별, 서비스별 등)
            - 검색 결과가 2개 이상인 경우
            
            **📋 제공되는 추가 정보:**
            - 상세 데이터 테이블
            - 요약 통계 (총 건수, 평균, 최다 발생)
            - 백분율 정보
            
            **🎯 차트 생성 예시 질문:**
            - "2024년 연도별 장애 통계"
            - "부서별 장애 처리 현황"
            - "시간대별 장애 발생 분포"
            - "서비스별 장애 건수"
            - "장애등급별 발생 비율"
            """)