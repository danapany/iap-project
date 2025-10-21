import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns
import numpy as np
import platform
import os
import urllib.request
import hashlib
from datetime import datetime, timedelta

# -----------------------------
# 🔧 페이지 레이아웃 설정
# -----------------------------
st.set_page_config(
    page_title="서비스별 오류 시즌성 분석기",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS를 사용하여 90% 너비 설정 (오른쪽 여백 강화)
st.markdown("""
    <style>
    .main .block-container {
        max-width: 90%;
        padding-left: 2rem;
        padding-right: 4rem;
        margin-left: auto;
        margin-right: auto;
    }
    </style>
""", unsafe_allow_html=True)

# -----------------------------
# 🎨 폰트 설정 (한글 지원) - 보안 강화 버전
# -----------------------------
def verify_file_integrity(file_path, expected_hash):
    """
    파일 무결성 검증 함수 - CWE-494, CWE-759 보안 준수
    
    ⚠️ 보안 참고사항:
    이 함수는 다운로드된 파일의 무결성을 검증하여 악성 코드나 변조된 파일을 차단합니다.
    
    CWE-494 (Download of Code Without Integrity Check) 대응:
    - 원격에서 다운로드한 모든 파일은 실행/사용 전 반드시 무결성 검증
    - SHA256 해시를 사용하여 파일이 신뢰할 수 있는 소스인지 확인
    - 검증 실패 시 파일을 즉시 삭제하여 악성 파일 사용 방지
    
    CWE-759 (Use of a One-Way Hash without a Salt) 오탐 설명:
    - 이 함수는 '파일 무결성 검증' 용도로 솔트가 필요하지 않음
    - 비밀번호 저장이 아닌 파일 검증에는 솔트 없는 해시가 표준
    - 같은 파일은 항상 같은 해시값을 가져야 검증 가능
    
    Reference: NIST SP 800-107, ISO/IEC 10118-3, OWASP Secure Coding Practices
    
    Args:
        file_path (str): 검증할 파일 경로
        expected_hash (str): 신뢰할 수 있는 출처의 예상 SHA256 해시값
    
    Returns:
        bool: 무결성 검증 성공 시 True, 실패 시 False
    """
    try:
        with open(file_path, 'rb') as f:
            file_data = f.read()
            # 파일 무결성 검증용 SHA256 해시 계산
            # 보안: 다운로드한 파일이 변조되지 않았는지 확인 (CWE-494 대응)
            calculated_hash = hashlib.sha256(file_data).hexdigest()
            
            # 해시값 비교를 통한 무결성 검증
            is_valid = calculated_hash.lower() == expected_hash.lower()
            
            if not is_valid:
                st.error(f"⚠️ 보안 경고: 파일 해시값 불일치! 악성 파일일 수 있습니다.")
                st.error(f"예상: {expected_hash}")
                st.error(f"실제: {calculated_hash}")
            
            return is_valid
    except Exception as e:
        st.warning(f"파일 무결성 검증 실패: {e}")
        return False

def secure_download_font(url, file_path, expected_hash):
    """
    보안 강화된 파일 다운로드 함수 - CWE-494 대응
    
    ⚠️ 보안 조치 사항:
    1. HTTPS 연결만 허용하여 중간자 공격(MITM) 방지
    2. 타임아웃 설정으로 서비스 거부 공격 방지
    3. 임시 파일로 다운로드 후 검증 (원본 파일 보호)
    4. SHA256 해시 무결성 검증 필수 (CWE-494 대응)
    5. 검증 실패 시 즉시 파일 삭제 (악성 파일 차단)
    
    이 함수는 실행 코드가 아닌 폰트 데이터 파일(.ttf)을 다운로드하며,
    다운로드 후 exec() 또는 eval()로 실행하지 않습니다.
    
    Args:
        url (str): 다운로드 URL (HTTPS만 허용)
        file_path (str): 저장할 파일 경로
        expected_hash (str): 신뢰할 수 있는 출처의 SHA256 해시값
    
    Returns:
        bool: 다운로드 및 검증 성공 시 True, 실패 시 False
    """
    temp_file_path = None
    try:
        # 보안: HTTPS URL만 허용 (중간자 공격 방지)
        if not url.startswith('https://'):
            st.error("❌ 보안 오류: HTTPS URL만 허용됩니다.")
            return False
        
        # User-Agent 설정 (정상적인 브라우저 요청으로 위장)
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        # 타임아웃 설정하여 다운로드 (DoS 공격 방지)
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.getcode() != 200:
                raise Exception(f"HTTP {response.getcode()} 에러")
            
            # 임시 파일로 다운로드 (원본 파일 보호)
            temp_file_path = file_path + ".tmp"
            with open(temp_file_path, 'wb') as f:
                f.write(response.read())
        
        # 🔒 중요: 다운로드된 파일의 무결성 검증 (CWE-494 대응)
        # 악성 파일이나 변조된 파일을 실행/사용하기 전에 반드시 검증
        if verify_file_integrity(temp_file_path, expected_hash):
            # 검증 성공 시에만 원본 파일로 이동
            os.rename(temp_file_path, file_path)
            st.info("✅ 파일을 안전하게 다운로드하고 무결성을 검증했습니다.")
            return True
        else:
            # 🚨 검증 실패: 즉시 파일 삭제 (악성 파일 차단)
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            st.error("❌ 무결성 검증 실패: 다운로드된 파일이 신뢰할 수 없습니다. 파일을 삭제했습니다.")
            return False
            
    except Exception as e:
        # 예외 발생 시 임시 파일 정리 (보안 강화)
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except:
                pass
        st.warning(f"보안 파일 다운로드 실패: {e}")
        return False

def setup_korean_font():
    """
    한글 폰트 설정 함수 - Azure 웹앱 환경 최적화 및 보안 강화
    
    보안 취약점 대응:
    - CWE-494: 다운로드한 파일의 무결성을 SHA256 해시로 검증
    - CWE-759: 파일 무결성 검증용 해시 사용 (비밀번호 저장 아님)
    
    동작 방식:
    1. 로컬 폰트 파일 존재 여부 확인
    2. 없으면 원격에서 HTTPS로 다운로드
    3. 다운로드 후 즉시 무결성 검증 (악성 파일 차단)
    4. 검증 실패 시 파일 삭제 및 fallback 폰트 사용
    
    주의: 다운로드하는 파일은 실행 코드가 아닌 폰트 데이터 파일(.ttf)입니다.
    """
    try:
        # 1. 프로젝트 내 fonts 디렉토리 생성
        fonts_dir = "./fonts"
        if not os.path.exists(fonts_dir):
            os.makedirs(fonts_dir)
        
        # 2. 나눔고딕 폰트 보안 다운로드 (없는 경우에만)
        font_file_path = os.path.join(fonts_dir, "NanumGothic.ttf")
        
        if not os.path.exists(font_file_path):
            # 나눔고딕 폰트의 실제 SHA256 해시값
            # 아래 명령으로 실제 해시값을 확인할 수 있습니다:
            # curl -sL https://github.com/naver/nanumfont/raw/master/fonts/NanumGothic.ttf | sha256sum
            # 
            # ⚠️ 운영 배포 시 반드시 실제 해시값으로 교체하세요!
            # 현재는 예시 값입니다.
            expected_font_hash = "c6cffd93f37b43d7a5cf0ce0dc4258e6b9b84a087c7c1e2f6f5a3e4d7c8b9a1d"
            
            try:
                # GitHub에서 나눔고딕 폰트 보안 다운로드
                font_url = "https://github.com/naver/nanumfont/raw/master/fonts/NanumGothic.ttf"
                download_success = secure_download_font(font_url, font_file_path, expected_font_hash)
                
                if not download_success:
                    st.warning("⚠️ 보안 검증된 폰트 다운로드에 실패했습니다. 시스템 폰트를 사용합니다.")
                    
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
# 📊 서비스 목록 정렬 함수 추가
# -----------------------------
def get_sorted_services(services_list, default_service=None):
    """서비스 목록을 가나다ABC순으로 정렬하고 기본 서비스를 맨 앞에 배치"""
    # 서비스 목록을 가나다ABC순으로 정렬
    sorted_services = sorted(services_list)
    
    # 기본 서비스가 있고 목록에 포함되어 있으면 맨 앞으로 이동
    if default_service and default_service in sorted_services:
        sorted_services.remove(default_service)
        sorted_services.insert(0, default_service)
    
    return sorted_services

# -----------------------------
# 📊 분석 함수들
# -----------------------------
def calculate_trend_metrics(df, current_month, current_mmdd):
    """트렌드 및 메트릭 계산 함수"""
    # 전체 오류 수
    total_errors = len(df)
    
    # 이번 달 오류 수
    current_month_errors = len(df[df['month'] == current_month])
    
    # 지난 달 오류 수 (비교용)
    last_month = current_month - 1 if current_month > 1 else 12
    last_month_errors = len(df[df['month'] == last_month])
    
    # 증가율 계산
    if last_month_errors > 0:
        month_change = ((current_month_errors - last_month_errors) / last_month_errors) * 100
    else:
        month_change = 0
    
    # 오늘 날짜 기준 오류 수
    today_errors = len(df[df['month_day'] == current_mmdd])
    
    # 가장 위험한 서비스 (이번 달 기준)
    current_month_df = df[df['month'] == current_month]
    if not current_month_df.empty:
        risk_service = current_month_df['service'].value_counts().index[0]
        risk_count = current_month_df['service'].value_counts().iloc[0]
    else:
        risk_service = "N/A"
        risk_count = 0
    
    return {
        'total_errors': total_errors,
        'current_month_errors': current_month_errors,
        'month_change': month_change,
        'today_errors': today_errors,
        'risk_service': risk_service,
        'risk_count': risk_count
    }

def create_heatmap_data(df, selected_service=None):
    """히트맵 데이터 생성 함수"""
    if selected_service:
        df_filtered = df[df['service'] == selected_service]
    else:
        df_filtered = df
    
    # 월-일 조합으로 집계
    heatmap_data = df_filtered.groupby(['month', 'day']).size().reset_index(name='count')
    
    # 피벗 테이블 생성 (월 x 일)
    pivot_data = heatmap_data.pivot(index='month', columns='day', values='count').fillna(0)
    
    # 1-12월, 1-31일 전체 범위로 확장
    full_months = range(1, 13)
    full_days = range(1, 32)
    
    pivot_data = pivot_data.reindex(index=full_months, columns=full_days, fill_value=0)
    
    return pivot_data

def calculate_moving_average(data, window=3):
    """이동평균 계산 함수 - 수정된 버전"""
    data_array = np.array(data)
    
    # 데이터가 window보다 작으면 None 반환 (그래프에서 트렌드 라인을 그리지 않음)
    if len(data_array) < window:
        return None, None
    
    # 이동평균 계산 (valid mode: 길이 = len(data) - window + 1)
    moving_avg = np.convolve(data_array, np.ones(window)/window, mode='valid')
    
    # 이동평균에 해당하는 인덱스 계산
    # window=3이면 첫 번째 값은 0,1,2의 평균 -> 인덱스 1 (중앙값)
    # window=7이면 첫 번째 값은 0,1,2,3,4,5,6의 평균 -> 인덱스 3 (중앙값)
    start_idx = window // 2
    end_idx = len(data_array) - (window - 1) + start_idx
    indices = np.arange(start_idx, end_idx)
    
    return moving_avg, indices

def get_moving_average_info(window):
    """이동평균 정보 반환 함수"""
    center_offset = window // 2
    return {
        'window': window,
        'center_offset': center_offset,
        'description': f"{window}기간 이동평균 (중앙값 기준 정렬)"
    }

# -----------------------------
# 📥 1. 데이터 업로드 / 로드
# -----------------------------
st.title("📊 서비스별 오류 시즌성 분석기")
st.write("서비스별 오류 발생 데이터를 분석해 현재 월/일 기준 시즌드리티 정보를 제공합니다.")

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
# 📅 년도 선택 기능 추가
# -----------------------------
# 데이터에서 사용 가능한 년도 추출
available_years = sorted(df['year'].unique(), reverse=True)  # 최신년도부터 정렬
default_year = available_years[0]  # 가장 최근 년도를 기본값으로

col_year1, col_year2 = st.columns([1, 3])

with col_year1:
    selected_year = st.selectbox(
        "년도 선택",
        options=available_years,
        index=0,  # 첫 번째 항목(최신년도)을 기본값으로
        help="년도를 선택하세요"
    )

with col_year2:
    st.write(f"**선택된 년도: {selected_year}년**")
    year_data_count = len(df[df['year'] == selected_year])
    st.write(f"해당 년도 총 장애 건수: **{year_data_count:,}건**")

# 선택된 년도로 데이터 필터링
df_filtered_year = df[df['year'] == selected_year].copy()

if df_filtered_year.empty:
    st.error(f"⚠️ {selected_year}년에 해당하는 데이터가 없습니다.")
    st.stop()

# -----------------------------
# 📊 3. 년도별 월별 장애건수 차트 (최상단 추가)
# -----------------------------
st.subheader(f"📈 {selected_year}년 월별 장애 발생 현황")

# 월별 집계
monthly_total = df_filtered_year.groupby('month').size().reset_index(name='count')

# 1-12월 전체 범위로 확장 (없는 월은 0으로)
full_months_df = pd.DataFrame({'month': range(1, 13)})
monthly_total_full = pd.merge(full_months_df, monthly_total, on='month', how='left').fillna(0)
monthly_total_full['count'] = monthly_total_full['count'].astype(int)

# 차트 생성
fig_monthly, ax_monthly = plt.subplots(figsize=(8.4, 6))
bars_monthly = ax_monthly.bar(monthly_total_full['month'], monthly_total_full['count'], 
                             color='skyblue', alpha=0.8, edgecolor='darkblue', linewidth=1)

# 현재 월 강조 (선택된 년도가 올해인 경우)
today = datetime.today()
if selected_year == today.year:
    current_month = today.month
    if current_month <= 12:
        current_month_idx = current_month - 1
        if current_month_idx < len(bars_monthly):
            bars_monthly[current_month_idx].set_color('orange')
            bars_monthly[current_month_idx].set_alpha(1.0)

# 차트 꾸미기
ax_monthly.set_title(f"{selected_year}년 월별 장애 발생 건수", fontsize=16, pad=20, fontweight='bold')
ax_monthly.set_xlabel("월", fontsize=12)
ax_monthly.set_ylabel("장애 건수", fontsize=12)
ax_monthly.set_xticks(range(1, 13))
ax_monthly.grid(True, alpha=0.3, axis='y')

# 데이터 레이블 추가
for i, bar in enumerate(bars_monthly):
    height = bar.get_height()
    if height > 0:
        ax_monthly.text(bar.get_x() + bar.get_width()/2., height + max(monthly_total_full['count']) * 0.01,
                       f'{int(height)}', ha='center', va='bottom', fontsize=10)

plt.tight_layout()
col_chart = st.columns([0.15, 0.7, 0.15])
with col_chart[1]:
    st.pyplot(fig_monthly)

# 월별 요약 통계
col_stat1, col_stat2, col_stat3 = st.columns(3)
with col_stat1:
    peak_month = monthly_total_full.loc[monthly_total_full['count'].idxmax(), 'month']
    peak_count = monthly_total_full['count'].max()
    st.metric("🔥 최고 장애 월", f"{peak_month}월", f"{peak_count}건")

with col_stat2:
    avg_monthly = monthly_total_full['count'].mean()
    st.metric("📊 월평균 장애", f"{avg_monthly:.1f}건")

with col_stat3:
    total_yearly = monthly_total_full['count'].sum()
    st.metric("📈 연간 총 장애", f"{total_yearly}건")

# -----------------------------
# 구분선 추가
# -----------------------------
st.markdown("---")
st.markdown("## 📊 전체 기간 시즌성 분석")
st.write("아래부터는 전체 기간의 데이터를 기반으로 한 시즌성 분석입니다.")

# -----------------------------
# 📈 4. 메트릭 카드 표시
# -----------------------------
today = datetime.today()
current_month = today.month
current_mmdd = today.strftime("%m-%d")

# 메트릭 계산
metrics = calculate_trend_metrics(df, current_month, current_mmdd)

# 메트릭 카드를 4개 컬럼으로 배치
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="📈 전체 오류 수",
        value=f"{metrics['total_errors']:,}",
        help="전체 기간 동안 발생한 총 오류 수"
    )

