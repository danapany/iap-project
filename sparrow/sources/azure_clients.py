import streamlit as st
import hashlib
import json
from datetime import datetime, timedelta
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

class VectorEmbeddingClient:
    """벡터 임베딩 생성 및 캐싱 관리 클라이언트"""
    
    def __init__(self, azure_openai_client, config):
        self.client = azure_openai_client
        self.config = config
        self.embedding_model = config.embedding_model
        self.cache_enabled = config.enable_embedding_cache
        self.cache_ttl = config.embedding_cache_ttl
        
        # 세션 상태에 임베딩 캐시 초기화
        if 'embedding_cache' not in st.session_state:
            st.session_state.embedding_cache = {}
    
    def _get_cache_key(self, text):
        """텍스트에 대한 캐시 키 생성"""
        return hashlib.md5(f"{text}_{self.embedding_model}".encode()).hexdigest()
    
    def _is_cache_valid(self, cache_entry):
        """캐시 항목이 유효한지 확인"""
        if not cache_entry:
            return False
        
        cache_time = datetime.fromisoformat(cache_entry.get('timestamp', ''))
        expiry_time = cache_time + timedelta(seconds=self.cache_ttl)
        return datetime.now() < expiry_time
    
    def _clean_expired_cache(self):
        """만료된 캐시 항목 정리"""
        if not self.cache_enabled:
            return
        
        current_cache = st.session_state.embedding_cache
        valid_cache = {}
        
        for key, entry in current_cache.items():
            if self._is_cache_valid(entry):
                valid_cache[key] = entry
        
        st.session_state.embedding_cache = valid_cache
    
    def get_embedding(self, text, use_cache=True):
        """텍스트에 대한 임베딩 벡터 생성"""
        if not text or not text.strip():
            return []
        
        text = text.strip()
        cache_key = self._get_cache_key(text)
        
        # 캐시에서 확인
        if use_cache and self.cache_enabled:
            cached_entry = st.session_state.embedding_cache.get(cache_key)
            if cached_entry and self._is_cache_valid(cached_entry):
                return cached_entry['embedding']
        
        try:
            # Azure OpenAI를 통한 임베딩 생성
            response = self.client.embeddings.create(
                input=text,
                model=self.embedding_model
            )
            
            embedding = response.data[0].embedding
            
            # 캐시에 저장
            if use_cache and self.cache_enabled:
                st.session_state.embedding_cache[cache_key] = {
                    'embedding': embedding,
                    'timestamp': datetime.now().isoformat(),
                    'model': self.embedding_model,
                    'text_length': len(text)
                }
                
                # 주기적으로 만료된 캐시 정리
                if len(st.session_state.embedding_cache) % 50 == 0:
                    self._clean_expired_cache()
            
            return embedding
            
        except Exception as e:
            print(f"ERROR: 임베딩 생성 실패: {str(e)}")
            return []
    
    def get_batch_embeddings(self, texts, use_cache=True, batch_size=100):
        """여러 텍스트에 대한 배치 임베딩 생성"""
        if not texts:
            return []
        
        embeddings = []
        texts_to_embed = []
        cached_embeddings = {}
        
        # 캐시에서 사용 가능한 임베딩 확인
        if use_cache and self.cache_enabled:
            for i, text in enumerate(texts):
                if not text or not text.strip():
                    cached_embeddings[i] = []
                    continue
                    
                cache_key = self._get_cache_key(text.strip())
                cached_entry = st.session_state.embedding_cache.get(cache_key)
                
                if cached_entry and self._is_cache_valid(cached_entry):
                    cached_embeddings[i] = cached_entry['embedding']
                else:
                    texts_to_embed.append((i, text.strip()))
        else:
            texts_to_embed = [(i, text.strip()) for i, text in enumerate(texts) if text and text.strip()]
        
        # 캐시에 없는 텍스트들에 대해 배치 임베딩 생성
        if texts_to_embed:
            try:
                # 배치 크기로 나누어서 처리
                for batch_start in range(0, len(texts_to_embed), batch_size):
                    batch_texts = texts_to_embed[batch_start:batch_start + batch_size]
                    batch_input = [text for _, text in batch_texts]
                    
                    response = self.client.embeddings.create(
                        input=batch_input,
                        model=self.embedding_model
                    )
                    
                    # 결과를 캐시에 저장
                    for j, (original_index, text) in enumerate(batch_texts):
                        embedding = response.data[j].embedding
                        cached_embeddings[original_index] = embedding
                        
                        if use_cache and self.cache_enabled:
                            cache_key = self._get_cache_key(text)
                            st.session_state.embedding_cache[cache_key] = {
                                'embedding': embedding,
                                'timestamp': datetime.now().isoformat(),
                                'model': self.embedding_model,
                                'text_length': len(text)
                            }
                        
            except Exception as e:
                print(f"ERROR: 배치 임베딩 생성 실패: {str(e)}")
                # 실패한 경우 개별적으로 처리
                for original_index, text in texts_to_embed:
                    if original_index not in cached_embeddings:
                        cached_embeddings[original_index] = self.get_embedding(text, use_cache)
        
        # 원래 순서대로 임베딩 재구성
        for i in range(len(texts)):
            embeddings.append(cached_embeddings.get(i, []))
        
        return embeddings
    
    def get_cache_stats(self):
        """캐시 통계 반환"""
        if not self.cache_enabled:
            return {"cache_enabled": False}
        
        cache = st.session_state.embedding_cache
        total_entries = len(cache)
        valid_entries = sum(1 for entry in cache.values() if self._is_cache_valid(entry))
        
        return {
            "cache_enabled": True,
            "total_entries": total_entries,
            "valid_entries": valid_entries,
            "cache_hit_rate": valid_entries / max(total_entries, 1),
            "cache_ttl_hours": self.cache_ttl / 3600
        }
    
    def clear_cache(self):
        """캐시 완전 삭제"""
        st.session_state.embedding_cache = {}
        return True


