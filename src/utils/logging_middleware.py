# utils/logging_middleware.py - 실제 클라이언트 IP 추출 개선 버전
import streamlit as st
import time
import functools
import re
import socket
import requests
from datetime import datetime
from typing import Any, Callable, Optional
from utils.monitoring_manager import MonitoringManager

class LoggingMiddleware:
    """사용자 활동 로깅 미들웨어 - 실제 클라이언트 IP 추출 개선 버전"""
    
    def __init__(self):
        self.monitoring_manager = MonitoringManager()
        
        # 답변 실패 패턴 정의
        self.failure_patterns = [
            r"해당.*조건.*문서.*찾을 수 없습니다",
            r"검색된 문서가 없어서 답변을 제공할 수 없습니다",
            r"관련 정보를 찾을 수 없습니다",
            r"문서를 찾을 수 없습니다",
            r"답변을 생성할 수 없습니다",
            r"죄송합니다.*오류가 발생했습니다",
            r"처리 중 오류가 발생했습니다",
            r"연결에 실패했습니다",
            r"서비스를 이용할 수 없습니다"
        ]
    
    def get_client_ip(self) -> str:
        """실제 클라이언트 IP 주소 추출 - 개선된 버전"""
        try:
            # 1. 세션 상태에서 미리 설정된 IP 확인
            if hasattr(st, 'session_state') and 'client_ip' in st.session_state:
                cached_ip = st.session_state.client_ip
                if cached_ip and cached_ip not in ["127.0.0.1", "localhost", "unknown"]:
                    return cached_ip
            
            # 2. Streamlit 요청 헤더에서 실제 IP 추출 시도
            real_ip = self._extract_real_ip_from_headers()
            if real_ip and real_ip not in ["127.0.0.1", "localhost"]:
                # 세션에 캐시
                if hasattr(st, 'session_state'):
                    st.session_state.client_ip = real_ip
                return real_ip
            
            # 3. 외부 IP 조회 서비스 사용 (운영환경용)
            external_ip = self._get_external_ip()
            if external_ip and external_ip not in ["127.0.0.1", "localhost"]:
                # 세션에 캐시
                if hasattr(st, 'session_state'):
                    st.session_state.client_ip = external_ip
                return external_ip
            
            # 4. 로컬 네트워크 IP 추출 (개발환경용)
            local_ip = self._get_local_network_ip()
            if local_ip and local_ip != "127.0.0.1":
                return local_ip
            
            # 5. 모든 방법이 실패하면 기본값 반환
            return "127.0.0.1"
            
        except Exception as e:
            print(f"IP 추출 중 오류 발생: {str(e)}")
            return "unknown"
    
    def _extract_real_ip_from_headers(self) -> Optional[str]:
        """HTTP 헤더에서 실제 IP 추출"""
        try:
            # Streamlit의 요청 컨텍스트에서 헤더 정보 추출 시도
            # 주의: Streamlit에서는 직접적인 요청 헤더 접근이 제한적임
            
            # 환경변수나 쿠키를 통해 전달된 IP 정보 확인
            import os
            
            # 일반적인 프록시 헤더들
            header_names = [
                'HTTP_X_FORWARDED_FOR',
                'HTTP_X_REAL_IP',
                'HTTP_X_FORWARDED',
                'HTTP_CF_CONNECTING_IP',  # Cloudflare
                'HTTP_CLIENT_IP',
                'HTTP_X_CLUSTER_CLIENT_IP',
                'REMOTE_ADDR'
            ]
            
            for header_name in header_names:
                if header_value := os.environ.get(header_name):
                    # X-Forwarded-For는 여러 IP가 콤마로 구분될 수 있음
                    if ',' in header_value:
                        # 첫 번째 IP가 원래 클라이언트 IP
                        ip = header_value.split(',')[0].strip()
                    else:
                        ip = header_value.strip()
                    
                    if self._is_valid_ip(ip) and not self._is_private_ip(ip):
                        print(f"헤더에서 IP 추출 성공: {header_name} = {ip}")
                        return ip
            
            return None
            
        except Exception as e:
            print(f"헤더에서 IP 추출 실패: {str(e)}")
            return None
    
    def _get_external_ip(self) -> Optional[str]:
        """외부 IP 조회 서비스를 통한 IP 추출 (운영환경용)"""
        try:
            # 여러 IP 조회 서비스 시도 (타임아웃 짧게 설정)
            services = [
                'https://api.ipify.org?format=text',
                'https://ifconfig.me/ip',
                'https://icanhazip.com',
                'https://ident.me',
                'https://ipecho.net/plain'
            ]
            
            for service in services:
                try:
                    response = requests.get(service, timeout=3)
                    if response.status_code == 200:
                        ip = response.text.strip()
                        if self._is_valid_ip(ip):
                            print(f"외부 서비스에서 IP 조회 성공: {service} = {ip}")
                            return ip
                except:
                    continue
            
            return None
            
        except Exception as e:
            print(f"외부 IP 조회 실패: {str(e)}")
            return None
    
    def _get_local_network_ip(self) -> Optional[str]:
        """로컬 네트워크 IP 추출 (개발환경용)"""
        try:
            # 소켓을 통한 로컬 IP 추출
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                # 구글 DNS에 연결 시도 (실제 데이터 전송하지 않음)
                s.connect(('8.8.8.8', 80))
                local_ip = s.getsockname()[0]
                
                if local_ip and local_ip != "127.0.0.1":
                    print(f"로컬 네트워크 IP 추출: {local_ip}")
                    return local_ip
            
            return None
            
        except Exception as e:
            print(f"로컬 IP 추출 실패: {str(e)}")
            return None
    
    def _is_valid_ip(self, ip: str) -> bool:
        """IP 주소 유효성 검증"""
        try:
            import ipaddress
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False
    
    def _is_private_ip(self, ip: str) -> bool:
        """사설 IP 주소인지 확인"""
        try:
            import ipaddress
            ip_obj = ipaddress.ip_address(ip)
            return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local
        except ValueError:
            return False
    
    def get_user_agent(self) -> str:
        """사용자 에이전트 정보 추출"""
        try:
            import os
            # 환경변수에서 User-Agent 추출 시도
            user_agent = os.environ.get('HTTP_USER_AGENT', 'Streamlit/ChatBot-Enhanced')
            return user_agent
        except:
            return "unknown"
    
    def _analyze_response_quality(self, response_content: str, document_count: int) -> tuple:
        """응답 품질 분석 및 성공/실패 판단 (RAG 기반 답변 여부 포함)"""
        
        # 1. 응답이 없는 경우
        if not response_content or response_content.strip() == "":
            return False, "응답 내용 없음"
        
        # 2. 응답이 너무 짧은 경우 (10자 미만)
        if len(response_content.strip()) < 10:
            return False, "응답 길이 부족"
        
        # 3. 문서 검색 실패
        if document_count == 0:
            return False, "관련 문서 검색 실패"
        
        # 4. 실패 패턴 검사
        for pattern in self.failure_patterns:
            if re.search(pattern, response_content, re.IGNORECASE):
                if "조건.*문서.*찾을 수 없습니다" in pattern:
                    return False, "조건 맞는 문서 없음"
                elif "검색된 문서가 없어서" in pattern:
                    return False, "검색 결과 없음"
                elif "오류가 발생했습니다" in pattern:
                    return False, "시스템 오류"
                else:
                    return False, "적절한 답변 생성 실패"
        
        # 5. RAG 기반 답변인지 판단
        if not self._is_rag_based_response(response_content, document_count):
            return False, "RAG 기반 답변 아님"
        
        # 6. 특정 키워드로 성공 여부 추가 판단
        positive_indicators = [
            "복구방법", "장애원인", "유사 사례", "통계", "건수", "차트", 
            "case1", "case2", "장애 id", "서비스명:", "발생일시:"
        ]
        
        negative_indicators = [
            "찾을 수 없습니다", "없습니다", "오류", "실패", "죄송합니다"
        ]
        
        positive_score = sum(1 for indicator in positive_indicators if indicator in response_content)
        negative_score = sum(1 for indicator in negative_indicators if indicator in response_content)
        
        # 부정적 지표가 많고 긍정적 지표가 적으면 실패로 판단
        if negative_score > positive_score and negative_score >= 2:
            return False, "부정적 응답 패턴 감지"
        
        # 모든 검사를 통과하면 성공
        return True, None

    def _is_rag_based_response(self, response_content: str, document_count: int = None) -> bool:
        """RAG 원천 데이터 기반 답변인지 판단"""
        
        if not response_content:
            return False
        
        response_lower = response_content.lower()
        
        # 1. 문서 수가 매우 적은 경우 (2개 미만)
        if document_count is not None and document_count < 2:
            return False
        
        # 2. RAG 기반 답변의 특징적 마커들 확인
        rag_markers = [
            '[repair_box_start]', '[cause_box_start]', 
            'case1', 'case2', 'case3',
            '장애 id', 'incident_id', 'service_name',
            '복구방법:', '장애원인:', '서비스명:',
            '발생일시:', '장애시간:', '담당부서:',
            '참조장애정보', '장애등급:', 'inm2'
        ]
        
        rag_marker_count = sum(1 for marker in rag_markers if marker in response_lower)
        
        # 3. RAG 기반 답변에 자주 나타나는 패턴들
        rag_patterns = [
            r'장애\s*id\s*:\s*inm\d+',  # INM으로 시작하는 장애 ID
            r'서비스명\s*:\s*\w+',       # 서비스명: 패턴
            r'발생일[시자]\s*:\s*\d{4}', # 발생일시: 년도 패턴
            r'장애시간\s*:\s*\d+분',     # 장애시간: 숫자분 패턴
            r'복구방법\s*:\s*',          # 복구방법: 패턴
            r'장애원인\s*:\s*',          # 장애원인: 패턴
            r'\d+등급',                 # X등급 패턴
            r'incident_repair',         # incident_repair 필드 언급
            r'error_date',              # error_date 필드 언급
            r'case\d+\.',               # Case1. Case2. 패턴
        ]
        
        rag_pattern_count = sum(1 for pattern in rag_patterns if re.search(pattern, response_lower))
        
        # 4. 일반적인 답변 패턴들 (RAG가 아닌 일반 지식 기반)
        general_patterns = [
            r'일반적으로\s+',
            r'보통\s+',
            r'대부분\s+',
            r'흔히\s+',
            r'주로\s+',
            r'다음과\s+같은\s+방법',
            r'다음\s+단계',
            r'기본적인\s+',
            r'표준적인\s+',
            r'권장사항',
            r'best\s+practice',
            r'모범\s+사례',
            r'다음과\s+같이\s+접근',
            r'시스템\s+관리자',
            r'네트워크\s+관리',
            r'서버\s+관리',
        ]
        
        general_pattern_count = sum(1 for pattern in general_patterns if re.search(pattern, response_lower))
        
        # 5. RAG 답변에서 흔히 사용되지 않는 일반적 표현들
        non_rag_keywords = [
            '일반적으로', '보통', '대부분', '흔히', '주로',
            '기본적으로', '표준적으로', '권장사항', '모범사례',
            '다음과 같은 방법', '다음 단계', '기본적인 점검',
            '시스템 관리', '네트워크 관리', '서버 관리',
            '일반적인 해결책', '표준 절차', '기본 원칙'
        ]
        
        non_rag_keyword_count = sum(1 for keyword in non_rag_keywords if keyword in response_lower)
        
        # 6. 특정 질문 유형별 RAG 기반 판단
        statistics_indicators = ['건수', '통계', '현황', '분포', '년도별', '월별', '차트']
        statistics_count = sum(1 for indicator in statistics_indicators if indicator in response_lower)
        
        # 7. 판단 로직
        # RAG 마커나 패턴이 충분히 있으면 RAG 기반으로 판단
        if rag_marker_count >= 3 or rag_pattern_count >= 2:
            return True
        
        # 통계 관련 답변이고 통계 지표가 있으면 RAG 기반으로 판단
        if statistics_count >= 2 and any(word in response_lower for word in ['차트', '표', '총', '합계']):
            return True
        
        # 일반적 표현이 많고 RAG 특징이 적으면 일반 답변으로 판단
        if general_pattern_count >= 2 or non_rag_keyword_count >= 3:
            if rag_marker_count == 0 and rag_pattern_count == 0:
                return False
        
        # RAG 마커가 하나라도 있으면 RAG 기반으로 판단
        if rag_marker_count > 0 or rag_pattern_count > 0:
            return True
        
        # 응답이 길고 구체적이면서 문서가 충분히 있으면 RAG 기반으로 판단
        if len(response_content) > 200 and document_count and document_count >= 3:
            # 하지만 일반적 표현이 너무 많으면 제외
            if non_rag_keyword_count < 2:
                return True
        
        # 기본적으로 일반 답변으로 판단
        return False

    def log_query(self, question: str, query_type: str = None, 
                  response_time: float = None, document_count: int = None,
                  success: bool = None, error_message: str = None,
                  response_content: str = None, source: str = "middleware"):
        """향상된 쿼리 로그 기록 - 실제 IP 추출 개선"""
        try:
            # 디버그 로그 추가
            print(f"[{source.upper()}] 로깅 시작: {question[:30]}...")
            
            # 중복 로깅 방지 체크
            if hasattr(st.session_state, 'current_query_logged') and st.session_state.current_query_logged:
                print(f"[{source.upper()}] 이미 로깅된 쿼리 - 중복 로깅 방지")
                return
            
            # 개선된 IP 추출
            ip_address = self.get_client_ip()
            print(f"[{source.upper()}] 추출된 IP 주소: {ip_address}")
            
            user_agent = self.get_user_agent()
            
            # success가 지정되지 않은 경우 자동 분석
            if success is None and response_content:
                success, auto_error = self._analyze_response_quality(response_content, document_count or 0)
                if auto_error and not error_message:
                    error_message = auto_error
            
            # 오류 메시지 길이 제한 (50자)
            if error_message and len(error_message) > 50:
                error_message = error_message[:50] + "..."
            
            self.monitoring_manager.log_user_activity(
                ip_address=ip_address,
                question=question,
                query_type=query_type,
                user_agent=user_agent,
                response_time=response_time,
                document_count=document_count,
                success=success,
                error_message=error_message,
                response_content=response_content
            )
            
            # 로깅 완료 표시
            if hasattr(st.session_state, 'current_query_logged'):
                st.session_state.current_query_logged = True
                
            print(f"[{source.upper()}] 로깅 완료 - IP: {ip_address}, Success: {success}")
            
        except Exception as e:
            # 로깅 실패해도 메인 기능에는 영향을 주지 않음
            print(f"[{source.upper()}] 로깅 실패: {str(e)}")

