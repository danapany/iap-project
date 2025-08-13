import streamlit as st
from config.prompts import SystemPrompts
from config.settings import AppConfig
from utils.search_utils import SearchManager
from utils.ui_components import UIComponents
from utils.internet_search import InternetSearchManager

class QueryProcessor:
    """쿼리 처리 관리 클래스"""
    
    def __init__(self, azure_openai_client, search_client, model_name, config=None):
        self.azure_openai_client = azure_openai_client
        self.search_client = search_client
        self.model_name = model_name
        # config가 전달되지 않으면 새로 생성
        self.config = config if config else AppConfig()
        self.search_manager = SearchManager(search_client, self.config)
        self.ui_components = UIComponents()
        self.internet_search = InternetSearchManager(self.config)
    
    def classify_query_type_with_llm(self, query):
        """LLM을 사용하여 쿼리 타입을 자동으로 분류"""
        try:
            classification_prompt = f"""
다음 사용자 질문을 분석하여 적절한 카테고리를 선택해주세요.

**분류 기준:**
1. **repair**: 서비스명과 장애현상이 모두 포함된 복구방법 문의
   - 예: "ERP 접속불가 복구방법", "API_Link 응답지연 해결방법"
   
2. **cause**: 장애원인 분석이나 원인 파악을 요청하는 문의
   - 예: "ERP 접속불가 원인이 뭐야?", "API 응답지연 장애원인", "왜 장애가 발생했어?"
   
3. **similar**: 서비스명 없이 장애현상만으로 유사사례 문의
   - 예: "접속불가 현상 유사사례", "응답지연 동일현상 복구방법"
   
4. **default**: 그 외의 모든 경우 (통계, 건수, 일반 문의 등)
   - 예: "년도별 건수", "장애 통계", "서비스 현황"

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
            st.warning(f"쿼리 분류 실패, 기본값 사용: {str(e)}")
            return 'default'

    def generate_rag_response_with_accurate_count(self, query, documents, query_type="default"):
        """개선된 RAG 응답 생성 - 정확한 집계 정보 포함"""
        try:
            # 문서 개수 및 년도별 집계 미리 계산
            total_count = len(documents)
            yearly_stats = {}
            
            # 년도별 집계 계산
            for doc in documents:
                # error_date에서 년도 추출 (YYYY-MM-DD 형태)
                error_date = doc.get('error_date', '')
                year_from_date = None
                if error_date and len(error_date) >= 4:
                    try:
                        year_from_date = int(error_date[:4])
                    except:
                        pass
                
                # year 필드도 확인
                year_from_field = doc.get('year', '')
                if year_from_field:
                    try:
                        year_from_field = int(year_from_field)
                    except:
                        year_from_field = None
                
                # 우선순위: error_date > year 필드
                final_year = year_from_date or year_from_field
                
                if final_year:
                    yearly_stats[final_year] = yearly_stats.get(final_year, 0) + 1
            
            # 집계 검증
            yearly_total = sum(yearly_stats.values())
            
            # 검색된 문서들을 컨텍스트로 구성 (품질 정보 + 집계 정보 포함)
            context_parts = []
            
            # 집계 정보를 컨텍스트 상단에 추가
            stats_info = f"""
=== 정확한 집계 정보 ===
전체 문서 수: {total_count}건
년도별 분포: {dict(sorted(yearly_stats.items()))}
년도별 합계: {yearly_total}건
집계 검증: {'일치' if yearly_total == total_count else '불일치 - 재계산 필요'}
===========================
"""
            context_parts.append(stats_info)
            
            for i, doc in enumerate(documents):
                final_score = doc.get('final_score', 0)
                quality_tier = doc.get('quality_tier', 'Standard')
                filter_reason = doc.get('filter_reason', '기본 선별')
                service_match_type = doc.get('service_match_type', 'unknown')
                
                context_part = f"""문서 {i+1} [{quality_tier}급 - {filter_reason} - {service_match_type} 매칭]:
장애 ID: {doc['incident_id']}
서비스명: {doc['service_name']}
장애시간: {doc['error_time']}
영향도: {doc['effect']}
현상: {doc['symptom']}
복구공지: {doc['repair_notice']}
발생일자: {doc['error_date']}
요일: {doc['week']}
시간대: {doc['daynight']}
장애원인: {doc['root_cause']}
복구방법: {doc['incident_repair']}
개선계획: {doc['incident_plan']}
원인유형: {doc['cause_type']}
처리유형: {doc['done_type']}
장애등급: {doc['incident_grade']}
담당부서: {doc['owner_depart']}
년도: {doc['year']}
월: {doc['month']}
품질점수: {final_score:.2f}
"""
                context_parts.append(context_part)
            
            context = "\n\n".join(context_parts)
            
            # 질문 타입에 따른 시스템 프롬프트 선택
            system_prompt = SystemPrompts.get_prompt(query_type)

            user_prompt = f"""
다음 장애 이력 문서들을 참고하여 질문에 답변해주세요.
(모든 문서는 서비스명 포함 매칭 + 동적 임계값 기반 고품질 필터링을 통과한 검색 결과입니다):

