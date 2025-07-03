# app.py (메인 파일)
import streamlit as st

# 네비게이션 설정
pg = st.navigation([
    st.Page("menu/1_Chatbot.py", title="트러블 체이서 챗봇", icon="🕵️‍♂️"),
    st.Page("menu/1_upload_EML_Report.py", title="장애보고서 초안생성(1단계)", icon="📰"),
    st.Page("menu/2_Create Report.py", title="장애보고서 초안생성(2단계)", icon="📰"),
    st.Page("menu/3_Process_Chatbot.py", title="장애프로세스 안내챗봇", icon="👨‍⚕️"),
    st.Page("menu/4_Process Description.py", title="장애 프로세스 안내", icon="📌"),
    st.Page("menu/5_Process_FAQ.py", title="장애프로세스 FAQ", icon="❓"),
    #st.Page("menu/99_azure_test01.py", title="RAG Test", icon="🎯"),    
    st.Page("menu/99_azure_test02.py", title="프롬프팅 개발용", icon="🎯"),    
])

pg.run()



