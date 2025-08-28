import streamlit as st
import re
from config.settings_local import AppConfigLocal

class SearchManagerLocal:
    """검색 관련 기능 관리 클래스 - 쿼리 타입별 적응형 검색 최적화"""
    
    # 일반적인 용어로 사용되는 서비스명들 - 하드코딩 예외처리
    COMMON_TERM_SERVICES = {
        'OTP': ['otp', '일회용비밀번호', '원타임패스워드', '2차인증', '이중인증'],           
        '본인인증': ['실명인증', '신원확인'],
        'API': ['api', 'Application Programming Interface', 'REST API', 'API호출'],
        'SMS': ['sms', '문자', '단문', 'Short Message Service', '문자메시지'],
        'VPN': ['vpn', 'Virtual Private Network', '가상사설망'],
        'DNS': ['dns', 'Domain Name System', '도메인네임시스템'],
        'SSL': ['ssl', 'https', 'Secure Sockets Layer', '보안소켓계층'],
        'URL': ['url', 'link', '링크', 'Uniform Resource Locator']
    }
    
    def __init__(self, search_client, config=None):
        self.search_client = search_client
        self.config = config if config else AppConfigLocal()
        self._service_names_cache = None
        self._cache_loaded = False
        # effect 패턴 캐시
        self._effect_patterns_cache = None
        self._effect_cache_loaded = False
    
    def is_common_term_service(self, service_name):
        """일반 용어로 사용되는 서비스명인지 확인"""
        if not service_name:
            return False
        
        service_lower = service_name.lower().strip()
        
        for common_service, aliases in self.COMMON_TERM_SERVICES.items():
            if service_lower == common_service.lower() or service_lower in [alias.lower() for alias in aliases]:
                return True, common_service
        
        return False, None
    
    def get_common_term_search_patterns(self, service_name):
        """일반 용어 서비스명에 대한 검색 패턴 생성"""
        is_common, main_service = self.is_common_term_service(service_name)
        
        if not is_common:
            return []
        
        patterns = []
        aliases = self.COMMON_TERM_SERVICES.get(main_service, [])
        
        # 메인 서비스명과 모든 별칭들에 대한 패턴 생성
        for term in [main_service] + aliases:
            patterns.extend([
                f'({term})',
                f'(effect:"{term}")',
                f'(symptom:"{term}")',
                f'(root_cause:"{term}")',
                f'(incident_repair:"{term}")',
                f'(repair_notice:"{term}")'
            ])
        
        return patterns

    def extract_query_keywords(self, query):
        """질문에서 핵심 키워드 추출 - 관련성 검증용 (repair/cause 전용)"""
        keywords = {
            'service_keywords': [],
            'symptom_keywords': [],
            'action_keywords': [],
            'time_keywords': []
        }
        
        # 서비스 관련 키워드 - 일반 용어 서비스명 추가
        service_patterns = [
            r'\b(관리자|admin)\s*(웹|web|페이지|page)',
            r'\b(API|api)\s*(링크|link|서비스)',
            r'\b(ERP|erp)\b',
            r'\b(마이페이지|mypage)',
            r'\b(보험|insurance)',
            r'\b(커뮤니티|community)',
            r'\b(블록체인|blockchain)',
            # 일반 용어 서비스명 패턴 추가
            r'\b(OTP|otp|일회용비밀번호)\b',
            r'\b(SMS|sms|문자|단문)\b',
            r'\b(VPN|vpn|가상사설망)\b',
            r'\b(DNS|dns|도메인)\b',
            r'\b(SSL|ssl|https|보안)\b'
        ]
        
        for pattern in service_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                keywords['service_keywords'].extend([match if isinstance(match, str) else ' '.join(match) for match in matches])
        
        # 증상/현상 관련 키워드 - 의미적 동의어 확장
        symptom_patterns = [
            r'\b(로그인|login)\s*(불가|실패|안됨|오류)',
            r'\b(접속|연결)\s*(불가|실패|안됨|오류)',
            r'\b(가입|회원가입)\s*(불가|실패|안됨)',
            r'\b(결제|구매|주문)\s*(불가|실패|오류)',
            r'\b(응답|response)\s*(지연|느림|없음)',
            r'\b(페이지|page)\s*(로딩|loading)\s*(불가|실패)',
            r'\b(문자|SMS)\s*(발송|전송)\s*(불가|실패|안됨)',  # 확장된 패턴
            r'\b(발송|전송|송신)\s*(불가|실패|안됨|오류)',     # 추가 패턴
            # OTP 관련 증상 패턴 추가
            r'\b(OTP|otp|일회용비밀번호)\s*(불가|실패|안됨|오류|지연)',
            r'\b(인증|2차인증|이중인증)\s*(불가|실패|안됨|오류)'
        ]
        
        for pattern in symptom_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                keywords['symptom_keywords'].extend([match if isinstance(match, str) else ' '.join(match) for match in matches])
        
        # 요청 행동 관련 키워드
        action_patterns = [
            r'\b(복구|해결|수리)(?:방법|조치)',
            r'\b(원인|이유|cause)',
            r'\b(유사|비슷|similar)(?:사례|현상)',
            r'\b(내역|이력|history)',
            r'\b(건수|개수|통계)'
        ]
        
        for pattern in action_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                keywords['action_keywords'].extend(matches)
        
        # 시간 관련 키워드
        time_patterns = [
            r'\b(\d{4})년',
            r'\b(\d{1,2})월',
            r'\b(야간|주간|오전|오후)',
            r'\b(최근|recent|어제|오늘)'
        ]
        
        for pattern in time_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                keywords['time_keywords'].extend(matches)
        
        return keywords
    
    def calculate_keyword_relevance_score(self, query, document):
        """키워드 기반 관련성 점수 계산 - repair/cause용 정확성 향상"""
        query_keywords = self.extract_query_keywords(query)
        score = 0
        max_score = 100
        
        # 문서 텍스트 준비
        doc_text = f"""
        {document.get('service_name', '')} 
        {document.get('symptom', '')} 
        {document.get('effect', '')} 
        {document.get('root_cause', '')} 
        {document.get('incident_repair', '')}
        """.lower()
        
        # 서비스명 매칭 (40점)
        service_score = 0
        for keyword in query_keywords['service_keywords']:
            if keyword.lower() in doc_text:
                service_score = 40
                break
        score += service_score
        
        # 증상/현상 매칭 (35점)
        symptom_score = 0
        for keyword in query_keywords['symptom_keywords']:
            if keyword.lower() in doc_text:
                symptom_score = 35
                break
        score += symptom_score
        
        # 요청 행동 매칭 (15점)
        action_score = 0
        for keyword in query_keywords['action_keywords']:
            if keyword.lower() in doc_text:
                action_score = 15
                break
        score += action_score
        
        # 시간 관련 매칭 (10점)
        time_score = 0
        for keyword in query_keywords['time_keywords']:
            if keyword.lower() in doc_text:
                time_score = 10
                break
        score += time_score
        
        return min(score, max_score)

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
        """텍스트를 의미적 유사성 비교를 위해 정규화 - 의미적 동의어 확장"""
        if not text:
            return ""
        
        # 띄어쓰기 제거
        normalized = re.sub(r'\s+', '', text.lower())
        
        # 의미가 같은 표현들을 통일 - 확장된 동의어 사전
        replacements = {
            # 불가/실패 관련 확장
            '불가능': '불가', '실패': '불가', '안됨': '불가', '되지않음': '불가', 
            '할수없음': '불가', '불능': '불가', '에러': '불가', '장애': '불가',
            
            # 접속/연결 관련
            '접속': '연결', '로그인': '접속', '액세스': '접속', '진입': '접속',
            
            # 오류/에러 관련
            '오류': '에러', '장애': '에러', '문제': '에러', '이슈': '에러', '버그': '에러',
            
            # 지연/느림 관련
            '지연': '느림', '늦음': '느림', '응답없음': '느림', '타임아웃': '느림',
            
            # 서비스/기능 관련
            '서비스': '기능', '시스템': '서비스', '플랫폼': '서비스',
            
            # 가입/등록 관련
            '가입': '등록', '신청': '등록', '회원가입': '등록', '회원등록': '등록',
            
            # 결제/구매 관련
            '결제': '구매', '구매': '결제', '주문': '결제', '거래': '결제', '구입': '결제',
            
            # 발송/전송 관련 - 확장
            '발송': '전송', '송신': '전송', '전달': '전송', '보내기': '전송',
            
            # 일반 용어 서비스명 정규화
            'otp': 'OTP', '일회용비밀번호': 'OTP', '원타임패스워드': 'OTP',
            'api': 'API', 'sms': 'SMS', '문자': 'SMS', '단문': 'SMS',
            'vpn': 'VPN', '가상사설망': 'VPN', 'dns': 'DNS', '도메인': 'DNS'
        }
        
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        
        return normalized
    
    def _extract_semantic_keywords(self, text):
        """텍스트에서 의미적 키워드 추출 - 발송/전송 관련 확장"""
        if not text:
            return []
        
        keyword_patterns = [
            # 동작 + 대상 패턴 - 발송/전송 관련 추가
            r'(\w+)(불가|실패|에러|오류|지연|느림)',
            r'(\w+)(가입|등록|신청)',
            r'(\w+)(결제|구매|주문)',
            r'(\w+)(접속|연결|로그인)',
            r'(\w+)(조회|검색|확인)',
            r'(\w+)(발송|전송|송신)',  # 새로 추가
            
            # 대상 + 상태 패턴 - 확장
            r'(보험|가입|결제|접속|로그인|조회|검색|주문|구매|발송|전송|문자|SMS|OTP|API)(\w*)',
            
            # 서비스명 관련
            r'(앱|웹|사이트|페이지|시스템|서비스)(\w*)',
            
            # 단독 중요 키워드 - 발송 관련 추가
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
        """쿼리를 의미적으로 유사한 표현들로 확장 - 동의어 확장"""
        effect_patterns = self.get_effect_patterns_from_rag()
        
        if not effect_patterns:
            return query
        
        query_keywords = self._extract_semantic_keywords(query)
        query_normalized = self._normalize_text_for_similarity(query)
        
        similar_effects = set()
        semantic_expansions = set()
        
        # 동의어 확장을 위한 추가 처리
        expanded_query_keywords = set(query_keywords)
        
        # 불가/실패 동의어 확장
        if any(keyword in query.lower() for keyword in ['불가', '실패', '안됨', '에러', '오류']):
            expanded_query_keywords.update(['불가', '실패', '안됨', '에러', '오류', '장애'])
        
        # 발송/전송 동의어 확장
        if any(keyword in query.lower() for keyword in ['발송', '전송', '문자', 'sms']):
            expanded_query_keywords.update(['발송', '전송', '송신', '문자', 'sms'])
        
        # 일반 용어 서비스명 확장
        for common_service in self.COMMON_TERM_SERVICES.keys():
            if common_service.lower() in query.lower():
                aliases = self.COMMON_TERM_SERVICES[common_service]
                expanded_query_keywords.update([common_service] + aliases)
        
        for keyword in expanded_query_keywords:
            if keyword in effect_patterns:
                for pattern_info in effect_patterns[keyword]:
                    similarity = self._calculate_text_similarity(
                        query_normalized, 
                        pattern_info['normalized_effect']
                    )
                    
                    if similarity > 0.2:  # 임계값을 낮춰서 더 포괄적으로
                        similar_effects.add(pattern_info['original_effect'])
                        semantic_expansions.update(pattern_info['keywords'])
        
        if similar_effects or semantic_expansions:
            expanded_terms = []
            expanded_terms.append(f'({query})')
            
            # 동의어 기반 확장 쿼리 추가
            synonyms = []
            if '불가' in query or '실패' in query:
                synonyms.extend(['불가', '실패', '안됨', '에러', '오류'])
            if '발송' in query or '전송' in query:
                synonyms.extend(['발송', '전송', '송신'])
            
            if synonyms:
                synonym_query = query
                for synonym in synonyms:
                    if synonym not in query:
                        synonym_query = synonym_query.replace('불가', synonym).replace('실패', synonym).replace('발송', synonym).replace('전송', synonym)
                        expanded_terms.append(f'({synonym_query})')
            
            for effect in list(similar_effects)[:5]:
                expanded_terms.append(f'(effect:"{effect}")')
            
            if semantic_expansions:
                semantic_query_parts = []
                for expansion in list(semantic_expansions)[:10]:
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
            
            effect_similarity = 0
            symptom_similarity = 0
            
            if effect:
                effect_normalized = self._normalize_text_for_similarity(effect)
                effect_similarity = self._calculate_text_similarity(query_normalized, effect_normalized)
                
                effect_keywords = set(self._extract_semantic_keywords(effect))
                keyword_overlap = len(query_keywords.intersection(effect_keywords))
                if keyword_overlap > 0:
                    effect_similarity += (keyword_overlap * 0.1)
            
            if symptom:
                symptom_normalized = self._normalize_text_for_similarity(symptom)
                symptom_similarity = self._calculate_text_similarity(query_normalized, symptom_normalized)
            
            max_similarity = max(effect_similarity, symptom_similarity)
            
            if max_similarity > 0.3:
                original_score = doc.get('final_score', doc.get('score', 0))
                boost_factor = 1 + (max_similarity * 0.5)
                doc['final_score'] = original_score * boost_factor
                doc['semantic_similarity'] = max_similarity
                
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
    
    def _normalize_service_name(self, service_name):
        """서비스명을 정규화 - 특수문자 제거 및 공백 처리"""
        if not service_name:
            return ""
        
        # 특수문자를 공백으로 변환 후 중복 공백 제거
        normalized = re.sub(r'[^\w\s가-힣]', ' ', service_name)
        normalized = re.sub(r'\s+', ' ', normalized).strip().lower()
        
        return normalized
    
    def _extract_service_tokens(self, service_name):
        """서비스명에서 의미있는 토큰들을 추출"""
        if not service_name:
            return []
        
        # 특수문자 제거하고 단어 토큰으로 분리
        tokens = re.findall(r'[A-Za-z가-힣0-9]+', service_name)
        # 길이 2 이상인 토큰만 유효하다고 판단
        valid_tokens = [token.lower() for token in tokens if len(token) >= 2]
        
        return valid_tokens
    
    def _calculate_service_similarity(self, query_tokens, service_tokens):
        """토큰 기반 서비스명 유사도 계산"""
        if not query_tokens or not service_tokens:
            return 0.0
        
        query_set = set(query_tokens)
        service_set = set(service_tokens)
        
        # Jaccard 유사도
        intersection = len(query_set.intersection(service_set))
        union = len(query_set.union(service_set))
        
        jaccard_score = intersection / union if union > 0 else 0
        
        # 포함 비율 (쿼리 토큰이 서비스 토큰에 얼마나 포함되는지)
        inclusion_score = intersection / len(query_set) if len(query_set) > 0 else 0
        
        # 두 점수의 가중 평균 (포함 비율을 더 중시)
        final_score = (jaccard_score * 0.3) + (inclusion_score * 0.7)
        
        return final_score
    
    def extract_service_name_from_query(self, query):
        """개선된 RAG 데이터 기반 서비스명 추출 - 토큰 기반 유사도 매칭 + 일반용어 예외처리"""
        # 1단계: 일반 용어 서비스명 확인
        is_common, common_service = self.is_common_term_service(query)
        if is_common:
            st.info(f"일반 용어 서비스명 감지: **{common_service}** (전체 필드 검색 모드)")
            return common_service
        
        rag_service_names = self.get_service_names_from_rag()
        
        if not rag_service_names:
            return self._extract_service_name_legacy(query)
        
        query_lower = query.lower()
        query_tokens = self._extract_service_tokens(query)
        
        if not query_tokens:
            return None
        
        # 후보 서비스명과 유사도 점수를 저장할 리스트
        candidates = []
        
        for service_name in rag_service_names:
            service_tokens = self._extract_service_tokens(service_name)
            
            if not service_tokens:
                continue
            
            # 1단계: 완전 일치 검색 (최고 우선순위)
            if service_name.lower() in query_lower:
                candidates.append((service_name, 1.0, 'exact_match'))
                continue
            
            # 2단계: 정규화된 텍스트 포함 관계
            normalized_query = self._normalize_service_name(query)
            normalized_service = self._normalize_service_name(service_name)
            
            if normalized_service in normalized_query or normalized_query in normalized_service:
                candidates.append((service_name, 0.9, 'normalized_inclusion'))
                continue
            
            # 3단계: 토큰 기반 유사도 계산
            similarity = self._calculate_service_similarity(query_tokens, service_tokens)
            
            if similarity >= 0.5:  # 50% 이상 유사도
                candidates.append((service_name, similarity, 'token_similarity'))
        
        # 후보가 없으면 None 반환
        if not candidates:
            return None
        
        # 유사도 점수 기준으로 정렬 (높은 순)
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        # 가장 높은 점수의 서비스명 반환
        best_match = candidates[0]
        
        # 디버깅을 위한 정보 출력 (개발 환경에서만)
        if len(candidates) > 1:
            st.info(f"서비스명 매칭 결과: '{best_match[0]}' (유사도: {best_match[1]:.2f}, 방식: {best_match[2]})")
        
        return best_match[0]

    def calculate_hybrid_score(self, search_score, reranker_score):
        """검색 점수와 Reranker 점수를 조합하여 하이브리드 점수 계산 - None 값 처리"""
        # None 값 처리
        search_score = search_score if search_score is not None else 0.0
        reranker_score = reranker_score if reranker_score is not None else 0.0
        
        if reranker_score > 0:
            normalized_reranker = min(reranker_score / 4.0, 1.0)
            normalized_search = min(search_score, 1.0)
            hybrid_score = (normalized_reranker * 0.8) + (normalized_search * 0.2)
        else:
            hybrid_score = min(search_score, 1.0)
        
        return hybrid_score

    def advanced_filter_documents_for_accuracy(self, documents, query_type="default", query_text="", target_service_name=None):
        """정확성 우선 필터링 - repair/cause용 - None 값 처리 강화 + 일반용어 서비스명 예외처리"""
        
        thresholds = self.config.get_dynamic_thresholds(query_type, query_text)
        documents = self._boost_semantic_documents(documents, query_text)
        
        # 일반 용어 서비스명인지 확인
        is_common_service = False
        if target_service_name:
            is_common, _ = self.is_common_term_service(target_service_name)
            is_common_service = is_common
        
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
            'keyword_relevant': 0,
            'final_selected': 0,
            'common_term_matches': 0
        }
        
        for doc in documents:
            # None 값 처리
            search_score = doc.get('score', 0) if doc.get('score') is not None else 0.0
            reranker_score = doc.get('reranker_score', 0) if doc.get('reranker_score') is not None else 0.0
            
            if 'semantic_similarity' in doc:
                filter_stats['semantic_boosted'] += 1
            
            # 키워드 기반 관련성 점수 계산
            keyword_relevance = self.calculate_keyword_relevance_score(query_text, doc)
            if keyword_relevance >= 30:
                filter_stats['keyword_relevant'] += 1
                doc['keyword_relevance_score'] = keyword_relevance
            
            # 기본 검색 점수 필터링
            if search_score < thresholds['search_threshold']:
                continue
            filter_stats['search_filtered'] += 1
            
            # 서비스명 매칭 - 일반 용어 서비스명 예외처리
            if target_service_name:
                doc_service_name = doc.get('service_name', '').strip()
                
                if is_common_service:
                    # 일반 용어 서비스명인 경우: 모든 필드에서 검색
                    all_fields_text = f"""
                    {doc.get('service_name', '')} {doc.get('symptom', '')} 
                    {doc.get('effect', '')} {doc.get('root_cause', '')} 
                    {doc.get('incident_repair', '')} {doc.get('repair_notice', '')}
                    """.lower()
                    
                    aliases = self.COMMON_TERM_SERVICES.get(target_service_name, [])
                    search_terms = [target_service_name.lower()] + [alias.lower() for alias in aliases]
                    
                    if any(term in all_fields_text for term in search_terms):
                        filter_stats['common_term_matches'] += 1
                        doc['service_match_type'] = 'common_term'
                    else:
                        continue
                else:
                    # 일반적인 서비스명 매칭
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
            
            # Reranker 점수 우선 평가
            if reranker_score >= thresholds['reranker_threshold']:
                filter_stats['reranker_qualified'] += 1
                match_type = doc.get('service_match_type', 'unknown')
                relevance_info = f" (키워드 관련성: {keyword_relevance}점)" if keyword_relevance >= 30 else ""
                match_desc = "일반용어 전체필드" if match_type == 'common_term' else match_type
                doc['filter_reason'] = f"정확성 우선 - {match_desc} 매칭 + Reranker 고품질 (점수: {reranker_score:.2f}){relevance_info}"
                doc['final_score'] = reranker_score
                doc['quality_tier'] = 'Premium'
                filtered_docs.append(doc)
                filter_stats['final_selected'] += 1
                continue
            
            # 하이브리드 점수 평가
            hybrid_score = self.calculate_hybrid_score(search_score, reranker_score)
            final_score = doc.get('final_score', hybrid_score)
            
            # final_score도 None일 수 있으므로 처리
            final_score = final_score if final_score is not None else 0.0
            
            if final_score >= thresholds['hybrid_threshold']:
                filter_stats['hybrid_qualified'] += 1
                match_type = doc.get('service_match_type', 'unknown')
                relevance_info = f" (키워드 관련성: {keyword_relevance}점)" if keyword_relevance >= 30 else ""
                match_desc = "일반용어 전체필드" if match_type == 'common_term' else match_type
                doc['filter_reason'] = f"정확성 우선 - {match_desc} 매칭 + 하이브리드 통과 (점수: {final_score:.2f}){relevance_info}"
                doc['quality_tier'] = 'Standard'
                filtered_docs.append(doc)
                filter_stats['final_selected'] += 1
        
        # 정확성 우선 정렬
        def sort_key(doc):
            match_priority = {'exact': 3, 'partial': 2, 'common_term': 2.5, 'all': 1}
            semantic_boost = doc.get('semantic_similarity', 0) or 0
            keyword_boost = doc.get('keyword_relevance_score', 0) or 0
            final_score = doc.get('final_score', 0) or 0
            
            return (
                match_priority.get(doc.get('service_match_type', 'all'), 0), 
                final_score + (semantic_boost * 0.1) + (keyword_boost * 0.001)
            )
        
        filtered_docs.sort(key=sort_key, reverse=True)
        final_docs = filtered_docs[:thresholds['max_results']]
       
        common_term_info = f"\n        - 일반용어 전체필드 매칭: {filter_stats['common_term_matches']}개" if is_common_service else ""
        
        st.info(f"""
        정확성 우선 필터링 결과 (repair/cause 최적화)
        - 전체 검색 결과: {filter_stats['total']}개
        - 기본 점수 통과: {filter_stats['search_filtered']}개
        - 총 서비스명 매칭: {filter_stats['service_filtered']}개{common_term_info}
        - Reranker 고품질: {filter_stats['reranker_qualified']}개
        - 하이브리드 통과: {filter_stats['hybrid_qualified']}개
        - 의미적 유사성 부스팅: {filter_stats['semantic_boosted']}개
        - 키워드 관련성 확보: {filter_stats['keyword_relevant']}개
        - 최종 선별: {len(final_docs)}개
        """)
        
        return final_docs

    def simple_filter_documents_for_coverage(self, documents, query_type="default", query_text="", target_service_name=None):
        """포괄성 우선 필터링 - similar/default용 - None 값 처리 강화 + 일반용어 서비스명 예외처리"""
        
        thresholds = self.config.get_dynamic_thresholds(query_type, query_text)
        documents = self._boost_semantic_documents(documents, query_text)
        
        # 일반 용어 서비스명인지 확인
        is_common_service = False
        if target_service_name:
            is_common, _ = self.is_common_term_service(target_service_name)
            is_common_service = is_common
        
        filtered_docs = []
        filter_stats = {
            'total': len(documents),
            'search_filtered': 0,
            'service_filtered': 0,
            'reranker_qualified': 0,
            'hybrid_qualified': 0,
            'semantic_boosted': 0,
            'final_selected': 0,
            'common_term_matches': 0
        }
        
        for doc in documents:
            # None 값 처리
            search_score = doc.get('score', 0) if doc.get('score') is not None else 0.0
            reranker_score = doc.get('reranker_score', 0) if doc.get('reranker_score') is not None else 0.0
            
            if 'semantic_similarity' in doc:
                filter_stats['semantic_boosted'] += 1
            
            # 기본 검색 점수 필터링
            if search_score < thresholds['search_threshold']:
                continue
            filter_stats['search_filtered'] += 1
            
            # 서비스명 매칭 (간소화) - 일반 용어 서비스명 예외처리
            if target_service_name:
                doc_service_name = doc.get('service_name', '').strip()
                
                if is_common_service:
                    # 일반 용어 서비스명인 경우: 모든 필드에서 검색
                    all_fields_text = f"""
                    {doc.get('service_name', '')} {doc.get('symptom', '')} 
                    {doc.get('effect', '')} {doc.get('root_cause', '')} 
                    {doc.get('incident_repair', '')} {doc.get('repair_notice', '')}
                    """.lower()
                    
                    aliases = self.COMMON_TERM_SERVICES.get(target_service_name, [])
                    search_terms = [target_service_name.lower()] + [alias.lower() for alias in aliases]
                    
                    if any(term in all_fields_text for term in search_terms):
                        filter_stats['common_term_matches'] += 1
                        doc['service_match_type'] = 'common_term'
                    else:
                        continue
                else:
                    # 일반적인 서비스명 매칭
                    if doc_service_name.lower() == target_service_name.lower():
                        doc['service_match_type'] = 'exact'
                    elif target_service_name.lower() in doc_service_name.lower() or doc_service_name.lower() in target_service_name.lower():
                        doc['service_match_type'] = 'partial'
                    else:
                        continue
            else:
                doc['service_match_type'] = 'all'
                
            filter_stats['service_filtered'] += 1
            
            # Reranker 점수 우선 평가
            if reranker_score >= thresholds['reranker_threshold']:
                filter_stats['reranker_qualified'] += 1
                match_type = doc.get('service_match_type', 'unknown')
                match_desc = "일반용어 전체필드" if match_type == 'common_term' else match_type
                doc['filter_reason'] = f"포괄성 우선 - {match_desc} 매칭 + Reranker 고품질 (점수: {reranker_score:.2f})"
                doc['final_score'] = reranker_score
                doc['quality_tier'] = 'Premium'
                filtered_docs.append(doc)
                filter_stats['final_selected'] += 1
                continue
            
            # 하이브리드 점수 평가
            hybrid_score = self.calculate_hybrid_score(search_score, reranker_score)
            final_score = doc.get('final_score', hybrid_score)
            
            # final_score도 None일 수 있으므로 처리
            final_score = final_score if final_score is not None else 0.0
            
            if final_score >= thresholds['hybrid_threshold']:
                filter_stats['hybrid_qualified'] += 1
                match_type = doc.get('service_match_type', 'unknown')
                match_desc = "일반용어 전체필드" if match_type == 'common_term' else match_type
                doc['filter_reason'] = f"포괄성 우선 - {match_desc} 매칭 + 하이브리드 통과 (점수: {final_score:.2f})"
                doc['quality_tier'] = 'Standard'
                filtered_docs.append(doc)
                filter_stats['final_selected'] += 1
        
        # 포괄성 우선 정렬 (의미적 유사성 중시)
        def sort_key(doc):
            match_priority = {'exact': 3, 'partial': 2, 'common_term': 2.5, 'all': 1}
            semantic_boost = doc.get('semantic_similarity', 0) or 0
            final_score = doc.get('final_score', 0) or 0
            
            return (
                match_priority.get(doc.get('service_match_type', 'all'), 0), 
                final_score + (semantic_boost * 0.1)
            )
        
        filtered_docs.sort(key=sort_key, reverse=True)
        final_docs = filtered_docs[:thresholds['max_results']]
       
        common_term_info = f"\n        - 일반용어 전체필드 매칭: {filter_stats['common_term_matches']}개" if is_common_service else ""
        
        st.info(f"""
        포괄성 우선 필터링 결과 (similar/default 최적화)
        - 전체 검색 결과: {filter_stats['total']}개
        - 기본 점수 통과: {filter_stats['search_filtered']}개
        - 총 서비스명 매칭: {filter_stats['service_filtered']}개{common_term_info}
        - Reranker 고품질: {filter_stats['reranker_qualified']}개
        - 하이브리드 통과: {filter_stats['hybrid_qualified']}개
        - 의미적 유사성 부스팅: {filter_stats['semantic_boosted']}개
        - 최종 선별: {len(final_docs)}개
        """)
        
        return final_docs

    def semantic_search_with_adaptive_filtering(self, query, target_service_name=None, query_type="default", top_k=50):
        """쿼리 타입별 적응형 필터링을 적용한 시맨틱 검색 - 오류 처리 강화 + 일반용어 서비스명 예외처리"""
        try:
            # 일반 용어 서비스명 확인
            is_common_service = False
            common_service_patterns = []
            if target_service_name:
                is_common, _ = self.is_common_term_service(target_service_name)
                if is_common:
                    is_common_service = True
                    common_service_patterns = self.get_common_term_search_patterns(target_service_name)
                    st.info(f"일반 용어 서비스명 '{target_service_name}' 검색: 모든 필드 대상")
            
            # 의미적 유사성 기반 쿼리 확장
            expanded_query = self._expand_query_with_semantic_similarity(query)
            
            # 쿼리 타입별 초기 검색 결과 수 조정
            if query_type in ['repair', 'cause']:
                top_k = max(top_k, 80)
                st.info(f"초기 검색 결과 수집 중... (정확성 우선 - LLM 검증 준비)")
            else:
                top_k = max(top_k, 30)
                st.info(f"초기 검색 결과 수집 중... (포괄성 우선 - 광범위한 검색)")
            
            # RAG 기반 서비스명 포함 검색을 위한 검색 쿼리 구성
            if target_service_name:
                if is_common_service:
                    # 일반 용어 서비스명: 모든 필드에서 검색
                    field_queries = []
                    aliases = self.COMMON_TERM_SERVICES.get(target_service_name, [])
                    search_terms = [target_service_name] + aliases
                    
                    for term in search_terms:
                        field_queries.extend([
                            f'service_name:"{term}"',
                            f'effect:"{term}"',
                            f'symptom:"{term}"',
                            f'root_cause:"{term}"',
                            f'incident_repair:"{term}"',
                            f'repair_notice:"{term}"'
                        ])
                    
                    enhanced_query = f'({" OR ".join(field_queries)})'
                    if expanded_query != target_service_name:
                        enhanced_query += f" AND ({expanded_query})"
                else:
                    # 일반적인 서비스명 검색
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
                    "error_time": result.get("error_time", 0) if result.get("error_time") is not None else 0,
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
                    "score": result.get("@search.score", 0) if result.get("@search.score") is not None else 0.0,
                    "reranker_score": result.get("@search.reranker_score", 0) if result.get("@search.reranker_score") is not None else 0.0
                })
            
            processing_mode = "정확성 우선 + 일반용어 전체필드" if is_common_service and query_type in ['repair', 'cause'] else \
                             "포괄성 우선 + 일반용어 전체필드" if is_common_service else \
                             "정확성 우선" if query_type in ['repair', 'cause'] else "포괄성 우선"
            
            st.info(f"쿼리 타입별 적응형 문서 선별 중... ({processing_mode} 최적화)")
            
            # 쿼리 타입별 적응형 필터링 적용
            if query_type in ['repair', 'cause']:
                filtered_documents = self.advanced_filter_documents_for_accuracy(documents, query_type, query, target_service_name)
            else:
                filtered_documents = self.simple_filter_documents_for_coverage(documents, query_type, query, target_service_name)
            
            return filtered_documents
            
        except Exception as e:
            st.warning(f"시맨틱 검색 실패, 일반 검색으로 대체: {str(e)}")
            return self.search_documents_with_service_filter(query, target_service_name, query_type, top_k//2)

    def search_documents_with_service_filter(self, query, target_service_name=None, query_type="default", top_k=15):
        """서비스명 필터링을 지원하는 일반 검색 (fallback용) - 오류 처리 강화 + 일반용어 서비스명 예외처리"""
        try:
            # 일반 용어 서비스명 확인 및 처리
            if target_service_name:
                is_common, _ = self.is_common_term_service(target_service_name)
                
                if is_common:
                    # 일반 용어 서비스명: 모든 필드에서 검색
                    aliases = self.COMMON_TERM_SERVICES.get(target_service_name, [])
                    search_terms = [target_service_name] + aliases
                    
                    field_queries = []
                    for term in search_terms:
                        field_queries.extend([
                            f'service_name:"{term}"',
                            f'effect:"{term}"',
                            f'symptom:"{term}"',
                            f'root_cause:"{term}"',
                            f'incident_repair:"{term}"'
                        ])
                    
                    enhanced_query = f'({" OR ".join(field_queries)}) AND ({query})'
                else:
                    # 일반적인 서비스명 검색
                    enhanced_query = f'(service_name:"{target_service_name}" OR service_name:*{target_service_name}*) AND ({query})'
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
                documents.append({
                    "incident_id": result.get("incident_id", ""),
                    "service_name": result.get("service_name", ""),
                    "error_time": result.get("error_time", 0) if result.get("error_time") is not None else 0,
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
                    "score": result.get("@search.score", 0) if result.get("@search.score") is not None else 0.0,
                    "reranker_score": result.get("@search.reranker_score", 0) if result.get("@search.reranker_score") is not None else 0.0
                })
            
            # 쿼리 타입별 적응형 필터링 적용
            if query_type in ['repair', 'cause']:
                filtered_documents = self.advanced_filter_documents_for_accuracy(documents, query_type, query, target_service_name)
            else:
                filtered_documents = self.simple_filter_documents_for_coverage(documents, query_type, query, target_service_name)
            
            return filtered_documents
            
        except Exception as e:
            st.error(f"일반 검색 실패: {str(e)}")
            return []

    def search_documents_fallback(self, query, target_service_name=None, top_k=25):
        """매우 관대한 기준의 대체 검색 - 오류 처리 강화 + 일반용어 서비스명 예외처리"""
        try:
            fallback_thresholds = {
                'search_threshold': 0.05,
                'reranker_threshold': 0.5,
                'hybrid_threshold': 0.1,
                'semantic_threshold': 0.05,
                'max_results': 15
            }
            
            if target_service_name:
                is_common, _ = self.is_common_term_service(target_service_name)
                
                if is_common:
                    # 일반 용어 서비스명: 단순 포함 검색
                    search_query = f'*{target_service_name}*'
                else:
                    # 일반적인 서비스명 검색
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
                score = score if score is not None else 0.0
                
                if score >= fallback_thresholds['search_threshold']:
                    doc = {
                        "incident_id": result.get("incident_id", ""),
                        "service_name": result.get("service_name", ""),
                        "error_time": result.get("error_time", 0) if result.get("error_time") is not None else 0,
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
                        "reranker_score": result.get("@search.reranker_score", 0) if result.get("@search.reranker_score") is not None else 0.0,
                        "final_score": score,
                        "quality_tier": "Basic",
                        "filter_reason": f"대체 검색 (관대한 기준, 점수: {score:.2f})",
                        "service_match_type": "fallback"
                    }
                    documents.append(doc)
            
            documents.sort(key=lambda x: x.get('final_score', 0) or 0, reverse=True)
            
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