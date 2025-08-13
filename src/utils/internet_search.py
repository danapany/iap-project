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
    
    def generate_internet_search_response(self, azure_openai_client, query: str, service_name: str, search_results: List[Dict], model_name: str, query_type: str) -> str:
        """인터넷 검색 결과를 바탕으로 LLM 응답 생성"""
        try:
            # 검색 결과 포맷팅
            search_context = self.format_search_results_for_llm(search_results)
            
            # 쿼리 타입별 시스템 프롬프트
            if query_type == 'repair':
                system_prompt = """당신은 IT 트러블슈팅 전문가입니다. 
인터넷 검색 결과를 바탕으로 사용자의 복구방법 질문에 대해 실용적이고 구체적인 답변을 제공해주세요.
답변은 한국어로 작성하고, 단계별로 명확하게 설명해주세요.
검색 결과의 출처도 함께 언급해주세요."""
                
            elif query_type == 'cause':
                system_prompt = """당신은 IT 장애 분석 전문가입니다. 
인터넷 검색 결과를 바탕으로 사용자의 장애 원인 질문에 대해 체계적이고 분석적인 답변을 제공해주세요.
가능한 원인들을 우선순위별로 정리하고, 각 원인에 대한 설명을 포함해주세요.
답변은 한국어로 작성하고, 검색 결과의 출처도 함께 언급해주세요."""
            
            else:
                system_prompt = """당신은 IT 전문가입니다. 
인터넷 검색 결과를 바탕으로 사용자의 질문에 대해 정확하고 유용한 답변을 제공해주세요.
답변은 한국어로 작성하고, 검색 결과의 출처도 함께 언급해주세요."""
            
            user_prompt = f"""
다음 인터넷 검색 결과를 참고하여 질문에 답변해주세요:

{search_context}

질문: {query}
서비스명: {service_name or '명시되지 않음'}

답변 요구사항:
1. 검색 결과를 바탕으로 구체적이고 실용적인 답변 제공
2. 주요 포인트는 **굵은 글씨**로 강조
3. 가능하면 단계별로 설명
4. 참고한 출처 정보 포함
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
            
            return response.choices[0].message.content
            
        except Exception as e:
            st.error(f"🌐 인터넷 검색 기반 응답 생성 실패: {str(e)}")
            return f"죄송합니다. 인터넷 검색 결과를 처리하는 중 오류가 발생했습니다: {str(e)}"