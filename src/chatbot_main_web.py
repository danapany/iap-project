import streamlit as st
from config.settings_web import AppConfig
from utils.azure_clients_web import AzureClientManager
from utils.ui_components_web import UIComponents
from utils.query_processor_web import QueryProcessor

# =================================================================
# DEBUG 모드 설정 - 개발자용 내부 로깅만 (사용자에게는 보이지 않음)
# =================================================================
DEBUG_MODE = False  # 개발 시에만 True, 운영 시에는 False 로 설정

# 질문 길이 제한 설정
MAX_QUERY_LENGTH = 300  # 한글 기준 최대 300자

# 웹 버전 전용 세션 키 정의
WEB_SESSION_KEY = "web_chatbot"
WEB_MESSAGES_KEY = f"{WEB_SESSION_KEY}_messages"
WEB_LAST_QUERY_KEY = f"{WEB_SESSION_KEY}_last_query"

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
    - 서비스명과 문제상황을 중심으로 작성해주세요
    - 불필요한 수식어나 부가 설명은 제외해주세요
    
    ✅ **좋은 질문 예시**:
    - "웹서버 접속불가 해결방법 알려줘"
    - "API 응답지연 원인이 뭐야?"
    - "데이터베이스 연결오류 유사사례 찾아줘"
    """
    
    with st.chat_message("assistant"):
        st.warning(error_msg)
    
    # 웹 버전 전용 세션에 메시지 추가
    st.session_state[WEB_MESSAGES_KEY].append({"role": "assistant", "content": error_msg})

def initialize_web_session():
    """웹 버전 전용 세션 상태 초기화"""
    if WEB_MESSAGES_KEY not in st.session_state:
        st.session_state[WEB_MESSAGES_KEY] = []
    
    if WEB_LAST_QUERY_KEY not in st.session_state:
        st.session_state[WEB_LAST_QUERY_KEY] = ""
    
    # 웹 버전 식별자 설정
    st.session_state[WEB_SESSION_KEY] = True

def clear_web_search_states(user_query):
    """웹 검색 관련 상태 초기화"""
    if user_query and user_query != st.session_state.get(WEB_LAST_QUERY_KEY, ''):
        # 웹 버전 전용 검색 관련 상태 초기화
        keys_to_remove = [key for key in st.session_state.keys() 
                         if key.startswith((f'{WEB_SESSION_KEY}_internet_search_', 
                                          f'{WEB_SESSION_KEY}_search_performed_', 
                                          f'{WEB_SESSION_KEY}_show_search_modal_'))]
        for key in keys_to_remove:
            del st.session_state[key]
        st.session_state[WEB_LAST_QUERY_KEY] = user_query

def main():
    """메인 애플리케이션 실행"""
    
    # 페이지 설정
    st.set_page_config(
        page_title="트러블 체이서 WEB검색",
        page_icon="🌐",
        layout="wide"
    )
    
    # 메인 페이지 제목
    st.title("🌐 트러블 체이서 WEB검색")
    
    # 웹 버전 전용 세션 초기화
    initialize_web_session()
    
    # DEBUG 모드 상태 표시 (개발자용)
    if DEBUG_MODE:
        st.info("🔧 DEBUG 모드: 모든 중간 과정이 표시됩니다")
        st.info(f"🔑 현재 세션: {WEB_SESSION_KEY} (웹 검색 전용)")
    
    # UI 컴포넌트 렌더링
    ui_components = UIComponents()
    ui_components.render_main_ui()
    
    # 설정 로드
    config = AppConfig()
    if not config.validate_config():
        ui_components.show_config_error(config.get_env_status())
        return
    
    # Azure 클라이언트 초기화
    client_manager = AzureClientManager(config)
    azure_openai_client, init_success = client_manager.init_clients()
    
    if not init_success:
        ui_components.show_connection_error()
        return
    
    # 웹 버전 전용 채팅 메시지 표시
    ui_components.display_chat_messages(WEB_MESSAGES_KEY)
    
    # 사용자 입력 처리
    user_query = st.chat_input(f"💬 질문을 입력하세요 (최대 {MAX_QUERY_LENGTH}자)")
    
    # 웹 버전 전용 상태 초기화
    clear_web_search_states(user_query)
    
    if user_query:
        # 질문 길이 검증
        is_valid_length, current_length = validate_query_length(user_query)
        
        if not is_valid_length:
            # 질문이 너무 길면 안내 메시지만 표시하고 처리 중단
            show_query_length_error(current_length)
            return
        
        # 질문 길이가 적절한 경우에만 처리 계속
        st.session_state[WEB_MESSAGES_KEY].append({"role": "user", "content": user_query})
        
        with st.chat_message("user"):
            st.write(user_query)
        
        # 쿼리 처리
        query_processor = QueryProcessor(
            azure_openai_client, 
            config.azure_openai_model,
            config,
            session_key=WEB_SESSION_KEY  # 웹 버전 전용 세션 키 전달
        )
        
        # DEBUG 모드 설정을 쿼리 프로세서에 전달
        query_processor.debug_mode = DEBUG_MODE
        
        # DEBUG 모드에서만 상세 정보 표시
        if DEBUG_MODE:
            improvements_status = f"""
            🚀 웹 검색 기반 챗봇 활성화:
            ✅ 실시간 Google 검색
            ✅ 신뢰성 평가 시스템
            ✅ 지능적 질문 분류
            ✅ 전문가 수준 답변 생성
            
            🔑 세션 관리:
            ✅ 웹 버전 전용 세션 ({WEB_SESSION_KEY})
            ✅ 로컬 버전과 독립적 메시지 관리
            ✅ 웹 검색 상태 별도 관리
            
            📏 질문 길이: {current_length}자 / {MAX_QUERY_LENGTH}자
            """
            st.info(improvements_status)
        
        try:
            query_processor.process_query(user_query)
        except Exception as e:
            error_message = f"오류가 발생했습니다: {str(e)}"
            st.error(error_message)
            st.info("잠시 후 다시 시도해주세요.")
            
            # 오류 메시지도 웹 버전 세션에 저장
            st.session_state[WEB_MESSAGES_KEY].append({"role": "assistant", "content": error_message})

if __name__ == "__main__":
    main()