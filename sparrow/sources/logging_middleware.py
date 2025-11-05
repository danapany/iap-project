# utils/logging_middleware.py - 경량화 버전
import streamlit as st
import time
import functools
import re
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
from utils.monitoring_manager import MonitoringManager

class LoggingMiddleware:
    """사용자 활동 로깅 미들웨어 - 중복 로깅 방지 개선 버전"""
    
    def __init__(self):
        self.monitoring_manager = MonitoringManager()
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
        try:
            return getattr(st.session_state, 'client_ip', "127.0.0.1")
        except:
            return "unknown"
    
    def get_user_agent(self) -> str:
        return "Streamlit/ChatBot-Enhanced"
    
    def _analyze_response_quality(self, response_content: str, document_count: int) -> tuple:
        """응답 품질 분석 및 성공/실패 판단 (RAG 기반 답변 여부 포함)"""
        if not response_content or len(response_content.strip()) < 10:
            return False, "응답 내용 부족"
        
        if document_count == 0:
            return False, "관련 문서 검색 실패"
        
        for pattern in self.failure_patterns:
            if re.search(pattern, response_content, re.IGNORECASE):
                return False, "적절한 답변 생성 실패"
        
        if not self._is_rag_based_response(response_content, document_count):
            return False, "RAG 기반 답변 아님"
        
        positive_indicators = ["복구방법", "장애원인", "유사 사례", "통계", "건수", "차트", "case1", "case2", "장애 id", "서비스명:", "발생일시:"]
        negative_indicators = ["찾을 수 없습니다", "없습니다", "오류", "실패", "죄송합니다"]
        
        positive_score = sum(1 for indicator in positive_indicators if indicator in response_content)
        negative_score = sum(1 for indicator in negative_indicators if indicator in response_content)
        
        if negative_score > positive_score and negative_score >= 2:
            return False, "부정적 응답 패턴 감지"
        
        return True, None

    def _is_rag_based_response(self, response_content: str, document_count: int = None) -> bool:
        """RAG 원천 데이터 기반 답변인지 판단"""
        if not response_content or (document_count is not None and document_count < 2):
            return False
        
        response_lower = response_content.lower()
        
        rag_markers = ['[repair_box_start]', '[cause_box_start]', 'case1', 'case2', 'case3', '장애 id', 'incident_id', 'service_name', '복구방법:', '장애원인:', '서비스명:', '발생일시:', '장애시간:', '담당부서:', '참조장애정보', '장애등급:', 'inm2']
        rag_marker_count = sum(1 for marker in rag_markers if marker in response_lower)
        
        rag_patterns = [r'장애\s*id\s*:\s*inm\d+', r'서비스명\s*:\s*\w+', r'발생일[시자]\s*:\s*\d{4}', r'장애시간\s*:\s*\d+분', r'복구방법\s*:\s*', r'장애원인\s*:\s*', r'\d+등급', r'incident_repair', r'error_date', r'case\d+\.']
        rag_pattern_count = sum(1 for pattern in rag_patterns if re.search(pattern, response_lower))
        
        non_rag_keywords = ['일반적으로', '보통', '대부분', '흔히', '주로', '기본적으로', '표준적으로', '권장사항', '모범사례', '다음과 같은 방법', '다음 단계', '기본적인 점검', '시스템 관리', '네트워크 관리', '서버 관리', '일반적인 해결책', '표준 절차', '기본 원칙']
        non_rag_keyword_count = sum(1 for keyword in non_rag_keywords if keyword in response_lower)
        
        statistics_indicators = ['건수', '통계', '현황', '분포', '년도별', '월별', '차트']
        statistics_count = sum(1 for indicator in statistics_indicators if indicator in response_lower)
        
        if rag_marker_count >= 3 or rag_pattern_count >= 2:
            return True
        
        if statistics_count >= 2 and any(word in response_lower for word in ['차트', '표', '총', '합계']):
            return True
        
        if non_rag_keyword_count >= 3 and rag_marker_count == 0 and rag_pattern_count == 0:
            return False
        
        if rag_marker_count > 0 or rag_pattern_count > 0:
            return True
        
        if len(response_content) > 200 and document_count and document_count >= 3 and non_rag_keyword_count < 2:
            return True
        
        return False

    def log_query(self, question: str, query_type: str = None, response_time: float = None, 
                  document_count: int = None, success: bool = None, error_message: str = None,
                  response_content: str = None, source: str = "middleware"):
        """향상된 쿼리 로그 기록 - 중복 방지"""
        try:
            if getattr(st.session_state, 'current_query_logged', False):
                return
            
            if success is None and response_content:
                success, auto_error = self._analyze_response_quality(response_content, document_count or 0)
                if auto_error and not error_message:
                    error_message = auto_error
            
            if error_message and len(error_message) > 50:
                error_message = error_message[:50] + "..."
            
            self.monitoring_manager.log_user_activity(
                ip_address=self.get_client_ip(),
                question=question,
                query_type=query_type,
                user_agent=self.get_user_agent(),
                response_time=response_time,
                document_count=document_count,
                success=success,
                error_message=error_message,
                response_content=response_content
            )
            
            st.session_state.current_query_logged = True
            
        except Exception as e:
            print(f"로깅 실패: {str(e)}")

