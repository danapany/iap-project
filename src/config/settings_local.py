import os
from dotenv import load_dotenv

class AppConfigLocal:
    def __init__(self):
        load_dotenv()
        
        # 기존 설정들
        self.azure_openai_endpoint = os.getenv("OPENAI_ENDPOINT")
        self.azure_openai_key = os.getenv("OPENAI_KEY")
        self.azure_openai_model = os.getenv("CHAT_MODEL", "iap-gpt-4o-mini")
        self.azure_openai_api_version = os.getenv("OPENAI_API_VERSION", "2024-02-01")
        
        # Vector 검색 관련 설정들
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")
        self.embedding_api_version = os.getenv("EMBEDDING_API_VERSION", "2024-02-01")
        
        # 검색 설정
        self.search_endpoint = os.getenv("SEARCH_ENDPOINT")
        self.search_key = os.getenv("SEARCH_API_KEY")
        self.search_index = os.getenv("INDEX_REBUILD_NAME", "iap-incident-index")
        
        # Vector 하이브리드 검색 파라미터
        self.vector_weight = float(os.getenv("VECTOR_WEIGHT", "0.5"))
        self.text_weight = float(os.getenv("TEXT_WEIGHT", "0.5"))
        self.use_semantic_reranker = os.getenv("USE_SEMANTIC_RERANKER", "true").lower() == "true"
        
        # RRF (Reciprocal Rank Fusion) 설정
        self.rrf_k = int(os.getenv("RRF_K", "60"))
        
        # 벡터 검색 최적화 설정
        self.vector_top_k = int(os.getenv("VECTOR_TOP_K", "50"))
        self.text_top_k = int(os.getenv("TEXT_TOP_K", "50"))
        self.final_top_k = int(os.getenv("FINAL_TOP_K", "20"))
        
        # 임베딩 캐싱 설정
        self.enable_embedding_cache = os.getenv("ENABLE_EMBEDDING_CACHE", "true").lower() == "true"
        self.embedding_cache_ttl = int(os.getenv("EMBEDDING_CACHE_TTL", "3600"))
        
        # 기존 임계값들
        self.search_score_threshold = 0.20
        self.reranker_score_threshold = 1.8
        self.hybrid_score_threshold = 0.35
        self.semantic_score_threshold = 0.25
        self.max_initial_results = 50
        self.max_final_results = 15
        
        # LangSmith 설정
        self.langchain_api_key = os.getenv("LANGCHAIN_API_KEY")
        self.langsmith_tracing = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
        self.langchain_project = os.getenv("LANGCHAIN_PROJECT", "trouble-chaser-chatbot")
    
    def get_vector_search_config(self, query_type="default"):
        """쿼리 타입별 벡터 검색 설정 반환 - 4가지 타입으로 통합"""
        configs = {
            "repair": {
                "vector_weight": 0.6,
                "text_weight": 0.4,
                "use_semantic_reranker": True,
                "vector_similarity_threshold": 0.7,
                "description": "복구방법/원인/유사사례 통합 - 의미적 유사성 우선"
            },
            "inquiry": {
                "vector_weight": 0.3,
                "text_weight": 0.7,
                "use_semantic_reranker": False,
                "vector_similarity_threshold": 0.5,
                "description": "조회/목록 - 키워드 매칭 우선"
            },
            "statistics": {
                "vector_weight": 0.2,
                "text_weight": 0.8,
                "use_semantic_reranker": False,
                "vector_similarity_threshold": 0.4,
                "description": "통계 - 정확한 키워드 매칭"
            },
            "default": {
                "vector_weight": self.vector_weight,
                "text_weight": self.text_weight,
                "use_semantic_reranker": self.use_semantic_reranker,
                "vector_similarity_threshold": 0.5,
                "description": "기본 - 하이브리드 검색"
            }
        }
        return configs.get(query_type, configs["default"])
    
    def get_search_mode_for_query(self, query_type, query_text):
        """쿼리에 따른 최적 검색 모드 결정 - 4가지 타입으로 수정"""
        # 통계성 키워드 체크
        stats_keywords = ['건수', '통계', '현황', '분포', '연도별', '월별']
        is_stats_query = any(keyword in query_text.lower() for keyword in stats_keywords)
        
        # 서비스명 정확성이 중요한 쿼리 체크
        service_keywords = ['API', 'ERP', 'OTP', 'SMS', 'VPN']
        has_service_keyword = any(keyword in query_text for keyword in service_keywords)
        
        if is_stats_query:
            return "text_primary"
        elif query_type == "repair" and not has_service_keyword:
            return "vector_primary"
        else:
            return "hybrid_balanced"

    def validate_config(self):
        required_fields = [
            self.azure_openai_endpoint, 
            self.azure_openai_key, 
            self.search_endpoint, 
            self.search_key, 
            self.search_index
        ]
        return all(required_fields)
    
    def get_env_status(self):
        return {k: "✅" if v else "❌" for k, v in {
            "OPENAI_ENDPOINT": self.azure_openai_endpoint,
            "OPENAI_KEY": self.azure_openai_key,
            "SEARCH_ENDPOINT": self.search_endpoint,
            "SEARCH_API_KEY": self.search_key,
            "INDEX_REBUILD_NAME": self.search_index,
            "EMBEDDING_MODEL": self.embedding_model,
            "LANGCHAIN_API_KEY": self.langchain_api_key,
            "LANGSMITH_TRACING": self.langsmith_tracing,
            "LANGCHAIN_PROJECT": self.langchain_project
        }.items()}
    
    def setup_langsmith(self):
        if self.langchain_api_key and self.langsmith_tracing:
            os.environ.update({
                "LANGCHAIN_API_KEY": self.langchain_api_key,
                "LANGCHAIN_TRACING_V2": "true",
                "LANGCHAIN_PROJECT": self.langchain_project
            })
            return True
        return False
    
    def get_dynamic_thresholds(self, query_type, query_text):
        """동적 임계값 설정 - 벡터 검색 통합 + 4가지 타입으로 수정"""
        base_thresholds = {
            'search_threshold': self.search_score_threshold,
            'reranker_threshold': self.reranker_score_threshold,
            'hybrid_threshold': self.hybrid_score_threshold,
            'semantic_threshold': self.semantic_score_threshold,
            'max_results': self.max_final_results
        }
        
        # 벡터 검색 설정 추가
        vector_config = self.get_vector_search_config(query_type)
        base_thresholds.update({
            'vector_weight': vector_config['vector_weight'],
            'text_weight': vector_config['text_weight'],
            'use_semantic_reranker': vector_config['use_semantic_reranker'],
            'vector_similarity_threshold': vector_config['vector_similarity_threshold'],
            'search_mode': self.get_search_mode_for_query(query_type, query_text)
        })
        
        # 쿼리 타입별 특화 설정 (4가지 타입)
        specialized_configs = {
            "repair": {
                'search_threshold': 0.25,
                'reranker_threshold': 2.2,
                'hybrid_threshold': 0.45,
                'semantic_threshold': 0.30,
                'max_results': 10,
                'processing_mode': 'accuracy_first'
            },
            "inquiry": {
                'search_threshold': 0.15,
                'reranker_threshold': 1.5,
                'hybrid_threshold': 0.30,
                'semantic_threshold': 0.20,
                'max_results': 20,
                'processing_mode': 'coverage_first'
            },
            "statistics": {
                'search_threshold': 0.10,
                'reranker_threshold': 1.0,
                'hybrid_threshold': 0.20,
                'semantic_threshold': 0.15,
                'max_results': 50,
                'processing_mode': 'statistics_complete'
            },
            "default": {
                **base_thresholds,
                'processing_mode': 'balanced'
            }
        }
        
        config = specialized_configs.get(query_type, specialized_configs["default"])
        base_thresholds.update(config)
        return base_thresholds