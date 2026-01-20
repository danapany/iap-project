import streamlit as st
import re
import html as html_module
import time

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
            formatted = ''.join([f'<li key="cause-{num}" style="margin-bottom:8px;line-height:1.5;"><strong>원인{num}:</strong> {c}</li>' 
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
        """강화된 박스 마커 제거 - REPAIR_BOX 제거"""
        patterns = [
            r'\[CAUSE_BOX_START\].*?\[CAUSE_BOX_END\]',
            r'\[.*?_BOX_START\].*?\[.*?_BOX_END\]', 
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
    

    # ============== 새로 추가된 메서드들 (repair 디자인용) ==============

    def _strip_html_tags(self, text):
        """HTML 태그와 마크다운 헤더를 제거하고 순수 텍스트만 반환"""
        if not text:
            return text
        
        # HTML 태그 제거
        clean_text = re.sub(r'<[^>]+>', '', text)
        # HTML 엔티티 디코드
        clean_text = html_module.unescape(clean_text)
        
        # 마크다운 헤더 제거 및 정리
        clean_text = self._clean_markdown_headers(clean_text)
        
        return clean_text.strip()
    
    def _clean_markdown_headers(self, text):
        """마크다운 헤더를 제거하고 적절한 줄바꿈으로 변환"""
        if not text:
            return text
        
        # ## 📋 형태의 헤더를 이모지와 텍스트만 남기고 줄바꿈 추가
        text = re.sub(r'^#+\s*(📋.*?)(?=\s|$)', r'\1\n', text, flags=re.MULTILINE)
        
        # ### 형태의 헤더도 동일하게 처리
        text = re.sub(r'^#+\s*(.*?)(?=\s|$)', r'\1\n', text, flags=re.MULTILINE)
        
        # 연속된 공백이나 줄바꿈 정리
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r'^\s+', '', text, flags=re.MULTILINE)
        
        return text.strip()
    
    def _parse_html_content(self, html_content):
        """HTML 컨텐츠를 태그와 텍스트로 분리"""
        parts = []
        tag_pattern = re.compile(r'(<[^>]+>)')
        segments = tag_pattern.split(html_content)
        
        for segment in segments:
            if segment.startswith('<'):
                parts.append({'type': 'tag', 'content': segment, 'text': ''})
            elif segment:
                parts.append({'type': 'text', 'content': segment, 'text': segment})
        
        return parts
    
    def typewriter_sections(self, sections, duration=10.0):
        """스마트 타이핑 효과"""
        time_per_section = duration / len(sections) if sections else 0
        
        for placeholder, content in sections:
            parts = self._parse_html_content(content)
            text_chars = sum(len(p['text']) for p in parts if p['type'] == 'text')
            char_delay = time_per_section / text_chars if text_chars > 0 else 0.01
            
            displayed_parts = []
            for part in parts:
                if part['type'] == 'tag':
                    displayed_parts.append(part['content'])
                else:
                    for char in part['text']:
                        displayed_parts.append(char)
                        placeholder.markdown(''.join(displayed_parts), unsafe_allow_html=True)
                        time.sleep(char_delay)
            
            placeholder.markdown(content, unsafe_allow_html=True)
    
    def display_repair_report_with_tabs(self, incidents_data, use_typewriter=False, duration=8.0, message_index=None):
        """
        repair 타입의 응답을 탭 기반 디자인으로 표시
        Args:
            incidents_data: {
                'summary': {
                    'overall': '전체 종합의견',
                    'recovery_methods': ['복구방법1', '복구방법2', ...]
                },
                'incidents': [
                    {장애1 데이터},
                    {장애2 데이터},
                    ...
                ]
            }
            message_index: 메시지 인덱스 (여러 답변 구분용)
        """
        # 안정적인 고유 ID 생성 (내용 기반 해시)
        import hashlib
        
        # incidents의 incident_id들을 조합하여 고유 ID 생성
        incident_ids = [inc.get('incident_id', '') for inc in incidents_data.get('incidents', [])]
        id_string = '-'.join(incident_ids[:10])  # 최대 10개만 사용
        
        # message_index가 있으면 포함
        if message_index is not None:
            id_string = f"{message_index}-{id_string}"
        
        unique_call_id = hashlib.md5(id_string.encode()).hexdigest()[:12]
        
        # 헤더
        st.markdown("""
        <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        </div>
        """, unsafe_allow_html=True)
        
        if use_typewriter:
            ph1 = st.empty()
            sections = []
            
            # 종합 의견 섹션 (plain text로 표시)
            overall_text = self._strip_html_tags(incidents_data['summary']['overall'])
            
            # 복구방법들을 텍스트로 조합
            recovery_text = ""
            for idx, method in enumerate(incidents_data['summary']['recovery_methods'], 1):
                clean_method = self._strip_html_tags(method)
                recovery_text += f"\n\n복구방법 {idx}\n{clean_method}"
            
            # 전체 텍스트 조합
            full_text = f"{overall_text}\n\n통합 복구 방법{recovery_text}"
            
            sections.append((ph1, f"""
            <div key="summary-{unique_call_id}" style='background: white; padding: 30px; border-radius: 15px;
                        margin-bottom: 20px; box-shadow: 0 8px 25px rgba(0,0,0,0.12);
                        border-top: 6px solid #667eea;'>
                <h2 style='color: #667eea; margin: 0 0 15px 0; font-size: 1.9em;
                           border-bottom: 3px solid #667eea; padding-bottom: 15px;
                           display: flex; align-items: center;'>
                    <span style='margin-right: 10px;'>💡</span> 종합 의견
                </h2>
                <div style='background: #f7fafc; padding: 20px; border-radius: 10px; 
                            margin-bottom: 20px; border-left: 4px solid #667eea;'>
                    <pre style='color: #2d3748; line-height: 1.8; font-size: 1.05em; margin: 0; 
                               white-space: pre-wrap; word-wrap: break-word; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;'>
    {html_module.escape(full_text)}</pre>
                </div>
            </div>
            """))
            
            self.typewriter_sections(sections, duration)
        else:
            # 타이핑 효과 없이 즉시 표시
            overall_text = self._strip_html_tags(incidents_data['summary']['overall'])
            
            # 복구방법들을 텍스트로 조합
            recovery_text = ""
            for idx, method in enumerate(incidents_data['summary']['recovery_methods'], 1):
                clean_method = self._strip_html_tags(method)
                recovery_text += f"\n\n복구방법 {idx}\n{clean_method}"
            
            # 전체 텍스트 조합
            full_text = f"{overall_text}\n\n통합 복구 방법{recovery_text}"
            
            st.markdown(f"""
            <div key="summary-{unique_call_id}" style='background: white; padding: 30px; border-radius: 15px;
                        margin-bottom: 20px; box-shadow: 0 8px 25px rgba(0,0,0,0.12);
                        border-top: 6px solid #667eea;'>
                <h2 style='color: #667eea; margin: 0 0 15px 0; font-size: 1.9em;
                           border-bottom: 3px solid #667eea; padding-bottom: 15px;
                           display: flex; align-items: center;'>
                    <span style='margin-right: 10px;'>💡</span> 종합 의견
                </h2>
                <div style='background: #f7fafc; padding: 20px; border-radius: 10px; 
                            margin-bottom: 20px; border-left: 4px solid #667eea;'>
                    <pre style='color: #2d3748; line-height: 1.8; font-size: 1.05em; margin: 0; 
                               white-space: pre-wrap; word-wrap: break-word; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;'>
    {html_module.escape(full_text)}</pre>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # ============================================================
        # 페이징 기능 추가: 한 페이지당 6개의 탭만 표시
        # ============================================================
        
        # 세션 스테이트 초기화: 고유 ID별 현재 페이지 번호
        page_key = f'repair_tab_page_{unique_call_id}'
        if page_key not in st.session_state:
            st.session_state[page_key] = 0
        
        # 페이징 설정
        ITEMS_PER_PAGE = 6
        total_incidents = len(incidents_data['incidents'])
        total_pages = (total_incidents + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE  # 올림 나눗셈
        
        # 현재 페이지 범위 계산
        current_page = st.session_state[page_key]
        start_idx = current_page * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, total_incidents)
        
        # 페이징 컨트롤 (상단) - 2페이지 이상일 때만 표시
        if total_pages > 1:
            col_prev, col_info, col_next = st.columns([1, 2, 1])
            
            with col_prev:
                if current_page > 0:
                    if st.button("◀ 이전", key=f"prev_{unique_call_id}", use_container_width=True):
                        st.session_state[page_key] -= 1
                        st.rerun()
            
            with col_info:
                st.markdown(f"""
                <div key="pageinfo-{unique_call_id}-{current_page}" style='text-align: center; padding: 10px; font-size: 1.1em; color: #4a5568;'>
                    <b>페이지 {current_page + 1} / {total_pages}</b> 
                    <span style='color: #718096;'>(전체 {total_incidents}개 중 {start_idx + 1}-{end_idx}번째 표시)</span>
                </div>
                """, unsafe_allow_html=True)
            
            with col_next:
                if current_page < total_pages - 1:
                    if st.button("다음 ▶", key=f"next_{unique_call_id}", use_container_width=True):
                        st.session_state[page_key] += 1
                        st.rerun()
        
        # 현재 페이지의 인시던트만 표시
        current_page_incidents = incidents_data['incidents'][start_idx:end_idx]
        
        # 각 장애별 탭 구성 - 장애/이상징후 구분
        tab_labels = []
        
        for idx in range(start_idx, end_idx):
            inc = incidents_data['incidents'][idx]
            source_type = inc.get('_source_type', 'incident')
            incident_id = inc.get('incident_id', 'INC-UNKNOWN')
            
            # 전체 인덱스 기준으로 번호 표시 (연속성 유지)
            display_num = idx + 1
            
            if source_type == 'anomaly':
                label = f"이상징후 {display_num}: {incident_id}"
            else:  # 'incident' or default
                label = f"장애 {display_num}: {incident_id}"
            
            tab_labels.append(label)
        
        tabs = st.tabs(tab_labels)
        
        # 각 탭에 장애 정보 표시
        for tab, incident in zip(tabs, current_page_incidents):
            with tab:
                self._display_single_incident_detail(incident)
        
    def _display_single_incident_detail(self, incident):
            """단일 장애 상세 정보 표시 - 핵심 포인트 섹션 추가 (필드 매핑 수정)"""
            
            # ★★★ 이상징후 여부 확인 ★★★
            source_type = incident.get('_source_type', 'incident')
            is_anomaly = (source_type == 'anomaly')
            
            # 고유 ID 생성 (React key 충돌 방지)
            incident_id = incident.get('incident_id', 'unknown')
            unique_key = f"{incident_id}-{id(incident)}"
            
            # ======================================
            # 핵심 포인트 섹션 - 장애내역만 표시
            # ======================================
            
            # ★★★ 이상징후는 핵심 포인트 섹션 스킵 ★★★
            if not is_anomaly:
                # 안전한 데이터 추출 함수
                def safe_get(data, *keys):
                    """여러 키를 시도하여 값을 가져오고 HTML 태그 제거"""
                    for key in keys:
                        value = data.get(key, '')
                        if value and str(value).strip():
                            # HTML 태그 제거
                            cleaned = re.sub(r'<[^>]+>', '', str(value))
                            cleaned = html_module.unescape(cleaned)
                            return cleaned.strip()
                    return ''
                
                # 각 필드에 대한 값 추출
                cause_text = safe_get(incident, 'detailed_cause', 'cause', 'root_cause')
                impact_text = safe_get(incident, 'failure_status', 'impact', 'symptom')
                recovery_text = safe_get(incident, 'recovery_method', 'recovery', 'incident_repair')
                followup_text = safe_get(incident, 'improvement_plan', 'followup', 'incident_plan')
                
                st.markdown(f"""
                <div key="keypoints-{unique_key}" style='background: white; padding: 25px; border-radius: 12px;
                            margin-bottom: 15px; box-shadow: 0 6px 20px rgba(0,0,0,0.1);
                            border-left: 6px solid #4facfe;'>
                    <h3 style='color: #4facfe; margin: 0 0 20px 0; font-size: 1.6em;
                            border-bottom: 2px solid #e2e8f0; padding-bottom: 12px;'>
                        🎯 핵심 포인트
                    </h3>
                    <div style='display: grid; grid-template-columns: 1fr 1fr; gap: 15px;'>
                        <div key="cause-{unique_key}" style='background: #f0f9ff; padding: 15px; border-radius: 8px;
                                    border-left: 4px solid #3b82f6;'>
                            <div style='color: #1e40af; font-weight: bold; margin-bottom: 8px; 
                                        font-size: 1.1em;'>① 장애 원인</div>
                            <div style='color: #1e293b; line-height: 1.6; font-size: 0.95em;'>
                                {html_module.escape(cause_text) if cause_text else '<span style="color: #94a3b8;">정보 없음</span>'}
                            </div>
                        </div>
                        <div key="impact-{unique_key}" style='background: #fef3c7; padding: 15px; border-radius: 8px;
                                    border-left: 4px solid #f59e0b;'>
                            <div style='color: #92400e; font-weight: bold; margin-bottom: 8px; 
                                        font-size: 1.1em;'>② 영향 범위</div>
                            <div style='color: #1e293b; line-height: 1.6; font-size: 0.95em;'>
                                {html_module.escape(impact_text) if impact_text else '<span style="color: #94a3b8;">정보 없음</span>'}
                            </div>
                        </div>
                        <div key="recovery-{unique_key}" style='background: #dcfce7; padding: 15px; border-radius: 8px;
                                    border-left: 4px solid #10b981;'>
                            <div style='color: #065f46; font-weight: bold; margin-bottom: 8px; 
                                        font-size: 1.1em;'>③ 복구 조치</div>
                            <div style='color: #1e293b; line-height: 1.6; font-size: 0.95em;'>
                                {html_module.escape(recovery_text) if recovery_text else '<span style="color: #94a3b8;">정보 없음</span>'}
                            </div>
                        </div>
                        <div key="followup-{unique_key}" style='background: #fce7f3; padding: 15px; border-radius: 8px;
                                    border-left: 4px solid #ec4899;'>
                            <div style='color: #831843; font-weight: bold; margin-bottom: 8px; 
                                        font-size: 1.1em;'>④ 후속 조치</div>
                            <div style='color: #1e293b; line-height: 1.6; font-size: 0.95em;'>
                                {html_module.escape(followup_text) if followup_text else '<span style="color: #94a3b8;">정보 없음</span>'}
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # ======================================
            # 기존 3열 레이아웃 (INCIDENT INFO, SYSTEM INFO, RECOVERY ACTION)
            # ======================================
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown(f"""
                <div key="info-{unique_key}" style='background: white; padding: 20px; border-radius: 10px;
                            border: 2px solid #e2e8f0; height: 100%;'>
                    <div style='background: #667eea; color: white; padding: 8px 12px;
                                border-radius: 6px; margin-bottom: 15px; font-weight: 600;
                                text-align: center; font-size: 0.95em; letter-spacing: 0.5px;'>
                        INCIDENT INFO
                    </div>
                    <div style='color: #475569; line-height: 1.9; font-size: 0.92em;'>
                        <p key="service-{unique_key}" style='margin: 10px 0; padding: 8px; background: #f8fafc; border-radius: 5px;'>
                            <span style='color: #64748b; font-weight: 600; display: block; margin-bottom: 5px;'>서비스명</span>
                            <span style='color: #1e293b;'>{html_module.escape(str(incident.get('service', incident.get('service_name', ''))))}</span>
                        </p>
                        <p key="severity-{unique_key}" style='margin: 10px 0; padding: 8px; background: #f8fafc; border-radius: 5px;'>
                            <span style='color: #64748b; font-weight: 600; display: block; margin-bottom: 5px;'>장애등급</span>
                            <span style='color: #dc2626; font-weight: 700;'>{html_module.escape(str(incident.get('severity', incident.get('incident_grade', ''))))}</span>
                        </p>
                        <p key="timestamp-{unique_key}" style='margin: 10px 0; padding: 8px; background: #f8fafc; border-radius: 5px;'>
                            <span style='color: #64748b; font-weight: 600; display: block; margin-bottom: 5px;'>발생일시</span>
                            <span style='color: #1e293b;'>{html_module.escape(str(incident.get('timestamp', incident.get('error_date', ''))))}</span>
                        </p>
                        <p key="duration-{unique_key}" style='margin: 10px 0; padding: 8px; background: #f8fafc; border-radius: 5px;'>
                            <span style='color: #64748b; font-weight: 600; display: block; margin-bottom: 5px;'>장애시간</span>
                            <span style='color: #dc2626; font-weight: 600;'>{html_module.escape(str(incident.get('duration', incident.get('error_time', ''))))}</span>
                        </p>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                st.markdown(f"""
                <div key="system-{unique_key}" style='background: white; padding: 20px; border-radius: 10px;
                            border: 2px solid #e2e8f0; height: 100%;'>
                    <div style='background: #f093fb; color: white; padding: 8px 12px;
                                border-radius: 6px; margin-bottom: 15px; font-weight: 600;
                                text-align: center; font-size: 0.95em; letter-spacing: 0.5px;'>
                        SYSTEM INFO
                    </div>
                    <div style='color: #475569; line-height: 1.9; font-size: 0.92em;'>
                        <p key="dept-{unique_key}" style='margin: 10px 0; padding: 8px; background: #f8fafc; border-radius: 5px;'>
                            <span style='color: #64748b; font-weight: 600; display: block; margin-bottom: 5px;'>담당부서</span>
                            <span style='color: #1e293b;'>{html_module.escape(str(incident.get('department', incident.get('owner_depart', ''))))}</span>
                        </p>
                        <p key="fixtype-{unique_key}" style='margin: 10px 0; padding: 8px; background: #f8fafc; border-radius: 5px;'>
                            <span style='color: #64748b; font-weight: 600; display: block; margin-bottom: 5px;'>처리유형</span>
                            <span style='color: #1e293b;'>{html_module.escape(str(incident.get('fix_type', incident.get('done_type', ''))))}</span>
                        </p>
                        <p key="detcause-{unique_key}" style='margin: 10px 0; padding: 8px; background: #f8fafc; border-radius: 5px;'>
                            <span style='color: #64748b; font-weight: 600; display: block; margin-bottom: 5px;'>장애원인</span>
                            <span style='color: #1e293b;'>{html_module.escape(str(incident.get('detailed_cause', incident.get('root_cause', ''))))}</span>
                        </p>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            with col3:
                # ★★★ 핵심 수정: symptom 필드를 확실하게 fallback으로 추가 ★★★
                failure_status_value = incident.get('failure_status', '')
                if not failure_status_value or str(failure_status_value).strip() == '':
                    # failure_status가 비어있으면 symptom 필드 확인
                    failure_status_value = incident.get('symptom', '')
                
                st.markdown(f"""
                <div key="recovery-action-{unique_key}" style='background: white; padding: 20px; border-radius: 10px;
                            border: 2px solid #e2e8f0; height: 100%;'>
                    <div style='background: #10b981; color: white; padding: 8px 12px;
                                border-radius: 6px; margin-bottom: 15px; font-weight: 600;
                                text-align: center; font-size: 0.95em; letter-spacing: 0.5px;'>
                        RECOVERY ACTION
                    </div>
                    <div style='color: #475569; line-height: 1.9; font-size: 0.92em;'>
                        <p key="failstatus-{unique_key}" style='margin: 10px 0; padding: 8px; background: #f8fafc; border-radius: 5px;'>
                            <span style='color: #64748b; font-weight: 600; display: block; margin-bottom: 5px;'>장애상황</span>
                            <span style='color: #1e293b;'>{html_module.escape(str(failure_status_value))}</span>
                        </p>
                        <p key="recovmethod-{unique_key}" style='margin: 10px 0; padding: 8px; background: #f8fafc; border-radius: 5px;'>
                            <span style='color: #64748b; font-weight: 600; display: block; margin-bottom: 5px;'>복구방법</span>
                            <span style='color: #1e293b;'>{html_module.escape(str(incident.get('recovery_method', incident.get('incident_repair', ''))))}</span>
                        </p>
                        <p key="impplan-{unique_key}" style='margin: 10px 0; padding: 8px; background: #f8fafc; border-radius: 5px;'>
                            <span style='color: #64748b; font-weight: 600; display: block; margin-bottom: 5px;'>개선계획</span>
                            <span style='color: #1e293b;'>{html_module.escape(str(incident.get('improvement_plan', incident.get('incident_plan', ''))))}</span>
                        </p>
                    </div>
                </div>
                """, unsafe_allow_html=True)

    def _extract_and_format_timestamp(self, text):
        """텍스트에서 날짜/시간 정보를 추출하고 표준 형식으로 변환"""
        import re
        from datetime import datetime
        
        if not text:
            return ''
        
        # 다양한 날짜 패턴 매칭
        date_patterns = [
            r'(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{1,2})',  # 2024-04-01 09:26
            r'(\d{4})\.(\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{1,2})', # 2024.04.01 09:26
            r'(\d{4})/(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{1,2})',  # 2024/04/01 09:26
            r'(\d{4})-(\d{1,2})-(\d{1,2})',  # 2024-04-01 (시간 없음)
            r'(\d{4})\.(\d{1,2})\.(\d{1,2})',  # 2024.04.01 (시간 없음)
            r'(\d{1,2})/(\d{1,2})/(\d{4})',   # 01/04/2024
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                groups = match.groups()
                try:
                    if len(groups) == 5:  # 날짜 + 시간
                        year, month, day, hour, minute = groups
                        return f"{int(year):04d}-{int(month):02d}-{int(day):02d} {int(hour):02d}:{int(minute):02d}"
                    elif len(groups) == 3:  # 날짜만
                        if len(groups[2]) == 4:  # MM/DD/YYYY 형식
                            month, day, year = groups
                            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
                        else:  # YYYY-MM-DD 형식
                            year, month, day = groups
                            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
                except ValueError:
                    continue
        
        # 패턴이 매칭되지 않으면 원본 반환
        return text.strip()
    
    def _parse_repair_response_to_incidents_data(self, response_text):
        """repair 응답 텍스트를 incidents_data 구조로 파싱 - 실제 응답 형식에 맞춤"""
        try:
            # ★★★ 디버그: LLM 응답 출력 ★★★
            print("="*80)
            print("DEBUG: LLM 응답 (처음 1500자)")
            print("="*80)
            print(response_text[:1500])
            print("="*80)
            incidents_data = {
                'summary': {
                    'overall': '',
                    'recovery_methods': []
                },
                'incidents': []
            }
            
            # 전체 텍스트에서 날짜 패턴 검색
            import re
            date_matches = re.findall(r'(\d{4}[-./]\d{1,2}[-./]\d{1,2}(?:\s+\d{1,2}:\d{1,2})?)', response_text)
            extracted_dates = [self._extract_and_format_timestamp(match) for match in date_matches]
            
            lines = response_text.split('\n')
            overall_lines = []
            recovery_methods = []
            current_incident = None
            incidents = []
            in_incident_section = False
            
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                
                # 장애내역/이상징후내역 섹션 시작 감지
                if ('장애내역' in line and 'Incident Records' in line) or ('이상징후내역' in line and 'Anomaly Records' in line):
                    in_incident_section = True
                    print(f"DEBUG: ✅ 섹션 감지됨: {line}")
                    i += 1
                    continue
                
                # 개별 장애/이상징후 시작 감지 (예: [장애내역 2], [이상징후 1], Case 1 등)
                if in_incident_section and (line.startswith('[장애내역') or line.startswith('[이상징후') or line.startswith('Case ')):
                    if current_incident and any(current_incident.values()):
                        incidents.append(current_incident)
                        print(f"DEBUG: ✅ Incident 추가됨: {current_incident.get('incident_id')}")
                    
                    # _source_type 결정: [이상징후]로 시작하면 'anomaly', 그 외는 'incident'
                    source_type = 'anomaly' if line.startswith('[이상징후') else 'incident'
                    print(f"DEBUG: 🆕 새 Incident 시작: {line} (type: {source_type})")
                    
                    current_incident = {
                        'incident_id': '',
                        'service': '',
                        'severity': '',
                        'timestamp': extracted_dates[0] if extracted_dates else '',
                        'duration': '',
                        'department': '',
                        'fix_type': '',
                        'detailed_cause': '',
                        'failure_status': '',
                        'symptom': '',  # ★★★ 추가: symptom 필드 ★★★
                        'recovery_method': '',
                        'improvement_plan': '',
                        '_source_type': source_type  # 중요: 소스 타입 추가
                    }
                    
                    # ★★★ 같은 라인에 장애ID가 있는 경우 처리 (예: "[이상징후 7] 장애ID: INM...") ★★★
                    if '장애 ID:' in line or '장애ID:' in line:
                        id_text = line.split('ID:')[-1].strip().replace('**', '').replace('*', '')
                        current_incident['incident_id'] = id_text
                    
                    i += 1
                    continue
                
                # 장애내역 섹션 전까지는 종합 의견
                if not in_incident_section and line and not line.startswith('---'):
                    # HTML 태그나 특수 문자 제외
                    if not line.startswith('<') and not line.startswith('※'):
                        overall_lines.append(line)
                
                # 표 형태 데이터 파싱 추가
                if '|' in line and ('장애' in line or 'INM' in line or '2024' in line):
                    # 표의 행 데이터 파싱
                    cells = [cell.strip() for cell in line.split('|') if cell.strip()]
                    if len(cells) >= 4:  # 최소 4개 컬럼이 있어야 유효한 데이터
                        if current_incident is None:
                            current_incident = {
                                'incident_id': '',
                                'service_name': '',
                                'severity': '',
                                'timestamp': extracted_dates[0] if extracted_dates else '',
                                'duration': '',
                                'department': '',
                                'fix_type': '',
                                'detailed_cause': '',
                                'failure_status': '',
                                'symptom': '',  # ★★★ 추가: symptom 필드 ★★★
                                'recovery_method': '',
                                'improvement_plan': '',
                                '_source_type': 'table'
                            }
                        
                        # 표의 컬럼 순서에 맞게 데이터 추출
                        for idx, cell in enumerate(cells):
                            if idx == 0 and 'INM' in cell:  # 장애 ID
                                current_incident['incident_id'] = cell
                            elif idx == 1:  # 서비스명
                                current_incident['service_name'] = cell
                            elif idx == 2:  # 장애등급
                                current_incident['severity'] = cell
                            elif idx == 3 and ('2024' in cell or '2025' in cell):  # 발생일자
                                current_incident['timestamp'] = cell
                            elif idx == 4:  # 시간대
                                if current_incident['timestamp']:
                                    current_incident['timestamp'] += f" ({cell})"
                            elif idx == 5:  # 장애시간
                                current_incident['duration'] = cell
                            elif '분' in cell and not current_incident['duration']:  # 장애시간 (다른 위치)
                                current_incident['duration'] = cell
                            elif len(cell) > 10 and not current_incident['failure_status']:  # 장애현상 (긴 텍스트)
                                current_incident['failure_status'] = cell
                            elif cell and not current_incident['department'] and len(cell) < 20:  # 담당부서
                                current_incident['department'] = cell
                if current_incident is not None and in_incident_section:
                    # 다양한 형식 지원
                    if '장애 ID:' in line or '장애ID:' in line or 'ID:' in line:
                        id_text = line.split('ID:')[-1].strip().replace('**', '').replace('*', '')
                        current_incident['incident_id'] = id_text
                    
                    elif '서비스명:' in line or '서비스:' in line:
                        current_incident['service'] = line.split(':')[-1].strip()
                    
                    elif '장애등급:' in line or '등급:' in line:
                        current_incident['severity'] = line.split(':')[-1].strip()
                    
                    elif '발생일시:' in line or '발생시간:' in line or '발생일자:' in line:
                        # split(':', 1)로 첫 번째 콜론만 분리 (시간 형식 "HH:MM" 보존)
                        current_incident['timestamp'] = line.split(':', 1)[-1].strip()
                    # 시간대와 요일은 timestamp에 추가하지 않음 (error_date에 이미 완전한 형식 포함)
                    #                     elif '시간대:' in line:
                    #                         # 시간대 정보가 있으면 timestamp에 추가
                    #                         time_period = line.split(':')[-1].strip()
                    #                         if current_incident['timestamp']:
                    #                             current_incident['timestamp'] += f" ({time_period})"
                    #                         else:
                    #                             current_incident['timestamp'] = time_period
                    #                     
                    #                     elif '요일:' in line:
                    #                         # 요일 정보가 있으면 timestamp에 추가
                    #                         day_of_week = line.split(':')[-1].strip()
                    #                         if current_incident['timestamp']:
                    #                             current_incident['timestamp'] += f" {day_of_week}"
                    #                         else:
                    #                             current_incident['timestamp'] = day_of_week
                    
                    elif '장애시간:' in line or '지속시간:' in line:
                        current_incident['duration'] = line.split(':')[-1].strip()
                    
                    elif '담당부서:' in line or '부서:' in line:
                        current_incident['department'] = line.split(':')[-1].strip()
                    
                    elif '처리유형:' in line or '조치유형:' in line:
                        current_incident['fix_type'] = line.split(':')[-1].strip()
                    
                    elif '장애원인:' in line or '원인:' in line:
                        cause_text = line.split(':')[-1].strip()
                        # 다음 줄도 원인의 일부인지 확인
                        j = i + 1
                        while j < len(lines) and lines[j].strip() and not ':' in lines[j]:
                            cause_text += ' ' + lines[j].strip()
                            j += 1
                        current_incident['detailed_cause'] = cause_text
                        i = j - 1
                    
                    elif '장애상황:' in line or '현상:' in line or '증상:' in line:
                        status_value = line.split(':')[-1].strip()
                        # ★★★ 빈 값이 아닐 때만 저장 (빈 라인 무시) ★★★
                        if status_value:
                            current_incident['failure_status'] = status_value
                            current_incident['symptom'] = status_value
                    
                    elif '복구방법:' in line or '조치방법:' in line or '해결방법:' in line:
                        recovery_text = line.split(':')[-1].strip()
                        # 여러 줄에 걸친 복구방법 수집
                        j = i + 1
                        while j < len(lines) and lines[j].strip():
                            next_line = lines[j].strip()
                            # 다음 필드가 시작되면 중단
                            if any(keyword in next_line for keyword in ['개선계획:', '장애내역', 'Case ', '---', '장애 ID:']):
                                break
                            recovery_text += ' ' + next_line
                            j += 1
                        current_incident['recovery_method'] = recovery_text
                        recovery_methods.append(recovery_text)
                        i = j - 1
                    
                    elif '개선계획:' in line or '예방대책:' in line:
                        current_incident['improvement_plan'] = line.split(':')[-1].strip()
                
                i += 1
            
            # 마지막 incident 추가
            if current_incident and any(current_incident.values()):
                # timestamp 포맷팅 적용
                if current_incident.get('timestamp'):
                    current_incident['timestamp'] = self._extract_and_format_timestamp(current_incident['timestamp'])
                incidents.append(current_incident)
            
            # 종합 의견 구성
            incidents_data['summary']['overall'] = '\n'.join(overall_lines) if overall_lines else '장애 분석 결과입니다.'
            incidents_data['summary']['recovery_methods'] = recovery_methods if recovery_methods else ['복구방법을 확인해주세요.']
            
            # 모든 incidents의 timestamp 포맷팅
            for incident in incidents:
                if incident.get('timestamp'):
                    incident['timestamp'] = self._extract_and_format_timestamp(incident['timestamp'])
            
            incidents_data['incidents'] = incidents
            
            # 디버그 로그
            if self.debug_mode:
                print(f"파싱 결과: {len(incidents)}개 장애 발견")
                print(f"종합의견 길이: {len(incidents_data['summary']['overall'])}")
                print(f"복구방법 개수: {len(recovery_methods)}")
            
            # 최소한 incidents가 있어야 성공
            print(f"DEBUG: 파싱 완료 - incidents 개수: {len(incidents)}")
            if incidents:
                for inc in incidents[:3]:  # 처음 3개만 출력
                    print(f"  - {inc.get('incident_id')}: symptom='{inc.get('symptom')}', failure_status='{inc.get('failure_status')}'")
            else:
                print("DEBUG: ❌ incidents가 비어있음 - None 반환!")
            return incidents_data if incidents else None
            
        except Exception as e:
            if self.debug_mode:
                print(f"UI_DEBUG: repair 응답 파싱 실패: {str(e)}")
                import traceback
                print(traceback.format_exc())
            return None
    

    def display_response_with_query_type_awareness(self, response, query_type="default", chart_info=None):
            """쿼리 타입을 고려한 응답 표시 - repair 타입은 새 디자인 사용"""
            if not response:
                st.write("응답이 없습니다.")
                return
            
            response_text, chart_info = response if isinstance(response, tuple) else (response, chart_info)
            if chart_info and chart_info.get('chart'):
                response_text = self.remove_text_charts_from_response(response_text)
            
            # ★★★ REPAIR 타입 처리 - 새 디자인 적용 ★★★
            if query_type.lower() == 'repair':
                # response_text에서 incidents_data 파싱
                incidents_data = self._parse_repair_response_to_incidents_data(response_text)
                if incidents_data:
                    # 현재 메시지 인덱스 계산 (새 메시지이므로 기존 메시지 수)
                    msg_idx = len(st.session_state.get('messages', []))
                    self.display_repair_report_with_tabs(incidents_data, use_typewriter=True, message_index=msg_idx)
                    return
                # 파싱 실패 시 기존 방식으로 폴백
            
            # 나머지 코드는 기존과 동일...
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
                if '[CAUSE_BOX_START]' in converted_content:
                    converted_content, has_html = self.convert_cause_box_to_html(converted_content)
                    html_converted = html_converted or has_html
            
            # 응답 표시
            if html_converted:
                st.markdown(converted_content, unsafe_allow_html=True)
            else:
                st.write(converted_content)
            
            # 차트 표시 - statistics 타입에서만
            if (chart_info and chart_info.get('chart') and 
                query_type.lower() == 'statistics' and 
                self.chart_manager is not None):
                try:
                    # 올바른 메서드 호출: display_chart_with_data
                    self.chart_manager.display_chart_with_data(
                        chart_info['chart'],
                        chart_info.get('chart_data', {}),
                        chart_info.get('chart_type', 'bar'),
                        chart_info.get('query', '')
                    )
                    if self.debug_mode:
                        print(f"UI_DEBUG: 차트 표시 성공 - 타입: {chart_info.get('chart_type', 'bar')}")
                except Exception as e:
                    if self.debug_mode:
                        print(f"UI_DEBUG: 차트 표시 오류: {str(e)}")
                    import traceback
                    traceback.print_exc()
            
            
            # 엑셀 다운로드 버튼 (inquiry 타입에서만)
            if query_type.lower() == 'inquiry':
                if self.debug_mode:
                    print(f"UI_DEBUG: INQUIRY 타입 감지 - 엑셀 다운로드 버튼 표시 시작")
                
                try:
                    from utils.excel_utils import ExcelDownloadManager
                    excel_manager = ExcelDownloadManager()
                    
                    # 엑셀 다운로드 버튼 표시 시도
                    success = excel_manager.display_download_button(converted_content, query_type)
                    
                    if not success:
                        # 표가 없는 경우 사용자에게 안내
                        st.markdown("---")
                        st.markdown("### 📊 엑셀 다운로드")
                        st.warning("⚠️ 엑셀 다운로드를 위해서는 응답에 표 형식의 데이터가 필요합니다. 마크다운 표가 포함된 응답을 생성해주세요.")
                        
                        # 표 형식 예시 제공
                        with st.expander("📋 표 형식 예시 보기"):
                            st.markdown("""
                            응답에 다음과 같은 마크다운 표가 포함되어야 합니다:
                            
                            ```
                            | 장애ID | 서비스명 | 장애등급 | 발생일자 | 시간대 |
                            |--------|----------|----------|----------|--------|
                            | INM123 | ERP | 2등급 | 2025-01-15 | 주간 |
                            ```
                            """)
                    
                    if self.debug_mode:
                        print(f"UI_DEBUG: 엑셀 다운로드 버튼 표시 {'성공' if success else '실패'}")
                        
                except ImportError as e:
                    if self.debug_mode:
                        print(f"UI_DEBUG: ExcelDownloadManager import 실패: {str(e)}")
                    st.error("엑셀 다운로드 모듈을 불러올 수 없습니다. excel_utils.py 파일을 확인해주세요.")
                    
                except Exception as e:
                    if self.debug_mode:
                        print(f"UI_DEBUG: 엑셀 다운로드 기능 오류: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    
                    # 에러 발생 시에도 사용자에게 안내
                    st.markdown("---")
                    st.markdown("### 📊 엑셀 다운로드")
                    st.error(f"엑셀 다운로드 기능에 오류가 발생했습니다: {str(e)}")
                    st.info("💡 데이터를 복사하여 엑셀에 직접 붙여넣기 해주세요.")

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
        """채팅 메시지 표시 - 디자인 템플릿 유지 (후진 호환성 보장)"""
        with st.container():
            for msg_idx, message in enumerate(st.session_state.messages):
                with st.chat_message(message["role"]):
                    if message["role"] == "assistant":
                        # 새로운 메시지 구조 확인 (후진 호환성 유지)
                        query_type = message.get("query_type", "general")
                        rendered_content = message.get("rendered_content")
                        content = message["content"]
                        
                        # 새로운 구조의 메시지인 경우
                        if rendered_content and isinstance(rendered_content, dict):
                            if rendered_content.get("type") == "repair":
                                # repair 타입은 전용 디자인으로 표시
                                incidents_data = rendered_content.get("data")
                                if incidents_data:
                                    try:
                                        self.display_repair_report_with_tabs(incidents_data, use_typewriter=False, message_index=msg_idx)
                                        continue
                                    except Exception as e:
                                        # 오류 시 기본 표시로 폴백
                                        print(f"repair 디스플레이 오류: {e}")
                            elif rendered_content.get("type") == "text":
                                # 기타 텍스트 타입
                                content = rendered_content.get("content", content)
                                query_type = rendered_content.get("query_type", query_type)
                        
                        # repair 응답인지 확인 (기존 메시지 처리)
                        if query_type == "repair" and not rendered_content:
                            # 기존 repair 메시지를 파싱해서 디자인 적용
                            try:
                                incidents_data = self._parse_repair_response_to_incidents_data(content)
                                if incidents_data:
                                    self.display_repair_report_with_tabs(incidents_data, use_typewriter=False, message_index=msg_idx)
                                    continue
                            except Exception as e:
                                print(f"기존 repair 메시지 파싱 오류: {e}")
                        
                        # 기본 처리 (CAUSE_BOX 등)
                        self._display_content_with_markers(content, query_type)
                    else: 
                        st.write(message["content"])
    
    def _display_content_with_markers(self, content, query_type):
        """컨텐츠를 마커에 따라 적절히 표시"""
        html_converted = False
        
        # repair 타입 자동 감지 (기존 메시지 처리용)
        if not query_type or query_type == "general":
            if self._is_repair_response(content):
                query_type = "repair"
                # repair 응답을 파싱해서 전용 디자인으로 표시
                try:
                    incidents_data = self._parse_repair_response_to_incidents_data(content)
                    if incidents_data:
                        self.display_repair_report_with_tabs(incidents_data, use_typewriter=False)
                        return
                except Exception as e:
                    print(f"repair 응답 파싱 실패: {e}")
        
        # CAUSE_BOX 처리
        if '[CAUSE_BOX_START]' in content:
            content, has_html = self.convert_cause_box_to_html(content)
            html_converted = html_converted or has_html
        
        # HTML이 포함된 경우 또는 특수 디자인이 필요한 경우
        if html_converted or ('<div style=' in content and ('장애원인' in content or '복구방법' in content)):
            st.markdown(content, unsafe_allow_html=True)
        else: 
            st.write(content)
    
    def _is_repair_response(self, content):
        """repair 타입 응답인지 감지"""
        if not content:
            return False
        
        # repair 응답의 특징적인 패턴들
        repair_indicators = [
            '📋 장애내역 복구방법',
            '📋 이상징후내역 복구방법', 
            '복구방법 1',
            '복구방법 2',
            '복구방법 3',
            '종합 복구 방법',
            '통합 복구 방법'
        ]
        
        return any(indicator in content for indicator in repair_indicators)
    
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
    def format_output_type1(self, incident_data):
        """안 1: 간결한 3단계 구조 형식으로 포맷팅"""
        output = []
        
        # 헤더 정보
        output.append("=" * 80)
        output.append("                          장애 분석 보고서")
        output.append("=" * 80)
        output.append("")
        
        # 기본 정보
        if incident_id := incident_data.get('incident_id'):
            output.append(f"📋 장애 ID: {incident_id}")
        if service := incident_data.get('service'):
            output.append(f"🔧 서비스: {service}")
        if severity := incident_data.get('severity'):
            output.append(f"⚠️  등급: {severity}")
        if timestamp := incident_data.get('timestamp'):
            output.append(f"🕐 발생시간: {timestamp}")
        if time_period := incident_data.get('time_period'):
            output.append(f"🌓 시간대: {time_period}")
        if duration := incident_data.get('duration'):
            output.append(f"⏱️  장애시간: {duration}")
        if day_of_week := incident_data.get('day_of_week'):
            output.append(f"📅 요일: {day_of_week}")
        if department := incident_data.get('department'):
            output.append(f"👥 담당부서: {department}")
        
        output.append("")
        output.append("-" * 80)
        output.append("")
        
        # 1단계: 요약
        if summary := incident_data.get('summary'):
            output.append("【 1단계: 장애 요약 】")
            output.append("")
            output.append(f"  {summary}")
            output.append("")
        
        # 2단계: 상세 분석
        output.append("【 2단계: 상세 분석 】")
        output.append("")
        
        if cause := incident_data.get('cause'):
            output.append(f"  🔍 원인: {cause}")
        if detailed_cause := incident_data.get('detailed_cause'):
            output.append(f"  📝 상세원인: {detailed_cause}")
        if impact := incident_data.get('impact'):
            output.append(f"  💥 영향: {impact}")
        if failure_status := incident_data.get('failure_status'):
            output.append(f"  ❌ 장애상태: {failure_status}")
        
        output.append("")
        
        # 3단계: 조치 및 계획
        output.append("【 3단계: 조치 및 개선 】")
        output.append("")
        
        if recovery := incident_data.get('recovery'):
            output.append(f"  ✅ 복구방법: {recovery}")
        if recovery_method := incident_data.get('recovery_method'):
            output.append(f"  🔧 복구절차: {recovery_method}")
        if followup := incident_data.get('followup'):
            output.append(f"  📈 후속조치: {followup}")
        if improvement_plan := incident_data.get('improvement_plan'):
            output.append(f"  💡 개선계획: {improvement_plan}")
        if improvement_detail := incident_data.get('improvement_detail'):
            output.append(f"  📋 개선상세: {improvement_detail}")
        if fix_type := incident_data.get('fix_type'):
            output.append(f"  🔨 처리유형: {fix_type}")
        
        output.append("")
        output.append("=" * 80)
        
        return "\n".join(output)
    
    def display_incident_report_type1(self, incident_data, use_typewriter=True, duration=10.0):
        """안 1: 간결한 3단계 구조 형식으로 장애 분석 보고서 출력
        
        Args:
            incident_data: 장애 데이터 딕셔너리
            use_typewriter: 타이핑 효과 사용 여부 (기본값: True)
            duration: 타이핑 효과 전체 지속 시간 (초, 기본값: 10.0)
        """
        import time
        
        # 포맷팅된 텍스트 생성
        formatted_text = self.format_output_type1(incident_data)
        
        if use_typewriter:
            # 타이핑 효과로 출력
            placeholder = st.empty()
            text_length = len(formatted_text)
            chars_per_second = text_length / duration
            
            displayed_text = ""
            for i, char in enumerate(formatted_text):
                displayed_text += char
                placeholder.code(displayed_text, language='text')
                
                # 지연 시간 계산 (초 단위)
                if i < len(formatted_text) - 1:
                    time.sleep(1.0 / chars_per_second)
        else:
            # 즉시 출력
            st.code(formatted_text, language='text')