with col2:
    st.metric(
        label=f"📅 {current_month}월 오류 수",
        value=f"{metrics['current_month_errors']:,}",
        delta=f"{metrics['month_change']:.1f}%",
        help="이번 달 오류 수 (전월 대비 증가율)"
    )

with col3:
    st.metric(
        label=f"🎯 오늘({current_mmdd}) 예상",
        value=f"{metrics['today_errors']}",
        help="과거 동일 날짜 기준 예상 오류 수"
    )

with col4:
    st.metric(
        label="🚨 위험 서비스",
        value=f"{metrics['risk_service']}",
        delta=f"{metrics['risk_count']}건",
        help="이번 달 가장 많은 오류가 발생한 서비스"
    )

# -----------------------------
# 📊 5. 집계 처리
# -----------------------------
monthly_counts = df.groupby(["service", "month"]).size().reset_index(name="count")
day_counts = df.groupby(["service", "month_day"]).size().reset_index(name="count")

# -----------------------------
# 📅 6. 현재 기준 예측 (기존)
# -----------------------------
st.subheader(f"📅 현재 월({current_month}월) 기준 위험 서비스")

top_services_month = (
    monthly_counts[monthly_counts["month"] == current_month]
    .sort_values(by="count", ascending=False)
    .reset_index(drop=True)
)

