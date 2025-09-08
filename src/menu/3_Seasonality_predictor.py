import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import platform
import os
import urllib.request
from datetime import datetime

# -----------------------------
# 🎨 폰트 설정 (한글 지원) - Azure 웹앱 최적화
# -----------------------------
def setup_korean_font():
    """한글 폰트 설정 함수 - Azure 웹앱 환경 최적화"""
    try:
        # 1. 프로젝트 내 fonts 디렉토리 생성
        fonts_dir = "./fonts"
        if not os.path.exists(fonts_dir):
            os.makedirs(fonts_dir)
        
        # 2. 나눔고딕 폰트 다운로드 (없는 경우에만)
        font_file_path = os.path.join(fonts_dir, "NanumGothic.ttf")
        
        if not os.path.exists(font_file_path):
            try:
                # GitHub에서 나눔고딕 폰트 다운로드
                font_url = "https://github.com/naver/nanumfont/raw/master/fonts/NanumGothic.ttf"
                urllib.request.urlretrieve(font_url, font_file_path)
                st.info("한글 폰트를 다운로드했습니다.")
            except Exception as e:
                st.warning(f"폰트 다운로드 실패: {e}")
        
        # 3. 폰트 파일이 존재하는 경우 설정
        if os.path.exists(font_file_path):
            try:
                # matplotlib 폰트 매니저에 폰트 추가
                fm.fontManager.addfont(font_file_path)
                font_prop = fm.FontProperties(fname=font_file_path)
                font_name = font_prop.get_name()
                
                # matplotlib 설정
                plt.rcParams['font.family'] = font_name
                plt.rcParams['axes.unicode_minus'] = False
                
                return font_name
            except Exception as e:
                st.warning(f"다운로드된 폰트 설정 실패: {e}")
        
        # 4. 기존 시스템 폰트 시도
        if platform.system() == 'Windows':
            font_paths = [
                "C:/Windows/Fonts/malgun.ttf",
                "C:/Windows/Fonts/gulim.ttc",
                "C:/Windows/Fonts/batang.ttc"
            ]
        elif platform.system() == 'Darwin':  # macOS
            font_paths = [
                "/System/Library/Fonts/AppleGothic.ttf",
                "/Library/Fonts/AppleGothic.ttf"
            ]
        else:  # Linux (Azure 웹앱 포함)
            font_paths = [
                "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                font_file_path  # 다운로드된 폰트 경로 추가
            ]
        
        # 사용 가능한 폰트 찾기
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    if font_path.endswith('.ttf') or font_path.endswith('.ttc'):
                        fm.fontManager.addfont(font_path)
                    font_prop = fm.FontProperties(fname=font_path)
                    font_name = font_prop.get_name()
                    plt.rcParams['font.family'] = font_name
                    plt.rcParams['axes.unicode_minus'] = False
                    return font_name
                except Exception:
                    continue
        
        # 5. 설치된 한글 폰트 검색
        korean_fonts = []
        for font in fm.fontManager.ttflist:
            if any(keyword in font.name.lower() for keyword in ['nanum', 'malgun', 'gothic', 'batang', 'gulim']):
                korean_fonts.append(font.name)
        
        if korean_fonts:
            font_name = korean_fonts[0]
            plt.rcParams['font.family'] = font_name
            plt.rcParams['axes.unicode_minus'] = False
            return font_name
        
        # 6. 최종 fallback - unicode 지원 폰트
        fallback_fonts = ['DejaVu Sans', 'Arial Unicode MS', 'Lucida Grande']
        for font in fallback_fonts:
            try:
                plt.rcParams['font.family'] = font
                plt.rcParams['axes.unicode_minus'] = False
                return font
            except:
                continue
                
        # 7. 기본 설정
        plt.rcParams['font.family'] = 'DejaVu Sans'
        plt.rcParams['axes.unicode_minus'] = False
        return 'DejaVu Sans'
        
    except Exception as e:
        # 모든 폰트 설정 실패시 기본 설정
        plt.rcParams['font.family'] = 'DejaVu Sans'
        plt.rcParams['axes.unicode_minus'] = False
        st.error(f"폰트 설정 중 오류 발생: {e}")
        return 'DejaVu Sans'

# 폰트 설정 실행
font_name = setup_korean_font()

# -----------------------------
# 📥 1. 데이터 업로드 / 로드
# -----------------------------
st.title("📊 서비스별 오류 시즌성 분석기")
st.write("서비스별 오류 발생 데이터를 분석해 현재 월/일 기준 오류가 자주 발생할 가능성이 높은 서비스를 예측합니다.")

# 업로드 대신 정해진 경로의 파일을 자동 로드
csv_path = "./data/csv/seasonality.csv"

try:
    df = pd.read_csv(csv_path, parse_dates=["error_date"])
except FileNotFoundError:
    st.error(f"⚠️ 파일을 찾을 수 없습니다: {csv_path}")
    st.stop()
except Exception as e:
    st.error(f"⚠️ CSV 파일을 여는 중 오류 발생: {e}")
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
st.subheader(f"📅 현재 월({current_month}월) 기준")
st.dataframe(top_services_month, use_container_width=True)

st.subheader(f"📆 오늘({current_mmdd}) 기준")
st.dataframe(top_services_day, use_container_width=True)

