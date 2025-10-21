import streamlit as st
from openai import AzureOpenAI

class AzureClientManager:
    """웹 검색 기반 Azure 클라이언트 관리 클래스"""
    
    def __init__(self, config):
        self.config = config
    
    @st.cache_resource
    def init_clients(_self):
        """Azure OpenAI 클라이언트만 초기화 (검색 클라이언트 제거)"""
        try:
            # Azure OpenAI 클라이언트 설정
            azure_openai_client = AzureOpenAI(
                azure_endpoint=_self.config.azure_openai_endpoint,
                api_key=_self.config.azure_openai_key,
                api_version=_self.config.azure_openai_api_version
            )
            
            return azure_openai_client, True
            
        except Exception as e:
            st.error(f"Azure OpenAI 클라이언트 초기화 실패: {str(e)}")
            return None, False