중요! 집계 관련 질문인 경우 위의 "정확한 집계 정보" 섹션을 참조하여 정확한 숫자를 제공하세요.
- 전체 건수: {total_count}건
- 년도별 건수: {dict(sorted(yearly_stats.items()))}
- 반드시 년도별 합계가 전체 건수와 일치하는지 확인하세요.

{context}

질문: {query}

답변:"""

            # Azure OpenAI API 호출
            response = self.azure_openai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,  # 정확한 집계를 위해 temperature 낮춤
                max_tokens=1500
            )
            
            return response.choices[0].message.content
        
        except Exception as e:
            st.error(f"응답 생성 실패: {str(e)}")
            return "죄송합니다. 응답을 생성하는 중 오류가 발생했습니다."

    def process_query(self, query, query_type=None):
        """서비스명 포함 검색을 지원하는 개선된 쿼리 처리"""
        with st.chat_message("assistant"):
            # LLM 기반 쿼리 타입 자동 분류
            if query_type is None:
                with st.spinner("🤖 질문 유형 분석 중..."):
                    query_type = self.classify_query_type_with_llm(query)
                    
                    # 분류 결과 표시
                    type_labels = {
                        'repair': '🔧 복구방법 안내',
                        'cause': '🔍 장애원인 분석',
                        'similar': '📄 유사사례 참조', 
                        'default': '📊 일반 문의'
                    }
                    st.info(f"📋 질문 유형: **{type_labels.get(query_type, '📊 일반 문의')}**")
            else:
                type_labels = {
                    'repair': '🔧 복구방법 안내',
                    'cause': '🔍 장애원인 분석',
                    'similar': '📄 유사사례 참조', 
                    'default': '📊 일반 문의'
                }
            
            # 서비스명 추출
            target_service_name = self.search_manager.extract_service_name_from_query(query)
            
            if target_service_name:
                st.success(f"🎯 감지된 대상 서비스: **{target_service_name}** (정확/포함 매칭 모두 지원)")
            
            with st.spinner("🎯 서비스명 포함 매칭 + 동적 임계값 기반 고품질 검색 중..."):
                # 개선된 검색 함수 호출
                documents = self.search_manager.semantic_search_with_service_filter(
                    query, target_service_name, query_type
                )
                
                if documents:
                    # 서비스명 매칭 검증 및 분류
                    exact_matches = [doc for doc in documents if doc.get('service_match_type') == 'exact']
                    partial_matches = [doc for doc in documents if doc.get('service_match_type') == 'partial']
                    
                    if exact_matches and partial_matches:
                        st.success(f"✅ '{target_service_name}' 서비스: 정확 매칭 {len(exact_matches)}개, 포함 매칭 {len(partial_matches)}개")
                    elif exact_matches:
                        st.success(f"✅ '{target_service_name}' 서비스: 정확 매칭 {len(exact_matches)}개")
                    elif partial_matches:
                        st.info(f"📋 '{target_service_name}' 서비스: 포함 매칭 {len(partial_matches)}개")
                    elif target_service_name:
                        st.info(f"📋 '{target_service_name}' 관련 {len(documents)}개 문서가 선별되었습니다.")
                    
                    premium_count = sum(1 for doc in documents if doc.get('quality_tier') == 'Premium')
                    standard_count = sum(1 for doc in documents if doc.get('quality_tier') == 'Standard')
                    basic_count = sum(1 for doc in documents if doc.get('quality_tier') == 'Basic')
                    
                    # 집계 관련 질문인지 확인
                    is_count_query = any(keyword in query.lower() for keyword in ['건수', '개수', '몇건', '년도별', '월별', '통계', '현황'])
                    
                    # 집계 미리보기 (집계 관련 질문인 경우)
                    if is_count_query:
                        yearly_stats = {}
                        for doc in documents:
                            error_date = doc.get('error_date', '')
                            year_from_date = None
                            if error_date and len(error_date) >= 4:
                                try:
                                    year_from_date = int(error_date[:4])
                                except:
                                    pass
                            
                            year_from_field = doc.get('year', '')
                            if year_from_field:
                                try:
                                    year_from_field = int(year_from_field)
                                except:
                                    year_from_field = None
                            
                            final_year = year_from_date or year_from_field
                            if final_year:
                                yearly_stats[final_year] = yearly_stats.get(final_year, 0) + 1
                        
                        yearly_total = sum(yearly_stats.values())
                        st.info(f"""
                        📊 **집계 미리보기**
                        - 전체 건수: {len(documents)}건
                        - 년도별 분포: {dict(sorted(yearly_stats.items()))}
                        - 년도별 합계: {yearly_total}건
                        - 검증 상태: {'✅ 일치' if yearly_total == len(documents) else '⚠ 불일치'}
                        """)
                    
                    st.success(f"🏆 {len(documents)}개의 매칭 문서 선별 완료! (Premium: {premium_count}개, Standard: {standard_count}개, Basic: {basic_count}개)")
                    
                    # 검색된 문서 표시
                    with st.expander("🔍 매칭된 문서 보기"):
                        self.ui_components.display_documents_with_quality_info(documents)
                    
                    # RAG 응답 생성
                    with st.spinner("💡 포함 매칭 기반 답변 생성 중..."):
                        response = self.generate_rag_response_with_accurate_count(
                            query, documents, query_type
                        )
                        
                        with st.expander("🤖 AI 답변 보기 (포함 매칭 지원)", expanded=True):
                            st.write(response)
                            match_info = "정확/포함 매칭" if exact_matches and partial_matches else "정확 매칭" if exact_matches else "포함 매칭"
                            type_info = type_labels.get(query_type, '일반 문의')
                            st.info(f"✨ 이 답변은 '{target_service_name or '모든 서비스'}'에 {match_info}된 문서를 바탕으로 **{type_info}** 형태로 생성되었습니다.")
                            
                            # 모든 쿼리 타입에서 인터넷 검색 버튼 추가
                            if self.internet_search.is_available():
                                st.markdown("---")
                                
                                # 버튼 클릭 상태를 세션에서 확인
                                search_button_key = f"internet_search_{hash(query)}"
                                
                                col1, col2, col3 = st.columns([1, 2, 1])
                                with col2:
                                    # 쿼리 타입에 따른 버튼 텍스트 변경
                                    button_text = self._get_internet_search_button_text(query_type)
                                    if st.button(button_text, 
                                               key=search_button_key,
                                               help="구글 검색을 통해 추가적인 정보를 찾아보세요"):
                                        # 버튼 클릭 시 세션 상태 저장
                                        st.session_state[f"show_search_modal_{search_button_key}"] = True
                                        st.session_state[f"search_query_{search_button_key}"] = query
                                        st.session_state[f"search_service_{search_button_key}"] = target_service_name
                                        st.session_state[f"search_type_{search_button_key}"] = query_type
                                        st.rerun()
                        
                        # 팝업 모달 표시 체크
                        search_button_key = f"internet_search_{hash(query)}"
                        if st.session_state.get(f"show_search_modal_{search_button_key}", False):
                            self._display_search_modal(search_button_key, type_labels)
                        
                        st.session_state.messages.append({"role": "assistant", "content": response})
                else:
                    # 대체 검색 시도
                    st.warning("📄 포함 매칭으로도 결과가 없어 더 관대한 기준으로 재검색 중...")
                    
                    # 매우 관대한 기준으로 재검색 (서비스명 포함 필터링 유지)
                    fallback_documents = self.search_manager.search_documents_fallback(query, target_service_name)
                    
                    if fallback_documents:
                        st.info(f"📋 대체 검색으로 {len(fallback_documents)}개 문서 발견")
                        
                        response = self.generate_rag_response_with_accurate_count(
                            query, fallback_documents, query_type
                        )
                        with st.expander("🤖 AI 답변 보기 (대체 검색)", expanded=True):
                            st.write(response)
                            type_info = type_labels.get(query_type, '일반 문의')
                            st.warning(f"⚠️ 이 답변은 '{target_service_name or '해당 조건'}'에 대한 관대한 기준의 검색 결과를 바탕으로 **{type_info}** 형태로 생성되었습니다.")
                            
                            # repair 타입인 경우 대체 검색에서도 인터넷 검색 버튼 추가
                            if query_type == 'repair' and self.internet_search.is_available():
                                st.markdown("---")
                                
                                # 버튼 클릭 상태를 세션에서 확인
                                fallback_search_button_key = f"internet_search_fallback_{hash(query)}"
                                fallback_button_clicked = st.session_state.get(fallback_search_button_key, False)
                                
                                if not fallback_button_clicked:
                                    # 버튼이 아직 클릭되지 않은 경우 버튼 표시
                                    col1, col2, col3 = st.columns([1, 2, 1])
                                    with col2:
                                        if st.button("🌐 인터넷으로도 복구방법을 검색해볼까요?", 
                                                   key=fallback_search_button_key,
                                                   help="구글 검색을 통해 추가적인 복구방법을 찾아보세요"):
                                            # 버튼 클릭 시 세션 상태 업데이트하고 검색 실행
                                            st.session_state[fallback_search_button_key] = True
                                            st.rerun()
                                else:
                                    # 버튼이 클릭된 경우 검색 실행 (기존 답변 아래에 추가)
                                    self._perform_additional_internet_search_below(query, target_service_name, query_type, type_labels)
                        
                        st.session_state.messages.append({"role": "assistant", "content": response})
                    else:
                        # repair, cause 타입인 경우 인터넷 검색 시도
                        if query_type in ['repair', 'cause'] and self.internet_search.is_available():
                            st.info("🌐 내부 문서에서 관련 정보를 찾을 수 없어 인터넷 검색을 시도합니다...")
                            
                            with st.spinner("🔍 구글 검색으로 관련 정보 찾는 중..."):
                                # 인터넷 검색 실행
                                search_results = self.internet_search.search_google(query, target_service_name, num_results=5)
                                
                                if search_results:
                                    st.success(f"🌐 인터넷에서 {len(search_results)}개의 관련 정보를 찾았습니다!")
                                    
                                    # 검색 결과 표시
                                    with st.expander("🔍 인터넷 검색 결과 보기"):
                                        for i, result in enumerate(search_results, 1):
                                            st.markdown(f"### 🔗 검색 결과 {i}")
                                            st.markdown(f"**제목**: {result['title']}")
                                            st.markdown(f"**출처**: {result['source']}")
                                            st.markdown(f"**내용**: {result['snippet']}")
                                            st.markdown(f"**링크**: [바로가기]({result['link']})")
                                            st.markdown("---")
                                    
                                    # 인터넷 검색 기반 응답 생성
                                    with st.spinner("💡 인터넷 검색 결과를 바탕으로 답변 생성 중..."):
                                        internet_response = self.internet_search.generate_internet_search_response(
                                            self.azure_openai_client, query, target_service_name, 
                                            search_results, self.model_name, query_type
                                        )
                                        
                                        with st.expander("🤖 AI 답변 보기 (인터넷 검색 기반)", expanded=True):
                                            st.write(internet_response)
                                            type_info = type_labels.get(query_type, '일반 문의')
                                            st.info(f"🌐 이 답변은 구글 검색 결과를 바탕으로 **{type_info}** 형태로 생성되었습니다.")
                                        
                                        st.session_state.messages.append({"role": "assistant", "content": internet_response})
                                else:
                                    # 인터넷 검색도 실패한 경우
                                    self._show_no_results_message(target_service_name, query_type, type_labels)
                        else:
                            # repair, cause가 아니거나 인터넷 검색 불가능한 경우
                            if query_type in ['repair', 'cause'] and not self.internet_search.is_available():
                                st.warning("🌐 SerpApi가 설정되지 않아 인터넷 검색을 사용할 수 없습니다.")
                            
                            # 모든 타입에서 인터넷 검색 버튼 제공
                            if self.internet_search.is_available():
                                st.markdown("---")
                                col1, col2, col3 = st.columns([1, 2, 1])
                                with col2:
                                    no_result_search_key = f"no_result_search_{hash(query)}"
                                    button_text = self._get_internet_search_button_text(query_type)
                                    if st.button(button_text, 
                                               key=no_result_search_key,
                                               help="구글 검색을 통해 관련 정보를 찾아보세요"):
                                        # 버튼 클릭 시 세션 상태 저장
                                        st.session_state[f"show_search_modal_{no_result_search_key}"] = True
                                        st.session_state[f"search_query_{no_result_search_key}"] = query
                                        st.session_state[f"search_service_{no_result_search_key}"] = target_service_name
                                        st.session_state[f"search_type_{no_result_search_key}"] = query_type
                                        st.rerun()
                            
                            # 팝업 모달 표시 체크 (검색 실패 케이스)
                            no_result_search_key = f"no_result_search_{hash(query)}"
                            if st.session_state.get(f"show_search_modal_{no_result_search_key}", False):
                                self._display_search_modal(no_result_search_key, type_labels)
                            
                            self._show_no_results_message(target_service_name, query_type, type_labels)
    
    def _get_internet_search_button_text(self, query_type):
        """쿼리 타입에 따른 인터넷 검색 버튼 텍스트 반환"""
        button_texts = {
            'repair': '🌐 인터넷으로도 복구방법을 검색해볼까요?',
            'cause': '🌐 인터넷으로도 장애원인을 검색해볼까요?',
            'similar': '🌐 인터넷으로도 유사사례를 검색해볼까요?',
            'default': '🌐 인터넷으로도 관련정보를 검색해볼까요?'
        }
        return button_texts.get(query_type, button_texts['default'])
    
    def _perform_additional_internet_search_below(self, query, target_service_name, query_type, type_labels):
        """기존 답변 아래에 추가 인터넷 검색 결과를 표시"""
        try:
            # 새로운 assistant 메시지로 인터넷 검색 결과 추가
            with st.chat_message("assistant"):
                st.info("🔍 추가 인터넷 검색을 시작합니다...")
                
                with st.spinner("🔍 구글에서 추가 정보 검색 중..."):
                    # 인터넷 검색 실행
                    search_results = self.internet_search.search_google(query, target_service_name, num_results=5)
                    
                    if search_results:
                        st.success(f"🌐 인터넷에서 {len(search_results)}개의 추가 정보를 찾았습니다!")
                        
                        # 검색 결과 표시
                        with st.expander("🔍 인터넷 검색 결과 보기", expanded=True):
                            st.markdown("### 🌐 구글 검색 결과")
                            for i, result in enumerate(search_results, 1):
                                with st.container():
                                    st.markdown(f"#### 🔗 검색 결과 {i}")
                                    col1, col2 = st.columns([3, 1])
                                    with col1:
                                        st.markdown(f"**제목**: {result['title']}")
                                        st.markdown(f"**출처**: {result['source']}")
                                        st.markdown(f"**내용**: {result['snippet']}")
                                    with col2:
                                        st.markdown(f"[🔗 바로가기]({result['link']})")
                                    
                                    if i < len(search_results):
                                        st.divider()
                        
                        # 인터넷 검색 기반 AI 응답 생성
                        with st.expander("🤖 AI 추가 분석 (인터넷 검색 기반)", expanded=True):
                            with st.spinner("💡 검색 결과를 분석하여 추가 답변 생성 중..."):
                                internet_response = self.internet_search.generate_internet_search_response(
                                    self.azure_openai_client, query, target_service_name, 
                                    search_results, self.model_name, query_type
                                )
                                
                                # AI 답변 표시
                                search_purpose = self._get_search_purpose(query_type)
                                st.markdown(f"#### 🌐 인터넷 검색 기반 추가 {search_purpose}")
                                st.write(internet_response)
                                
                                # 정보 표시
                                type_info = type_labels.get(query_type, '일반 문의')
                                st.info(f"🌐 이 추가 답변은 구글 검색 결과를 바탕으로 **{type_info}** 형태로 생성되었습니다.")
                                st.success(f"✨ 위의 내부 문서 답변과 이 인터넷 검색 결과를 함께 참고하여 더 완전한 {search_purpose}을(를) 찾아보세요!")
                        
                        # 추가 답변을 세션에 저장
                        search_purpose = self._get_search_purpose(query_type)
                        additional_response = f"""
