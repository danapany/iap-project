# utils/logging_middleware.py
import streamlit as st
import time
import functools
from datetime import datetime
from typing import Any, Callable, Optional
from utils.monitoring_manager import MonitoringManager

class LoggingMiddleware:
    """사용자 활동 로깅 미들웨어"""
    
    def __init__(self):
        self.monitoring_manager = MonitoringManager()
    
    def get_client_ip(self) -> str:
        """클라이언트 IP 주소 추출"""
        try:
            # Streamlit에서 IP 주소를 직접 가져오기는 어려우므로 
            # 세션 정보나 헤더를 통해 가져오거나 임시값 사용
            if hasattr(st, 'session_state') and 'client_ip' in st.session_state:
                return st.session_state.client_ip
            
            # 개발 환경에서는 임시 IP 사용
            return "127.0.0.1"
        except:
            return "unknown"
    
    def get_user_agent(self) -> str:
        """사용자 에이전트 정보 추출"""
        try:
            # 실제 운영환경에서는 HTTP 헤더에서 추출
            return "Streamlit/Unknown"
        except:
            return "unknown"
    
    def log_query(self, question: str, query_type: str = None, 
                  response_time: float = None, document_count: int = None,
                  success: bool = True, error_message: str = None):
        """쿼리 로그 기록"""
        try:
            ip_address = self.get_client_ip()
            user_agent = self.get_user_agent()
            
            self.monitoring_manager.log_user_activity(
                ip_address=ip_address,
                question=question,
                query_type=query_type,
                user_agent=user_agent,
                response_time=response_time,
                document_count=document_count,
                success=success,
                error_message=error_message
            )
        except Exception as e:
            # 로깅 실패해도 메인 기능에는 영향을 주지 않음
            print(f"로깅 실패: {str(e)}")

def log_user_activity(query_type: str = None):
    """사용자 활동 로깅 데코레이터"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            middleware = LoggingMiddleware()
            
            try:
                # 함수 실행
                result = func(*args, **kwargs)
                
                # 성공 로그 기록
                response_time = time.time() - start_time
                
                # 함수 매개변수에서 질문과 문서 수 추출
                question = kwargs.get('query', '') or (args[0] if args else '')
                document_count = None
                
                if isinstance(result, (list, tuple)):
                    if len(result) >= 2 and isinstance(result[1], (list, tuple)):
                        document_count = len(result[1])
                elif hasattr(result, '__len__'):
                    document_count = len(result)
                
                middleware.log_query(
                    question=str(question),
                    query_type=query_type,
                    response_time=response_time,
                    document_count=document_count,
                    success=True
                )
                
                return result
                
            except Exception as e:
                # 실패 로그 기록
                response_time = time.time() - start_time
                question = kwargs.get('query', '') or (args[0] if args else '')
                
                middleware.log_query(
                    question=str(question),
                    query_type=query_type,
                    response_time=response_time,
                    success=False,
                    error_message=str(e)
                )
                
                raise  # 원래 예외를 다시 발생시킴
        
        return wrapper
    return decorator

def log_page_visit(page_name: str):
    """페이지 방문 로깅"""
    middleware = LoggingMiddleware()
    middleware.log_query(
        question=f"페이지 방문: {page_name}",
        query_type="page_visit",
        success=True
    )

# IP 주소 설정 유틸리티 (개발용)
def set_client_ip(ip_address: str):
    """클라이언트 IP 주소 설정 (개발/테스트용)"""
    st.session_state.client_ip = ip_address

# 실제 쿼리 프로세서에 로깅 적용하는 헬퍼 함수
def apply_logging_to_query_processor(query_processor):
    """기존 쿼리 프로세서에 로깅 기능 추가"""
    original_process_query = query_processor.process_query
    
    @log_user_activity(query_type="chatbot")
    def logged_process_query(query, query_type=None):
        return original_process_query(query, query_type)
    
    query_processor.process_query = logged_process_query
    return query_processor