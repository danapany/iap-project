import streamlit as st
from config.settings_local import AppConfigLocal
from utils.azure_clients import AzureClientManager
from utils.search_utils_local import SearchManagerLocal
from utils.ui_components_local import UIComponentsLocal
from utils.query_processor_local import QueryProcessorLocal
from utils.logging_middleware import apply_logging_to_query_processor, set_client_ip

# 검색 품질 설정
DEFAULT_QUALITY_LEVEL = "고급"
DEFAULT_SEARCH_THRESHOLD = 0.25
DEFAULT_RERANKER_THRESHOLD = 2.2
DEFAULT_MAX_RESULTS = 20
DEFAULT_SEMANTIC_THRESHOLD = 0.3
DEFAULT_HYBRID_THRESHOLD = 0.4
MAX_QUERY_LENGTH = 300
DEBUG_MODE = False

def validate_query_length(query):
    """질문 길이 검증"""
    return len(query) <= MAX_QUERY_LENGTH, len(query)

def show_query_length_error(current_length):
    """질문 길이 초과 안내"""
    error_msg = f"""
    ⚠️ **질문을 조금 더 간단히 입력해 주세요**
    
    📏 현재: {current_length}자 / 최대: {MAX_QUERY_LENGTH}자
    📝 초과: {current_length - MAX_QUERY_LENGTH}자
    
    💡 **팁**: 핵심 내용만 간결하게, 서비스명과 장애현상 중심으로 작성
    """
    with st.chat_message("assistant"):
        st.warning(error_msg)
    st.session_state.messages.append({"role": "assistant", "content": error_msg})

def get_quality_config(level):
    """품질 설정 팩토리 함수"""
    configs = {
        'high': {
            'search_threshold': DEFAULT_SEARCH_THRESHOLD,
            'reranker_threshold': DEFAULT_RERANKER_THRESHOLD,
            'semantic_threshold': DEFAULT_SEMANTIC_THRESHOLD,
            'hybrid_threshold': DEFAULT_HYBRID_THRESHOLD,
            'max_results': DEFAULT_MAX_RESULTS,
            'quality_level': 'high',
            'description': f'최고 정확성 (검색점수 {int(DEFAULT_SEARCH_THRESHOLD*100)}점, Reranker {DEFAULT_RERANKER_THRESHOLD}점 이상)'
        },
        'medium': {
            'search_threshold': 0.20,
            'reranker_threshold': 2.0,
            'semantic_threshold': 0.25,
            'hybrid_threshold': 0.35,
            'max_results': 15,
            'quality_level': 'medium',
            'description': '정확성과 포괄성 균형 (검색점수 20점, Reranker 2.0점 이상)'
        },
        'low': {
            'search_threshold': 0.15,
            'reranker_threshold': 1.5,
            'semantic_threshold': 0.2,
            'hybrid_threshold': 0.25,
            'max_results': 20,
            'quality_level': 'low',
            'description': '최대 포괄성 (검색점수 15점, Reranker 1.5점 이상)'
        }
    }
    return configs.get(level, configs['medium'])

def apply_quality_config_to_app_config(app_config, quality_config):
    """앱 설정에 품질 설정 적용"""
    original_get_dynamic_thresholds = app_config.get_dynamic_thresholds
    
    def get_enhanced_dynamic_thresholds(query_type="default", query_text=""):
        base_thresholds = original_get_dynamic_thresholds(query_type, query_text)
        
        improvements = ['negative_keyword_filtering', 'confidence_scoring', 
                       'enhanced_prompting', 'reflection_prompting']
        
        if query_type in ['repair', 'cause']:
            enhanced_thresholds = {
                'search_threshold': max(quality_config['search_threshold'], 0.25),
                'reranker_threshold': max(quality_config['reranker_threshold'], 2.0),
                'semantic_threshold': max(quality_config['semantic_threshold'], 0.25),
                'hybrid_threshold': max(quality_config['hybrid_threshold'], 0.4),
                'max_results': min(quality_config['max_results'], 15),
                'processing_mode': 'accuracy_first',
                'description': '정확성 우선 처리',
                'improvements_applied': improvements
            }
        elif query_type in ['similar', 'default']:
            enhanced_thresholds = {
                'search_threshold': min(quality_config['search_threshold'], 0.15),
                'reranker_threshold': min(quality_config['reranker_threshold'], 1.5),
                'semantic_threshold': min(quality_config['semantic_threshold'], 0.2),
                'hybrid_threshold': min(quality_config['hybrid_threshold'], 0.3),
                'max_results': max(quality_config['max_results'], 20),
                'processing_mode': 'coverage_first',
                'description': '포괄성 우선 처리',
                'improvements_applied': improvements
            }
        else:
            enhanced_thresholds = quality_config.copy()
            enhanced_thresholds.update({
                'processing_mode': 'balanced',
                'description': '균형잡힌 처리',
                'improvements_applied': improvements
            })
        
        base_thresholds.update(enhanced_thresholds)
        return base_thresholds
    
    app_config.get_dynamic_thresholds = get_enhanced_dynamic_thresholds
    return app_config