**[🌐 추가 인터넷 검색 기반 {search_purpose}]**

{internet_response}

※ 이 답변은 사용자 요청에 의한 추가 구글 검색 결과를 바탕으로 생성되었습니다.
"""
                        st.session_state.messages.append({"role": "assistant", "content": additional_response})
                        
                    else:
                        st.warning("🌐 인터넷에서 추가 정보를 찾을 수 없습니다.")
                        st.info("위의 내부 문서 답변을 참고하시거나, 다른 키워드로 다시 질문해보세요.")
                        
                        # 검색 실패도 기록
                        search_purpose = self._get_search_purpose(query_type)
                        no_result_response = f"""
**[🌐 추가 인터넷 검색 시도]**

죄송합니다. 해당 주제에 대한 추가 인터넷 정보를 찾을 수 없었습니다.
위의 내부 문서 답변을 참고해주세요.

※ 다른 키워드로 다시 질문하시면 더 나은 결과를 얻을 수 있습니다.
"""
                        st.session_state.messages.append({"role": "assistant", "content": no_result_response})
                        
        except Exception as e:
            with st.chat_message("assistant"):
                st.error(f"🌐 추가 인터넷 검색 중 오류가 발생했습니다: {str(e)}")
                st.info("위의 내부 문서 답변을 참고하시거나, 잠시 후 다시 시도해보세요.")
                
                # 오류도 기록
                error_response = f"""