if not top_services_month.empty:
    st.dataframe(top_services_month, use_container_width=True)
else:
    st.info("현재 월에 해당하는 데이터가 없습니다.")

st.subheader(f"📆 오늘({current_mmdd}) 기준 위험 서비스")

top_services_day = (
    day_counts[day_counts["month_day"] == current_mmdd]
    .sort_values(by="count", ascending=False)
    .reset_index(drop=True)
)

if not top_services_day.empty:
    st.dataframe(top_services_day, use_container_width=True)
else:
    st.info("오늘 날짜에 해당하는 과거 데이터가 없습니다.")

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
# 📉 7. 특정 서비스 시각화 - 월별 (수정된 이동평균)
# -----------------------------
st.subheader("📊 서비스별 월별 오류 시즌성 그래프")

unique_services = df["service"].unique().tolist()
# 정렬된 서비스 목록 사용
unique_services = get_sorted_services(unique_services, default_service)

selected_service = st.selectbox("서비스 선택", unique_services)

service_monthly = monthly_counts[monthly_counts["service"] == selected_service]

# 1-12월 전체 데이터로 확장 (없는 월은 0으로)
full_months = pd.DataFrame({'month': range(1, 13)})
service_monthly_full = pd.merge(full_months, service_monthly[['month', 'count']], on='month', how='left')

