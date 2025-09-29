# utils/monitoring_manager.py
import json
import os
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import List, Dict, Any, Optional
import re
from pathlib import Path

class MonitoringManager:
    """사용자 활동 모니터링 관리 클래스"""
    
    def __init__(self, db_path: str = "data/db/monitoring.db"):
        """모니터링 매니저 초기화"""
        self.db_path = db_path
        self.ensure_db_directory()
        self.init_database()
    
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
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
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
    
    def log_user_activity(self, ip_address: str, question: str, query_type: str = None, 
                         user_agent: str = None, response_time: float = None,
                         document_count: int = None, success: bool = True, 
                         error_message: str = None):
        """사용자 활동 로그 기록"""
        try:
            timestamp = datetime.now().isoformat()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 로그 기록
                cursor.execute('''
                    INSERT INTO user_logs 
                    (timestamp, ip_address, user_agent, question, query_type, 
                     response_time, document_count, success, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (timestamp, ip_address, user_agent, question, query_type,
                      response_time, document_count, success, error_message))
                
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
        """지정된 기간의 로그 조회"""
        start_str = start_date.isoformat()
        end_str = (end_date + timedelta(days=1)).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT timestamp, ip_address, user_agent, question, query_type,
                       response_time, document_count, success, error_message
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
                    'error_message': row[8]
                }
                for row in rows
            ]
    
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
            'response_times': []
        })
        
        for log in logs_data:
            ip = log['ip_address']
            timestamp = log['timestamp']
            
            ip_stats[ip]['count'] += 1
            ip_stats[ip]['query_types'].add(log.get('query_type', 'unknown'))
            
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
                    'count': stats['count']
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
            '알려줘', '알려주세요', '보여줘', '보여주세요', '해줘', '해주세요', '뭐야', '뭐에요'
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