**[🌐 추가 인터넷 검색 오류]**

추가 인터넷 검색 중 오류가 발생했습니다: {str(e)}
위의 내부 문서 답변을 참고해주세요.
"""
                st.session_state.messages.append({"role": "assistant", "content": error_response})
    
    def _perform_additional_internet_search_inline(self, query, target_service_name, query_type, type_labels):
        """인라인 추가 인터넷 검색 수행 (버튼 클릭 후 즉시 실행)"""
        try:
            # 검색 시작 알림
            with st.container():
                st.info("🔍 추가 인터넷 검색을 시작합니다...")
                
                with st.spinner("🔍 구글에서 추가 복구방법 검색 중..."):
                    # 인터넷 검색 실행
                    search_results = self.internet_search.search_google(query, target_service_name, num_results=5)
                    
                    if search_results:
                        st.success(f"🌐 인터넷에서 {len(search_results)}개의 추가 복구방법을 찾았습니다!")
                        
                        # 검색 결과 즉시 표시
                        st.markdown("### 🔍 추가 인터넷 검색 결과")
                        
                        # 각 검색 결과를 카드 형태로 표시
                        for i, result in enumerate(search_results, 1):
                            with st.container():
                                st.markdown(f"#### 🔗 검색 결과 {i}")
                                col1, col2 = st.columns([3, 1])
                                with col1:
                                    st.markdown(f"**제목**: {result['title']}")
                                    st.markdown(f"**출처**: {result['source']}")
                                    st.markdown(f"**내용**: {result['snippet']}")
                                with col2:
                                    st.markdown(f"[🔗 바로가기]({result['link']})")
                                
                                if i < len(search_results):
                                    st.divider()
                        
                        # 인터넷 검색 기반 AI 응답 생성
                        st.markdown("### 🤖 AI 추가 분석")
                        with st.spinner("💡 검색 결과를 분석하여 추가 답변 생성 중..."):
                            internet_response = self.internet_search.generate_internet_search_response(
                                self.azure_openai_client, query, target_service_name, 
                                search_results, self.model_name, query_type
                            )
                            
                            # AI 답변 표시
                            st.markdown("#### 🌐 인터넷 검색 기반 추가 정보")
                            st.write(internet_response)
                            
                            # 정보 표시
                            type_info = type_labels.get(query_type, '일반 문의')
                            search_purpose = self._get_search_purpose(query_type)
                            st.info(f"🌐 이 추가 답변은 구글 검색 결과를 바탕으로 **{type_info}** 형태로 생성되었습니다.")
                            st.success(f"✨ 내부 문서 답변과 인터넷 검색 결과를 함께 참고하여 더 완전한 {search_purpose}을(를) 찾아보세요!")
                            
                            # 추가 답변을 세션에 저장
                            additional_response = f"""
