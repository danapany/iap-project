import requests
import streamlit as st
from dotenv import load_dotenv
import os

# .env 파일 불러오기
load_dotenv()

st.set_page_config(page_title="SerpApi 사용량 확인", page_icon="🔎")

st.title("🔎 SerpApi 사용량 모니터링")

# .env 에서 API Key 읽기
api_key = os.getenv("SERPAPI_API_KEY")

if not api_key:
    st.error("❌ .env 파일에 SERPAPI_API_KEY가 설정되지 않았습니다.")
else:
    def get_serpapi_usage(api_key: str):
        url = f"https://serpapi.com/account?api_key={api_key}"
        response = requests.get(url)
        
        if response.status_code != 200:
            return None, response.text
        
        data = response.json()
        
        plan_total = data.get("plan_searches", 0)       # 이번 달 총 할당량
        searches_left = data.get("searches_left", 0)    # 남은 검색 횟수
        used = plan_total - searches_left               # 사용한 횟수
        
        return {
            "총 할당량": plan_total,
            "사용한 횟수": used,
            "남은 횟수": searches_left
        }, None

    with st.spinner("사용량 조회 중..."):
        usage, error = get_serpapi_usage(api_key)
        if error:
            st.error(f"API 호출 실패: {error}")
        else:
            st.success("✅ 사용량 조회 성공")
            st.metric("이번달 총 할당량", usage["총 할당량"])
            st.metric("이번달 사용 횟수", usage["사용한 횟수"])
            st.metric("이번달 남은 횟수", usage["남은 횟수"])