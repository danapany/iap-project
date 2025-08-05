# app.py (메인 파일)
import streamlit as st

# 네비게이션 설정
pg = st.navigation([
    # 서비스 페이지
    st.Page("menu/1_Chatbot.py",  title="[목표1] 트러블 체이서 챗봇", icon="🕵️‍♂️"),
    # st.Page("menu/1_Chatbot2.py", title="[목표1] 트러블 체이서 챗봇 (장애보고서학습)", icon="🕵️‍♂️"),
    st.Page("menu/2_Report_Gen_Assistant.py", title="[목표2] 분석 보고서 초안 생성 도우미", icon="📰"),
    st.Page("menu/3_Process_Chatbot.py", title="[부가] 장애프로세스 안내챗봇", icon="👨‍⚕️"),
    st.Page("menu/4_Process Description.py", title="[부가] 장애프로세스 쉬운설명", icon="📌"),
    st.Page("menu/5_Process_FAQ.py", title="[부가] 장애프로세스 FAQ", icon="❓"),

    # 관리자용
    st.Page("menu/91_Admin-Process_Description_Create.py", title="[부가] 장애프로세스 쉬운설명 (생성용)", icon="⚙️"),
    st.Page("menu/92_Admin-FAQ_Create.py", title="[부가] 장애프로세스 FAQ (생성용)", icon="⚙️"),
    st.Page("menu/93_Admin-Keyword-based_question_Create.py", title="[부가] 장애프로세스 챗봇 키워드버튼 (생성용)", icon="⚙️"),

    # 개발용 (임시)
    st.Page("menu/99_azure_test01.py", title="[개발용] 프롬프팅 개발용", icon="🎯")  
])

pg.run()