**[추가 인터넷 검색 기반 {search_purpose}]**

{internet_response}

※ 이 답변은 사용자 요청에 의한 추가 구글 검색 결과를 바탕으로 생성되었습니다.
"""
                            st.session_state.messages.append({"role": "assistant", "content": additional_response})
                            
                    else:
                        st.warning("🌐 인터넷에서 추가 정보를 찾을 수 없습니다.")
                        st.info("내부 문서의 답변을 참고하시거나, 다른 키워드로 다시 질문해보세요.")
                        
        except Exception as e:
            st.error(f"🌐 추가 인터넷 검색 중 오류가 발생했습니다: {str(e)}")
            st.info("내부 문서의 답변을 참고하시거나, 잠시 후 다시 시도해보세요.")
    
    def _display_search_modal(self, search_button_key, type_labels):
        """검색 모달 표시"""
        # 저장된 검색 데이터 가져오기
        query = st.session_state.get(f"search_query_{search_button_key}", "")
        target_service_name = st.session_state.get(f"search_service_{search_button_key}", "")
        query_type = st.session_state.get(f"search_type_{search_button_key}", "default")
        
        # 모달 다이얼로그 표시
        @st.dialog(f"🌐 인터넷 검색 결과 - {self._get_search_purpose(query_type)}")
        def search_modal():
            try:
                st.info("🔍 구글에서 관련 정보를 검색하고 있습니다...")
                
                # 프로그레스 바 표시
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # 검색 실행
                status_text.text("🔍 검색 중...")
                progress_bar.progress(30)
                
                search_results = self.internet_search.search_google(query, target_service_name, num_results=5)
                progress_bar.progress(60)
                
                if search_results:
                    status_text.text("✅ 검색 완료!")
                    progress_bar.progress(100)
                    
                    st.success(f"🌐 총 {len(search_results)}개의 관련 정보를 찾았습니다!")
                    
                    # 검색 결과 탭으로 구성
                    tab1, tab2 = st.tabs(["📋 검색 결과", "🤖 AI 분석"])
                    
                    with tab1:
                        st.markdown("### 🔍 구글 검색 결과")
                        for i, result in enumerate(search_results, 1):
                            with st.expander(f"🔗 검색 결과 {i}: {result['title'][:50]}...", expanded=i==1):
                                st.markdown(f"**제목**: {result['title']}")
                                st.markdown(f"**출처**: {result['source']}")
                                st.markdown(f"**내용**: {result['snippet']}")
                                st.markdown(f"**링크**: [바로가기]({result['link']})")
                    
                    with tab2:
                        st.markdown("### 🤖 AI 분석 결과")
                        with st.spinner("💡 검색 결과를 분석하여 답변을 생성하고 있습니다..."):
                            internet_response = self.internet_search.generate_internet_search_response(
                                self.azure_openai_client, query, target_service_name, 
                                search_results, self.model_name, query_type
                            )
                            
                            # AI 분석 결과 표시
                            search_purpose = self._get_search_purpose(query_type)
                            st.markdown(f"#### 🌐 인터넷 검색 기반 {search_purpose}")
                            st.write(internet_response)
                            
                            # 정보 표시
                            type_info = type_labels.get(query_type, '일반 문의')
                            st.info(f"🌐 이 답변은 구글 검색 결과를 바탕으로 **{type_info}** 형태로 생성되었습니다.")
                    
                    # 답변을 채팅에 추가할지 묻기
                    st.markdown("---")
                    col1, col2 = st.columns([1, 1])
                    
                    with col1:
                        if st.button("💬 채팅에 추가", use_container_width=True, type="primary"):
                            # 답변을 세션에 저장
                            search_purpose = self._get_search_purpose(query_type)
                            additional_response = f"""
