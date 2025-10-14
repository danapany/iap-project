import streamlit as st
import re
import math
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from config.settings_local import AppConfigLocal
from utils.filter_manager import DocumentFilterManager, FilterConditions, QueryType

class SearchManagerLocal:
    """Vector 하이브리드 검색 관리 클래스 - RAG 데이터 무결성 절대 보장"""
    
    def __init__(self, search_client, embedding_client, config=None):
        self.search_client = search_client
        self.embedding_client = embedding_client
        self.config = config or AppConfigLocal()
        self.debug_mode = False
        
        # 통합 필터링 매니저
        self.filter_manager = DocumentFilterManager(
            debug_mode=self.debug_mode, 
            search_manager=self, 
            config=self.config
        )
        
        # 캐시 변수들
        self._service_names_cache = None
        self._cache_loaded = False
        self._effect_patterns_cache = None
        self._effect_cache_loaded = False
        self._service_names_file_cache = None
        self._service_file_cache_loaded = False
        
        # RRF 파라미터
        self.rrf_k = getattr(config, 'rrf_k', 60)
        
        # 통계 쿼리 동의어 매핑
        self.statistics_synonyms = {
            '몇건이야': '몇건', '몇건이니': '몇건', '몇건인가': '몇건',
            '알려줘': '', '보여줘': '', '말해줘': ''
        }
        
        # 텍스트 정규화 매핑
        self.text_replacements = {
            'ㄱ': 'ㄱ', 'ㄴ': 'ㄴ', 'ㄷ': 'ㄷ', 'ㄹ': 'ㄹ', 'ㅁ': 'ㅁ',
            'ㅂ': 'ㅂ', 'ㅅ': 'ㅅ', 'ㅇ': 'ㅇ', 'ㅈ': 'ㅈ', 'ㅊ': 'ㅊ',
            'ㅋ': 'ㅋ', 'ㅌ': 'ㅌ', 'ㅍ': 'ㅍ', 'ㅎ': 'ㅎ'
        }
        
        # 일반 용어 서비스 정의
        self.COMMON_TERM_SERVICES = {
            'OTP': ['otp', '일회용비밀번호', '원타임패스워드', '2차인증', '이중인증'],           
            '본인인증': ['실명인증', '신원확인'],
            'API': ['api', 'Application Programming Interface', 'REST API', 'API호출'],
            'SMS': ['sms', '문자', '단문', 'Short Message Service', '문자메시지'],
            'VPN': ['vpn', 'Virtual Private Network', '가상사설망'],
            'DNS': ['dns', 'Domain Name System', '도메인네임시스템'],
            'SSL': ['ssl', 'https', 'Secure Sockets Layer', '보안소켓계층'],
            'URL': ['url', 'link', '링크', 'Uniform Resource Locator']
        }

    def _load_service_names_from_file(self):
        """config/service_names.txt 파일에서 서비스명 목록 로드"""
        try:
            # search_utils_local.py는 src/utils/에 위치
            # service_names.txt는 src/config/에 위치
            # 따라서 상대 경로: ../config/service_names.txt
            current_dir = Path(__file__).parent
            config_path = current_dir.parent / "config" / "service_names.txt"
            
            if not config_path.exists() or not config_path.is_file():
                print(f"WARNING: service_names.txt file not found at: {config_path}")
                return []
            
            print(f"DEBUG: Found service_names.txt at: {config_path}")
            
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    service_names = []
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        # 빈 줄이나 주석(#으로 시작) 제외
                        if line and not line.startswith('#'):
                            service_names.append(line)
                    
                    if service_names:
                        print(f"DEBUG: Successfully loaded {len(service_names)} service names from file")
                        # 길이순으로 정렬 (긴 것부터) - 매칭 정확도 향상
                        return sorted(set(service_names), key=len, reverse=True)
                    else:
                        print(f"WARNING: service_names.txt is empty: {config_path}")
                        return []
                        
            except UnicodeDecodeError:
                print(f"ERROR: UTF-8 encoding error, trying EUC-KR encoding")
                try:
                    with open(config_path, 'r', encoding='euc-kr') as f:
                        service_names = [line.strip() for line in f 
                                    if line.strip() and not line.startswith('#')]
                        if service_names:
                            print(f"DEBUG: Successfully loaded {len(service_names)} service names with EUC-KR encoding")
                            return sorted(set(service_names), key=len, reverse=True)
                        return []
                except Exception as e:
                    print(f"ERROR: Failed to read with EUC-KR encoding: {e}")
                    return []
                    
            except Exception as e:
                print(f"ERROR: Failed to read {config_path}: {e}")
                return []
            
        except Exception as e:
            print(f"ERROR: Critical failure in _load_service_names_from_file: {e}")
            return []

    
    def get_service_names_from_file(self):
        """파일 기반 서비스명 목록 가져오기 (캐시 활용)"""
        if not self._service_file_cache_loaded:
            self._service_names_file_cache = self._load_service_names_from_file()
            self._service_file_cache_loaded = True
        return self._service_names_file_cache or []
    
    def _find_service_name_in_file(self, query):
        """conf/service_names.txt에서 서비스명 찾기"""
        file_service_names = self.get_service_names_from_file()
        if not file_service_names:
            print("DEBUG: No service names loaded from file")
            return None
            
        query_lower = query.lower().strip()
        query_tokens = self._extract_service_tokens(query)
        candidates = []
        
        print(f"DEBUG: Searching in {len(file_service_names)} file service names for query: '{query}'")
        
        for service_name in file_service_names:
            service_lower = service_name.lower()
            
            # 1. 정확한 매칭 (최우선)
            if service_name == query.strip() or service_lower == query_lower:
                print(f"DEBUG: Exact match found: '{service_name}'")
                return service_name
            
            # 2. 완전 포함 관계 매칭
            if service_lower in query_lower:
                candidates.append((service_name, 1.0, 'file_service_in_query'))
                print(f"DEBUG: Service in query match: '{service_name}' in '{query}'")
                continue
                
            if query_lower in service_lower:
                candidates.append((service_name, 0.95, 'file_query_in_service'))
                print(f"DEBUG: Query in service match: '{query}' in '{service_name}'")
                continue
            
            # 3. 공백 무시한 매칭
            service_no_space = re.sub(r'\s+', '', service_lower)
            query_no_space = re.sub(r'\s+', '', query_lower)
            
            if service_no_space in query_no_space:
                candidates.append((service_name, 0.9, 'file_no_space_service_in_query'))
                continue
                
            if query_no_space in service_no_space:
                candidates.append((service_name, 0.85, 'file_no_space_query_in_service'))
                continue
            
            # 4. 토큰 기반 유사도 매칭 (더 엄격한 기준)
            service_tokens = self._extract_service_tokens(service_name)
            if query_tokens and service_tokens:
                similarity = self._calculate_service_similarity(query_tokens, service_tokens)
                if similarity >= 0.7:  # 기존 0.6에서 0.7로 상향 조정
                    candidates.append((service_name, similarity, 'file_token_similarity'))
                    print(f"DEBUG: Token similarity match: '{service_name}' (score: {similarity:.2f})")
        
        if candidates:
            # 점수 기준으로 정렬
            candidates.sort(key=lambda x: x[1], reverse=True)
            best_match = candidates[0]
            print(f"DEBUG: Best file match: '{best_match[0]}' (score: {best_match[1]:.2f}, method: {best_match[2]})")
            return best_match[0]
        
        print(f"DEBUG: No match found in file service names")
        return None

    def semantic_search_with_adaptive_filtering(self, query, target_service_name=None, query_type="default", top_k=50):
        """메인 검색 진입점 - RAG 데이터 무결성 절대 보장"""
        try:
            print(f"DEBUG: Vector hybrid search: '{query}', service: {target_service_name}")
            
            # 하이브리드 검색 실행
            documents = self._execute_vector_hybrid_search(query, target_service_name, query_type, top_k)
            
            if not documents:
                return []
            
            # 통합 필터링 시스템 적용
            query_type_enum = self._convert_to_query_type_enum(query_type)
            conditions = self.filter_manager.extract_all_conditions(query, query_type_enum)
            
            # 벡터 검색 설정 적용
            vector_config = self.config.get_vector_search_config(query_type)
            conditions.search_threshold = vector_config.get('vector_similarity_threshold', 0.5)
            
            # 서비스명 정보 설정
            if target_service_name:
                conditions.target_service_name = target_service_name
                conditions.service_name = target_service_name
                conditions.is_common_service = self.is_common_term_service(target_service_name)[0]
            
            # 하이브리드 필터링 적용
            filtered_documents, filter_history = self.filter_manager.apply_comprehensive_filtering(
                documents, query, query_type_enum, conditions=conditions
            )
            
            # 결과가 없으면 fallback
            if len(filtered_documents) == 0 and len(documents) > 0:
                print(f"WARNING: Vector filtering removed all documents! Returning top results")
                sorted_docs = sorted(documents, key=lambda d: d.get('hybrid_score', 0) or 0, reverse=True)
                filtered_documents = sorted_docs[:15]
            
            return filtered_documents
            
        except Exception as e:
            print(f"DEBUG: Vector hybrid search error: {e}")
            return self._fallback_to_original_search(query, target_service_name, query_type, top_k//2)

    def _execute_vector_hybrid_search(self, query, target_service_name, query_type, top_k):
        """벡터 하이브리드 검색 실행 - RAG 데이터 무결성 보장"""
        try:
            vector_config = self.config.get_vector_search_config(query_type)
            search_mode = self.config.get_search_mode_for_query(query_type, query)
            
            # 쿼리 임베딩 생성
            query_vector = self.embedding_client.get_embedding(query)
            if not query_vector:
                return self._execute_text_only_search(query, target_service_name, query_type, top_k)
            
            # 검색 모드에 따른 실행
            search_methods = {
                "vector_primary": self._execute_vector_primary_search,
                "text_primary": self._execute_text_primary_search,
                "hybrid_balanced": self._execute_balanced_hybrid_search
            }
            
            search_method = search_methods.get(search_mode, self._execute_balanced_hybrid_search)
            documents = search_method(query, query_vector, target_service_name, vector_config, top_k)
            
            # RRF 스코어링 및 정규화 적용
            documents = self._apply_rrf_scoring_and_normalization(documents, vector_config)
            
            return documents
            
        except Exception as e:
            print(f"ERROR: Vector hybrid search execution failed: {e}")
            return self._fallback_to_original_search(query, target_service_name, query_type, top_k)

    def _execute_balanced_hybrid_search(self, query, query_vector, target_service_name, vector_config, top_k):
        """균형잡힌 하이브리드 검색"""
        try:
            enhanced_query = self._build_enhanced_query(query, target_service_name)
            
            vector_queries = [{
                "kind": "vector",
                "vector": query_vector,
                "k_nearest_neighbors": min(self.config.vector_top_k, 50),
                "fields": "contentVector"
            }]
            
            results = self._execute_search_with_params(
                enhanced_query, vector_queries, 
                "semantic" if vector_config.get('use_semantic_reranker', True) else "simple",
                top_k, "any"
            )
            
            return self._process_search_results(results, "Hybrid")
            
        except Exception as e:
            print(f"ERROR: Balanced hybrid search failed: {e}")
            return []
    
    def _execute_vector_primary_search(self, query, query_vector, target_service_name, vector_config, top_k):
        """벡터 검색 우선 모드"""
        try:
            vector_queries = [{
                "kind": "vector",
                "vector": query_vector,
                "k_nearest_neighbors": min(top_k * 2, 100),
                "fields": "contentVector"
            }]
            
            basic_query = self._build_basic_query(query, target_service_name)
            
            results = self._execute_search_with_params(
                basic_query if basic_query else "*", vector_queries, "semantic", top_k, "any"
            )
            
            return self._process_search_results(results, "Vector Primary")
            
        except Exception as e:
            print(f"ERROR: Vector primary search failed: {e}")
            return []
    
    def _execute_text_primary_search(self, query, query_vector, target_service_name, vector_config, top_k):
        """텍스트 검색 우선 모드"""
        try:
            enhanced_query = self._build_enhanced_query(query, target_service_name)
            
            vector_queries = [{
                "kind": "vector",
                "vector": query_vector,
                "k_nearest_neighbors": min(top_k // 2, 25),
                "fields": "contentVector"
            }] if query_vector else None
            
            results = self._execute_search_with_params(
                enhanced_query, vector_queries, "simple", top_k, 
                "any" if vector_queries else "all"
            )
            
            return self._process_search_results(results, "Text Primary")
            
        except Exception as e:
            print(f"ERROR: Text primary search failed: {e}")
            return []
    
    def _execute_text_only_search(self, query, target_service_name, query_type, top_k):
        """텍스트 전용 검색"""
        try:
            enhanced_query = self._build_enhanced_query(query, target_service_name)
            
            results = self._execute_search_with_params(
                enhanced_query, None, "semantic", top_k, "all"
            )
            
            return self._process_search_results(results, "Text-only fallback")
            
        except Exception as e:
            print(f"ERROR: Text-only search failed: {e}")
            return []
    
    def _execute_search_with_params(self, search_text, vector_queries, query_type, top_k, search_mode="any"):
        """공통 검색 실행 로직"""
        search_params = {
            "search_text": search_text,
            "top": top_k,
            "search_mode": search_mode,
            "include_total_count": True,
            "select": [
                "incident_id", "service_name", "error_time", "effect", "symptom", 
                "repair_notice", "error_date", "week", "daynight", "root_cause", 
                "incident_repair", "incident_plan", "cause_type", "done_type", 
                "incident_grade", "owner_depart", "year", "month"
            ]
        }
        
        if vector_queries:
            search_params["vector_queries"] = vector_queries
            
        if query_type == "semantic":
            search_params.update({
                "query_type": "semantic",
                "semantic_configuration_name": "iap-incident-semantic-config"
            })
        elif query_type == "simple":
            search_params["query_type"] = "simple"
        
        return self.search_client.search(**search_params)
    
    def _process_search_results(self, results, search_type):
        """검색 결과 처리"""
        documents = []
        for i, result in enumerate(results):
            if i < 5:  # 디버그용 상위 5개 로그
                print(f"DEBUG: {search_type} Result {i+1}: ID={result.get('incident_id')}, "
                      f"search_score={result.get('@search.score')}, "
                      f"reranker_score={result.get('@search.reranker_score')}")
            
            doc = self._convert_search_result_to_document(result)
            documents.append(doc)
        
        return documents
    
    def _convert_search_result_to_document(self, result):
        """RAG 원본 데이터 절대 보존 - 단일 구현"""
        base_fields = [
            "incident_id", "service_name", "effect", "symptom", "repair_notice",
            "error_date", "week", "daynight", "root_cause", "incident_repair",
            "incident_plan", "cause_type", "done_type", "incident_grade",
            "owner_depart", "year", "month"
        ]
        
        doc = {}
        
        # 각 필드를 원본 그대로 보존
        for field in base_fields:
            original_value = result.get(field)
            doc[field] = original_value if original_value is not None else ""
        
        # error_time은 숫자 변환만 수행
        doc["error_time"] = self._parse_error_time(result.get("error_time", 0))
        
        # 검색 관련 메타데이터 추가
        doc.update({
            "score": result.get("@search.score") or 0.0,
            "reranker_score": result.get("@search.reranker_score") or 0.0,
            "captions": result.get("@search.captions", []),
            "highlights": result.get("@search.highlights", {}),
            "_data_integrity_preserved": True,
            "_original_search_result": True
        })
        
        return doc

    def _parse_error_time(self, error_time_raw):
        """error_time 파싱"""
        try:
            if error_time_raw is None:
                return 0
            if isinstance(error_time_raw, str):
                cleaned = error_time_raw.strip()
                if not cleaned or cleaned.lower() in ['null', 'none', 'n/a', '']:
                    return 0
                return int(float(cleaned))
            return int(error_time_raw)
        except (ValueError, TypeError):
            print(f"WARNING: Failed to parse error_time: {error_time_raw}, using 0")
            return 0
    
    def _apply_rrf_scoring_and_normalization(self, documents, vector_config):
        """RRF 스코어링 및 정규화"""
        if not documents:
            return documents
        
        try:
            for i, doc in enumerate(documents):
                search_score = doc.get('score', 0) or 0
                reranker_score = doc.get('reranker_score', 0) or 0
                
                # RRF 스코어 계산
                rrf_score = 1.0 / (self.rrf_k + i + 1)
                
                # 가중 평균으로 하이브리드 스코어 생성
                vector_weight = vector_config.get('vector_weight', 0.5)
                text_weight = vector_config.get('text_weight', 0.5)
                
                # 정규화된 스코어들
                normalized_search = min(search_score, 1.0) if search_score else 0
                normalized_reranker = min(reranker_score / 4.0, 1.0) if reranker_score else 0
                
                # 하이브리드 스코어 계산
                hybrid_score = (
                    (normalized_search * text_weight) + 
                    (normalized_reranker * vector_weight) + 
                    (rrf_score * 0.1)
                )
                
                # 스코어 정보 저장
                doc.update({
                    'hybrid_score': hybrid_score,
                    'rrf_score': rrf_score,
                    'normalized_search_score': normalized_search,
                    'normalized_reranker_score': normalized_reranker,
                    'vector_weight_used': vector_weight,
                    'text_weight_used': text_weight,
                    '_scoring_applied': True
                })
            
            # 하이브리드 스코어로 재정렬
            documents.sort(key=lambda d: d.get('hybrid_score', 0), reverse=True)
            
            print(f"DEBUG: Applied RRF scoring to {len(documents)} documents")
            return documents
            
        except Exception as e:
            print(f"ERROR: RRF scoring failed: {e}")
            return documents
    
    def _build_enhanced_query(self, query, target_service_name):
        """향상된 검색 쿼리 구성"""
        try:
            # 등급 정보 추출
            grade_info = self.extract_incident_grade_from_query(query)
            
            # 시간 정보 추출
            time_info = self._extract_year_month_from_query_unified(query)
            
            # 의미적 확장
            expanded_query = self._expand_query_with_semantic_similarity(query)
            
            # 등급 조건 추가
            if grade_info['has_grade_query']:
                expanded_query = self.build_grade_search_query(expanded_query, grade_info)
            
            # 시간 조건 추가
            enhanced_query = self._add_time_conditions(expanded_query, time_info)
            
            # 서비스명 조건
            if target_service_name:
                enhanced_query = self._add_service_conditions(enhanced_query, target_service_name)
            
            return enhanced_query
            
        except Exception as e:
            print(f"ERROR: Enhanced query building failed: {e}")
            return query
    
    def _add_time_conditions(self, query, time_info):
        """시간 조건을 쿼리에 추가"""
        if not (time_info['year'] or time_info['months']):
            return query
            
        time_conditions = []
        
        if time_info['year']:
            time_conditions.append(f'(year:"{time_info["year"]}" OR error_date:{time_info["year"]}-*)')
        
        if time_info['months']:
            month_conditions = []
            for month_num in time_info['months']:
                month_conditions.append(f'month:"{month_num}"')
                month_str = f"{month_num:02d}"
                if time_info['year']:
                    month_conditions.append(f'error_date:{time_info["year"]}-{month_str}-*')
                else:
                    month_conditions.append(f'error_date:*-{month_str}-*')
            time_conditions.append(f'({" OR ".join(month_conditions)})')
        
        if time_conditions:
            time_filter = " AND ".join(time_conditions)
            return f'({query}) AND {time_filter}' if query.strip() else time_filter
        
        return query
    
    def _add_service_conditions(self, query, target_service_name):
        """서비스명 조건을 쿼리에 추가"""
        is_common = self.is_common_term_service(target_service_name)[0]
        service_query = (f'service_name:"{target_service_name}"' if is_common 
                        else f'(service_name:"{target_service_name}" OR service_name:*{target_service_name}*)')
        return (f'{service_query} AND ({query})' if query != target_service_name 
                else f'{service_query} AND (*)')
    
    def _build_basic_query(self, query, target_service_name):
        """기본 검색 쿼리 구성"""
        basic_query = query
        
        if target_service_name:
            is_common = self.is_common_term_service(target_service_name)[0]
            service_query = (f'service_name:"{target_service_name}"' if is_common 
                           else f'service_name:*{target_service_name}*')
            basic_query = f'({service_query}) AND ({query})' if query else service_query
        
        return basic_query

    def _convert_to_query_type_enum(self, query_type_str):
        """문자열 쿼리 타입을 QueryType enum으로 변환"""
        mapping = {
            'repair': QueryType.REPAIR,
            'inquiry': QueryType.INQUIRY, 
            'statistics': QueryType.STATISTICS,
            'default': QueryType.DEFAULT
        }
        return mapping.get(query_type_str, QueryType.DEFAULT)
    
    def _fallback_to_original_search(self, query, target_service_name, query_type, top_k):
        """원래 검색 방식으로 fallback"""
        print("DEBUG: Falling back to original search method")
        try:
            return self.search_documents_with_service_filter(query, target_service_name, query_type, top_k)
        except:
            return []
    
    def _safe_execute(self, func, default_value=None, error_msg=""):
        """안전한 실행 헬퍼"""
        try:
            return func()
        except Exception as e:
            if error_msg and self.debug_mode:
                print(f"DEBUG: {error_msg}: {e}")
            return default_value
    
    def extract_incident_grade_from_query(self, query):
        """쿼리에서 장애등급 정보 추출"""
        grade_info = {'has_grade_query': False, 'specific_grade': None, 'grade_keywords': []}
        
        if not query:
            return grade_info
        
        query_lower = query.lower()
        
        # 일반 등급 키워드
        grade_general_keywords = ['등급', '장애등급', '전파등급', 'grade', '심각도']
        if any(k in query_lower for k in grade_general_keywords):
            grade_info['has_grade_query'] = True
            grade_info['grade_keywords'].extend([k for k in grade_general_keywords if k in query_lower])
        
        # 구체적인 등급 추출
        grade_patterns = [r'(\d+)등급', r'(\d+)급', r'(\d+)grade', r'등급.*?(\d+)', r'(\d+).*?등급']
        for pattern in grade_patterns:
            if matches := re.findall(pattern, query_lower):
                grade_info['specific_grade'] = f"{matches[0]}등급"
                grade_info['has_grade_query'] = True
                grade_info['grade_keywords'].append(grade_info['specific_grade'])
                break
        
        return grade_info
    
    def build_grade_search_query(self, query, grade_info):
        """장애등급 기반 검색 쿼리 구성"""
        if not grade_info['has_grade_query']:
            return query
        
        if grade_info['specific_grade']:
            grade_query = f'incident_grade:"{grade_info["specific_grade"]}"'
            cleaned_query = query
            for keyword in grade_info['grade_keywords']:
                cleaned_query = cleaned_query.replace(keyword, '').strip()
            return (grade_query if not cleaned_query or len(cleaned_query.strip()) < 2 
                   else f'({grade_query}) AND ({cleaned_query})')
        
        return query
    
    def is_common_term_service(self, service_name):
        """일반 용어로 사용되는 서비스명인지 확인"""
        if not service_name:
            return False, None
        
        service_lower = service_name.lower().strip()
        for common_service, aliases in self.COMMON_TERM_SERVICES.items():
            if (service_lower == common_service.lower() or 
                service_lower in [a.lower() for a in aliases]):
                return True, common_service
        return False, None
    
    def get_common_term_search_patterns(self, service_name):
        """일반 용어 서비스명에 대한 검색 패턴 생성"""
        is_common, main_service = self.is_common_term_service(service_name)
        if not is_common:
            return []
        
        patterns = [f'service_name:"{main_service}"']
        aliases = self.COMMON_TERM_SERVICES.get(main_service, [])
        
        # 별칭 패턴 추가
        for alias in aliases:
            patterns.append(f'service_name:"{alias}"')
        
        # 필드별 패턴 추가
        fields = ['effect', 'symptom', 'root_cause', 'incident_repair', 'repair_notice']
        for term in [main_service] + aliases:
            patterns.extend([f'({field}:"{term}")' for field in fields])
        
        return patterns

    def extract_query_keywords(self, query):
        """질문에서 핵심 키워드 추출"""
        keywords = {'service_keywords': [], 'symptom_keywords': [], 'action_keywords': [], 'time_keywords': []}
        
        normalized_query = self._normalize_statistics_query(query)
        
        # 패턴 정의 통합
        all_patterns = {
            'service_keywords': [
                r'\b(관리자|admin)\s*(웹|web|페이지|page)', r'\b(API|api)\s*(링크|link|서비스)',
                r'\b(ERP|erp)\b', r'\b(마이페이지|mypage)', r'\b(보험|insurance)', r'\b(커뮤니티|community)',
                r'\b(블록체인|blockchain)', r'\b(OTP|otp|일회용비밀번호)\b', r'\b(SMS|sms|문자|단문)\b',
                r'\b(VPN|vpn|가상사설망)\b', r'\b(DNS|dns|도메인)\b', r'\b(SSL|ssl|https|보안)\b',
                r'\b([A-Z]{2,10})\s*(?:서비스|시스템)?\s*(?:건수|통계|현황|몇|개수)',
                r'(?:건수|통계|현황|몇|개수)\s*.*?\b([A-Z]{2,10})\b',
            ],
            'symptom_keywords': [
                r'\b(로그인|login)\s*(불가|실패|안됨|오류)', r'\b(접속|연결)\s*(불가|실패|안됨|오류)',
                r'\b(가입|회원가입)\s*(불가|실패|안됨)', r'\b(결제|구매|주문)\s*(불가|실패|오류)',
                r'\b(응답|response)\s*(지연|늦림|없음)', r'\b(페이지|page)\s*(로딩|loading)\s*(불가|실패)',
                r'\b(문자|SMS)\s*(발송|전송)\s*(불가|실패|안됨)', r'\b(발송|전송|송신)\s*(불가|실패|안됨|오류)',
                r'\b(OTP|otp|일회용비밀번호)\s*(불가|실패|안됨|오류|지연)', r'\b(인증|2차인증|이중인증)\s*(불가|실패|안됨|오류)',
                r'\b(장애|오류|에러|문제)\s*(?:건수|통계|현황|몇|개수)',
                r'(?:건수|통계|현황|몇|개수)\s*.*?\b(장애|오류|에러|문제)\b',
            ],
            'time_keywords': [
                r'\b(202[0-9]|201[0-9])년?\b', r'\b(\d{1,2})월\b',
                r'\b(야간|주간|밤|낮|새벽|심야|오전|오후)\b',
                r'\b(월요일|화요일|수요일|목요일|금요일|토요일|일요일|평일|주말)\b',
            ]
        }
        
        # 모든 패턴에 대해 매칭 수행
        for key, pattern_list in all_patterns.items():
            for pattern in pattern_list:
                if matches := re.findall(pattern, normalized_query, re.IGNORECASE):
                    keywords[key].extend([m if isinstance(m, str) else ' '.join(m) for m in matches])
        
        return keywords
    
    def calculate_keyword_relevance_score(self, query, document):
        """키워드 기반 관련성 점수 계산"""
        query_keywords = self.extract_query_keywords(query)
        doc_text = ' '.join([document.get(f, '') for f in 
                           ['service_name', 'symptom', 'effect', 'root_cause', 'incident_repair']]).lower()
        
        score = 0
        keyword_weights = [('service_keywords', 40), ('symptom_keywords', 35), 
                          ('action_keywords', 15), ('time_keywords', 10)]
        
        for key, weight in keyword_weights:
            if any(k.lower() in doc_text for k in query_keywords[key]):
                score += weight
        
        return min(score, 100)

    @st.cache_data(ttl=3600)
    def _load_effect_patterns_from_rag(_self):
        """RAG 데이터에서 effect 필드의 패턴들을 분석하여 캐시"""
        return _self._safe_execute(lambda: {
            keyword: [{
                'original_effect': effect,
                'normalized_effect': _self._normalize_text_for_similarity(effect),
                'symptom': result.get("symptom", "").strip(),
                'service_name': result.get("service_name", "").strip(),
                'keywords': _self._extract_semantic_keywords(effect)
            } for result in _self.search_client.search(
                search_text="*", top=1000,
                select=["effect", "symptom", "service_name"],
                include_total_count=True
            ) if (effect := result.get("effect", "").strip()) 
               and keyword in (keywords := _self._extract_semantic_keywords(effect))]
            for keyword in set().union(*[_self._extract_semantic_keywords(r.get("effect", "")) 
                                       for r in _self.search_client.search(
                search_text="*", top=1000, select=["effect"], include_total_count=True
            ) if r.get("effect", "").strip()])
        }, {})
    
    def _normalize_text_for_similarity(self, text):
        """텍스트를 의미적 유사성 비교를 위해 정규화"""
        if not text:
            return ""
        
        normalized = re.sub(r'\s+', '', text.lower())
        
        for old, new in self.text_replacements.items():
            normalized = normalized.replace(old, new)
        
        return normalized
    
    def _extract_semantic_keywords(self, text):
        """텍스트에서 의미적 키워드 추출"""
        if not text:
            return []
        
        keyword_patterns = [
            r'(\w+)(불가|실패|에러|오류|지연|느림)', r'(\w+)(가입|등록|신청)',
            r'(\w+)(결제|구매|주문)', r'(\w+)(접속|연결|로그인)',
            r'(\w+)(조회|검색|확인)', r'(\w+)(발송|전송|송신)',
            r'(보험|가입|결제|접속|로그인|조회|검색|주문|구매|발송|전송|문자|SMS|OTP|API)(\w*)',
            r'(앱|웹|사이트|페이지|시스템|서비스)(\w*)',
            r'\b(보험|가입|불가|실패|에러|오류|지연|접속|로그인|결제|구매|주문|조회|검색|발송|전송|문자|SMS|OTP|API)\b'
        ]
        
        keywords = set()
        text_normalized = self._normalize_text_for_similarity(text)
        
        for pattern in keyword_patterns:
            matches = re.findall(pattern, text_normalized, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    keywords.update([m for m in match if m and len(m) >= 2])
                elif match and len(match) >= 2:
                    keywords.add(match)
        
        # 명사 추출
        nouns = re.findall(r'[가-힣]{2,}', text)
        keywords.update([self._normalize_text_for_similarity(n) for n in nouns if len(n) >= 2])
        
        return list(keywords)
    
    def get_effect_patterns_from_rag(self):
        """RAG 데이터에서 effect 패턴 목록 가져오기 (캐시 활용)"""
        if not self._effect_cache_loaded:
            self._effect_patterns_cache = self._load_effect_patterns_from_rag()
            self._effect_cache_loaded = True
        return self._effect_patterns_cache or {}
    
    def _expand_query_with_semantic_similarity(self, query):
        """쿼리를 의미적으로 유사한 표현들로 확장"""
        effect_patterns = self.get_effect_patterns_from_rag()
        if not effect_patterns:
            return query
        
        query_keywords = self._extract_semantic_keywords(query)
        query_normalized = self._normalize_text_for_similarity(query)
        
        expanded_query_keywords = set(query_keywords)
        
        # 동의어 확장
        synonym_mappings = [
            (['불가', '실패', '안됨', '에러', '오류'], ['불가', '실패', '안됨', '에러', '오류', '장애']),
            (['발송', '전송', '문자', 'sms'], ['발송', '전송', '송신', '문자', 'sms']),
        ]
        
        for source_keywords, target_keywords in synonym_mappings:
            if any(k in query.lower() for k in source_keywords):
                expanded_query_keywords.update(target_keywords)
        
        # 공통 서비스 확장
        for common_service in self.COMMON_TERM_SERVICES:
            if common_service.lower() in query.lower():
                expanded_query_keywords.update([common_service] + self.COMMON_TERM_SERVICES[common_service])
        
        similar_effects = set()
        semantic_expansions = set()
        
        for keyword in expanded_query_keywords:
            if keyword in effect_patterns:
                for pattern_info in effect_patterns[keyword]:
                    similarity = self._calculate_text_similarity(query_normalized, pattern_info['normalized_effect'])
                    if similarity > 0.2:
                        similar_effects.add(pattern_info['original_effect'])
                        semantic_expansions.update(pattern_info['keywords'])
        
        if similar_effects or semantic_expansions:
            expanded_terms = [f'({query})']
            
            # 동의어 추가
            synonyms = []
            if any(k in query for k in ['불가', '실패']):
                synonyms.extend(['불가', '실패', '안됨', '에러', '오류'])
            if any(k in query for k in ['발송', '전송']):
                synonyms.extend(['발송', '전송', '송신'])
            
            if synonyms:
                synonym_query = query
                for synonym in synonyms:
                    if synonym not in query:
                        for old in ['불가', '실패', '발송', '전송']:
                            synonym_query = synonym_query.replace(old, synonym)
                        expanded_terms.append(f'({synonym_query})')
            
            # 유사 효과 추가
            for effect in list(similar_effects)[:5]:
                expanded_terms.append(f'(effect:"{effect}")')
            
            # 의미적 확장 추가
            if semantic_expansions:
                expanded_terms.append(f'({" OR ".join(list(semantic_expansions)[:10])})')
            
            return ' OR '.join(expanded_terms)
        
        return query
    
    def _calculate_text_similarity(self, text1, text2):
        """두 텍스트 간의 유사도 계산 (Jaccard 유사도 기반)"""
        if not text1 or not text2:
            return 0
        
        bigrams1 = set([text1[i:i+2] for i in range(len(text1)-1)])
        bigrams2 = set([text2[i:i+2] for i in range(len(text2)-1)])
        
        if not bigrams1 or not bigrams2:
            return 0
        
        intersection = len(bigrams1.intersection(bigrams2))
        union = len(bigrams1.union(bigrams2))
        
        return intersection / union if union > 0 else 0
    
    def _boost_semantic_documents(self, documents, query):
        """의미적 유사성이 높은 문서들의 점수 부스팅"""
        query_normalized = self._normalize_text_for_similarity(query)
        query_keywords = set(self._extract_semantic_keywords(query))
        
        for doc in documents:
            effect = doc.get('effect', '')
            symptom = doc.get('symptom', '')
            
            max_similarity = 0
            
            # effect 유사성 계산
            if effect:
                effect_normalized = self._normalize_text_for_similarity(effect)
                effect_similarity = self._calculate_text_similarity(query_normalized, effect_normalized)
                effect_keywords = set(self._extract_semantic_keywords(effect))
                keyword_overlap = len(query_keywords.intersection(effect_keywords))
                effect_similarity += keyword_overlap * 0.1
                max_similarity = max(max_similarity, effect_similarity)
            
            # symptom 유사성 계산
            if symptom:
                symptom_normalized = self._normalize_text_for_similarity(symptom)
                symptom_similarity = self._calculate_text_similarity(query_normalized, symptom_normalized)
                max_similarity = max(max_similarity, symptom_similarity)
            
            # 부스팅 적용
            if max_similarity > 0.3:
                original_score = doc.get('final_score', doc.get('score', 0))
                doc['final_score'] = original_score * (1 + max_similarity * 0.5)
                doc['semantic_similarity'] = max_similarity
                if 'filter_reason' in doc:
                    doc['filter_reason'] += f" + 의미적 유사도 부스팅 ({max_similarity:.2f})"
        
        return documents

    @st.cache_data(ttl=3600)
    def _load_service_names_from_rag(_self):
        """RAG 데이터에서 실제 서비스명 목록을 가져와서 캐시"""
        return _self._safe_execute(lambda: sorted(list({
            r.get("service_name", "").strip() 
            for r in _self.search_client.search(
                search_text="*", top=1000, select=["service_name"], include_total_count=True
            ) if r.get("service_name", "").strip()
        }), key=len, reverse=True), [])
    
    def get_service_names_from_rag(self):
        """RAG 데이터에서 서비스명 목록 가져오기 (캐시 활용)"""
        if not self._cache_loaded:
            self._service_names_cache = self._load_service_names_from_rag()
            self._cache_loaded = True
        return self._service_names_cache or []
    
    def _normalize_service_name(self, service_name):
        """서비스명을 정규화"""
        if not service_name:
            return ""
        normalized = re.sub(r'[^\w\s가-힣]', ' ', service_name)
        return re.sub(r'\s+', ' ', normalized).strip().lower()
    
    def _extract_service_tokens(self, service_name):
        """서비스명에서 의미있는 토큰들을 추출"""
        if not service_name:
            return []
        tokens = re.findall(r'[A-Za-z가-힣0-9]+', service_name)
        return [t.lower() for t in tokens if len(t) >= 2]
    
    def _calculate_service_similarity(self, query_tokens, service_tokens):
        """토큰 기반 서비스명 유사도 계산"""
        if not query_tokens or not service_tokens:
            return 0.0
        
        query_set = set(query_tokens)
        service_set = set(service_tokens)
        
        intersection = len(query_set.intersection(service_set))
        union = len(query_set.union(service_set))
        
        jaccard_score = intersection / union if union > 0 else 0
        inclusion_score = intersection / len(query_set) if len(query_tokens) > 0 else 0
        
        return jaccard_score * 0.3 + inclusion_score * 0.7
    
    def extract_service_name_from_query(self, query):
        """개선된 서비스명 추출 - conf/service_names.txt 우선순위 강화"""
        if not query:
            return None
            
        print(f"DEBUG: [SERVICE_EXTRACTION] Starting enhanced service name extraction")
        print(f"DEBUG: [SERVICE_EXTRACTION] Input query: '{query}'")
        
        # 원인유형 쿼리인지 먼저 확인
        is_cause_type_query = self._is_cause_type_query(query)
        if is_cause_type_query:
            print(f"DEBUG: [SERVICE_EXTRACTION] Cause type query detected - limiting service extraction")
            return self._extract_service_name_for_cause_type_query(query)
        
        # 1단계: 일반 용어 서비스 우선 체크 (변경 없음)
        is_common, common_service = self.is_common_term_service(query)
        if is_common:
            print(f"DEBUG: [SERVICE_EXTRACTION] Common term service found: '{common_service}'")
            return common_service
        
        # ⭐ 2단계: conf/service_names.txt 파일에서 최우선 검색 (강화)
        print(f"DEBUG: [SERVICE_EXTRACTION] Checking conf/service_names.txt file first...")
        file_service_name = self._find_service_name_in_file(query)
        if file_service_name:
            print(f"DEBUG: [SERVICE_EXTRACTION] ✅ Service found in FILE: '{file_service_name}'")
            return file_service_name
        
        # 3단계: 통계 쿼리에 특화된 서비스명 추출 (파일에서 찾지 못한 경우만)
        print(f"DEBUG: [SERVICE_EXTRACTION] File search failed, trying statistics pattern...")
        stats_service_name = self._extract_service_name_for_statistics(query)
        if stats_service_name:
            # 통계에서 추출된 서비스명도 파일에 있는지 다시 확인
            file_service_names = self.get_service_names_from_file()
            if file_service_names and stats_service_name in file_service_names:
                print(f"DEBUG: [SERVICE_EXTRACTION] Statistics service found in file: '{stats_service_name}'")
                return stats_service_name
            elif not file_service_names:  # 파일이 없는 경우만 통계 결과 사용
                print(f"DEBUG: [SERVICE_EXTRACTION] Statistics service found (no file available): '{stats_service_name}'")
                return stats_service_name
        
        # ⭐ 4단계: Azure AI Search 데이터 기반 검색 (최종 fallback)
        print(f"DEBUG: [SERVICE_EXTRACTION] Fallback to Azure AI Search data...")
        
        normalized_query = self._normalize_statistics_query(query)
        rag_service_names = self.get_service_names_from_rag()
        
        if not rag_service_names:
            print(f"DEBUG: [SERVICE_EXTRACTION] No RAG service names available, using legacy extraction")
            return self._extract_service_name_legacy(normalized_query)
        
        query_lower = normalized_query.lower()
        query_tokens = self._extract_service_tokens(normalized_query)
        
        if not query_tokens:
            print(f"DEBUG: [SERVICE_EXTRACTION] No valid tokens extracted from query")
            return None
        
        candidates = []
        for service_name in rag_service_names:
            service_tokens = self._extract_service_tokens(service_name)
            if not service_tokens:
                continue
            
            # 정확한 매칭
            if service_name.lower() in query_lower:
                candidates.append((service_name, 1.0, 'rag_exact_match'))
                continue
            
            # 정규화된 매칭
            normalized_query_clean = self._normalize_service_name(normalized_query)
            normalized_service = self._normalize_service_name(service_name)
            
            if (normalized_service in normalized_query_clean or 
                normalized_query_clean in normalized_service):
                candidates.append((service_name, 0.9, 'rag_normalized_inclusion'))
                continue
            
            # 토큰 유사도 매칭 (더 엄격한 기준)
            similarity = self._calculate_service_similarity(query_tokens, service_tokens)
            if similarity >= 0.5:  # 기존 0.4에서 0.5로 상향 조정
                candidates.append((service_name, similarity, 'rag_token_similarity'))
        
        if not candidates:
            print(f"DEBUG: [SERVICE_EXTRACTION] No candidates found in RAG data")
            return None
        
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_match = candidates[0]
        print(f"DEBUG: [SERVICE_EXTRACTION] ⚠️  Best RAG match: '{best_match[0]}' (Score: {best_match[1]:.2f})")
        print(f"DEBUG: [SERVICE_EXTRACTION] Note: This service was NOT found in conf/service_names.txt")
        return best_match[0]

    def _is_cause_type_query(self, query):
        """원인유형 쿼리인지 엄격하게 판별 - 통계/분류 관련 쿼리만"""
        if not query:
            return False
        
        query_lower = query.lower()
        
        # 1단계: 원인유형/분류를 명시적으로 묻는 키워드
        explicit_cause_type_keywords = [
            '원인유형', '원인별', '원인유형별', '원인타입', 'cause_type',
            '원인분석', '원인현황', '원인통계', '원인분포',
            '원인분류', '원인종류', '원인카테고리'
        ]
        
        for keyword in explicit_cause_type_keywords:
            if keyword in query_lower:
                return True
        
        # 2단계: "원인" + "통계/분류" 조합 체크
        has_cause = any(word in query_lower for word in ['원인', 'cause'])
        has_stats_or_category = any(word in query_lower for word in 
            ['통계', '분류', '유형', '타입', '별', '현황', '분포', '분석', '카테고리', '종류'])
        
        if has_cause and has_stats_or_category:
            # 하지만 "원인이 뭐야", "원인 알려줘" 같은 일반 질문은 제외
            exclude_patterns = [
                r'원인[이가]?\s*(뭐|무엇|어떻게|왜)',
                r'원인.*?(알려|설명|말해|보여)',
                r'(뭐|무엇|어떤|어떻게).*?원인'
            ]
            
            for pattern in exclude_patterns:
                if re.search(pattern, query_lower):
                    return False
            
            return True
        
        return False

    def _extract_service_name_for_cause_type_query(self, query):
        """원인유형 쿼리에서 서비스명 추출 (매우 제한적)"""
        if not query:
            return None
        
        # 원인유형 쿼리에서는 명시적으로 따옴표나 괄호로 감싸진 서비스명만 추출
        service_patterns = [
            r'["\']([A-Za-z가-힣][A-Za-z0-9가-힣\s]{2,20})["\']',
            r'\(([A-Za-z가-힣][A-Za-z0-9가-힣\s]{2,20})\)',
            r'\b([A-Z]{3,10})\s+(?:서비스|시스템).*?원인유형',
            r'원인유형.*?\b([A-Z]{3,10})\s+(?:서비스|시스템)'
        ]
        
        # 제외할 원인유형 관련 키워드들
        exclude_keywords = [
            '원인', '원인유형', '원인별', '유형', '타입', 'type', '원인유형별',
            '원인타입별', '문제원인', '장애원인', '발생원인', '근본원인',
            '원인분석', '원인현황', '원인통계', '원인분포', '원인분류'
        ]
        
        for pattern in service_patterns:
            try:
                matches = re.findall(pattern, query, re.IGNORECASE)
                if matches:
                    for match in matches:
                        service_name = match.strip() if isinstance(match, str) else match[0].strip()
                        
                        if (len(service_name) >= 2 and 
                            service_name.lower() not in [k.lower() for k in exclude_keywords] and
                            not service_name.isdigit()):
                            
                            print(f"DEBUG: [CAUSE_TYPE_QUERY] Service name found: '{service_name}'")
                            return service_name
                            
            except Exception as e:
                continue
        
        print(f"DEBUG: [CAUSE_TYPE_QUERY] No service name found in cause type query")
        return None

    def _extract_service_name_for_statistics(self, query):
        """통계 쿼리에 특화된 서비스명 추출"""
        if not query:
            return None
        
        # 통계 쿼리에 특화된 패턴들
        stats_service_patterns = [
            # "상체인증플랫폼 년도별 장애건수" 형태
            r'^([가-힣]{4,20}(?:플랫폼|시스템|서비스|포털|앱|APP|관리|센터))\s+(?:년도별|연도별|월별|장애|건수|통계|현황)',
            
            # "네트워크보안범위관리 서비스 통계" 형태  
            r'^([가-힣]{4,30})\s+(?:서비스|시스템)?\s*(?:년도별|연도별|월별|장애|건수|통계|현황)',
            
            # "ERP 년도별" 형태
            r'^([A-Z가-힣][A-Za-z0-9가-힣\-_]{1,20})\s+(?:년도별|연도별|월별|장애|건수|통계|현황)',
            
            # 중간에 있는 서비스명 "알려줘 상체인증플랫폼 통계"
            r'(?:알려|보여|확인).*?([가-힣]{4,20}(?:플랫폼|시스템|서비스|포털|앱|관리|센터)).*?(?:년도별|연도별|월별|장애|건수|통계|현황)',
            
            # 따옴표나 특수문자로 감싸진 서비스명
            r'["\']([A-Za-z가-힣][A-Za-z0-9가-힣\s\-_]{2,30})["\'].*?(?:년도별|연도별|월별|장애|건수|통계|현황)',
            
            # 서비스명이 쿼리의 핵심인 경우
            r'\b([A-Za-z가-힣][A-Za-z0-9가-힣\s\-_]{3,20})\b.*?(?:년도별|연도별|월별|장애|건수|통계|현황|몇건|개수)',
        ]
        
        for pattern in stats_service_patterns:
            try:
                matches = re.findall(pattern, query, re.IGNORECASE)
                if matches:
                    for match in matches:
                        service_name = match[0].strip() if isinstance(match, tuple) else match.strip()
                        
                        # 제외할 통계 관련 키워드들
                        exclude_stats_keywords = [
                            '년도별', '연도별', '월별', '요일별', '시간대별', '부서별', '등급별',
                            '장애', '건수', '통계', '현황', '몇', '개수', '발생', '알려', '보여',
                            '확인', '체크', '분석', '조회', '검색', '정보', '데이터', 'SELECT',
                            'FROM', 'WHERE', 'AND', 'OR', '년', '월', '일'
                        ]
                        
                        if (len(service_name) >= 3 and 
                            service_name not in exclude_stats_keywords and
                            not service_name.isdigit() and
                            not re.match(r'^[0-9]+$', service_name)):
                            
                            return service_name
            except Exception as e:
                continue
        
        return None

    def diagnose_service_name_matching(self, query):
        """서비스명 매칭 진단 도구 (디버깅용)"""
        print(f"\n=== [DIAGNOSIS] SERVICE NAME MATCHING DIAGNOSIS ===")
        print(f"[DIAGNOSIS] Query: '{query}'")
        
        # 1. 파일 기반 서비스명 확인
        file_services = self.get_service_names_from_file()
        print(f"\n[DIAGNOSIS] 1. File-based services ({len(file_services)}):")
        if file_services:
            for i, service in enumerate(file_services[:10]):
                print(f"   {i+1}. {service}")
            if len(file_services) > 10:
                print(f"   ... and {len(file_services) - 10} more")
        else:
            print(f"   No services loaded from conf/service_names.txt")
        
        # 2. RAG 기반 서비스명 확인  
        rag_services = self.get_service_names_from_rag()
        print(f"\n[DIAGNOSIS] 2. RAG-based services ({len(rag_services)}):")
        for i, service in enumerate(rag_services[:10]):
            print(f"   {i+1}. {service}")
        if len(rag_services) > 10:
            print(f"   ... and {len(rag_services) - 10} more")
        
        # 3. 매칭 결과
        final_result = self.extract_service_name_from_query(query)
        print(f"\n[DIAGNOSIS] 3. Final matching result: {final_result}")
        
        # 4. 결과 요약
        print(f"\n[DIAGNOSIS] 4. Summary:")
        print(f"   File services available: {len(file_services) > 0}")
        print(f"   RAG services available: {len(rag_services) > 0}")
        print(f"   Final result: {'SUCCESS' if final_result else 'NO MATCH'}")
        
        if final_result:
            is_in_file = final_result in file_services
            is_in_rag = final_result in rag_services
            print(f"   Source: {'FILE' if is_in_file else 'RAG' if is_in_rag else 'COMMON_TERM'}")
        
        print(f"=== [DIAGNOSIS] END DIAGNOSIS ===\n")
        return {
            'file_services_count': len(file_services),
            'rag_services_count': len(rag_services),
            'final_result': final_result,
            'file_available': len(file_services) > 0,
            'rag_available': len(rag_services) > 0
        }

    def calculate_hybrid_score(self, search_score, reranker_score):
        """검색 점수와 Reranker 점수를 조합하여 하이브리드 점수 계산"""
        search_score = search_score or 0.0
        reranker_score = reranker_score or 0.0
        
        if reranker_score > 0:
            normalized_reranker = min(reranker_score / 4.0, 1.0)
            normalized_search = min(search_score, 1.0)
            return normalized_reranker * 0.8 + normalized_search * 0.2
        
        return min(search_score, 1.0)

    def _extract_year_month_from_query_unified(self, query):
        """통합된 연도와 월 조건 추출"""
        time_info = {'year': None, 'months': []}
        if not query:
            return time_info
        
        # 연도 추출
        year_patterns = [r'\b(\d{4})년\b', r'\b(\d{4})\s*년도\b', r'\b(\d{4})년도\b']
        for pattern in year_patterns:
            if matches := re.findall(pattern, query, re.IGNORECASE):
                time_info['year'] = matches[-1]
                break
        
        # 모든 월 관련 패턴을 통합
        months_set = set()
        
        # 월 범위 패턴
        range_patterns = [r'\b(\d+)\s*~\s*(\d+)월\b', r'\b(\d+)월\s*~\s*(\d+)월\b', 
                         r'\b(\d+)\s*-\s*(\d+)월\b', r'\b(\d+)월\s*-\s*(\d+)월\b']
        for pattern in range_patterns:
            if matches := re.findall(pattern, query, re.IGNORECASE):
                for match in matches:
                    start_month, end_month = int(match[0]), int(match[1])
                    if 1 <= start_month <= 12 and 1 <= end_month <= 12 and start_month <= end_month:
                        months_set.update(range(start_month, end_month + 1))
        
        # 개별 월 및 콤마로 구분된 월
        if comma_matches := re.findall(r'(\d{1,2})월', query):
            for match in comma_matches:
                month_num = int(match)
                if 1 <= month_num <= 12:
                    months_set.add(month_num)
        
        time_info['months'] = sorted(list(months_set))
        
        return time_info

    def search_documents_with_service_filter(self, query, target_service_name=None, query_type="default", top_k=15):
        """서비스명 필터링을 지원하는 일반 검색 (fallback용)"""
        try:
            # 기본 검색 로직
            grade_info = self.extract_incident_grade_from_query(query)
            time_info = self._extract_year_month_from_query_unified(query)
            
            enhanced_query = (self.build_grade_search_query(query, grade_info) 
                            if grade_info['has_grade_query'] else query)
            
            # 시간 조건 추가
            enhanced_query = self._add_time_conditions(enhanced_query, time_info)
            
            # 서비스명 조건 추가  
            if target_service_name:
                enhanced_query = self._add_service_conditions(enhanced_query, target_service_name)
            
            results = self.search_client.search(
                search_text=enhanced_query, top=top_k, include_total_count=True,
                select=["incident_id", "service_name", "error_time", "effect", "symptom", "repair_notice",
                       "error_date", "week", "daynight", "root_cause", "incident_repair", "incident_plan",
                       "cause_type", "done_type", "incident_grade", "owner_depart", "year", "month"]
            )
            
            documents = [self._convert_search_result_to_document(result) for result in results]
            
            # 통합 필터링 시스템 적용
            query_type_enum = self._convert_to_query_type_enum(query_type)
            filtered_docs, _ = self.filter_manager.apply_comprehensive_filtering(
                documents, query, query_type_enum, enable_llm_validation=False
            )
            
            return filtered_docs
        except:
            return []

    def search_documents_fallback(self, query, target_service_name=None, top_k=25):
        """매우 관대한 기준의 대체 검색"""
        try:
            grade_info = self.extract_incident_grade_from_query(query)
            
            search_query = (f'service_name:*{target_service_name}*' if target_service_name 
                          else query)
            
            if grade_info['has_grade_query'] and grade_info['specific_grade']:
                search_query += f' AND incident_grade:"{grade_info["specific_grade"]}"'
            
            results = self.search_client.search(
                search_text=search_query, top=top_k, include_total_count=True,
                select=["incident_id", "service_name", "error_time", "effect", "symptom", "repair_notice",
                       "error_date", "week", "daynight", "root_cause", "incident_repair", "incident_plan",
                       "cause_type", "done_type", "incident_grade", "owner_depart", "year", "month"]
            )
            
            documents = []
            for result in results:
                score = result.get("@search.score") or 0.0
                if score >= 0.05:  # 매우 낮은 임계값
                    doc = self._convert_search_result_to_document(result)
                    doc.update({
                        "final_score": score,
                        "quality_tier": "Basic",
                        "filter_reason": f"대체 검색 (관대한 기준, 점수: {score:.2f})",
                        "service_match_type": "fallback"
                    })
                    
                    if grade_info['has_grade_query']:
                        doc_grade = result.get("incident_grade", "")
                        if grade_info['specific_grade'] and doc_grade == grade_info['specific_grade']:
                            doc['grade_match_type'] = 'exact'
                            doc['filter_reason'] += f" (등급: {doc_grade})"
                        elif doc_grade:
                            doc['grade_match_type'] = 'general'
                            doc['filter_reason'] += f" (등급: {doc_grade})"
                    
                    documents.append(doc)
            
            documents.sort(key=lambda x: x.get('final_score', 0) or 0, reverse=True)
            return documents[:15]
        except:
            return []

    def _extract_service_name_legacy(self, query):
        """기존 패턴 기반 서비스명 추출 (fallback)"""
        service_patterns = [
            r'([A-Za-z가-힣][A-Za-z0-9가-힣_\-/\+\(\)\s]*[A-Za-z0-9가-힣_\-/\+\)])\s+(?:연도별|월별|건수|장애|현상|복구|서비스|통계|발생|발생일자|언제)',
            r'서비스.*?([A-Za-z가-힣][A-Za-z0-9가-힣_\-/\+\(\)\s]*[A-Za-z0-9가-힣_\-/\+\)])',
            r'^([A-Za-z가-힣][A-Za-z0-9가-힣_\-/\+\(\)\s]*[A-Za-z0-9가-힣_\-/\+\)])\s+(?!으로|에서|에게|에|을|를|이|가)',
            r'["\']([A-Za-z가-힣][A-Za-z0-9가-힣_\-/\+\(\)\s]*[A-Za-z0-9가-힣_\-/\+\)])["\']',
            r'\(([A-Za-z가-힣][A-Za-z0-9가-힣_\-/\+\s]*[A-Za-z0-9가-힣_\-/\+])\)',
            r'\b([A-Za-z가-힣][A-Za-z0-9가-힣_\-/\+\(\)]{2,}(?:\s+[A-Za-z0-9가-힣_\-/\+\(\)]+)*)\b'
        ]
        
        for pattern in service_patterns:
            if matches := re.findall(pattern, query, re.IGNORECASE):
                for match in matches:
                    if (service_name := match.strip()) and len(service_name) >= 2:
                        return service_name
        return None

    def _normalize_statistics_query(self, query):
        """통계 쿼리의 동의어들을 정규화"""
        if not query:
            return query
        
        normalized = query
        for old_term, new_term in self.statistics_synonyms.items():
            normalized = normalized.replace(old_term, new_term)
        
        # 연속된 공백 정리
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized

    def test_service_name_matching(self):
        """서비스명 매칭 테스트"""
        test_queries = [
            "네트워크보안범위관리 서비스에서 발생한 실명인증 장애 복구방법",
            "ERP 로그인 불가 문제",
            "블록체인 지역화폐 접속 장애",
            "OTP 인증 실패",
            "API 연동 오류"
        ]
        
        print("=== SERVICE NAME MATCHING TEST ===")
        for query in test_queries:
            result = self.extract_service_name_from_query(query)
            print(f"Query: {query}")
            print(f"Result: {result}")
            print("-" * 50)

    # 기존 코드와의 호환성을 위한 wrapper 메서드들 - filter_manager로 위임
    def filter_documents_by_time_conditions(self, documents, time_conditions):
        """시간 조건 기반 필터링 (호환성 wrapper)"""
        return self.filter_manager.filter_documents_by_time_conditions(documents, time_conditions)
    
    def filter_documents_by_department_conditions(self, documents, department_conditions):
        """부서 조건 기반 필터링 (호환성 wrapper)"""
        return self.filter_manager.filter_documents_by_department_conditions(documents, department_conditions)
    
    def filter_documents_by_grade(self, documents, grade_info):
        """장애 등급 기반 문서 필터링 (호환성 wrapper)"""
        if not grade_info['has_grade_query']:
            return documents
        
        conditions = FilterConditions()
        conditions.has_grade_query = grade_info['has_grade_query']
        conditions.specific_grade = grade_info.get('specific_grade')
        conditions.grade = grade_info.get('specific_grade')
        
        filtered_docs = []
        for doc in documents:
            is_valid, _ = self.filter_manager.validator.validate_document_conditions(doc, conditions)
            if is_valid:
                doc['grade_match_type'] = 'exact' if conditions.specific_grade else 'general'
                filtered_docs.append(doc)
        
        # 등급 순서로 정렬
        grade_order = {'1등급': 1, '2등급': 2, '3등급': 3, '4등급': 4}
        filtered_docs.sort(key=lambda d: next((v for k, v in grade_order.items() 
                                             if k in d.get('incident_grade', '')), 999))
        return filtered_docs