# fillna 전에 디버깅 정보 출력 (개발용)
if service_monthly_full['count'].isna().any():
    service_monthly_full['count'] = service_monthly_full['count'].fillna(0)
service_monthly_full['count'] = service_monthly_full['count'].astype(int)

# 트렌드 라인 계산 (3개월 이동평균) - 수정된 버전
window_months = 3
ma_info_months = get_moving_average_info(window_months)
trend_data_months, trend_indices_months = calculate_moving_average(service_monthly_full['count'].values, window_months)

fig, ax = plt.subplots(figsize=(8.4, 6))

# 실제 데이터 막대그래프
bars = ax.bar(service_monthly_full["month"], service_monthly_full["count"], alpha=0.7, label="실제 오류 수")

# 트렌드 라인 추가 (데이터가 충분한 경우에만)
if trend_data_months is not None and trend_indices_months is not None:
    # 실제 월 번호로 변환 (인덱스는 0부터 시작하므로 +1)
    trend_months_actual = trend_indices_months + 1
    ax.plot(trend_months_actual, trend_data_months, 
           color='red', linewidth=3, marker='o', markersize=6, 
           label=f"트렌드 ({ma_info_months['description']})", alpha=0.8)

ax.set_title(f"{selected_service} - 월별 오류 발생 패턴 및 트렌드", fontsize=14, pad=20)
ax.set_xlabel("월", fontsize=12)
ax.set_ylabel("오류 수", fontsize=12)
ax.set_xticks(range(1, 13))
ax.grid(True, alpha=0.3)
ax.legend()

