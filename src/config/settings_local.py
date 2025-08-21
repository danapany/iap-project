import os
from dotenv import load_dotenv

class AppConfigLocal:
    """애플리케이션 설정 클래스 - 로컬 검색 전용 (의미적 유사성 최적화)"""
    
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
        
        # 검색 품질 임계값 설정 (포괄적 의미적 유사성 강화)
        self.search_score_threshold = 0.15      # 더욱 관대하게 조정
        self.reranker_score_threshold = 1.2     # 완화
        self.hybrid_score_threshold = 0.35      # 완화
        self.semantic_score_threshold = 0.2     # 의미적 유사성 임계값
        self.max_initial_results = 40           # 초기 검색 결과 대폭 증가
        self.max_final_results = 12             # 최종 결과 증가
    
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
            "INDEX_REBUILD_NAME": "✅" if self.search_index else "❌"
        }
    
    def get_dynamic_thresholds(self, query_type, query_text):
        """쿼리 타입과 내용에 따라 동적으로 임계값 조정 - 의미적 유사성 강화"""
        # 년도별, 통계성 쿼리 감지
        year_keywords = ['년도', '년', '월별', '기간', '현황', '통계', '건수', '발생', '발생일자', '언제']
        is_statistical_query = any(keyword in query_text for keyword in year_keywords)
        
        # 보험 관련 키워드 감지 (특별 처리) - 더 포괄적으로 확장
        insurance_keywords = ['보험', '가입', '불가', '접속', '단말', '휴대폰', '실패', '안됨', '오류', '사용자']
        is_insurance_query = any(keyword in query_text for keyword in insurance_keywords)
        
        if is_statistical_query or query_type == "default":
            # 통계성 쿼리나 일반 쿼리는 더 관대한 기준 적용
            return {
                'search_threshold': 0.1,        # 더욱 관대한 기준
                'reranker_threshold': 1.0,
                'hybrid_threshold': 0.25,
                'semantic_threshold': 0.15,     # 의미적 유사성 임계값 완화
                'max_results': 15
            }
        elif query_type == "repair":
            if is_insurance_query:
                # 보험 및 유사 개념 관련 쿼리는 포괄적 의미적 유사성을 최우선
                return {
                    'search_threshold': 0.05,       # 매우 관대하게 (거의 모든 결과 포함)
                    'reranker_threshold': 1.0,
                    'hybrid_threshold': 0.2,
                    'semantic_threshold': 0.15,     # 의미적 유사성 중시하되 관대하게
                    'max_results': 12
                }
            else:
                # 일반 복구방법 쿼리
                return {
                    'search_threshold': 0.3,
                    'reranker_threshold': 1.6,
                    'hybrid_threshold': 0.5,
                    'semantic_threshold': 0.3,
                    'max_results': 8
                }
        elif query_type in ["cause", "similar"]:
            # 장애원인, 유사사례는 의미적 유사성과 품질을 함께 고려
            return {
                'search_threshold': 0.25,
                'reranker_threshold': 1.5,
                'hybrid_threshold': 0.45,
                'semantic_threshold': 0.25,
                'max_results': 8
            }
        else:
            # 기본값
            return {
                'search_threshold': self.search_score_threshold,
                'reranker_threshold': self.reranker_score_threshold,
                'hybrid_threshold': self.hybrid_score_threshold,
                'semantic_threshold': self.semantic_score_threshold,
                'max_results': self.max_final_results
            }