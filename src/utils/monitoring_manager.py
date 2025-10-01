# utils/monitoring_manager.py
import json
import os
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import List, Dict, Any, Optional
import re
from pathlib import Path
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

def get_monitoring_db_path():
    """환경변수에서 모니터링 DB 경로 가져오기"""
    base_path = os.getenv('DB_BASE_PATH', 'data/db')
    return os.path.join(base_path, 'monitoring.db')

class MonitoringManager:
    """사용자 활동 모니터링 관리 클래스"""
    
    def __init__(self, db_path: str = None):
        """모니터링 매니저 초기화"""
        # db_path가 제공되지 않으면 환경변수에서 가져오기
        if db_path is None:
            db_path = get_monitoring_db_path()
        
        self.db_path = db_path
        self.ensure_db_directory()
        self.init_database()
        
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
    
    def ensure_db_directory(self):
        """데이터베이스 디렉토리 생성"""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
    
    def init_database(self):
        """데이터베이스 초기화"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 사용자 활동 로그 테이블
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    ip_address TEXT NOT NULL,
                    user_agent TEXT,
                    question TEXT NOT NULL,
                    query_type TEXT,
                    response_time REAL,
                    document_count INTEGER,
                    success BOOLEAN,
                    error_message TEXT,
                    response_content TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 기존 테이블에 response_content 컬럼이 없다면 추가
            cursor.execute("PRAGMA table_info(user_logs)")
            columns = [column[1] for column in cursor.fetchall()]
            if 'response_content' not in columns:
                cursor.execute('ALTER TABLE user_logs ADD COLUMN response_content TEXT')
            
            # IP 통계 테이블
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ip_stats (
                    ip_address TEXT PRIMARY KEY,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    total_queries INTEGER DEFAULT 0,
                    successful_queries INTEGER DEFAULT 0,
                    failed_queries INTEGER DEFAULT 0,
                    avg_response_time REAL DEFAULT 0.0,
                    is_suspicious BOOLEAN DEFAULT FALSE,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 일별 통계 테이블
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_stats (
                    date TEXT PRIMARY KEY,
                    total_queries INTEGER DEFAULT 0,
                    unique_ips INTEGER DEFAULT 0,
                    avg_response_time REAL DEFAULT 0.0,
                    query_types_json TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
    
    def _determine_response_success(self, response_content: str = None, error_message: str = None, document_count: int = None) -> tuple:
            """답변 성공/실패 여부와 오류 메시지 판단 (RAG 기반 답변 여부 포함)"""
            
            # 1. 명시적 오류가 있는 경우
            if error_message:
                truncated_error = (error_message[:50] + '...') if len(error_message) > 50 else error_message
                return False, truncated_error
            
            # 2. 응답 내용이 없는 경우
            if not response_content or response_content.strip() == "":
                return False, "응답 내용 없음"
            
            # 3. 응답 내용에서 실패 패턴 검사
            if response_content:
                for pattern in self.failure_patterns:
                    if re.search(pattern, response_content, re.IGNORECASE):
                        return False, "적절한 답변 생성 실패"
            
            # 4. 문서 수가 0인 경우 (검색 실패)
            if document_count is not None and document_count == 0:
                return False, "관련 문서 검색 실패"
            
            # 5. 응답이 너무 짧은 경우 (10자 미만)
            if response_content and len(response_content.strip()) < 10:
                return False, "응답 길이 부족"
            
            # 6. RAG 기반 답변인지 판단
            if response_content and not self._is_rag_based_response(response_content, document_count):
                return False, "RAG 데이터 기반 답변 아님"
            
            # 모든 조건을 통과하면 성공
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
            '[REPAIR_BOX_START]', '[CAUSE_BOX_START]', 
            'case1', 'case2', 'case3',
            '장애 id', 'incident_id', 'service_name',
            '복구방법:', '장애원인:', '서비스명:',
            '발생일시:', '장애시간:', '담당부서:',
            '참조장애정보', '장애등급:'
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
            r'일반적인\s+',
            r'표준적인\s+',
            r'권장사항',
            r'best\s+practice',
            r'모범\s+사례',
            r'다음과\s+같이\s+접근',
        ]
        
        general_pattern_count = sum(1 for pattern in general_patterns if re.search(pattern, response_lower))
        
        # 5. RAG 답변에서 흔히 사용되지 않는 일반적 표현들
        non_rag_keywords = [
            '일반적으로', '보통', '대부분', '흔히', '주로',
            '기본적으로', '표준적으로', '권장사항', '모범사례',
            '다음과 같은 방법', '다음 단계', '기본적인 점검',
            '시스템 관리', '네트워크 관리', '서버 관리'
        ]
        
        non_rag_keyword_count = sum(1 for keyword in non_rag_keywords if keyword in response_lower)
        
        # 6. 특정 질문 유형별 RAG 기반 판단
        statistics_indicators = ['건수', '통계', '현황', '분포', '년도별', '월별']
        statistics_count = sum(1 for indicator in statistics_indicators if indicator in response_lower)
        
        # 7. 판단 로직
        # RAG 마커나 패턴이 충분히 있으면 RAG 기반으로 판단
        if rag_marker_count >= 3 or rag_pattern_count >= 2:
            return True
        
        # 통계 관련 답변이고 통계 지표가 있으면 RAG 기반으로 판단
        if statistics_count >= 2 and ('차트' in response_lower or '표' in response_lower):
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
            return True
        
        # 기본적으로 일반 답변으로 판단
        return False

    def _classify_failure_reason(self, response_content: str, document_count: int) -> str:
        """실패 원인을 더 구체적으로 분류"""
        
        if not response_content or response_content.strip() == "":
            return "응답 내용 없음"
        
        if document_count == 0:
            return "관련 문서 검색 실패"
        
        if len(response_content.strip()) < 10:
            return "응답 길이 부족"
        
        response_lower = response_content.lower()
        
        # 실패 패턴별 세분화
        if re.search(r"해당.*조건.*문서.*찾을 수 없습니다", response_content, re.IGNORECASE):
            return "조건 맞는 문서 없음"
        
        if re.search(r"검색된 문서가 없어서", response_content, re.IGNORECASE):
            return "검색 결과 없음"
        
        if re.search(r"오류가 발생했습니다", response_content, re.IGNORECASE):
            return "시스템 오류 발생"
        
        if re.search(r"답변을 생성할 수 없습니다", response_content, re.IGNORECASE):
            return "답변 생성 실패"
        
        # RAG 기반이 아닌 일반 답변인 경우
        if not self._is_rag_based_response(response_content, document_count):
            return "RAG 기반 답변 아님"
        
        return "적절한 답변 생성 실패"

    def log_user_activity(self, ip_address: str, question: str, query_type: str = None, 
                         user_agent: str = None, response_time: float = None,
                         document_count: int = None, success: bool = None, 
                         error_message: str = None, response_content: str = None):
        """사용자 활동 로그 기록 (향상된 버전)"""
        try:
            timestamp = datetime.now().isoformat()
            
            # success가 명시되지 않은 경우 자동 판단
            if success is None:
                success, auto_error_message = self._determine_response_success(
                    response_content, error_message, document_count
                )
                # 자동 판단된 오류 메시지가 있고 기존 error_message가 없으면 사용
                if auto_error_message and not error_message:
                    error_message = auto_error_message
            
            # 오류 메시지 길이 제한 (50자)
            if error_message and len(error_message) > 50:
                error_message = error_message[:50] + "..."
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 로그 기록
                cursor.execute('''
                    INSERT INTO user_logs 
                    (timestamp, ip_address, user_agent, question, query_type, 
                     response_time, document_count, success, error_message, response_content)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (timestamp, ip_address, user_agent, question, query_type,
                      response_time, document_count, success, error_message, 
                      response_content[:1000] if response_content else None))  # 응답 내용도 길이 제한
                
                # IP 통계 업데이트
                self._update_ip_stats(cursor, ip_address, response_time, success)
                
                # 일별 통계 업데이트
                self._update_daily_stats(cursor, query_type, response_time)
                
                conn.commit()
                
        except Exception as e:
            print(f"로그 기록 실패: {str(e)}")
    
    def _update_ip_stats(self, cursor, ip_address: str, response_time: float = None, success: bool = True):
        """IP 통계 업데이트"""
        now = datetime.now().isoformat()
        
        # 기존 IP 통계 조회
        cursor.execute('SELECT * FROM ip_stats WHERE ip_address = ?', (ip_address,))
        existing = cursor.fetchone()
        
        if existing:
            # 기존 통계 업데이트
            total_queries = existing[3] + 1
            successful_queries = existing[4] + (1 if success else 0)
            failed_queries = existing[5] + (0 if success else 1)
            
            # 평균 응답 시간 계산
            if response_time and existing[6]:
                avg_response_time = (existing[6] * existing[3] + response_time) / total_queries
            elif response_time:
                avg_response_time = response_time
            else:
                avg_response_time = existing[6]
            
            cursor.execute('''
                UPDATE ip_stats 
                SET last_seen = ?, total_queries = ?, successful_queries = ?,
                    failed_queries = ?, avg_response_time = ?, updated_at = ?
                WHERE ip_address = ?
            ''', (now, total_queries, successful_queries, failed_queries,
                  avg_response_time, now, ip_address))
        else:
            # 새 IP 통계 생성
            cursor.execute('''
                INSERT INTO ip_stats 
                (ip_address, first_seen, last_seen, total_queries, successful_queries,
                 failed_queries, avg_response_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (ip_address, now, now, 1, 1 if success else 0, 0 if success else 1,
                  response_time or 0.0))
    
    def _update_daily_stats(self, cursor, query_type: str = None, response_time: float = None):
        """일별 통계 업데이트"""
        today = datetime.now().date().isoformat()
        
        # 기존 일별 통계 조회
        cursor.execute('SELECT * FROM daily_stats WHERE date = ?', (today,))
        existing = cursor.fetchone()
        
        if existing:
            # 기존 통계 업데이트
            total_queries = existing[1] + 1
            
            # 질문 유형 통계 업데이트
            try:
                query_types = json.loads(existing[4]) if existing[4] else {}
            except:
                query_types = {}
            
            if query_type:
                query_types[query_type] = query_types.get(query_type, 0) + 1
            
            # 평균 응답 시간 계산
            if response_time and existing[3]:
                avg_response_time = (existing[3] * existing[1] + response_time) / total_queries
            elif response_time:
                avg_response_time = response_time
            else:
                avg_response_time = existing[3]
            
            cursor.execute('''
                UPDATE daily_stats 
                SET total_queries = ?, avg_response_time = ?, query_types_json = ?, updated_at = ?
                WHERE date = ?
            ''', (total_queries, avg_response_time, json.dumps(query_types),
                  datetime.now().isoformat(), today))
        else:
            # 새 일별 통계 생성
            query_types = {query_type: 1} if query_type else {}
            
            cursor.execute('''
                INSERT INTO daily_stats 
                (date, total_queries, unique_ips, avg_response_time, query_types_json)
                VALUES (?, ?, ?, ?, ?)
            ''', (today, 1, 1, response_time or 0.0, json.dumps(query_types)))
    
    def get_logs_in_range(self, start_date, end_date) -> List[Dict[str, Any]]:
        """지정된 기간의 로그 조회 (답변유무와 오류메시지 포함)"""
        start_str = start_date.isoformat()
        end_str = (end_date + timedelta(days=1)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT timestamp, ip_address, user_agent, question, query_type,
                       response_time, document_count, success, error_message, response_content
                FROM user_logs 
                WHERE timestamp >= ? AND timestamp < ?
                ORDER BY timestamp DESC
            ''', (start_str, end_str))
            
            rows = cursor.fetchall()
            
            return [
                {
                    'timestamp': row[0],
                    'ip_address': row[1],
                    'user_agent': row[2],
                    'question': row[3],
                    'query_type': row[4],
                    'response_time': row[5],
                    'document_count': row[6],
                    'success': row[7],
                    'error_message': row[8],
                    'response_content': row[9]
                }
                for row in rows
            ]

    # 기존 메서드들 유지
    def get_daily_statistics(self, logs_data: List[Dict]) -> List[Dict]:
        """일별 통계 계산"""
        daily_counts = defaultdict(int)
        
        for log in logs_data:
            date = datetime.fromisoformat(log['timestamp']).date()
            daily_counts[date] += 1
        
        return [
            {'date': date.isoformat(), 'count': count}
            for date, count in sorted(daily_counts.items())
        ]
    
    def get_weekly_statistics(self, logs_data: List[Dict]) -> List[Dict]:
        """주별 통계 계산"""
        weekly_counts = defaultdict(int)
        
        for log in logs_data:
            date = datetime.fromisoformat(log['timestamp']).date()
            # 주의 시작일 (월요일) 계산
            week_start = date - timedelta(days=date.weekday())
            weekly_counts[week_start] += 1
        
        return [
            {'period': f"{date.isoformat()} ~ {(date + timedelta(days=6)).isoformat()}", 
             'count': count}
            for date, count in sorted(weekly_counts.items())
        ]
    
    def get_monthly_statistics(self, logs_data: List[Dict]) -> List[Dict]:
        """월별 통계 계산"""
        monthly_counts = defaultdict(int)
        
        for log in logs_data:
            date = datetime.fromisoformat(log['timestamp']).date()
            month_key = f"{date.year}-{date.month:02d}"
            monthly_counts[month_key] += 1
        
        return [
            {'period': period, 'count': count}
            for period, count in sorted(monthly_counts.items())
        ]
    
    def get_hourly_statistics(self, logs_data: List[Dict]) -> List[Dict]:
        """시간대별 통계 계산"""
        hourly_counts = defaultdict(int)
        
        for log in logs_data:
            hour = datetime.fromisoformat(log['timestamp']).hour
            hourly_counts[hour] += 1
        
        return [
            {'hour': hour, 'count': count}
            for hour, count in sorted(hourly_counts.items())
        ]
    
    def get_daily_ip_statistics(self, logs_data: List[Dict]) -> List[Dict]:
        """일별 고유 IP 통계"""
        daily_ips = defaultdict(set)
        
        for log in logs_data:
            date = datetime.fromisoformat(log['timestamp']).date()
            daily_ips[date].add(log['ip_address'])
        
        return [
            {'date': date.isoformat(), 'unique_ips': len(ips)}
            for date, ips in sorted(daily_ips.items())
        ]
    
    def get_weekly_ip_statistics(self, logs_data: List[Dict]) -> List[Dict]:
        """주별 고유 IP 통계"""
        weekly_ips = defaultdict(set)
        
        for log in logs_data:
            date = datetime.fromisoformat(log['timestamp']).date()
            week_start = date - timedelta(days=date.weekday())
            weekly_ips[week_start].add(log['ip_address'])
        
        return [
            {'period': f"{date.isoformat()} ~ {(date + timedelta(days=6)).isoformat()}", 
             'unique_ips': len(ips)}
            for date, ips in sorted(weekly_ips.items())
        ]
    
    def get_monthly_ip_statistics(self, logs_data: List[Dict]) -> List[Dict]:
        """월별 고유 IP 통계"""
        monthly_ips = defaultdict(set)
        
        for log in logs_data:
            date = datetime.fromisoformat(log['timestamp']).date()
            month_key = f"{date.year}-{date.month:02d}"
            monthly_ips[month_key].add(log['ip_address'])
        
        return [
            {'period': period, 'unique_ips': len(ips)}
            for period, ips in sorted(monthly_ips.items())
        ]
    
    def get_ip_statistics(self, logs_data: List[Dict]) -> Dict[str, Dict]:
        """IP별 상세 통계"""
        ip_stats = defaultdict(lambda: {
            'count': 0,
            'first_seen': None,
            'last_seen': None,
            'query_types': set(),
            'success_rate': 0.0,
            'avg_response_time': 0.0,
            'response_times': [],
            'successful_queries': 0,
            'failed_queries': 0
        })
        
        for log in logs_data:
            ip = log['ip_address']
            timestamp = log['timestamp']
            
            ip_stats[ip]['count'] += 1
            ip_stats[ip]['query_types'].add(log.get('query_type', 'unknown'))
            
            # 성공/실패 통계
            if log.get('success'):
                ip_stats[ip]['successful_queries'] += 1
            else:
                ip_stats[ip]['failed_queries'] += 1
            
            if log.get('response_time'):
                ip_stats[ip]['response_times'].append(log['response_time'])
            
            if not ip_stats[ip]['first_seen'] or timestamp < ip_stats[ip]['first_seen']:
                ip_stats[ip]['first_seen'] = timestamp
            
            if not ip_stats[ip]['last_seen'] or timestamp > ip_stats[ip]['last_seen']:
                ip_stats[ip]['last_seen'] = timestamp
        
        # 후처리
        for ip, stats in ip_stats.items():
            stats['query_types'] = list(stats['query_types'])
            if stats['response_times']:
                stats['avg_response_time'] = sum(stats['response_times']) / len(stats['response_times'])
            if stats['count'] > 0:
                stats['success_rate'] = stats['successful_queries'] / stats['count'] * 100
        
        return dict(ip_stats)
    
    def get_ip_activity_patterns(self, logs_data: List[Dict]) -> Dict:
        """IP 활동 패턴 분석"""
        patterns = {
            'hourly_distribution': defaultdict(int),
            'daily_distribution': defaultdict(int),
            'burst_activities': []
        }
        
        ip_timestamps = defaultdict(list)
        
        for log in logs_data:
            ip = log['ip_address']
            timestamp = datetime.fromisoformat(log['timestamp'])
            ip_timestamps[ip].append(timestamp)
            
            patterns['hourly_distribution'][timestamp.hour] += 1
            patterns['daily_distribution'][timestamp.date()] += 1
        
        # 버스트 활동 탐지 (1분 내 5개 이상 요청)
        for ip, timestamps in ip_timestamps.items():
            timestamps.sort()
            for i in range(len(timestamps) - 4):
                if (timestamps[i + 4] - timestamps[i]).total_seconds() <= 60:
                    patterns['burst_activities'].append({
                        'ip': ip,
                        'start_time': timestamps[i].isoformat(),
                        'request_count': 5,
                        'duration': (timestamps[i + 4] - timestamps[i]).total_seconds()
                    })
        
        return patterns
    
    def detect_suspicious_ips(self, logs_data: List[Dict], threshold: int = 100) -> Dict[str, Dict]:
        """의심스러운 IP 탐지"""
        ip_stats = self.get_ip_statistics(logs_data)
        suspicious_ips = {}
        
        for ip, stats in ip_stats.items():
            suspicion_score = 0
            reasons = []
            
            # 과도한 요청 수
            if stats['count'] > threshold:
                suspicion_score += 50
                reasons.append(f"과도한 요청 ({stats['count']}회)")
            
            # 높은 실패율
            if stats['success_rate'] < 30:  # 성공률 30% 미만
                suspicion_score += 30
                reasons.append(f"높은 실패율 ({stats['success_rate']:.1f}%)")
            
            # 짧은 시간 내 다수 요청
            if len(stats['response_times']) > 50:
                avg_interval = 86400 / len(stats['response_times'])  # 하루 기준
                if avg_interval < 10:  # 10초 미만 간격
                    suspicion_score += 30
                    reasons.append("짧은 간격 반복 요청")
            
            # 단일 질문 유형만 사용
            if len(stats['query_types']) == 1 and stats['count'] > 20:
                suspicion_score += 20
                reasons.append("단일 질문 유형 반복")
            
            if suspicion_score >= 50:
                suspicious_ips[ip] = {
                    'score': suspicion_score,
                    'reason': ', '.join(reasons),
                    'count': stats['count'],
                    'success_rate': stats['success_rate']
                }
        
        return suspicious_ips
    
    def get_query_type_statistics(self, logs_data: List[Dict]) -> Dict[str, int]:
        """질문 유형별 통계"""
        type_counts = Counter()
        
        for log in logs_data:
            query_type = log.get('query_type', 'unknown')
            type_counts[query_type] += 1
        
        return dict(type_counts)
    
    def extract_popular_keywords(self, logs_data: List[Dict], top_n: int = 50) -> List[tuple]:
        """인기 키워드 추출"""
        all_words = []
        
        # 한국어 불용어 목록
        stop_words = {
            '이', '그', '저', '것', '수', '등', '및', '또한', '그리고', '하지만', '그러나',
            '때문에', '으로', '에서', '에게', '에', '을', '를', '이', '가', '은', '는',
            '의', '와', '과', '도', '만', '에서', '부터', '까지', '대해', '대한', '위해',
            '알려줘', '알려주세요', '보여줘', '보여주세요', '해줘', '해주세요', '뭐야', '뭐예요'
        }
        
        for log in logs_data:
            question = log['question']
            # 한글, 영문, 숫자만 추출
            words = re.findall(r'[가-힣A-Za-z0-9]+', question)
            
            for word in words:
                if len(word) >= 2 and word not in stop_words:
                    all_words.append(word)
        
        return Counter(all_words).most_common(top_n)
    
    def get_question_length_statistics(self, logs_data: List[Dict]) -> Dict[str, int]:
        """질문 길이별 통계"""
        length_ranges = {
            '매우 짧음 (1-10자)': 0,
            '짧음 (11-30자)': 0,
            '보통 (31-70자)': 0,
            '김 (71-150자)': 0,
            '매우 김 (151자 이상)': 0
        }
        
        for log in logs_data:
            length = len(log['question'])
            
            if length <= 10:
                length_ranges['매우 짧음 (1-10자)'] += 1
            elif length <= 30:
                length_ranges['짧음 (11-30자)'] += 1
            elif length <= 70:
                length_ranges['보통 (31-70자)'] += 1
            elif length <= 150:
                length_ranges['김 (71-150자)'] += 1
            else:
                length_ranges['매우 김 (151자 이상)'] += 1
        
        return length_ranges
    
    def get_response_time_statistics(self, logs_data: List[Dict]) -> Dict[str, int]:
        """응답 시간별 통계"""
        time_ranges = {
            '매우 빠름 (1초 미만)': 0,
            '빠름 (1-3초)': 0,
            '보통 (3-10초)': 0,
            '느림 (10-30초)': 0,
            '매우 느림 (30초 이상)': 0
        }
        
        for log in logs_data:
            response_time = log.get('response_time', 0)
            
            if response_time < 1:
                time_ranges['매우 빠름 (1초 미만)'] += 1
            elif response_time < 3:
                time_ranges['빠름 (1-3초)'] += 1
            elif response_time < 10:
                time_ranges['보통 (3-10초)'] += 1
            elif response_time < 30:
                time_ranges['느림 (10-30초)'] += 1
            else:
                time_ranges['매우 느림 (30초 이상)'] += 1
        
        return time_ranges
    
    def get_success_rate_statistics(self, logs_data: List[Dict]) -> Dict[str, Any]:
        """답변 성공률 통계"""
        total_queries = len(logs_data)
        successful_queries = sum(1 for log in logs_data if log.get('success'))
        failed_queries = total_queries - successful_queries
        
        success_rate = (successful_queries / total_queries * 100) if total_queries > 0 else 0
        
        # 실패 원인별 통계
        failure_reasons = Counter()
        for log in logs_data:
            if not log.get('success') and log.get('error_message'):
                failure_reasons[log['error_message']] += 1
        
        return {
            'total_queries': total_queries,
            'successful_queries': successful_queries,
            'failed_queries': failed_queries,
            'success_rate': success_rate,
            'failure_reasons': dict(failure_reasons.most_common(10))
        }
    
    def calculate_daily_average(self, logs_data: List[Dict]) -> float:
        """일평균 질문 수 계산"""
        if not logs_data:
            return 0.0
        
        dates = set()
        for log in logs_data:
            date = datetime.fromisoformat(log['timestamp']).date()
            dates.add(date)
        
        return len(logs_data) / len(dates) if dates else 0.0
    
    def get_top_query_type(self, logs_data: List[Dict]) -> str:
        """가장 인기 있는 질문 유형"""
        type_stats = self.get_query_type_statistics(logs_data)
        if type_stats:
            return max(type_stats.items(), key=lambda x: x[1])[0]
        return "없음"
    
    def get_growth_rate(self, logs_data: List[Dict], metric_type: str) -> int:
        """성장률 계산 (임시 구현)"""
        # 실제로는 이전 기간과 비교해야 하지만, 여기서는 간단히 구현
        return 15  # 15% 성장률로 가정