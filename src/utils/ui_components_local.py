import streamlit as st
import re

class UIComponentsLocal:
    """UI 컴포넌트 관리 클래스"""
    
    def __init__(self):
        self.debug_mode = False
        # ChartManager 초기화 추가
        self.chart_manager = None
        try:
            from utils.chart_utils import ChartManager
            self.chart_manager = ChartManager()
            print("ChartManager 초기화 성공")
        except ImportError as e:
            print(f"ChartManager import 실패: {e}")
        except Exception as e:
            print(f"ChartManager 초기화 실패: {e}")

    def _parse_cause_content(self, cause_content):
        """원인 컨텐츠 파싱"""
        cause_pattern = r'원인(\d+):\s*([^\n원]*(?:\n(?!원인\d+:)[^\n]*)*)'
        matches = re.findall(cause_pattern, cause_content, re.MULTILINE)
        
        if matches:
            return [(num, re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content.strip()))
                    for num, content in matches[:3] if content.strip()]
        
        lines = [line.strip() for line in cause_content.split('\n') if line.strip()]
        bullet_lines = [line[1:].strip() if line.startswith(('•', '-', '*')) else line 
                       for line in lines if line][:3]
        
        return [(str(i+1), re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content))
                for i, content in enumerate(bullet_lines or [cause_content])]
    
    def _create_info_box(self, content, title, emoji, icon):
        """정보 박스 HTML 생성"""
        return f"""<div style="background:#e8f5e8;border:1px solid #10b981;border-radius:8px;padding:15px;margin:15px 0;display:flex;align-items:flex-start;gap:12px;">
<div style="background:#10b981;border-radius:50%;width:32px;height:32px;display:flex;align-items:center;justify-content:center;color:white;font-size:16px;flex-shrink:0;margin-top:2px;">{icon}</div>
<div style="flex:1;"><h4 style="color:#065f46;margin:0 0 8px 0;font-size:16px;font-weight:bold;">{title}</h4>
<div style="color:#065f46;line-height:1.5;font-size:14px;">{content}</div></div></div>"""
    
    def convert_cause_box_to_html(self, text):
        """장애원인 마커를 HTML로 변환"""
        return self._convert_box_to_html(text, 'CAUSE_BOX', '장애원인', '📋', True)
    
    def convert_repair_box_to_html(self, text):
        """복구방법 마커를 HTML로 변환"""
        return self._convert_box_to_html(text, 'REPAIR_BOX', '복구방법 (incident_repair 기준)', '🤖', False)
    
    def _convert_box_to_html(self, text, box_type, title, icon, parse_causes):
        """박스 마커를 HTML로 변환하는 공통 로직"""
        start_marker, end_marker = f'[{box_type}_START]', f'[{box_type}_END]'
        if start_marker not in text or end_marker not in text: 
            return text, False
        
        start_idx, end_idx = text.find(start_marker), text.find(end_marker)
        if start_idx == -1 or end_idx == -1: 
            return text, False
        
        content = text[start_idx + len(start_marker):end_idx].strip()
        
        if parse_causes:
            parsed = self._parse_cause_content(content)
            formatted = ''.join([f'<li style="margin-bottom:8px;line-height:1.5;"><strong>원인{num}:</strong> {c}</li>' 
                               for num, c in parsed])
            content = f'<ul style="margin:0;padding-left:20px;list-style-type:none;">{formatted}</ul>'
        else:
            content = content.replace('**', '<strong>').replace('**', '</strong>')
        
        html_box = self._create_info_box(content, title, '', icon)
        return text[:start_idx] + html_box + text[end_idx + len(end_marker):], True
    
    def _remove_patterns(self, text, patterns):
        """패턴 목록을 사용한 텍스트 제거"""
        for pattern in patterns:
            old_text = text
            text = re.sub(pattern, '', text, flags=re.DOTALL | re.IGNORECASE)
            if old_text != text and self.debug_mode:
                print(f"UI_DEBUG: 패턴 제거됨: {pattern}")
        return text

    def _remove_box_markers_enhanced(self, text):
        """강화된 박스 마커 제거"""
        patterns = [
            r'\[REPAIR_BOX_START\].*?\[REPAIR_BOX_END\]', r'\[CAUSE_BOX_START\].*?\[CAUSE_BOX_END\]',
            r'\[.*?_BOX_START\].*?\[.*?_BOX_END\]', r'\[REPAIR_BOX_START\].*', r'.*\[REPAIR_BOX_END\]',
            r'\[CAUSE_BOX_START\].*', r'.*\[CAUSE_BOX_END\]'
        ]
        return self._remove_patterns(text, patterns)

    def _remove_html_boxes_enhanced(self, text):
        """HTML 형태의 모든 박스 제거"""
        patterns = [
            r'<div style="background:#e8f5e8;.*?</div>', r'<div[^>]*>.*?복구방법.*?</div>',
            r'<div[^>]*>.*?장애원인.*?</div>', r'<div[^>]*>.*?🔧.*?</div>',
            r'<div[^>]*>.*?📋.*?</div>', r'<div[^>]*class=".*?repair.*?".*?</div>',
            r'<div[^>]*class=".*?cause.*?".*?</div>'
        ]
        return self._remove_patterns(text, patterns)

    def _remove_repair_text_sections(self, text):
        """복구방법 관련 텍스트 섹션 제거"""
        lines = text.split('\n')
        cleaned_lines = []
        skip_mode = False
        skip_keywords = ['복구방법', '복구절차', '조치방법', '해결방법', '대응방법', '복구', '조치', 
                        '해결', '대응', '수정', '개선', 'repair', 'recovery', 'solution', 'fix']
        
        for line in lines:
            line_stripped = line.strip()
            line_lower = line_stripped.lower()
            
            # 복구방법 섹션 시작 감지
            if any(keyword in line_lower for keyword in skip_keywords):
                if (line_stripped.startswith(('**', '#')) or line_stripped.endswith(':') or
                    '복구방법:' in line_lower or '조치방법:' in line_lower):
                    skip_mode = True
                    if self.debug_mode: print(f"UI_DEBUG: 복구방법 섹션 시작 감지: {line_stripped}")
                    continue
            
            # 새로운 섹션이나 표 시작되면 스킵 모드 해제
            if (line_stripped.startswith(('#', '##', 'Case', '|', '1.')) or 
                (line_stripped.startswith('**') and not any(kw in line_lower for kw in skip_keywords))):
                skip_mode = False
            
            if not skip_mode:
                cleaned_lines.append(line)
            elif self.debug_mode:
                print(f"UI_DEBUG: 라인 스킵됨: {line_stripped[:50]}...")
        
        return '\n'.join(cleaned_lines)

    def _clean_inquiry_response(self, text):
        """INQUIRY 응답 최종 정리"""
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        lines = [line for line in text.split('\n') 
                if line.strip() not in ['복구방법', '복구방법:', '**복구방법**', '**복구방법:**']]
        
        # 마지막 빈 줄들 제거
        while lines and not lines[-1].strip():
            lines.pop()
        
        result = '\n'.join(lines).strip()
        if self.debug_mode: print(f"UI_DEBUG: 최종 정리 완료. 결과 길이: {len(result)}")
        return result

    def _emergency_remove_green_boxes(self, text, query_type):
        """긴급 해결책 - INQUIRY 타입에서 모든 녹색박스 관련 요소 강제 제거"""
        if query_type.lower() != 'inquiry':
            return text
            
        # HTML div 태그 제거
        patterns = [
            r'<div[^>]*style[^>]*background[^>]*#e8f5e8[^>]*>.*?</div>',
            r'<div[^>]*style[^>]*녹색[^>]*>.*?</div>'
        ]
        text = self._remove_patterns(text, patterns)
        
        # 복구방법 관련 텍스트 섹션 제거
        lines = text.split('\n')
        filtered_lines = []
        skip_until_next_section = False
        
        for line in lines:
            line_clean = line.strip()
            
            if any(keyword in line_clean.lower() for keyword in ['복구방법', '조치방법', '해결방법']):
                if line_clean.endswith(':') or '**' in line_clean:
                    skip_until_next_section = True
                    if self.debug_mode: print(f"EMERGENCY: 복구방법 섹션 시작 - 스킵: {line_clean}")
                    continue
            
            if (line_clean.startswith(('1.', '2.', '3.', 'Case', '|')) or '장애 ID' in line_clean):
                skip_until_next_section = False
            
            if not skip_until_next_section:
                filtered_lines.append(line)
            elif self.debug_mode:
                print(f"EMERGENCY: 라인 스킵됨: {line_clean[:30]}...")
        
        result = '\n'.join(filtered_lines)
        result = re.sub(r'\[.*?BOX.*?\]', '', result, flags=re.IGNORECASE)
        result = re.sub(r'\n{3,}', '\n\n', result)
        
        if self.debug_mode: print(f"EMERGENCY: 최종 결과 길이: {len(result)}")
        return result.strip()
    
    def _remove_box_markers(self, text):
        """박스 마커들을 제거하는 헬퍼 메서드 - 강화된 버전으로 대체"""
        return self._remove_box_markers_enhanced(text)
    
    def display_response_with_query_type_awareness(self, response, query_type="default", chart_info=None):
        """쿼리 타입을 고려한 응답 표시 - statistics에서만 차트 표시"""
        if not response:
            st.write("응답이 없습니다.")
            return
        
        response_text, chart_info = response if isinstance(response, tuple) else (response, chart_info)
        if chart_info and chart_info.get('chart'):
            response_text = self.remove_text_charts_from_response(response_text)
        
        converted_content = response_text
        html_converted = False
        
        if self.debug_mode:
            print(f"UI_DEBUG: Query type: {query_type}")
            print(f"UI_DEBUG: Chart manager available: {self.chart_manager is not None}")
        
        # INQUIRY 타입인 경우 강화된 박스 제거
        if query_type.lower() == 'inquiry':
            if self.debug_mode: print("UI_DEBUG: INQUIRY 타입 감지 - 모든 박스 제거 시작")
            
            converted_content = self._remove_box_markers_enhanced(converted_content)
            converted_content = self._remove_html_boxes_enhanced(converted_content)
            converted_content = self._remove_repair_text_sections(converted_content)
            converted_content = self._clean_inquiry_response(converted_content)
            converted_content = self._emergency_remove_green_boxes(converted_content, query_type)
            
            if self.debug_mode:
                print(f"UI_DEBUG: 박스 제거 완료. 최종 길이: {len(converted_content)}")
        else:
            # INQUIRY가 아닌 경우에만 박스 변환 적용
            if '[REPAIR_BOX_START]' in converted_content:
                converted_content, has_html = self.convert_repair_box_to_html(converted_content)
                html_converted = html_converted or has_html
            if '[CAUSE_BOX_START]' in converted_content:
                converted_content, has_html = self.convert_cause_box_to_html(converted_content)
                html_converted = html_converted or has_html
        
        # 응답 표시
        if html_converted:
            st.markdown(converted_content, unsafe_allow_html=True)
        else:
            st.write(converted_content)
        
        # 차트 표시 - statistics 타입에서만 그리고 chart_manager가 있을 때만
        if (chart_info and chart_info.get('chart') and 
            query_type.lower() == 'statistics' and 
            self.chart_manager is not None):
            st.markdown("---")
            try:
                self.chart_manager.display_chart_with_data(
                    chart_info['chart'], chart_info['chart_data'], 
                    chart_info['chart_type'], chart_info.get('query', ''))
            except Exception as e:
                st.error(f"차트 표시 중 오류: {str(e)}")
        elif chart_info and chart_info.get('chart') and query_type.lower() == 'statistics':
            st.warning("차트 매니저가 초기화되지 않아 차트를 표시할 수 없습니다.")
        
        # INQUIRY 타입인 경우 엑셀 다운로드 버튼 표시
        if query_type.lower() == 'inquiry':
            if self.debug_mode: print("UI_DEBUG: INQUIRY 타입 - 엑셀 다운로드 버튼 표시 시도")
            try:
                from utils.excel_utils import ExcelDownloadManager
                excel_manager = ExcelDownloadManager()
                excel_manager.debug_mode = True
                excel_manager.display_download_button(converted_content, query_type)
            except Exception as e:
                if self.debug_mode:
                    print(f"UI_DEBUG: 엑셀 다운로드 기능 오류: {str(e)}")
    
    def render_main_ui(self):
        """메인 UI 렌더링"""
        html_code = """<style>
*{margin:0;padding:0;box-sizing:border-box;}
body{background:#f0f8ff;font-family:'Arial',sans-serif;padding:20px;}
.web-search-container{background:linear-gradient(180deg,#e6f3ff 0%,#b3d9ff 100%);padding:60px 40px;border-radius:25px;margin:20px 0;position:relative;min-height:350px;overflow:hidden;max-width:1000px;box-shadow:0 20px 60px rgba(30,144,255,0.2);}
.search-icon{position:absolute;color:rgba(30,144,255,0.6);font-size:20px;animation:float-search 6s ease-in-out infinite;}
.search1{top:20px;left:10%;animation-delay:0s;}.search2{top:30px;right:15%;animation-delay:-2s;}.search3{bottom:40px;left:20%;animation-delay:-4s;}
@keyframes float-search{0%,100%{transform:translateY(0px) rotate(0deg);opacity:0.6;}33%{transform:translateY(-10px) rotate(5deg);opacity:1;}66%{transform:translateY(5px) rotate(-3deg);opacity:0.8;}}
.title{text-align:center;color:#1e3a8a;font-size:24px;font-weight:500;margin-bottom:50px;font-family:'Arial',sans-serif;letter-spacing:1px;}
.web-journey-path{display:flex;align-items:center;justify-content:center;gap:40px;position:relative;flex-wrap:wrap;}
.web-step-circle{width:85px;height:85px;background:rgba(255,255,255,0.95);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:30px;box-shadow:0 10px 30px rgba(30,144,255,0.3);transition:all 0.4s ease;position:relative;animation:web-breathe 5s ease-in-out infinite;border:3px solid rgba(30,144,255,0.2);}
.web-step-circle:nth-child(1){animation-delay:0s;}.web-step-circle:nth-child(3){animation-delay:1s;}.web-step-circle:nth-child(5){animation-delay:2s;}.web-step-circle:nth-child(7){animation-delay:3s;}
@keyframes web-breathe{0%,100%{transform:scale(1);box-shadow:0 10px 30px rgba(30,144,255,0.3);}50%{transform:scale(1.08);box-shadow:0 15px 40px rgba(30,144,255,0.5);}}
.web-step-circle:hover{transform:scale(1.15) translateY(-8px);box-shadow:0 20px 50px rgba(30,144,255,0.6);}
.web-step-label{position:absolute;bottom:-40px;left:50%;transform:translateX(-50%);font-size:13px;color:#1e3a8a;white-space:nowrap;font-weight:400;letter-spacing:0.5px;}
.web-path-line{width:35px;height:3px;background:linear-gradient(90deg,#1e90ff,#4169e1);border-radius:2px;position:relative;animation:web-flow 4s ease-in-out infinite;}
@keyframes web-flow{0%,100%{opacity:0.7;transform:scaleX(1);}50%{opacity:1;transform:scaleX(1.1);}}
.web-path-line::before{content:'';position:absolute;right:-4px;top:-2px;width:0;height:0;border-left:5px solid #1e90ff;border-top:3px solid transparent;border-bottom:3px solid transparent;}
.web-subtitle{text-align:left;margin-top:70px;color:#4682b4;font-size:15px;font-weight:300;letter-spacing:1px;font-style:italic;}
.web-decoration{position:absolute;color:rgba(30,144,255,0.5);font-size:14px;animation:web-twinkle 4s ease-in-out infinite;}
@keyframes web-twinkle{0%,100%{opacity:0.3;transform:scale(0.9);}50%{opacity:1;transform:scale(1.3);}}
.web-deco1{top:50px;left:8%;animation-delay:0s;}.web-deco2{top:90px;right:10%;animation-delay:2s;}.web-deco3{bottom:60px;left:15%;animation-delay:4s;}
@media (max-width:1024px){.web-search-container{max-width:950px;}.web-journey-path{gap:25px;}.web-step-circle{width:70px;height:70px;font-size:24px;}.web-path-line{width:20px;}}
@media (max-width:768px){.web-journey-path{flex-direction:column;gap:30px;align-items:flex-start;}.web-path-line{width:3px;height:30px;transform:rotate(90deg);}.web-path-line::before{right:-2px;top:-4px;border-left:3px solid transparent;border-right:3px solid transparent;border-top:5px solid #1e90ff;}.web-search-container{padding:40px 20px;min-height:700px;margin:20px 0;}.title{font-size:20px;}.web-step-circle{width:75px;height:75px;font-size:26px;}}
</style>
<div class="web-search-container">
<div class="search-icon search1">🤔</div><div class="search-icon search2">🎯</div><div class="search-icon search3">💡</div>
<div class="web-decoration web-deco1">✦</div><div class="web-decoration web-deco2">✧</div><div class="web-decoration web-deco3">✦</div>
<div class="title">AI를 활용하여 신속한 장애복구에 활용해보세요!</div>
<div class="web-journey-path">
<div class="web-step-circle">🤔<div class="web-step-label"><b>복구방법</b></div></div>
<div class="web-path-line"></div>
<div class="web-step-circle">🎯<div class="web-step-label"><b>장애원인</b></div></div>
<div class="web-path-line"></div>
<div class="web-step-circle">💡<div class="web-step-label"><b>장애현상</b></div></div>
<div class="web-path-line"></div>
<div class="web-step-circle">⚖️<div class="web-step-label"><b>이력조회</b></div></div>
</div></div>
<div style="text-align:left;">
<h4>💬 질문예시</h4>
<h6>* 복구방법 : 마이페이지 보험가입불가 현상 복구방법 알려줘<br>
* 장애원인 : ERP EP업무 처리시 간헐적 접속불가현상에 대한 장애원인이 뭐야?<br>
* 유사사례 : 문자발송 실패 현상에 대한 조치방법 알려줘<br>
* 장애내역 : 블록체인기반지역화폐 야간에 발생한 장애내역 알려줘 &nbsp;&nbsp; <font color="blue">※ 내역조회는 엑셀다운로드 추가제공</font><br>
* 장애통계 : 년, 월, 서비스별, 원인유형별, 요일별, 주/야간 통계정보에 최적화 되어있습니다<br>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;- ERP 2025년 장애가 몇건이야? / 2025년 원인유형별 장애건수 알려줘 / 2025년 버그 원인으로 발생한 장애건수 알려줘<br>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;- 2등급 장애 년도별 건수 알려줘 / 2025년 요일별 건수 알려줘 / ERP 2025년 야간에 발생한 장애건수 알려줘<br>
* 차트분석 : ERP 연도별 장애건수 막대차트로 그려줘, 2025년 원인유형별 장애건수 파이차트로 그려줘 &nbsp;&nbsp;<font color="blue">※ 제공가능: 가로/세로 막대, 선, 파이 차트</font><br><br>
<font color="red">※ 서비스명을 정확히 입력하시고 같이 검색하시면 보다 더 정확한 답변을 얻을 수 있습니다<br>
※ 대량조회가 안되도록 임계치 설정 및 일부 인시던트는 학습데이터에서 제외되어 통계성 질문은 일부 부정확 할 수있다는 점 양해 부탁드립니다.<br>
</font></h6></div></div>"""
        st.markdown(html_code, unsafe_allow_html=True)
    
    def show_config_error(self, env_status):
        """설정 오류 표시"""
        st.error("환경변수 설정이 필요합니다.")
        st.info("""**설정해야 할 환경변수:**
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
```""")
        st.write("**환경변수 상태:**")
        for var, status in env_status.items():
            st.write(f"{status} {var}")
    
    def show_connection_error(self):
        """연결 오류 표시"""
        st.error("Azure 서비스 연결에 실패했습니다. 환경변수를 확인해주세요.")
        st.info("""**필요한 환경변수:**
- OPENAI_ENDPOINT: Azure OpenAI 엔드포인트
- OPENAI_KEY: Azure OpenAI API 키
- OPENAI_API_VERSION: API 버전 (기본값: 2024-02-01)
- CHAT_MODEL: 모델명 (기본값: iap-gpt-4o-mini)
- SEARCH_ENDPOINT: Azure AI Search 엔드포인트
- SEARCH_API_KEY: Azure AI Search API 키
- INDEX_REBUILD_NAME: 검색 인덱스명""")
    
    def display_chat_messages(self):
        """채팅 메시지 표시"""
        with st.container():
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    if message["role"] == "assistant":
                        content, html_converted = message["content"], False
                        
                        if '[REPAIR_BOX_START]' in content:
                            content, has_html = self.convert_repair_box_to_html(content)
                            html_converted = html_converted or has_html
                        
                        if '[CAUSE_BOX_START]' in content:
                            content, has_html = self.convert_cause_box_to_html(content)
                            html_converted = html_converted or has_html
                        
                        if html_converted or ('<div style=' in content and ('장애원인' in content or '복구방법' in content)):
                            st.markdown(content, unsafe_allow_html=True)
                        else: 
                            st.write(content)
                    else: 
                        st.write(message["content"])
    
    def display_documents_with_quality_info(self, documents):
        """품질 정보와 처리 방식 정보를 포함한 문서 표시"""
        tier_map = {'Premium': ('🏆', '🟢'), 'Standard': ('🎯', '🟡'), 'Basic': ('📋', '🔵')}
        match_map = {"exact": ("🎯", "정확 매칭"), "partial": ("🔍", "포함 매칭"), 
                     "all": ("📋", "전체"), "fallback": ("🔄", "대체 검색"), "unknown": ("❓", "알 수 없음")}
        
        for i, doc in enumerate(documents):
            tier = doc.get('quality_tier', 'Standard')
            tier_emoji, tier_color = tier_map.get(tier, tier_map['Standard'])
            match_type = doc.get('service_match_type', 'unknown')
            match_emoji, match_label = match_map.get(match_type, match_map['unknown'])
            
            time_info = ""
            if daynight := doc.get('daynight'):
                time_info += f" {'🌞' if daynight == '주간' else '🌙'} {daynight}"
            if week := doc.get('week'):
                time_info += f" 📅 {week}{'요일' if week not in ['평일', '주말'] else ''}"
            
            if self.debug_mode:
                st.markdown(f"### {tier_emoji} **문서 {i+1}** - {tier}급 {tier_color} {match_emoji} {match_label}{time_info}")
                st.markdown(f"**선별 기준**: {doc.get('filter_reason', '기본 선별')}")
                
                score_cols = st.columns(4 if any([doc.get('relevance_score'), doc.get('keyword_relevance_score'), 
                                                  doc.get('semantic_similarity')]) else 3)
                with score_cols[0]: 
                    st.metric("검색 점수", f"{doc.get('score', 0):.2f}")
                with score_cols[1]:
                    reranker = doc.get('reranker_score', 0)
                    st.metric("Reranker 점수", f"{reranker:.2f}" if reranker > 0 else "N/A")
                with score_cols[2]: 
                    st.metric("최종 점수", f"{doc.get('final_score', 0):.2f}")
                
                if len(score_cols) > 3:
                    with score_cols[3]:
                        if rel := doc.get('relevance_score'): 
                            st.metric("관련성 점수", f"{rel}점")
                        elif kw := doc.get('keyword_relevance_score'): 
                            st.metric("키워드 점수", f"{kw}점")
                        elif sem := doc.get('semantic_similarity'): 
                            st.metric("의미 유사성", f"{sem:.2f}")
                        else: 
                            st.metric("추가 메트릭", "N/A")
                
                if any([doc.get('relevance_score'), doc.get('keyword_relevance_score'), doc.get('semantic_similarity')]):
                    with st.expander("상세 점수 분석"):
                        if rel := doc.get('relevance_score'):
                            st.write(f"**LLM 관련성 점수**: {rel}점 (70점 이상 통과)")
                            st.write(f"**검증 사유**: {doc.get('validation_reason', '검증됨')}")
                        if kw := doc.get('keyword_relevance_score'):
                            st.write(f"**키워드 관련성 점수**: {kw}점 (30점 이상 관련)")
                        if sem := doc.get('semantic_similarity'):
                            st.write(f"**의미적 유사성**: {sem:.2f} (0.3 이상 유사)")
            else: 
                st.markdown(f"### {tier_emoji} **문서 {i+1}**{time_info}")
            
            col1, col2 = st.columns(2)
            with col1:
                for k, v in [('incident_id', '장애 ID'), ('service_name', '서비스명'), 
                            ('error_date', '발생일자'), ('error_time', '장애시간'), ('effect', '영향도')]:
                    if val := doc.get(k): 
                        st.write(f"**{v}**: {val}{'분' if k == 'error_time' else ''}")
                if daynight := doc.get('daynight'): 
                    st.write(f"**발생시간대**: {daynight}")
                if week := doc.get('week'): 
                    st.write(f"**발생요일**: {week}")

            with col2:
                for k, v in [('symptom', '현상'), ('incident_grade', '장애등급'), 
                            ('root_cause', '장애원인'), ('cause_type', '원인유형'), 
                            ('done_type', '처리유형'), ('owner_depart', '담당부서')]:
                    if val := doc.get(k): 
                        st.write(f"**{v}**: {val}")
            
            repair, plan = doc.get('incident_repair', '').strip(), doc.get('incident_plan', '').strip()
            
            if repair:
                st.write("**복구방법 (incident_repair)**:")
                clean = repair.replace(plan, '').strip() if plan and plan in repair else repair
                st.write(f"  {(clean or repair)[:300]}...")
            
            if plan:
                st.write("**개선계획 (incident_plan) - 참고용**:")
                st.write(f"  {plan[:300]}...")
            
            if notice := doc.get('repair_notice'): 
                st.write(f"**복구공지**: {notice[:200]}...")
            st.markdown("---")
    
    def display_processing_mode_info(self, query_type, processing_mode):
        """처리 모드 정보 표시"""
        if not self.debug_mode: 
            return
        
        modes = {
            'accuracy_first': ('정확성 우선', '#ff6b6b', '🎯', 'LLM 관련성 검증을 통한 최고 정확도 제공'),
            'coverage_first': ('포괄성 우선', '#4ecdc4', '📋', '의미적 유사성 기반 광범위한 검색 결과 제공'),
            'balanced': ('균형 처리', '#45b7d1', '⚖️', '정확성과 포괄성의 최적 균형')
        }
        
        name, color, icon, desc = modes.get(processing_mode, modes['balanced'])
        st.markdown(f"""<div style="background-color:{color}15;border-left:4px solid {color};padding:10px;border-radius:5px;margin:10px 0;">
<strong>{icon} {name} ({query_type.upper()})</strong><br><small>{desc}</small></div>""", unsafe_allow_html=True)
    
    def display_performance_metrics(self, metrics):
        """성능 메트릭 표시"""
        if not metrics or not self.debug_mode: 
            return
        with st.expander("처리 성능 메트릭"):
            cols = st.columns(len(metrics))
            for i, (name, value) in enumerate(metrics.items()):
                with cols[i]: 
                    st.metric(name.replace('_', ' ').title(), value)
    
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
            'inquiry': [
                "조회하고 싶은 조건을 명확히 명시하세요",
                "'내역', '목록', '리스트' 등의 키워드를 사용하세요",
                "시간대, 요일, 서비스명 등 필터 조건을 포함하세요",
                "결과는 표 형태로 제공되며 엑셀 다운로드가 가능합니다",
                "복구방법 박스 없이 깔끔한 목록 형태로 제공됩니다"
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
            for ex in time_examples: 
                st.write(f"  - {ex}")
            
            if query_type == 'inquiry':
                st.write("\n**📋 장애 내역 조회 예시:**")
                inquiry_examples = [
                    "블록체인기반지역화폐 야간 장애내역",
                    "ERP 2025년 1월 장애 목록",
                    "API 서비스 주간 장애 리스트",
                    "2등급 장애 2025년 전체 내역"
                ]
                for ex in inquiry_examples: 
                    st.write(f"  - {ex}")
                
                st.write("\n**📥 엑셀 다운로드 기능:**")
                st.write("• 장애 내역 조회 결과를 자동으로 표 형태로 정리")
                st.write("• 조건별로 파일명 자동 생성 (예: ERP_2025년_야간_장애내역_20250104_143022.xlsx)")
                st.write("• 다운로드 버튼을 통해 즉시 엑셀 파일로 저장 가능")
            
            if query_type == 'default':
                st.write("\n**📊 자동 차트 생성 예시:**")
                chart_examples = [
                    "2024년 연도별 장애 통계 → 연도별 선 그래프",
                    "부서별 장애 처리 현황 → 부서별 가로 막대 그래프", 
                    "시간대별 장애 발생 분포 → 시간대별 세로 막대 그래프",
                    "장애등급별 발생 비율 → 등급별 원형 그래프",
                    "월별 장애 발생 추이 → 월별 선 그래프"
                ]
                for ex in chart_examples: 
                    st.write(f"  - {ex}")
            
            if query_type == 'repair':
                st.write("\n**복구방법 관련 중요 안내:**")
                st.write("• 복구방법은 incident_repair 필드 데이터만 사용됩니다")
                st.write("• 개선계획(incident_plan)은 별도 참고용으로 제공됩니다")
                st.write("• 두 정보는 명확히 구분되어 표시됩니다")
    
    def display_time_filter_info(self, time_conditions):
        """시간 조건 필터링 정보 표시"""
        if not time_conditions or not time_conditions.get('is_time_query') or not self.debug_mode: 
            return
        
        desc = []
        if daynight := time_conditions.get('daynight'):
            desc.append(f"{'🌞' if daynight == '주간' else '🌙'} 시간대: {daynight}")
        if week := time_conditions.get('week'):
            week_desc = f"{week}{'요일' if week not in ['평일', '주말'] else ''}"
            desc.append(f"📅 {week_desc}")
        
        if desc: 
            st.info(f"⏰ 시간 조건 필터링 적용: {', '.join(desc)}")
    
    def display_validation_results(self, validation_result):
        """쿼리 처리 검증 결과 표시"""
        if not validation_result or not self.debug_mode: 
            return
        
        if not validation_result['is_valid']:
            st.warning("처리 결과에 주의사항이 있습니다.")
        
        if validation_result['warnings']:
            with st.expander("경고사항"):
                for w in validation_result['warnings']: 
                    st.warning(w)
        
        if validation_result['recommendations']:
            with st.expander("개선 권장사항"):
                for r in validation_result['recommendations']: 
                    st.info(r)
    
    def remove_text_charts_from_response(self, response_text):
        """응답에서 텍스트 차트 제거"""
        if not response_text:
            return response_text
        
        patterns = [
            r'각\s*월별.*?차트로\s*나타낼\s*수\s*있습니다:.*?(?=\n\n|\n[^월"\d]|$)',
            r'\d+월:\s*[▬▓▒░▬\*\-\|]+.*?(?=\n\n|\n[^월"\d]|$)',
            r'\n.*[▬▓▒░▬\*\-\|]{2,}.*\n',
            r'```[^`]*[▬▓▒░▬\*\-\|]{2,}[^`]*```'
        ]
        
        cleaned_response = response_text
        for pattern in patterns:
            cleaned_response = re.sub(pattern, '', cleaned_response, flags=re.MULTILINE | re.DOTALL)
        
        return re.sub(r'\n{3,}', '\n\n', cleaned_response).strip()
    
    def _get_stats(self, documents, field, label_map=None):
        """통계 데이터 추출"""
        stats = {}
        for doc in documents:
            if val := doc.get(field): 
                stats[val] = stats.get(val, 0) + 1
        return stats
    
    def _display_stats(self, stats, label, emoji_map=None, sort_key=None):
        """통계 표시"""
        if not stats: 
            return
        st.write(f"**{label}:**")
        items = sorted(stats.items(), key=sort_key or (lambda x: x[1]), reverse=True)
        for key, count in items:
            emoji = emoji_map.get(key, '') if emoji_map else ''
            st.write(f"  {emoji} {key}: {count}건")
    
    def show_time_statistics(self, documents):
        """시간대/요일별 통계 정보 표시"""
        if not documents: 
            return
        daynight_stats, week_stats = self._get_stats(documents, 'daynight'), self._get_stats(documents, 'week')
        
        if daynight_stats or week_stats:
            with st.expander("시간별 통계 정보"):
                col1, col2 = st.columns(2)
                with col1:
                    if daynight_stats:
                        self._display_stats(daynight_stats, "시간대별 분포", {'주간': '🌞', '야간': '🌙'})
                with col2:
                    if week_stats:
                        week_order = ['월', '화', '수', '목', '금', '토', '일', '평일', '주말']
                        self._display_stats(week_stats, "요일별 분포", 
                                          sort_key=lambda x: week_order.index(x[0]) if x[0] in week_order else 999)
    
    def show_department_statistics(self, documents):
        """부서별 통계 정보 표시"""
        if not documents: 
            return
        dept_stats = self._get_stats(documents, 'owner_depart')
        if dept_stats:
            with st.expander("부서별 통계 정보"):
                self._display_stats(dept_stats, "담당부서별 분포")
    
    def show_comprehensive_statistics(self, documents):
        """시간대/요일/부서별 종합 통계 정보 표시"""
        if not documents: 
            return
        daynight, week, dept = (self._get_stats(documents, field) 
                               for field in ['daynight', 'week', 'owner_depart'])
        
        if any([daynight, week, dept]):
            with st.expander("종합 통계 정보"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    if daynight: 
                        self._display_stats(daynight, "시간대별 분포", {'주간': '🌞', '야간': '🌙'})
                with col2:
                    if week:
                        week_order = ['월', '화', '수', '목', '금', '토', '일', '평일', '주말']
                        self._display_stats(week, "요일별 분포",
                                          sort_key=lambda x: week_order.index(x[0]) if x[0] in week_order else 999)
                with col3:
                    if dept:
                        top5 = dict(sorted(dept.items(), key=lambda x: x[1], reverse=True)[:5])
                        self._display_stats(top5, "담당부서별 분포")
    
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

**📋 INQUIRY 타입 특별 안내:**
- 장애 내역 조회 시에는 복구방법 박스가 표시되지 않습니다
- 깔끔한 목록 형태로 결과를 제공합니다
- 표 형태의 데이터를 엑셀 파일로 다운로드할 수 있습니다""")
    
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
- 분류 관련 키워드 포함 (연도별, 부서별, 서비스별 등)
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
    
    def show_inquiry_feature_info(self):
        """INQUIRY 기능 안내 정보"""
        with st.expander("📋 장애 내역 조회 및 엑셀 다운로드 기능"):
            st.markdown("""
**📊 장애 내역 조회 기능:**
- 특정 조건에 맞는 장애 내역을 목록 형태로 제공
- 복구방법 박스 없이 깔끔한 표 형태로 결과 표시
- 다양한 필터 조건 지원 (서비스명, 시간대, 요일, 등급 등)

**📥 엑셀 다운로드 기능:**
- 조회 결과를 자동으로 표 형태로 정리
- 원클릭으로 xlsx 파일 다운로드 가능
- 조건별로 파일명 자동 생성

**💡 사용 예시:**
- "블록체인기반지역화폐 야간 장애내역" 
- "ERP 2025년 1월 장애 목록"
- "API 서비스 주간 장애 리스트"
- "2등급 장애 전체 내역"

**📄 다운로드 파일 형식:**
- 파일명: 서비스명_조건_장애내역_날짜시간.xlsx
- 포함 정보: 장애ID, 서비스명, 등급, 발생일자, 시간대, 요일, 장애시간, 현상, 원인, 담당부서
- 스타일링: 헤더 강조, 테두리, 자동 컬럼 너비 조정

**🎯 INQUIRY 모드 특징:**
- 복구방법 박스 표시 안함
- 목록 위주의 깔끔한 UI
- 표 형태 데이터 제공
- 엑셀 다운로드 버튼 자동 표시
""")