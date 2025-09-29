import streamlit as st
from config.settings_local import AppConfigLocal
from utils.azure_clients import AzureClientManager
from utils.search_utils_local import SearchManagerLocal
from utils.ui_components_local import UIComponentsLocal
from utils.query_processor_local import QueryProcessorLocal
# 로깅 미들웨어 import 추가
from utils.logging_middleware import apply_logging_to_query_processor, set_client_ip

# =================================================================
# 검색 품질 설정 변수 (여기서 직접 수정 가능)
# =================================================================
DEFAULT_QUALITY_LEVEL = "고급"  # "고급 (정확성 우선)", "중급 (권장)", "초급 (포괄성 우선)"
DEFAULT_SEARCH_THRESHOLD = 0.25     # 검색 점수 임계값 (0.25 ~ 0.35)
DEFAULT_RERANKER_THRESHOLD = 2.2    # Reranker 점수 임계값 (2.2 ~ 2.8)
DEFAULT_MAX_RESULTS = 20             # 최대 결과 수 (6 ~ 10)
DEFAULT_SEMANTIC_THRESHOLD = 0.3    # 의미적 유사성 임계값 (0.3 ~ 0.5)
DEFAULT_HYBRID_THRESHOLD = 0.4      # 종합 점수 임계값 (0.4 ~ 0.6)

# 질문 길이 제한 설정
MAX_QUERY_LENGTH = 300  # 한글 기준 최대 300자

# 디버그 모드 설정 - 개발자용 내부 로깅만 (사용자에게는 보이지 않음)
DEBUG_MODE = False  # 개발 시에만 True, 운영 시에는 False 로 설정

def validate_query_length(query):
    """질문 길이 검증 및 안내 메시지 처리"""
    if len(query) > MAX_QUERY_LENGTH:
        return False, len(query)
    return True, len(query)

def show_query_length_error(current_length):
    """질문 길이 초과 시 안내 메시지 표시"""
    error_msg = f"""
    ⚠️ **질문을 조금 더 간단히 입력해 주세요**
    
    📏 **현재 질문 길이**: {current_length}자 / 최대 {MAX_QUERY_LENGTH}자
    📝 **초과 길이**: {current_length - MAX_QUERY_LENGTH}자
    
    💡 **질문 작성 팁**:
    - 핵심 내용만 간결하게 작성해주세요
    - 서비스명과 장애현상을 중심으로 작성해주세요
    - 불필요한 수식어나 부가 설명은 제외해주세요
    """
    
    with st.chat_message("assistant"):
        st.warning(error_msg)
    
    # 세션 상태에 메시지 추가
    st.session_state.messages.append({"role": "assistant", "content": error_msg})

def get_high_quality_config():
    """고급 설정 (정확성 우선) - repair/cause에 최적화된 관련없는 결과 최소화"""
    return {
        'search_threshold': DEFAULT_SEARCH_THRESHOLD,      
        'reranker_threshold': DEFAULT_RERANKER_THRESHOLD,  
        'semantic_threshold': DEFAULT_SEMANTIC_THRESHOLD,     
        'hybrid_threshold': DEFAULT_HYBRID_THRESHOLD,       
        'max_results': DEFAULT_MAX_RESULTS,              
        'quality_level': 'high',
        'description': f'최고 정확성 - 4가지 개선사항 적용 (검색점수 {int(DEFAULT_SEARCH_THRESHOLD*100)}점, Reranker {DEFAULT_RERANKER_THRESHOLD}점 이상)'
    }

def get_medium_quality_config():
    """중급 설정 (균형) - 정확성과 포괄성의 균형"""
    return {
        'search_threshold': 0.20,      
        'reranker_threshold': 2.0,     
        'semantic_threshold': 0.25,     
        'hybrid_threshold': 0.35,       
        'max_results': 15,              
        'quality_level': 'medium',
        'description': '정확성과 포괄성의 최적 균형 - 적응형 처리 + 개선사항 적용 (검색점수 20점, Reranker 2.0점 이상)'
    }