def main():
    """메인 애플리케이션"""
    st.set_page_config(
        page_title="트러블 체이서 챗봇",
        page_icon="🚀",
        layout="wide"
    )
    
    st.markdown("""
    <style>
        .fixed-chart-container {
            width: 800px !important; height: 650px !important;
            margin: 0 auto !important; border: 1px solid #e0e0e0;
            border-radius: 8px; padding: 10px; background-color: #fafafa;
            overflow: hidden; display: flex; justify-content: center; align-items: center;
        }
        .fixed-chart-container > div { width: 800px !important; height: 600px !important; }
        .stPyplot > div { display: flex !important; justify-content: center !important; }
        .main .block-container {
            max-width: none !important; padding-left: 2rem !important; padding-right: 2rem !important;
        }
        .chart-section { display: flex; justify-content: center; align-items: center; width: 100%; }
        .stChatMessage, .stChatInput {
            max-width: 1200px; margin: 0 !important; margin-left: 0 !important; margin-right: auto !important;
        }
    </style>
    """, unsafe_allow_html=True)
    
    st.title("🚀 트러블 체이서 챗봇")
    
    processing_modes = {
        'repair': '정확성 우선 (LLM 검증+의미적 유사성)',
        'cause': '정확성 우선 (LLM 검증+의미적 유사성)',
        'similar': '포괄성 우선 (LLM 검증+의미적 유사성)',
        'inquiry': '조건별 내역 조회 (LLM 검증+의미적 유사성+특정 조건 기반 장애 검색)',
        'statistics': '통계 전용 처리 (정확한 집계+월별 범위 정규화+데이터 무결성 보장)',
        'default': '포괄성 우선 (LLM 검증+의미적 유사성+광범위 검색+차트 지원)'
    }
    
    # 품질 설정 선택
    level_map = {"고급": "high", "초급": "low", "중급": "medium"}
    selected_level = level_map.get(next((k for k in level_map if k in DEFAULT_QUALITY_LEVEL), "중급"))
    selected_quality_config = get_quality_config(selected_level)
    
    if DEBUG_MODE:
        mode_msg = {"high": "🎯 정확성 우선", "low": "📋 포괄성 우선", "medium": "⚖️ 균형 모드"}
        st.success(mode_msg.get(selected_level, "⚖️ 균형 모드"))
    
    st.session_state['quality_config'] = selected_quality_config
    
    # UI 및 설정 초기화
    ui_components = UIComponentsLocal()
    ui_components.render_main_ui()
    
    config = AppConfigLocal()
    if not config.validate_config():
        ui_components.show_config_error(config.get_env_status())
        return
    
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
    
    ui_components.display_chat_messages()
    
    # 사용자 입력 처리
    user_query = st.chat_input(f"질문을 입력하세요 (최대 {MAX_QUERY_LENGTH}자)")
    
    # 새 질문 시 이전 상태 초기화
    if user_query and user_query != st.session_state.get('last_query', ''):
        keys_to_remove = [key for key in st.session_state.keys() 
                         if key.startswith(('search_performed_', 'show_search_modal_'))]
        for key in keys_to_remove:
            del st.session_state[key]
        st.session_state['last_query'] = user_query
    
    if user_query:
        is_valid_length, current_length = validate_query_length(user_query)
        
        if not is_valid_length:
            show_query_length_error(current_length)
            return
        
        st.session_state.messages.append({"role": "user", "content": user_query})
        
        with st.chat_message("user"):
            st.write(user_query)
        
        query_processor = QueryProcessorLocal(
            azure_openai_client, search_client, 
            config.azure_openai_model, config
        )
        
        try:
            query_processor = apply_logging_to_query_processor(query_processor)
        except Exception as e:
            print(f"DEBUG: Failed to apply logging middleware: {e}")
        
        query_processor.debug_mode = DEBUG_MODE
        query_processor.search_manager.debug_mode = DEBUG_MODE
        
        if DEBUG_MODE:
            st.info(f"""
            🚀 5가지 개선사항 활성화
            🔍 새 쿼리 타입: INQUIRY, STATISTICS
            📊 완전 고정 크기 차트 (800x600px)
            📏 질문 길이: {current_length}자 / {MAX_QUERY_LENGTH}자
            🔍 로깅 시스템 활성화
            """)
        
        try:
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