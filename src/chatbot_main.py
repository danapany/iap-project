import streamlit as st
from config.settings import AppConfig
from utils.azure_clients import AzureClientManager
from utils.search_utils import SearchManager
from utils.ui_components import UIComponents
from utils.query_processor import QueryProcessor

def main():
    """메인 애플리케이션 실행"""
    # 페이지 설정
    st.set_page_config(
        page_title="트러블 체이서 챗봇",
        page_icon="🤖",
        layout="wide"
    )
    
    # 메인 페이지 제목
    st.title("🤖 트러블 체이서 챗봇")
    
    # UI 컴포넌트 렌더링
    ui_components = UIComponents()
    ui_components.render_main_ui()
    
    # 인터넷 검색 토글 추가
    ui_components.render_internet_search_toggle()
    
    # 설정 로드
    config = AppConfig()
    if not config.validate_config():
        ui_components.show_config_error(config.get_env_status())
        return
    
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
                         if key.startswith(('internet_search_', 'search_performed_', 'show_search_modal_'))]
        for key in keys_to_remove:
            del st.session_state[key]
        st.session_state['last_query'] = user_query
    
    if user_query:
        st.session_state.messages.append({"role": "user", "content": user_query})
        
        with st.chat_message("user"):
            st.write(user_query)
        
        # 쿼리 처리 (인터넷 검색 토글 상태 전달)
        query_processor = QueryProcessor(
            azure_openai_client, 
            search_client, 
            config.azure_openai_model,
            config  # config 객체를 전달
        )
        query_processor.process_query(user_query)

if __name__ == "__main__":
    main()