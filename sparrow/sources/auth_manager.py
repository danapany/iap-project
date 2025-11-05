# utils/auth_manager.py
import streamlit as st
import bcrypt
import sqlite3
import os
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

class AuthManager:
    """관리자 인증 관리 클래스 (DB 기반)"""
    
    def __init__(self):
        self.db_base_path = os.getenv('DB_BASE_PATH', 'data/db')
        self.db_path = os.path.join(self.db_base_path, 'admin.db')
        self.ensure_database()
        self.initialize_default_admin()
    
    def ensure_database(self):
        """데이터베이스 및 테이블 생성"""
        # 디렉토리 생성
        Path(self.db_base_path).mkdir(parents=True, exist_ok=True)
        
        # 데이터베이스 연결 및 테이블 생성
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # admins 테이블 생성
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                created_at TEXT NOT NULL,
                last_login TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT
            )
        ''')
        
        # 로그인 시도 기록 테이블 (선택사항)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                success INTEGER NOT NULL,
                ip_address TEXT,
                timestamp TEXT NOT NULL
            )
        ''')
        
        # 설정 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        
        conn.commit()
        conn.close()
        
        # 기본 설정 초기화
        self._initialize_settings()
    
    def _initialize_settings(self):
        """기본 설정 초기화"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        default_settings = {
            'session_timeout': '3600',  # 1시간
            'max_login_attempts': '5',
            'lockout_duration': '1800'  # 30분
        }
        
        for key, value in default_settings.items():
            cursor.execute('''
                INSERT OR IGNORE INTO settings (key, value)
                VALUES (?, ?)
            ''', (key, value))
        
        conn.commit()
        conn.close()
    
    def get_connection(self) -> sqlite3.Connection:
        """데이터베이스 연결 반환"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 딕셔너리 형태로 결과 반환
        return conn
    
    def initialize_default_admin(self):
        """기본 관리자 계정 생성 (없는 경우)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 관리자 계정이 하나도 없으면 기본 계정 생성
        cursor.execute('SELECT COUNT(*) as count FROM admins')
        count = cursor.fetchone()['count']
        
        if count == 0:
            default_username = 'admin'
            default_password = 'admin123!'
            default_name = '시스템 관리자'
            
            password_hash = self._hash_password(default_password)
            
            cursor.execute('''
                INSERT INTO admins (username, password_hash, name, role, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (default_username, password_hash, default_name, 'super_admin', 
                  datetime.now().isoformat(), 1))
            
            conn.commit()
            print(f"기본 관리자 계정이 생성되었습니다: {default_username} / {default_password}")
        
        conn.close()
    
    def _hash_password(self, password: str) -> str:
        """비밀번호 해시화 (bcrypt 사용)"""
        salt = bcrypt.gensalt()
        password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
        return password_hash.decode('utf-8')
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """비밀번호 검증"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        except Exception as e:
            print(f"비밀번호 검증 오류: {str(e)}")
            return False
    
    def verify_admin_credentials(self, username: str, password: str) -> bool:
        """관리자 자격 증명 확인"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT password_hash, is_active 
            FROM admins 
            WHERE username = ?
        ''', (username,))
        
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return False
        
        # 계정 활성화 상태 확인
        if not result['is_active']:
            return False
        
        # 비밀번호 확인
        return self._verify_password(password, result['password_hash'])
    
    def login_admin(self, username: str, password: str) -> bool:
        """관리자 로그인"""
        if self.verify_admin_credentials(username, password):
            # 세션에 관리자 정보 저장
            st.session_state['admin_logged_in'] = True
            st.session_state['admin_username'] = username
            
            # 마지막 로그인 시간 업데이트
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE admins 
                SET last_login = ?, updated_at = ?
                WHERE username = ?
            ''', (datetime.now().isoformat(), datetime.now().isoformat(), username))
            
            conn.commit()
            conn.close()
            
            # 로그인 시도 기록
            self._log_login_attempt(username, success=True)
            
            return True
        
        # 로그인 실패 기록
        self._log_login_attempt(username, success=False)
        return False
    
    def _log_login_attempt(self, username: str, success: bool):
        """로그인 시도 기록"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO login_attempts (username, success, timestamp)
                VALUES (?, ?, ?)
            ''', (username, 1 if success else 0, datetime.now().isoformat()))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"로그인 시도 기록 오류: {str(e)}")
    
    def logout_admin(self):
        """관리자 로그아웃"""
        for key in ['admin_logged_in', 'admin_username', 'admin_login_time']:
            if key in st.session_state:
                del st.session_state[key]
    
    def is_admin_logged_in(self) -> bool:
        """관리자 로그인 상태 확인"""
        return st.session_state.get('admin_logged_in', False)
    
    def get_current_admin(self) -> Optional[Dict]:
        """현재 로그인한 관리자 정보 반환"""
        if not self.is_admin_logged_in():
            return None
        
        username = st.session_state.get('admin_username')
        if not username:
            return None
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, name, role, created_at, last_login, is_active
            FROM admins 
            WHERE username = ?
        ''', (username,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return dict(result)
        
        return None
    
    def add_admin(self, username: str, password: str, name: str, role: str = "admin") -> bool:
        """새 관리자 추가"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # 중복 확인
            cursor.execute('SELECT COUNT(*) as count FROM admins WHERE username = ?', (username,))
            if cursor.fetchone()['count'] > 0:
                conn.close()
                return False
            
            password_hash = self._hash_password(password)
            
            cursor.execute('''
                INSERT INTO admins (username, password_hash, name, role, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (username, password_hash, name, role, datetime.now().isoformat(), 1))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"관리자 추가 오류: {str(e)}")
            return False
    
    def update_admin_password(self, username: str, new_password: str) -> bool:
        """관리자 비밀번호 변경"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            password_hash = self._hash_password(new_password)
            
            cursor.execute('''
                UPDATE admins 
                SET password_hash = ?, updated_at = ?
                WHERE username = ?
            ''', (password_hash, datetime.now().isoformat(), username))
            
            conn.commit()
            affected_rows = cursor.rowcount
            conn.close()
            
            return affected_rows > 0
        except Exception as e:
            print(f"비밀번호 변경 오류: {str(e)}")
            return False
    
    def deactivate_admin(self, username: str) -> bool:
        """관리자 계정 비활성화"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE admins 
                SET is_active = 0, updated_at = ?
                WHERE username = ?
            ''', (datetime.now().isoformat(), username))
            
            conn.commit()
            affected_rows = cursor.rowcount
            conn.close()
            
            return affected_rows > 0
        except Exception as e:
            print(f"계정 비활성화 오류: {str(e)}")
            return False
    
    def activate_admin(self, username: str) -> bool:
        """관리자 계정 활성화"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE admins 
                SET is_active = 1, updated_at = ?
                WHERE username = ?
            ''', (datetime.now().isoformat(), username))
            
            conn.commit()
            affected_rows = cursor.rowcount
            conn.close()
            
            return affected_rows > 0
        except Exception as e:
            print(f"계정 활성화 오류: {str(e)}")
            return False
    
    def get_all_admins(self) -> List[Dict]:
        """모든 관리자 목록 반환"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, name, role, created_at, last_login, is_active
            FROM admins
            ORDER BY created_at DESC
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in results]
    
    def delete_admin(self, username: str) -> bool:
        """관리자 계정 삭제"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # 최소 1명의 활성 관리자는 남겨둬야 함
            cursor.execute('SELECT COUNT(*) as count FROM admins WHERE is_active = 1')
            active_count = cursor.fetchone()['count']
            
            if active_count <= 1:
                conn.close()
                return False
            
            cursor.execute('DELETE FROM admins WHERE username = ?', (username,))
            
            conn.commit()
            affected_rows = cursor.rowcount
            conn.close()
            
            return affected_rows > 0
        except Exception as e:
            print(f"계정 삭제 오류: {str(e)}")
            return False
    
    def get_login_attempts(self, username: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """로그인 시도 기록 조회"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if username:
            cursor.execute('''
                SELECT * FROM login_attempts 
                WHERE username = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (username, limit))
        else:
            cursor.execute('''
                SELECT * FROM login_attempts 
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
        
        results = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in results]
    
    def check_session_timeout(self) -> bool:
        """세션 타임아웃 확인"""
        if not self.is_admin_logged_in():
            return True
        
        login_time = st.session_state.get('admin_login_time')
        if not login_time:
            return True
        
        from datetime import timedelta
        
        # 설정에서 타임아웃 값 가져오기
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = ?', ('session_timeout',))
        result = cursor.fetchone()
        conn.close()
        
        timeout_seconds = int(result['value']) if result else 3600
        
        if datetime.now() - login_time > timedelta(seconds=timeout_seconds):
            self.logout_admin()
            return True
        
        return False
    
    def migrate_from_json(self, json_path: str = "data/admin_config.json") -> bool:
        """JSON 설정 파일에서 DB로 마이그레이션"""
        import json
        
        try:
            if not os.path.exists(json_path):
                print(f"JSON 파일이 존재하지 않습니다: {json_path}")
                return False
            
            with open(json_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # 기존 관리자들 마이그레이션
            for username, info in config.get('admins', {}).items():
                # 이미 존재하는지 확인
                cursor.execute('SELECT COUNT(*) as count FROM admins WHERE username = ?', (username,))
                if cursor.fetchone()['count'] > 0:
                    print(f"관리자 '{username}'는 이미 존재합니다. 건너뜁니다.")
                    continue
                
                # JSON의 SHA256 해시를 bcrypt로 재해싱할 수 없으므로
                # 기본 비밀번호로 설정하고 변경하도록 안내
                temp_password = 'changeMe123!'
                password_hash = self._hash_password(temp_password)
                
                cursor.execute('''
                    INSERT INTO admins (username, password_hash, name, role, created_at, last_login, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    username,
                    password_hash,
                    info.get('name', username),
                    info.get('role', 'admin'),
                    info.get('created_at', datetime.now().isoformat()),
                    info.get('last_login'),
                    1 if info.get('is_active', True) else 0
                ))
                
                print(f"관리자 '{username}' 마이그레이션 완료. 임시 비밀번호: {temp_password}")
            
            conn.commit()
            conn.close()
            
            print("마이그레이션이 완료되었습니다.")
            return True
            
        except Exception as e:
            print(f"마이그레이션 오류: {str(e)}")
            return False