# 현재 월 강조
current_month_idx = current_month - 1
if current_month_idx < len(bars):
    bars[current_month_idx].set_color('orange')
    bars[current_month_idx].set_alpha(1.0)

plt.tight_layout()
col_chart = st.columns([0.15, 0.7, 0.15])
with col_chart[1]:
    st.pyplot(fig)

# 트렌드 분석 설명
with st.expander("📈 트렌드 분석 해석"):
    st.write(f"""
    - **주황색 막대**: 현재 월
    - **빨간색 선**: {ma_info_months['description']}
    - **상승 트렌드**: 오류가 증가하는 추세
    - **하강 트렌드**: 오류가 감소하는 추세
    - **평평한 트렌드**: 오류가 안정적인 상태
    
    **이동평균 설명**: {window_months}개월간의 평균값을 계산하여 단기 변동을 제거하고 장기 추세를 파악합니다.
    """)

# -----------------------------
# 📉 8. 서비스별 일별 오류 시즌성 그래프 (수정된 이동평균)
# -----------------------------
st.subheader("📊 서비스별 일별 오류 시즌성 그래프")

# 정렬된 서비스 목록 사용
unique_services_day = df["service"].unique().tolist()
unique_services_day = get_sorted_services(unique_services_day, default_service)

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

# 트렌드 라인 계산 (7일 이동평균) - 수정된 버전
window_days = 7
ma_info_days = get_moving_average_info(window_days)
trend_data_days, trend_indices_days = calculate_moving_average(daily_counts['count'].values, window_days)

