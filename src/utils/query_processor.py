import streamlit as st
import re
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
    
    def is_internet_search_enabled(self):
        """인터넷 검색 토글 상태 확인"""
        # 토글이 활성화되어 있고, SerpApi가 설정되어 있어야 함
        toggle_enabled = st.session_state.get('internet_search_enabled', False)
        serpapi_available = self.internet_search.is_available()
        
        return toggle_enabled and serpapi_available
    
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

    def _should_skip_internet_search(self, query, query_type):
        """인터넷 검색을 건너뛸지 판단"""
        # 내부 데이터 전용 키워드들
        internal_only_keywords = [
            '장애이력', '장애내역', '장애건수', '장애통계', '장애현황',
            '건수', '개수', '몇건', '년도별', '월별', '일별', '통계', '현황',
            '발생건수', '발생현황', '집계', '합계', '이계', '이건수',
            '이력조회', '내역조회', '발생일자', '언제', '기간별',
            '분포', '추이', '경향', '트렌드'
        ]
        
        # 쿼리에 내부 전용 키워드가 포함되어 있는지 확인
        query_lower = query.lower()
        for keyword in internal_only_keywords:
            if keyword in query_lower:
                return True
        
        # default 타입이고 통계성 질문인 경우 건너뛰기
        if query_type == 'default':
            statistical_patterns = ['몇', '얼마', '수치', '데이터', '정보']
            if any(pattern in query_lower for pattern in statistical_patterns):
                return True
        
        return False

    def _extract_technical_search_terms(self, query, target_service_name=None):
        """IT 전문가 관점에서 기술적 검색어 추출 및 강화"""
        # 서비스명만 제거 (있는 경우)
        if target_service_name:
            general_query = re.sub(r'\b' + re.escape(target_service_name) + r'\b', '', query, flags=re.IGNORECASE)
            general_query = re.sub(r'\s+', ' ', general_query).strip()
        else:
            general_query = query.strip()
        
        # 빈 문자열이 되지 않도록 처리
        if not general_query.strip():
            general_query = query
        
        # IT 기술 분야별 전문 용어 매핑
        technical_keywords = {
            # 네트워크 관련
            'connectivity': ['network connectivity issues', 'connection timeout', 'network troubleshooting'],
            'timeout': ['connection timeout', 'request timeout', 'network latency issues'],
            'dns': ['DNS resolution failure', 'DNS server issues', 'DNS troubleshooting'],
            
            # 시스템 관련
            'server': ['server down', 'server performance issues', 'server monitoring'],
            'database': ['database connection issues', 'DB performance tuning', 'database troubleshooting'],
            'application': ['application error', 'software bug', 'application performance'],
            
            # 장애 유형별
            'performance': ['system performance degradation', 'slow response time', 'performance optimization'],
            'security': ['security incident', 'cybersecurity issues', 'security vulnerability'],
            'hardware': ['hardware failure', 'hardware diagnostics', 'server hardware issues']
        }
        
        # 쿼리에서 기술적 키워드 감지 및 전문 용어 추가
        enhanced_keywords = []
        query_lower = general_query.lower()
        
        # 장애 현상 기반 기술 키워드 추가
        if any(keyword in query_lower for keyword in ['접속', '연결', 'connection', 'connect']):
            enhanced_keywords.extend(technical_keywords['connectivity'])
        
        if any(keyword in query_lower for keyword in ['지연', '느림', 'slow', 'delay', 'timeout']):
            enhanced_keywords.extend(technical_keywords['timeout'])
            enhanced_keywords.extend(technical_keywords['performance'])
        
        if any(keyword in query_lower for keyword in ['서버', 'server']):
            enhanced_keywords.extend(technical_keywords['server'])
        
        if any(keyword in query_lower for keyword in ['데이터베이스', 'database', 'db']):
            enhanced_keywords.extend(technical_keywords['database'])
        
        if any(keyword in query_lower for keyword in ['어플리케이션', 'application', 'app']):
            enhanced_keywords.extend(technical_keywords['application'])
        
        # 기본 IT 전문 키워드 추가
        base_technical_terms = [
            'IT troubleshooting',
            'system administration', 
            'technical support',
            'root cause analysis',
            'incident management'
        ]
        
        # 최종 검색 쿼리 구성 (원본 + 기술 키워드)
        all_keywords = enhanced_keywords + base_technical_terms
        final_query = f"{general_query} {' '.join(all_keywords[:5])}"  # 상위 5개만 사용
        
        return final_query.strip()

    def _validate_search_results_quality(self, search_results, query, target_service_name):
        """검색 결과의 품질과 관련성을 검증"""
        if not search_results:
            return False, "검색 결과가 없습니다.", []
        
        # IT/기술 관련성 검증 키워드
        it_keywords = [
            'troubleshooting', 'error', 'fix', 'solution', 'problem', 'issue',
            'server', 'network', 'database', 'application', 'system', 'software',
            '오류', '해결', '문제', '장애', '복구', '원인', '서버', '네트워크', '시스템'
        ]
        
        relevant_results = []
        for result in search_results:
            title = result.get('title', '').lower()
            snippet = result.get('snippet', '').lower()
            
            # IT 관련성 점수 계산
            relevance_score = 0
            for keyword in it_keywords:
                if keyword.lower() in title:
                    relevance_score += 2
                if keyword.lower() in snippet:
                    relevance_score += 1
            
            # 최소 관련성 점수 기준 (낮춤)
            if relevance_score >= 1:
                relevant_results.append(result)
        
        if not relevant_results:
            return False, "IT 기술 관련 정보를 찾을 수 없습니다.", search_results
        
        if len(relevant_results) < 2:
            return False, f"관련 기술 정보가 부족합니다. ({len(relevant_results)}개 발견)", search_results
        
        return True, f"검증된 IT 기술 정보 {len(relevant_results)}개를 발견했습니다.", relevant_results

    def _generate_enhanced_technical_response(self, search_query, original_query, search_results, query_type, type_labels):
        """향상된 IT 전문가 관점의 기술적 응답 생성"""
        try:
            # 검색 결과 품질 검증
            is_quality, quality_message, filtered_results = self._validate_search_results_quality(
                search_results, original_query, None
            )
            
            # 정보 부족 시에도 일반적인 답변 제공
            if not is_quality:
                response_prefix = """
**🔍 IT 전문가 분석 결과**

⚠️ **정보가 부족하여 일반적인 내용으로 답변드립니다.**

"""
                # 일반적인 IT 지식 기반 답변 생성
                general_system_prompt = f"""당신은 20년 경력의 IT 전문가입니다. 
검색된 정보가 부족하지만, 일반적인 IT 지식과 경험을 바탕으로 도움이 되는 답변을 제공해주세요.

**답변 방침:**
1. **일반적 접근법**: 해당 유형의 문제에 대한 일반적인 해결 접근법 제시
2. **경험 기반**: IT 현장에서 자주 발생하는 유사 상황과 대응 방법
3. **단계적 가이드**: 체계적인 문제 해결 단계 제공
4. **주의사항**: 일반적인 내용임을 명시하고 구체적 환경 고려 필요성 강조
5. **추가 조치**: 더 정확한 진단을 위한 추가 정보 수집 방법 안내

검색된 정보가 제한적이므로 일반적이고 안전한 접근법을 중심으로 답변해주세요."""
                
                # 검색 결과가 있다면 활용, 없다면 일반 지식만 사용
                if search_results:
                    search_context = self.internet_search.format_search_results_for_llm(search_results)
                    context_info = f"\n\n**제한적 검색 정보:**\n{search_context}\n"
                else:
                    context_info = "\n**검색 정보:** 관련 정보를 찾을 수 없어 일반적인 IT 지식으로 답변합니다.\n"
                
            else:
                # 충분한 정보가 있는 경우 기존 로직 유지
                response_prefix = """
**🔍 IT 전문가 분석 결과**

✅ **검색된 기술 정보를 바탕으로 답변드립니다.**

"""
                # 검증된 결과만 사용
                search_context = self.internet_search.format_search_results_for_llm(filtered_results)
                context_info = f"\n\n**검증된 기술 정보:**\n{search_context}\n"
                
                # 쿼리 타입별 엄격한 시스템 프롬프트
                if query_type == 'repair':
                    general_system_prompt = """당신은 20년 경력의 IT 트러블슈팅 시니어 전문가입니다. 
검색된 기술 문서에 근거하여 정확하고 검증된 복구방법을 제시해주세요."""
                elif query_type == 'cause':
                    general_system_prompt = """당신은 20년 경력의 IT 시스템 분석 시니어 전문가입니다.
검색된 기술 문서에 근거하여 정확하고 논리적인 원인 분석을 제시해주세요."""
                else:
                    general_system_prompt = """당신은 20년 경력의 IT 컨설팅 시니어 전문가입니다.
검색된 기술 문서에 근거하여 정확하고 실무적인 기술 정보를 제시해주세요."""
            
            user_prompt = f"""
다음 정보를 바탕으로 IT 전문가 수준의 답변을 제공해주세요:

{context_info}

**원본 질문:** {original_query}
**기술 검색어:** {search_query}

**IT 전문가 답변 요구사항:**
1. **실용적 접근**: 현장에서 실행 가능한 구체적 방안
2. **단계적 가이드**: 체계적인 문제 해결 단계
3. **안전성 고려**: 시스템에 영향을 주지 않는 안전한 방법 우선
4. **추가 진단**: 더 정확한 문제 파악을 위한 방법 제시
5. **환경 고려**: 다양한 환경에서의 적용 고려사항

**답변 구조:**
- **🔍 상황 분석**: 문제 상황에 대한 기술적 분석
- **💡 권장 해결방안**: 단계별 실행 가능한 조치
- **⚠️ 주의사항**: 적용 시 고려해야 할 사항
- **📄 추가 진단**: 근본 원인 파악을 위한 방법
- **📚 참고사항**: 관련 기술 문서나 모범 사례

전문가 답변:"""

            # LLM 응답 생성
            response = self.azure_openai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": general_system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,  # 일관된 전문가 답변
                max_tokens=2500
            )
            
            # 응답에 정보 부족 알림 추가
            final_response = response_prefix + response.choices[0].message.content
            
            if not is_quality:
                final_response += f"""

---
**📋 정보 품질 안내:**
- 검색 상태: {quality_message}
- 답변 기준: 일반적인 IT 전문가 지식 및 경험
- 추가 권장: 구체적 시스템 환경과 오류 로그 확인 필요성 강조
- 주의사항: 일반적인 내용임을 명시하고 구체적 환경 고려 필요성 강조

**🔍 더 정확한 답변을 위한 제안:**
- 구체적인 오류 메시지나 로그 정보 제공
- 사용 중인 시스템/소프트웨어 버전 정보 추가
- 장애 발생 시점과 관련 작업 이력 확인
"""
            else:
                final_response += f"""

---
**📋 정보 품질 안내:**
- 검색 상태: {quality_message}
- 답변 기준: 검증된 기술 문서 및 전문가 경험
- 적용 권장: 실제 환경 특성을 고려하여 단계적 적용
"""
            
            return final_response
            
        except Exception as e:
            st.error(f"🌐 IT 전문가 관점 응답 생성 실패: {str(e)}")
            return f"""
**🔍 IT 전문가 분석 결과**

⚠️ **정보가 부족하여 일반적인 내용으로 답변드립니다.**

죄송합니다. 기술 정보 분석 중 오류가 발생했습니다: {str(e)}

**일반적인 IT 문제 해결 접근법:**
1. **문제 상황 정확히 파악**: 오류 메시지, 로그, 발생 시점 확인
2. **기본 점검**: 네트워크 연결, 서비스 상태, 리소스 사용량 확인  
3. **단계적 진단**: 간단한 해결책부터 복잡한 방법까지 순차 적용
4. **전문가 상담**: 복잡한 문제는 해당 분야 전문가와 협의

※ 구체적인 환경 정보와 함께 다시 문의하시면 더 정확한 답변을 드릴 수 있습니다.
"""

    def _perform_enhanced_internet_search(self, query, target_service_name, query_type, type_labels):
        """향상된 IT 전문가 관점의 인터넷 검색 수행 (토글 상태 확인)"""
        # 인터넷 검색 토글 상태 확인
        if not self.is_internet_search_enabled():
            if not st.session_state.get('internet_search_enabled', False):
                st.info("🔒 인터넷 검색이 비활성화되어 있습니다. 활성화하려면 상단의 토글을 켜주세요.")
            else:
                st.warning("⚠️ SerpApi가 설정되지 않아 인터넷 검색을 사용할 수 없습니다.")
            return
        
        try:
            # IT 전문가 관점의 기술적 검색어 생성
            technical_search_query = self._extract_technical_search_terms(query, target_service_name)
            
            with st.spinner(f"🔍 IT 전문가 관점에서 기술 정보 검색 중... (검색어: {technical_search_query})"):
                # IT 전문 기술 정보로 인터넷 검색 실행
                search_results = self.internet_search.search_google(technical_search_query, service_name=None, num_results=8)
                
                if search_results:
                    # 검색 결과 품질 검증
                    is_quality, quality_message, filtered_results = self._validate_search_results_quality(
                        search_results, query, target_service_name
                    )
                    
                    # 품질과 관계없이 검색 결과 표시 및 답변 제공
                    if is_quality:
                        st.success(f"🌐 {quality_message}")
                        display_message = "**📌 참고:** 아래는 IT 전문가/트러블슈팅 전문가 관점에서 수집된 검증된 기술 정보입니다."
                        info_type = "검증된 기술 정보"
                    else:
                        st.info(f"🌐 {quality_message} - 일반적인 내용으로 답변드립니다.")
                        display_message = "**📌 참고:** 아래는 제한적인 기술 정보이지만 일반적인 IT 지식으로 보완하여 답변드립니다."
                        info_type = "제한적 기술 정보"
                    
                    # 검색 결과 표시 (접을 수 있는 형태)
                    with st.expander(f"🔍 IT 전문 기술 정보 검색 결과", expanded=False):
                        st.info(f"🎯 IT 전문가 검색어: {technical_search_query}")
                        st.markdown(display_message)
                        st.markdown("---")
                        
                        for i, result in enumerate(search_results, 1):
                            st.markdown(f"#### 🔗 {info_type} {i}")
                            st.markdown(f"**제목**: {result['title']}")
                            st.markdown(f"**출처**: {result['source']}")
                            st.markdown(f"**내용**: {result['snippet']}")
                            st.markdown(f"**링크**: [바로가기]({result['link']})")
                            if i < len(search_results):
                                st.divider()
                    
                    # IT 전문가 관점의 AI 답변 생성 및 표시 (정보 부족 시에도 답변 제공)
                    with st.spinner("💡 IT 전문가 관점에서 기술 정보 분석 중..."):
                        internet_response = self._generate_enhanced_technical_response(
                            technical_search_query, query, search_results, query_type, type_labels
                        )
                        
                        # 기존 'AI 답변보기'와 동일한 구성으로 표시
                        with st.expander("🤖 AI 답변보기 (IT 전문가 관점)", expanded=True):
                            st.write(internet_response)
                            search_purpose = self._get_search_purpose(query_type)
                            type_info = type_labels.get(query_type, '일반 문의')
                            
                            if is_quality:
                                st.info(f"🌐 이 답변은 IT 전문가/트러블슈팅 전문가 관점에서 검증된 기술 정보를 종합한 **{type_info}** 형태의 전문 분석입니다.")
                            else:
                                st.info(f"🌐 이 답변은 제한적인 기술 정보를 일반적인 IT 전문가 지식으로 보완한 **{type_info}** 형태의 분석입니다.")
                            
                            st.warning("⚠️ 이 정보는 인터넷상의 기술 문서를 기반으로 하며, 실제 환경 특성을 고려하여 적용하시기 바랍니다.")
                        
                        # 인터넷 검색 답변도 세션에 저장
                        search_purpose = self._get_search_purpose(query_type)
                        additional_response = f"""
**[🌐 IT 전문가 관점 기반 {search_purpose}]**

{internet_response}

※ 이 답변은 IT 전문가/트러블슈팅 전문가 관점에서 기술 정보를 종합한 결과입니다.
※ 실제 적용 시에는 해당 환경의 특성을 고려하시기 바랍니다.
"""
                        st.session_state.messages.append({"role": "assistant", "content": additional_response})
                        
                else:
                    st.warning("🌐 관련 IT 전문 기술 정보를 찾을 수 없습니다.")
                    st.info("다른 키워드로 다시 질문해보거나 내부 문서 답변을 참고해주세요.")
                    
                    # 검색 결과 없음에도 일반적인 답변 제공
                    with st.spinner("💡 일반적인 IT 지식으로 답변 생성 중..."):
                        # 검색 결과 없이 일반적인 답변 생성
                        general_response = self._generate_enhanced_technical_response(
                            technical_search_query, query, [], query_type, type_labels
                        )
                        
                        with st.expander("🤖 AI 답변보기 (일반 IT 지식)", expanded=True):
                            st.write(general_response)
                            search_purpose = self._get_search_purpose(query_type)
                            type_info = type_labels.get(query_type, '일반 문의')
                            st.info(f"🌐 이 답변은 일반적인 IT 전문가 지식과 경험을 바탕으로 한 **{type_info}** 형태의 분석입니다.")
                            st.warning("⚠️ 구체적인 환경 정보와 함께 문의하시면 더 정확한 답변을 드릴 수 있습니다.")
                    
                    # 일반적인 답변도 세션에 저장
                    search_purpose = self._get_search_purpose(query_type)
                    no_results_response = f"""
**[🌐 IT 전문가 일반 지식 기반 {search_purpose}]**

{general_response}

※ 이 답변은 검색 정보 부족으로 일반적인 IT 전문가 지식을 바탕으로 제공되었습니다.
※ 구체적인 환경 정보와 함께 문의하시면 더 정확한 답변을 드릴 수 있습니다.
"""
                    st.session_state.messages.append({"role": "assistant", "content": no_results_response})
                    
        except Exception as e:
            st.error(f"🌐 IT 전문 기술 정보 검색 중 오류가 발생했습니다: {str(e)}")
            st.info("내부 문서의 답변을 참고하시거나, 잠시 후 다시 시도해보세요.")
            
            # 오류 발생 시에도 일반적인 답변 시도
            try:
                with st.spinner("💡 일반적인 IT 지식으로 답변 생성 중..."):
                    error_response = self._generate_enhanced_technical_response(
                        query, query, [], query_type, type_labels
                    )
                    
                    with st.expander("🤖 AI 답변보기 (일반 IT 지식)", expanded=True):
                        st.write(error_response)
                        st.warning("⚠️ 검색 오류로 인해 일반적인 IT 지식으로만 답변드립니다.")
                
                # 오류 시 일반 답변도 세션에 저장
                search_purpose = self._get_search_purpose(query_type)
                error_fallback_response = f"""
**[🌐 IT 전문가 일반 지식 기반 {search_purpose}]**

{error_response}

※ 기술 정보 검색 중 오류가 발생하여 일반적인 IT 전문가 지식으로 답변드렸습니다.
※ 구체적인 환경 정보와 함께 재문의하시면 더 정확한 답변을 드릴 수 있습니다.
"""
                st.session_state.messages.append({"role": "assistant", "content": error_fallback_response})
                
            except Exception as inner_e:
                # 일반 답변 생성도 실패한 경우
                final_error_response = f"""
**[🌐 IT 전문가 검색 오류]**

⚠️ **정보가 부족하여 일반적인 내용으로 답변드립니다.**

기술 정보 검색 중 오류가 발생했습니다: {str(e)}

**일반적인 IT 문제 해결 접근법:**
1. **문제 상황 정확히 파악**: 오류 메시지, 로그, 발생 시점 확인
2. **기본 점검**: 네트워크 연결, 서비스 상태, 리소스 사용량 확인  
3. **단계적 진단**: 간단한 해결책부터 복잡한 방법까지 순차 적용
4. **전문가 상담**: 복잡한 문제는 해당 분야 전문가와 협의

※ 구체적인 환경 정보와 함께 다시 문의하시면 더 정확한 답변을 드릴 수 있습니다.
"""
                st.session_state.messages.append({"role": "assistant", "content": final_error_response})

    def _get_internet_search_button_text(self, query_type):
        """쿼리 타입에 따른 인터넷 검색 버튼 텍스트 반환"""
        button_texts = {
            'repair': '🌐 인터넷으로도 복구방법을 검색해볼까요?',
            'cause': '🌐 인터넷으로도 장애원인을 검색해볼까요?',
            'similar': '🌐 인터넷으로도 유사사례를 검색해볼까요?',
            'default': '🌐 인터넷으로도 관련정보를 검색해볼까요?'
        }
        return button_texts.get(query_type, button_texts['default'])

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
                        
                        # 향상된 인터넷 검색 필요성 판단 후 실행 (토글 상태 확인)
                        if self.is_internet_search_enabled() and not self._should_skip_internet_search(query, query_type):
                            st.markdown("---")
                            st.info("🔍 추가 정보를 위해 IT 전문가 관점의 인터넷 검색을 실행합니다...")
                            self._perform_enhanced_internet_search(query, target_service_name, query_type, type_labels)

                        elif not self.is_internet_search_enabled():
                            # 토글이 꺼져있거나 SerpApi가 없는 경우 알림
                            if st.session_state.get('internet_search_enabled', False):
                                st.info("⚠️ SerpApi가 설정되지 않아 인터넷 검색을 사용할 수 없습니다.")
                        
                        st.session_state.messages.append({"role": "assistant", "content": response})
                else:
                    # 대체 검색 시도
                    st.warning("🔄 포함 매칭으로도 결과가 없어 더 관대한 기준으로 재검색 중...")
                    
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
                        
                        # 향상된 인터넷 검색 필요성 판단 후 실행 (대체 검색)
                        if self.is_internet_search_enabled() and not self._should_skip_internet_search(query, query_type):
                            st.markdown("---")
                            st.info("🔍 추가 정보를 위해 IT 전문가 관점의 인터넷 검색을 실행합니다...")
                            self._perform_enhanced_internet_search(query, target_service_name, query_type, type_labels)
                        elif self._should_skip_internet_search(query, query_type):
                            st.info("📊 이 질문은 내부 데이터를 기반으로 한 답변이 가장 정확합니다.")
                        elif not self.is_internet_search_enabled():
                            if st.session_state.get('internet_search_enabled', False):
                                st.info("⚠️ SerpApi가 설정되지 않아 인터넷 검색을 사용할 수 없습니다.")
                        
                        st.session_state.messages.append({"role": "assistant", "content": response})
                    else:
                        # repair, cause 타입인 경우 자동 인터넷 검색 시도 (토글 상태 확인)
                        if query_type in ['repair', 'cause'] and self.is_internet_search_enabled():
                            st.info("🌐 내부 문서에서 관련 정보를 찾을 수 없어 IT 전문가 관점의 인터넷 검색을 시도합니다...")
                            self._perform_enhanced_internet_search(query, target_service_name, query_type, type_labels)
                        else:
                            # 향상된 인터넷 검색 필요성 판단 후 실행 (검색 실패 시)
                            if self.is_internet_search_enabled() and not self._should_skip_internet_search(query, query_type):
                                st.markdown("---")
                                st.info("🔍 추가 정보를 위해 IT 전문가 관점의 인터넷 검색을 실행합니다...")
                                self._perform_enhanced_internet_search(query, target_service_name, query_type, type_labels)
                            elif self._should_skip_internet_search(query, query_type):
                                st.info("📊 이 질문은 내부 데이터를 기반으로 한 답변이 필요하지만, 관련 문서를 찾을 수 없습니다.")
                                self._show_no_results_message(target_service_name, query_type, type_labels)
                            elif not self.is_internet_search_enabled():
                                if st.session_state.get('internet_search_enabled', False):
                                    st.info("⚠️ SerpApi가 설정되지 않아 인터넷 검색을 사용할 수 없습니다.")
                                self._show_no_results_message(target_service_name, query_type, type_labels)
                            else:
                                self._show_no_results_message(target_service_name, query_type, type_labels)
    
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