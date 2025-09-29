# menu/admin_management.py
import streamlit as st
import pandas as pd
from datetime import datetime
from auth_manager import AuthManager

def main():
    """관리자 관리 페이지"""
    
    # 관리자 인증 확인
    auth_manager = AuthManager()
    if not auth_manager.is_admin_logged_in():
        st.error("관리자 권한이 필요합니다.")
        st.info("좌측 메뉴에서 '관리자 로그인'을 먼저 진행해주세요.")
        return
    
    # 현재 로그인한 관리자 정보
    current_admin = auth_manager.get_current_admin()
    if not current_admin:
        st.error("관리자 정보를 불러올 수 없습니다.")
        return
    
    st.title("관리자 계정 관리")
    st.markdown("---")
    
    # 탭 구성
    tab1, tab2, tab3 = st.tabs(["관리자 목록", "새 관리자 추가", "내 정보 수정"])
    
    with tab1:
        show_admin_list(auth_manager, current_admin)
    
    with tab2:
        add_new_admin(auth_manager, current_admin)
    
    with tab3:
        edit_my_info(auth_manager, current_admin)

def show_admin_list(auth_manager, current_admin):
    """관리자 목록 표시"""
    st.subheader("등록된 관리자 목록")
    
    # 관리자 목록 가져오기
    admins = auth_manager.get_all_admins()
    
    if not admins:
        st.warning("등록된 관리자가 없습니다.")
        return
    
    # 관리자 정보를 데이터프레임으로 변환
    admin_data = []
    for admin in admins:
        last_login = "로그인 기록 없음"
        if admin.get('last_login'):
            last_login_dt = datetime.fromisoformat(admin['last_login'])
            last_login = last_login_dt.strftime('%Y-%m-%d %H:%M:%S')
        
        created_at = "정보 없음"
        if admin.get('created_at'):
            created_dt = datetime.fromisoformat(admin['created_at'])
            created_at = created_dt.strftime('%Y-%m-%d %H:%M:%S')
        
        admin_data.append({
            '사용자명': admin['username'],
            '이름': admin['name'],
            '권한': admin['role'],
            '상태': '활성' if admin.get('is_active', True) else '비활성',
            '생성일': created_at,
            '마지막 로그인': last_login
        })
    
    df_admins = pd.DataFrame(admin_data)
    st.dataframe(df_admins, use_container_width=True)
    
    # 관리자 관리 액션
    st.subheader("관리자 계정 관리")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**계정 상태 변경**")
        
        # 관리할 사용자 선택
        usernames = [admin['username'] for admin in admins 
                    if admin['username'] != current_admin['username']]
        
        if usernames:
            selected_user = st.selectbox("관리할 사용자 선택", usernames)
            
            # 현재 상태 표시
            selected_admin = next(admin for admin in admins if admin['username'] == selected_user)
            current_status = "활성" if selected_admin.get('is_active', True) else "비활성"
            st.info(f"현재 상태: {current_status}")
            
            # 상태 변경 버튼
            col_btn1, col_btn2 = st.columns(2)
            
            with col_btn1:
                if st.button("계정 비활성화", key="deactivate"):
                    if auth_manager.deactivate_admin(selected_user):
                        st.success(f"{selected_user} 계정이 비활성화되었습니다.")
                        st.rerun()
                    else:
                        st.error("계정 비활성화에 실패했습니다.")
            
            with col_btn2:
                if st.button("계정 활성화", key="activate"):
                    if auth_manager.activate_admin(selected_user):
                        st.success(f"{selected_user} 계정이 활성화되었습니다.")
                        st.rerun()
                    else:
                        st.error("계정 활성화에 실패했습니다.")
        else:
            st.info("관리할 수 있는 다른 관리자 계정이 없습니다.")
    
    with col2:
        st.write("**계정 삭제**")
        
        if usernames:
            delete_user = st.selectbox("삭제할 사용자 선택", usernames, key="delete_select")
            
            st.warning("이 작업은 되돌릴 수 없습니다!")
            
            # 삭제 확인
            if st.checkbox(f"{delete_user} 계정을 영구 삭제하겠습니다", key="delete_confirm"):
                if st.button("계정 삭제", type="primary", key="delete_btn"):
                    if auth_manager.delete_admin(delete_user):
                        st.success(f"{delete_user} 계정이 삭제되었습니다.")
                        st.rerun()
                    else:
                        st.error("계정 삭제에 실패했습니다. (최소 1명의 관리자는 유지되어야 합니다)")
        else:
            st.info("삭제할 수 있는 관리자 계정이 없습니다.")