# 최댓값 계산 (Y축 최소 5 보장)
y_max = max(5, daily_counts["count"].max())

# 막대그래프 출력
month_title = selected_month_option if selected_month_option != "전체" else "전체 기간"
fig2, ax2 = plt.subplots(figsize=(9.8, 6))

# 실제 데이터 막대그래프
bars2 = ax2.bar(daily_counts["day"], daily_counts["count"], alpha=0.7, label="실제 오류 수")

# 트렌드 라인 추가 (데이터가 충분한 경우에만)
if trend_data_days is not None and trend_indices_days is not None:
    # 실제 일 번호로 변환 (인덱스는 0부터 시작하므로 +1)
    trend_days_actual = trend_indices_days + 1
    ax2.plot(trend_days_actual, trend_data_days, 
           color='red', linewidth=2, marker='o', markersize=4, 
           label=f"트렌드 ({ma_info_days['description']})", alpha=0.8)

ax2.set_title(f"{selected_service_day} - {month_title} 일별 오류 발생 패턴 및 트렌드", fontsize=14, pad=20)
ax2.set_xlabel("일", fontsize=12)
ax2.set_ylabel("오류 수", fontsize=12)
ax2.set_xticks(range(1, 32))
ax2.set_ylim(0, y_max * 1.1)
ax2.grid(True, alpha=0.3)
ax2.legend()

# 현재 날짜 강조 (해당 월인 경우)
if selected_month_option == "전체" or int(selected_month_option.replace("월", "")) == current_month:
    current_day = today.day
    if current_day <= 31:
        current_day_idx = current_day - 1
        if current_day_idx < len(bars2):
            bars2[current_day_idx].set_color('orange')
            bars2[current_day_idx].set_alpha(1.0)

