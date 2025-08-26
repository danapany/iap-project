import streamlit as st
import re
from config.settings_local import AppConfigLocal

class SearchManagerLocal:
    """검색 관련 기능 관리 클래스 - effect 필드 기반 의미적 유사성 검색 최적화"""
    
    def __init__(self, search_client, config=None):
        self.search_client = search_client
        self.config = config if config else AppConfigLocal()
        self._service_names_cache = None
        self._cache_loaded = False
        # effect 패턴 캐시
        self._effect_patterns_cache = None
        self._effect_cache_loaded = False
    
    @st.cache_data(ttl=3600)
    def _load_effect_patterns_from_rag(_self):
        """RAG 데이터에서 effect 필드의 패턴들을 분석하여 캐시"""
        try:
            results = _self.search_client.search(
                search_text="*",
                top=1000,
                select=["effect", "symptom", "service_name"],
                include_total_count=True
            )
            
            effect_patterns = {}
            
            for result in results:
                effect = result.get("effect", "").strip()
                symptom = result.get("symptom", "").strip()
                service_name = result.get("service_name", "").strip()
                
                if effect:
                    # effect를 정규화하여 키워드 그룹 생성
                    normalized_effect = _self._normalize_text_for_similarity(effect)
                    keywords = _self._extract_semantic_keywords(effect)
                    
                    if keywords:
                        for keyword in keywords:
                            if keyword not in effect_patterns:
                                effect_patterns[keyword] = []
                            effect_patterns[keyword].append({
                                'original_effect': effect,
                                'normalized_effect': normalized_effect,
                                'symptom': symptom,
                                'service_name': service_name,
                                'keywords': keywords
                            })
            
            return effect_patterns
            
        except Exception as e:
            return {}
    
    def _normalize_text_for_similarity(self, text):
        """텍스트를 의미적 유사성 비교를 위해 정규화"""
        if not text:
            return ""
        
        # 도어쓰기 제거
        normalized = re.sub(r'\s+', '', text.lower())
        
        # 의미가 같은 표현들을 통일
        replacements = {
            # 불가/실패 관련
            '불가능': '불가',
            '실패': '불가',
            '안됨': '불가',
            '되지않음': '불가',
            '할수없음': '불가',
            
            # 접속/연결 관련
            '접속': '연결',
            '로그인': '접속',
            '액세스': '접속',
            
            # 오류/에러 관련
            '오류': '에러',
            '장애': '에러',
            '문제': '에러',
            '이슈': '에러',
            
            # 지연/느림 관련
            '지연': '느림',
            '늦음': '느림',
            '응답없음': '느림',
            
            # 서비스/기능 관련
            '서비스': '기능',
            '시스템': '서비스',
            '플랫폼': '서비스',
            
            # 가입/등록 관련
            '가입': '등록',
            '신청': '등록',
            '회원가입': '등록',
            
            # 결제/구매 관련
            '결제': '구매',
            '구매': '결제',
            '주문': '결제',
            '거래': '결제'
        }
        
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        
        return normalized
    
    def _extract_semantic_keywords(self, text):
        """텍스트에서 의미적 키워드 추출"""
        if not text:
            return []
        
        # 핵심 키워드 패턴들
        keyword_patterns = [
            # 동작 + 대상 패턴
            r'(\w+)(불가|실패|에러|오류|지연|느림)',
            r'(\w+)(가입|등록|신청)',
            r'(\w+)(결제|구매|주문)',
            r'(\w+)(접속|연결|로그인)',
            r'(\w+)(조회|검색|확인)',
            
            # 대상 + 상태 패턴
            r'(보험|가입|결제|접속|로그인|조회|검색|주문|구매)(\w*)',
            
            # 서비스명 관련
            r'(앱|웹|사이트|페이지|시스템|서비스)(\w*)',
            
            # 단독 중요 키워드
            r'\b(보험|가입|불가|실패|에러|오류|지연|접속|로그인|결제|구매|주문|조회|검색)\b'
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
        
        # 추가로 2글자 이상의 명사들 추출
        noun_pattern = r'[가-힣]{2,}'
        nouns = re.findall(noun_pattern, text)
        keywords.update([self._normalize_text_for_similarity(noun) for noun in nouns if len(noun) >= 2])
        
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
        
        # 쿼리에서 키워드 추출
        query_keywords = self._extract_semantic_keywords(query)
        query_normalized = self._normalize_text_for_similarity(query)
        
        # 유사한 effect 패턴 찾기
        similar_effects = set()
        semantic_expansions = set()
        
        for keyword in query_keywords:
            if keyword in effect_patterns:
                for pattern_info in effect_patterns[keyword]:
                    # 정규화된 텍스트로 유사도 계산
                    similarity = self._calculate_text_similarity(
                        query_normalized, 
                        pattern_info['normalized_effect']
                    )
                    
                    if similarity > 0.3:  # 30% 이상 유사하면 포함
                        similar_effects.add(pattern_info['original_effect'])
                        # 해당 패턴의 다른 키워드들도 추가
                        semantic_expansions.update(pattern_info['keywords'])
        
        # 쿼리 확장
        if similar_effects or semantic_expansions:
            expanded_terms = []
            
            # 원본 쿼리
            expanded_terms.append(f'({query})')
            
            # 유사한 effect들
            for effect in list(similar_effects)[:5]:  # 최대 5개까지
                expanded_terms.append(f'(effect:"{effect}")')
            
            # 의미적으로 확장된 키워드들
            if semantic_expansions:
                semantic_query_parts = []
                for expansion in list(semantic_expansions)[:10]:  # 최대 10개까지
                    semantic_query_parts.append(expansion)
                if semantic_query_parts:
                    expanded_terms.append(f'({" OR ".join(semantic_query_parts)})')
            
            expanded_query = ' OR '.join(expanded_terms)
            return expanded_query
        
        return query
    
    def _calculate_text_similarity(self, text1, text2):
        """두 텍스트 간의 유사도 계산 (Jaccard 유사도 기반)"""
        if not text1 or not text2:
            return 0
        
        # 2-gram 기반 유사도 (더 정확한 유사도 측정)
        def get_bigrams(text):
            return set([text[i:i+2] for i in range(len(text)-1)])
        
        bigrams1 = get_bigrams(text1)
        bigrams2 = get_bigrams(text2)
        
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
            
            # effect와 symptom 모두에서 유사도 계산
            effect_similarity = 0
            symptom_similarity = 0
            
            if effect:
                effect_normalized = self._normalize_text_for_similarity(effect)
                effect_similarity = self._calculate_text_similarity(query_normalized, effect_normalized)
                
                # 키워드 매칭 보너스
                effect_keywords = set(self._extract_semantic_keywords(effect))
                keyword_overlap = len(query_keywords.intersection(effect_keywords))
                if keyword_overlap > 0:
                    effect_similarity += (keyword_overlap * 0.1)  # 키워드 매칭당 10% 보너스
            
            if symptom:
                symptom_normalized = self._normalize_text_for_similarity(symptom)
                symptom_similarity = self._calculate_text_similarity(query_normalized, symptom_normalized)
            
            # 최고 유사도를 기준으로 점수 부스팅
            max_similarity = max(effect_similarity, symptom_similarity)
            
            if max_similarity > 0.3:  # 30% 이상 유사하면 부스팅
                original_score = doc.get('final_score', doc.get('score', 0))
                boost_factor = 1 + (max_similarity * 0.5)  # 최대 50% 부스팅
                doc['final_score'] = original_score * boost_factor
                doc['semantic_similarity'] = max_similarity
                
                # 부스팅 이유 표시
                if 'filter_reason' in doc:
                    doc['filter_reason'] += f" + 의미적 유사도 부스팅 ({max_similarity:.2f})"
        
        return documents

    @st.cache_data(ttl=3600)
    def _load_service_names_from_rag(_self):
        """RAG 데이터에서 실제 서비스명 목록을 가져와서 캐시"""
        try:
            results = _self.search_client.search(
                search_text="*",
                top=1000,
                select=["service_name"],
                include_total_count=True
            )
            
            service_names = set()
            for result in results:
                service_name = result.get("service_name", "").strip()
                if service_name:
                    service_names.add(service_name)
            
            sorted_service_names = sorted(list(service_names), key=len, reverse=True)
            return sorted_service_names
            
        except Exception as e:
            st.warning(f"RAG 데이터에서 서비스명 로드 실패: {str(e)}")
            return []
    
    def get_service_names_from_rag(self):
        """RAG 데이터에서 서비스명 목록 가져오기 (캐시 활용)"""
        if not self._cache_loaded:
            self._service_names_cache = self._load_service_names_from_rag()
            self._cache_loaded = True
        return self._service_names_cache or []
    
    def extract_service_name_from_query(self, query):
        """RAG 데이터 기반 서비스명 추출 (조용한 처리)"""
        rag_service_names = self.get_service_names_from_rag()
        
        if not rag_service_names:
            return self._extract_service_name_legacy(query)
        
        query_lower = query.lower()
        
        # 1단계: 완전 일치 검색
        for service_name in rag_service_names:
            if service_name.lower() in query_lower:
                return service_name
        
        # 2단계: 부분 일치 검색
        query_no_space = re.sub(r'\s+', '', query_lower)
        for service_name in rag_service_names:
            service_name_no_space = re.sub(r'\s+', '', service_name.lower())
            if service_name_no_space in query_no_space or query_no_space in service_name_no_space:
                return service_name
        
        # 3단계: 단어별 매칭
        query_words = re.findall(r'[A-Za-z가-힣]+', query)
        if query_words:
            for service_name in rag_service_names:
                service_words = re.findall(r'[A-Za-z가-힣]+', service_name)
                for query_word in query_words:
                    if len(query_word) >= 2:
                        for service_word in service_words:
                            if query_word.lower() == service_word.lower():
                                return service_name
        
        return None

    def calculate_hybrid_score(self, search_score, reranker_score):
        """검색 점수와 Reranker 점수를 조합하여 하이브리드 점수 계산"""
        if reranker_score > 0:
            normalized_reranker = min(reranker_score / 4.0, 1.0)
            normalized_search = min(search_score, 1.0)
            hybrid_score = (normalized_reranker * 0.8) + (normalized_search * 0.2)
        else:
            hybrid_score = min(search_score, 1.0)
        
        return hybrid_score

    def advanced_filter_documents_v3(self, documents, query_type="default", query_text="", target_service_name=None):
        """서비스명 포함 매칭을 지원하는 개선된 필터링 (의미적 유사성 최적화)"""
        
        # 동적 임계값 획득
        thresholds = self.config.get_dynamic_thresholds(query_type, query_text)
        
        # 의미적 유사성이 높은 문서들에 점수 부스팅 적용
        documents = self._boost_semantic_documents(documents, query_text)
        
        filtered_docs = []
        filter_stats = {
            'total': len(documents),
            'search_filtered': 0,
            'service_exact_match': 0,
            'service_partial_match': 0,
            'service_filtered': 0,
            'reranker_qualified': 0,
            'hybrid_qualified': 0,
            'semantic_boosted': 0,
            'final_selected': 0
        }
        
        for doc in documents:
            search_score = doc.get('score', 0)
            reranker_score = doc.get('reranker_score', 0)
            
            # 의미적 유사성 부스팅이 적용된 경우 통계에 반영
            if 'semantic_similarity' in doc:
                filter_stats['semantic_boosted'] += 1
            
            # 1단계: 기본 검색 점수 필터링
            if search_score < thresholds['search_threshold']:
                continue
            filter_stats['search_filtered'] += 1
            
            # 2단계: 서비스명 매칭
            if target_service_name:
                doc_service_name = doc.get('service_name', '').strip()
                
                if doc_service_name.lower() == target_service_name.lower():
                    filter_stats['service_exact_match'] += 1
                    doc['service_match_type'] = 'exact'
                elif target_service_name.lower() in doc_service_name.lower() or doc_service_name.lower() in target_service_name.lower():
                    filter_stats['service_partial_match'] += 1
                    doc['service_match_type'] = 'partial'
                else:
                    continue
            else:
                doc['service_match_type'] = 'all'
                
            filter_stats['service_filtered'] += 1
            
            # 3단계: Reranker 점수 우선 평가
            if reranker_score >= thresholds['reranker_threshold']:
                filter_stats['reranker_qualified'] += 1
                match_type = doc.get('service_match_type', 'unknown')
                doc['filter_reason'] = f"RAG 기반 서비스명 {match_type} 매칭 + Reranker 고품질 (점수: {reranker_score:.2f})"
                doc['final_score'] = reranker_score
                doc['quality_tier'] = 'Premium'
                filtered_docs.append(doc)
                filter_stats['final_selected'] += 1
                continue
            
            # 4단계: 하이브리드 점수 평가 (의미적 유사성 부스팅 반영)
            hybrid_score = self.calculate_hybrid_score(search_score, reranker_score)
            final_score = doc.get('final_score', hybrid_score)  # 부스팅된 점수 사용
            
            if final_score >= thresholds['hybrid_threshold']:
                filter_stats['hybrid_qualified'] += 1
                match_type = doc.get('service_match_type', 'unknown')
                doc['filter_reason'] = f"RAG 기반 서비스명 {match_type} 매칭 + 하이브리드 점수 통과 (점수: {final_score:.2f})"
                doc['quality_tier'] = 'Standard'
                filtered_docs.append(doc)
                filter_stats['final_selected'] += 1
        
        # 의미적 유사도와 점수를 모두 고려한 정렬
        def sort_key(doc):
            match_priority = {'exact': 3, 'partial': 2, 'all': 1}
            semantic_boost = doc.get('semantic_similarity', 0) * 0.1  # 의미적 유사도 보너스
            return (
                match_priority.get(doc.get('service_match_type', 'all'), 0), 
                doc.get('final_score', 0) + semantic_boost
            )
        
        filtered_docs.sort(key=sort_key, reverse=True)
        
        # 최종 결과 수 제한
        final_docs = filtered_docs[:thresholds['max_results']]
       
        # 개선된 통계 표시
        st.info(f"""
        📊 **의미적 유사성 기반 문서 필터링 결과**
        - 🔍 전체 검색 결과: {filter_stats['total']}개
        - ✅ 기본 점수 통과: {filter_stats['search_filtered']}개
        - ✅ 총 서비스명 매칭: {filter_stats['service_filtered']}개
        - 🏆 Reranker 고품질: {filter_stats['reranker_qualified']}개
        - 🎯 하이브리드 통과: {filter_stats['hybrid_qualified']}개
        - 🧠 의미적 유사성 부스팅: {filter_stats['semantic_boosted']}개
        - 📋 최종 선별: {len(final_docs)}개
        """)
        
        return final_docs

    def semantic_search_with_service_filter(self, query, target_service_name=None, query_type="default", top_k=20):
        """서비스명 포함 검색을 지원하는 개선된 시맨틱 검색 - 의미적 유사성 최적화"""
        try:
            # 의미적 유사성 기반 쿼리 확장
            expanded_query = self._expand_query_with_semantic_similarity(query)
            
            # 확장된 쿼리가 원본과 다르면 더 많은 결과 요청
            if expanded_query != query:
                top_k = max(top_k, 30)
                st.info(f"📄 1단계: {top_k}개 초기 검색 결과 수집 중... (의미적 유사성 확장 적용)")
            else:
                st.info(f"📄 1단계: {top_k}개 초기 검색 결과 수집 중... (기본 검색)")
            
            # RAG 기반 서비스명 포함 검색을 위한 검색 쿼리 구성
            if target_service_name:
                enhanced_query = f'(service_name:"{target_service_name}" OR service_name:*{target_service_name}*)'
                if expanded_query != target_service_name:
                    enhanced_query += f" AND ({expanded_query})"
            else:
                enhanced_query = expanded_query
            
            # 시맨틱 검색 실행
            results = self.search_client.search(
                search_text=enhanced_query,
                top=top_k,
                query_type="semantic",
                semantic_configuration_name="iap-incident-rebuild-meaning",
                include_total_count=True,
                select=[
                    "incident_id", "service_name", "error_time", "effect", "symptom", "repair_notice", 
                    "error_date", "week", "daynight", "root_cause", "incident_repair", 
                    "incident_plan", "cause_type", "done_type", "incident_grade", 
                    "owner_depart", "year", "month"
                ]
            )
            
            documents = []
            for result in results:
                documents.append({
                    "incident_id": result.get("incident_id", ""),
                    "service_name": result.get("service_name", ""),
                    "error_time": result.get("error_time", 0),
                    "effect": result.get("effect", ""),
                    "symptom": result.get("symptom", ""),
                    "repair_notice": result.get("repair_notice", ""),
                    "error_date": result.get("error_date", ""),
                    "week": result.get("week", ""),
                    "daynight": result.get("daynight", ""),
                    "root_cause": result.get("root_cause", ""),
                    "incident_repair": result.get("incident_repair", ""),
                    "incident_plan": result.get("incident_plan", ""),
                    "cause_type": result.get("cause_type", ""),
                    "done_type": result.get("done_type", ""),
                    "incident_grade": result.get("incident_grade", ""),
                    "owner_depart": result.get("owner_depart", ""),
                    "year": result.get("year", ""),
                    "month": result.get("month", ""),
                    "score": result.get("@search.score", 0),
                    "reranker_score": result.get("@search.reranker_score", 0)
                })
            
            st.info(f"🎯 2단계: 의미적 유사성 기반 문서 선별 중...")
            
            # 개선된 필터링 적용
            filtered_documents = self.advanced_filter_documents_v3(documents, query_type, query, target_service_name)
            
            return filtered_documents
            
        except Exception as e:
            st.warning(f"시맨틱 검색 실패, 일반 검색으로 대체: {str(e)}")
            return self.search_documents_with_service_filter(query, target_service_name, query_type, top_k)

    def search_documents_with_service_filter(self, query, target_service_name=None, query_type="default", top_k=15):
        """서비스명 필터링을 지원하는 일반 검색 (fallback용)"""
        try:
            # 검색 쿼리 구성
            if target_service_name:
                enhanced_query = f'(service_name:"{target_service_name}" OR service_name:*{target_service_name}*) AND ({query})'
            else:
                enhanced_query = query
            
            # 일반 검색 실행
            results = self.search_client.search(
                search_text=enhanced_query,
                top=top_k,
                include_total_count=True,
                select=[
                    "incident_id", "service_name", "error_time", "effect", "symptom", "repair_notice", 
                    "error_date", "week", "daynight", "root_cause", "incident_repair", 
                    "incident_plan", "cause_type", "done_type", "incident_grade", 
                    "owner_depart", "year", "month"
                ]
            )
            
            documents = []
            for result in results:
                documents.append({
                    "incident_id": result.get("incident_id", ""),
                    "service_name": result.get("service_name", ""),
                    "error_time": result.get("error_time", 0),
                    "effect": result.get("effect", ""),
                    "symptom": result.get("symptom", ""),
                    "repair_notice": result.get("repair_notice", ""),
                    "error_date": result.get("error_date", ""),
                    "week": result.get("week", ""),
                    "daynight": result.get("daynight", ""),
                    "root_cause": result.get("root_cause", ""),
                    "incident_repair": result.get("incident_repair", ""),
                    "incident_plan": result.get("incident_plan", ""),
                    "cause_type": result.get("cause_type", ""),
                    "done_type": result.get("done_type", ""),
                    "incident_grade": result.get("incident_grade", ""),
                    "owner_depart": result.get("owner_depart", ""),
                    "year": result.get("year", ""),
                    "month": result.get("month", ""),
                    "score": result.get("@search.score", 0),
                    "reranker_score": result.get("@search.reranker_score", 0)
                })
            
            # 개선된 필터링 적용
            filtered_documents = self.advanced_filter_documents_v3(documents, query_type, query, target_service_name)
            
            return filtered_documents
            
        except Exception as e:
            st.error(f"일반 검색 실패: {str(e)}")
            return []

    def search_documents_fallback(self, query, target_service_name=None, top_k=25):
        """매우 관대한 기준의 대체 검색"""
        try:
            # 매우 관대한 임계값으로 설정
            fallback_thresholds = {
                'search_threshold': 0.05,      # 매우 낮은 검색 점수 허용
                'reranker_threshold': 0.5,     # 매우 낮은 Reranker 점수 허용
                'hybrid_threshold': 0.1,       # 매우 낮은 하이브리드 점수 허용
                'semantic_threshold': 0.05,    # 매우 낮은 의미적 유사성 허용
                'max_results': 15              # 결과 수 제한
            }
            
            # 기본 검색 실행
            if target_service_name:
                # 서비스명이 있으면 서비스명을 우선시하되 매우 관대하게
                search_query = f'service_name:*{target_service_name}*'
            else:
                search_query = query
            
            results = self.search_client.search(
                search_text=search_query,
                top=top_k,
                include_total_count=True,
                select=[
                    "incident_id", "service_name", "error_time", "effect", "symptom", "repair_notice", 
                    "error_date", "week", "daynight", "root_cause", "incident_repair", 
                    "incident_plan", "cause_type", "done_type", "incident_grade", 
                    "owner_depart", "year", "month"
                ]
            )
            
            documents = []
            for result in results:
                score = result.get("@search.score", 0)
                
                # 매우 관대한 점수 기준 적용
                if score >= fallback_thresholds['search_threshold']:
                    doc = {
                        "incident_id": result.get("incident_id", ""),
                        "service_name": result.get("service_name", ""),
                        "error_time": result.get("error_time", 0),
                        "effect": result.get("effect", ""),
                        "symptom": result.get("symptom", ""),
                        "repair_notice": result.get("repair_notice", ""),
                        "error_date": result.get("error_date", ""),
                        "week": result.get("week", ""),
                        "daynight": result.get("daynight", ""),
                        "root_cause": result.get("root_cause", ""),
                        "incident_repair": result.get("incident_repair", ""),
                        "incident_plan": result.get("incident_plan", ""),
                        "cause_type": result.get("cause_type", ""),
                        "done_type": result.get("done_type", ""),
                        "incident_grade": result.get("incident_grade", ""),
                        "owner_depart": result.get("owner_depart", ""),
                        "year": result.get("year", ""),
                        "month": result.get("month", ""),
                        "score": score,
                        "reranker_score": result.get("@search.reranker_score", 0),
                        "final_score": score,
                        "quality_tier": "Basic",
                        "filter_reason": f"대체 검색 (관대한 기준, 점수: {score:.2f})",
                        "service_match_type": "fallback"
                    }
                    documents.append(doc)
            
            # 점수 기준으로 정렬하고 상위 결과만 반환
            documents.sort(key=lambda x: x.get('final_score', 0), reverse=True)
            
            return documents[:fallback_thresholds['max_results']]
            
        except Exception as e:
            st.error(f"대체 검색도 실패: {str(e)}")
            return []

    def _extract_service_name_legacy(self, query):
        """기존 패턴 기반 서비스명 추출 (fallback)"""
        service_patterns = [
            r'([A-Za-z가-힣][A-Za-z0-9가-힣_\-/\+\(\)\s]*[A-Za-z0-9가-힣_\-/\+\)])\s+(?:년도별|월별|건수|장애|현상|복구|서비스|통계|발생|발생일자|언제)',
            r'서비스.*?([A-Za-z가-힣][A-Za-z0-9가-힣_\-/\+\(\)\s]*[A-Za-z0-9가-힣_\-/\+\)])',
            r'^([A-Za-z가-힣][A-Za-z0-9가-힣_\-/\+\(\)\s]*[A-Za-z0-9가-힣_\-/\+\)])\s+(?!으로|에서|에게|에|을|를|이|가)',
            r'["\']([A-Za-z가-힣][A-Za-z0-9가-힣_\-/\+\(\)\s]*[A-Za-z0-9가-힣_\-/\+\)])["\']',
            r'\(([A-Za-z가-힣][A-Za-z0-9가-힣_\-/\+\s]*[A-Za-z0-9가-힣_\-/\+])\)',
            r'\b([A-Za-z가-힣][A-Za-z0-9가-힣_\-/\+\(\)]{2,}(?:\s+[A-Za-z0-9가-힣_\-/\+\(\)]+)*)\b'
        ]
        
        for pattern in service_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            for match in matches:
                service_name = match.strip()
                if len(service_name) >= 2:
                    return service_name
        
        return None