# IP 주소 강제 설정 유틸리티 (개발/테스트용)
def set_client_ip(ip_address: str):
    """클라이언트 IP 주소 강제 설정 (개발/테스트용)"""
    if hasattr(st, 'session_state'):
        st.session_state.client_ip = ip_address
        print(f"IP 주소 강제 설정: {ip_address}")

# IP 주소 초기화 (운영환경에서 자동 감지 위해)
def reset_client_ip():
    """클라이언트 IP 주소 초기화 (자동 감지하도록)"""
    if hasattr(st, 'session_state') and 'client_ip' in st.session_state:
        del st.session_state.client_ip
        print("IP 주소 초기화 완료 - 자동 감지 모드로 전환")

# 기존 함수들은 그대로 유지 (하위 호환성)
def log_user_activity_disabled(query_type: str = None):
    """비활성화된 로깅 데코레이터 - 중복 방지용"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            print(f"[DECORATOR-DISABLED] 데코레이터 로깅이 비활성화됨 - 함수만 실행")
            return func(*args, **kwargs)
        return wrapper
    return decorator

def log_user_activity_conditional(query_type: str = None, enable_logging: bool = True):
    """조건부 사용자 활동 로깅 데코레이터"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            if not enable_logging:
                print(f"[DECORATOR-CONDITIONAL] 로깅 비활성화 - 함수만 실행")
                return func(*args, **kwargs)
                
            start_time = time.time()
            middleware = LoggingMiddleware()
            
            question = ""
            response_content = ""
            document_count = 0
            success = None
            error_message = None
            
            try:
                if hasattr(st.session_state, 'current_query_logged') and st.session_state.current_query_logged:
                    print(f"[DECORATOR-CONDITIONAL] 이미 로깅됨 - 중복 방지")
                    return func(*args, **kwargs)
                
                result = func(*args, **kwargs)
                response_time = time.time() - start_time
                question = kwargs.get('query', '') or (args[1] if len(args) > 1 else '')
                
                if isinstance(result, (list, tuple)):
                    if len(result) >= 2:
                        if isinstance(result[0], str):
                            response_content = result[0]
                            if isinstance(result[1], (list, tuple)):
                                document_count = len(result[1])
                        elif isinstance(result[1], (list, tuple)):
                            document_count = len(result[1])
                elif isinstance(result, str):
                    response_content = result
                elif hasattr(result, '__len__'):
                    document_count = len(result)
                
                if response_content:
                    success, auto_error = middleware._analyze_response_quality(response_content, document_count)
                    if auto_error:
                        error_message = auto_error
                else:
                    success = True
                
                middleware.log_query(
                    question=str(question),
                    query_type=query_type,
                    response_time=response_time,
                    document_count=document_count,
                    success=success,
                    error_message=error_message,
                    response_content=response_content,
                    source="decorator"
                )
                
                return result
                
            except Exception as e:
                response_time = time.time() - start_time
                question = kwargs.get('query', '') or (args[1] if len(args) > 1 else '')
                error_message = str(e)[:50] + ("..." if len(str(e)) > 50 else "")
                
                middleware.log_query(
                    question=str(question),
                    query_type=query_type,
                    response_time=response_time,
                    document_count=0,
                    success=False,
                    error_message=error_message,
                    response_content="",
                    source="decorator"
                )
                
                raise
        
        return wrapper
    return decorator

