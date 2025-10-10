import streamlit as st
from config.settings_local import AppConfigLocal
from utils.azure_clients import AzureClientManager
from utils.search_utils_local import SearchManagerLocal
from utils.ui_components_local import UIComponentsLocal
from utils.query_processor_local import QueryProcessorLocal
from utils.logging_middleware import apply_logging_to_query_processor, set_client_ip

# 엑셀 다운로드를 위한 추가 import
try:
    import pandas as pd
    import openpyxl
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False
    st.warning("엑셀 다운로드 기능을 위해 pandas와 openpyxl 라이브러리가 필요합니다.")

# 설정 상수
SETTINGS = {
    'quality_level': "고급",
    'max_query_length': 300,
    'debug_mode': False,
    'thresholds': {
        'high': {'search_threshold': 0.25, 'reranker_threshold': 2.2, 'semantic_threshold': 0.3, 'hybrid_threshold': 0.4, 'max_results': 20, 'quality_level': 'high'},
        'medium': {'search_threshold': 0.20, 'reranker_threshold': 2.0, 'semantic_threshold': 0.25, 'hybrid_threshold': 0.35, 'max_results': 15, 'quality_level': 'medium'},
        'low': {'search_threshold': 0.15, 'reranker_threshold': 1.5, 'semantic_threshold': 0.2, 'hybrid_threshold': 0.25, 'max_results': 20, 'quality_level': 'low'}
    }
}

def validate_query_length(query):
    return len(query) <= SETTINGS['max_query_length'], len(query)

def show_query_length_error(current_length):
    max_len = SETTINGS['max_query_length']
    error_msg = f"""⚠️ **질문을 조금 더 간단히 입력해 주세요**
    
📏 현재: {current_length}자 / 최대: {max_len}자
📝 초과: {current_length - max_len}자

💡 **팁**: 핵심 내용만 간결하게, 서비스명과 장애현상 중심으로 작성"""
    
    with st.chat_message("assistant"):
        st.warning(error_msg)
    st.session_state.messages.append({"role": "assistant", "content": error_msg})

def get_quality_config(level):
    return SETTINGS['thresholds'].get(level, SETTINGS['thresholds']['medium'])

def apply_quality_config_to_app_config(app_config, quality_config):
    original_get_dynamic_thresholds = app_config.get_dynamic_thresholds
    
    def get_enhanced_dynamic_thresholds(query_type="default", query_text=""):
        base_thresholds = original_get_dynamic_thresholds(query_type, query_text)
        improvements = ['negative_keyword_filtering', 'confidence_scoring', 'enhanced_prompting', 'reflection_prompting']
        
        if query_type in ['repair', 'cause']:
            enhanced_thresholds = {
                'search_threshold': max(quality_config['search_threshold'], 0.25),
                'reranker_threshold': max(quality_config['reranker_threshold'], 2.0),
                'semantic_threshold': max(quality_config['semantic_threshold'], 0.25),
                'hybrid_threshold': max(quality_config['hybrid_threshold'], 0.4),
                'max_results': min(quality_config['max_results'], 15),
                'processing_mode': 'accuracy_first',
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
                'improvements_applied': improvements
            }
        else:
            enhanced_thresholds = quality_config.copy()
            enhanced_thresholds.update({'processing_mode': 'balanced', 'improvements_applied': improvements})
        
        base_thresholds.update(enhanced_thresholds)
        return base_thresholds
    
    app_config.get_dynamic_thresholds = get_enhanced_dynamic_thresholds
    return app_config

def apply_page_style():
    st.markdown("""<style>
        .main .block-container {max-width: none !important; padding-left: 2rem !important; padding-right: 2rem !important;}
        .stChatMessage, .stChatInput {max-width: 1200px; margin: 0 !important; margin-left: 0 !important; margin-right: auto !important;}
    </style>""", unsafe_allow_html=True)

def main():
    st.set_page_config(page_title="챗봇1", page_icon="🚀", layout="wide")
    
    if not EXCEL_AVAILABLE:
        st.sidebar.warning("📊 엑셀 다운로드 기능이 비활성화되었습니다. pandas와 openpyxl을 설치해주세요.")
    
    apply_page_style()
    st.title("🚀 챗봇1")
    
    # 품질 설정
    level_map = {"고급": "high", "초급": "low", "중급": "medium"}
    selected_level = level_map.get(next((k for k in level_map if k in SETTINGS['quality_level']), "중급"))
    selected_quality_config = get_quality_config(selected_level)
    st.session_state['quality_config'] = selected_quality_config
    
    # UI 구성
    ui_components = UIComponentsLocal()
    ui_components.render_main_ui()
        
    # 설정 및 클라이언트 초기화
    config = AppConfigLocal()
    if not config.validate_config():
        ui_components.show_config_error(config.get_env_status())
        return
    
    config = apply_quality_config_to_app_config(config, selected_quality_config)
    client_manager = AzureClientManager(config)
    azure_openai_client, search_client, embedding_client, init_success = client_manager.init_clients()
    
    if not init_success:
        ui_components.show_connection_error()
        return
    
    # 메시지 초기화 및 표시
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    ui_components.display_chat_messages()
    
    # 사용자 입력 처리
    user_query = st.chat_input(f"질문을 입력하세요 (최대 {SETTINGS['max_query_length']}자)")
    
    if user_query and user_query != st.session_state.get('last_query', ''):
        # 이전 검색 상태 정리
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
        
        # 메시지 추가 및 표시
        st.session_state.messages.append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.write(user_query)
        
        # 쿼리 처리
        query_processor = QueryProcessorLocal(
            azure_openai_client, search_client, config.azure_openai_model, 
            config, embedding_client=embedding_client
        )
        
        try:
            query_processor = apply_logging_to_query_processor(query_processor)
        except Exception as e:
            print(f"DEBUG: Failed to apply logging middleware: {e}")
        
        query_processor.debug_mode = SETTINGS['debug_mode']
        query_processor.search_manager.debug_mode = SETTINGS['debug_mode']
        
        try:
            query_processor.process_query(user_query)
        except Exception as e:
            st.error(f"오류가 발생했습니다: {str(e)}")
            st.info("잠시 후 다시 시도해주세요.")
            if SETTINGS['debug_mode']:
                import traceback
                st.error("상세 오류 정보:")
                st.code(traceback.format_exc())

if __name__ == "__main__":
    main()