# -----------------------------
# 기본 서비스 선택을 위한 설정
# -----------------------------
# 현재 월 기준 가장 오류가 많은 서비스를 기본값으로 설정
if not top_services_month.empty:
    default_service = top_services_month.iloc[0]["service"]
else:
    # 현재 월에 데이터가 없으면 전체 서비스 중 첫 번째
    default_service = df["service"].unique().tolist()[0]

# -----------------------------
# 📉 6. 특정 서비스 시각화
# -----------------------------
st.subheader("📊 서비스별 월별 오류 시즌성 그래프")

unique_services = df["service"].unique().tolist()
# 기본 서비스를 리스트 앞쪽으로 이동
if default_service in unique_services:
    unique_services.remove(default_service)
    unique_services.insert(0, default_service)

selected_service = st.selectbox("서비스 선택", unique_services)

service_monthly = monthly_counts[monthly_counts["service"] == selected_service]

fig, ax = plt.subplots(figsize=(10, 6))
ax.bar(service_monthly["month"], service_monthly["count"])
ax.set_title(f"{selected_service} - 월별 오류 발생 패턴", fontsize=14, pad=20)
ax.set_xlabel("월", fontsize=12)
ax.set_ylabel("오류 수", fontsize=12)
ax.set_xticks(range(1, 13))
ax.grid(True, alpha=0.3)
plt.tight_layout()
st.pyplot(fig)

# -----------------------------
# 📉 7. 서비스별 일별 오류 시즌성 그래프 (월 선택 가능)
# -----------------------------
st.subheader("📊 서비스별 일별 오류 시즌성 그래프 (월 선택 가능)")

# 기본 서비스를 리스트 앞쪽으로 이동
unique_services_day = df["service"].unique().tolist()
if default_service in unique_services_day:
    unique_services_day.remove(default_service)
    unique_services_day.insert(0, default_service)

selected_service_day = st.selectbox("서비스 선택 (일별 시즌성)", unique_services_day, key="day_select")
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

# 최댓값 계산 (Y축 최소 5 보장)
y_max = max(5, daily_counts["count"].max())

# 막대그래프 출력
fig2, ax2 = plt.subplots(figsize=(12, 6))
ax2.bar(daily_counts["day"], daily_counts["count"])
month_title = selected_month_option if selected_month_option != "전체" else "전체 기간"
ax2.set_title(f"{selected_service_day} - {month_title} 일별 오류 발생 패턴", fontsize=14, pad=20)
ax2.set_xlabel("일", fontsize=12)
ax2.set_ylabel("오류 수", fontsize=12)
ax2.set_xticks(range(1, 32))
ax2.set_ylim(0, y_max)
ax2.grid(True, alpha=0.3)
plt.tight_layout()
st.pyplot(fig2)

# 📆 8. 서비스별 요일별 오류 그래프
st.subheader("📆 서비스별 요일별 오류 발생 패턴")

# 기본 서비스를 리스트 앞쪽으로 이동
unique_services_week = df["service"].unique().tolist()
if default_service in unique_services_week:
    unique_services_week.remove(default_service)
    unique_services_week.insert(0, default_service)

selected_service_week = st.selectbox("서비스 선택 (요일)", unique_services_week, key="weekday_select")

weekday_order_kr = ["월", "화", "수", "목", "금", "토", "일"]

weekday_df = df[df["service"] == selected_service_week]
weekday_counts = (
    weekday_df.groupby("week")
    .size()
    .reindex(weekday_order_kr, fill_value=0)
    .reset_index(name="count")
)

fig3, ax3 = plt.subplots(figsize=(10, 6))
ax3.bar(weekday_counts["week"], weekday_counts["count"])
ax3.set_title(f"{selected_service_week} - 요일별 오류 발생 패턴", fontsize=14, pad=20)
ax3.set_xlabel("요일", fontsize=12)
ax3.set_ylabel("오류 수", fontsize=12)
ax3.grid(True, alpha=0.3)
plt.tight_layout()
st.pyplot(fig3)

# 🌙 9. 서비스별 주간/야간 오류 그래프
if 'daynight' in df.columns:
    st.subheader("🌙 서비스별 주간/야간 오류 발생 패턴")

    # 기본 서비스를 리스트 앞쪽으로 이동
    unique_services_daynight = df["service"].unique().tolist()
    if default_service in unique_services_daynight:
        unique_services_daynight.remove(default_service)
        unique_services_daynight.insert(0, default_service)

    selected_service_daynight = st.selectbox("서비스 선택 (주간/야간)", unique_services_daynight, key="daynight_select")

    time_df = df[df["service"] == selected_service_daynight]
    time_counts = (
        time_df["daynight"]
        .value_counts()
        .reindex(["주간", "야간"], fill_value=0)
        .reset_index()
    )
    time_counts.columns = ["daynight", "count"]

    fig4, ax4 = plt.subplots(figsize=(8, 6))
    ax4.bar(time_counts["daynight"], time_counts["count"])
    ax4.set_title(f"{selected_service_daynight} - 주간/야간 오류 발생 패턴", fontsize=14, pad=20)
    ax4.set_xlabel("시간대", fontsize=12)
    ax4.set_ylabel("오류 수", fontsize=12)
    ax4.grid(True, alpha=0.3)
    plt.tight_layout()
    st.pyplot(fig4)
else:
    st.info("주간/야간 데이터(daynight 컬럼)가 없어 해당 차트를 표시할 수 없습니다.")