def log_user_activity(query_type: str = None):
    """기존 로깅 데코레이터 - 중복 방지를 위해 비활성화"""
    print(f"[DECORATOR-LEGACY] 기존 로깅 데코레이터 호출 - 중복 방지를 위해 비활성화")
    return log_user_activity_disabled(query_type)

def apply_logging_to_query_processor(query_processor):
    """쿼리 프로세서에 로깅 기능 추가 - 개선된 IP 추출 포함"""
    print("=" * 60)
    print("[APPLY_LOGGING] apply_logging_to_query_processor 호출됨")
    print("[APPLY_LOGGING] 개선된 IP 추출 로직이 적용됩니다")
    print("=" * 60)
    
    query_processor._decorator_logging_enabled = False
    query_processor._manual_logging_enabled = True
    query_processor._logging_source = "manual_only"
    query_processor._enhanced_ip_extraction = True  # 개선된 IP 추출 플래그
    
    print("[APPLY_LOGGING] 설정 완료 - 수동 로깅만 활성화 (개선된 IP 추출)")
    return query_processor

# 실시간 IP 추출 테스트 함수
def test_ip_extraction():
    """IP 추출 로직 테스트"""
    middleware = LoggingMiddleware()
    detected_ip = middleware.get_client_ip()
    
    print("=" * 50)
    print("IP 추출 테스트 결과")
    print("=" * 50)
    print(f"감지된 IP 주소: {detected_ip}")
    
    if detected_ip == "127.0.0.1":
        print("⚠️  로컬호스트 IP가 감지되었습니다.")
        print("운영환경에서는 프록시 설정을 확인해주세요.")
    elif detected_ip == "unknown":
        print("❌ IP 추출에 실패했습니다.")
    else:
        print("✅ 실제 IP 주소가 성공적으로 추출되었습니다.")
    
    print("=" * 50)
    return detected_ip

