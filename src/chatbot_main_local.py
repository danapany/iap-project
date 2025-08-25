import streamlit as st
from config.settings_local import AppConfigLocal
from utils.azure_clients import AzureClientManager
from utils.search_utils_local import SearchManagerLocal
from utils.ui_components_local import UIComponentsLocal
from utils.query_processor_local import QueryProcessorLocal

# =================================================================
# 검색 품질 설정 변수 (여기서 직접 수정 가능)
# =================================================================
DEFAULT_QUALITY_LEVEL = "고급 (정확성 우선)"  # "고급 (정확성 우선)", "중급 (권장)", "초급 (포괄성 우선)"
DEFAULT_SEARCH_THRESHOLD = 0.3     # 검색 점수 고급 0.35, 중급 0.3 초급 0.25 
DEFAULT_RERANKER_THRESHOLD = 2.5    # Reranker 점수 고급 2.8, 중급 2.5 초급 2.2
DEFAULT_MAX_RESULTS = 20             # 고급 6, 중급 8, 초급 10  
DEFAULT_SEMANTIC_THRESHOLD = 0.4    # 의미적 유사성 임계값 고급 0.5, 중급 0.4, 초급 0.3
DEFAULT_HYBRID_THRESHOLD = 0.5      # 종합 점수 임계값 고급 0.5, 중급 0.5, 초급 0.4

# 사이드바 설정 함수 제거됨 - 상단 변수로 직접 설정

def get_high_quality_config():
    """고급 설정 (정확성 우선) - 관련없는 결과 최소화"""
    return {
        'search_threshold': DEFAULT_SEARCH_THRESHOLD,      
        'reranker_threshold': DEFAULT_RERANKER_THRESHOLD,  
        'semantic_threshold': DEFAULT_SEMANTIC_THRESHOLD,     
        'hybrid_threshold': DEFAULT_HYBRID_THRESHOLD,       
        'max_results': DEFAULT_MAX_RESULTS,              
        'quality_level': 'high',
        'description': f'매우 정확하지만 결과 수 적음 (검색점수 {int(DEFAULT_SEARCH_THRESHOLD*100)}점, Reranker {DEFAULT_RERANKER_THRESHOLD}점 이상)'
    }

def get_medium_quality_config():
    """중급 설정 (균형) - 정확성과 결과 수의 균형"""
    return {
        'search_threshold': 0.30,      
        'reranker_threshold': 2.5,     
        'semantic_threshold': 0.4,     
        'hybrid_threshold': 0.5,       
        'max_results': 8,              
        'quality_level': 'medium',
        'description': '정확성과 결과 수의 최적 균형 (검색점수 30점, Reranker 2.5점 이상)'
    }

def get_low_quality_config():
    """초급 설정 (포괄성 우선) - 관련 문서 최대 발견"""
    return {
        'search_threshold': 0.25,      
        'reranker_threshold': 2.2,     
        'semantic_threshold': 0.3,     
        'hybrid_threshold': 0.4,       
        'max_results': 10,             
        'quality_level': 'low',
        'description': '많은 결과, 일부 관련성 낮을 수 있음 (검색점수 25점, Reranker 2.2점 이상)'
    }

def apply_quality_config_to_app_config(app_config, quality_config):
    """앱 설정에 선택된 품질 설정 적용"""
    
    # 기존 get_dynamic_thresholds 메서드를 오버라이드
    original_get_dynamic_thresholds = app_config.get_dynamic_thresholds
    
    def get_dynamic_thresholds_override(query_type="default", query_text=""):
        # 기본 임계값을 선택된 품질 설정으로 덮어쓰기
        base_thresholds = original_get_dynamic_thresholds(query_type, query_text)
        base_thresholds.update(quality_config)
        return base_thresholds
    
    app_config.get_dynamic_thresholds = get_dynamic_thresholds_override
    
    return app_config

def main():
    """메인 애플리케이션 실행 - 로컬 검색 전용 (파일 기반 서비스명 매칭)"""
    
    # 페이지 설정
    st.set_page_config(
        page_title="트러블 체이서 챗봇 (파일 기반)",
        page_icon="🤖",
        layout="wide"
    )
    
    # 메인 페이지 제목
    st.title("🤖 트러블 체이서 챗봇 (파일 기반 서비스명 매칭)")
    
    # 상단 변수 설정을 기본 품질 설정으로 사용
    if "고급" in DEFAULT_QUALITY_LEVEL:
        selected_quality_config = get_high_quality_config()
    elif "초급" in DEFAULT_QUALITY_LEVEL:
        selected_quality_config = get_low_quality_config()
    else:
        selected_quality_config = get_medium_quality_config()
    
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
    
    # 선택된 품질 설정을 앱 설정에 적용
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
    user_query = st.chat_input("💬 질문을 입력하세요")
    
    # 새로운 질문이 들어올 때 이전 상태 초기화
    if user_query and user_query != st.session_state.get('last_query', ''):
        # 모든 검색 관련 상태 초기화
        keys_to_remove = [key for key in st.session_state.keys() 
                         if key.startswith(('search_performed_', 'show_search_modal_'))]
        for key in keys_to_remove:
            del st.session_state[key]
        st.session_state['last_query'] = user_query
    
    if user_query:
        st.session_state.messages.append({"role": "user", "content": user_query})
        
        with st.chat_message("user"):
            st.write(user_query)
        
        # 품질 설정에 따른 메시지 표시
        quality_level = selected_quality_config['quality_level']
        if quality_level == 'high':
            st.info("🔒 고급 품질 설정으로 검색 중... (정확성 우선, 파일 기반)")
        elif quality_level == 'low':
            st.info("🔓 초급 품질 설정으로 검색 중... (포괄성 우선, 파일 기반)")
        else:
            st.info("⚖️ 중급 품질 설정으로 검색 중... (균형 모드, 파일 기반)")
        
        # 쿼리 처리 (업데이트된 config 전달)
        query_processor = QueryProcessorLocal(
            azure_openai_client, 
            search_client, 
            config.azure_openai_model,
            config  # 품질 설정이 적용된 config 객체를 전달
        )
        query_processor.process_query(user_query)

if __name__ == "__main__":
    main()