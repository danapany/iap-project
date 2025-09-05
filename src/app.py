# app.py (메인 파일)
import streamlit as st

# 네비게이션 설정
pg = st.navigation([
    # 서비스 페이지
    st.Page("chatbot_main_local.py",  title="[목표1] 트러블 체이서 챗봇", icon="🕵️‍♂️"),
    #st.Page("chatbot_main.py",  title="[목표1] 트러블 체이서 챗봇(+인터넷)", icon="🕵️‍♂️"),
    st.Page("menu/2_Report_Gen_Assistant.py", title="[목표2] 분석 보고서 초안 생성 도우미", icon="📰"),
    st.Page("menu/3_Seasonality_Predictor.py", title="[목표3] 시즈널리티 통계정보", icon="📈"),

    #st.Page("menu/3_Process_Chatbot.py", title="[부가] 장애프로세스 안내챗봇", icon="👨‍⚕️"),
    #st.Page("menu/4_Process Description.py", title="[부가] 장애프로세스 쉬운설명", icon="📌"),
    #st.Page("menu/5_Process_FAQ.py", title="[부가] 장애프로세스 FAQ", icon="❓"),

    # 관리자용
    #st.Page("menu/90_Chatbot_Rag_Datapreprocess.py", title="[관리자] 챗봇 - 학습데이터 전처리기", icon="⚙️"),
    #st.Page("menu/90_Chatbot_Serpapi_Usage.py", title="[관리자] 챗봇 - SerpApi 사용량 모니터링", icon="⚙️"),

    #st.Page("menu/91_Admin-Process_Description_Create.py", title="[관리자] 장애프로세스 - 쉬운설명 생성", icon="⚙️"),
    #st.Page("menu/92_Admin-FAQ_Create.py", title="[관리자] 장애프로세스 - FAQ 생성", icon="⚙️"),
    #st.Page("menu/93_Admin-Keyword-based_question_Create.py", title="[관리자] 장애프로세스 - 키워드버튼 생성", icon="⚙️"),

    # 개발용 (임시)
    #st.Page("menu/99_azure_test01.py", title="[개발용] 프롬프팅 개발용", icon="🎯"),
    #st.Page("menu/1_Chatbot2.py", title="[개발용] 트러블 체이서 챗봇 (+이상징후)", icon="🕵️‍♂️"),
    #st.Page("menu/1_Chatbot3.py", title="[개발용] 트러블 체이서 챗봇 (장애보고서학습)", icon="🕵️‍♂️")
])

pg.run()



