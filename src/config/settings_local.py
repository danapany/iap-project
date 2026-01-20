import os
from dotenv import load_dotenv

class AppConfigLocal:
    def __init__(self):
        load_dotenv()
        
        # Azure OpenAI 설정
        self.azure_openai_endpoint = os.getenv("OPENAI_ENDPOINT")
        self.azure_openai_key = os.getenv("OPENAI_KEY")
        self.azure_openai_model = os.getenv("CHAT_MODEL", "iap-gpt-4o-mini")
        self.azure_openai_api_version = os.getenv("OPENAI_API_VERSION", "2024-02-01")
        
        # 임베딩 설정
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")
        self.embedding_api_version = os.getenv("EMBEDDING_API_VERSION", "2024-02-01")
        
        # 검색 설정
        self.search_endpoint = os.getenv("SEARCH_ENDPOINT")
        self.search_key = os.getenv("SEARCH_API_KEY")
        self.search_index = os.getenv("INDEX_REBUILD_NAME", "iap-incident-index")
        
        # ★★★ 추가: 이상징후 인덱스 설정 ★★★
        self.search_index_anomaly = os.getenv("INDEX_REBUILD_NAME2", "iap-anomaly-index")
        
        # 벡터 하이브리드 검색 파라미터
        self.vector_weight = float(os.getenv("VECTOR_WEIGHT", "0.5"))
        self.text_weight = float(os.getenv("TEXT_WEIGHT", "0.5"))
        self.use_semantic_reranker = os.getenv("USE_SEMANTIC_RERANKER", "true").lower() == "true"
        self.rrf_k = int(os.getenv("RRF_K", "60"))
        
        # 벡터 검색 최적화 설정
        self.vector_top_k = int(os.getenv("VECTOR_TOP_K", "50"))
        self.text_top_k = int(os.getenv("TEXT_TOP_K", "50"))
        self.final_top_k = int(os.getenv("FINAL_TOP_K", "20"))
        
        # 임베딩 캐싱 설정
        self.enable_embedding_cache = os.getenv("ENABLE_EMBEDDING_CACHE", "true").lower() == "true"
        self.embedding_cache_ttl = int(os.getenv("EMBEDDING_CACHE_TTL", "3600"))
        
        # 기본 임계값들 (장애내역용)
        self.search_score_threshold = 0.20
        self.reranker_score_threshold = 1.8
        self.hybrid_score_threshold = 0.35
        self.semantic_score_threshold = 0.25
        self.max_initial_results = 50
        self.max_final_results = 15
        
        # ★★★ 추가: 이상징후 전용 임계값 (더 엄격) ★★★
        self.anomaly_search_threshold = 0.35  # 장애: 0.20 → 이상징후: 0.35
        self.anomaly_reranker_threshold = 2.5  # 장애: 1.8 → 이상징후: 2.5
        self.anomaly_hybrid_threshold = 0.50   # 장애: 0.35 → 이상징후: 0.50
        self.anomaly_semantic_threshold = 0.40 # 장애: 0.25 → 이상징후: 0.40
        self.anomaly_max_results = 10          # 장애: 15 → 이상징후: 10
        self.anomaly_vector_similarity_threshold = 0.75  # 장애: 0.5-0.7 → 이상징후: 0.75
    
    def get_vector_search_config(self, query_type="default", is_anomaly=False):
        """
        쿼리 타입별 벡터 검색 설정 반환
        
        Args:
            query_type: 쿼리 타입 ("repair", "inquiry", "statistics", "default")
            is_anomaly: 이상징후 검색 여부 (True면 더 엄격한 기준 적용)
        """
        # ★★★ 이상징후는 무조건 엄격한 기준 적용 ★★★
        if is_anomaly:
            return {
                "vector_weight": 0.7,  # 벡터 검색 비중 높임
                "text_weight": 0.3,
                "use_semantic_reranker": True,
                "vector_similarity_threshold": self.anomaly_vector_similarity_threshold,
                "description": "이상징후 - 엄격한 유사성 기준"
            }
        
        # 장애내역은 기존 로직 유지
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
        """쿼리에 따른 최적 검색 모드 결정"""
        stats_keywords = ['건수', '통계', '현황', '분포', '연도별', '월별']
        service_keywords = ['API', 'ERP', 'OTP', 'SMS', 'VPN']
        
        is_stats_query = any(keyword in query_text.lower() for keyword in stats_keywords)
        has_service_keyword = any(keyword in query_text for keyword in service_keywords)
        
        if is_stats_query:
            return "text_primary"
        elif query_type == "repair" and not has_service_keyword:
            return "vector_primary"
        else:
            return "hybrid_balanced"

    def validate_config(self):
        """필수 설정값 검증"""
        required_fields = [
            self.azure_openai_endpoint, 
            self.azure_openai_key, 
            self.search_endpoint, 
            self.search_key, 
            self.search_index,
            # ★★★ 추가: 이상징후 인덱스 검증 ★★★
            self.search_index_anomaly
        ]
        return all(required_fields)
    
    def get_env_status(self):
        """환경변수 설정 상태 확인"""
        return {k: "✅" if v else "❌" for k, v in {
            "OPENAI_ENDPOINT": self.azure_openai_endpoint,
            "OPENAI_KEY": self.azure_openai_key,
            "SEARCH_ENDPOINT": self.search_endpoint,
            "SEARCH_API_KEY": self.search_key,
            "INDEX_REBUILD_NAME": self.search_index,
            # ★★★ 추가: 이상징후 인덱스 상태 확인 ★★★
            "INDEX_REBUILD_NAME2": self.search_index_anomaly,
            "EMBEDDING_MODEL": self.embedding_model
        }.items()}
    
    def get_dynamic_thresholds(self, query_type, query_text, is_anomaly=False):
        """
        동적 임계값 설정
        
        Args:
            query_type: 쿼리 타입
            query_text: 쿼리 텍스트
            is_anomaly: 이상징후 검색 여부
        """
        # ★★★ 이상징후는 엄격한 임계값 적용 ★★★
        if is_anomaly:
            base_thresholds = {
                'search_threshold': self.anomaly_search_threshold,
                'reranker_threshold': self.anomaly_reranker_threshold,
                'hybrid_threshold': self.anomaly_hybrid_threshold,
                'semantic_threshold': self.anomaly_semantic_threshold,
                'max_results': self.anomaly_max_results
            }
        else:
            # 장애내역은 기존 임계값 사용
            base_thresholds = {
                'search_threshold': self.search_score_threshold,
                'reranker_threshold': self.reranker_score_threshold,
                'hybrid_threshold': self.hybrid_score_threshold,
                'semantic_threshold': self.semantic_score_threshold,
                'max_results': self.max_final_results
            }
        
        # 벡터 검색 설정 추가
        vector_config = self.get_vector_search_config(query_type, is_anomaly)
        base_thresholds.update({
            'vector_weight': vector_config['vector_weight'],
            'text_weight': vector_config['text_weight'],
            'use_semantic_reranker': vector_config['use_semantic_reranker'],
            'vector_similarity_threshold': vector_config['vector_similarity_threshold'],
            'search_mode': self.get_search_mode_for_query(query_type, query_text)
        })
        
        # 장애내역 쿼리 타입별 특화 설정 (이상징후는 무시하고 엄격한 기준만 적용)
        if not is_anomaly:
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
        else:
            # 이상징후는 항상 'accuracy_first' 모드
            base_thresholds['processing_mode'] = 'accuracy_first'
        
        return base_thresholds