class AzureClientManager:
    """Azure 클라이언트 관리 클래스 - Vector 지원 추가"""
    
    def __init__(self, config):
        self.config = config
    
    @st.cache_resource
    def init_clients(_self):
        """Azure 클라이언트 초기화 - 임베딩 클라이언트 추가"""
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
            
            # Vector 임베딩 클라이언트 설정
            embedding_client = VectorEmbeddingClient(azure_openai_client, _self.config)
            
            # 연결 테스트
            test_result = _self._test_connections(azure_openai_client, search_client, embedding_client)
            
            return azure_openai_client, search_client, embedding_client, test_result
            
        except Exception as e:
            st.error(f"클라이언트 초기화 실패: {str(e)}")
            return None, None, None, False
    
    def _test_connections(self, openai_client, search_client, embedding_client):
        """클라이언트 연결 테스트"""
        try:
            # OpenAI 연결 테스트
            openai_client.chat.completions.create(
                model=self.config.azure_openai_model,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1
            )
            
            # Search 연결 테스트
            search_client.search(search_text="*", top=1)
            
            # Embedding 연결 테스트
            test_embedding = embedding_client.get_embedding("연결 테스트", use_cache=False)
            if not test_embedding:
                raise Exception("임베딩 생성 실패")
            
            return True
            
        except Exception as e:
            print(f"연결 테스트 실패: {str(e)}")
            return False
    
    def get_client_status(self):
        """클라이언트 상태 정보 반환"""
        try:
            azure_openai_client, search_client, embedding_client, success = self.init_clients()
            
            if not success:
                return {"status": "error", "message": "클라이언트 초기화 실패"}
            
            # 임베딩 캐시 통계
            cache_stats = embedding_client.get_cache_stats()
            
            return {
                "status": "connected",
                "openai_model": self.config.azure_openai_model,
                "embedding_model": self.config.embedding_model,
                "search_index": self.config.search_index,
                "cache_stats": cache_stats,
                "vector_config": self.config.get_vector_search_config()
            }
            
        except Exception as e:
            return {
                "status": "error", 
                "message": f"상태 확인 실패: {str(e)}"
            }


class HybridSearchClient:
    """하이브리드 검색 전용 클라이언트"""
    
    def __init__(self, search_client, embedding_client, config):
        self.search_client = search_client
        self.embedding_client = embedding_client
        self.config = config
    
    def execute_hybrid_search(self, query_text, query_vector=None, search_mode="hybrid_balanced", **kwargs):
        """하이브리드 검색 실행"""
        try:
            # 쿼리 벡터 생성 (제공되지 않은 경우)
            if query_vector is None and query_text:
                query_vector = self.embedding_client.get_embedding(query_text)
            
            # 검색 모드에 따른 파라미터 설정
            search_params = self._get_search_params(search_mode, **kwargs)
            
            # Azure AI Search 하이브리드 검색 실행
            results = self.search_client.search(
                search_text=query_text,
                vector_queries=[{
                    "vector": query_vector,
                    "k_nearest_neighbors": search_params["vector_top_k"],
                    "fields": "contentVector"
                }] if query_vector else None,
                query_type="semantic" if search_params["use_semantic"] else "simple",
                semantic_configuration_name="iap-incident-semantic-config" if search_params["use_semantic"] else None,
                top=search_params["top_k"],
                search_mode="all" if query_text and query_vector else ("any" if query_text else None),
                select=search_params.get("select_fields", ["*"]),
                include_total_count=True,
                **search_params.get("additional_params", {})
            )
            
            return list(results)
            
        except Exception as e:
            print(f"ERROR: 하이브리드 검색 실행 실패: {str(e)}")
            return []
    
    def _get_search_params(self, search_mode, **kwargs):
        """검색 모드별 파라미터 설정"""
        base_params = {
            "top_k": kwargs.get("top_k", self.config.final_top_k),
            "vector_top_k": kwargs.get("vector_top_k", self.config.vector_top_k),
            "use_semantic": kwargs.get("use_semantic", True),
            "select_fields": kwargs.get("select_fields"),
            "additional_params": kwargs.get("additional_params", {})
        }
        
        if search_mode == "vector_primary":
            # 벡터 검색 우선
            base_params.update({
                "vector_top_k": min(base_params["vector_top_k"] * 2, 100),
                "use_semantic": True
            })
        elif search_mode == "text_primary":
            # 텍스트 검색 우선
            base_params.update({
                "vector_top_k": max(base_params["vector_top_k"] // 2, 10),
                "use_semantic": False
            })
        # hybrid_balanced는 기본 설정 사용
        
        return base_params