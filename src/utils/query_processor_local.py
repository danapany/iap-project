import streamlit as st
import re
from config.prompts import SystemPrompts
from config.settings_local import AppConfigLocal
from utils.search_utils_local import SearchManagerLocal
from utils.ui_components_local import UIComponentsLocal

class QueryProcessorLocal:
    """쿼리 처리 관리 클래스 - 쿼리 타입별 최적화된 적응형 처리 시스템"""
    
    def __init__(self, azure_openai_client, search_client, model_name, config=None):
        self.azure_openai_client = azure_openai_client
        self.search_client = search_client
        self.model_name = model_name
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
            
            if query_type not in ['repair', 'cause', 'similar', 'default']:
                query_type = 'default'
                
            return query_type
            
        except Exception as e:
            st.warning(f"쿼리 분류 실패, 기본값 사용: {str(e)}")
            return 'default'

    def validate_document_relevance_with_llm(self, query, documents):
        """LLM을 사용하여 검색 결과의 관련성을 재검증 - repair/cause 전용"""
        try:
            if not documents:
                return []
            
            validation_prompt = f"""
사용자 질문: "{query}"

다음 검색된 문서들 중에서 사용자 질문과 실제로 관련성이 높은 문서만 선별해주세요.
각 문서에 대해 0-100점 사이의 관련성 점수를 매기고, 70점 이상인 문서만 선택하세요.

평가 기준:
1. 서비스명 일치도 (사용자가 특정 서비스를 언급한 경우)
2. 장애현상/증상 일치도  
3. 사용자가 요구한 정보 유형과의 일치도
4. 전체적인 맥락 일치도

"""

            for i, doc in enumerate(documents):
                doc_info = f"""
문서 {i+1}:
- 서비스명: {doc.get('service_name', '')}
- 장애현상: {doc.get('symptom', '')}
- 영향도: {doc.get('effect', '')}
- 장애원인: {doc.get('root_cause', '')[:100]}...
- 복구방법: {doc.get('incident_repair', '')[:100]}...
"""
                validation_prompt += doc_info

            validation_prompt += """

응답 형식 (JSON):
{
    "validated_documents": [
        {
            "document_index": 1,
            "relevance_score": 85,
            "reason": "서비스명과 장애현상이 정확히 일치함"
        },
        {
            "document_index": 3,
            "relevance_score": 72,
            "reason": "장애현상은 유사하지만 서비스명이 다름"
        }
    ]
}

70점 이상인 문서만 포함하세요.
"""

            response = self.azure_openai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "당신은 문서 관련성 평가 전문가입니다. 사용자 질문과 문서의 관련성을 정확하게 평가해주세요."},
                    {"role": "user", "content": validation_prompt}
                ],
                temperature=0.1,
                max_tokens=800
            )
            
            response_content = response.choices[0].message.content.strip()
            
            try:
                import json
                json_start = response_content.find('{')
                json_end = response_content.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_content = response_content[json_start:json_end]
                    validation_result = json.loads(json_content)
                    
                    validated_docs = []
                    for validated_doc in validation_result.get('validated_documents', []):
                        doc_index = validated_doc.get('document_index', 1) - 1
                        if 0 <= doc_index < len(documents):
                            original_doc = documents[doc_index].copy()
                            original_doc['relevance_score'] = validated_doc.get('relevance_score', 0)
                            original_doc['validation_reason'] = validated_doc.get('reason', '검증됨')
                            validated_docs.append(original_doc)
                    
                    validated_docs.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
                    return validated_docs
                    
            except (json.JSONDecodeError, KeyError) as e:
                st.warning(f"문서 검증 결과 파싱 실패: {str(e)}")
                return documents[:5]
                
        except Exception as e:
            st.warning(f"문서 관련성 검증 실패: {str(e)}")
            return documents[:5]
        
        return documents

    def generate_rag_response_with_adaptive_processing(self, query, documents, query_type="default"):
        """쿼리 타입별 적응형 RAG 응답 생성"""
        try:
            # 쿼리 타입별 처리 방식 결정
            use_llm_validation = query_type in ['repair', 'cause']
            
            if use_llm_validation:
                # repair/cause: 정확성 우선 처리
                st.info("🎯 정확성 우선 처리 - 검색 결과의 관련성 재검증 중...")
                validated_documents = self.validate_document_relevance_with_llm(query, documents)
                
                if len(validated_documents) < len(documents):
                    removed_count = len(documents) - len(validated_documents)
                    st.success(f"✅ 관련성 검증 완료: {len(validated_documents)}개 문서 선별 (관련성 낮은 {removed_count}개 문서 제외)")
                else:
                    st.success(f"✅ 관련성 검증 완료: 모든 {len(validated_documents)}개 문서가 관련성 기준 통과")
                
                if not validated_documents:
                    return "검색된 문서들이 사용자 질문과 관련성이 낮아 적절한 답변을 제공할 수 없습니다. 다른 검색어나 더 구체적인 질문을 시도해보세요."
                
                processing_documents = validated_documents
                processing_info = "관련성 검증 완료 (70점 이상)"
                
            else:
                # similar/default: 포괄성 우선 처리
                st.info("📋 포괄성 우선 처리 - 광범위한 검색 결과 활용 중...")
                processing_documents = documents
                processing_info = "포괄적 검색 결과 활용"
                st.success(f"✅ 포괄적 처리 완료: {len(processing_documents)}개 문서 활용")

            # 집계 정보 계산
            total_count = len(processing_documents)
            yearly_stats = {}
            
            for doc in processing_documents:
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
            
            # 컨텍스트 구성
            context_parts = []
            
            stats_info = f"""
=== 정확한 집계 정보 ({processing_info}) ===
전체 문서 수: {total_count}건
년도별 분포: {dict(sorted(yearly_stats.items()))}
년도별 합계: {yearly_total}건
집계 검증: {'일치' if yearly_total == total_count else '불일치 - 재계산 필요'}
처리 방식: {'정확성 우선 (LLM 검증)' if use_llm_validation else '포괄성 우선 (광범위 검색)'}
===========================
"""
            context_parts.append(stats_info)
            
            for i, doc in enumerate(processing_documents):
                final_score = doc.get('final_score', 0)
                quality_tier = doc.get('quality_tier', 'Standard')
                filter_reason = doc.get('filter_reason', '기본 선별')
                service_match_type = doc.get('service_match_type', 'unknown')
                relevance_score = doc.get('relevance_score', 0) if use_llm_validation else "N/A"
                validation_reason = doc.get('validation_reason', '검증됨') if use_llm_validation else "포괄적 처리"
                
                validation_info = f" - 관련성: {relevance_score}점 ({validation_reason})" if use_llm_validation else " - 포괄적 검색"
                
                context_part = f"""문서 {i+1} [{quality_tier}급 - {filter_reason} - {service_match_type} 매칭{validation_info}]:
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
                if use_llm_validation:
                    context_part += f"관련성점수: {relevance_score}점\n"
                
                context_parts.append(context_part)
            
            context = "\n\n".join(context_parts)
            
            # 시스템 프롬프트 선택
            system_prompt = SystemPrompts.get_prompt(query_type)

            user_prompt = f"""
