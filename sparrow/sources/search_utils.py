import streamlit as st
import re
from config.settings import AppConfig

class SearchManager:
    """검색 관련 기능 관리 클래스 - 인터넷 검색 지원 + RAG 기반 서비스명 추출"""
    
    def __init__(self, search_client, config=None):
        self.search_client = search_client
        # config가 None이면 새로 생성하여 안전장치 제공
        self.config = config if config else AppConfig()
        # 서비스명 캐시 (성능 향상을 위해)
        self._service_names_cache = None
        self._cache_loaded = False
    
    @st.cache_data(ttl=3600)  # 1시간 캐시
    def _load_service_names_from_rag(_self):
        """RAG 데이터에서 실제 서비스명 목록을 가져와서 캐시 (조용한 로딩)"""
        try:
            # Azure Search에서 모든 고유한 서비스명 가져오기
            results = _self.search_client.search(
                search_text="*",  # 모든 문서 검색
                top=1000,  # 충분한 수의 문서
                select=["service_name"],
                include_total_count=True
            )
            
            service_names = set()
            for result in results:
                service_name = result.get("service_name", "").strip()
                if service_name:
                    service_names.add(service_name)
            
            # 서비스명을 길이별로 정렬 (긴 것부터 - 더 구체적인 매칭 우선)
            sorted_service_names = sorted(list(service_names), key=len, reverse=True)
            
            # 로딩 완료 메시지는 표시하지 않음 (조용한 처리)
            return sorted_service_names
            
        except Exception as e:
            # 오류 시에만 경고 표시
            st.warning(f"RAG 데이터에서 서비스명 로드 실패: {str(e)}")
            return []
    
    def get_service_names_from_rag(self):
        """RAG 데이터에서 서비스명 목록 가져오기 (캐시 활용)"""
        if not self._cache_loaded:
            self._service_names_cache = self._load_service_names_from_rag()
            self._cache_loaded = True
        return self._service_names_cache or []
    
    def extract_service_name_from_query(self, query):
        """RAG 데이터 기반 서비스명 추출 - 인터넷 검색 버전 (조용한 처리)"""
        # RAG 데이터에서 실제 서비스명 목록 가져오기
        rag_service_names = self.get_service_names_from_rag()
        
        if not rag_service_names:
            # RAG 데이터 로드 실패 시에만 경고 표시
            return self._extract_service_name_legacy(query)
        
        # 쿼리를 소문자로 변환하여 비교
        query_lower = query.lower()
        
        # 1단계: 완전 일치 검색 (대소문자 무시) - 조용한 처리
        for service_name in rag_service_names:
            if service_name.lower() in query_lower:
                # 성공 메시지 제거, 서비스명만 반환
                return service_name
        
        # 2단계: 부분 일치 검색 (공백 제거 후) - 조용한 처리
        query_no_space = re.sub(r'\s+', '', query_lower)
        for service_name in rag_service_names:
            service_name_no_space = re.sub(r'\s+', '', service_name.lower())
            if service_name_no_space in query_no_space or query_no_space in service_name_no_space:
                # 매칭 정보 메시지 제거, 서비스명만 반환
                return service_name
        
        # 3단계: 단어별 매칭 (영문 단어 기준) - 조용한 처리
        query_words = re.findall(r'[A-Za-z]+', query)
        if query_words:
            for service_name in rag_service_names:
                service_words = re.findall(r'[A-Za-z]+', service_name)
                # 쿼리의 영문 단어가 서비스명에 포함되어 있는지 확인
                for query_word in query_words:
                    if len(query_word) >= 3:  # 3자 이상의 의미있는 단어만
                        for service_word in service_words:
                            if query_word.lower() == service_word.lower():
                                # 단어 매칭 정보 메시지 제거, 서비스명만 반환
                                return service_name
        
        # 4단계: 유사도 기반 매칭 (편집 거리 사용) - 조용한 처리
        best_match = self._find_best_similarity_match(query, rag_service_names)
        if best_match:
            # 유사도 매칭 정보 메시지 제거, 서비스명만 반환
            return best_match
        
        # 매칭 실패 메시지 제거, None 반환
        return None
    
    def _find_best_similarity_match(self, query, service_names, threshold=0.7):
        """편집 거리 기반 유사도 매칭"""
        def calculate_similarity(s1, s2):
            """간단한 유사도 계산 (Jaccard 유사도)"""
            s1_words = set(re.findall(r'[A-Za-z가-힣]+', s1.lower()))
            s2_words = set(re.findall(r'[A-Za-z가-힣]+', s2.lower()))
            
            if not s1_words or not s2_words:
                return 0
            
            intersection = len(s1_words.intersection(s2_words))
            union = len(s1_words.union(s2_words))
            
            return intersection / union if union > 0 else 0
        
        best_score = 0
        best_match = None
        
        for service_name in service_names:
            similarity = calculate_similarity(query, service_name)
            if similarity > best_score and similarity >= threshold:
                best_score = similarity
                best_match = service_name
        
        return best_match
    
    def _extract_service_name_legacy(self, query):
        """기존 패턴 기반 서비스명 추출 (fallback) - 조용한 처리"""
        # 기존 로직을 그대로 유지 (RAG 데이터 로드 실패시 사용)
        service_patterns = [
            r'([A-Za-z][A-Za-z0-9_\-/\+\(\)\s]*[A-Za-z0-9_\-/\+\)])\s+(?:년도별|월별|건수|장애|현상|복구|서비스|통계|발생|발생일자|언제)',
            r'서비스.*?([A-Za-z][A-Za-z0-9_\-/\+\(\)\s]*[A-Za-z0-9_\-/\+\)])',
            r'^([A-Za-z][A-Za-z0-9_\-/\+\(\)\s]*[A-Za-z0-9_\-/\+\)])\s+(?!으로|에서|에게|에|을|를|이|가)',
            r'["\']([A-Za-z][A-Za-z0-9_\-/\+\(\)\s]*[A-Za-z0-9_\-/\+\)])["\']',
            r'\(([A-Za-z][A-Za-z0-9_\-/\+\s]*[A-Za-z0-9_\-/\+])\)',
            r'\b([A-Za-z][A-Za-z0-9_\-/\+\(\)]{2,}(?:\s+[A-Za-z0-9_\-/\+\(\)]+)*)\b'
        ]
        
        for pattern in service_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            for match in matches:
                service_name = match.strip()
                if self.is_valid_service_name(service_name):
                    return service_name
        
        return None
    
    def display_available_services(self, limit=10):
        """사용 가능한 서비스명 목록 표시 (디버깅/참고용) - 인터넷 검색 버전"""
        service_names = self.get_service_names_from_rag()
        if service_names:
            st.info(f"📋 **사용 가능한 서비스명 예시** (총 {len(service_names)}개 중 {limit}개)")
            for i, service_name in enumerate(service_names[:limit]):
                st.write(f"• {service_name}")
            if len(service_names) > limit:
                st.write(f"... 외 {len(service_names) - limit}개")
    
    def search_service_names(self, keyword):
        """키워드로 서비스명 검색 (사용자 도움용)"""
        service_names = self.get_service_names_from_rag()
        matching_services = []
        
        keyword_lower = keyword.lower()
        for service_name in service_names:
            if keyword_lower in service_name.lower():
                matching_services.append(service_name)
        
        return matching_services[:10]  # 최대 10개까지
    
    def is_valid_service_name(self, service_name):
        """서비스명이 유효한지 검증"""
        # 기본 조건: 최소 길이 체크
        if len(service_name) < 3:
            return False
        
        # 영문자로 시작해야 함
        if not service_name[0].isalpha():
            return False
        
        # 괄호 검증: 열린 괄호와 닫힌 괄호 수가 일치해야 함
        if service_name.count('(') != service_name.count(')'):
            return False
        
        # 슬러시가 연속으로 나오지 않아야 함 (//)
        if '//' in service_name:
            return False
        
        # 플러스가 연속으로 나오지 않아야 함 (++)
        if '++' in service_name:
            return False
        
        # 특수문자로 끝나지 않아야 함 (단, 괄호 제외)
        if service_name[-1] in ['-', '/', '+'] and not service_name.endswith(')'):
            return False
        
        # 서비스명 특성 검증 (다음 중 하나라도 만족해야 함)
        validation_criteria = [
            '_' in service_name,                    # 언더스코어 포함
            '-' in service_name,                    # 하이픈 포함
            '/' in service_name,                    # 슬러시 포함
            '+' in service_name,                    # 플러스 포함
            '(' in service_name,                    # 괄호 포함
            any(c.isupper() for c in service_name), # 대문자 포함
            len(service_name) >= 5,                 # 5자 이상
            any(c.isdigit() for c in service_name), # 숫자 포함
            ' ' in service_name.strip(),            # 공백 포함 (양끝 제외)
        ]
        
        if not any(validation_criteria):
            return False
        
        # 제외할 일반적인 단어들
        excluded_words = [
            'service', 'system', 'server', 'client', 'application', 'app',
            'website', 'web', 'platform', 'portal', 'interface', 'api',
            'database', 'data', 'file', 'log', 'error', 'issue', 'problem',
            'http', 'https', 'www', 'com', 'org', 'net',
            '년도별', '월별', '건수', '장애', '현상', '복구', '통계', '발생'
        ]
        
        # 괄호, 슬러시, 플러스 등을 제외한 기본 이름 추출해서 검증
        clean_name = re.sub(r'[\(\)/\+_\-\s]', '', service_name).lower()
        if clean_name in excluded_words:
            return False
        
        # 한글이 포함된 경우 제외
        if any('\u3131' <= c <= '\u318E' or '\uAC00' <= c <= '\uD7A3' for c in service_name):
            return False
        
        return True

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
        """서비스명 포함 매칭을 지원하는 개선된 필터링 - 조용한 처리"""
        
        # 동적 임계값 획득
        thresholds = self.config.get_dynamic_thresholds(query_type, query_text)
        
        filtered_docs = []
        filter_stats = {
            'total': len(documents),
            'search_filtered': 0,
            'service_exact_match': 0,
            'service_partial_match': 0,
            'service_filtered': 0,
            'reranker_qualified': 0,
            'hybrid_qualified': 0,
            'final_selected': 0
        }
        
        excluded_docs = []  # 제외된 문서 추적
        
        for doc in documents:
            search_score = doc.get('score', 0)
            reranker_score = doc.get('reranker_score', 0)
            
            # 1단계: 기본 검색 점수 필터링 (동적 임계값 적용)
            if search_score < thresholds['search_threshold']:
                continue
            filter_stats['search_filtered'] += 1
            
            # 2단계: RAG 기반 서비스명 포함 매칭 (조용한 처리)
            if target_service_name:
                doc_service_name = doc.get('service_name', '').strip()
                
                # 정확한 매칭 우선 확인
                if doc_service_name.lower() == target_service_name.lower():
                    filter_stats['service_exact_match'] += 1
                    doc['service_match_type'] = 'exact'
                # 포함 매칭 확인
                elif target_service_name.lower() in doc_service_name.lower() or doc_service_name.lower() in target_service_name.lower():
                    filter_stats['service_partial_match'] += 1
                    doc['service_match_type'] = 'partial'
                else:
                    excluded_docs.append({
                        'incident_id': doc.get('incident_id', ''),
                        'service_name': doc_service_name,
                        'expected_service': target_service_name,
                        'reason': 'RAG 기반 서비스명 불일치'
                    })
                    continue
            else:
                doc['service_match_type'] = 'all'
                
            filter_stats['service_filtered'] += 1
            
            # 3단계: Reranker 점수 우선 평가 (동적 임계값 적용)
            if reranker_score >= thresholds['reranker_threshold']:
                filter_stats['reranker_qualified'] += 1
                match_type = doc.get('service_match_type', 'unknown')
                doc['filter_reason'] = f"RAG 기반 서비스명 {match_type} 매칭 + Reranker 고품질 (점수: {reranker_score:.2f})"
                doc['final_score'] = reranker_score
                doc['quality_tier'] = 'Premium'
                filtered_docs.append(doc)
                filter_stats['final_selected'] += 1
                continue
            
            # 4단계: 하이브리드 점수 평가 (동적 임계값 적용)
            hybrid_score = self.calculate_hybrid_score(search_score, reranker_score)
            if hybrid_score >= thresholds['hybrid_threshold']:
                filter_stats['hybrid_qualified'] += 1
                match_type = doc.get('service_match_type', 'unknown')
                doc['filter_reason'] = f"RAG 기반 서비스명 {match_type} 매칭 + 하이브리드 점수 통과 (점수: {hybrid_score:.2f})"
                doc['final_score'] = hybrid_score
                doc['quality_tier'] = 'Standard'
                filtered_docs.append(doc)
                filter_stats['final_selected'] += 1
        
        # 정확한 매칭을 우선으로 정렬 (exact > partial), 그 다음 점수순
        def sort_key(doc):
            match_priority = {'exact': 3, 'partial': 2, 'all': 1}
            return (match_priority.get(doc.get('service_match_type', 'all'), 0), doc['final_score'])
        
        filtered_docs.sort(key=sort_key, reverse=True)
        
        # 최종 결과 수 제한 (동적 적용)
        final_docs = filtered_docs[:thresholds['max_results']]
       
        # 간소화된 필터링 통계 표시 (중간 과정 메시지 제거, 최종 결과만 표시)
        st.info(f"""
        📊 **서비스명 포함 매칭 기반 문서 필터링 결과**
        - 🔍 전체 검색 결과: {filter_stats['total']}개
        - ✅ 기본 점수 통과: {filter_stats['search_filtered']}개
        - ✅ 총 서비스명 매칭: {filter_stats['service_filtered']}개
        - 🏆 Reranker 고품질: {filter_stats['reranker_qualified']}개
        - 🎯 하이브리드 통과: {filter_stats['hybrid_qualified']}개
        - 📋 최종 선별: {len(final_docs)}개
        """)
        
        return final_docs

    def semantic_search_with_service_filter(self, query, target_service_name=None, query_type="default", top_k=20):
        """서비스명 포함 검색을 지원하는 개선된 시맨틱 검색 - 조용한 처리"""
        try:
            # RAG 기반 서비스명 포함 검색을 위한 검색 쿼리 구성
            if target_service_name:
                # 정확한 매칭과 포함 검색을 모두 지원
                enhanced_query = f'(service_name:"{target_service_name}" OR service_name:*{target_service_name}*)'
                if query != target_service_name:  # 원래 쿼리에 추가 조건이 있는 경우
                    enhanced_query += f" AND ({query})"
                # 검색 쿼리 구성 메시지 제거
            else:
                enhanced_query = query
                
            st.info(f"📄 1단계: {top_k}개 초기 검색 결과 수집 중...")
            
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
            
            st.info(f"🎯 2단계: 서비스명 포함 매칭 + 동적 임계값 기반 고품질 문서 선별 중...")
            
            # 개선된 필터링 적용 (서비스명 포함 매칭)
            filtered_documents = self.advanced_filter_documents_v3(documents, query_type, query, target_service_name)
            
            return filtered_documents
            
        except Exception as e:
            st.warning(f"시맨틱 검색 실패, 일반 검색으로 대체: {str(e)}")
            return self.search_documents_with_service_filter(query, target_service_name, query_type, top_k)

    def search_documents_with_service_filter(self, query, target_service_name=None, query_type="default", top_k=20):
        """일반 검색에 서비스명 포함 필터링 적용 - 조용한 처리"""
        try:
            # RAG 기반 서비스명 포함 검색을 위한 검색 쿼리 구성
            if target_service_name:
                enhanced_query = f'(service_name:"{target_service_name}" OR service_name:*{target_service_name}*)'
                if query != target_service_name:
                    enhanced_query += f" AND ({query})"
            else:
                enhanced_query = query
                
            st.info(f"📄 1단계: {top_k}개 초기 검색 결과 수집 중...")
            
            results = self.search_client.search(
                search_text=enhanced_query,
                top=top_k,
                include_total_count=True,
                select=[
                    "incident_id", "service_name", "error_time", "effect", "symptom", "repair_notice", 
                    "error_date", "week", "daynight", "root_cause", "incident_repair", 
                    "incident_plan", "cause_type", "done_type", "incident_grade", 
                    "owner_depart", "year", "month"
                ],
                search_fields=[
                    "repair_notice", "error_date", "effect", "symptom", "week", "daynight", "root_cause", "incident_repair", 
                    "incident_plan", "service_name", "cause_type", 
                    "done_type", "owner_depart", "year", "month"
                ]
            )
            
            documents = []
            for result in results:
                documents.append({
                    "incident_id": result.get("incident_id", ""),
                    "service_name": result.get("service_name", ""),
                    "error_time": result.get("error_time", 0),
                    "repair_notice": result.get("repair_notice", ""),
                    "effect": result.get("effect", ""),
                    "symptom": result.get("symptom", ""),
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
                    "fail_type": result.get("fail_type", ""),
                    "year": result.get("year", ""),
                    "month": result.get("month", ""),
                    "score": result.get("@search.score", 0),
                    "reranker_score": 0  # 일반 검색에서는 0
                })
            
            st.info(f"🎯 2단계: 서비스명 포함 매칭 + 동적 임계값 기반 고품질 문서 선별 중...")
            
            # 개선된 필터링 적용 (서비스명 포함 매칭)
            filtered_documents = self.advanced_filter_documents_v3(documents, query_type, query, target_service_name)
            
            return filtered_documents
            
        except Exception as e:
            st.error(f"검색 실패: {str(e)}")
            return []

    def search_documents_fallback(self, query, target_service_name=None, top_k=15):
        """매우 관대한 기준의 대체 검색 (포함 매칭 지원) - 조용한 처리"""
        try:
            # RAG 기반 서비스명 포함 검색을 위한 검색 쿼리 구성
            if target_service_name:
                enhanced_query = f'(service_name:"{target_service_name}" OR service_name:*{target_service_name}*)'
                if query != target_service_name:
                    enhanced_query += f" AND ({query})"
            else:
                enhanced_query = query
                
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
                score = result.get("@search.score", 0)
                if score >= 0.1:  # 매우 낮은 기준
                    doc_service_name = result.get("service_name", "").strip()
                    
                    # RAG 기반 서비스명 포함 필터링 (대체 검색에서도 적용)
                    if target_service_name:
                        if not (doc_service_name.lower() == target_service_name.lower() or 
                               target_service_name.lower() in doc_service_name.lower() or 
                               doc_service_name.lower() in target_service_name.lower()):
                            continue
                        
                    documents.append({
                        "incident_id": result.get("incident_id", ""),
                        "service_name": doc_service_name,
                        "error_time": result.get("error_time", 0),
                        "repair_notice": result.get("repair_notice", ""),
                        "effect": result.get("effect", ""),
                        "symptom": result.get("symptom", ""),
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
                        "reranker_score": 0,
                        "final_score": score,
                        "quality_tier": "Basic",
                        "filter_reason": "대체 검색 통과 (포함 매칭)",
                        "service_match_type": "partial" if target_service_name else "all"
                    })
            
            return documents[:8]  # 최대 8개까지
            
        except Exception as e:
            st.error(f"대체 검색 실패: {str(e)}")
            return []