def log_user_activity_disabled(query_type: str = None):
    """비활성화된 로깅 데코레이터"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            return func(*args, **kwargs)
        return wrapper
    return decorator

def log_user_activity_conditional(query_type: str = None, enable_logging: bool = True):
    """조건부 사용자 활동 로깅 데코레이터"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            if not enable_logging or getattr(st.session_state, 'current_query_logged', False):
                return func(*args, **kwargs)
                
            start_time = time.time()
            middleware = LoggingMiddleware()
            
            try:
                result = func(*args, **kwargs)
                response_time = time.time() - start_time
                
                question = kwargs.get('query', '') or (args[1] if len(args) > 1 else '')
                response_content = ""
                document_count = 0
                
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
                
                success, error_message = (middleware._analyze_response_quality(response_content, document_count) 
                                        if response_content else (True, None))
                
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
    return log_user_activity_disabled(query_type)

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

def log_chat_interaction(question: str, response: str, query_type: str = None, 
                        document_count: int = 0, response_time: float = None):
    """채팅 상호작용 직접 로깅"""
    middleware = LoggingMiddleware()
    middleware.log_query(
        question=question,
        query_type=query_type,
        response_time=response_time,
        document_count=document_count,
        response_content=response,
        source="chat_interaction"
    )

def set_client_ip(ip_address: str):
    """클라이언트 IP 주소 설정"""
    st.session_state.client_ip = ip_address

def apply_logging_to_query_processor(query_processor):
    """쿼리 프로세서에 로깅 기능 추가 - 중복 방지 버전"""
    query_processor._decorator_logging_enabled = False
    query_processor._manual_logging_enabled = True
    query_processor._logging_source = "manual_only"
    return query_processor

def apply_logging_to_query_processor_force_decorator(query_processor):
    """강제로 데코레이터 로깅 적용"""
    if hasattr(query_processor, '_logging_applied'):
        return query_processor
    
    original_process_query = query_processor.process_query
    
    @log_user_activity_conditional(query_type="chatbot", enable_logging=True)
    def logged_process_query(query, query_type=None):
        return original_process_query(query, query_type)
    
    query_processor.process_query = logged_process_query
    query_processor._logging_applied = True
    query_processor._decorator_logging_enabled = True
    query_processor._manual_logging_enabled = False
    query_processor._logging_source = "decorator_only"
    
    return query_processor

def apply_logging_to_query_processor_safe(query_processor):
    """안전한 로깅 적용 - 기존 설정 확인 후 적용"""
    decorator_enabled = getattr(query_processor, '_decorator_logging_enabled', None)
    manual_enabled = getattr(query_processor, '_manual_logging_enabled', None)
    
    if decorator_enabled is None and manual_enabled is None:
        query_processor._decorator_logging_enabled = False
        query_processor._manual_logging_enabled = True
        query_processor._logging_source = "safe_manual"
    
    return query_processor

def get_recent_activity_summary(hours: int = 1):
    """최근 활동 요약 정보 반환"""
    try:
        monitoring_manager = MonitoringManager()
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        logs = monitoring_manager.get_logs_in_range(start_time.date(), end_time.date())
        recent_logs = [log for log in logs if datetime.fromisoformat(log['timestamp']) >= start_time]
        
        if not recent_logs:
            return {'total_queries': 0, 'successful_queries': 0, 'failed_queries': 0, 'success_rate': 0, 'avg_response_time': 0}
        
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
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        logs = monitoring_manager.get_logs_in_range(start_time.date(), end_time.date())
        failed_logs = [log for log in logs if datetime.fromisoformat(log['timestamp']) >= start_time and not log.get('success')]
        
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
    """로깅 상태 디버깅"""
    print("=" * 50)
    print("[DEBUG] 로깅 상태 확인")
    print("=" * 50)
    
    attrs = ['_decorator_logging_enabled', '_manual_logging_enabled', '_logging_applied', '_logging_source']
    for attr in attrs:
        print(f"{attr}: {getattr(query_processor, attr, 'UNKNOWN')}")
    
    print(f"Session Current Query Logged: {getattr(st.session_state, 'current_query_logged', 'NOT_SET')}")
    print("=" * 50)