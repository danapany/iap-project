import streamlit as st
import re
from config.prompts import SystemPrompts
from config.settings_local import AppConfigLocal
from utils.search_utils_local import SearchManagerLocal
from utils.ui_components_local import UIComponentsLocal

class QueryProcessorLocal:
    """쿼리 처리 관리 클래스 - 시간대/요일 기반 필터링 지원 추가 + 정확한 서비스명 필터링 강화"""
    
    def __init__(self, azure_openai_client, search_client, model_name, config=None):
        self.azure_openai_client = azure_openai_client
        self.search_client = search_client
        self.model_name = model_name
        self.config = config if config else AppConfigLocal()
        self.search_manager = SearchManagerLocal(search_client, self.config)
        self.ui_components = UIComponentsLocal()
        # 디버그 모드 설정 (개발 시에만 True로 설정)
        self.debug_mode = False
    
    def extract_time_conditions(self, query):
        """쿼리에서 시간대/요일 조건 추출"""
        time_conditions = {
            'daynight': None,  # '주간' 또는 '야간'
            'week': None,      # 요일
            'is_time_query': False
        }
        
        # 주간/야간 패턴 검색
        daynight_patterns = [
            r'\b(야간|밤|새벽|심야|야시간)\b',
            r'\b(주간|낮|오전|오후|주시간|일과시간)\b'
        ]
        
        for pattern in daynight_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                time_conditions['is_time_query'] = True
                for match in matches:
                    if match in ['야간', '밤', '새벽', '심야', '야시간']:
                        time_conditions['daynight'] = '야간'
                    elif match in ['주간', '낮', '오전', '오후', '주시간', '일과시간']:
                        time_conditions['daynight'] = '주간'
        
        # 요일 패턴 검색
        week_patterns = [
            r'\b(월요일|월)\b',
            r'\b(화요일|화)\b', 
            r'\b(수요일|수)\b',
            r'\b(목요일|목)\b',
            r'\b(금요일|금)\b',
            r'\b(토요일|토)\b',
            r'\b(일요일|일)\b',
            r'\b(평일|주중)\b',
            r'\b(주말|토일)\b'
        ]
        
        for pattern in week_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                time_conditions['is_time_query'] = True
                for match in matches:
                    if match in ['월요일', '월']:
                        time_conditions['week'] = '월'
                    elif match in ['화요일', '화']:
                        time_conditions['week'] = '화'
                    elif match in ['수요일', '수']:
                        time_conditions['week'] = '수'
                    elif match in ['목요일', '목']:
                        time_conditions['week'] = '목'
                    elif match in ['금요일', '금']:
                        time_conditions['week'] = '금'
                    elif match in ['토요일', '토']:
                        time_conditions['week'] = '토'
                    elif match in ['일요일', '일']:
                        time_conditions['week'] = '일'
                    elif match in ['평일', '주중']:
                        time_conditions['week'] = '평일'
                    elif match in ['주말', '토일']:
                        time_conditions['week'] = '주말'
        
        return time_conditions
    
    def extract_department_conditions(self, query):
        """쿼리에서 부서 관련 조건 추출"""
        department_conditions = {
            'owner_depart': None,  # 특정 부서명
            'is_department_query': False
        }
        
        # 부서 관련 키워드 감지
        department_keywords = [
            '담당부서', '조치부서', '처리부서', '책임부서', '관리부서',
            '부서', '팀', '조직', '담당', '처리', '조치', '관리'
        ]
        
        # 부서 질문인지 확인
        if any(keyword in query for keyword in department_keywords):
            department_conditions['is_department_query'] = True
        
        # 특정 부서명 추출 (일반적인 부서명 패턴)
        department_patterns = [
            r'\b(개발|운영|기술|시스템|네트워크|보안|DB|데이터베이스|인프라|클라우드)(?:부서|팀|파트)?\b',
            r'\b(고객|서비스|상담|지원|헬프데스크)(?:부서|팀|파트)?\b',
            r'\b(IT|정보시스템|정보기술|전산)(?:부서|팀|파트)?\b',
            r'\b([가-힣]+)(?:부서|팀|파트)\b'
        ]
        
        for pattern in department_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                # 첫 번째 매칭된 부서명 사용
                department_conditions['owner_depart'] = matches[0]
                break
        
        return department_conditions
    
    def classify_query_type_with_llm(self, query):
        """LLM을 사용하여 쿼리 타입을 자동으로 분류 - 시간 관련 쿼리 지원"""
        try:
            classification_prompt = f"""
다음 사용자 질문을 분석하여 적절한 카테고리를 선택해주세요.

**분류 기준:**
1. **repair**: 서비스명과 장애현상이 모두 포함된 복구방법 문의
   - 예: "ERP 접속불가 복구방법", "API_Link 응답지연 해결방법"
   
2. **cause**: 장애원인 분석이나 원인 파악을 요청하는 문의
   - 예: "ERP 접속불가 원인이 뭐야?", "API 응답지연 장애원인", "왜 장애가 발생했어?"
   
3. **similar**: 서비스명 없이 장애현상만으로 유사사례 문의
   - 예: "접속불가 현상 유사사례", "응답지연 동일현상 복구방법"
   
4. **default**: 그 외의 모든 경우 (통계, 건수, 일반 문의, 시간대별 조회 등)
   - 예: "년도별 건수", "장애 통계", "서비스 현황", "야간에 발생한 장애", "주말 장애 현황"

**사용자 질문:** {query}

**응답 형식:** repair, cause, similar, default 중 하나만 출력하세요.
"""

            response = self.azure_openai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "당신은 IT 질문을 분류하는 전문가입니다. 주어진 질문을 정확히 분석하여 적절한 카테고리를 선택해주세요."},
                    {"role": "user", "content": classification_prompt}
                ],
                temperature=0.1,
                max_tokens=50
            )
            
            query_type = response.choices[0].message.content.strip().lower()
            
            if query_type not in ['repair', 'cause', 'similar', 'default']:
                query_type = 'default'
                
            return query_type
            
        except Exception as e:
            if self.debug_mode:
                st.warning(f"쿼리 분류 실패, 기본값 사용: {str(e)}")
            return 'default'

    def validate_document_relevance_with_llm(self, query, documents):
        """LLM을 사용하여 검색 결과의 관련성을 재검증 - repair/cause 전용"""
        try:
            if not documents:
                return []
            
            validation_prompt = f"""
사용자 질문: "{query}"

다음 검색된 문서들 중에서 사용자 질문과 실제로 관련성이 높은 문서만 선별해주세요.
각 문서에 대해 0-100점 사이의 관련성 점수를 매기고, 70점 이상인 문서만 선택하세요.

평가 기준:
1. 서비스명 일치도 (사용자가 특정 서비스를 언급한 경우)
2. 장애현상/증상 일치도  
3. 사용자가 요구한 정보 유형과의 일치도
4. 전체적인 맥락 일치도

"""

            for i, doc in enumerate(documents):
                doc_info = f"""
문서 {i+1}:
- 서비스명: {doc.get('service_name', '')}
- 장애현상: {doc.get('symptom', '')}
- 영향도: {doc.get('effect', '')}
- 장애원인: {doc.get('root_cause', '')[:100]}...
- 복구방법: {doc.get('incident_repair', '')[:100]}...
"""
                validation_prompt += doc_info

            validation_prompt += """

응답 형식 (JSON):
{
    "validated_documents": [
        {
            "document_index": 1,
            "relevance_score": 85,
            "reason": "서비스명과 장애현상이 정확히 일치함"
        },
        {
            "document_index": 3,
            "relevance_score": 72,
            "reason": "장애현상은 유사하지만 서비스명이 다름"
        }
    ]
}

70점 이상인 문서만 포함하세요.
"""

            response = self.azure_openai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "당신은 문서 관련성 평가 전문가입니다. 사용자 질문과 문서의 관련성을 정확하게 평가해주세요."},
                    {"role": "user", "content": validation_prompt}
                ],
                temperature=0.1,
                max_tokens=800
            )
            
            response_content = response.choices[0].message.content.strip()
            
            try:
                import json
                json_start = response_content.find('{')
                json_end = response_content.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_content = response_content[json_start:json_end]
                    validation_result = json.loads(json_content)
                    
                    validated_docs = []
                    for validated_doc in validation_result.get('validated_documents', []):
                        doc_index = validated_doc.get('document_index', 1) - 1
                        if 0 <= doc_index < len(documents):
                            original_doc = documents[doc_index].copy()
                            original_doc['relevance_score'] = validated_doc.get('relevance_score', 0)
                            original_doc['validation_reason'] = validated_doc.get('reason', '검증됨')
                            validated_docs.append(original_doc)
                    
                    validated_docs.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
                    return validated_docs
                    
            except (json.JSONDecodeError, KeyError) as e:
                if self.debug_mode:
                    st.warning(f"문서 검증 결과 파싱 실패: {str(e)}")
                return documents[:5]
                
        except Exception as e:
            if self.debug_mode:
                st.warning(f"문서 관련성 검증 실패: {str(e)}")
            return documents[:5]
        
        return documents

    def validate_service_specific_documents(self, documents, target_service_name):
        """지정된 서비스명에 해당하는 문서만 필터링 - 정확한 서비스명 매칭 강화"""
        if not target_service_name or not documents:
            return documents
        
        # 일반 용어 서비스명인지 확인
        is_common, _ = self.search_manager.is_common_term_service(target_service_name)
        
        validated_docs = []
        filter_stats = {
            'total': len(documents),
            'exact_matches': 0,
            'partial_matches': 0,
            'excluded': 0
        }
        
        for doc in documents:
            doc_service_name = doc.get('service_name', '').strip()
            
            if is_common:
                # 일반 용어 서비스명: 정확히 일치하는 경우만 허용
                if doc_service_name.lower() == target_service_name.lower():
                    filter_stats['exact_matches'] += 1
                    validated_docs.append(doc)
                else:
                    filter_stats['excluded'] += 1
                    if self.debug_mode:
                        st.info(f"제외된 문서: {doc_service_name} (요청: {target_service_name})")
            else:
                # 일반적인 서비스명: 정확히 일치하거나 포함 관계인 경우 허용
                if doc_service_name.lower() == target_service_name.lower():
                    filter_stats['exact_matches'] += 1
                    validated_docs.append(doc)
                elif target_service_name.lower() in doc_service_name.lower() or doc_service_name.lower() in target_service_name.lower():
                    filter_stats['partial_matches'] += 1
                    validated_docs.append(doc)
                else:
                    filter_stats['excluded'] += 1
        
        # 디버그 모드에서만 필터링 결과 표시
        if self.debug_mode:
            service_type = "일반용어" if is_common else "일반"
            st.info(f"""
            🎯 서비스명 필터링 결과 ({service_type} 서비스: {target_service_name})
            - 전체 문서: {filter_stats['total']}개
            - 정확히 일치: {filter_stats['exact_matches']}개
            - 부분 일치: {filter_stats['partial_matches']}개
            - 제외된 문서: {filter_stats['excluded']}개
            - 최종 선별: {len(validated_docs)}개
            """)
        
        return validated_docs

    def generate_rag_response_with_adaptive_processing(self, query, documents, query_type="default", time_conditions=None, department_conditions=None):
        """쿼리 타입별 적응형 RAG 응답 생성 - 시간 조건 및 부서 조건 지원 + 정확한 서비스명 필터링 강화"""
        try:
            # 시간 조건이 있는 경우 문서 필터링
            if time_conditions and time_conditions.get('is_time_query'):
                documents = self.search_manager.filter_documents_by_time_conditions(documents, time_conditions)
                
                if not documents:
                    time_desc = []
                    if time_conditions.get('daynight'):
                        time_desc.append(f"{time_conditions['daynight']}")
                    if time_conditions.get('week'):
                        time_desc.append(f"{time_conditions['week']}")
                    
                    return f"{''.join(time_desc)} 조건에 해당하는 장애 내역을 찾을 수 없습니다. 다른 검색 조건을 시도해보세요."
            
            # 부서 조건이 있는 경우 문서 필터링
            if department_conditions and department_conditions.get('is_department_query'):
                documents = self.search_manager.filter_documents_by_department_conditions(documents, department_conditions)
                
                if not documents:
                    dept_desc = department_conditions.get('owner_depart', '해당 부서')
                    return f"{dept_desc} 조건에 해당하는 장애 내역을 찾을 수 없습니다. 다른 검색 조건을 시도해보세요."
            
            # 쿼리 타입별 처리 방식 결정
            use_llm_validation = query_type in ['repair', 'cause']
            
            if use_llm_validation:
                # repair/cause: 정확성 우선 처리
                if self.debug_mode:
                    st.info("🎯 정확성 우선 처리 - 검색 결과의 관련성 재검증 중...")
                validated_documents = self.validate_document_relevance_with_llm(query, documents)
                
                if self.debug_mode:
                    if len(validated_documents) < len(documents):
                        removed_count = len(documents) - len(validated_documents)
                        st.success(f"✅ 관련성 검증 완료: {len(validated_documents)}개 문서 선별 (관련성 낮은 {removed_count}개 문서 제외)")
                    else:
                        st.success(f"✅ 관련성 검증 완료: 모든 {len(validated_documents)}개 문서가 관련성 기준 통과")
                
                if not validated_documents:
                    return "검색된 문서들이 사용자 질문과 관련성이 낮아 적절한 답변을 제공할 수 없습니다. 다른 검색어나 더 구체적인 질문을 시도해보세요."
                
                processing_documents = validated_documents
                processing_info = "관련성 검증 완료 (70점 이상)"
                
            else:
                # similar/default: 포괄성 우선 처리
                if self.debug_mode:
                    st.info("📋 포괄성 우선 처리 - 광범위한 검색 결과 활용 중...")
                processing_documents = documents
                processing_info = "포괄적 검색 결과 활용"
                if self.debug_mode:
                    st.success(f"✅ 포괄적 처리 완료: {len(processing_documents)}개 문서 활용")

            # **수정: 중복 제거 및 정확한 집계 정보 계산 (시간 조건 및 부서 조건 반영)**
            # 장애 ID 기준으로 중복 제거
            unique_documents = {}
            for doc in processing_documents:
                incident_id = doc.get('incident_id', '')
                if incident_id and incident_id not in unique_documents:
                    unique_documents[incident_id] = doc
            
            # 중복 제거된 문서 리스트로 업데이트
            processing_documents = list(unique_documents.values())
            total_count = len(processing_documents)
            
            # **수정: 더 정확한 통계 계산**
            yearly_stats = {}
            time_stats = {'daynight': {}, 'week': {}}
            department_stats = {}
            service_stats = {}  # 서비스별 통계 추가
            
            for doc in processing_documents:
                # 년도 통계
                error_date = doc.get('error_date', '')
                year_from_date = None
                if error_date and len(error_date) >= 4:
                    try:
                        year_from_date = int(error_date[:4])
                    except:
                        pass
                
                year_from_field = doc.get('year', '')
                if year_from_field:
                    try:
                        year_from_field = int(year_from_field)
                    except:
                        year_from_field = None
                
                final_year = year_from_date or year_from_field
                if final_year:
                    yearly_stats[final_year] = yearly_stats.get(final_year, 0) + 1
                
                # 시간대 통계
                daynight = doc.get('daynight', '')
                if daynight:
                    time_stats['daynight'][daynight] = time_stats['daynight'].get(daynight, 0) + 1
                
                # 요일 통계  
                week = doc.get('week', '')
                if week:
                    time_stats['week'][week] = time_stats['week'].get(week, 0) + 1
                
                # 부서 통계
                owner_depart = doc.get('owner_depart', '')
                if owner_depart:
                    department_stats[owner_depart] = department_stats.get(owner_depart, 0) + 1
                
                # 서비스별 통계 추가
                service_name = doc.get('service_name', '')
                if service_name:
                    service_stats[service_name] = service_stats.get(service_name, 0) + 1
            
            yearly_total = sum(yearly_stats.values())
            
            # 컨텍스트 구성
            context_parts = []
            
            # 시간 조건 정보 추가
            time_condition_info = ""
            if time_conditions and time_conditions.get('is_time_query'):
                time_desc = []
                if time_conditions.get('daynight'):
                    time_desc.append(f"시간대: {time_conditions['daynight']}")
                if time_conditions.get('week'):
                    time_desc.append(f"요일: {time_conditions['week']}")
                time_condition_info = f" - 시간 조건: {', '.join(time_desc)}"
            
            # 부서 조건 정보 추가
            department_condition_info = ""
            if department_conditions and department_conditions.get('is_department_query'):
                if department_conditions.get('owner_depart'):
                    department_condition_info = f" - 부서 조건: {department_conditions['owner_depart']}"
                else:
                    department_condition_info = f" - 부서별 조회"
            
            # **수정: 서비스별 통계 정보 추가**
            service_stats_info = ""
            if len(service_stats) > 1:
                service_stats_info = f"\n서비스별 분포: {dict(sorted(service_stats.items(), key=lambda x: x[1], reverse=True))}"
            elif len(service_stats) == 1:
                service_name = list(service_stats.keys())[0]
                service_stats_info = f"\n대상 서비스: {service_name} ({service_stats[service_name]}건)"
            
            stats_info = f"""
=== 정확한 집계 정보 ({processing_info}{time_condition_info}{department_condition_info}) ===
전체 문서 수: {total_count}건
년도별 분포: {dict(sorted(yearly_stats.items()))}
년도별 합계: {yearly_total}건{service_stats_info}
집계 검증: {'일치' if yearly_total == total_count else '불일치 - 재계산 필요'}
처리 방식: {'정확성 우선 (LLM 검증)' if use_llm_validation else '포괄성 우선 (광범위 검색)'}
"""
            
            # 시간 통계 추가 (시간 쿼리인 경우)
            if time_conditions and time_conditions.get('is_time_query'):
                if time_stats['daynight']:
                    stats_info += f"시간대별 분포: {time_stats['daynight']}\n"
                if time_stats['week']:
                    stats_info += f"요일별 분포: {time_stats['week']}\n"
            
            # 부서 통계 추가 (부서 쿼리인 경우)
            if department_conditions and department_conditions.get('is_department_query'):
                if department_stats:
                    stats_info += f"부서별 분포: {department_stats}\n"
            
            stats_info += "==========================="
            
            context_parts.append(stats_info)
            
            for i, doc in enumerate(processing_documents):
                final_score = doc.get('final_score', 0)
                quality_tier = doc.get('quality_tier', 'Standard')
                filter_reason = doc.get('filter_reason', '기본 선별')
                service_match_type = doc.get('service_match_type', 'unknown')
                relevance_score = doc.get('relevance_score', 0) if use_llm_validation else "N/A"
                validation_reason = doc.get('validation_reason', '검증됨') if use_llm_validation else "포괄적 처리"
                
                validation_info = f" - 관련성: {relevance_score}점 ({validation_reason})" if use_llm_validation else " - 포괄적 검색"
                
                # 시간 정보 추가
                time_info = ""
                if doc.get('daynight'):
                    time_info += f" - 시간대: {doc.get('daynight')}"
                if doc.get('week'):
                    time_info += f" - 요일: {doc.get('week')}"
                
                # 부서 정보 추가
                department_info = ""
                if doc.get('owner_depart'):
                    department_info += f" - 담당부서: {doc.get('owner_depart')}"
                
                context_part = f"""문서 {i+1} [{quality_tier}급 - {filter_reason} - {service_match_type} 매칭{validation_info}{time_info}{department_info}]:
장애 ID: {doc['incident_id']}
서비스명: {doc['service_name']}
장애시간: {doc['error_time']}
영향도: {doc['effect']}
현상: {doc['symptom']}
복구공지: {doc['repair_notice']}
발생일자: {doc['error_date']}
요일: {doc['week']}
시간대: {doc['daynight']}
장애원인: {doc['root_cause']}
복구방법: {doc['incident_repair']}
개선계획: {doc['incident_plan']}
원인유형: {doc['cause_type']}
처리유형: {doc['done_type']}
장애등급: {doc['incident_grade']}
담당부서: {doc['owner_depart']}
년도: {doc['year']}
월: {doc['month']}
품질점수: {final_score:.2f}
"""
                if use_llm_validation:
                    context_part += f"관련성점수: {relevance_score}점\n"
                
                context_parts.append(context_part)
            
            context = "\n\n".join(context_parts)
            
            # 시스템 프롬프트 선택
            system_prompt = SystemPrompts.get_prompt(query_type)

            user_prompt = f"""
다음 장애 이력 문서들을 참고하여 질문에 답변해주세요.
(처리 방식: {'정확성 우선 - LLM 관련성 검증 적용' if use_llm_validation else '포괄성 우선 - 광범위한 검색 결과 활용'}):

**중요! 정확한 집계 검증 필수사항:**
- 실제 제공된 문서 수: {total_count}건 (중복 제거 완료)
- 년도별 건수: {dict(sorted(yearly_stats.items()))}
- 년도별 합계: {yearly_total}건
- 서비스별 분포: {dict(sorted(service_stats.items(), key=lambda x: x[1], reverse=True)) if service_stats else '정보없음'}
- **답변 시 반드시 실제 문서 수({total_count}건)와 일치해야 함**
- **표시하는 내역 수와 총 건수가 반드시 일치해야 함**
- **불일치 시 반드시 재계산 후 답변할 것**

**검증 절차:**
1. 답변하기 전에 실제 제공된 문서가 몇 개인지 다시 세어보세요
2. 표시할 내역 수가 총 건수와 일치하는지 확인하세요  
3. 불일치하면 정확한 수로 수정해서 답변하세요

{context}

질문: {query}

답변:"""

            # Azure OpenAI API 호출
            response = self.azure_openai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0,  # 정확성을 위해 0.0으로 설정
                max_tokens=1500
            )
            
            return response.choices[0].message.content
        
        except Exception as e:
            st.error(f"응답 생성 실패: {str(e)}")
            return "죄송합니다. 응답을 생성하는 중 오류가 발생했습니다."

    def process_query(self, query, query_type=None):
        """쿼리 타입별 최적화된 처리 로직을 적용한 메인 쿼리 처리 - 시간 조건 및 부서 조건 지원 + 정확한 서비스명 필터링 강화"""
        with st.chat_message("assistant"):
            # 시간 조건 추출
            time_conditions = self.extract_time_conditions(query)
            
            # 부서 조건 추출
            department_conditions = self.extract_department_conditions(query)
            
            # 1단계: LLM 기반 쿼리 타입 자동 분류
            if query_type is None:
                with st.spinner("🔍 질문 분석 중..."):
                    query_type = self.classify_query_type_with_llm(query)
                    
                # 처리 방식 안내 (간소화)
                if self.debug_mode:
                    if query_type in ['repair', 'cause']:
                        st.info(f"🔍 질문 유형: **{query_type.upper()}** (🎯 정확성 우선 처리 - LLM 검증 적용)")
                    else:
                        st.info(f"🔍 질문 유형: **{query_type.upper()}** (📋 포괄성 우선 처리 - 광범위한 검색)")
            
            # 시간 조건 안내 (간소화)
            if time_conditions.get('is_time_query') and self.debug_mode:
                time_desc = []
                if time_conditions.get('daynight'):
                    time_desc.append(f"시간대: {time_conditions['daynight']}")
                if time_conditions.get('week'):
                    time_desc.append(f"요일: {time_conditions['week']}")
                st.info(f"⏰ 시간 조건 감지: {', '.join(time_desc)}")
            
            # 부서 조건 안내 (간소화)
            if department_conditions.get('is_department_query') and self.debug_mode:
                if department_conditions.get('owner_depart'):
                    st.info(f"🏢 부서 조건 감지: {department_conditions['owner_depart']}")
                else:
                    st.info(f"🏢 부서별 조회 요청 감지")
            
            # 2단계: 서비스명 추출
            target_service_name = self.search_manager.extract_service_name_from_query(query)
            if target_service_name and self.debug_mode:
                st.info(f"🏷️ 추출된 서비스명: **{target_service_name}**")
            
            # 3단계: 쿼리 타입별 최적화된 검색 수행
            with st.spinner("🔄 문서 검색 중..."):
                documents = self.search_manager.semantic_search_with_adaptive_filtering(
                    query, target_service_name, query_type
                )
                
                if documents:
                    # **수정: 정확한 서비스명 필터링 추가**
                    if target_service_name:
                        original_count = len(documents)
                        documents = self.validate_service_specific_documents(documents, target_service_name)
                        filtered_count = len(documents)
                        
                        if self.debug_mode and filtered_count < original_count:
                            excluded_count = original_count - filtered_count
                            st.info(f"🎯 서비스명 정확 매칭: {target_service_name} 서비스만 {filtered_count}개 선별 ({excluded_count}개 제외)")
                    
                    # 검색 결과 품질 분석 (간소화)
                    premium_count = sum(1 for doc in documents if doc.get('quality_tier') == 'Premium')
                    standard_count = sum(1 for doc in documents if doc.get('quality_tier') == 'Standard')
                    basic_count = sum(1 for doc in documents if doc.get('quality_tier') == 'Basic')
                    
                    # 집계 관련 질문인지 확인
                    is_count_query = any(keyword in query.lower() for keyword in ['건수', '개수', '몇건', '년도별', '월별', '통계', '현황'])
                    
                    # 집계 미리보기 (디버그 모드에서만)
                    if is_count_query and self.debug_mode:
                        yearly_stats = {}
                        time_stats = {'daynight': {}, 'week': {}}
                        service_stats = {}
                        
                        for doc in documents:
                            error_date = doc.get('error_date', '')
                            year_from_date = None
                            if error_date and len(error_date) >= 4:
                                try:
                                    year_from_date = int(error_date[:4])
                                except:
                                    pass
                            
                            year_from_field = doc.get('year', '')
                            if year_from_field:
                                try:
                                    year_from_field = int(year_from_field)
                                except:
                                    year_from_field = None
                            
                            final_year = year_from_date or year_from_field
                            if final_year:
                                yearly_stats[final_year] = yearly_stats.get(final_year, 0) + 1
                            
                            # 시간 통계
                            daynight = doc.get('daynight', '')
                            if daynight:
                                time_stats['daynight'][daynight] = time_stats['daynight'].get(daynight, 0) + 1
                            
                            week = doc.get('week', '')
                            if week:
                                time_stats['week'][week] = time_stats['week'].get(week, 0) + 1
                            
                            # 서비스별 통계
                            service_name = doc.get('service_name', '')
                            if service_name:
                                service_stats[service_name] = service_stats.get(service_name, 0) + 1
                        
                        yearly_total = sum(yearly_stats.values())
                        processing_method = "정확성 우선" if query_type in ['repair', 'cause'] else "포괄성 우선"
                        
                        preview_info = f"""
                        📊 집계 미리보기 ({processing_method} 처리 예정)
                        - 전체 건수: {len(documents)}건
                        - 년도별 분포: {dict(sorted(yearly_stats.items()))}
                        - 년도별 합계: {yearly_total}건
                        - 검증 상태: {'일치' if yearly_total == len(documents) else '불일치'}
                        """
                        
                        if target_service_name and service_stats:
                            preview_info += f"\n                        - 서비스별 분포: {dict(sorted(service_stats.items(), key=lambda x: x[1], reverse=True))}"
                        
                        if time_conditions.get('is_time_query') and (time_stats['daynight'] or time_stats['week']):
                            if time_stats['daynight']:
                                preview_info += f"\n                        - 시간대별 분포: {time_stats['daynight']}"
                            if time_stats['week']:
                                preview_info += f"\n                        - 요일별 분포: {time_stats['week']}"
                        
                        st.info(preview_info)
                    
                    # 간소화된 성공 메시지
                    #if premium_count + standard_count + basic_count > 0:
                    #    st.success(f"✅ {len(documents)}개의 관련 문서를 찾았습니다.")
                    
                    # 검색된 문서 상세 표시 (선택적)
                    with st.expander("📄 매칭된 문서 상세 보기"):
                        self.ui_components.display_documents_with_quality_info(documents)
                    
                    # 4단계: 적응형 RAG 응답 생성
                    with st.spinner("🤖 AI 답변 생성 중..."):
                        response = self.generate_rag_response_with_adaptive_processing(
                            query, documents, query_type, time_conditions, department_conditions
                        )
                        
                        # 깔끔한 답변 표시
                        st.write(response)
                        
                        st.session_state.messages.append({"role": "assistant", "content": response})
                        
                else:
                    # 5단계: 대체 검색 시도
                    with st.spinner("🔄 추가 검색 중..."):
                        fallback_documents = self.search_manager.search_documents_fallback(query, target_service_name)
                        
                        if fallback_documents:
                            if self.debug_mode:
                                st.info(f"🔄 대체 검색으로 {len(fallback_documents)}개 문서 발견")
                            
                            response = self.generate_rag_response_with_adaptive_processing(
                                query, fallback_documents, query_type, time_conditions, department_conditions
                            )
                            st.write(response)
                            
                            st.session_state.messages.append({"role": "assistant", "content": response})
                        else:
                            self._show_no_results_message(target_service_name, query_type, time_conditions)
    
    def _show_no_results_message(self, target_service_name, query_type, time_conditions=None):
        """검색 결과가 없을 때 개선 방안 제시 - 시간 조건 안내 포함"""
        time_condition_desc = ""
        if time_conditions and time_conditions.get('is_time_query'):
            time_desc = []
            if time_conditions.get('daynight'):
                time_desc.append(f"시간대: {time_conditions['daynight']}")
            if time_conditions.get('week'):
                time_desc.append(f"요일: {time_conditions['week']}")
            time_condition_desc = f" ({', '.join(time_desc)} 조건)"
        
        error_msg = f"""
        '{target_service_name or '해당 조건'}{time_condition_desc}'에 해당하는 문서를 찾을 수 없습니다.
        
        **🔧 개선 방안:**
        - 서비스명의 일부만 입력해보세요 (예: 'API' 대신 'API_Link')
        - 다른 검색어를 시도해보세요
        - 전체 검색을 원하시면 서비스명을 제외하고 검색해주세요
        - 더 일반적인 키워드를 사용해보세요
        
        **시간 조건 관련 개선 방안:**
        - 시간대 조건을 제거해보세요 (주간/야간)
        - 요일 조건을 제거해보세요
        - 더 넓은 시간 범위로 검색해보세요
        
        **💡 {query_type.upper()} 쿼리 최적화 팁:**
        """
        
        # 쿼리 타입별 개선 팁 추가
        if query_type == 'repair':
            error_msg += """
        - 서비스명과 장애현상을 모두 포함하세요
        - '복구방법', '해결방법' 키워드를 포함하세요
        """
        elif query_type == 'cause':
            error_msg += """
        - '원인', '이유', '왜' 등의 키워드를 포함하세요
        - 장애 현상을 구체적으로 설명하세요
        """
        elif query_type == 'similar':
            error_msg += """
        - '유사', '비슷한', '동일한' 키워드를 포함하세요
        - 핵심 장애 현상만 간결하게 기술하세요
        """
        else:
            error_msg += """
        - 통계나 현황 조회 시 기간을 명시하세요
        - '건수', '통계', '현황' 등의 키워드를 활용하세요
        """
        
        st.write(error_msg)
        st.session_state.messages.append({"role": "assistant", "content": error_msg})