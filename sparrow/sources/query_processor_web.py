import streamlit as st
import re
from config.prompts_web import SystemPrompts
from config.settings_web import AppConfig
from utils.ui_components_web import UIComponents
from utils.internet_search_web import InternetSearchManager

class QueryProcessor:
    """웹 검색 기반 쿼리 처리 관리 클래스 (DEBUG 모드 지원, IT 관련 질문만 처리, 세션 분리 지원)"""
    
    def __init__(self, azure_openai_client, model_name, config=None, session_key="web_chatbot"):
        self.azure_openai_client = azure_openai_client
        self.model_name = model_name
        # config가 전달되지 않으면 새로 생성
        self.config = config if config else AppConfig()
        self.ui_components = UIComponents()
        self.internet_search = InternetSearchManager(self.config)
        self.debug_mode = getattr(config, 'debug_mode', False)
        
        # 웹 버전 전용 세션 키 설정
        self.session_key = session_key
        self.messages_key = f"{session_key}_messages"
    
    def is_it_related_query(self, query):
        """LLM을 사용하여 질문이 IT/전산/시스템 관련인지 판단"""
        try:
            validation_prompt = f"""
다음 사용자 질문이 IT/전산/시스템/기술 관련 질문인지 판단해주세요.

**IT 관련 질문 카테고리:**
- 컴퓨터, 서버, 네트워크, 데이터베이스 관련
- 소프트웨어, 애플리케이션, 웹서비스 관련  
- 프로그래밍, 개발, 배포 관련
- 클라우드, 인프라, 보안 관련
- 시스템 장애, 문제 해결, 설정 관련
- 기술 지원, 트러블슈팅 관련

**IT와 무관한 질문 예시:**
- 연예인, 연예계 소식
- 주식, 투자, 금융 정보
- 요리, 레시피, 음식
- 여행, 관광지 정보
- 스포츠, 게임(전자게임 제외)
- 의료, 건강 상담
- 법률, 정치 관련
- 일반 상식, 교육 내용

**사용자 질문:** {query}

**응답 형식:** 
- IT 관련 질문인 경우: "YES"
- IT와 무관한 질문인 경우: "NO"

반드시 "YES" 또는 "NO"만 출력하세요.
"""

            response = self.azure_openai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "당신은 질문을 분류하는 전문가입니다. 주어진 질문이 IT/전산/시스템 기술 관련인지 정확히 판단해주세요."},
                    {"role": "user", "content": validation_prompt}
                ],
                temperature=0.1,
                max_tokens=10
            )
            
            result = response.choices[0].message.content.strip().upper()
            
            # DEBUG 모드에서만 판단 결과 표시
            if self.debug_mode:
                st.info(f"🔍 DEBUG: IT 관련성 판단 결과 - {result}")
            
            return result == "YES"
            
        except Exception as e:
            if self.debug_mode:
                st.warning(f"IT 관련성 판단 실패, 기본값 사용: {str(e)}")
            # 판단 실패 시 안전하게 IT 관련으로 간주
            return True

    def show_non_it_response(self, query):
        """IT 관련이 아닌 질문에 대한 안내 메시지 표시"""
        non_it_response = f"""
🚫 **IT 기술 지원 전용 서비스입니다**

죄송합니다. 이 서비스는 **IT/전산/시스템 기술 문제**에 대한 전문 지원만 제공합니다.

**지원 가능한 분야:**
• 🖥️ 컴퓨터, 서버, 네트워크 문제
• 💾 데이터베이스, 소프트웨어 관련
• 🌐 웹서비스, API, 클라우드 서비스  
• 🔧 시스템 장애, 설정, 트러블슈팅
• 💻 프로그래밍, 개발 환경 문제
• 🔒 보안, 인프라 관련 문의

**IT 기술 관련 질문 예시:**
• "웹서버 접속불가 해결방법 알려줘"
• "데이터베이스 연결오류 원인이 뭐야?"  
• "Docker 컨테이너 설정 방법은?"
• "API 응답지연 문제 해결책은?"

IT 기술 관련 질문으로 다시 문의해주시기 바랍니다.
"""
        
        with st.chat_message("assistant"):
            st.write(non_it_response)
        
        # 웹 버전 전용 세션에 거부 메시지 저장
        st.session_state[self.messages_key].append({"role": "assistant", "content": non_it_response})

    def classify_query_type_with_llm(self, query):
        """LLM을 사용하여 쿼리 타입을 자동으로 분류"""
        try:
            classification_prompt = f"""
다음 사용자 질문을 분석하여 적절한 카테고리를 선택해주세요.

**분류 기준:**
1. **repair**: 문제 해결방법, 복구방법, 수리방법을 요청하는 문의
   - 예: "접속불가 해결방법", "오류 수정 방법", "시스템 복구하는 방법"
   
2. **cause**: 장애원인, 문제원인 분석이나 원인 파악을 요청하는 문의
   - 예: "접속불가 원인이 뭐야?", "왜 오류가 발생했어?", "문제 원인 분석"
   
3. **similar**: 유사사례, 비슷한 문제 사례를 요청하는 문의
   - 예: "비슷한 문제 사례", "유사한 오류 경험", "같은 현상 해결사례"
   
4. **default**: 그 외의 모든 경우 (일반 문의, 정보 요청 등)
   - 예: "설정 방법", "사용법", "개념 설명", "비교 분석"

**사용자 질문:** {query}

**응답 형식:** repair, cause, similar, default 중 하나만 출력하세요.
"""

            response = self.azure_openai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "당신은 IT 질문을 분류하는 전문가입니다. 주어진 질문을 정확히 분석하여 적절한 카테고리를 선택해주세요."},
                    {"role": "user", "content": classification_prompt}
                ],
                temperature=0.1,
                max_tokens=50
            )
            
            query_type = response.choices[0].message.content.strip().lower()
            
            # 유효한 타입인지 확인
            if query_type not in ['repair', 'cause', 'similar', 'default']:
                query_type = 'default'
                
            return query_type
            
        except Exception as e:
            if self.debug_mode:
                st.warning(f"쿼리 분류 실패, 기본값 사용: {str(e)}")
            return 'default'

    def extract_service_name_from_query(self, query):
        """쿼리에서 서비스명 추출 (간단한 패턴 기반)"""
        # 일반적인 서비스명 패턴들
        service_patterns = [
            r'([A-Za-z][A-Za-z0-9_\-/\+\(\)\s]*[A-Za-z0-9_\-/\+\)])\s+(?:장애|현상|복구|서비스|오류|문제)',
            r'서비스.*?([A-Za-z][A-Za-z0-9_\-/\+\(\)\s]*[A-Za-z0-9_\-/\+\)])',
            r'^([A-Za-z][A-Za-z0-9_\-/\+\(\)\s]*[A-Za-z0-9_\-/\+\)])\s+',
            r'["\']([A-Za-z][A-Za-z0-9_\-/\+\(\)\s]*[A-Za-z0-9_\-/\+\)])["\']',
            r'\(([A-Za-z][A-Za-z0-9_\-/\+\s]*[A-Za-z0-9_\-/\+])\)',
            r'\b([A-Za-z][A-Za-z0-9_\-/\+\(\)]{3,}(?:\s+[A-Za-z0-9_\-/\+\(\)]+)*)\b'
        ]
        
        for pattern in service_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            for match in matches:
                service_name = match.strip()
                if self.is_valid_service_name(service_name):
                    return service_name
        
        return None
    
    def is_valid_service_name(self, service_name):
        """서비스명이 유효한지 검증"""
        # 기본 조건: 최소 길이 체크
        if len(service_name) < 3:
            return False
        
        # 영문자로 시작해야 함
        if not service_name[0].isalpha():
            return False
        
        # 제외할 일반적인 단어들
        excluded_words = [
            'service', 'system', 'server', 'client', 'application', 'app',
            'website', 'web', 'platform', 'portal', 'interface', 'api',
            'database', 'data', 'file', 'log', 'error', 'issue', 'problem',
            'http', 'https', 'www', 'com', 'org', 'net',
            '장애', '현상', '복구', '통계', '발생'
        ]
        
        clean_name = re.sub(r'[\(\)/\+_\-\s]', '', service_name).lower()
        if clean_name in excluded_words:
            return False
        
        return True

    def _generate_web_search_response(self, query, target_service_name, query_type, type_labels):
        """웹 검색 기반 응답 생성 (DEBUG 모드 지원)"""
        try:
            # 웹 검색 수행
            search_spinner_text = "🔍 웹에서 관련 정보 검색 중..." if not self.debug_mode else "🔍 DEBUG: 웹에서 관련 정보 검색 중..."
            with st.spinner(search_spinner_text):
                # 쿼리 타입별 검색 설정 가져오기
                search_settings = self.config.get_search_quality_settings(query_type)
                
                # 웹 검색 실행
                search_results = self.internet_search.search_google(
                    query, 
                    service_name=target_service_name, 
                    num_results=search_settings['max_results']
                )
                
                if search_results:
                    # 검색 결과 품질 검증
                    reliability_assessment = self.internet_search.assess_search_reliability(search_results, query)
                    
                    # DEBUG 모드에서만 검색 결과 상세 표시
                    if self.debug_mode:
                        with st.expander(f"🔍 웹 검색 결과 ({len(search_results)}개)", expanded=False):
                            st.info(f"🎯 검색 키워드: {self.internet_search.extract_search_keywords(query, target_service_name)}")
                            st.markdown("---")
                            
                            for i, result in enumerate(search_results, 1):
                                st.markdown(f"#### 🔗 검색 결과 {i}")
                                st.markdown(f"**제목**: {result['title']}")
                                st.markdown(f"**출처**: {result['source']}")
                                st.markdown(f"**내용**: {result['snippet']}")
                                st.markdown(f"**링크**: [바로가기]({result['link']})")
                                if i < len(search_results):
                                    st.divider()
                    
                    # AI 답변 생성 및 표시
                    answer_spinner_text = "🤖 웹 검색 정보를 바탕으로 AI 답변 생성 중..." if not self.debug_mode else "🤖 DEBUG: AI 답변 생성 중..."
                    with st.spinner(answer_spinner_text):
                        internet_response = self.internet_search.generate_internet_search_response(
                            self.azure_openai_client, query, target_service_name, 
                            search_results, self.model_name, query_type
                        )
                        
                        # 답변 표시
                        with st.expander("🤖 AI 답변보기 (웹 검색 기반)", expanded=True):
                            st.write(internet_response)
                            search_purpose = self._get_search_purpose(query_type)
                            type_info = type_labels.get(query_type, '일반 문의')
                            
                            reliability_level = reliability_assessment['reliability_level']
                            if reliability_level == 'high':
                                st.success(f"🌐 이 답변은 신뢰할 만한 웹 소스를 바탕으로 한 **{type_info}** 형태의 전문 분석입니다.")
                            elif reliability_level == 'medium':
                                st.info(f"🌐 이 답변은 웹 검색 정보를 종합한 **{type_info}** 형태의 분석입니다.")
                            else:
                                st.warning(f"🌐 이 답변은 제한적인 웹 정보를 일반적인 IT 지식으로 보완한 **{type_info}** 형태의 분석입니다.")
                        
                        # 웹 버전 전용 세션에 답변 저장
                        search_purpose = self._get_search_purpose(query_type)
                        final_response = f"""
**[🌐 웹 검색 기반 {search_purpose}]**

{internet_response}

※ 이 답변은 웹 검색 정보를 바탕으로 생성되었으며, 실제 환경에 적용 시 해당 시스템의 특성을 고려하시기 바랍니다.
"""
                        st.session_state[self.messages_key].append({"role": "assistant", "content": final_response})
                        
                else:
                    # 검색 결과 없을 때
                    if self.debug_mode:
                        st.warning("🌐 DEBUG: 관련 웹 정보를 찾을 수 없습니다.")
                    else:
                        st.info("🌐 관련 웹 정보를 찾을 수 없어 일반적인 IT 지식으로 답변드립니다.")
                    
                    # 검색 결과 없음에도 일반적인 답변 제공
                    with st.spinner("🤖 일반적인 IT 지식으로 답변 생성 중..."):
                        general_response = self._generate_fallback_response(query, query_type, type_labels)
                        
                        with st.expander("🤖 AI 답변보기 (일반 IT 지식)", expanded=True):
                            st.write(general_response)
                            search_purpose = self._get_search_purpose(query_type)
                            type_info = type_labels.get(query_type, '일반 문의')
                            st.info(f"🌐 이 답변은 일반적인 IT 전문가 지식을 바탕으로 한 **{type_info}** 형태의 분석입니다.")
                            st.warning("⚠️ 구체적인 환경 정보와 함께 문의하시면 더 정확한 답변을 드릴 수 있습니다.")
                    
                    # 일반적인 답변도 웹 버전 전용 세션에 저장
                    search_purpose = self._get_search_purpose(query_type)
                    no_results_response = f"""
**[🌐 일반 IT 지식 기반 {search_purpose}]**

{general_response}

※ 웹 검색 정보 부족으로 일반적인 IT 전문가 지식을 바탕으로 제공되었습니다.
※ 구체적인 환경 정보와 함께 문의하시면 더 정확한 답변을 드릴 수 있습니다.
"""
                    st.session_state[self.messages_key].append({"role": "assistant", "content": no_results_response})
                    
        except Exception as e:
            if self.debug_mode:
                st.error(f"🌐 DEBUG: 웹 검색 중 오류가 발생했습니다: {str(e)}")
            else:
                st.error("🌐 웹 검색 중 오류가 발생했습니다. 잠시 후 다시 시도해보세요.")
            
            # 오류 발생 시에도 일반적인 답변 시도
            try:
                with st.spinner("🤖 일반적인 IT 지식으로 답변 생성 중..."):
                    error_response = self._generate_fallback_response(query, query_type, type_labels)
                    
                    with st.expander("🤖 AI 답변보기 (일반 IT 지식)", expanded=True):
                        st.write(error_response)
                        st.warning("⚠️ 웹 검색 오류로 인해 일반적인 IT 지식으로만 답변드립니다.")
                
                # 오류 시 일반 답변도 웹 버전 전용 세션에 저장
                search_purpose = self._get_search_purpose(query_type)
                error_fallback_response = f"""
**[🌐 일반 IT 지식 기반 {search_purpose}]**

{error_response}

※ 웹 검색 중 오류가 발생하여 일반적인 IT 전문가 지식으로 답변드렸습니다.
※ 구체적인 환경 정보와 함께 재문의하시면 더 정확한 답변을 드릴 수 있습니다.
"""
                st.session_state[self.messages_key].append({"role": "assistant", "content": error_fallback_response})
                
            except Exception as inner_e:
                # 일반 답변 생성도 실패한 경우
                final_error_response = f"""
**[🌐 웹 검색 오류]**

⚠️ **정보가 부족하여 일반적인 내용으로 답변드립니다.**

웹 검색 중 오류가 발생했습니다.

**일반적인 IT 문제 해결 접근법:**
1. **문제 상황 정확히 파악**: 오류 메시지, 로그, 발생 시점 확인
2. **기본 점검**: 네트워크 연결, 서비스 상태, 리소스 사용량 확인  
3. **단계적 진단**: 간단한 해결책부터 복잡한 방법까지 순차 적용
4. **전문가 상담**: 복잡한 문제는 해당 분야 전문가와 협의

※ 구체적인 환경 정보와 함께 다시 문의하시면 더 정확한 답변을 드릴 수 있습니다.
"""
                st.session_state[self.messages_key].append({"role": "assistant", "content": final_error_response})

    def _generate_fallback_response(self, query, query_type, type_labels):
        """웹 검색 실패 시 일반적인 IT 지식 기반 답변 생성"""
        try:
            system_prompt = SystemPrompts.get_prompt(query_type)
            
            user_prompt = f"""
웹 검색 정보가 없어 일반적인 IT 전문가 지식을 바탕으로 답변해주세요:

질문: {query}

답변 요구사항:
1. 일반적인 IT 원칙과 모범 사례 중심으로 답변
2. 주요 포인트는 **굵은 글씨**로 강조
3. 실무에서 적용 가능한 단계적 접근법 제시
4. 추가 확인이 필요한 사항들 명시
5. 답변 마지막에 "※ 이 답변은 일반적인 IT 지식을 바탕으로 생성되었습니다." 추가

답변:"""

            response = self.azure_openai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            error_detail = str(e) if self.debug_mode else "처리 중 오류가 발생했습니다"
            return f"""⚠️ **일반적인 IT 문제 해결 접근법:**

죄송합니다. 답변 생성 중 오류가 발생했습니다: {error_detail}

**기본적인 문제 해결 단계:**
1. **문제 상황 파악**: 정확한 오류 메시지와 발생 조건 확인
2. **기본 점검**: 시스템 상태, 네트워크 연결, 서비스 상태 확인
3. **로그 분석**: 관련 로그 파일에서 오류 원인 추적
4. **단계적 해결**: 간단한 방법부터 복잡한 해결책까지 순차 적용
5. **문서화**: 해결 과정과 결과를 기록하여 향후 참조

※ 구체적인 환경 정보와 함께 다시 문의하시기 바랍니다."""

    def _get_search_purpose(self, query_type):
        """쿼리 타입에 따른 검색 목적 반환"""
        purposes = {
            'repair': '해결방법',
            'cause': '원인분석',
            'similar': '유사사례',
            'default': '관련정보'
        }
        return purposes.get(query_type, purposes['default'])

    def process_query(self, query, query_type=None):
        """웹 검색 기반 쿼리 처리 (IT 관련 질문만 처리, DEBUG 모드 지원, 세션 분리)"""
        with st.chat_message("assistant"):
            # 1단계: IT 관련 질문인지 먼저 확인
            validation_spinner_text = "🔍 질문 유형 검증 중..." if not self.debug_mode else "🔍 DEBUG: IT 관련성 검증 중..."
            with st.spinner(validation_spinner_text):
                if not self.is_it_related_query(query):
                    # IT 관련이 아닌 경우 거부 메시지 표시 후 처리 중단
                    self.show_non_it_response(query)
                    return
            
            # IT 관련 질문으로 확인됨 - 기존 처리 로직 계속 진행
            if self.debug_mode:
                st.success("✅ DEBUG: IT 관련 질문으로 확인됨")

            # LLM 기반 쿼리 타입 자동 분류
            if query_type is None:
                classify_spinner_text = "🤖 질문 유형 분석 중..." if not self.debug_mode else "🤖 DEBUG: 질문 유형 분석 중..."
                with st.spinner(classify_spinner_text):
                    query_type = self.classify_query_type_with_llm(query)
                    
                    # 분류 결과 표시
                    type_labels = {
                        'repair': '🔧 문제 해결방법',
                        'cause': '🔍 원인 분석',
                        'similar': '📄 유사사례 참조', 
                        'default': '📋 일반 문의'
                    }
                    
                    # DEBUG 모드에서만 상세 분류 정보 표시
                    if self.debug_mode:
                        st.info(f"📋 DEBUG: 질문 유형 분석 결과 - **{type_labels.get(query_type, '📋 일반 문의')}**")
            else:
                type_labels = {
                    'repair': '🔧 문제 해결방법',
                    'cause': '🔍 원인 분석',
                    'similar': '📄 유사사례 참조', 
                    'default': '📋 일반 문의'
                }
            
            # 서비스명 추출
            target_service_name = self.extract_service_name_from_query(query)
            
            if target_service_name:
                if self.debug_mode:
                    st.success(f"🎯 DEBUG: 감지된 대상 서비스 - **{target_service_name}**")
            
            # SerpApi 설정 확인
            if not self.internet_search.is_available():
                st.error("🌐 SerpApi 키가 설정되지 않았습니다.")
                st.info("웹 검색 기능을 사용하려면 .env 파일에 SERPAPI_API_KEY를 설정해주세요.")
                
                # SerpApi 없이도 일반적인 답변 제공
                with st.spinner("🤖 일반적인 IT 지식으로 답변 생성 중..."):
                    fallback_response = self._generate_fallback_response(query, query_type, type_labels)
                    
                    with st.expander("🤖 AI 답변보기 (일반 IT 지식)", expanded=True):
                        st.write(fallback_response)
                        search_purpose = self._get_search_purpose(query_type)
                        type_info = type_labels.get(query_type, '일반 문의')
                        st.warning(f"⚠️ 웹 검색 불가로 일반적인 IT 지식을 바탕으로 한 **{type_info}** 형태의 답변입니다.")
                
                # 답변 웹 버전 전용 세션에 저장
                search_purpose = self._get_search_purpose(query_type)
                no_serpapi_response = f"""
**[🌐 일반 IT 지식 기반 {search_purpose}]**

{fallback_response}

※ SerpApi 설정이 없어 웹 검색을 사용할 수 없습니다.
※ 웹 검색 기능을 사용하려면 SERPAPI_API_KEY를 설정해주세요.
"""
                st.session_state[self.messages_key].append({"role": "assistant", "content": no_serpapi_response})
                return
            
            # 웹 검색 기반 응답 생성
            self._generate_web_search_response(query, target_service_name, query_type, type_labels)