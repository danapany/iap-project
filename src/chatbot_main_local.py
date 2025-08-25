import streamlit as st
from config.settings_local import AppConfigLocal
from utils.azure_clients import AzureClientManager
from utils.search_utils_local import SearchManagerLocal
from utils.ui_components_local import UIComponentsLocal
from utils.query_processor_local import QueryProcessorLocal

def add_search_quality_selector():
    """사이드바에 검색 품질 선택 기능 추가"""
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🎯 검색 품질 설정")
    
    # 품질 수준 선택
    quality_level = st.sidebar.selectbox(
        "검색 결과 품질 수준을 선택하세요:",
        options=["중급 (권장)", "고급 (정확성 우선)", "초급 (포괄성 우선)"],
        index=1,  # 기본값: 중급
        help="""
        • 고급: 매우 정확하지만 결과 수 적음 (검색 35점, Reranker 2.8점 이상)
        • 중급: 정확성과 결과 수의 균형 (검색 30점, Reranker 2.5점 이상)
        • 초급: 결과 수 많지만 관련성 낮은 것 포함 가능 (검색 25점, Reranker 2.2점 이상)
        """
    )
    
    # 선택된 품질에 따른 설정값 표시
    if "고급" in quality_level:
        config = get_high_quality_config()
        st.sidebar.markdown("🔒 **고급 설정 (정확성 우선)**")
        st.sidebar.markdown(f"• 검색 점수: {config['search_threshold']} (35점 이상)")
        st.sidebar.markdown(f"• Reranker 점수: {config['reranker_threshold']} (2.8점 이상)")
        st.sidebar.markdown(f"• 최대 결과: {config['max_results']}개")
        st.sidebar.markdown("✅ 매우 관련성 높은 결과만")
        
    elif "초급" in quality_level:
        config = get_low_quality_config()
        st.sidebar.markdown("🔓 **초급 설정 (포괄성 우선)**")
        st.sidebar.markdown(f"• 검색 점수: {config['search_threshold']} (25점 이상)")
        st.sidebar.markdown(f"• Reranker 점수: {config['reranker_threshold']} (2.2점 이상)")
        st.sidebar.markdown(f"• 최대 결과: {config['max_results']}개")
        st.sidebar.markdown("📈 많은 결과, 일부 관련성 낮을 수 있음")
        
    else:  # 중급
        config = get_medium_quality_config()
        st.sidebar.markdown("⚖️ **중급 설정 (균형)**")
        st.sidebar.markdown(f"• 검색 점수: {config['search_threshold']} (30점 이상)")
        st.sidebar.markdown(f"• Reranker 점수: {config['reranker_threshold']} (2.5점 이상)")
        st.sidebar.markdown(f"• 최대 결과: {config['max_results']}개")
        st.sidebar.markdown("🎯 정확성과 결과 수의 최적 균형")
    
    # 고급 설정 (접기/펼치기)
    with st.sidebar.expander("🔧 상세 설정 보기"):
        st.markdown("**현재 적용 중인 임계값:**")
        st.json(config)
        
        st.markdown("**설정 설명:**")
        st.markdown("• `search_threshold`: 기본 검색 점수 최소값 (25점 이상 필수)")
        st.markdown("• `reranker_threshold`: AI 재순위 점수 최소값 (2.2점 이상 필수)")
        st.markdown("• `semantic_threshold`: 의미적 유사성 최소값")
        st.markdown("• `hybrid_threshold`: 종합 점수 최소값")
        st.markdown("• **중요**: 부정확한 결과 제거를 위해 임계값이 상향 조정되었습니다.")
    
    # 서비스명 파일 정보 표시
    with st.sidebar.expander("📁 서비스명 파일 정보"):
        st.markdown("**파일 위치:** `config/service_names.txt`")
        st.markdown("**매칭 방식:** 정확 매칭 + 포함 매칭 (공백 무시)")
        st.markdown("**특징:**")
        st.markdown("• 대소문자 구분 없음")
        st.markdown("• 공백, 하이픈, 언더스코어 무시")
        st.markdown("• 부분 매칭 지원")
        st.markdown("• 유사도 기반 fallback 매칭")
    
    return config

def get_high_quality_config():
    """고급 설정 (정확성 우선) - 관련없는 결과 최소화"""
    return {
        'search_threshold': 0.35,      # 매우 높은 검색 점수 (35점)
        'reranker_threshold': 2.8,     # 매우 높은 Reranker 점수 (2.8점)
        'semantic_threshold': 0.5,     # 매우 높은 의미적 유사성
        'hybrid_threshold': 0.6,       # 매우 높은 종합 점수
        'max_results': 6,              # 적은 결과 수
        'quality_level': 'high',
        'description': '매우 정확하지만 결과 수 적음 (검색점수 35점, Reranker 2.8점 이상)'
    }

def get_medium_quality_config():
    """중급 설정 (균형) - 정확성과 결과 수의 균형"""
    return {
        'search_threshold': 0.30,      # 높은 검색 점수 (30점)
        'reranker_threshold': 2.5,     # 높은 Reranker 점수 (2.5점)
        'semantic_threshold': 0.4,     # 높은 의미적 유사성
        'hybrid_threshold': 0.5,       # 높은 종합 점수
        'max_results': 8,              # 적당한 결과 수
        'quality_level': 'medium',
        'description': '정확성과 결과 수의 최적 균형 (검색점수 30점, Reranker 2.5점 이상)'
    }

def get_low_quality_config():
    """초급 설정 (포괄성 우선) - 관련 문서 최대 발견"""
    return {
        'search_threshold': 0.25,      # 적당한 검색 점수 (25점)
        'reranker_threshold': 2.2,     # 적당한 Reranker 점수 (2.2점)
        'semantic_threshold': 0.3,     # 적당한 의미적 유사성
        'hybrid_threshold': 0.4,       # 적당한 종합 점수
        'max_results': 10,             # 많은 결과 수
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
    
    # 사이드바에 검색 품질 선택기 추가
    selected_quality_config = add_search_quality_selector()
    
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
    
    # 현재 적용된 품질 설정 표시 (메인 화면)
    st.info(f"""
    🎯 **현재 검색 품질 설정**: {selected_quality_config['description']}
    - 검색 점수 임계값: {selected_quality_config['search_threshold']} ({int(selected_quality_config['search_threshold']*100)}점 이상)
    - Reranker 점수 임계값: {selected_quality_config['reranker_threshold']} ({selected_quality_config['reranker_threshold']}점 이상)
    - 최대 결과 수: {selected_quality_config['max_results']}개
    - 📁 **서비스명 매칭**: config/service_names.txt 파일 기반 (공백 무시 매칭)
    """)
    
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