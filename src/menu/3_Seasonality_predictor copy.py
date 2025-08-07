import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime

# -----------------------------
# 📥 1. 데이터 업로드 / 로드
# -----------------------------
st.title("🔍 시즈널리티 통계 정보")
st.write("서비스별 오류 발생 데이터를 분석해 현재 월/일 기준 오류가 자주 발생하는 서비스 통계를 제공합니다.")

# 업로드 대신 정해진 경로의 파일을 자동 로드
csv_path = "./data/csv/seasonality.csv"

try:
    df = pd.read_csv(csv_path, parse_dates=["error_date"])
except FileNotFoundError:
    st.error(f"❌ 파일을 찾을 수 없습니다: {csv_path}")
    st.stop()
except Exception as e:
    st.error(f"❌ CSV 파일을 여는 중 오류 발생: {e}")
    st.stop()


# -----------------------------
# 🧹 2. 데이터 전처리
# -----------------------------
df["year"] = df["error_date"].dt.year
df["month"] = df["error_date"].dt.month
df["day"] = df["error_date"].dt.day
df["month_day"] = df["error_date"].dt.strftime("%m-%d")

# 요일 정보 추가 (0=월요일, 6=일요일)
df["weekday"] = df["error_date"].dt.weekday
weekday_map = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}
df["week"] = df["weekday"].map(weekday_map)


# -----------------------------
# 📊 3. 집계 처리
# -----------------------------
monthly_counts = df.groupby(["service", "month"]).size().reset_index(name="count")
day_counts = df.groupby(["service", "month_day"]).size().reset_index(name="count")

# -----------------------------
# 📅 4. 현재 기준 예측
# -----------------------------
today = datetime.today()
current_month = today.month
current_mmdd = today.strftime("%m-%d")

top_services_month = (
    monthly_counts[monthly_counts["month"] == current_month]
    .sort_values(by="count", ascending=False)
    .reset_index(drop=True)
)

top_services_day = (
    day_counts[day_counts["month_day"] == current_mmdd]
    .sort_values(by="count", ascending=False)
    .reset_index(drop=True)
)

# -----------------------------
# 📈 5. 결과 표시
# -----------------------------
st.subheader(f"📅 현재 월({current_month}월) 기준 정보")
st.dataframe(top_services_month, use_container_width=True)

st.subheader(f"📆 오늘({current_mmdd}) 기준 정보")
st.dataframe(top_services_day, use_container_width=True)

# -----------------------------
# 📉 6. 특정 서비스 시각화
# -----------------------------
# 한글 폰트 설정 (위 코드 포함 필요)
import matplotlib.font_manager as fm
import platform

if platform.system() == 'Windows':
    font_path = "C:/Windows/Fonts/malgun.ttf"
elif platform.system() == 'Darwin':
    font_path = "/System/Library/Fonts/AppleGothic.ttf"
else:
    font_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"

font_name = fm.FontProperties(fname=font_path).get_name()
plt.rc('font', family=font_name)

st.subheader("📊 서비스별 월별 오류 시즌성 그래프")

unique_services = df["service"].unique().tolist()
selected_service = st.selectbox("서비스 선택", unique_services)

service_monthly = monthly_counts[monthly_counts["service"] == selected_service]

fig, ax = plt.subplots()
ax.bar(service_monthly["month"], service_monthly["count"])
ax.set_title(f"{selected_service} - 월별 오류 발생 패턴")
ax.set_xlabel("월")
ax.set_ylabel("오류 수")
ax.set_xticks(range(1, 13))
plt.rc('font', family=font_name)
plt.rcParams['axes.unicode_minus'] = False    
st.pyplot(fig)

# -----------------------------
# 📉 7. 서비스별 일별 오류 시즌성 그래프 (월 선택 가능)
# -----------------------------
st.subheader("📊 서비스별 일별 오류 시즌성 그래프 (월 선택 가능)")

selected_service_day = st.selectbox("서비스 선택 (일별 시즌성)", unique_services, key="day_select")
selected_month_option = st.selectbox(
    "월 선택 (전체 또는 특정 월)",
    options=["전체"] + [f"{i}월" for i in range(1, 13)],
    key="month_select"
)

# 월 선택에 따라 데이터 필터링
if selected_month_option == "전체":
    filtered_df = df[df["service"] == selected_service_day]
else:
    selected_month = int(selected_month_option.replace("월", ""))
    filtered_df = df[(df["service"] == selected_service_day) & (df["month"] == selected_month)]

# 1일부터 31일까지 초기화된 DataFrame 생성
all_days = pd.DataFrame({'day': list(range(1, 32))})

# 실제 데이터 집계
if not filtered_df.empty:
    actual_daily_counts = (
        filtered_df.groupby("day")
        .size()
        .reset_index(name="count")
    )
    # 1~31일과 병합하여 누락된 날짜는 count=0으로 채움
    daily_counts = pd.merge(all_days, actual_daily_counts, on="day", how="left").fillna(0)
    daily_counts["count"] = daily_counts["count"].astype(int)
else:
    daily_counts = all_days.copy()
    daily_counts["count"] = 0

# 최대값 계산 (Y축 최소 5 보장)
y_max = max(5, daily_counts["count"].max())

# 막대그래프 출력
fig2, ax2 = plt.subplots()
ax2.bar(daily_counts["day"], daily_counts["count"])
month_title = selected_month_option if selected_month_option != "전체" else "전체 기간"
ax2.set_title(f"{selected_service_day} - {month_title} 일별 오류 발생 패턴")
ax2.set_xlabel("일")
ax2.set_ylabel("오류 수")
ax2.set_xticks(range(1, 32))
ax2.set_ylim(0, y_max)
st.pyplot(fig2)


# 📆 8. 서비스별 요일별 오류 그래프
st.subheader("📆 서비스별 요일별 오류 발생 패턴")

selected_service_week = st.selectbox("서비스 선택 (요일)", unique_services, key="weekday_select")

weekday_order_kr = ["월", "화", "수", "목", "금", "토", "일"]

weekday_df = df[df["service"] == selected_service_week]
weekday_counts = (
    weekday_df.groupby("week")
    .size()
    .reindex(weekday_order_kr, fill_value=0)
    .reset_index(name="count")
)

fig3, ax3 = plt.subplots()
ax3.bar(weekday_counts["week"], weekday_counts["count"])
ax3.set_title(f"{selected_service_week} - 요일별 오류 발생 패턴")
ax3.set_xlabel("요일")
ax3.set_ylabel("오류 수")
st.pyplot(fig3)

# 🌙 9. 서비스별 주간/야간 오류 그래프
st.subheader("🌙 서비스별 주간/야간 오류 발생 패턴")

selected_service_daynight = st.selectbox("서비스 선택 (주간/야간)", unique_services, key="daynight_select")

time_df = df[df["service"] == selected_service_daynight]
time_counts = (
    time_df["daynight"]
    .value_counts()
    .reindex(["주간", "야간"], fill_value=0)
    .reset_index()
)
time_counts.columns = ["daynight", "count"]

fig4, ax4 = plt.subplots()
ax4.bar(time_counts["daynight"], time_counts["count"])
ax4.set_title(f"{selected_service_daynight} - 주간/야간 오류 발생 패턴")
ax4.set_xlabel("시간대")
ax4.set_ylabel("오류 수")
st.pyplot(fig4)