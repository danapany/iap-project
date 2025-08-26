import streamlit as st
import re
from config.prompts import SystemPrompts
from config.settings_local import AppConfigLocal
from utils.search_utils_local import SearchManagerLocal
from utils.ui_components_local import UIComponentsLocal

class QueryProcessorLocal:
    """쿼리 처리 관리 클래스"""
    
    def __init__(self, azure_openai_client, search_client, model_name, config=None):
        self.azure_openai_client = azure_openai_client
        self.search_client = search_client
        self.model_name = model_name
        # config가 전달되지 않으면 새로 생성
        self.config = config if config else AppConfigLocal()
        self.search_manager = SearchManagerLocal(search_client, self.config)
        self.ui_components = UIComponentsLocal()
    
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
                with st.spinner("질문 유형 분석 중..."):
                    query_type = self.classify_query_type_with_llm(query)
            
            # 서비스명 추출
            target_service_name = self.search_manager.extract_service_name_from_query(query)
            
            with st.spinner("문서 검색 중..."):
                # 개선된 검색 함수 호출
                documents = self.search_manager.semantic_search_with_service_filter(
                    query, target_service_name, query_type
                )
                
                if documents:
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
                        집계 미리보기
                        - 전체 건수: {len(documents)}건
                        - 년도별 분포: {dict(sorted(yearly_stats.items()))}
                        - 년도별 합계: {yearly_total}건
                        - 검증 상태: {'일치' if yearly_total == len(documents) else '불일치'}
                        """)
                    
                    st.success(f"{len(documents)}개의 매칭 문서 선별 완료! (Premium: {premium_count}개, Standard: {standard_count}개, Basic: {basic_count}개)")
                    
                    # 검색된 문서 표시
                    with st.expander("매칭된 문서 보기"):
                        self.ui_components.display_documents_with_quality_info(documents)
                    
                    # RAG 응답 생성
                    with st.spinner("답변 생성 중..."):
                        response = self.generate_rag_response_with_accurate_count(
                            query, documents, query_type
                        )
                        
                        with st.expander("AI 답변 보기", expanded=True):
                            st.write(response)
                        
                        st.session_state.messages.append({"role": "assistant", "content": response})
                else:
                    # 대체 검색 시도
                    st.warning("포함 매칭으로도 결과가 없어 더 관대한 기준으로 재검색 중...")
                    
                    # 매우 관대한 기준으로 재검색 (서비스명 포함 필터링 유지)
                    fallback_documents = self.search_manager.search_documents_fallback(query, target_service_name)
                    
                    if fallback_documents:
                        st.info(f"대체 검색으로 {len(fallback_documents)}개 문서 발견")
                        
                        response = self.generate_rag_response_with_accurate_count(
                            query, fallback_documents, query_type
                        )
                        with st.expander("AI 답변 보기 (대체 검색)", expanded=True):
                            st.write(response)
                        
                        st.session_state.messages.append({"role": "assistant", "content": response})
                    else:
                        self._show_no_results_message(target_service_name, query_type)
    
    def _show_no_results_message(self, target_service_name, query_type):
        """검색 결과가 없을 때 메시지 표시"""
        error_msg = f"""
        '{target_service_name or '해당 조건'}'에 해당하는 문서를 찾을 수 없습니다.
        
        **개선 방안:**
        - 서비스명의 일부만 입력해보세요 (예: 'API' 대신 'API_Link')
        - 다른 검색어를 시도해보세요
        - 전체 검색을 원하시면 서비스명을 제외하고 검색해주세요
        """
        
        with st.expander("AI 답변 보기", expanded=True):
            st.write(error_msg)
        
        st.session_state.messages.append({"role": "assistant", "content": error_msg})