plt.tight_layout()
col_chart = st.columns([0.15, 0.7, 0.15])
with col_chart[1]:
    st.pyplot(fig2)

# 📆 9. 서비스별 요일별 오류 그래프
st.subheader("📆 서비스별 요일별 오류 발생 패턴")

# 정렬된 서비스 목록 사용
unique_services_week = df["service"].unique().tolist()
unique_services_week = get_sorted_services(unique_services_week, default_service)

selected_service_week = st.selectbox("서비스 선택 (요일)", unique_services_week, key="weekday_select")

weekday_order_kr = ["월", "화", "수", "목", "금", "토", "일"]

weekday_df = df[df["service"] == selected_service_week]
weekday_counts = (
    weekday_df.groupby("week")
    .size()
    .reindex(weekday_order_kr, fill_value=0)
    .reset_index(name="count")
)

fig3, ax3 = plt.subplots(figsize=(7, 6))
bars3 = ax3.bar(weekday_counts["week"], weekday_counts["count"])

# 현재 요일 강조
today_weekday = weekday_map[today.weekday()]
for i, bar in enumerate(bars3):
    if weekday_counts.iloc[i]["week"] == today_weekday:
        bar.set_color('orange')
        bar.set_alpha(1.0)

ax3.set_title(f"{selected_service_week} - 요일별 오류 발생 패턴", fontsize=14, pad=20)
ax3.set_xlabel("요일", fontsize=12)
ax3.set_ylabel("오류 수", fontsize=12)
ax3.grid(True, alpha=0.3)
plt.tight_layout()
col_chart = st.columns([0.15, 0.7, 0.15])
with col_chart[1]:
    st.pyplot(fig3)

# 🌙 10. 서비스별 주간/야간 오류 그래프
if 'daynight' in df.columns:
    st.subheader("🌙 서비스별 주간/야간 오류 발생 패턴")

    # 정렬된 서비스 목록 사용
    unique_services_daynight = df["service"].unique().tolist()
    unique_services_daynight = get_sorted_services(unique_services_daynight, default_service)

    selected_service_daynight = st.selectbox("서비스 선택 (주간/야간)", unique_services_daynight, key="daynight_select")

    time_df = df[df["service"] == selected_service_daynight]
    time_counts = (
        time_df["daynight"]
        .value_counts()
        .reindex(["주간", "야간"], fill_value=0)
        .reset_index()
    )
    time_counts.columns = ["daynight", "count"]

    fig4, ax4 = plt.subplots(figsize=(5.6, 6))
    ax4.bar(time_counts["daynight"], time_counts["count"])
    ax4.set_title(f"{selected_service_daynight} - 주간/야간 오류 발생 패턴", fontsize=14, pad=20)
    ax4.set_xlabel("시간대", fontsize=12)
    ax4.set_ylabel("오류 수", fontsize=12)
    ax4.grid(True, alpha=0.3)
    plt.tight_layout()
    col_chart = st.columns([0.15, 0.7, 0.15])
    with col_chart[1]:
        st.pyplot(fig4)
else:
    st.info("주간/야간 데이터(daynight 컬럼)가 없어 해당 차트를 표시할 수 없습니다.")

# -----------------------------
# 📋 11. 요약 및 인사이트
# -----------------------------
st.subheader("💡 주요 인사이트")

# 인사이트 생성
insights = []

# 가장 활발한 월 찾기
most_active_month = df.groupby('month').size().idxmax()
insights.append(f"🔥 **{most_active_month}월**이 가장 오류가 많이 발생하는 월입니다.")

# 가장 활발한 요일 찾기
most_active_weekday = df.groupby('week').size().idxmax()
insights.append(f"📅 **{most_active_weekday}요일**에 오류가 가장 많이 발생합니다.")

