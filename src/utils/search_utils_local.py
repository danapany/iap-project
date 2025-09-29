import streamlit as st
import re
from config.settings_local import AppConfigLocal

class SearchManagerLocal:
    """검색 관련 기능 관리 클래스 - 통계 정확성 강화"""
    
    # 일반적인 용어로 사용되는 서비스명들
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
    
    # 네거티브 키워드 시스템
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
        'default': {
            'strong': [],
            'weak': []
        }
    }
    
    # 장애등급 관련 키워드
    INCIDENT_GRADE_KEYWORDS = {
        '1등급': ['1등급', '1급', '최고등급', '최고심각도', '1grade'],
        '2등급': ['2등급', '2급', '2grade'],
        '3등급': ['3등급', '3급', '3grade'],
        '4등급': ['4등급', '4급', '최저등급', '4grade'],
        '등급': ['등급', '장애등급', '전파등급', 'grade', '심각도']
    }
    
    def __init__(self, search_client, config=None):
        self.search_client = search_client
        self.config = config if config else AppConfigLocal()
        self._service_names_cache = None
        self._cache_loaded = False
        self._effect_patterns_cache = None
        self._effect_cache_loaded = False
        self.debug_mode = False
    
    def extract_incident_grade_from_query(self, query):
        """쿼리에서 장애등급 정보 추출"""
        grade_info = {
            'has_grade_query': False,
            'specific_grade': None,
            'grade_keywords': []
        }
        
        query_lower = query.lower()
        
        grade_general_keywords = ['등급', '장애등급', '전파등급', 'grade', '심각도']
        if any(keyword in query_lower for keyword in grade_general_keywords):
            grade_info['has_grade_query'] = True
            grade_info['grade_keywords'].extend([k for k in grade_general_keywords if k in query_lower])
        
        grade_patterns = [
            r'(\d+)등급',
            r'(\d+)급',
            r'(\d+)grade',
            r'등급.*?(\d+)',
            r'(\d+).*?등급'
        ]
        
        for pattern in grade_patterns:
            matches = re.findall(pattern, query_lower)
            if matches:
                grade_number = matches[0]
                grade_info['specific_grade'] = f"{grade_number}등급"
                grade_info['has_grade_query'] = True
                grade_info['grade_keywords'].append(f"{grade_number}등급")
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
            
            if not cleaned_query or len(cleaned_query.strip()) < 2:
                enhanced_query = grade_query
            else:
                enhanced_query = f'({grade_query}) AND ({cleaned_query})'
        else:
            enhanced_query = query
        
        return enhanced_query
    
    def filter_documents_by_grade(self, documents, grade_info):
        """장애등급 기반 문서 필터링"""
        if not grade_info['has_grade_query']:
            return documents
        
        filtered_docs = []
        filter_stats = {
            'total': len(documents),
            'grade_matched': 0,
            'grade_filtered': 0
        }
        
        for doc in documents:
            doc_grade = doc.get('incident_grade', '').strip()
            
            if grade_info['specific_grade']:
                if doc_grade == grade_info['specific_grade']:
                    filter_stats['grade_matched'] += 1
                    filtered_docs.append(doc)
                    doc['grade_match_type'] = 'exact'
                else:
                    filter_stats['grade_filtered'] += 1
                    continue
            else:
                if doc_grade:
                    filter_stats['grade_matched'] += 1
                    filtered_docs.append(doc)
                    doc['grade_match_type'] = 'general'
                else:
                    filter_stats['grade_filtered'] += 1
                    continue
        
        def grade_sort_key(doc):
            grade = doc.get('incident_grade', '')
            if '1등급' in grade:
                return 1
            elif '2등급' in grade:
                return 2
            elif '3등급' in grade:
                return 3
            elif '4등급' in grade:
                return 4
            else:
                return 999
        
        filtered_docs.sort(key=grade_sort_key)
        return filtered_docs
    
    def check_negative_keywords(self, text, query_type):
        """텍스트에 네거티브 키워드가 포함되어 있는지 확인"""
        if not text or query_type not in self.NEGATIVE_KEYWORDS:
            return {'has_strong': False, 'has_weak': False, 'strong_keywords': [], 'weak_keywords': []}
        
        text_lower = text.lower()
        keywords = self.NEGATIVE_KEYWORDS[query_type]
        
        strong_found = []
        weak_found = []
        
        for keyword in keywords['strong']:
            if keyword in text_lower:
                strong_found.append(keyword)
        
        for keyword in keywords['weak']:
            if keyword in text_lower:
                weak_found.append(keyword)
        
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
        filter_stats = {
            'total': len(documents),
            'year_filtered': 0,
            'month_filtered': 0,
            'daynight_filtered': 0,
            'week_filtered': 0,
            'final_count': 0,
            'excluded_year': 0,
            'excluded_month': 0,
            'excluded_daynight': 0,
            'excluded_week': 0
        }
        
        for doc in documents:
            if doc is None:
                continue
                
            should_include = True
            
            # 연도 필터링
            if time_conditions.get('year'):
                required_year = time_conditions['year']
                doc_year = None
                
                if doc.get('year'):
                    doc_year = str(doc.get('year')).strip()
                
                if not doc_year and doc.get('error_date'):
                    error_date = str(doc.get('error_date')).strip()
                    if len(error_date) >= 4 and error_date[:4].isdigit():
                        doc_year = error_date[:4]
                
                if not doc_year or doc_year != required_year:
                    should_include = False
                    filter_stats['excluded_year'] += 1
                    continue
                else:
                    filter_stats['year_filtered'] += 1
            
            # 월 필터링
            if time_conditions.get('month') and should_include:
                required_month = time_conditions['month']
                doc_month = None
                
                if doc.get('month'):
                    month_val = str(doc.get('month')).strip()
                    try:
                        month_num = int(month_val)
                        if 1 <= month_num <= 12:
                            doc_month = str(month_num)
                    except (ValueError, TypeError):
                        pass
                
                if not doc_month and doc.get('error_date'):
                    error_date = str(doc.get('error_date')).strip()
                    parts = error_date.split('-')
                    if len(parts) >= 2 and parts[1].isdigit():
                        try:
                            month_num = int(parts[1])
                            if 1 <= month_num <= 12:
                                doc_month = str(month_num)
                        except (ValueError, TypeError):
                            pass
                
                if not doc_month or doc_month != required_month:
                    should_include = False
                    filter_stats['excluded_month'] += 1
                    continue
                else:
                    filter_stats['month_filtered'] += 1
            
            # 시간대 필터링
            if time_conditions.get('daynight') and should_include:
                doc_daynight = doc.get('daynight', '').strip()
                required_daynight = time_conditions['daynight']
                
                if not doc_daynight:
                    should_include = False
                    filter_stats['excluded_daynight'] += 1
                    continue
                elif doc_daynight != required_daynight:
                    should_include = False
                    filter_stats['excluded_daynight'] += 1
                    continue
                else:
                    filter_stats['daynight_filtered'] += 1
            
            # 요일 필터링
            if time_conditions.get('week') and should_include:
                doc_week = doc.get('week', '').strip()
                required_week = time_conditions['week']
                
                if required_week == '평일':
                    if doc_week not in ['월', '화', '수', '목', '금']:
                        should_include = False
                        filter_stats['excluded_week'] += 1
                        continue
                elif required_week == '주말':
                    if doc_week not in ['토', '일']:
                        should_include = False
                        filter_stats['excluded_week'] += 1
                        continue
                else:
                    if not doc_week:
                        should_include = False
                        filter_stats['excluded_week'] += 1
                        continue
                    elif doc_week != required_week:
                        should_include = False
                        filter_stats['excluded_week'] += 1
                        continue
                
                filter_stats['week_filtered'] += 1
            
            if should_include:
                filtered_docs.append(doc)
                filter_stats['final_count'] += 1
        
        if self.debug_mode:
            print(f"Time filtering stats: {filter_stats}")
        
        return filtered_docs
    
    def filter_documents_by_department_conditions(self, documents, department_conditions):
        """부서 조건에 따른 문서 필터링"""
        if not department_conditions or not department_conditions.get('is_department_query'):
            return documents
        
        filtered_docs = []
        filter_stats = {
            'total': len(documents),
            'department_filtered': 0,
            'final_count': 0
        }
        
        for doc in documents:
            if doc is None:
                continue
                
            if department_conditions.get('owner_depart'):
                doc_owner_depart = doc.get('owner_depart', '').strip()
                required_department = department_conditions['owner_depart']
                
                if not doc_owner_depart or required_department.lower() not in doc_owner_depart.lower():
                    continue
                filter_stats['department_filtered'] += 1
            
            filtered_docs.append(doc)
            filter_stats['final_count'] += 1
        
        return filtered_docs

    def is_common_term_service(self, service_name):
        """일반 용어로 사용되는 서비스명인지 확인"""
        if not service_name:
            return False, None
        
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
        
        patterns.append(f'service_name:"{main_service}"')
        
        for alias in aliases:
            patterns.append(f'service_name:"{alias}"')
        
        for term in [main_service] + aliases:
            patterns.extend([
                f'(effect:"{term}")',
                f'(symptom:"{term}")',
                f'(root_cause:"{term}")',
                f'(incident_repair:"{term}")',
                f'(repair_notice:"{term}")'
            ])
        
        return patterns

    def extract_query_keywords(self, query):
        """질문에서 핵심 키워드 추출"""
        keywords = {
            'service_keywords': [],
            'symptom_keywords': [],
            'action_keywords': [],
            'time_keywords': []
        }
        
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
            r'\b(SSL|ssl|https|보안)\b'
        ]
        
        for pattern in service_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                keywords['service_keywords'].extend([match if isinstance(match, str) else ' '.join(match) for match in matches])
        
        symptom_patterns = [
            r'\b(로그인|login)\s*(불가|실패|안됨|오류)',
            r'\b(접속|연결)\s*(불가|실패|안됨|오류)',
            r'\b(가입|회원가입)\s*(불가|실패|안됨)',
            r'\b(결제|구매|주문)\s*(불가|실패|오류)',
            r'\b(응답|response)\s*(지연|느림|없음)',
            r'\b(페이지|page)\s*(로딩|loading)\s*(불가|실패)',
            r'\b(문자|SMS)\s*(발송|전송)\s*(불가|실패|안됨)',
            r'\b(발송|전송|송신)\s*(불가|실패|안됨|오류)',
            r'\b(OTP|otp|일회용비밀번호)\s*(불가|실패|안됨|오류|지연)',
            r'\b(인증|2차인증|이중인증)\s*(불가|실패|안됨|오류)'
        ]
        
        for pattern in symptom_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                keywords['symptom_keywords'].extend([match if isinstance(match, str) else ' '.join(match) for match in matches])
        
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
        
        time_patterns = [
            r'\b(\d{4})년',
            r'\b(\d{1,2})월',
            r'\b(야간|주간|오전|오후)',
            r'\b(월요일|화요일|수요일|목요일|금요일|토요일|일요일|평일|주말)',
            r'\b(최근|recent|어제|오늘)'
        ]
        
        for pattern in time_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                keywords['time_keywords'].extend(matches)
        
        return keywords
    
    def calculate_keyword_relevance_score(self, query, document):
        """키워드 기반 관련성 점수 계산"""
        query_keywords = self.extract_query_keywords(query)
        score = 0
        max_score = 100
        
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
        """텍스트를 의미적 유사성 비교를 위해 정규화"""
        if not text:
            return ""
        
        normalized = re.sub(r'\s+', '', text.lower())
        
        replacements = {
            '불가능': '불가', '실패': '불가', '안됨': '불가', '되지않음': '불가', 
            '할수없음': '불가', '불능': '불가', '에러': '불가', '장애': '불가',
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
            r'(\w+)(불가|실패|에러|오류|지연|느림)',
            r'(\w+)(가입|등록|신청)',
            r'(\w+)(결제|구매|주문)',
            r'(\w+)(접속|연결|로그인)',
            r'(\w+)(조회|검색|확인)',
            r'(\w+)(발송|전송|송신)',
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
        
        query_keywords = self._extract_semantic_keywords(query)
        query_normalized = self._normalize_text_for_similarity(query)
        
        similar_effects = set()
        semantic_expansions = set()
        
        expanded_query_keywords = set(query_keywords)
        
        if any(keyword in query.lower() for keyword in ['불가', '실패', '안됨', '에러', '오류']):
            expanded_query_keywords.update(['불가', '실패', '안됨', '에러', '오류', '장애'])
        
        if any(keyword in query.lower() for keyword in ['발송', '전송', '문자', 'sms']):
            expanded_query_keywords.update(['발송', '전송', '송신', '문자', 'sms'])
        
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
                    
                    if similarity > 0.2:
                        similar_effects.add(pattern_info['original_effect'])
                        semantic_expansions.update(pattern_info['keywords'])
        
        if similar_effects or semantic_expansions:
            expanded_terms = []
            expanded_terms.append(f'({query})')
            
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
        normalized = re.sub(r'\s+', ' ', normalized).strip().lower()
        
        return normalized
    
    def _extract_service_tokens(self, service_name):
        """서비스명에서 의미있는 토큰들을 추출"""
        if not service_name:
            return []
        
        tokens = re.findall(r'[A-Za-z가-힣0-9]+', service_name)
        valid_tokens = [token.lower() for token in tokens if len(token) >= 2]
        
        return valid_tokens
    
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
        
        final_score = (jaccard_score * 0.3) + (inclusion_score * 0.7)
        
        return final_score
    
    def extract_service_name_from_query(self, query):
        """개선된 RAG 데이터 기반 서비스명 추출"""
        is_common, common_service = self.is_common_term_service(query)
        if is_common:
            return common_service
        
        rag_service_names = self.get_service_names_from_rag()
        
        if not rag_service_names:
            return self._extract_service_name_legacy(query)
        
        query_lower = query.lower()
        query_tokens = self._extract_service_tokens(query)
        
        if not query_tokens:
            return None
        
        candidates = []
        
        for service_name in rag_service_names:
            service_tokens = self._extract_service_tokens(service_name)
            
            if not service_tokens:
                continue
            
            if service_name.lower() in query_lower:
                candidates.append((service_name, 1.0, 'exact_match'))
                continue
            
            normalized_query = self._normalize_service_name(query)
            normalized_service = self._normalize_service_name(service_name)
            
            if normalized_service in normalized_query or normalized_query in normalized_service:
                candidates.append((service_name, 0.9, 'normalized_inclusion'))
                continue
            
            similarity = self._calculate_service_similarity(query_tokens, service_tokens)
            
            if similarity >= 0.5:
                candidates.append((service_name, similarity, 'token_similarity'))
        
        if not candidates:
            return None
        
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_match = candidates[0]
        
        return best_match[0]

    def calculate_hybrid_score(self, search_score, reranker_score):
        """검색 점수와 Reranker 점수를 조합하여 하이브리드 점수 계산"""
        search_score = search_score if search_score is not None else 0.0
        reranker_score = reranker_score if reranker_score is not None else 0.0
        
        if reranker_score > 0:
            normalized_reranker = min(reranker_score / 4.0, 1.0)
            normalized_search = min(search_score, 1.0)
            hybrid_score = (normalized_reranker * 0.8) + (normalized_search * 0.2)
        else:
            hybrid_score = min(search_score, 1.0)
        
        return hybrid_score

    def advanced_filter_documents_for_accuracy(self, documents, query_type="default", query_text="", target_service_name=None, grade_info=None):
        """정확성 우선 필터링 - repair/cause용"""
        
        thresholds = self.config.get_dynamic_thresholds(query_type, query_text)
        documents = self._boost_semantic_documents(documents, query_text)
        
        if grade_info and grade_info['has_grade_query']:
            documents = self.filter_documents_by_grade(documents, grade_info)
        
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
            'common_term_matches': 0,
            'grade_matched': 0
        }
        
        for doc in documents:
            search_score = doc.get('score', 0) if doc.get('score') is not None else 0.0
            reranker_score = doc.get('reranker_score', 0) if doc.get('reranker_score') is not None else 0.0
            
            if 'semantic_similarity' in doc:
                filter_stats['semantic_boosted'] += 1
            
            if doc.get('grade_match_type'):
                filter_stats['grade_matched'] += 1
            
            keyword_relevance = self.calculate_keyword_relevance_score(query_text, doc)
            if keyword_relevance >= 30:
                filter_stats['keyword_relevant'] += 1
                doc['keyword_relevance_score'] = keyword_relevance
            
            if search_score < thresholds['search_threshold']:
                continue
            filter_stats['search_filtered'] += 1
            
            if target_service_name:
                doc_service_name = doc.get('service_name', '').strip()
                
                if is_common_service:
                    if doc_service_name.lower() == target_service_name.lower():
                        filter_stats['service_exact_match'] += 1
                        doc['service_match_type'] = 'exact_common_term'
                    else:
                        continue
                else:
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
            
            if reranker_score >= thresholds['reranker_threshold']:
                filter_stats['reranker_qualified'] += 1
                match_type = doc.get('service_match_type', 'unknown')
                grade_info_text = f" (등급: {doc.get('incident_grade', 'N/A')})" if grade_info and grade_info['has_grade_query'] else ""
                relevance_info = f" (키워드 관련성: {keyword_relevance}점)" if keyword_relevance >= 30 else ""
                match_desc = "정확한 일반용어" if match_type == 'exact_common_term' else match_type
                doc['filter_reason'] = f"정확성 우선 - {match_desc} 매칭 + Reranker 고품질 (점수: {reranker_score:.2f}){grade_info_text}{relevance_info}"
                doc['final_score'] = reranker_score
                doc['quality_tier'] = 'Premium'
                filtered_docs.append(doc)
                filter_stats['final_selected'] += 1
                continue
            
            hybrid_score = self.calculate_hybrid_score(search_score, reranker_score)
            final_score = doc.get('final_score', hybrid_score)
            final_score = final_score if final_score is not None else 0.0
            
            if final_score >= thresholds['hybrid_threshold']:
                filter_stats['hybrid_qualified'] += 1
                match_type = doc.get('service_match_type', 'unknown')
                grade_info_text = f" (등급: {doc.get('incident_grade', 'N/A')})" if grade_info and grade_info['has_grade_query'] else ""
                relevance_info = f" (키워드 관련성: {keyword_relevance}점)" if keyword_relevance >= 30 else ""
                match_desc = "정확한 일반용어" if match_type == 'exact_common_term' else match_type
                doc['filter_reason'] = f"정확성 우선 - {match_desc} 매칭 + 하이브리드 통과 (점수: {final_score:.2f}){grade_info_text}{relevance_info}"
                doc['quality_tier'] = 'Standard'
                filtered_docs.append(doc)
                filter_stats['final_selected'] += 1
        
        def sort_key(doc):
            match_priority = {'exact': 3, 'partial': 2, 'exact_common_term': 3, 'all': 1}
            semantic_boost = doc.get('semantic_similarity', 0) or 0
            keyword_boost = doc.get('keyword_relevance_score', 0) or 0
            final_score = doc.get('final_score', 0) or 0
            
            grade_priority = 0
            if grade_info and grade_info['has_grade_query']:
                grade = doc.get('incident_grade', '')
                if '1등급' in grade:
                    grade_priority = 4
                elif '2등급' in grade:
                    grade_priority = 3
                elif '3등급' in grade:
                    grade_priority = 2
                elif '4등급' in grade:
                    grade_priority = 1
            
            return (
                grade_priority,
                match_priority.get(doc.get('service_match_type', 'all'), 0), 
                final_score + (semantic_boost * 0.1) + (keyword_boost * 0.001)
            )
        
        filtered_docs.sort(key=sort_key, reverse=True)
        final_docs = filtered_docs[:thresholds['max_results']]
        
        return final_docs

    def simple_filter_documents_for_coverage(self, documents, query_type="default", query_text="", target_service_name=None, grade_info=None):
        """포괄성 우선 필터링 - similar/default용"""
        
        thresholds = self.config.get_dynamic_thresholds(query_type, query_text)
        documents = self._boost_semantic_documents(documents, query_text)
        
        if grade_info and grade_info['has_grade_query']:
            documents = self.filter_documents_by_grade(documents, grade_info)
        
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
            'common_term_matches': 0,
            'grade_matched': 0
        }
        
        for doc in documents:
            search_score = doc.get('score', 0) if doc.get('score') is not None else 0.0
            reranker_score = doc.get('reranker_score', 0) if doc.get('reranker_score') is not None else 0.0
            
            if 'semantic_similarity' in doc:
                filter_stats['semantic_boosted'] += 1
            
            if doc.get('grade_match_type'):
                filter_stats['grade_matched'] += 1
            
            if search_score < thresholds['search_threshold']:
                continue
            filter_stats['search_filtered'] += 1
            
            if target_service_name:
                doc_service_name = doc.get('service_name', '').strip()
                
                if is_common_service:
                    if doc_service_name.lower() == target_service_name.lower():
                        filter_stats['common_term_matches'] += 1
                        doc['service_match_type'] = 'exact_common_term'
                    else:
                        continue
                else:
                    if doc_service_name.lower() == target_service_name.lower():
                        doc['service_match_type'] = 'exact'
                    elif target_service_name.lower() in doc_service_name.lower() or doc_service_name.lower() in target_service_name.lower():
                        doc['service_match_type'] = 'partial'
                    else:
                        continue
            else:
                doc['service_match_type'] = 'all'
                
            filter_stats['service_filtered'] += 1
            
            if reranker_score >= thresholds['reranker_threshold']:
                filter_stats['reranker_qualified'] += 1
                match_type = doc.get('service_match_type', 'unknown')
                grade_info_text = f" (등급: {doc.get('incident_grade', 'N/A')})" if grade_info and grade_info['has_grade_query'] else ""
                match_desc = "정확한 일반용어" if match_type == 'exact_common_term' else match_type
                doc['filter_reason'] = f"포괄성 우선 - {match_desc} 매칭 + Reranker 고품질 (점수: {reranker_score:.2f}){grade_info_text}"
                doc['final_score'] = reranker_score
                doc['quality_tier'] = 'Premium'
                filtered_docs.append(doc)
                filter_stats['final_selected'] += 1
                continue
            
            hybrid_score = self.calculate_hybrid_score(search_score, reranker_score)
            final_score = doc.get('final_score', hybrid_score)
            final_score = final_score if final_score is not None else 0.0
            
            if final_score >= thresholds['hybrid_threshold']:
                filter_stats['hybrid_qualified'] += 1
                match_type = doc.get('service_match_type', 'unknown')
                grade_info_text = f" (등급: {doc.get('incident_grade', 'N/A')})" if grade_info and grade_info['has_grade_query'] else ""
                match_desc = "정확한 일반용어" if match_type == 'exact_common_term' else match_type
                doc['filter_reason'] = f"포괄성 우선 - {match_desc} 매칭 + 하이브리드 통과 (점수: {final_score:.2f}){grade_info_text}"
                doc['quality_tier'] = 'Standard'
                filtered_docs.append(doc)
                filter_stats['final_selected'] += 1
        
        def sort_key(doc):
            match_priority = {'exact': 3, 'partial': 2, 'exact_common_term': 3, 'all': 1}
            semantic_boost = doc.get('semantic_similarity', 0) or 0
            final_score = doc.get('final_score', 0) or 0
            
            grade_priority = 0
            if grade_info and grade_info['has_grade_query']:
                grade = doc.get('incident_grade', '')
                if '1등급' in grade:
                    grade_priority = 4
                elif '2등급' in grade:
                    grade_priority = 3
                elif '3등급' in grade:
                    grade_priority = 2
                elif '4등급' in grade:
                    grade_priority = 1
            
            return (
                grade_priority,
                match_priority.get(doc.get('service_match_type', 'all'), 0), 
                final_score + (semantic_boost * 0.1)
            )
        
        filtered_docs.sort(key=sort_key, reverse=True)
        final_docs = filtered_docs[:thresholds['max_results']]
        
        return final_docs

    def semantic_search_with_adaptive_filtering(self, query, target_service_name=None, query_type="default", top_k=50):
        """시맨틱 검색 - 월 조건 검색 쿼리 강화 및 통계 쿼리 통합"""
        try:
            print(f"DEBUG: ========== SEARCH START ==========")
            print(f"DEBUG: Query: '{query}'")
            print(f"DEBUG: Target service: {target_service_name}")
            print(f"DEBUG: Query type: {query_type}")
            
            grade_info = self.extract_incident_grade_from_query(query)
            time_info = self._extract_year_month_from_query_unified(query)
            
            print(f"DEBUG: Unified time info extracted: {time_info}")
            print(f"DEBUG: Grade info extracted: {grade_info}")
            
            is_common_service = False
            if target_service_name:
                is_common, _ = self.is_common_term_service(target_service_name)
                if is_common:
                    is_common_service = True
            
            expanded_query = self._expand_query_with_semantic_similarity(query)
            print(f"DEBUG: Expanded query: '{expanded_query}'")
            
            if grade_info['has_grade_query']:
                expanded_query = self.build_grade_search_query(expanded_query, grade_info)
                print(f"DEBUG: Query with grade filter: '{expanded_query}'")
            
            # 개선된 통합 시간 조건 처리
            if time_info['year'] or time_info['months']:
                time_conditions = []
                
                # 연도 조건 (정확한 매칭만)
                if time_info['year']:
                    year_conditions = [
                        f'year:"{time_info["year"]}"',
                        f'error_date:{time_info["year"]}-*'
                    ]
                    time_conditions.append(f'({" OR ".join(year_conditions)})')
                    print(f"DEBUG: Year condition added: {year_conditions}")
                
                # 통합된 월 조건 처리 (범위와 개별 월 모두 동일하게 처리)
                if time_info['months']:
                    month_conditions = []
                    for month_num in time_info['months']:
                        # month 필드 정확 매칭
                        month_conditions.append(f'month:"{month_num}"')
                        
                        # error_date 월 매칭 (YYYY-MM-DD 형식)
                        month_str = f"{month_num:02d}"
                        if time_info['year']:
                            month_conditions.append(f'error_date:{time_info["year"]}-{month_str}-*')
                        else:
                            # 연도 없이 월만 지정된 경우
                            month_conditions.append(f'error_date:*-{month_str}-*')
                    
                    time_conditions.append(f'({" OR ".join(month_conditions)})')
                    print(f"DEBUG: Unified months condition added for months: {time_info['months']}")
                
                # 최종 시간 필터 적용
                if time_conditions:
                    time_filter = " AND ".join(time_conditions)
                    if expanded_query and expanded_query.strip():
                        enhanced_query = f'({expanded_query}) AND {time_filter}'
                    else:
                        enhanced_query = time_filter
                    
                    print(f"DEBUG: Final enhanced query with unified time filter: '{enhanced_query}'")
                else:
                    enhanced_query = expanded_query
            else:
                enhanced_query = expanded_query
            
            # 서비스명 조건 추가
            if target_service_name:
                if is_common_service:
                    service_query = f'service_name:"{target_service_name}"'
                    if enhanced_query != target_service_name:
                        enhanced_query = f'{service_query} AND ({enhanced_query})'
                    else:
                        enhanced_query = f'{service_query} AND (*)'
                else:
                    service_query = f'(service_name:"{target_service_name}" OR service_name:*{target_service_name}*)'
                    if enhanced_query != target_service_name:
                        enhanced_query = f'{service_query} AND ({enhanced_query})'
                    else:
                        enhanced_query = f'{service_query} AND (*)'
            
            print(f"DEBUG: Final search query: '{enhanced_query}'")
            
            # Azure Cognitive Search 실행
            if query_type in ['repair', 'cause']:
                top_k = max(top_k, 80)
            else:
                top_k = max(top_k, 30)
            
            print(f"DEBUG: Executing Azure search with top_k={top_k}")
            
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
            
            # 검색 결과를 문서 리스트로 변환
            documents = []
            print(f"DEBUG: ========== SEARCH RESULTS ==========")
            
            for i, result in enumerate(results):
                if i < 5:  # 처음 5개만 로그
                    incident_id = result.get("incident_id", "N/A")
                    error_date = result.get("error_date", "N/A")
                    year = result.get("year", "N/A")
                    month = result.get("month", "N/A")
                    score = result.get("@search.score", 0)
                    print(f"DEBUG: Search result {i+1}: ID={incident_id}, error_date={error_date}, year={year}, month={month}, score={score}")
                
                error_time_raw = result.get("error_time", 0)
                try:
                    if error_time_raw is None:
                        error_time = 0
                    elif isinstance(error_time_raw, str):
                        error_time = int(float(error_time_raw.strip())) if error_time_raw.strip() else 0
                    else:
                        error_time = int(error_time_raw)
                except (ValueError, TypeError):
                    error_time = 0
                
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
                    "score": result.get("@search.score", 0) if result.get("@search.score") is not None else 0.0,
                    "reranker_score": result.get("@search.reranker_score", 0) if result.get("@search.reranker_score") is not None else 0.0
                })
            
            print(f"DEBUG: Total search results: {len(documents)}")
            
            # 추가 필터링 적용
            if query_type in ['repair', 'cause']:
                filtered_documents = self.advanced_filter_documents_for_accuracy(documents, query_type, query, target_service_name, grade_info)
            else:
                filtered_documents = self.simple_filter_documents_for_coverage(documents, query_type, query, target_service_name, grade_info)
            
            print(f"DEBUG: After document filtering: {len(filtered_documents)}")
            print(f"DEBUG: ========== SEARCH END ==========")
            
            return filtered_documents
            
        except Exception as e:
            print(f"DEBUG: Search error: {e}")
            return self.search_documents_with_service_filter(query, target_service_name, query_type, top_k//2)

    def _extract_year_month_from_query_unified(self, query):
        """통합된 연도와 월 조건 추출 - 범위와 개별 월을 동일하게 처리"""
        import re
        
        time_info = {
            'year': None,
            'months': []  # 모든 월을 리스트로 통합 관리
        }
        
        if not query:
            return time_info
        
        print(f"DEBUG: Unified time extraction from query: '{query}'")
        
        # 연도 추출
        year_patterns = [
            r'\b(\d{4})년\b',
            r'\b(\d{4})\s*년도\b',
            r'\b(\d{4})년도\b'
        ]
        
        for pattern in year_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                time_info['year'] = matches[-1]
                print(f"DEBUG: Extracted year from query: {time_info['year']}")
                break
        
        # 모든 월 관련 패턴을 통합하여 처리
        months_set = set()
        
        # 월 범위 패턴들
        month_range_patterns = [
            r'\b(\d+)\s*~\s*(\d+)월\b',
            r'\b(\d+)월\s*~\s*(\d+)월\b',  
            r'\b(\d+)\s*-\s*(\d+)월\b',
            r'\b(\d+)월\s*-\s*(\d+)월\b'
        ]
        
        for pattern in month_range_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                for match in matches:
                    start_month = int(match[0])
                    end_month = int(match[1])
                    if 1 <= start_month <= 12 and 1 <= end_month <= 12 and start_month <= end_month:
                        for month_num in range(start_month, end_month + 1):
                            months_set.add(month_num)
                        print(f"DEBUG: Added month range {start_month}~{end_month} to months set")
        
        # 개별 월 패턴들
        individual_month_patterns = [
            r'\b(\d{1,2})월\b',
            r'\b(\d{1,2})\s*월\b'
        ]
        
        for pattern in individual_month_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                for match in matches:
                    month_num = int(match)
                    if 1 <= month_num <= 12:
                        months_set.add(month_num)
                        print(f"DEBUG: Added individual month {month_num} to months set")
        
        # 콤마로 구분된 월 패턴 (1월, 2월, 3월, 4월, 5월, 6월)
        comma_separated_pattern = r'(\d{1,2})월(?:\s*,\s*(\d{1,2})월)*'
        comma_matches = re.findall(r'(\d{1,2})월', query)
        if comma_matches:
            for match in comma_matches:
                month_num = int(match)
                if 1 <= month_num <= 12:
                    months_set.add(month_num)
                    print(f"DEBUG: Added comma-separated month {month_num} to months set")
        
        # 최종 months 리스트 생성 (정렬된 상태)
        time_info['months'] = sorted(list(months_set))
        
        print(f"DEBUG: Final unified time info: year={time_info['year']}, months={time_info['months']}")
        
        return time_info

    def search_documents_with_service_filter(self, query, target_service_name=None, query_type="default", top_k=15):
        """서비스명 필터링을 지원하는 일반 검색 (fallback용)"""
        try:
            grade_info = self.extract_incident_grade_from_query(query)
            time_info = self._extract_year_month_from_query_unified(query)
            
            enhanced_query = query
            if grade_info['has_grade_query']:
                enhanced_query = self.build_grade_search_query(query, grade_info)
            
            if time_info['year'] or time_info['months']:
                time_conditions = []
                
                if time_info['year']:
                    year_conditions = [
                        f'year:"{time_info["year"]}"',
                        f'error_date:{time_info["year"]}*'
                    ]
                    time_conditions.append(f'({" OR ".join(year_conditions)})')
                
                if time_info['months']:
                    month_conditions = []
                    for month_num in time_info['months']:
                        month_conditions.append(f'month:"{month_num}"')
                    time_conditions.append(f'({" OR ".join(month_conditions)})')
                
                if time_conditions:
                    time_filter = " AND ".join(time_conditions)
                    enhanced_query = f'({enhanced_query}) AND {time_filter}'
            
            if target_service_name:
                is_common, _ = self.is_common_term_service(target_service_name)
                
                if is_common:
                    enhanced_query = f'service_name:"{target_service_name}" AND ({enhanced_query})'
                else:
                    enhanced_query = f'(service_name:"{target_service_name}" OR service_name:*{target_service_name}*) AND ({enhanced_query})'
            
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
                error_time_raw = result.get("error_time", 0)
                try:
                    if error_time_raw is None:
                        error_time = 0
                    elif isinstance(error_time_raw, str):
                        error_time = int(float(error_time_raw.strip())) if error_time_raw.strip() else 0
                    else:
                        error_time = int(error_time_raw)
                except (ValueError, TypeError):
                    error_time = 0
                
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
                    "score": result.get("@search.score", 0) if result.get("@search.score") is not None else 0.0,
                    "reranker_score": result.get("@search.reranker_score", 0) if result.get("@search.reranker_score") is not None else 0.0
                })
            
            if query_type in ['repair', 'cause']:
                filtered_documents = self.advanced_filter_documents_for_accuracy(documents, query_type, query, target_service_name, grade_info)
            else:
                filtered_documents = self.simple_filter_documents_for_coverage(documents, query_type, query, target_service_name, grade_info)
            
            return filtered_documents
            
        except Exception as e:
            return []

    def search_documents_fallback(self, query, target_service_name=None, top_k=25):
        """매우 관대한 기준의 대체 검색"""
        try:
            grade_info = self.extract_incident_grade_from_query(query)
            
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
                    search_query = f'service_name:*{target_service_name}*'
                else:
                    search_query = f'service_name:*{target_service_name}*'
            else:
                search_query = query
            
            if grade_info['has_grade_query'] and grade_info['specific_grade']:
                search_query += f' AND incident_grade:"{grade_info["specific_grade"]}"'
            
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
                    error_time_raw = result.get("error_time", 0)
                    try:
                        if error_time_raw is None:
                            error_time = 0
                        elif isinstance(error_time_raw, str):
                            error_time = int(float(error_time_raw.strip())) if error_time_raw.strip() else 0
                        else:
                            error_time = int(error_time_raw)
                    except (ValueError, TypeError):
                        error_time = 0
                    
                    doc = {
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
                        "score": score,
                        "reranker_score": result.get("@search.reranker_score", 0) if result.get("@search.reranker_score") is not None else 0.0,
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
            
        except Exception as e:
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
            matches = re.findall(pattern, query, re.IGNORECASE)
            for match in matches:
                service_name = match.strip()
                if len(service_name) >= 2:
                    return service_name
        
        return None