def get_low_quality_config():
    """초급 설정 (포괄성 우선) - similar/default에 최적화된 관련 문서 최대 발견"""
    return {
        'search_threshold': 0.15,      
        'reranker_threshold': 1.5,     
        'semantic_threshold': 0.2,     
        'hybrid_threshold': 0.25,       
        'max_results': 20,             
        'quality_level': 'low',
        'description': '최대 포괄성 - 광범위한 검색 결과 활용 + 개선사항 적용 (검색점수 15점, Reranker 1.5점 이상)'
    }

def apply_quality_config_to_app_config(app_config, quality_config):
    """앱 설정에 선택된 품질 설정을 적용하여 쿼리 타입별 최적화"""
    
    # 기존 get_dynamic_thresholds 메서드를 개선된 버전으로 오버라이드
    original_get_dynamic_thresholds = app_config.get_dynamic_thresholds
    
    def get_enhanced_dynamic_thresholds(query_type="default", query_text=""):
        """쿼리 타입별 최적화된 동적 임계값 설정 - 4가지 개선사항 반영"""
        
        # 기본 임계값 가져오기
        base_thresholds = original_get_dynamic_thresholds(query_type, query_text)
        
        # 쿼리 타입별 특화 설정
        if query_type in ['repair', 'cause']:
            # 정확성 우선 - 더 엄격한 기준 적용
            enhanced_thresholds = {
                'search_threshold': max(quality_config['search_threshold'], 0.25),
                'reranker_threshold': max(quality_config['reranker_threshold'], 2.0),
                'semantic_threshold': max(quality_config['semantic_threshold'], 0.25),
                'hybrid_threshold': max(quality_config['hybrid_threshold'], 0.4),
                'max_results': min(quality_config['max_results'], 15),  # 정확한 결과 위주
                'processing_mode': 'accuracy_first',
                'description': f'정확성 우선 처리 - 4가지 개선사항 적용 (네거티브 키워드 필터링, 신뢰도 점수, 고급 프롬프팅, 반성적 프롬프팅)',
                'improvements_applied': ['negative_keyword_filtering', 'confidence_scoring', 'enhanced_prompting', 'reflection_prompting']
            }
        elif query_type in ['similar', 'default']:
            # 포괄성 우선 - 더 관대한 기준 적용
            enhanced_thresholds = {
                'search_threshold': min(quality_config['search_threshold'], 0.15),
                'reranker_threshold': min(quality_config['reranker_threshold'], 1.5),
                'semantic_threshold': min(quality_config['semantic_threshold'], 0.2),
                'hybrid_threshold': min(quality_config['hybrid_threshold'], 0.3),
                'max_results': max(quality_config['max_results'], 20),  # 포괄적 결과 위주
                'processing_mode': 'coverage_first',
                'description': f'포괄성 우선 처리 - 광범위한 검색 결과 활용 + 4가지 개선사항 적용',
                'improvements_applied': ['negative_keyword_filtering', 'confidence_scoring', 'enhanced_prompting', 'reflection_prompting']
            }
        else:
            # 기본 설정
            enhanced_thresholds = quality_config.copy()
            enhanced_thresholds['processing_mode'] = 'balanced'
            enhanced_thresholds['description'] = '균형잡힌 처리 + 개선사항 적용'
            enhanced_thresholds['improvements_applied'] = ['negative_keyword_filtering', 'confidence_scoring', 'enhanced_prompting', 'reflection_prompting']
        
        # 기본 임계값과 병합
        base_thresholds.update(enhanced_thresholds)
        return base_thresholds
    
    app_config.get_dynamic_thresholds = get_enhanced_dynamic_thresholds
    
    return app_config

def main():
    """메인 애플리케이션 실행"""
    
    # 페이지 설정 - wide 레이아웃으로 변경
    st.set_page_config(
        page_title="트러블 체이서 챗봇",
        page_icon="🚀",
        layout="wide"
    )
    
    # 차트와 UI를 위한 전역 CSS 스타일 추가 - 웹 버전과 동일한 스타일 적용
    st.markdown("""
    <style>
        /* 차트 컨테이너 고정 크기 스타일 */
        .fixed-chart-container {
            width: 800px !important;
            height: 650px !important;
            margin: 0 auto !important;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 10px;
            background-color: #fafafa;
            overflow: hidden;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        
        .fixed-chart-container > div {
            width: 800px !important;
            height: 600px !important;
        }
        
        /* 스트림릿 기본 차트 컨테이너 오버라이드 */
        .stPyplot > div {
            display: flex !important;
            justify-content: center !important;
        }
        
        /* 메인 컨텐츠 설정 */
        .main .block-container {
            max-width: none !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }
        
        /* 차트 섹션 중앙 정렬 */
        .chart-section {
            display: flex;
            justify-content: center;
            align-items: center;
            width: 100%;
        }
        
        /* 채팅 영역 좌측 정렬로 수정 */
        .stChatMessage {
            max-width: 1200px;
            margin: 0 !important; /* 좌측 정렬 */
            margin-left: 0 !important;
            margin-right: auto !important;
        }

        /* 입력창 좌측 정렬로 수정 */
        .stChatInput {
            max-width: 1200px;
            margin: 0 !important; /* 좌측 정렬 */
            margin-left: 0 !important;
            margin-right: auto !important;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # 메인 페이지 제목
    st.title("🚀 트러블 체이서 챗봇")
    
    # 🆕 처리 모드 정보 (전역 정의) - STATISTICS 타입 추가
    processing_modes = {
        'repair': '정확성 우선 (LLM 검증+의미적 유사성)',
        'cause': '정확성 우선 (LLM 검증+의미적 유사성)',
        'similar': '포괄성 우선 (LLM 검증+의미적 유사성)',
        'inquiry': '조건별 내역 조회 (LLM 검증+의미적 유사성+특정 조건 기반 장애 검색)',
        'statistics': '통계 전용 처리 (정확한 집계+월별 범위 정규화+데이터 무결성 보장)',  # 🆕 추가
        'default': '포괄성 우선 (LLM 검증+의미적 유사성+광범위 검색+차트 지원)'
    }
    
    # 상단 변수 설정을 기본 품질 설정으로 사용
    if "고급" in DEFAULT_QUALITY_LEVEL:
        selected_quality_config = get_high_quality_config()
        # 운영 모드에서는 간단한 상태 메시지만 표시
        if DEBUG_MODE:
            st.success("🎯 정확성 우선 모드: repair/cause/inquiry 쿼리에서 LLM 관련성 검증")
    elif "초급" in DEFAULT_QUALITY_LEVEL:
        selected_quality_config = get_low_quality_config()
        if DEBUG_MODE:
            st.success("📋 포괄성 우선 모드: similar/default 쿼리에서 광범위한 검색")
    else:
        selected_quality_config = get_medium_quality_config()
        if DEBUG_MODE:
            st.success("⚖️ 균형 모드: 모든 쿼리 타입에서 정확성과 포괄성의 최적 균형")
    
    # 세션 상태에 품질 설정 저장
    st.session_state['quality_config'] = selected_quality_config
       
    # UI 컴포넌트 렌더링
    ui_components = UIComponentsLocal()
    ui_components.render_main_ui()
    
    # 설정 로드
    config = AppConfigLocal()
    if not config.validate_config():
        ui_components.show_config_error(config.get_env_status())
        return
    
    # 선택된 품질 설정을 앱 설정에 적용 (쿼리 타입별 최적화 포함)
    config = apply_quality_config_to_app_config(config, selected_quality_config)
    
    # Azure 클라이언트 초기화
    client_manager = AzureClientManager(config)
    azure_openai_client, search_client, init_success = client_manager.init_clients()
    
    if not init_success:
        ui_components.show_connection_error()
        return
    
    # 세션 상태 초기화
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    
    # 채팅 메시지 표시
    ui_components.display_chat_messages()
    
    # 사용자 입력 처리
    user_query = st.chat_input(f"질문을 입력하세요 (최대 {MAX_QUERY_LENGTH}자)")
    
    # 새로운 질문이 들어올 때 이전 상태 초기화
    if user_query and user_query != st.session_state.get('last_query', ''):
        # 모든 검색 관련 상태 초기화
        keys_to_remove = [key for key in st.session_state.keys() 
                         if key.startswith(('search_performed_', 'show_search_modal_'))]
        for key in keys_to_remove:
            del st.session_state[key]
        st.session_state['last_query'] = user_query
    
    if user_query:
        # === 새로 추가: 질문 길이 검증 ===
        is_valid_length, current_length = validate_query_length(user_query)
        
        if not is_valid_length:
            # 질문이 너무 길면 안내 메시지만 표시하고 처리 중단
            show_query_length_error(current_length)
            return
        
        # 질문 길이가 적절한 경우에만 처리 계속
        st.session_state.messages.append({"role": "user", "content": user_query})
        
        with st.chat_message("user"):
            st.write(user_query)
        
        # 로깅을 위한 IP 설정 (개발/테스트 환경용)
        # set_client_ip("127.0.0.1")  # 테스트용 IP 주소
        
        # 향상된 쿼리 처리 (4가지 개선사항이 적용된 config 전달)
        query_processor = QueryProcessorLocal(
            azure_openai_client, 
            search_client, 
            config.azure_openai_model,
            config  # 4가지 개선사항이 적용된 config 객체를 전달
        )
        
        # 로깅 미들웨어 적용
        try:
            query_processor = apply_logging_to_query_processor(query_processor)
        except Exception as e:
            # 로깅 미들웨어 적용에 실패해도 계속 진행
            print(f"DEBUG: Failed to apply logging middleware: {e}")
        
        # 디버그 모드 설정을 쿼리 프로세서에 전달
        query_processor.debug_mode = DEBUG_MODE
        query_processor.search_manager.debug_mode = DEBUG_MODE
        
        # 개발자 모드에서만 개선사항 적용 안내 표시
        if DEBUG_MODE:
            improvements_status = """
            🚀 5가지 즉시 적용 개선사항 활성화:
            ✅ 네거티브 키워드 필터링
            ✅ 신뢰도 점수 시스템  
            ✅ 고급 프롬프팅
            ✅ 반성적 프롬프팅
            ✅ 완전 고정 크기 차트 시각화 기능 (800x600px)
            
            🔍 새로운 쿼리 타입 지원:
            ✅ INQUIRY: 조건별 장애 내역 조회
            ✅ STATISTICS: 통계 전용 처리 (🆕 추가)
            
            📊 완전 고정 크기 차트 지원 통계 질문:
            ✅ 연도별, 월별, 시간대별 통계
            ✅ 부서별, 서비스별, 등급별 분포
            ✅ 자동 차트 생성 및 데이터 테이블
            ✅ CSS + 컬럼 레이아웃으로 완전 고정 크기 보장
            
            📏 질문 길이: {current_length}자 / {MAX_QUERY_LENGTH}자
            
            🔍 로깅 시스템 활성화: 사용자 질문이 모니터링 DB에 저장됩니다.
            """.format(current_length=current_length, MAX_QUERY_LENGTH=MAX_QUERY_LENGTH)
            st.info(improvements_status)
        
        if user_query:
            try:
                # 기존 코드...
                query_processor.process_query(user_query)
            except Exception as e:
                st.error(f"오류가 발생했습니다: {str(e)}")
                st.info("잠시 후 다시 시도해주세요.")
                if DEBUG_MODE:
                    import traceback
                    st.error("상세 오류 정보:")
                    st.code(traceback.format_exc())

if __name__ == "__main__":
    main()