def add_new_admin(auth_manager, current_admin):
    """새 관리자 추가"""
    st.subheader("새 관리자 계정 추가")
    
    with st.form("add_admin_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            new_username = st.text_input("사용자명", placeholder="영문, 숫자 조합")
            new_name = st.text_input("이름", placeholder="관리자 실명")
        
        with col2:
            new_password = st.text_input("비밀번호", type="password", placeholder="8자 이상")
            confirm_password = st.text_input("비밀번호 확인", type="password")
        
        new_role = st.selectbox("권한 레벨", ["admin", "super_admin"])
        
        submit_button = st.form_submit_button("관리자 추가", type="primary")
    
    if submit_button:
        # 입력 검증
        errors = []
        
        if not new_username or len(new_username) < 3:
            errors.append("사용자명은 3자 이상이어야 합니다.")
        
        if not new_name:
            errors.append("이름을 입력해주세요.")
        
        if not new_password or len(new_password) < 8:
            errors.append("비밀번호는 8자 이상이어야 합니다.")
        
        if new_password != confirm_password:
            errors.append("비밀번호가 일치하지 않습니다.")
        
        # 중복 사용자명 검사
        existing_admins = auth_manager.get_all_admins()
        if any(admin['username'] == new_username for admin in existing_admins):
            errors.append("이미 존재하는 사용자명입니다.")
        
        if errors:
            for error in errors:
                st.error(error)
        else:
            # 관리자 추가
            if auth_manager.add_admin(new_username, new_password, new_name, new_role):
                st.success(f"관리자 '{new_username}'가 성공적으로 추가되었습니다.")
                st.balloons()
                
                # 폼 초기화를 위해 페이지 새로고침
                st.rerun()
            else:
                st.error("관리자 추가에 실패했습니다.")

def edit_my_info(auth_manager, current_admin):
    """내 정보 수정"""
    st.subheader("내 정보 수정")
    
    # 현재 정보 표시
    col1, col2 = st.columns(2)
    
    with col1:
        st.info(f"**사용자명**: {current_admin['username']}")
        st.info(f"**이름**: {current_admin['name']}")
    
    with col2:
        st.info(f"**권한**: {current_admin['role']}")
        if current_admin.get('created_at'):
            created_date = datetime.fromisoformat(current_admin['created_at'])
            st.info(f"**가입일**: {created_date.strftime('%Y-%m-%d')}")
    
    st.markdown("---")
    
    # 비밀번호 변경
    st.subheader("비밀번호 변경")
    
    with st.form("change_password_form"):
        current_password = st.text_input("현재 비밀번호", type="password")
        new_password = st.text_input("새 비밀번호", type="password", placeholder="8자 이상")
        confirm_new_password = st.text_input("새 비밀번호 확인", type="password")
        
        change_password_btn = st.form_submit_button("비밀번호 변경", type="primary")
    
    if change_password_btn:
        # 현재 비밀번호 확인
        if not auth_manager.verify_admin_credentials(current_admin['username'], current_password):
            st.error("현재 비밀번호가 올바르지 않습니다.")
        elif not new_password or len(new_password) < 8:
            st.error("새 비밀번호는 8자 이상이어야 합니다.")
        elif new_password != confirm_new_password:
            st.error("새 비밀번호가 일치하지 않습니다.")
        elif new_password == current_password:
            st.error("새 비밀번호는 현재 비밀번호와 달라야 합니다.")
        else:
            # 비밀번호 변경
            if auth_manager.update_admin_password(current_admin['username'], new_password):
                st.success("비밀번호가 성공적으로 변경되었습니다.")
                st.info("보안을 위해 다시 로그인해주세요.")
                
                # 로그아웃 버튼 제공
                if st.button("다시 로그인하기"):
                    auth_manager.logout_admin()
                    st.rerun()
            else:
                st.error("비밀번호 변경에 실패했습니다.")
    
    # 세션 정보
    st.markdown("---")
    st.subheader("세션 정보")
    
    login_time = st.session_state.get('admin_login_time')
    if login_time:
        st.info(f"**로그인 시간**: {login_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if current_admin.get('last_login'):
        last_login = datetime.fromisoformat(current_admin['last_login'])
        st.info(f"**마지막 로그인**: {last_login.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 로그아웃 버튼
    if st.button("로그아웃", type="secondary"):
        auth_manager.logout_admin()
        st.success("로그아웃되었습니다.")
        st.rerun()

if __name__ == "__main__":
    main()