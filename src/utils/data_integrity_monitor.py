import json
import re
import datetime
import os
from typing import Dict, List, Tuple, Any
import streamlit as st

class DataIntegrityMonitor:
    """RAG 데이터 무결성 실시간 모니터링 시스템"""
    
    def __init__(self, config=None):
        self.config = config
        self.violation_logs = []
        self.critical_fields = ['root_cause', 'incident_repair', 'incident_plan', 'symptom', 'effect']
        self.technical_patterns = self._initialize_technical_patterns()
        self.violation_count = {'high': 0, 'medium': 0, 'low': 0}
        
        if self.config and self.config.save_violation_logs:
            log_dir = os.path.dirname(self.config.violation_log_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
    
    def _initialize_technical_patterns(self):
        return {
            'system_components': [
                r'[가-힣]*(?:서버|시스템|서비스|데이터베이스|네트워크|API|헤더|로직|프로세스)',
                r'[A-Za-z]+(?:\s+[A-Za-z]+)*(?:Server|System|Service|Database|Network|API|Header|Logic|Process)',
                r'(?:WAS|DB|DNS|SSL|VPN|OTP|SMS|HTTP|HTTPS|TCP|IP)'
            ],
            'error_terms': [
                r'(?:누락|중단|실패|오류|에러|장애|문제|이슈|버그)',
                r'(?:불가|안됨|안되|되지않|할수없|불능)',
                r'(?:지연|타임아웃|timeout|delay|slow)'
            ],
            'action_terms': [
                r'(?:적용|설정|구성|배포|설치|업데이트|패치|수정|변경)',
                r'(?:재시작|리부팅|재시도|롤백|복구|복원)',
                r'(?:점검|확인|검증|모니터링|체크)'
            ],
            'specific_values': [
                r'\d+(?:MB|GB|TB|KB|분|시간|초|%|개|건)',
                r'\d{1,3}(?:\.\d{1,3}){3}',
                r'\d{4}-\d{2}-\d{2}',
                r'[A-Za-z0-9]+\.[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*'
            ]
        }
    
    def validate_llm_output(self, original_documents: List[Dict], llm_output: str) -> Dict[str, Any]:
        if not original_documents or not llm_output:
            return {'is_valid': True, 'violations': [], 'warning_count': 0}
        
        all_violations = []
        
        for idx, doc in enumerate(original_documents[:3]):
            doc_violations = self._validate_document_fields(doc, llm_output, idx)
            all_violations.extend(doc_violations)
        
        global_violations = self._validate_global_technical_terms(original_documents, llm_output)
        all_violations.extend(global_violations)
        
        high_violations = [v for v in all_violations if v['severity'] == 'HIGH']
        medium_violations = [v for v in all_violations if v['severity'] == 'MEDIUM']
        low_violations = [v for v in all_violations if v['severity'] == 'LOW']
        
        is_valid = len(high_violations) == 0 and len(medium_violations) <= 1
        
        validation_result = {
            'is_valid': is_valid,
            'violations': all_violations,
            'violation_count': len(all_violations),
            'severity_breakdown': {
                'high': len(high_violations),
                'medium': len(medium_violations),
                'low': len(low_violations)
            },
            'critical_field_violations': len([v for v in all_violations if v.get('field') in ['root_cause', 'incident_repair']]),
            'technical_term_retention_rate': self._calculate_technical_term_retention(original_documents, llm_output),
            'overall_score': self._calculate_integrity_score(all_violations, len(original_documents))
        }
        
        if all_violations and self.config and self.config.log_integrity_violations:
            self._log_violations(validation_result)
        
        return validation_result
    
    def _validate_document_fields(self, doc: Dict, llm_output: str, doc_index: int) -> List[Dict]:
        violations = []
        
        for field in self.critical_fields:
            original_value = doc.get(field, '').strip()
            if not original_value or len(original_value) < 10:
                continue
            
            violation = self._check_field_preservation(field, original_value, llm_output, doc_index, doc.get('incident_id', ''))
            if violation:
                violations.append(violation)
        
        return violations
    
    def _check_field_preservation(self, field_name: str, original_value: str, llm_output: str, doc_index: int, incident_id: str) -> Dict:
        tech_terms = self._extract_technical_terms(original_value)
        if not tech_terms:
            return None
        
        preserved_terms = []
        missing_terms = []
        
        for term in tech_terms:
            if self._is_term_preserved_in_output(term, llm_output):
                preserved_terms.append(term)
            else:
                missing_terms.append(term)
        
        preservation_rate = len(preserved_terms) / len(tech_terms) if tech_terms else 1.0
        
        if field_name in ['root_cause', 'incident_repair']:
            if preservation_rate < 0.7:
                severity = 'HIGH'
            elif preservation_rate < 0.8:
                severity = 'MEDIUM'
            elif preservation_rate < 0.9:
                severity = 'LOW'
            else:
                return None
        else:
            if preservation_rate < 0.5:
                severity = 'HIGH'
            elif preservation_rate < 0.7:
                severity = 'MEDIUM'
            elif preservation_rate < 0.8:
                severity = 'LOW'
            else:
                return None
        
        return {
            'type': 'FIELD_MODIFICATION',
            'field': field_name,
            'document_index': doc_index,
            'incident_id': incident_id,
            'severity': severity,
            'preservation_rate': preservation_rate,
            'original_length': len(original_value),
            'missing_terms': missing_terms,
            'preserved_terms': preserved_terms,
            'total_terms': len(tech_terms),
            'description': f"{field_name} 필드의 기술 용어 {len(missing_terms)}개 누락 (보존율: {preservation_rate:.1%})"
        }
    
    def _extract_technical_terms(self, text: str) -> List[str]:
        if not text:
            return []
        
        terms = set()
        
        for category, patterns in self.technical_patterns.items():
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    if isinstance(match, str) and len(match.strip()) >= 2:
                        terms.add(match.strip())
        
        english_terms = re.findall(r'\b[A-Z][A-Za-z]{2,}\b', text)
        terms.update([term for term in english_terms if len(term) >= 3])
        
        korean_terms = re.findall(r'[가-힣]{3,}', text)
        terms.update([term for term in korean_terms if len(term) >= 3 and not re.match(r'^[가-힣]{1,2}(이|가|을|를|의|에|서|로|으로|에서|부터|까지)$', term)])
        
        numeric_terms = re.findall(r'\d+[가-힣A-Za-z%]+', text)
        terms.update(numeric_terms)
        
        return list(terms)[:15]
    
    def _is_term_preserved_in_output(self, term: str, llm_output: str) -> bool:
        if not term or not llm_output:
            return False
        
        if term in llm_output:
            return True
        
        if term.lower() in llm_output.lower():
            return True
        
        if len(term) >= 3:
            if re.search(re.escape(term), llm_output, re.IGNORECASE):
                return True
        
        synonyms = self._get_term_synonyms(term)
        for synonym in synonyms:
            if synonym in llm_output:
                return True
        
        return False
    
    def _get_term_synonyms(self, term: str) -> List[str]:
        synonym_map = {
            '누락': ['빠짐', '없음', '미포함'],
            '중단': ['정지', '중지', '종료'],
            '실패': ['오류', '에러', '장애'],
            '서버': ['시스템', '호스트'],
            '데이터베이스': ['DB', '디비'],
            '네트워크': ['망', '통신'],
            '로그인': ['접속', '인증'],
            '가입': ['등록', '신청'],
            '결제': ['구매', '주문'],
            '발송': ['전송', '송신']
        }
        
        return synonym_map.get(term.lower(), [])
    
    def _validate_global_technical_terms(self, documents: List[Dict], llm_output: str) -> List[Dict]:
        violations = []
        
        all_critical_terms = set()
        for doc in documents[:3]:
            for field in ['root_cause', 'incident_repair']:
                value = doc.get(field, '')
                if value:
                    terms = self._extract_technical_terms(value)
                    critical_terms = [t for t in terms if self._is_critical_technical_term(t)]
                    all_critical_terms.update(critical_terms)
        
        if not all_critical_terms:
            return violations
        
        preserved_critical_terms = []
        missing_critical_terms = []
        
        for term in all_critical_terms:
            if self._is_term_preserved_in_output(term, llm_output):
                preserved_critical_terms.append(term)
            else:
                missing_critical_terms.append(term)
        
        global_preservation_rate = len(preserved_critical_terms) / len(all_critical_terms)
        
        if global_preservation_rate < 0.6:
            violations.append({
                'type': 'GLOBAL_TECHNICAL_TERM_LOSS',
                'severity': 'HIGH',
                'preservation_rate': global_preservation_rate,
                'missing_terms': missing_critical_terms,
                'preserved_terms': preserved_critical_terms,
                'total_critical_terms': len(all_critical_terms),
                'description': f"글로벌 핵심 기술 용어 {len(missing_critical_terms)}개 누락 (보존율: {global_preservation_rate:.1%})"
            })
        elif global_preservation_rate < 0.8:
            violations.append({
                'type': 'GLOBAL_TECHNICAL_TERM_LOSS',
                'severity': 'MEDIUM',
                'preservation_rate': global_preservation_rate,
                'missing_terms': missing_critical_terms,
                'preserved_terms': preserved_critical_terms,
                'total_critical_terms': len(all_critical_terms),
                'description': f"글로벌 핵심 기술 용어 일부 누락 (보존율: {global_preservation_rate:.1%})"
            })
        
        return violations
    
    def _is_critical_technical_term(self, term: str) -> bool:
        critical_patterns = [
            r'.*(?:서버|시스템|서비스|데이터베이스|네트워크|API|헤더|로직).*',
            r'.*(?:누락|중단|실패|오류|에러|장애).*',
            r'[A-Z]{2,}',
            r'\d+(?:MB|GB|분|%)',
            r'.*(?:설정|구성|적용|프로세스).*'
        ]
        
        return any(re.match(pattern, term, re.IGNORECASE) for pattern in critical_patterns)
    
    def _calculate_technical_term_retention(self, documents: List[Dict], llm_output: str) -> float:
        all_terms = set()
        
        for doc in documents[:3]:
            for field in self.critical_fields:
                value = doc.get(field, '')
                if value:
                    terms = self._extract_technical_terms(value)
                    all_terms.update(terms)
        
        if not all_terms:
            return 1.0
        
        preserved_count = sum(1 for term in all_terms if self._is_term_preserved_in_output(term, llm_output))
        return preserved_count / len(all_terms)
    
    def _calculate_integrity_score(self, violations: List[Dict], document_count: int) -> float:
        if not violations:
            return 100.0
        
        penalty = 0
        for violation in violations:
            if violation['severity'] == 'HIGH':
                penalty += 25
            elif violation['severity'] == 'MEDIUM':
                penalty += 10
            elif violation['severity'] == 'LOW':
                penalty += 5
        
        adjusted_penalty = penalty / max(document_count, 1)
        
        return max(0.0, 100.0 - adjusted_penalty)
    
    def _log_violations(self, validation_result: Dict):
        log_entry = {
            'timestamp': datetime.datetime.now().isoformat(),
            'violation_type': 'RAG_DATA_INTEGRITY_CHECK',
            'result': validation_result,
            'session_info': {
                'user_agent': 'Streamlit-ChatBot',
                'ip_address': getattr(st.session_state, 'client_ip', 'unknown')
            }
        }
        
        self.violation_logs.append(log_entry)
        
        severity_breakdown = validation_result.get('severity_breakdown', {})
        self.violation_count['high'] += severity_breakdown.get('high', 0)
        self.violation_count['medium'] += severity_breakdown.get('medium', 0)
        self.violation_count['low'] += severity_breakdown.get('low', 0)
        
        if self.config and self.config.save_violation_logs and self.config.violation_log_path:
            try:
                existing_logs = []
                if os.path.exists(self.config.violation_log_path):
                    with open(self.config.violation_log_path, 'r', encoding='utf-8') as f:
                        existing_logs = json.load(f)
                
                existing_logs.append(log_entry)
                
                if len(existing_logs) > 1000:
                    existing_logs = existing_logs[-1000:]
                
                with open(self.config.violation_log_path, 'w', encoding='utf-8') as f:
                    json.dump(existing_logs, f, ensure_ascii=False, indent=2)
                    
            except Exception as e:
                print(f"WARNING: Failed to save violation log: {e}")
        
        if self.config and self.config.debug_data_integrity:
            print(f"🚨 DATA INTEGRITY VIOLATION: {validation_result['violation_count']} violations detected")
            for violation in validation_result['violations']:
                print(f"   - {violation['severity']}: {violation['description']}")
    
    def get_violation_summary(self) -> str:
        if not self.violation_logs:
            return "✅ 데이터 무결성 위반 없음"
        
        total_violations = sum(self.violation_count.values())
        
        summary = f"""
📊 데이터 무결성 위반 요약:
- 총 세션 수: {len(self.violation_logs)}
- 총 위반 건수: {total_violations}
- 🔴 높은 심각도: {self.violation_count['high']}건
- 🟡 중간 심각도: {self.violation_count['medium']}건  
- 🟢 낮은 심각도: {self.violation_count['low']}건

최근 위반 시각: {self.violation_logs[-1]['timestamp'] if self.violation_logs else 'N/A'}
        """.strip()
        
        return summary
    
    def get_field_violation_statistics(self) -> Dict[str, int]:
        field_violations = {}
        
        for log_entry in self.violation_logs:
            violations = log_entry.get('result', {}).get('violations', [])
            for violation in violations:
                field = violation.get('field', 'unknown')
                if field not in field_violations:
                    field_violations[field] = 0
                field_violations[field] += 1
        
        return field_violations
    
    def generate_integrity_report(self) -> str:
        if not self.violation_logs:
            return "📊 데이터 무결성 리포트: 위반 사항 없음"
        
        field_stats = self.get_field_violation_statistics()
        
        report = f"""
📊 데이터 무결성 상세 리포트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 전체 통계:
- 검증 세션 수: {len(self.violation_logs)}
- 총 위반 건수: {sum(self.violation_count.values())}

🎯 심각도별 분포:
- HIGH (🔴): {self.violation_count['high']}건 ({self.violation_count['high']/max(sum(self.violation_count.values()),1)*100:.1f}%)
- MEDIUM (🟡): {self.violation_count['medium']}건 ({self.violation_count['medium']/max(sum(self.violation_count.values()),1)*100:.1f}%)
- LOW (🟢): {self.violation_count['low']}건 ({self.violation_count['low']/max(sum(self.violation_count.values()),1)*100:.1f}%)

📋 필드별 위반 통계:
"""
        
        for field, count in sorted(field_stats.items(), key=lambda x: x[1], reverse=True):
            report += f"- {field}: {count}건\n"
        
        report += f"\n🕒 최근 위반 사례 (최대 5개):\n"
        recent_logs = self.violation_logs[-5:]
        
        for i, log_entry in enumerate(recent_logs, 1):
            timestamp = log_entry['timestamp']
            violations = log_entry.get('result', {}).get('violations', [])
            high_violations = [v for v in violations if v['severity'] == 'HIGH']
            
            report += f"{i}. {timestamp}: {len(violations)}건 위반"
            if high_violations:
                report += f" (HIGH: {len(high_violations)}건)"
            report += "\n"
        
        return report.strip()
    
    def reset_statistics(self):
        self.violation_logs.clear()
        self.violation_count = {'high': 0, 'medium': 0, 'low': 0}
        print("🔄 데이터 무결성 통계가 초기화되었습니다.")