# 채팅 상호작용 직접 로깅 (개선된 IP 추출 포함)
def log_chat_interaction(question: str, response: str, query_type: str = None, 
                        document_count: int = 0, response_time: float = None):
    """채팅 상호작용 직접 로깅 - 개선된 IP 추출"""
    middleware = LoggingMiddleware()
    middleware.log_query(
        question=question,
        query_type=query_type,
        response_time=response_time,
        document_count=document_count,
        response_content=response,
        source="chat_interaction"
    )

# 기타 기존 함수들도 그대로 유지
def log_page_visit(page_name: str):
    """페이지 방문 로깅"""
    middleware = LoggingMiddleware()
    middleware.log_query(
        question=f"페이지 방문: {page_name}",
        query_type="page_visit",
        success=True,
        response_content=f"페이지 방문: {page_name}",
        source="page_visit"
    )

def get_recent_activity_summary(hours: int = 1):
    """최근 활동 요약 정보 반환"""
    try:
        monitoring_manager = MonitoringManager()
        from datetime import datetime, timedelta
        
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        logs = monitoring_manager.get_logs_in_range(start_time.date(), end_time.date())
        
        recent_logs = [
            log for log in logs 
            if datetime.fromisoformat(log['timestamp']) >= start_time
        ]
        
        if not recent_logs:
            return {
                'total_queries': 0,
                'successful_queries': 0,
                'failed_queries': 0,
                'success_rate': 0,
                'avg_response_time': 0
            }
        
        successful = sum(1 for log in recent_logs if log.get('success'))
        failed = len(recent_logs) - successful
        success_rate = (successful / len(recent_logs) * 100) if recent_logs else 0
        
        response_times = [log.get('response_time', 0) for log in recent_logs if log.get('response_time')]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        return {
            'total_queries': len(recent_logs),
            'successful_queries': successful,
            'failed_queries': failed,
            'success_rate': success_rate,
            'avg_response_time': avg_response_time
        }
    except Exception as e:
        print(f"최근 활동 요약 조회 실패: {str(e)}")
        return None