다음 장애 이력 문서들을 참고하여 질문에 답변해주세요.
(처리 방식: {'정확성 우선 - LLM 관련성 검증 적용' if use_llm_validation else '포괄성 우선 - 광범위한 검색 결과 활용'}):

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
                temperature=0.1 if use_llm_validation else 0.2,  # 정확성 vs 창의성 조절
                max_tokens=1500
            )
            
            return response.choices[0].message.content
        
        except Exception as e:
            st.error(f"응답 생성 실패: {str(e)}")
            return "죄송합니다. 응답을 생성하는 중 오류가 발생했습니다."

    def process_query(self, query, query_type=None):
        """쿼리 타입별 최적화된 처리 로직을 적용한 메인 쿼리 처리"""
        with st.chat_message("assistant"):
            # 1단계: LLM 기반 쿼리 타입 자동 분류
            if query_type is None:
                with st.spinner("🔍 질문 유형 분석 중..."):
                    query_type = self.classify_query_type_with_llm(query)
                    
                # 처리 방식 안내
                if query_type in ['repair', 'cause']:
                    st.info(f"📝 질문 유형: **{query_type.upper()}** (🎯 정확성 우선 처리 - LLM 검증 적용)")
                else:
                    st.info(f"📝 질문 유형: **{query_type.upper()}** (📋 포괄성 우선 처리 - 광범위한 검색)")
            
            # 2단계: 서비스명 추출
            target_service_name = self.search_manager.extract_service_name_from_query(query)
            if target_service_name:
                st.info(f"🏷️ 추출된 서비스명: **{target_service_name}**")
            
            # 3단계: 쿼리 타입별 최적화된 검색 수행
            with st.spinner("🔄 문서 검색 중..."):
                documents = self.search_manager.semantic_search_with_adaptive_filtering(
                    query, target_service_name, query_type
                )
                
                if documents:
                    # 검색 결과 품질 분석
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
                        processing_method = "정확성 우선" if query_type in ['repair', 'cause'] else "포괄성 우선"
                        st.info(f"""
                        📊 집계 미리보기 ({processing_method} 처리 예정)
                        - 전체 건수: {len(documents)}건
                        - 년도별 분포: {dict(sorted(yearly_stats.items()))}
                        - 년도별 합계: {yearly_total}건
                        - 검증 상태: {'일치' if yearly_total == len(documents) else '불일치'}
                        """)
                    
                    st.success(f"✅ {len(documents)}개의 매칭 문서 선별 완료! (🏆 Premium: {premium_count}개, 🎯 Standard: {standard_count}개, 📋 Basic: {basic_count}개)")
                    
                    # 검색된 문서 상세 표시
                    with st.expander("📄 매칭된 문서 상세 보기"):
                        self.ui_components.display_documents_with_quality_info(documents)
                    
                    # 4단계: 적응형 RAG 응답 생성
                    with st.spinner("🤖 AI 답변 생성 중..."):
                        response = self.generate_rag_response_with_adaptive_processing(
                            query, documents, query_type
                        )
                        
                        processing_type = "🎯 정확성 우선 처리" if query_type in ['repair', 'cause'] else "📋 포괄성 우선 처리"
                        with st.expander(f"🤖 AI 답변 ({processing_type})", expanded=True):
                            st.write(response)
                        
                        st.session_state.messages.append({"role": "assistant", "content": response})
                        
                else:
                    # 5단계: 대체 검색 시도
                    st.warning("⚠️ 포함 매칭으로도 결과가 없어 더 관대한 기준으로 재검색 중...")
                    
                    fallback_documents = self.search_manager.search_documents_fallback(query, target_service_name)
                    
                    if fallback_documents:
                        st.info(f"🔄 대체 검색으로 {len(fallback_documents)}개 문서 발견")
                        
                        response = self.generate_rag_response_with_adaptive_processing(
                            query, fallback_documents, query_type
                        )
                        with st.expander("🤖 AI 답변 (대체 검색)", expanded=True):
                            st.write(response)
                        
                        st.session_state.messages.append({"role": "assistant", "content": response})
                    else:
                        self._show_no_results_message(target_service_name, query_type)
    
    def _show_no_results_message(self, target_service_name, query_type):
        """검색 결과가 없을 때 개선 방안 제시"""
        error_msg = f"""
        '{target_service_name or '해당 조건'}'에 해당하는 문서를 찾을 수 없습니다.
        
        **🔧 개선 방안:**
        - 서비스명의 일부만 입력해보세요 (예: 'API' 대신 'API_Link')
        - 다른 검색어를 시도해보세요
        - 전체 검색을 원하시면 서비스명을 제외하고 검색해주세요
        - 더 일반적인 키워드를 사용해보세요
        
        **💡 {query_type.upper()} 쿼리 최적화 팁:**
        """
        
        # 쿼리 타입별 개선 팁 추가
        if query_type == 'repair':
            error_msg += """
        - 서비스명과 장애현상을 모두 포함하세요
        - '복구방법', '해결방법' 키워드를 포함하세요
        """
        elif query_type == 'cause':
            error_msg += """
        - '원인', '이유', '왜' 등의 키워드를 포함하세요
        - 장애 현상을 구체적으로 설명하세요
        """
        elif query_type == 'similar':
            error_msg += """
        - '유사', '비슷한', '동일한' 키워드를 포함하세요
        - 핵심 장애 현상만 간결하게 기술하세요
        """
        else:
            error_msg += """
        - 통계나 현황 조회 시 기간을 명시하세요
        - '건수', '통계', '현황' 등의 키워드를 활용하세요
        """
        
        with st.expander("🤖 AI 답변", expanded=True):
            st.write(error_msg)
        
        st.session_state.messages.append({"role": "assistant", "content": error_msg})