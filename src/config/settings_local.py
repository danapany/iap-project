import os
from dotenv import load_dotenv

class AppConfigLocal:
    def __init__(self):
        load_dotenv()
        self.azure_openai_endpoint = os.getenv("OPENAI_ENDPOINT")
        self.azure_openai_key = os.getenv("OPENAI_KEY")
        self.azure_openai_model = os.getenv("CHAT_MODEL", "iap-gpt-4o-mini")
        self.azure_openai_api_version = os.getenv("OPENAI_API_VERSION", "2024-02-01")
        self.search_endpoint = os.getenv("SEARCH_ENDPOINT")
        self.search_key = os.getenv("SEARCH_API_KEY")
        self.search_index = os.getenv("INDEX_REBUILD_NAME")
        self.langchain_api_key = os.getenv("LANGCHAIN_API_KEY")
        self.langsmith_tracing = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
        self.langchain_project = os.getenv("LANGCHAIN_PROJECT", "trouble-chaser-chatbot")
        self.search_score_threshold = 0.20
        self.reranker_score_threshold = 1.8
        self.hybrid_score_threshold = 0.35
        self.semantic_score_threshold = 0.25
        self.max_initial_results = 50
        self.max_final_results = 15
    
    def validate_config(self):
        return all([self.azure_openai_endpoint, self.azure_openai_key, self.search_endpoint, self.search_key, self.search_index])
    
    def get_env_status(self):
        return {k: "✅" if v else "❌" for k, v in {
            "OPENAI_ENDPOINT": self.azure_openai_endpoint, "OPENAI_KEY": self.azure_openai_key,
            "SEARCH_ENDPOINT": self.search_endpoint, "SEARCH_API_KEY": self.search_key,
            "INDEX_REBUILD_NAME": self.search_index, "LANGCHAIN_API_KEY": self.langchain_api_key,
            "LANGSMITH_TRACING": self.langsmith_tracing, "LANGCHAIN_PROJECT": self.langchain_project
        }.items()}
    
    def setup_langsmith(self):
        if self.langchain_api_key and self.langsmith_tracing:
            os.environ.update({"LANGCHAIN_API_KEY": self.langchain_api_key, "LANGCHAIN_TRACING_V2": "true", "LANGCHAIN_PROJECT": self.langchain_project})
            return True
        return False
    
    def get_langsmith_status(self):
        return {"enabled": self.langsmith_tracing and bool(self.langchain_api_key), "api_key_set": bool(self.langchain_api_key), "tracing_enabled": self.langsmith_tracing, "project_name": self.langchain_project}
    
    def get_dynamic_thresholds(self, query_type, query_text):
        year_keywords = ['년도', '년', '월별', '기간', '현황', '통계', '건수', '발생', '발생일자', '언제']
        is_statistical_query = any(k in query_text for k in year_keywords)
        complex_keywords = ['보험', '가입', '불가', '접속', '단말', '휴대폰', '실패', '안됨', '오류', '사용자', '로그인', '결제']
        is_complex_query = any(k in query_text for k in complex_keywords)
        
        base = {'search_threshold': self.search_score_threshold, 'reranker_threshold': self.reranker_score_threshold, 'hybrid_threshold': self.hybrid_score_threshold, 'semantic_threshold': self.semantic_score_threshold, 'max_results': self.max_final_results}
        
        thresholds = {
            "repair": {'search_threshold': 0.30 if is_complex_query else 0.25, 'reranker_threshold': 2.5 if is_complex_query else 2.2, 'hybrid_threshold': 0.50 if is_complex_query else 0.45, 'semantic_threshold': 0.35 if is_complex_query else 0.30, 'max_results': 8 if is_complex_query else 10, 'processing_mode': 'accuracy_first', 'description': '복구방법 정확성 최우선 - LLM 관련성 검증' if is_complex_query else '복구방법 정확성 우선 - LLM 관련성 검증'},
            "cause": {'search_threshold': 0.28, 'reranker_threshold': 2.3, 'hybrid_threshold': 0.48, 'semantic_threshold': 0.32, 'max_results': 8, 'processing_mode': 'accuracy_first', 'description': '장애원인 정확성 우선 - 키워드 매칭 강화'},
            "similar": {'search_threshold': 0.15, 'reranker_threshold': 1.5, 'hybrid_threshold': 0.30, 'semantic_threshold': 0.20, 'max_results': 15, 'processing_mode': 'coverage_first', 'description': '유사사례 포괄성 우선 - 의미적 유사성 기반'},
            "statistics": {'search_threshold': 0.10, 'reranker_threshold': 1.0, 'hybrid_threshold': 0.20, 'semantic_threshold': 0.15, 'max_results': 50, 'processing_mode': 'statistics_complete', 'description': '통계 완전성 우선 - 모든 관련 데이터 수집 및 정확한 집계'},
            "default": {'search_threshold': 0.12, 'reranker_threshold': 1.3, 'hybrid_threshold': 0.25, 'semantic_threshold': 0.18, 'max_results': 20, 'processing_mode': 'coverage_first', 'description': '일반/통계 포괄성 우선 - 광범위한 검색'} if is_statistical_query else {**base, 'processing_mode': 'balanced', 'description': '균형잡힌 처리'}
        }
        return thresholds.get(query_type, thresholds["default"])
    
    def get_query_optimization_config(self, query_type):
        configs = {
            "repair": {'use_llm_validation': True, 'keyword_relevance_weight': 0.3, 'semantic_boost_factor': 0.4, 'quality_over_quantity': True, 'strict_service_matching': True},
            "cause": {'use_llm_validation': True, 'keyword_relevance_weight': 0.4, 'semantic_boost_factor': 0.3, 'quality_over_quantity': True, 'strict_service_matching': True},
            "similar": {'use_llm_validation': False, 'keyword_relevance_weight': 0.1, 'semantic_boost_factor': 0.6, 'quality_over_quantity': False, 'strict_service_matching': False},
            "statistics": {'use_llm_validation': False, 'keyword_relevance_weight': 0.05, 'semantic_boost_factor': 0.2, 'quality_over_quantity': False, 'strict_service_matching': False, 'ensure_completeness': True, 'aggregate_all_matches': True},
            "default": {'use_llm_validation': False, 'keyword_relevance_weight': 0.1, 'semantic_boost_factor': 0.5, 'quality_over_quantity': False, 'strict_service_matching': False}
        }
        return configs.get(query_type, configs["default"])
    
    def get_processing_mode_info(self):
        return {
            'accuracy_first': {'name': '정확성 우선', 'description': 'LLM 관련성 검증을 통한 최고 정확도', 'best_for': ['repair', 'cause'], 'features': ['LLM 문서 검증', '키워드 관련성 점수', '엄격한 필터링']},
            'coverage_first': {'name': '포괄성 우선', 'description': '의미적 유사성 기반 광범위한 검색', 'best_for': ['similar', 'default'], 'features': ['의미적 유사성 부스팅', '관대한 필터링', '포괄적 결과']},
            'statistics_complete': {'name': '통계 완전성', 'description': '정확한 통계 집계를 위한 완전한 데이터 수집', 'best_for': ['statistics'], 'features': ['모든 관련 데이터 수집', '정확한 집계', '일관성 검증', '중복 제거']},
            'balanced': {'name': '균형 처리', 'description': '정확성과 포괄성의 최적 균형', 'best_for': ['모든 쿼리 타입'], 'features': ['적응형 필터링', '균형잡힌 임계값', '안정적 결과']}
        }
    
    def get_performance_metrics(self):
        return {
            'accuracy_targets': {'repair': 0.85, 'cause': 0.80, 'similar': 0.70, 'statistics': 0.95, 'default': 0.75},
            'response_time_targets': {'accuracy_first': 8.0, 'coverage_first': 5.0, 'statistics_complete': 10.0, 'balanced': 6.0},
            'result_count_targets': {
                'repair': {'min': 3, 'max': 10, 'optimal': 6}, 'cause': {'min': 3, 'max': 10, 'optimal': 6},
                'similar': {'min': 5, 'max': 20, 'optimal': 12}, 'statistics': {'min': 10, 'max': 100, 'optimal': 50},
                'default': {'min': 5, 'max': 25, 'optimal': 15}
            }
        }
    
    def validate_query_processing(self, query_type, processing_mode, result_count):
        targets = self.get_performance_metrics()['result_count_targets'].get(query_type, {'min': 1, 'max': 50, 'optimal': 10})
        validation_result = {'is_valid': True, 'warnings': [], 'recommendations': []}
        
        if result_count < targets['min']:
            validation_result['warnings'].append(f"결과 수가 최소 기준({targets['min']}개)보다 적습니다.")
            validation_result['recommendations'].append("검색 임계값을 낮춰보세요.")
        if result_count > targets['max']:
            validation_result['warnings'].append(f"결과 수가 최대 기준({targets['max']}개)을 초과했습니다.")
            validation_result['recommendations'].append("검색 임계값을 높여보세요.")
        
        mode_mapping = {'repair': 'accuracy_first', 'cause': 'accuracy_first', 'similar': 'coverage_first', 'default': 'coverage_first', 'statistics': 'statistics_complete'}
        expected_mode = mode_mapping.get(query_type)
        if expected_mode and processing_mode != expected_mode:
            validation_result['recommendations'].append(f"{query_type} 쿼리는 {expected_mode} 모드를 권장합니다.")
        
        return validation_result