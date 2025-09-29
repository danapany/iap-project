import os
from dotenv import load_dotenv

class AppConfig:
    """웹 검색 기반 애플리케이션 설정 클래스"""
    
    def __init__(self):
        # .env 파일 로드
        load_dotenv()
        
        # Azure OpenAI 설정
        self.azure_openai_endpoint = os.getenv("OPENAI_ENDPOINT")
        self.azure_openai_key = os.getenv("OPENAI_KEY")
        self.azure_openai_model = os.getenv("CHAT_MODEL", "gpt-4o-mini")
        self.azure_openai_api_version = os.getenv("OPENAI_API_VERSION", "2024-02-01")
        
        # SerpApi 설정 (Google 검색 - 필수)
        self.serpapi_key = os.getenv("SERPAPI_API_KEY")
        
        # 웹 검색 품질 설정
        self.max_search_results = 8
        self.search_timeout = 10
        self.reliability_threshold = 50  # 신뢰성 점수 임계값
        
        # DEBUG 모드 설정 (기본값: False)
        self.debug_mode = False
    
    def validate_config(self):
        """필수 설정값 검증"""
        required_vars = [
            self.azure_openai_endpoint,
            self.azure_openai_key,
            self.serpapi_key  # 웹 검색 기반이므로 필수
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
            "SERPAPI_API_KEY": "✅" if self.serpapi_key else "❌ (필수)"
        }
    
    def get_search_quality_settings(self, query_type):
        """쿼리 타입에 따른 검색 품질 설정"""
        quality_settings = {
            'repair': {
                'max_results': 6,
                'reliability_threshold': 60,
                'search_keywords_boost': ['troubleshooting', 'fix', 'solution', 'error'],
                'trusted_domains_boost': ['docs.microsoft.com', 'stackoverflow.com', 'github.com']
            },
            'cause': {
                'max_results': 6,
                'reliability_threshold': 60,
                'search_keywords_boost': ['cause', 'root cause', 'analysis', 'debugging'],
                'trusted_domains_boost': ['docs.microsoft.com', 'technet.microsoft.com', 'serverfault.com']
            },
            'similar': {
                'max_results': 8,
                'reliability_threshold': 50,
                'search_keywords_boost': ['case study', 'example', 'similar issue', 'same problem'],
                'trusted_domains_boost': ['stackoverflow.com', 'serverfault.com', 'superuser.com']
            },
            'default': {
                'max_results': 8,
                'reliability_threshold': 50,
                'search_keywords_boost': ['guide', 'tutorial', 'documentation'],
                'trusted_domains_boost': ['docs.microsoft.com', 'developer.mozilla.org']
            }
        }
        return quality_settings.get(query_type, quality_settings['default'])