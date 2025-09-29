# menu/admin_login.py
import streamlit as st
from auth_manager import AuthManager
from datetime import datetime

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
        
        st.success(f"환영합니다, {current_admin['name']}님!")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.info(f"**현재 로그인 계정**: {current_admin['username']}")
            st.info(f"**권한**: {current_admin['role']}")
            if current_admin['last_login']:
                last_login = datetime.fromisoformat(current_admin['last_login'])
                st.info(f"**마지막 로그인**: {last_login.strftime('%Y-%m-%d %H:%M:%S')}")
        
        with col2:
            st.write("**관리자 메뉴:**")
            st.write("- 사용자 활동 모니터링")
            st.write("- 관리자 계정 관리")
            st.write("- 시스템 설정")
        
        if st.button("로그아웃", type="primary"):
            auth_manager.logout_admin()
            st.success("로그아웃되었습니다.")
            st.rerun()
        
        return
    
    # 로그인 폼
    st.title("관리자 로그인")
    st.markdown("---")
    
    with st.form("admin_login_form"):
        st.subheader("관리자 인증")
        
        username = st.text_input("사용자명", placeholder="관리자 ID를 입력하세요")
        password = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            submit_button = st.form_submit_button("로그인", type="primary")
        
        with col2:
            remember_me = st.checkbox("로그인 상태 유지")
    
    if submit_button:
        if not username or not password:
            st.error("사용자명과 비밀번호를 모두 입력해주세요.")
        else:
            # 로그인 시도
            if auth_manager.login_admin(username, password):
                if remember_me:
                    st.session_state['admin_login_time'] = datetime.now()
                
                st.success("로그인에 성공했습니다!")
                st.balloons()
                st.rerun()
            else:
                st.error("잘못된 사용자명 또는 비밀번호입니다.")
                
                # 로그인 실패 로그 (선택사항)
                st.warning("보안을 위해 로그인 시도가 기록됩니다.")
    
    # 도움말 정보
    with st.expander("도움말"):
        st.markdown("""
        **기본 관리자 계정:**
        - 사용자명: `admin`
        - 비밀번호: `admin123!`
        
        **주의사항:**
        - 관리자 계정 정보는 안전하게 보관하세요
        - 비밀번호는 정기적으로 변경하세요
        - 의심스러운 접근 시도가 있을 경우 즉시 비밀번호를 변경하세요
        
        **문제 해결:**
        - 비밀번호를 잊어버린 경우 시스템 관리자에게 문의하세요
        - 계정이 잠긴 경우 30분 후 다시 시도하세요
        """)
    
    # 보안 정보
    st.markdown("---")
    st.caption("보안을 위해 모든 로그인 시도가 기록됩니다.")

if __name__ == "__main__":
    main()