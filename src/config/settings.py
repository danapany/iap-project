import os
from dotenv import load_dotenv

class AppConfig:
    """애플리케이션 설정 클래스"""
    
    def __init__(self):
        # .env 파일 로드
        load_dotenv()
        
        # Azure OpenAI 설정
        self.azure_openai_endpoint = os.getenv("OPENAI_ENDPOINT")
        self.azure_openai_key = os.getenv("OPENAI_KEY")
        self.azure_openai_model = os.getenv("CHAT_MODEL", "iap-gpt-4o-mini")
        self.azure_openai_api_version = os.getenv("OPENAI_API_VERSION", "2024-02-01")
        
        # Azure Search 설정
        self.search_endpoint = os.getenv("SEARCH_ENDPOINT")
        self.search_key = os.getenv("SEARCH_API_KEY")
        self.search_index = os.getenv("INDEX_REBUILD_NAME")
        
        # SerpApi 설정 (Google 검색)
        self.serpapi_key = os.getenv("SERPAPI_API_KEY")
        
        # 검색 품질 임계값 설정
        self.search_score_threshold = 0.3
        self.reranker_score_threshold = 1.5
        self.hybrid_score_threshold = 0.5
        self.max_initial_results = 20
        self.max_final_results = 8
    
    def validate_config(self):
        """필수 설정값 검증"""
        required_vars = [
            self.azure_openai_endpoint,
            self.azure_openai_key,
            self.search_endpoint,
            self.search_key,
            self.search_index
        ]
        return all(required_vars)
    
    def has_serpapi_config(self):
        """SerpApi 설정 검증"""
        return bool(self.serpapi_key)
    
    def get_env_status(self):
        """환경변수 상태 반환"""
        return {
            "OPENAI_ENDPOINT": "✅" if self.azure_openai_endpoint else "❌",
            "OPENAI_KEY": "✅" if self.azure_openai_key else "❌",
            "SEARCH_ENDPOINT": "✅" if self.search_endpoint else "❌",
            "SEARCH_API_KEY": "✅" if self.search_key else "❌",
            "INDEX_REBUILD_NAME": "✅" if self.search_index else "❌",
            "SERPAPI_API_KEY": "✅" if self.serpapi_key else "❌ (선택사항)"
        }
    
    def get_dynamic_thresholds(self, query_type, query_text):
        """쿼리 타입과 내용에 따라 동적으로 임계값 조정"""
        # 년도별, 통계성 쿼리 감지
        year_keywords = ['년도', '년', '월별', '기간', '현황', '통계', '건수', '발생', '발생일자', '언제']
        is_statistical_query = any(keyword in query_text for keyword in year_keywords)
        
        if is_statistical_query or query_type == "default":
            # 통계성 쿼리나 일반 쿼리는 더 관대한 기준 적용
            return {
                'search_threshold': 0.2,
                'reranker_threshold': 1.0,
                'hybrid_threshold': 0.4,
                'max_results': 10
            }
        elif query_type in ["repair", "cause", "similar"]:
            # 복구방법, 장애원인, 유사사례는 품질 중심
            return {
                'search_threshold': 0.4,
                'reranker_threshold': 1.8,
                'hybrid_threshold': 0.6,
                'max_results': 5
            }
        else:
            # 기본값
            return {
                'search_threshold': self.search_score_threshold,
                'reranker_threshold': self.reranker_score_threshold,
                'hybrid_threshold': self.hybrid_score_threshold,
                'max_results': self.max_final_results
            }