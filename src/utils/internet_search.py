import streamlit as st
import requests
from typing import List, Dict, Optional
import re

class InternetSearchManager:
    """SerpApi를 사용한 인터넷 검색 관리 클래스"""
    
    def __init__(self, config):
        self.config = config
        self.serpapi_key = config.serpapi_key
        self.base_url = "https://serpapi.com/search"
    
    def is_available(self) -> bool:
        """SerpApi 사용 가능 여부 확인"""
        return bool(self.serpapi_key)
    
    def extract_search_keywords(self, query: str, service_name: str = None) -> str:
        """쿼리에서 검색에 적합한 키워드 추출"""
        # 기본 검색어 구성
        search_terms = []
        
        # 서비스명이 있는 경우 추가
        if service_name:
            search_terms.append(service_name)
        
        # 한글 키워드를 영문으로 매핑
        keyword_mapping = {
            '장애': 'error issue problem',
            '복구': 'recovery fix solution',
            '원인': 'cause root cause',
            '해결': 'solution resolve',
            '방법': 'method way how to',
            '접속불가': 'connection failed access denied',
            '응답지연': 'response delay timeout',
            '로그인': 'login authentication',
            '데이터베이스': 'database DB',
            '서버': 'server',
            '네트워크': 'network',
            '시스템': 'system'
        }
        
        # 키워드 변환 및 추가
        for korean_word, english_words in keyword_mapping.items():
            if korean_word in query:
                search_terms.extend(english_words.split())
        
        # IT 관련 용어 추가
        search_terms.extend(['IT', 'troubleshooting', 'technical'])
        
        # 중복 제거 및 조합
        unique_terms = list(dict.fromkeys(search_terms))
        search_query = ' '.join(unique_terms[:10])  # 최대 10개 키워드
        
        return search_query
    
    def search_google(self, query: str, service_name: str = None, num_results: int = 5) -> List[Dict]:
        """Google 검색 실행"""
        if not self.is_available():
            st.warning("🌐 SerpApi 키가 설정되지 않아 인터넷 검색을 사용할 수 없습니다.")
            return []
        
        try:
            # 검색 키워드 최적화
            search_query = self.extract_search_keywords(query, service_name)
            
            st.info(f"🔍 구글 검색 중: {search_query}")
            
            # SerpApi 요청 파라미터
            params = {
                'api_key': self.serpapi_key,
                'engine': 'google',
                'q': search_query,
                'num': num_results,
                'hl': 'ko',  # 한국어 결과 우선
                'gl': 'kr',  # 한국 지역 결과 우선
                'safe': 'active'  # 안전 검색 활성화
            }
            
            # API 호출
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            
            search_results = response.json()
            
            # 검색 결과 파싱
            organic_results = search_results.get('organic_results', [])
            
            formatted_results = []
            for result in organic_results[:num_results]:
                formatted_result = {
                    'title': result.get('title', ''),
                    'link': result.get('link', ''),
                    'snippet': result.get('snippet', ''),
                    'source': result.get('source', ''),
                    'position': result.get('position', 0)
                }
                formatted_results.append(formatted_result)
            
            return formatted_results
            
        except requests.exceptions.RequestException as e:
            st.error(f"🌐 인터넷 검색 요청 실패: {str(e)}")
            return []
        except Exception as e:
            st.error(f"🌐 인터넷 검색 중 오류 발생: {str(e)}")
            return []
    
    def format_search_results_for_llm(self, search_results: List[Dict]) -> str:
        """검색 결과를 LLM이 처리하기 좋은 형태로 포맷팅"""
        if not search_results:
            return "인터넷 검색 결과가 없습니다."
        
        formatted_text = "=== 인터넷 검색 결과 ===\n\n"
        
        for i, result in enumerate(search_results, 1):
            formatted_text += f"검색 결과 {i}:\n"
            formatted_text += f"제목: {result['title']}\n"
            formatted_text += f"출처: {result['source']}\n"
            formatted_text += f"내용: {result['snippet']}\n"
            formatted_text += f"링크: {result['link']}\n"
            formatted_text += "-" * 50 + "\n\n"
        
        return formatted_text
    
    def assess_search_reliability(self, search_results: List[Dict], query: str) -> Dict:
        """검색 결과의 신뢰성을 평가"""
        if not search_results:
            return {
                'reliability_score': 0,
                'reliability_level': 'unreliable',
                'assessment_reason': '검색 결과가 없습니다',
                'disclaimer_needed': True
            }
        
        reliability_score = 0
        assessment_factors = []
        
        # IT 관련 신뢰할 만한 출처 패턴
        trusted_sources = [
            'microsoft.com', 'docs.microsoft.com', 'technet.microsoft.com',
            'stackoverflow.com', 'serverfault.com', 'superuser.com',
            'github.com', 'redis.io', 'apache.org', 'oracle.com',
            'aws.amazon.com', 'cloud.google.com', 'azure.microsoft.com',
            'ibm.com', 'redhat.com', 'ubuntu.com', 'centos.org',
            'cisco.com', 'vmware.com', 'docker.com', 'kubernetes.io',
            'elastic.co', 'mongodb.com', 'postgresql.org', 'mysql.com',
            'itworld.co.kr', 'zdnet.co.kr', 'ciokorea.com'
        ]
        
        # 기술 문서/포럼 키워드
        technical_indicators = [
            'documentation', 'troubleshooting', 'configuration', 'tutorial',
            'guide', 'manual', 'best practice', 'solution', 'fix',
            '문서', '가이드', '매뉴얼', '해결', '설정', '구성'
        ]
        
        # 검색 결과 분석
        for result in search_results:
            source = result.get('source', '').lower()
            title = result.get('title', '').lower()
            snippet = result.get('snippet', '').lower()
            
            # 신뢰할 만한 출처 점수
            if any(trusted_source in source for trusted_source in trusted_sources):
                reliability_score += 30
                assessment_factors.append(f"신뢰할 만한 출처: {result.get('source', '')}")
            
            # 기술 문서 관련 키워드 점수
            tech_keyword_count = sum(1 for keyword in technical_indicators 
                                   if keyword in title or keyword in snippet)
            if tech_keyword_count > 0:
                reliability_score += tech_keyword_count * 10
                assessment_factors.append(f"기술 문서 관련 키워드 {tech_keyword_count}개 발견")
            
            # 질문과의 관련성 점수
            query_words = set(query.lower().split())
            result_words = set(title.split() + snippet.split())
            relevance = len(query_words.intersection(result_words)) / len(query_words)
            
            if relevance > 0.3:
                reliability_score += relevance * 20
                assessment_factors.append(f"질문과의 관련성: {relevance:.2f}")
        
        # 신뢰성 수준 결정
        if reliability_score >= 80:
            reliability_level = 'high'
            disclaimer_needed = False
        elif reliability_score >= 50:
            reliability_level = 'medium'
            disclaimer_needed = True
        elif reliability_score >= 20:
            reliability_level = 'low'
            disclaimer_needed = True
        else:
            reliability_level = 'unreliable'
            disclaimer_needed = True
        
        return {
            'reliability_score': reliability_score,
            'reliability_level': reliability_level,
            'assessment_reason': '; '.join(assessment_factors) if assessment_factors else '신뢰성 지표 부족',
            'disclaimer_needed': disclaimer_needed
        }
    
    def should_use_internet_search(self, query_type: str, documents: List[Dict], query: str) -> bool:
        """인터넷 검색 사용 여부 결정"""
        # repair, cause 타입이고 관련 문서가 없거나 매우 적은 경우
        if query_type in ['repair', 'cause']:
            if not documents or len(documents) == 0:
                return True
            
            # 문서가 있더라도 품질이 낮은 경우
            high_quality_docs = [doc for doc in documents if doc.get('quality_tier') in ['Premium', 'Standard']]
            if len(high_quality_docs) == 0:
                return True
        
        return False
    
    def generate_reliability_disclaimer(self, reliability_assessment: Dict, query_type: str) -> str:
        """신뢰성 평가 결과에 따른 면책 조항 생성"""
        reliability_level = reliability_assessment['reliability_level']
        
        if reliability_level == 'high':
            return ""  # 고신뢰성 - 면책 조항 불필요
        
        elif reliability_level == 'medium':
            disclaimer = "⚠️ **정확한 정보는 찾을 수 없지만, 일반적으로 다음과 같은 확인이 필요합니다:**\n\n"
            
        elif reliability_level == 'low':
            disclaimer = "⚠️ **신뢰할 만한 구체적 정보를 찾기 어려우나, 일반적인 접근 방법으로는 다음과 같은 확인이 권장됩니다:**\n\n"
            
        else:  # unreliable
            disclaimer = "⚠️ **정확한 기술 정보를 찾을 수 없어 일반적인 IT 원칙에 따른 접근이 필요합니다:**\n\n"
        
        return disclaimer
    
    def generate_internet_search_response(self, azure_openai_client, query: str, service_name: str, search_results: List[Dict], model_name: str, query_type: str) -> str:
        """인터넷 검색 결과를 바탕으로 LLM 응답 생성 - 신뢰성 검증 포함"""
        try:
            # 신뢰성 평가 실행
            reliability_assessment = self.assess_search_reliability(search_results, query)
            
            # 검색 결과 포맷팅
            search_context = self.format_search_results_for_llm(search_results)
            
            # 신뢰성에 따른 면책 조항 생성
            disclaimer = self.generate_reliability_disclaimer(reliability_assessment, query_type)
            
            # 쿼리 타입별 시스템 프롬프트 (신뢰성 고려)
            if query_type == 'repair':
                if reliability_assessment['reliability_level'] in ['high', 'medium']:
                    system_prompt = """당신은 IT 트러블슈팅 전문가입니다. 
인터넷 검색 결과를 바탕으로 사용자의 복구방법 질문에 대해 실용적이고 구체적인 답변을 제공해주세요.
답변은 한국어로 작성하고, 단계별로 명확하게 설명해주세요.
검색 결과의 출처도 함께 언급해주세요."""
                else:
                    system_prompt = """당신은 IT 트러블슈팅 전문가입니다. 
제한적인 검색 결과를 바탕으로 일반적인 IT 복구 원칙에 따른 안전한 접근 방법을 제공해주세요.
구체적인 단계보다는 확인해야 할 사항들과 일반적인 해결 방향을 제시해주세요.
답변은 한국어로 작성하고, 추가 확인이 필요한 사항을 명시해주세요."""
                
            elif query_type == 'cause':
                if reliability_assessment['reliability_level'] in ['high', 'medium']:
                    system_prompt = """당신은 IT 장애 분석 전문가입니다. 
인터넷 검색 결과를 바탕으로 사용자의 장애 원인 질문에 대해 체계적이고 분석적인 답변을 제공해주세요.
가능한 원인들을 우선순위별로 정리하고, 각 원인에 대한 설명을 포함해주세요.
답변은 한국어로 작성하고, 검색 결과의 출처도 함께 언급해주세요."""
                else:
                    system_prompt = """당신은 IT 장애 분석 전문가입니다. 
제한적인 검색 결과를 바탕으로 일반적인 장애 원인 분석 접근법을 제공해주세요.
구체적인 원인보다는 확인해야 할 요소들과 진단 방향을 제시해주세요.
답변은 한국어로 작성하고, 추가 조사가 필요한 사항을 명시해주세요."""
            
            else:
                if reliability_assessment['reliability_level'] in ['high', 'medium']:
                    system_prompt = """당신은 IT 전문가입니다. 
인터넷 검색 결과를 바탕으로 사용자의 질문에 대해 정확하고 유용한 답변을 제공해주세요.
답변은 한국어로 작성하고, 검색 결과의 출처도 함께 언급해주세요."""
                else:
                    system_prompt = """당신은 IT 전문가입니다. 
제한적인 검색 결과를 바탕으로 일반적인 IT 원칙에 따른 접근 방법을 제공해주세요.
구체적인 해답보다는 확인해야 할 사항들과 일반적인 방향을 제시해주세요.
답변은 한국어로 작성하고, 추가 확인이 필요한 사항을 명시해주세요."""

            user_prompt = f"""
다음 인터넷 검색 결과를 참고하여 질문에 답변해주세요:

{search_context}

질문: {query}
서비스명: {service_name or '명시되지 않음'}

신뢰성 평가:
- 신뢰성 점수: {reliability_assessment['reliability_score']}/100
- 신뢰성 수준: {reliability_assessment['reliability_level']}
- 평가 근거: {reliability_assessment['assessment_reason']}

답변 요구사항:
1. 신뢰성 수준에 맞는 적절한 답변 제공
2. 주요 포인트는 **굵은 글씨**로 강조
3. 신뢰성이 낮은 경우 일반적인 확인 사항 중심으로 답변
4. 참고한 출처 정보 포함 (신뢰할 만한 출처 우선)
5. 답변 마지막에 "※ 이 답변은 인터넷 검색 결과를 바탕으로 생성되었습니다." 추가

답변:"""

            # LLM 응답 생성
            response = azure_openai_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=1500
            )
            
            llm_response = response.choices[0].message.content
            
            # 신뢰성이 낮은 경우 면책 조항을 답변 앞에 추가
            if disclaimer:
                final_response = disclaimer + llm_response
            else:
                final_response = llm_response
            
            # 신뢰성 정보를 답변 하단에 추가
            reliability_info = f"""

---
**🔍 검색 결과 신뢰성 평가**
- **신뢰성 수준**: {reliability_assessment['reliability_level'].upper()} ({reliability_assessment['reliability_score']}/100점)
- **평가 근거**: {reliability_assessment['assessment_reason']}
- **권장사항**: {'신뢰할 만한 결과로 참고 가능' if reliability_assessment['reliability_level'] == 'high' 
                else '추가 확인 및 전문가 상담 권장' if reliability_assessment['reliability_level'] == 'medium'
                else '일반적 접근법으로 활용, 구체적 환경에서 재검증 필요' if reliability_assessment['reliability_level'] == 'low'
                else '참고용으로만 활용, 전문가 상담 필수'}
"""
            
            return final_response + reliability_info
            
        except Exception as e:
            st.error(f"🌐 인터넷 검색 기반 응답 생성 실패: {str(e)}")
            error_response = f"""⚠️ **정확한 정보는 찾을 수 없지만, 일반적으로 다음과 같은 확인이 필요합니다:**

죄송합니다. 인터넷 검색 결과를 처리하는 중 오류가 발생했습니다: {str(e)}

**일반적인 IT 문제 해결 접근법:**
1. **문제 상황 정확히 파악**: 오류 메시지, 로그, 발생 시점 확인
2. **기본 점검**: 네트워크 연결, 서비스 상태, 리소스 사용량 확인  
3. **단계적 진단**: 간단한 해결책부터 복잡한 방법까지 순차 적용
4. **전문가 상담**: 복잡한 문제는 해당 분야 전문가와 협의

※ 구체적인 환경 정보와 함께 다시 문의하시면 더 정확한 답변을 드릴 수 있습니다.

---
**🔍 검색 결과 신뢰성 평가**
- **신뢰성 수준**: ERROR (처리 오류 발생)
- **권장사항**: 전문가 상담 및 공식 문서 참조 필요
"""
            return error_response