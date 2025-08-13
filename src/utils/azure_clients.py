import streamlit as st
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

class AzureClientManager:
    """Azure 클라이언트 관리 클래스"""
    
    def __init__(self, config):
        self.config = config
    
    @st.cache_resource
    def init_clients(_self):
        """Azure 클라이언트 초기화"""
        try:
            # Azure OpenAI 클라이언트 설정
            azure_openai_client = AzureOpenAI(
                azure_endpoint=_self.config.azure_openai_endpoint,
                api_key=_self.config.azure_openai_key,
                api_version=_self.config.azure_openai_api_version
            )
            
            # Azure AI Search 클라이언트 설정
            search_client = SearchClient(
                endpoint=_self.config.search_endpoint,
                index_name=_self.config.search_index,
                credential=AzureKeyCredential(_self.config.search_key)
            )
            
            return azure_openai_client, search_client, True
            
        except Exception as e:
            st.error(f"클라이언트 초기화 실패: {str(e)}")
            return None, None, False