def get_failure_analysis(hours: int = 24):
    """실패 분석 정보 반환"""
    try:
        monitoring_manager = MonitoringManager()
        from datetime import datetime, timedelta
        
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        logs = monitoring_manager.get_logs_in_range(start_time.date(), end_time.date())
        
        failed_logs = [
            log for log in logs 
            if datetime.fromisoformat(log['timestamp']) >= start_time and not log.get('success')
        ]
        
        if not failed_logs:
            return {'total_failures': 0, 'failure_reasons': {}}
        
        failure_reasons = {}
        for log in failed_logs:
            reason = log.get('error_message', '알 수 없는 오류')
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
        
        return {
            'total_failures': len(failed_logs),
            'failure_reasons': dict(sorted(failure_reasons.items(), key=lambda x: x[1], reverse=True))
        }
    except Exception as e:
        print(f"실패 분석 조회 실패: {str(e)}")
        return None

def debug_logging_status(query_processor):
    """로깅 상태 디버깅 - 개선된 IP 추출 포함"""
    print("=" * 50)
    print("[DEBUG_LOGGING_STATUS] 로깅 상태 확인")
    print("=" * 50)
    
    decorator_enabled = getattr(query_processor, '_decorator_logging_enabled', 'UNKNOWN')
    manual_enabled = getattr(query_processor, '_manual_logging_enabled', 'UNKNOWN')
    logging_applied = getattr(query_processor, '_logging_applied', 'UNKNOWN')
    logging_source = getattr(query_processor, '_logging_source', 'UNKNOWN')
    enhanced_ip = getattr(query_processor, '_enhanced_ip_extraction', 'UNKNOWN')
    
    print(f"Decorator Logging Enabled: {decorator_enabled}")
    print(f"Manual Logging Enabled: {manual_enabled}")
    print(f"Logging Applied: {logging_applied}")
    print(f"Logging Source: {logging_source}")
    print(f"Enhanced IP Extraction: {enhanced_ip}")
    
    # 세션 상태 확인
    if hasattr(st.session_state, 'current_query_logged'):
        print(f"Session Current Query Logged: {st.session_state.current_query_logged}")
    else:
        print("Session Current Query Logged: NOT_SET")
    
    # IP 추출 테스트
    print("\n--- IP 추출 테스트 ---")
    test_ip_extraction()
    
    print("=" * 50)