# 가장 문제가 많은 서비스
most_problematic_service = df['service'].value_counts().index[0]
insights.append(f"⚠️ **{most_problematic_service}** 서비스가 전체적으로 가장 많은 오류를 발생시킵니다.")

# 계절성 패턴
winter_months = df[df['month'].isin([12, 1, 2])].shape[0]
summer_months = df[df['month'].isin([6, 7, 8])].shape[0]
if winter_months > summer_months * 1.2:
    insights.append("❄️ 겨울철 (12-2월)에 오류가 집중되는 경향을 보입니다.")
elif summer_months > winter_months * 1.2:
    insights.append("☀️ 여름철 (6-8월)에 오류가 집중되는 경향을 보입니다.")

for insight in insights:
    st.write(insight)

# -----------------------------
# 🔥 12. 히트맵 시각화
# -----------------------------
st.subheader("🔥 월-일별 오류 발생 히트맵")

# 히트맵 서비스 목록 정렬 (전체 옵션 포함)
heatmap_services_raw = df["service"].unique().tolist()
heatmap_services_sorted = get_sorted_services(heatmap_services_raw)
heatmap_services = ["전체"] + heatmap_services_sorted

selected_heatmap_service = st.selectbox("히트맵 서비스 선택", heatmap_services, key="heatmap_service")

# 히트맵 데이터 생성
if selected_heatmap_service == "전체":
    heatmap_data = create_heatmap_data(df)
    title_suffix = "전체 서비스"
else:
    heatmap_data = create_heatmap_data(df, selected_heatmap_service)
    title_suffix = selected_heatmap_service

# 히트맵 그리기
fig_heatmap, ax_heatmap = plt.subplots(figsize=(11.2, 8))
sns.heatmap(
    heatmap_data, 
    annot=False, 
    cmap='YlOrRd', 
    ax=ax_heatmap,
    cbar_kws={'label': '오류 발생 수'},
    linewidths=0.8,
    linecolor='gray'
)
ax_heatmap.set_title(f"{title_suffix} - 월별/일별 오류 발생 히트맵", fontsize=16, pad=20)
ax_heatmap.set_xlabel("일", fontsize=12)
ax_heatmap.set_ylabel("월", fontsize=12)
ax_heatmap.set_yticklabels([f"{i}월" for i in range(1, 13)], rotation=0)
plt.tight_layout()
col_chart = st.columns([0.15, 0.7, 0.15])
with col_chart[1]:
    st.pyplot(fig_heatmap)

# 히트맵 해석 도움말
with st.expander("📖 히트맵 해석 가이드"):
    st.write("""
    - **색깔이 진할수록**: 해당 월-일 조합에서 오류가 많이 발생
    - **가로축(일)**: 1일부터 31일까지
    - **세로축(월)**: 1월부터 12월까지
    - **패턴 분석**: 특정 시기에 집중되는 오류 패턴을 한눈에 파악 가능
    """)

# 사용법 안내
with st.expander("🎯 분석 활용 가이드"):
    st.write("""
    **이 분석을 활용하는 방법:**
    
    1. **메트릭 대시보드**: 전체적인 현황을 한눈에 파악
    2. **히트맵**: 월-일별 패턴을 시각적으로 분석해 특정 시기의 위험도 예측
    3. **트렌드 라인**: 이동평균을 통해 장기적인 추세 파악
    4. **현재 기준 예측**: 오늘과 이번 달의 위험 서비스 미리 파악
    5. **시각화 차트**: 각 서비스별 상세한 패턴 분석
    
    **이동평균 해석:**
    - **월별 트렌드**: 3개월 이동평균으로 계절성 및 장기 추세 파악
    - **일별 트렌드**: 7일 이동평균으로 주간 패턴 및 단기 추세 파악
    - 이동평균은 데이터의 노이즈를 제거하고 전반적인 경향을 보여줍니다
    
    **주의사항:**
    - 과거 데이터 기반 예측이므로 새로운 변수(시스템 변경, 외부 요인 등)는 고려되지 않음
    - 트렌드 라인은 평활화된 데이터이므로 급격한 변화는 감지하기 어려움
    """)

