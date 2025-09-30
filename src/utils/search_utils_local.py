import streamlit as st
import re
from config.settings_local import AppConfigLocal

class SearchManagerLocal:
    """검색 관련 기능 관리 클래스 - 통계 정확성 강화"""
    
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
    
    NEGATIVE_KEYWORDS = {
        'repair': {
            'strong': ['통계', '건수', '현황', '분석', '몇건', '개수', '이', '전체', '연도별', '월별'],
            'weak': ['시간대별', '요일별', '부서별', '등급별']
        },
        'cause': {
            'strong': ['복구방법', '해결방법', '조치방법', '대응방법', '복구절차'],
            'weak': ['통계', '건수', '현황', '분석']
        },
        'similar': {
            'strong': ['건수', '통계', '현황', '분석', '개수', '이'],
            'weak': ['연도별', '월별', '시간대별']
        },
        'default': {'strong': [], 'weak': []}
    }
    
    INCIDENT_GRADE_KEYWORDS = {
        '1등급': ['1등급', '1급', '최고등급', '최고심각도', '1grade'],
        '2등급': ['2등급', '2급', '2grade'],
        '3등급': ['3등급', '3급', '3grade'],
        '4등급': ['4등급', '4급', '최저등급', '4grade'],
        '등급': ['등급', '장애등급', '전파등급', 'grade', '심각도']
    }
    
    def __init__(self, search_client, config=None):
        self.search_client = search_client
        self.config = config or AppConfigLocal()
        self._service_names_cache = None
        self._cache_loaded = False
        self._effect_patterns_cache = None
        self._effect_cache_loaded = False
        self.debug_mode = False
    
    def extract_incident_grade_from_query(self, query):
        """쿼리에서 장애등급 정보 추출"""
        grade_info = {'has_grade_query': False, 'specific_grade': None, 'grade_keywords': []}
        query_lower = query.lower()
        
        grade_general_keywords = ['등급', '장애등급', '전파등급', 'grade', '심각도']
        if any(k in query_lower for k in grade_general_keywords):
            grade_info['has_grade_query'] = True
            grade_info['grade_keywords'].extend([k for k in grade_general_keywords if k in query_lower])
        
        for pattern in [r'(\d+)등급', r'(\d+)급', r'(\d+)grade', r'등급.*?(\d+)', r'(\d+).*?등급']:
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
            return grade_query if not cleaned_query or len(cleaned_query.strip()) < 2 else f'({grade_query}) AND ({cleaned_query})'
        
        return query
    
    def filter_documents_by_grade(self, documents, grade_info):
        """장애등급 기반 문서 필터링"""
        if not grade_info['has_grade_query']:
            return documents
        
        filtered_docs = []
        for doc in documents:
            doc_grade = doc.get('incident_grade', '').strip()
            
            if grade_info['specific_grade']:
                if doc_grade == grade_info['specific_grade']:
                    doc['grade_match_type'] = 'exact'
                    filtered_docs.append(doc)
            elif doc_grade:
                doc['grade_match_type'] = 'general'
                filtered_docs.append(doc)
        
        grade_order = {'1등급': 1, '2등급': 2, '3등급': 3, '4등급': 4}
        filtered_docs.sort(key=lambda d: next((v for k, v in grade_order.items() if k in d.get('incident_grade', '')), 999))
        return filtered_docs
    
    def check_negative_keywords(self, text, query_type):
        """텍스트에 네거티브 키워드가 포함되어 있는지 확인"""
        if not text or query_type not in self.NEGATIVE_KEYWORDS:
            return {'has_strong': False, 'has_weak': False, 'strong_keywords': [], 'weak_keywords': []}
        
        text_lower = text.lower()
        keywords = self.NEGATIVE_KEYWORDS[query_type]
        strong_found = [k for k in keywords['strong'] if k in text_lower]
        weak_found = [k for k in keywords['weak'] if k in text_lower]
        
        return {
            'has_strong': len(strong_found) > 0,
            'has_weak': len(weak_found) > 0,
            'strong_keywords': strong_found,
            'weak_keywords': weak_found
        }
    
    def filter_documents_by_time_conditions(self, documents, time_conditions):
        """시간 조건에 따른 문서 필터링"""
        if not time_conditions or not time_conditions.get('is_time_query'):
            return documents
        
        filtered_docs = []
        for doc in documents:
            if doc is None:
                continue
            
            should_include = True
            
            # 연도 필터링
            if time_conditions.get('year') and should_include:
                required_year = time_conditions['year']
                doc_year = str(doc.get('year', '')).strip()
                if not doc_year and doc.get('error_date'):
                    error_date = str(doc.get('error_date')).strip()
                    if len(error_date) >= 4 and error_date[:4].isdigit():
                        doc_year = error_date[:4]
                should_include = doc_year == required_year
            
            # 월 필터링
            if time_conditions.get('month') and should_include:
                required_month = time_conditions['month']
                doc_month = str(doc.get('month', '')).strip()
                try:
                    month_num = int(doc_month)
                    doc_month = str(month_num) if 1 <= month_num <= 12 else None
                except (ValueError, TypeError):
                    if doc.get('error_date'):
                        parts = str(doc.get('error_date')).strip().split('-')
                        if len(parts) >= 2 and parts[1].isdigit():
                            month_num = int(parts[1])
                            doc_month = str(month_num) if 1 <= month_num <= 12 else None
                should_include = doc_month == required_month
            
            # 시간대 필터링
            if time_conditions.get('daynight') and should_include:
                should_include = doc.get('daynight', '').strip() == time_conditions['daynight']
            
            # 요일 필터링
            if time_conditions.get('week') and should_include:
                doc_week = doc.get('week', '').strip()
                required_week = time_conditions['week']
                if required_week == '평일':
                    should_include = doc_week in ['월', '화', '수', '목', '금']
                elif required_week == '주말':
                    should_include = doc_week in ['토', '일']
                else:
                    should_include = doc_week == required_week
            
            if should_include:
                filtered_docs.append(doc)
        
        return filtered_docs
    
    def filter_documents_by_department_conditions(self, documents, department_conditions):
        """부서 조건에 따른 문서 필터링"""
        if not department_conditions or not department_conditions.get('is_department_query'):
            return documents
        
        if not department_conditions.get('owner_depart'):
            return documents
        
        required_dept = department_conditions['owner_depart'].lower()
        return [doc for doc in documents if doc and required_dept in doc.get('owner_depart', '').strip().lower()]

    def is_common_term_service(self, service_name):
        """일반 용어로 사용되는 서비스명인지 확인"""
        if not service_name:
            return False, None
        
        service_lower = service_name.lower().strip()
        for common_service, aliases in self.COMMON_TERM_SERVICES.items():
            if service_lower == common_service.lower() or service_lower in [a.lower() for a in aliases]:
                return True, common_service
        return False, None
    
    def get_common_term_search_patterns(self, service_name):
        """일반 용어 서비스명에 대한 검색 패턴 생성"""
        is_common, main_service = self.is_common_term_service(service_name)
        if not is_common:
            return []
        
        patterns = [f'service_name:"{main_service}"']
        aliases = self.COMMON_TERM_SERVICES.get(main_service, [])
        
        for alias in aliases:
            patterns.append(f'service_name:"{alias}"')
        
        for term in [main_service] + aliases:
            patterns.extend([f'({field}:"{term}")' for field in ['effect', 'symptom', 'root_cause', 'incident_repair', 'repair_notice']])
        
        return patterns

    def extract_query_keywords(self, query):
        """질문에서 핵심 키워드 추출 - 통계 동의어 처리 강화"""
        keywords = {'service_keywords': [], 'symptom_keywords': [], 'action_keywords': [], 'time_keywords': []}
        
        # 쿼리 정규화
        normalized_query = self._normalize_statistics_query(query)
        
        # 확장된 서비스 패턴
        service_patterns = [
            r'\b(관리자|admin)\s*(웹|web|페이지|page)', 
            r'\b(API|api)\s*(링크|link|서비스)',
            r'\b(ERP|erp)\b', 
            r'\b(마이페이지|mypage)', 
            r'\b(보험|insurance)', 
            r'\b(커뮤니티|community)',
            r'\b(블록체인|blockchain)', 
            r'\b(OTP|otp|일회용비밀번호)\b', 
            r'\b(SMS|sms|문자|단문)\b',
            r'\b(VPN|vpn|가상사설망)\b', 
            r'\b(DNS|dns|도메인)\b', 
            r'\b(SSL|ssl|https|보안)\b',
            # 추가된 패턴들
            r'\b([A-Z]{2,10})\s*(?:서비스|시스템)?\s*(?:건수|통계|현황|몇|개수)',
            r'(?:건수|통계|현황|몇|개수)\s*.*?\b([A-Z]{2,10})\b',
        ]
        
        # 확장된 증상 패턴 (통계 쿼리 맥락에서)
        symptom_patterns = [
            r'\b(로그인|login)\s*(불가|실패|안됨|오류)', 
            r'\b(접속|연결)\s*(불가|실패|안됨|오류)',
            r'\b(가입|회원가입)\s*(불가|실패|안됨)', 
            r'\b(결제|구매|주문)\s*(불가|실패|오류)',
            r'\b(응답|response)\s*(지연|늦림|없음)', 
            r'\b(페이지|page)\s*(로딩|loading)\s*(불가|실패)',
            r'\b(문자|SMS)\s*(발송|전송)\s*(불가|실패|안됨)', 
            r'\b(발송|전송|송신)\s*(불가|실패|안됨|오류)',
            r'\b(OTP|otp|일회용비밀번호)\s*(불가|실패|안됨|오류|지연)', 
            r'\b(인증|2차인증|이중인증)\s*(불가|실패|안됨|오류)',
            # 통계 관련 패턴 추가
            r'\b(장애|오류|에러|문제)\s*(?:건수|통계|현황|몇|개수)',
            r'(?:건수|통계|현황|몇|개수)\s*.*?\b(장애|오류|에러|문제)\b',
        ]
        
        for patterns, key in [(service_patterns, 'service_keywords'), (symptom_patterns, 'symptom_keywords')]:
            for pattern in patterns:
                if matches := re.findall(pattern, normalized_query, re.IGNORECASE):
                    keywords[key].extend([m if isinstance(m, str) else ' '.join(m) for m in matches])
        
        # 시간 키워드 추출 (통계 쿼리에서 중요)
        time_patterns = [
            r'\b(202[0-9]|201[0-9])년?\b',
            r'\b(\d{1,2})월\b',
            r'\b(야간|주간|밤|낮|새벽|심야|오전|오후)\b',
            r'\b(월요일|화요일|수요일|목요일|금요일|토요일|일요일|평일|주말)\b',
        ]
        
        for pattern in time_patterns:
            if matches := re.findall(pattern, normalized_query, re.IGNORECASE):
                keywords['time_keywords'].extend(matches)
        
        return keywords
    
    def calculate_keyword_relevance_score(self, query, document):
        """키워드 기반 관련성 점수 계산"""
        query_keywords = self.extract_query_keywords(query)
        doc_text = ' '.join([document.get(f, '') for f in ['service_name', 'symptom', 'effect', 'root_cause', 'incident_repair']]).lower()
        
        score = 0
        if any(k.lower() in doc_text for k in query_keywords['service_keywords']):
            score += 40
        if any(k.lower() in doc_text for k in query_keywords['symptom_keywords']):
            score += 35
        if any(k.lower() in doc_text for k in query_keywords['action_keywords']):
            score += 15
        if any(k.lower() in doc_text for k in query_keywords['time_keywords']):
            score += 10
        
        return min(score, 100)

    @st.cache_data(ttl=3600)
    def _load_effect_patterns_from_rag(_self):
        """RAG 데이터에서 effect 필드의 패턴들을 분석하여 캐시"""
        try:
            results = _self.search_client.search(
                search_text="*", top=1000,
                select=["effect", "symptom", "service_name"],
                include_total_count=True
            )
            
            effect_patterns = {}
            for result in results:
                if effect := result.get("effect", "").strip():
                    normalized_effect = _self._normalize_text_for_similarity(effect)
                    keywords = _self._extract_semantic_keywords(effect)
                    
                    for keyword in keywords:
                        if keyword not in effect_patterns:
                            effect_patterns[keyword] = []
                        effect_patterns[keyword].append({
                            'original_effect': effect,
                            'normalized_effect': normalized_effect,
                            'symptom': result.get("symptom", "").strip(),
                            'service_name': result.get("service_name", "").strip(),
                            'keywords': keywords
                        })
            
            return effect_patterns
        except:
            return {}
    
    def _normalize_text_for_similarity(self, text):
        """텍스트를 의미적 유사성 비교를 위해 정규화"""
        if not text:
            return ""
        
        normalized = re.sub(r'\s+', '', text.lower())
        
        replacements = {
            '불가능': '불가', '실패': '불가', '안됨': '불가', '되지않음': '불가', '할수없음': '불가', '불능': '불가', '에러': '불가', '장애': '불가',
            '접속': '연결', '로그인': '접속', '액세스': '접속', '진입': '접속',
            '오류': '에러', '장애': '에러', '문제': '에러', '이슈': '에러', '버그': '에러',
            '지연': '느림', '늦음': '느림', '응답없음': '느림', '타임아웃': '느림',
            '서비스': '기능', '시스템': '서비스', '플랫폼': '서비스',
            '가입': '등록', '신청': '등록', '회원가입': '등록', '회원등록': '등록',
            '결제': '구매', '구매': '결제', '주문': '결제', '거래': '결제', '구입': '결제',
            '발송': '전송', '송신': '전송', '전달': '전송', '보내기': '전송',
            'otp': 'OTP', '일회용비밀번호': 'OTP', '원타임패스워드': 'OTP',
            'api': 'API', 'sms': 'SMS', '문자': 'SMS', '단문': 'SMS',
            'vpn': 'VPN', '가상사설망': 'VPN', 'dns': 'DNS', '도메인': 'DNS'
        }
        
        for old, new in replacements.items():
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
        if any(k in query.lower() for k in ['불가', '실패', '안됨', '에러', '오류']):
            expanded_query_keywords.update(['불가', '실패', '안됨', '에러', '오류', '장애'])
        if any(k in query.lower() for k in ['발송', '전송', '문자', 'sms']):
            expanded_query_keywords.update(['발송', '전송', '송신', '문자', 'sms'])
        
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
            if '불가' in query or '실패' in query:
                synonyms.extend(['불가', '실패', '안됨', '에러', '오류'])
            if '발송' in query or '전송' in query:
                synonyms.extend(['발송', '전송', '송신'])
            
            if synonyms:
                synonym_query = query
                for synonym in synonyms:
                    if synonym not in query:
                        for old in ['불가', '실패', '발송', '전송']:
                            synonym_query = synonym_query.replace(old, synonym)
                        expanded_terms.append(f'({synonym_query})')
            
            for effect in list(similar_effects)[:5]:
                expanded_terms.append(f'(effect:"{effect}")')
            
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
            if effect:
                effect_normalized = self._normalize_text_for_similarity(effect)
                effect_similarity = self._calculate_text_similarity(query_normalized, effect_normalized)
                effect_keywords = set(self._extract_semantic_keywords(effect))
                keyword_overlap = len(query_keywords.intersection(effect_keywords))
                effect_similarity += keyword_overlap * 0.1
                max_similarity = max(max_similarity, effect_similarity)
            
            if symptom:
                symptom_normalized = self._normalize_text_for_similarity(symptom)
                symptom_similarity = self._calculate_text_similarity(query_normalized, symptom_normalized)
                max_similarity = max(max_similarity, symptom_similarity)
            
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
        try:
            results = _self.search_client.search(
                search_text="*", top=1000,
                select=["service_name"],
                include_total_count=True
            )
            
            service_names = {r.get("service_name", "").strip() for r in results if r.get("service_name", "").strip()}
            return sorted(list(service_names), key=len, reverse=True)
        except:
            return []
    
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
        inclusion_score = intersection / len(query_set) if len(query_set) > 0 else 0
        
        return jaccard_score * 0.3 + inclusion_score * 0.7
    
    def extract_service_name_from_query(self, query):
        """개선된 RAG 데이터 기반 서비스명 추출 - 통계 쿼리 동의어 처리 강화"""
        # 1. 일반 용어 서비스 우선 체크
        is_common, common_service = self.is_common_term_service(query)
        if is_common:
            return common_service
        
        # 2. 쿼리 정규화 - 통계 관련 동의어 처리
        normalized_query = self._normalize_statistics_query(query)
        
        rag_service_names = self.get_service_names_from_rag()
        if not rag_service_names:
            return self._extract_service_name_legacy(normalized_query)
        
        query_lower = normalized_query.lower()
        query_tokens = self._extract_service_tokens(normalized_query)
        if not query_tokens:
            return None
        
        candidates = []
        for service_name in rag_service_names:
            service_tokens = self._extract_service_tokens(service_name)
            if not service_tokens:
                continue
            
            # 정확한 매칭
            if service_name.lower() in query_lower:
                candidates.append((service_name, 1.0, 'exact_match'))
                continue
            
            # 정규화된 매칭
            normalized_query_clean = self._normalize_service_name(normalized_query)
            normalized_service = self._normalize_service_name(service_name)
            
            if normalized_service in normalized_query_clean or normalized_query_clean in normalized_service:
                candidates.append((service_name, 0.9, 'normalized_inclusion'))
                continue
            
            # 토큰 유사도 매칭
            similarity = self._calculate_service_similarity(query_tokens, service_tokens)
            if similarity >= 0.5:
                candidates.append((service_name, similarity, 'token_similarity'))
        
        if not candidates:
            return None
        
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    def calculate_hybrid_score(self, search_score, reranker_score):
        """검색 점수와 Reranker 점수를 조합하여 하이브리드 점수 계산"""
        search_score = search_score or 0.0
        reranker_score = reranker_score or 0.0
        
        if reranker_score > 0:
            normalized_reranker = min(reranker_score / 4.0, 1.0)
            normalized_search = min(search_score, 1.0)
            return normalized_reranker * 0.8 + normalized_search * 0.2
        
        return min(search_score, 1.0)

    def _filter_documents_common(self, documents, query_type, query_text, target_service_name, grade_info, is_accuracy_priority):
        """공통 문서 필터링 로직"""
        thresholds = self.config.get_dynamic_thresholds(query_type, query_text)
        documents = self._boost_semantic_documents(documents, query_text)
        
        if grade_info and grade_info['has_grade_query']:
            documents = self.filter_documents_by_grade(documents, grade_info)
        
        is_common_service = target_service_name and self.is_common_term_service(target_service_name)[0]
        
        filtered_docs = []
        match_priority = {'exact': 3, 'partial': 2, 'exact_common_term': 3, 'all': 1}
        
        for doc in documents:
            search_score = doc.get('score') or 0.0
            reranker_score = doc.get('reranker_score') or 0.0
            
            if search_score < thresholds['search_threshold']:
                continue
            
            # 서비스 매칭
            if target_service_name:
                doc_service_name = doc.get('service_name', '').strip()
                if is_common_service:
                    if doc_service_name.lower() != target_service_name.lower():
                        continue
                    doc['service_match_type'] = 'exact_common_term'
                else:
                    if doc_service_name.lower() == target_service_name.lower():
                        doc['service_match_type'] = 'exact'
                    elif target_service_name.lower() in doc_service_name.lower() or doc_service_name.lower() in target_service_name.lower():
                        doc['service_match_type'] = 'partial'
                    else:
                        continue
            else:
                doc['service_match_type'] = 'all'
            
            # 키워드 관련성 (정확성 우선일 때만)
            keyword_relevance = 0
            if is_accuracy_priority:
                keyword_relevance = self.calculate_keyword_relevance_score(query_text, doc)
                if keyword_relevance >= 30:
                    doc['keyword_relevance_score'] = keyword_relevance
            
            # 품질 판단
            grade_info_text = f" (등급: {doc.get('incident_grade', 'N/A')})" if grade_info and grade_info['has_grade_query'] else ""
            relevance_info = f" (키워드 관련성: {keyword_relevance}점)" if keyword_relevance >= 30 else ""
            match_desc = "정확한 일반용어" if doc.get('service_match_type') == 'exact_common_term' else doc.get('service_match_type', 'unknown')
            priority_type = "정확성 우선" if is_accuracy_priority else "포괄성 우선"
            
            if reranker_score >= thresholds['reranker_threshold']:
                doc['filter_reason'] = f"{priority_type} - {match_desc} 매칭 + Reranker 고품질 (점수: {reranker_score:.2f}){grade_info_text}{relevance_info}"
                doc['final_score'] = reranker_score
                doc['quality_tier'] = 'Premium'
                filtered_docs.append(doc)
            else:
                hybrid_score = self.calculate_hybrid_score(search_score, reranker_score)
                final_score = doc.get('final_score', hybrid_score) or 0.0
                
                if final_score >= thresholds['hybrid_threshold']:
                    doc['filter_reason'] = f"{priority_type} - {match_desc} 매칭 + 하이브리드 통과 (점수: {final_score:.2f}){grade_info_text}{relevance_info}"
                    doc['quality_tier'] = 'Standard'
                    filtered_docs.append(doc)
        
        # 정렬
        def sort_key(doc):
            semantic_boost = doc.get('semantic_similarity', 0) or 0
            keyword_boost = doc.get('keyword_relevance_score', 0) or 0 if is_accuracy_priority else 0
            final_score = doc.get('final_score', 0) or 0
            
            grade_priority = 0
            if grade_info and grade_info['has_grade_query']:
                grade = doc.get('incident_grade', '')
                grade_priority = 4 if '1등급' in grade else 3 if '2등급' in grade else 2 if '3등급' in grade else 1 if '4등급' in grade else 0
            
            return (
                grade_priority,
                match_priority.get(doc.get('service_match_type', 'all'), 0),
                final_score + semantic_boost * 0.1 + keyword_boost * 0.001
            )
        
        filtered_docs.sort(key=sort_key, reverse=True)
        return filtered_docs[:thresholds['max_results']]

    def advanced_filter_documents_for_accuracy(self, documents, query_type="default", query_text="", target_service_name=None, grade_info=None):
        """정확성 우선 필터링 - repair/cause용"""
        return self._filter_documents_common(documents, query_type, query_text, target_service_name, grade_info, True)

    def simple_filter_documents_for_coverage(self, documents, query_type="default", query_text="", target_service_name=None, grade_info=None):
        """포괄성 우선 필터링 - similar/default용"""
        return self._filter_documents_common(documents, query_type, query_text, target_service_name, grade_info, False)

    def semantic_search_with_adaptive_filtering(self, query, target_service_name=None, query_type="default", top_k=50):
        """시맨틱 검색 - 월 조건 검색 쿼리 강화 및 통계 쿼리 통합"""
        try:
            print(f"DEBUG: ========== SEARCH START ==========")
            print(f"DEBUG: Query: '{query}', Target service: {target_service_name}, Query type: {query_type}")
            
            grade_info = self.extract_incident_grade_from_query(query)
            time_info = self._extract_year_month_from_query_unified(query)
            
            print(f"DEBUG: Unified time info: {time_info}, Grade info: {grade_info}")
            
            expanded_query = self._expand_query_with_semantic_similarity(query)
            print(f"DEBUG: Expanded query: '{expanded_query}'")
            
            if grade_info['has_grade_query']:
                expanded_query = self.build_grade_search_query(expanded_query, grade_info)
                print(f"DEBUG: Query with grade filter: '{expanded_query}'")
            
            # 개선된 통합 시간 조건 처리
            enhanced_query = expanded_query
            if time_info['year'] or time_info['months']:
                time_conditions = []
                
                if time_info['year']:
                    time_conditions.append(f'(year:"{time_info["year"]}" OR error_date:{time_info["year"]}-*)')
                    print(f"DEBUG: Year condition added for {time_info['year']}")
                
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
                    print(f"DEBUG: Unified months condition added: {time_info['months']}")
                
                if time_conditions:
                    time_filter = " AND ".join(time_conditions)
                    enhanced_query = f'({expanded_query}) AND {time_filter}' if expanded_query.strip() else time_filter
                    print(f"DEBUG: Final enhanced query with time filter: '{enhanced_query}'")
            
            # 서비스명 조건
            if target_service_name:
                is_common = self.is_common_term_service(target_service_name)[0]
                service_query = f'service_name:"{target_service_name}"' if is_common else f'(service_name:"{target_service_name}" OR service_name:*{target_service_name}*)'
                enhanced_query = f'{service_query} AND ({enhanced_query})' if enhanced_query != target_service_name else f'{service_query} AND (*)'
            
            print(f"DEBUG: Final search query: '{enhanced_query}'")
            
            top_k = max(top_k, 80 if query_type in ['repair', 'cause'] else 30)
            print(f"DEBUG: Executing Azure search with top_k={top_k}")
            
            results = self.search_client.search(
                search_text=enhanced_query,
                top=top_k,
                query_type="semantic",
                semantic_configuration_name="iap-incident-rebuild-meaning",
                include_total_count=True,
                select=["incident_id", "service_name", "error_time", "effect", "symptom", "repair_notice", 
                       "error_date", "week", "daynight", "root_cause", "incident_repair", "incident_plan",
                       "cause_type", "done_type", "incident_grade", "owner_depart", "year", "month"]
            )
            
            documents = []
            print(f"DEBUG: ========== SEARCH RESULTS ==========")
            
            for i, result in enumerate(results):
                if i < 5:
                    print(f"DEBUG: Result {i+1}: ID={result.get('incident_id')}, error_date={result.get('error_date')}, year={result.get('year')}, month={result.get('month')}, score={result.get('@search.score')}")
                
                error_time = self._parse_error_time(result.get("error_time", 0))
                
                documents.append({
                    "incident_id": result.get("incident_id", ""),
                    "service_name": result.get("service_name", ""),
                    "error_time": error_time,
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
                    "score": result.get("@search.score") or 0.0,
                    "reranker_score": result.get("@search.reranker_score") or 0.0
                })
            
            print(f"DEBUG: Total search results: {len(documents)}")
            
            if query_type in ['repair', 'cause']:
                filtered_documents = self.advanced_filter_documents_for_accuracy(documents, query_type, query, target_service_name, grade_info)
            else:
                filtered_documents = self.simple_filter_documents_for_coverage(documents, query_type, query, target_service_name, grade_info)
            
            print(f"DEBUG: After filtering: {len(filtered_documents)}")
            print(f"DEBUG: ========== SEARCH END ==========")
            
            return filtered_documents
            
        except Exception as e:
            print(f"DEBUG: Search error: {e}")
            return self.search_documents_with_service_filter(query, target_service_name, query_type, top_k//2)

    def _extract_year_month_from_query_unified(self, query):
        """통합된 연도와 월 조건 추출 - 범위와 개별 월을 동일하게 처리"""
        time_info = {'year': None, 'months': []}
        if not query:
            return time_info
        
        print(f"DEBUG: Unified time extraction from query: '{query}'")
        
        # 연도 추출
        for pattern in [r'\b(\d{4})년\b', r'\b(\d{4})\s*년도\b', r'\b(\d{4})년도\b']:
            if matches := re.findall(pattern, query, re.IGNORECASE):
                time_info['year'] = matches[-1]
                print(f"DEBUG: Extracted year: {time_info['year']}")
                break
        
        # 모든 월 관련 패턴을 통합
        months_set = set()
        
        # 월 범위 패턴
        for pattern in [r'\b(\d+)\s*~\s*(\d+)월\b', r'\b(\d+)월\s*~\s*(\d+)월\b', r'\b(\d+)\s*-\s*(\d+)월\b', r'\b(\d+)월\s*-\s*(\d+)월\b']:
            if matches := re.findall(pattern, query, re.IGNORECASE):
                for match in matches:
                    start_month, end_month = int(match[0]), int(match[1])
                    if 1 <= start_month <= 12 and 1 <= end_month <= 12 and start_month <= end_month:
                        months_set.update(range(start_month, end_month + 1))
                        print(f"DEBUG: Added month range {start_month}~{end_month}")
        
        # 개별 월 및 콤마로 구분된 월
        if comma_matches := re.findall(r'(\d{1,2})월', query):
            for match in comma_matches:
                month_num = int(match)
                if 1 <= month_num <= 12:
                    months_set.add(month_num)
                    print(f"DEBUG: Added month {month_num}")
        
        time_info['months'] = sorted(list(months_set))
        print(f"DEBUG: Final unified time info: year={time_info['year']}, months={time_info['months']}")
        
        return time_info

    def _parse_error_time(self, error_time_raw):
        """error_time 파싱 헬퍼"""
        try:
            if error_time_raw is None:
                return 0
            if isinstance(error_time_raw, str):
                return int(float(error_time_raw.strip())) if error_time_raw.strip() else 0
            return int(error_time_raw)
        except (ValueError, TypeError):
            return 0

    def search_documents_with_service_filter(self, query, target_service_name=None, query_type="default", top_k=15):
        """서비스명 필터링을 지원하는 일반 검색 (fallback용)"""
        try:
            grade_info = self.extract_incident_grade_from_query(query)
            time_info = self._extract_year_month_from_query_unified(query)
            
            enhanced_query = self.build_grade_search_query(query, grade_info) if grade_info['has_grade_query'] else query
            
            if time_info['year'] or time_info['months']:
                time_conditions = []
                if time_info['year']:
                    time_conditions.append(f'(year:"{time_info["year"]}" OR error_date:{time_info["year"]}*)')
                if time_info['months']:
                    month_conditions = [f'month:"{m}"' for m in time_info['months']]
                    time_conditions.append(f'({" OR ".join(month_conditions)})')
                if time_conditions:
                    enhanced_query = f'({enhanced_query}) AND {" AND ".join(time_conditions)}'
            
            if target_service_name:
                is_common = self.is_common_term_service(target_service_name)[0]
                service_prefix = f'service_name:"{target_service_name}"' if is_common else f'(service_name:"{target_service_name}" OR service_name:*{target_service_name}*)'
                enhanced_query = f'{service_prefix} AND ({enhanced_query})'
            
            results = self.search_client.search(
                search_text=enhanced_query, top=top_k, include_total_count=True,
                select=["incident_id", "service_name", "error_time", "effect", "symptom", "repair_notice",
                       "error_date", "week", "daynight", "root_cause", "incident_repair", "incident_plan",
                       "cause_type", "done_type", "incident_grade", "owner_depart", "year", "month"]
            )
            
            documents = [{
                **{k: result.get(k, "") for k in ["incident_id", "service_name", "effect", "symptom", "repair_notice",
                                                    "error_date", "week", "daynight", "root_cause", "incident_repair",
                                                    "incident_plan", "cause_type", "done_type", "incident_grade",
                                                    "owner_depart", "year", "month"]},
                "error_time": self._parse_error_time(result.get("error_time", 0)),
                "score": result.get("@search.score") or 0.0,
                "reranker_score": result.get("@search.reranker_score") or 0.0
            } for result in results]
            
            return self.advanced_filter_documents_for_accuracy(documents, query_type, query, target_service_name, grade_info) if query_type in ['repair', 'cause'] else self.simple_filter_documents_for_coverage(documents, query_type, query, target_service_name, grade_info)
        except:
            return []

    def search_documents_fallback(self, query, target_service_name=None, top_k=25):
        """매우 관대한 기준의 대체 검색"""
        try:
            grade_info = self.extract_incident_grade_from_query(query)
            fallback_thresholds = {
                'search_threshold': 0.05, 'reranker_threshold': 0.5,
                'hybrid_threshold': 0.1, 'semantic_threshold': 0.05, 'max_results': 15
            }
            
            if target_service_name:
                is_common = self.is_common_term_service(target_service_name)[0]
                search_query = f'service_name:*{target_service_name}*'
            else:
                search_query = query
            
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
                if score >= fallback_thresholds['search_threshold']:
                    doc = {
                        **{k: result.get(k, "") for k in ["incident_id", "service_name", "effect", "symptom", "repair_notice",
                                                           "error_date", "week", "daynight", "root_cause", "incident_repair",
                                                           "incident_plan", "cause_type", "done_type", "incident_grade",
                                                           "owner_depart", "year", "month"]},
                        "error_time": self._parse_error_time(result.get("error_time", 0)),
                        "score": score,
                        "reranker_score": result.get("@search.reranker_score") or 0.0,
                        "final_score": score,
                        "quality_tier": "Basic",
                        "filter_reason": f"대체 검색 (관대한 기준, 점수: {score:.2f})",
                        "service_match_type": "fallback"
                    }
                    
                    if grade_info['has_grade_query']:
                        doc_grade = result.get("incident_grade", "")
                        if grade_info['specific_grade'] and doc_grade == grade_info['specific_grade']:
                            doc['grade_match_type'] = 'exact'
                            doc['filter_reason'] += f" (등급: {doc_grade})"
                        elif doc_grade:
                            doc['grade_match_type'] = 'general'
                            doc['filter_reason'] += f" (등급: {doc_grade})"
                    
                    documents.append(doc)
            
            if grade_info['has_grade_query']:
                documents = self.filter_documents_by_grade(documents, grade_info)
            
            documents.sort(key=lambda x: x.get('final_score', 0) or 0, reverse=True)
            return documents[:fallback_thresholds['max_results']]
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
        
        # 통계 관련 동의어 정규화
        statistics_synonyms = {
            '장애건수': '건수',
            '장애 건수': '건수',
            '발생건수': '건수',
            '몇건이야': '몇건',
            '몇건이니': '몇건', 
            '몇건인가': '몇건',
            '몇건이나': '몇건',
            '알려줘': '',  # 제거하여 서비스명 추출에 방해되지 않도록
            '보여줘': '',
            '말해줘': '',
            '확인해줘': '',
            '발생했어': '발생',
            '발생했나': '발생',
            '있어': '있음',
            '있나': '있음',
            '얼마나': '몇',
            '어느정도': '몇',
            '어떻게': '몇',
        }
        
        normalized = query
        for old_term, new_term in statistics_synonyms.items():
            normalized = normalized.replace(old_term, new_term)
        
        # 연속된 공백 정리
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized    