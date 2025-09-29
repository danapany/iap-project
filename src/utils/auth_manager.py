# auth_manager.py
import streamlit as st
import hashlib
import json
import os
from typing import Dict, List, Optional
from pathlib import Path

class AuthManager:
    """관리자 인증 관리 클래스"""
    
    def __init__(self, config_path: str = "data/admin_config.json"):
        self.config_path = config_path
        self.ensure_config_directory()
        self.load_admin_config()
    
    def ensure_config_directory(self):
        """설정 디렉토리 생성"""
        config_dir = Path(self.config_path).parent
        config_dir.mkdir(parents=True, exist_ok=True)
    
    def load_admin_config(self):
        """관리자 설정 로드"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.admin_config = json.load(f)
            else:
                # 기본 관리자 계정 생성
                self.admin_config = {
                    "admins": {
                        "admin": {
                            "password_hash": self._hash_password("admin123!"),
                            "name": "시스템 관리자",
                            "role": "super_admin",
                            "created_at": "2024-01-01T00:00:00",
                            "last_login": None,
                            "is_active": True
                        }
                    },
                    "settings": {
                        "session_timeout": 3600,  # 1시간
                        "max_login_attempts": 5,
                        "lockout_duration": 1800  # 30분
                    }
                }
                self.save_admin_config()
        except Exception as e:
            st.error(f"관리자 설정 로드 실패: {str(e)}")
            self.admin_config = {"admins": {}, "settings": {}}
    
    def save_admin_config(self):
        """관리자 설정 저장"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.admin_config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            st.error(f"관리자 설정 저장 실패: {str(e)}")
    
    def _hash_password(self, password: str) -> str:
        """비밀번호 해시화"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_admin_credentials(self, username: str, password: str) -> bool:
        """관리자 자격 증명 확인"""
        if username not in self.admin_config["admins"]:
            return False
        
        admin_info = self.admin_config["admins"][username]
        
        # 계정 활성화 상태 확인
        if not admin_info.get("is_active", True):
            return False
        
        # 비밀번호 확인
        password_hash = self._hash_password(password)
        return password_hash == admin_info["password_hash"]
    
    def login_admin(self, username: str, password: str) -> bool:
        """관리자 로그인"""
        if self.verify_admin_credentials(username, password):
            # 세션에 관리자 정보 저장
            st.session_state['admin_logged_in'] = True
            st.session_state['admin_username'] = username
            st.session_state['admin_login_time'] = st.session_state.get('admin_login_time', None)
            
            # 마지막 로그인 시간 업데이트
            from datetime import datetime
            self.admin_config["admins"][username]["last_login"] = datetime.now().isoformat()
            self.save_admin_config()
            
            return True
        return False
    
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
        if username and username in self.admin_config["admins"]:
            admin_info = self.admin_config["admins"][username].copy()
            admin_info['username'] = username
            return admin_info
        
        return None
    
    def add_admin(self, username: str, password: str, name: str, role: str = "admin") -> bool:
        """새 관리자 추가"""
        if username in self.admin_config["admins"]:
            return False
        
        from datetime import datetime
        self.admin_config["admins"][username] = {
            "password_hash": self._hash_password(password),
            "name": name,
            "role": role,
            "created_at": datetime.now().isoformat(),
            "last_login": None,
            "is_active": True
        }
        
        self.save_admin_config()
        return True
    
    def update_admin_password(self, username: str, new_password: str) -> bool:
        """관리자 비밀번호 변경"""
        if username not in self.admin_config["admins"]:
            return False
        
        self.admin_config["admins"][username]["password_hash"] = self._hash_password(new_password)
        self.save_admin_config()
        return True
    
    def deactivate_admin(self, username: str) -> bool:
        """관리자 계정 비활성화"""
        if username not in self.admin_config["admins"]:
            return False
        
        self.admin_config["admins"][username]["is_active"] = False
        self.save_admin_config()
        return True
    
    def activate_admin(self, username: str) -> bool:
        """관리자 계정 활성화"""
        if username not in self.admin_config["admins"]:
            return False
        
        self.admin_config["admins"][username]["is_active"] = True
        self.save_admin_config()
        return True
    
    def get_all_admins(self) -> List[Dict]:
        """모든 관리자 목록 반환"""
        admins = []
        for username, info in self.admin_config["admins"].items():
            admin_info = info.copy()
            admin_info['username'] = username
            admins.append(admin_info)
        return admins
    
    def delete_admin(self, username: str) -> bool:
        """관리자 계정 삭제"""
        if username not in self.admin_config["admins"]:
            return False
        
        # 최소 1명의 관리자는 남겨둬야 함
        active_admins = [u for u, info in self.admin_config["admins"].items() 
                        if info.get("is_active", True)]
        
        if len(active_admins) <= 1:
            return False
        
        del self.admin_config["admins"][username]
        self.save_admin_config()
        return True
    
    def check_session_timeout(self) -> bool:
        """세션 타임아웃 확인"""
        if not self.is_admin_logged_in():
            return True
        
        login_time = st.session_state.get('admin_login_time')
        if not login_time:
            return True
        
        from datetime import datetime, timedelta
        timeout_seconds = self.admin_config["settings"].get("session_timeout", 3600)
        
        if datetime.now() - login_time > timedelta(seconds=timeout_seconds):
            self.logout_admin()
            return True
        
        return False