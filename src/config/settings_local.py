import os
from dotenv import load_dotenv

class AppConfigLocal:
    """애플리케이션 설정 클래스"""
    
    def __init__(self):
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
        
        # LangSmith 설정
        self.langchain_api_key = os.getenv("LANGCHAIN_API_KEY")
        self.langsmith_tracing = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
        self.langchain_project = os.getenv("LANGCHAIN_PROJECT", "trouble-chaser-chatbot")
        
        # 기본 검색 품질 임계값 설정
        self.search_score_threshold = 0.20
        self.reranker_score_threshold = 1.8
        self.hybrid_score_threshold = 0.35
        self.semantic_score_threshold = 0.25
        self.max_initial_results = 50
        self.max_final_results = 15
    
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
    
    def get_env_status(self):
        """환경변수 상태 반환"""
        return {
            "OPENAI_ENDPOINT": "✅" if self.azure_openai_endpoint else "❌",
            "OPENAI_KEY": "✅" if self.azure_openai_key else "❌",
            "SEARCH_ENDPOINT": "✅" if self.search_endpoint else "❌",
            "SEARCH_API_KEY": "✅" if self.search_key else "❌",
            "INDEX_REBUILD_NAME": "✅" if self.search_index else "❌",
            "LANGCHAIN_API_KEY": "✅" if self.langchain_api_key else "❌",
            "LANGSMITH_TRACING": "✅" if self.langsmith_tracing else "❌",
            "LANGCHAIN_PROJECT": "✅" if self.langchain_project else "❌"
        }
    
    def setup_langsmith(self):
        """LangSmith 환경 설정"""
        if self.langchain_api_key and self.langsmith_tracing:
            os.environ["LANGCHAIN_API_KEY"] = self.langchain_api_key
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_PROJECT"] = self.langchain_project
            return True
        return False
    
    def get_langsmith_status(self):
        """LangSmith 설정 상태 반환"""
        return {
            "enabled": self.langsmith_tracing and bool(self.langchain_api_key),
            "api_key_set": bool(self.langchain_api_key),
            "tracing_enabled": self.langsmith_tracing,
            "project_name": self.langchain_project
        }
    
    def get_dynamic_thresholds(self, query_type, query_text):
        """쿼리 타입과 내용에 따라 동적으로 임계값 조정"""
        
        # 특수 키워드 감지
        year_keywords = ['년도', '년', '월별', '기간', '현황', '통계', '건수', '발생', '발생일자', '언제']
        is_statistical_query = any(keyword in query_text for keyword in year_keywords)
        
        # 복잡한 장애 키워드 감지
        complex_keywords = ['보험', '가입', '불가', '접속', '단말', '휴대폰', '실패', '안됨', '오류', '사용자', '로그인', '결제']
        is_complex_query = any(keyword in query_text for keyword in complex_keywords)
        
        # 기본 임계값 설정
        base_thresholds = {
            'search_threshold': self.search_score_threshold,
            'reranker_threshold': self.reranker_score_threshold,
            'hybrid_threshold': self.hybrid_score_threshold,
            'semantic_threshold': self.semantic_score_threshold,
            'max_results': self.max_final_results
        }
        
        # 쿼리 타입별 최적화된 임계값 적용
        if query_type == "repair":
            # 복구방법 쿼리 - 정확성 최우선
            if is_complex_query:
                return {
                    'search_threshold': 0.30,
                    'reranker_threshold': 2.5,
                    'hybrid_threshold': 0.50,
                    'semantic_threshold': 0.35,
                    'max_results': 8,
                    'processing_mode': 'accuracy_first',
                    'description': '복구방법 정확성 최우선 - LLM 관련성 검증'
                }
            else:
                return {
                    'search_threshold': 0.25,
                    'reranker_threshold': 2.2,
                    'hybrid_threshold': 0.45,
                    'semantic_threshold': 0.30,
                    'max_results': 10,
                    'processing_mode': 'accuracy_first',
                    'description': '복구방법 정확성 우선 - LLM 관련성 검증'
                }
                
        elif query_type == "cause":
            # 장애원인 쿼리 - 정확성과 분석 품질 중시
            return {
                'search_threshold': 0.28,
                'reranker_threshold': 2.3,
                'hybrid_threshold': 0.48,
                'semantic_threshold': 0.32,
                'max_results': 8,
                'processing_mode': 'accuracy_first',
                'description': '장애원인 정확성 우선 - 키워드 매칭 강화'
            }
            
        elif query_type == "similar":
            # 유사사례 쿼리 - 포괄성과 의미적 유사성 중시
            return {
                'search_threshold': 0.15,
                'reranker_threshold': 1.5,
                'hybrid_threshold': 0.30,
                'semantic_threshold': 0.20,
                'max_results': 15,
                'processing_mode': 'coverage_first',
                'description': '유사사례 포괄성 우선 - 의미적 유사성 기반'
            }
        
        elif query_type == "statistics":
            # 🆕 통계 쿼리 - 완전성과 정확성 최우선
            return {
                'search_threshold': 0.10,  # 매우 낮은 임계값으로 모든 관련 데이터 수집
                'reranker_threshold': 1.0,  # 낮은 재정렬 임계값
                'hybrid_threshold': 0.20,   # 낮은 하이브리드 임계값
                'semantic_threshold': 0.15,  # 낮은 시맨틱 임계값
                'max_results': 50,  # 통계 집계를 위해 많은 결과 필요
                'processing_mode': 'statistics_complete',
                'description': '통계 완전성 우선 - 모든 관련 데이터 수집 및 정확한 집계'
            }
            
        elif query_type == "default" or is_statistical_query:
            # 일반/통계 쿼리 - 포괄성과 완전성 중시
            return {
                'search_threshold': 0.12,
                'reranker_threshold': 1.3,
                'hybrid_threshold': 0.25,
                'semantic_threshold': 0.18,
                'max_results': 20,
                'processing_mode': 'coverage_first',
                'description': '일반/통계 포괄성 우선 - 광범위한 검색'
            }
        else:
            # 기본 균형 설정
            base_thresholds.update({
                'processing_mode': 'balanced',
                'description': '균형잡힌 처리'
            })
            return base_thresholds
    
    def get_query_optimization_config(self, query_type):
        """쿼리 타입별 최적화 설정 반환"""
        optimizations = {
            "repair": {
                "use_llm_validation": True,
                "keyword_relevance_weight": 0.3,
                "semantic_boost_factor": 0.4,
                "quality_over_quantity": True,
                "strict_service_matching": True
            },
            "cause": {
                "use_llm_validation": True,
                "keyword_relevance_weight": 0.4,
                "semantic_boost_factor": 0.3,
                "quality_over_quantity": True,
                "strict_service_matching": True
            },
            "similar": {
                "use_llm_validation": False,
                "keyword_relevance_weight": 0.1,
                "semantic_boost_factor": 0.6,
                "quality_over_quantity": False,
                "strict_service_matching": False
            },
            "statistics": {  # 🆕 통계 전용 최적화 설정
                "use_llm_validation": False,
                "keyword_relevance_weight": 0.05,  # 키워드 관련성 낮게 (모든 데이터 포함)
                "semantic_boost_factor": 0.2,       # 시맨틱 부스팅 낮게
                "quality_over_quantity": False,     # 양 우선 (완전한 통계를 위해)
                "strict_service_matching": False,   # 유연한 매칭
                "ensure_completeness": True,        # 완전성 보장
                "aggregate_all_matches": True       # 모든 매칭 항목 집계
            },
            "default": {
                "use_llm_validation": False,
                "keyword_relevance_weight": 0.1,
                "semantic_boost_factor": 0.5,
                "quality_over_quantity": False,
                "strict_service_matching": False
            }
        }
        
        return optimizations.get(query_type, optimizations["default"])
    
    def get_processing_mode_info(self):
        """처리 모드별 상세 정보 반환"""
        return {
            'accuracy_first': {
                'name': '정확성 우선',
                'description': 'LLM 관련성 검증을 통한 최고 정확도',
                'best_for': ['repair', 'cause'],
                'features': ['LLM 문서 검증', '키워드 관련성 점수', '엄격한 필터링']
            },
            'coverage_first': {
                'name': '포괄성 우선', 
                'description': '의미적 유사성 기반 광범위한 검색',
                'best_for': ['similar', 'default'],
                'features': ['의미적 유사성 부스팅', '관대한 필터링', '포괄적 결과']
            },
            'statistics_complete': {  # 🆕 통계 전용 처리 모드
                'name': '통계 완전성',
                'description': '정확한 통계 집계를 위한 완전한 데이터 수집',
                'best_for': ['statistics'],
                'features': ['모든 관련 데이터 수집', '정확한 집계', '일관성 검증', '중복 제거']
            },
            'balanced': {
                'name': '균형 처리',
                'description': '정확성과 포괄성의 최적 균형',
                'best_for': ['모든 쿼리 타입'],
                'features': ['적응형 필터링', '균형잡힌 임계값', '안정적 결과']
            }
        }
    
    def get_performance_metrics(self):
        """성능 메트릭 기준값 반환"""
        return {
            'accuracy_targets': {
                'repair': 0.85,
                'cause': 0.80,
                'similar': 0.70,
                'statistics': 0.95,  # 🆕 통계는 매우 높은 정확도 요구
                'default': 0.75
            },
            'response_time_targets': {
                'accuracy_first': 8.0,
                'coverage_first': 5.0,
                'statistics_complete': 10.0,  # 🆕 통계는 더 긴 처리 시간 허용
                'balanced': 6.0
            },
            'result_count_targets': {
                'repair': {'min': 3, 'max': 10, 'optimal': 6},
                'cause': {'min': 3, 'max': 10, 'optimal': 6},
                'similar': {'min': 5, 'max': 20, 'optimal': 12},
                'statistics': {'min': 10, 'max': 100, 'optimal': 50},  # 🆕 통계는 많은 데이터 필요
                'default': {'min': 5, 'max': 25, 'optimal': 15}
            }
        }
    
    def validate_query_processing(self, query_type, processing_mode, result_count):
        """쿼리 처리 결과 검증"""
        performance_metrics = self.get_performance_metrics()
        targets = performance_metrics['result_count_targets'].get(query_type, {'min': 1, 'max': 50, 'optimal': 10})
        
        validation_result = {
            'is_valid': True,
            'warnings': [],
            'recommendations': []
        }
        
        if result_count < targets['min']:
            validation_result['warnings'].append(f"결과 수가 최소 기준({targets['min']}개)보다 적습니다.")
            validation_result['recommendations'].append("검색 임계값을 낮춰보세요.")
        
        if result_count > targets['max']:
            validation_result['warnings'].append(f"결과 수가 최대 기준({targets['max']}개)을 초과했습니다.")
            validation_result['recommendations'].append("검색 임계값을 높여보세요.")
        
        # 쿼리 타입과 처리 모드 매칭 검증
        optimization_config = self.get_query_optimization_config(query_type)
        if query_type in ['repair', 'cause'] and processing_mode != 'accuracy_first':
            validation_result['recommendations'].append(f"{query_type} 쿼리는 정확성 우선 모드를 권장합니다.")
        elif query_type in ['similar', 'default'] and processing_mode != 'coverage_first':
            validation_result['recommendations'].append(f"{query_type} 쿼리는 포괄성 우선 모드를 권장합니다.")
        elif query_type == 'statistics' and processing_mode != 'statistics_complete':  # 🆕 통계 검증
            validation_result['recommendations'].append("statistics 쿼리는 통계 완전성 모드를 권장합니다.")
        
        return validation_result