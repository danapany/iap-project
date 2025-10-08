# app.py (메인 파일)
import streamlit as st
from auth_manager import AuthManager

# 인증 매니저 초기화
auth_manager = AuthManager()

# 기본 페이지 목록
base_pages = [
    # 서비스 페이지
    st.Page("chatbot_main_local.py",  title="트러블 체이서 챗봇", icon="🕵️‍♂️"),
    st.Page("chatbot_main_web.py",  title="트러블 체이서 챗봇(WEB검색)", icon="🕵️‍♂️"),
    st.Page("menu/2_Report_Gen_Assistant.py", title="장애보고서 초안생성 도우미", icon="📰"),
    st.Page("menu/3_Seasonality_Predictor.py", title="시즈널리티 통계정보", icon="📈"),
]

# 관리자용 페이지 목록
admin_pages = [
    st.Page("menu/90_Chatbot_Incident_data_mng.py", title="[관리자] 챗봇 - 인시던트 데이터관리(통계용)", icon="⚙️"),    
    st.Page("menu/90_Chatbot_Rag_Datapreprocess.py", title="[관리자] 챗봇 - 학습데이터 전처리기", icon="⚙️"),
    st.Page("menu/90_Chatbot_UserQuestion_Changer.py", title="[관리자] 챗봇 - 개별 프롬프팅설정", icon="⚙️"),
    st.Page("menu/90_Admin_monitoring.py", title="[관리자] 챗봇 - 질문정보 모니터링", icon="⚙️"),
    st.Page("menu/90_Chatbot_Serpapi_Usage.py", title="[관리자] 챗봇 - SerpApi 사용량 모니터링", icon="⚙️"),

    #st.Page("menu/91_Admin-Process_Description_Create.py", title="[관리자] 장애프로세스 - 쉬운설명 생성", icon="⚙️"),
    #st.Page("menu/92_Admin-FAQ_Create.py", title="[관리자] 장애프로세스 - FAQ 생성", icon="⚙️"),
    #st.Page("menu/93_Admin-Keyword-based_question_Create.py", title="[관리자] 장애프로세스 - 키워드버튼 생성", icon="⚙️"),
]

# 인증 관련 페이지 (항상 표시)
auth_pages = [
    st.Page("menu/admin_login.py", title="관리자 로그인", icon="🔐"),
]

# 관리자 전용 관리 페이지
admin_management_pages = [
    st.Page("menu/admin_management.py", title="👨‍💼 관리자 관리", icon="👨‍💼"),
]

# 개발용 페이지 (주석 처리됨)
#dev_pages = [
    #st.Page("menu/99_azure_test01.py", title="[개발용] 프롬프팅 개발용", icon="🎯"),
    #st.Page("menu/1_Chatbot2.py", title="[개발용] 트러블 체이서 챗봇 (+이상징후)", icon="🕵️‍♂️"),
    #st.Page("menu/1_Chatbot3.py", title="[개발용] 트러블 체이서 챗봇 (장애보고서학습)", icon="🕵️‍♂️")
#]

# 네비게이션 페이지 구성
pages = base_pages + auth_pages

# 관리자가 로그인되어 있으면 관리자용 페이지 추가
if auth_manager.is_admin_logged_in():
    pages += admin_management_pages + admin_pages

# 네비게이션 설정
pg = st.navigation(pages)

pg.run()