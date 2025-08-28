import streamlit as st
from config.settings_local import AppConfigLocal
from utils.azure_clients import AzureClientManager
from utils.search_utils_local import SearchManagerLocal
from utils.ui_components_local import UIComponentsLocal
from utils.query_processor_local import QueryProcessorLocal

# =================================================================
# 검색 품질 설정 변수 (여기서 직접 수정 가능)
# =================================================================
DEFAULT_QUALITY_LEVEL = "고급"  # "고급 (정확성 우선)", "중급 (권장)", "초급 (포괄성 우선)"
DEFAULT_SEARCH_THRESHOLD = 0.25     # 검색 점수 임계값 (0.25 ~ 0.35)
DEFAULT_RERANKER_THRESHOLD = 2.2    # Reranker 점수 임계값 (2.2 ~ 2.8)
DEFAULT_MAX_RESULTS = 20             # 최대 결과 수 (6 ~ 10)
DEFAULT_SEMANTIC_THRESHOLD = 0.3    # 의미적 유사성 임계값 (0.3 ~ 0.5)
DEFAULT_HYBRID_THRESHOLD = 0.4      # 종합 점수 임계값 (0.4 ~ 0.6)

def get_high_quality_config():
    """고급 설정 (정확성 우선) - repair/cause에 최적화된 관련없는 결과 최소화"""
    return {
        'search_threshold': DEFAULT_SEARCH_THRESHOLD,      
        'reranker_threshold': DEFAULT_RERANKER_THRESHOLD,  
        'semantic_threshold': DEFAULT_SEMANTIC_THRESHOLD,     
        'hybrid_threshold': DEFAULT_HYBRID_THRESHOLD,       
        'max_results': DEFAULT_MAX_RESULTS,              
        'quality_level': 'high',
        'description': f'최고 정확성 - LLM 관련성 검증 적용 (검색점수 {int(DEFAULT_SEARCH_THRESHOLD*100)}점, Reranker {DEFAULT_RERANKER_THRESHOLD}점 이상)'
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
        'description': '정확성과 포괄성의 최적 균형 - 적응형 처리 (검색점수 20점, Reranker 2.0점 이상)'
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
        'description': '최대 포괄성 - 광범위한 검색 결과 활용 (검색점수 15점, Reranker 1.5점 이상)'
    }

def apply_quality_config_to_app_config(app_config, quality_config):
    """앱 설정에 선택된 품질 설정을 적용하여 쿼리 타입별 최적화"""
    
    # 기존 get_dynamic_thresholds 메서드를 개선된 버전으로 오버라이드
    original_get_dynamic_thresholds = app_config.get_dynamic_thresholds
    
    def get_enhanced_dynamic_thresholds(query_type="default", query_text=""):
        """쿼리 타입별 최적화된 동적 임계값 설정"""
        
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
                'description': f'정확성 우선 처리 - LLM 관련성 검증 적용'
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
                'description': f'포괄성 우선 처리 - 광범위한 검색 결과 활용'
            }
        else:
            # 기본 설정
            enhanced_thresholds = quality_config.copy()
            enhanced_thresholds['processing_mode'] = 'balanced'
            enhanced_thresholds['description'] = '균형잡힌 처리'
        
        # 기본 임계값과 병합
        base_thresholds.update(enhanced_thresholds)
        return base_thresholds
    
    app_config.get_dynamic_thresholds = get_enhanced_dynamic_thresholds
    
    return app_config

def main():
    """메인 애플리케이션 실행 - 쿼리 타입별 최적화된 통합 처리"""
    
    # 페이지 설정
    st.set_page_config(
        page_title="트러블 체이서 챗봇",
        page_icon="🤖",
        layout="wide"
    )
    
    # 메인 페이지 제목
    st.title("트러블 체이서 챗봇")
    
    # 처리 모드 정보 (전역 정의) - 오류 수정
    processing_modes = {
        'repair': '정확성 우선 (LLM 검증)',
        'cause': '정확성 우선 (키워드 매칭)',
        'similar': '포괄성 우선 (의미적 유사성)',
        'default': '포괄성 우선 (광범위 검색)'
    }
    
    # 상단 변수 설정을 기본 품질 설정으로 사용
    if "고급" in DEFAULT_QUALITY_LEVEL:
        selected_quality_config = get_high_quality_config()
        #st.info("정확성 우선 모드: repair/cause 쿼리에서 LLM 관련성 검증을 통한 최고 정확성 제공")
    elif "초급" in DEFAULT_QUALITY_LEVEL:
        selected_quality_config = get_low_quality_config()
        #st.info("포괄성 우선 모드: similar/default 쿼리에서 광범위한 검색을 통한 최대 커버리지 제공")
    else:
        selected_quality_config = get_medium_quality_config()
        #st.info("균형 모드: 모든 쿼리 타입에서 정확성과 포괄성의 최적 균형 제공")
    
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
    user_query = st.chat_input("질문을 입력하세요 (AI가 자동으로 최적 처리 방식을 선택합니다)")
    
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
        
        # 향상된 쿼리 처리 (쿼리 타입별 최적화된 config 전달)
        query_processor = QueryProcessorLocal(
            azure_openai_client, 
            search_client, 
            config.azure_openai_model,
            config  # 쿼리 타입별 최적화가 적용된 config 객체를 전달
        )
        query_processor.process_query(user_query)


if __name__ == "__main__":
    main()