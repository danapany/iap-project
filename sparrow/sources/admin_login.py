# menu/admin_login.py
import streamlit as st
from datetime import datetime
import sys
import os

# utils 디렉토리를 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.auth_manager import AuthManager

def main():
    """관리자 로그인 페이지"""
    
    st.set_page_config(
        page_title="관리자 로그인",
        page_icon="🔐",
        layout="centered"
    )
    
    auth_manager = AuthManager()
    
    # 이미 로그인된 경우
    if auth_manager.is_admin_logged_in():
        current_admin = auth_manager.get_current_admin()
        
        if not current_admin:
            st.error("관리자 정보를 불러올 수 없습니다.")
            auth_manager.logout_admin()
            st.rerun()
            return
        
        st.success(f"환영합니다, {current_admin['name']}님!")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.info(f"**현재 로그인 계정**: {current_admin['username']}")
            st.info(f"**권한**: {current_admin['role']}")
            if current_admin.get('last_login'):
                last_login = datetime.fromisoformat(current_admin['last_login'])
                st.info(f"**마지막 로그인**: {last_login.strftime('%Y-%m-%d %H:%M:%S')}")
        
        with col2:
            st.write("**관리자 메뉴:**")
            st.write("- 사용자 활동 모니터링")
            st.write("- 관리자 계정 관리")
            st.write("- 시스템 설정")
        
        # 계정 상태 표시
        if current_admin.get('is_active'):
            st.success("✅ 계정 활성화 상태")
        else:
            st.error("⚠️ 계정이 비활성화되었습니다")
        
        if st.button("로그아웃", type="primary"):
            auth_manager.logout_admin()
            st.success("로그아웃되었습니다.")
            st.rerun()
        
        return
    
    # 로그인 폼
    st.title("🔐 관리자 로그인")
    st.markdown("---")
    
    # 데이터베이스 정보 표시 (개발 모드)
    if os.getenv('DEBUG', 'False').lower() == 'true':
        db_path = auth_manager.db_path
        st.caption(f"📁 DB 경로: {db_path}")
    
    with st.form("admin_login_form"):
        st.subheader("관리자 인증")
        
        username = st.text_input("사용자명", placeholder="관리자 ID를 입력하세요")
        password = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            submit_button = st.form_submit_button("로그인", type="primary", use_container_width=True)
        
        with col2:
            remember_me = st.checkbox("로그인 상태 유지")
    
    if submit_button:
        if not username or not password:
            st.error("❌ 사용자명과 비밀번호를 모두 입력해주세요.")
        else:
            # 로그인 시도
            with st.spinner("로그인 중..."):
                if auth_manager.login_admin(username, password):
                    if remember_me:
                        st.session_state['admin_login_time'] = datetime.now()
                    
                    st.success("✅ 로그인에 성공했습니다!")
                    st.balloons()
                    st.rerun()
                else:
                    st.error("❌ 잘못된 사용자명 또는 비밀번호입니다.")
                    
                    # 로그인 실패 로그
                    st.warning("⚠️ 보안을 위해 로그인 시도가 기록됩니다.")
    
    # 보안 정보
    st.markdown("---")
    st.caption("📊 보안을 위해 모든 로그인 시도가 기록됩니다.")

if __name__ == "__main__":
    main()