**[🌐 인터넷 검색 기반 {search_purpose}]**

{internet_response}

※ 이 답변은 구글 검색 결과를 바탕으로 생성되었습니다.
"""
                            st.session_state.messages.append({"role": "assistant", "content": additional_response})
                            st.success("✅ 답변이 채팅에 추가되었습니다!")
                            # 모달 닫기
                            st.session_state[f"show_search_modal_{search_button_key}"] = False
                            st.rerun()
                    
                    with col2:
                        if st.button("❌ 닫기", use_container_width=True):
                            st.session_state[f"show_search_modal_{search_button_key}"] = False
                            st.rerun()
                
                else:
                    status_text.text("❌ 검색 실패")
                    progress_bar.progress(100)
                    
                    st.warning("🌐 관련 정보를 찾을 수 없습니다.")
                    st.info("다른 키워드로 다시 검색해보거나 내부 문서 답변을 참고해주세요.")
                    
                    if st.button("❌ 닫기", use_container_width=True):
                        st.session_state[f"show_search_modal_{search_button_key}"] = False
                        st.rerun()
                        
            except Exception as e:
                st.error(f"🌐 인터넷 검색 중 오류가 발생했습니다: {str(e)}")
                if st.button("❌ 닫기", use_container_width=True):
                    st.session_state[f"show_search_modal_{search_button_key}"] = False
                    st.rerun()
        
        # 모달 실행
        search_modal()
    
    def _show_internet_search_modal(self, query, target_service_name, query_type, type_labels):
        """인터넷 검색 결과를 모달 팝업으로 표시"""
        try:
            # 모달 다이얼로그 생성
            @st.dialog(f"🌐 인터넷 검색 결과 - {self._get_search_purpose(query_type)}")
            def show_search_results():
                st.info("🔍 구글에서 관련 정보를 검색하고 있습니다...")
                
                # 프로그레스 바 표시
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # 검색 실행
                status_text.text("🔍 검색 중...")
                progress_bar.progress(30)
                
                search_results = self.internet_search.search_google(query, target_service_name, num_results=5)
                progress_bar.progress(60)
                
                if search_results:
                    status_text.text("✅ 검색 완료!")
                    progress_bar.progress(100)
                    
                    st.success(f"🌐 총 {len(search_results)}개의 관련 정보를 찾았습니다!")
                    
                    # 검색 결과 탭으로 구성
                    tab1, tab2 = st.tabs(["📋 검색 결과", "🤖 AI 분석"])
                    
                    with tab1:
                        st.markdown("### 🔍 구글 검색 결과")
                        for i, result in enumerate(search_results, 1):
                            with st.container():
                                # 카드 스타일로 각 결과 표시
                                st.markdown(f"""
                                <div style="border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; margin: 10px 0; background-color: #f9f9f9;">
                                    <h4 style="color: #1f77b4; margin: 0 0 10px 0;">🔗 검색 결과 {i}</h4>
                                    <p style="margin: 5px 0;"><strong>제목:</strong> {result['title']}</p>
                                    <p style="margin: 5px 0;"><strong>출처:</strong> {result['source']}</p>
                                    <p style="margin: 5px 0;"><strong>내용:</strong> {result['snippet']}</p>
                                    <p style="margin: 10px 0 0 0;">
                                        <a href="{result['link']}" target="_blank" style="
                                            background-color: #1f77b4; 
                                            color: white; 
                                            padding: 8px 16px; 
                                            text-decoration: none; 
                                            border-radius: 4px;
                                            display: inline-block;
                                        ">🔗 바로가기</a>
                                    </p>
                                </div>
                                """, unsafe_allow_html=True)
                    
                    with tab2:
                        st.markdown("### 🤖 AI 분석 결과")
                        with st.spinner("💡 검색 결과를 분석하여 답변을 생성하고 있습니다..."):
                            internet_response = self.internet_search.generate_internet_search_response(
                                self.azure_openai_client, query, target_service_name, 
                                search_results, self.model_name, query_type
                            )
                            
                            # AI 분석 결과 표시
                            search_purpose = self._get_search_purpose(query_type)
                            st.markdown(f"#### 🌐 인터넷 검색 기반 {search_purpose}")
                            
                            # 답변을 박스로 감싸기
                            st.markdown(f"""
                            <div style="
                                border: 2px solid #4CAF50; 
                                border-radius: 10px; 
                                padding: 20px; 
                                margin: 10px 0; 
                                background-color: #f0f8f0;
                            ">
                                {internet_response.replace('\n', '<br>')}
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # 정보 표시
                            type_info = type_labels.get(query_type, '일반 문의')
                            st.info(f"🌐 이 답변은 구글 검색 결과를 바탕으로 **{type_info}** 형태로 생성되었습니다.")
                    
                    # 답변을 채팅에 추가할지 묻기
                    st.markdown("---")
                    col1, col2, col3 = st.columns([1, 1, 1])
                    
                    with col1:
                        if st.button("💬 채팅에 추가", use_container_width=True, type="primary"):
                            # 답변을 세션에 저장
                            search_purpose = self._get_search_purpose(query_type)
                            additional_response = f"""
**[🌐 인터넷 검색 기반 {search_purpose}]**

{internet_response}

※ 이 답변은 구글 검색 결과를 바탕으로 생성되었습니다.
"""
                            st.session_state.messages.append({"role": "assistant", "content": additional_response})
                            st.success("✅ 답변이 채팅에 추가되었습니다!")
                            st.rerun()
                    
                    with col2:
                        if st.button("📋 복사", use_container_width=True):
                            # 클립보드 복사를 위한 JavaScript 코드
                            st.markdown(f"""
                            <script>
                            navigator.clipboard.writeText(`{internet_response.replace('`', '\\`')}`);
                            </script>
                            """, unsafe_allow_html=True)
                            st.success("📋 답변이 클립보드에 복사되었습니다!")
                    
                    with col3:
                        if st.button("❌ 닫기", use_container_width=True):
                            st.rerun()
                
                else:
                    status_text.text("❌ 검색 실패")
                    progress_bar.progress(100)
                    
                    st.warning("🌐 관련 정보를 찾을 수 없습니다.")
                    st.info("다른 키워드로 다시 검색해보거나 내부 문서 답변을 참고해주세요.")
                    
                    col1, col2 = st.columns([1, 1])
                    with col2:
                        if st.button("❌ 닫기", use_container_width=True):
                            st.rerun()
            
            # 모달 실행
            show_search_results()
            
        except Exception as e:
            st.error(f"🌐 인터넷 검색 중 오류가 발생했습니다: {str(e)}")
    
    def _get_search_purpose(self, query_type):
        """쿼리 타입에 따른 검색 목적 반환"""
        purposes = {
            'repair': '해결방법',
            'cause': '원인분석',
            'similar': '유사사례',
            'default': '관련정보'
        }
        return purposes.get(query_type, purposes['default'])
    
    def _perform_additional_internet_search(self, query, target_service_name, query_type, type_labels):
        """추가 인터넷 검색 수행 (repair 타입용)"""
        try:
            st.info("🔍 추가 인터넷 검색을 시작합니다...")
            
            with st.spinner("🔍 인터넷에서 추가 복구방법 검색 중..."):
                # 인터넷 검색 실행
                search_results = self.internet_search.search_google(query, target_service_name, num_results=5)
                
                if search_results:
                    st.success(f"🌐 인터넷에서 {len(search_results)}개의 추가 복구방법을 찾았습니다!")
                    
                    # 검색 결과 표시
                    with st.expander("🔍 추가 인터넷 검색 결과", expanded=True):
                        st.markdown("### 🌐 구글 검색 결과")
                        for i, result in enumerate(search_results, 1):
                            with st.container():
                                st.markdown(f"#### 🔗 검색 결과 {i}")
                                st.markdown(f"**제목**: {result['title']}")
                                st.markdown(f"**출처**: {result['source']}")
                                st.markdown(f"**내용**: {result['snippet']}")
                                st.markdown(f"**링크**: [바로가기]({result['link']})")
                                if i < len(search_results):
                                    st.divider()
                    
                    # 인터넷 검색 기반 응답 생성
                    with st.spinner("💡 인터넷 검색 결과를 바탕으로 추가 답변 생성 중..."):
                        internet_response = self.internet_search.generate_internet_search_response(
                            self.azure_openai_client, query, target_service_name, 
                            search_results, self.model_name, query_type
                        )
                        
                        with st.expander("🤖 추가 AI 답변 (인터넷 검색 기반)", expanded=True):
                            st.markdown("### 🌐 인터넷 검색 기반 추가 복구방법")
                            st.write(internet_response)
                            type_info = type_labels.get(query_type, '일반 문의')
                            st.info(f"🌐 이 추가 답변은 구글 검색 결과를 바탕으로 **{type_info}** 형태로 생성되었습니다.")
                            st.success("✨ 내부 문서와 인터넷 검색 결과를 함께 참고하여 더 완전한 해결방법을 찾아보세요!")
                        
                        # 추가 답변도 세션에 저장
                        additional_response = f"""
**[추가 인터넷 검색 답변]**

{internet_response}

※ 이 답변은 사용자 요청에 의한 추가 인터넷 검색 결과입니다.
"""
                        st.session_state.messages.append({"role": "assistant", "content": additional_response})
                        
                else:
                    st.warning("🌐 인터넷에서 추가 정보를 찾을 수 없습니다. 내부 문서의 답변을 참고해주세요.")
                    
        except Exception as e:
            st.error(f"🌐 추가 인터넷 검색 중 오류가 발생했습니다: {str(e)}")
            st.info("내부 문서의 답변을 참고하시거나, 다른 검색어로 다시 시도해보세요.")
    
    def _show_no_results_message(self, target_service_name, query_type, type_labels):
        """검색 결과가 없을 때 메시지 표시"""
        error_msg = f"""
        🔍 '{target_service_name or '해당 조건'}'에 해당하는 문서를 찾을 수 없습니다.
        
        **개선 방안:**
        - 서비스명의 일부만 입력해보세요 (예: 'API' 대신 'API_Link')
        - 다른 검색어를 시도해보세요
        - 전체 검색을 원하시면 서비스명을 제외하고 검색해주세요
        
        **참고**: 현재 시스템은 서비스명 정확 매칭과 포함 매칭을 모두 지원하며, **{type_labels.get(query_type, '일반 문의')}** 유형으로 분류되었습니다.
        """
        with st.expander("🤖 AI 답변 보기", expanded=True):
            st.write(error_msg)
        st.session_state.messages.append({"role": "assistant", "content": error_msg})