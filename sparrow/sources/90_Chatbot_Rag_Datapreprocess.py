import streamlit as st
import pandas as pd
from openai import AzureOpenAI
from io import StringIO
import re
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# Streamlit 페이지 설정
st.set_page_config(
    page_title="인시던트 요약 시스템",
    page_icon="🔧",
    layout="wide"
)

st.title("🔧 인시던트 요약 시스템")
st.markdown("---")

# .env 파일에서 Azure OpenAI 설정 로드
azure_openai_endpoint = os.getenv("OPENAI_ENDPOINT")
azure_openai_key = os.getenv("OPENAI_KEY")
azure_openai_model = os.getenv("CHAT_MODEL", "iap-gpt-4o-mini")
azure_openai_api_version = os.getenv("OPENAI_API_VERSION", "2024-02-01")

# Azure OpenAI 클라이언트 초기화
client = None

if azure_openai_endpoint and azure_openai_key:
    try:
        client = AzureOpenAI(
            azure_endpoint=azure_openai_endpoint,
            api_key=azure_openai_key,
            api_version=azure_openai_api_version
        )
    except Exception as e:
        st.error(f"❌ Azure OpenAI 클라이언트 초기화 실패: {str(e)}")
else:
    # 수동 입력 옵션을 사이드바에만 표시
    with st.sidebar:
        st.header("⚙️ Azure OpenAI 설정")
        st.warning("⚠️ .env 파일에서 Azure OpenAI 설정을 찾을 수 없습니다.")
        
        with st.expander("🔧 수동 설정"):
            manual_endpoint = st.text_input("Azure OpenAI Endpoint:", value=azure_openai_endpoint or "")
            manual_key = st.text_input("Azure OpenAI Key:", type="password", value=azure_openai_key or "")
            manual_model = st.text_input("Chat Model:", value=azure_openai_model)
            manual_api_version = st.text_input("API Version:", value=azure_openai_api_version)
            
            if manual_endpoint and manual_key:
                try:
                    client = AzureOpenAI(
                        azure_endpoint=manual_endpoint,
                        api_key=manual_key,
                        api_version=manual_api_version
                    )
                    azure_openai_model = manual_model
                    st.success("✅ 수동 설정으로 Azure OpenAI 클라이언트가 초기화되었습니다.")
                except Exception as e:
                    st.error(f"❌ Azure OpenAI 클라이언트 초기화 실패: {str(e)}")

# 요약 함수
def summarize_text(text, summary_type, max_tokens=150):
    """
    Azure OpenAI API를 사용하여 텍스트를 요약합니다.
    
    Args:
        text (str): 요약할 텍스트
        summary_type (str): 요약 유형 (장애원인, 복구방법, 후속과제)
        max_tokens (int): 최대 토큰 수
    
    Returns:
        str: 요약된 텍스트
    """
    if not text or pd.isna(text) or text.strip() == "":
        return "정보 없음"
    
    if not client:
        return "Azure OpenAI 클라이언트가 초기화되지 않았습니다."
    
    # 텍스트 전처리 (불필요한 공백, 개행 문자 정리)
    cleaned_text = re.sub(r'\s+', ' ', str(text).strip())
    
    try:
        prompt_templates = {
            "장애원인": f"""
다음 장애원인 텍스트에서 장애를 직접적으로 유발한 근본원인을 명확하게 식별하여 요약해주세요.
원인과 결과의 인과관계를 명확히 하고, 기술적 세부사항을 포함하여 재발방지에 도움이 되도록 구체적으로 작성하세요.

분석 기준:
1. 근본원인(Root Cause): 장애를 최초로 유발한 직접적 원인
2. 연쇄반응: 근본원인이 어떻게 최종 장애로 이어졌는지
3. 기술적 세부사항: 관련 시스템, 구성요소, 설정값 등

포함할 내용:
- 구체적인 시스템/컴포넌트 명칭
- 정확한 오류 내용이나 설정 문제
- 영향받은 서비스나 기능
- 장애 전파 경로 (A → B → C)
- 임계치 초과, 용량 한계 등 수치 정보
- 작업 실수의 구체적 내용

제외할 내용:
- 추상적 표현 ("시스템 문제", "네트워크 이슈" 등)
- 발견 과정이나 대응 과정
- 추정성 내용 ("~로 보임", "~일 가능성")
- 시간 정보나 담당자 정보

출력 규칙:
- 레이블 없이 내용만 작성 (장애원인요약: 등의 표현 금지)
- 쌍따옴표, 따옴표 사용 금지
- 순수 텍스트만 출력

출력 형식:
[구체적 시스템/구성요소]에서 [정확한 문제 상황/오류 내용]이 발생하여 [연쇄반응 과정]을 통해 [최종 장애 결과]가 나타남.

예시들:
원문: 방화벽 정책 작업 오수행으로 IAMUI WAS에서 WEB의 메일포맷 호출 연동 정책 삭제
출력: 방화벽 정책 변경 작업 중 작업자 실수로 정책 ID 596(IAMUI WAS-메일서버 SMTP 연동) 정책이 삭제되어 WAS에서 메일서버로의 통신이 차단됨

원문: {cleaned_text}""",
            "복구방법": f"""
다음 복구방법 텍스트에서 실제 장애복구에 직접적으로 기여한 핵심 조치사항만 추출하여 요약해주세요.
시간정보, 상황공지, 점검활동, 확인작업 등은 제외하고 오직 복구를 위한 실질적인 기술적 조치만 포함하세요.

포함할 내용:
- 시스템/서비스 재기동, 재시작
- 설정 변경, 정책 수정
- 데이터 복구, 동기화
- 하드웨어 교체, 수리
- 네트워크 복구, 연결 복원
- 프로세스 복구, 서비스 복원

제외할 내용:
- 시간 정보 (06:44, 07:20 등)
- 상황 공지, 알림 발송
- 단순 확인, 점검, 모니터링
- 담당자 연락, 회의 개최
- 상황창 개설, 에스컬레이션

출력 규칙:
- 레이블 없이 내용만 작성 (복구조치요약: 등의 표현 금지)
- 쌍따옴표, 따옴표 사용 금지
- 순수 텍스트만 출력

예시:
원문: 06:44 장애발생, 07:20 점검시작, 08:26 Kafka 재기동, 08:30 상황공지, 08:40 정상확인
출력: Kafka 재기동으로 복구

원문: {cleaned_text}""",
            "후속과제": f"""
다음 후속과제 텍스트에서 실제 장애 재발방지와 시스템 개선에 직접적으로 기여하는 구체적인 과제만 추출하여 요약해주세요.
각 과제를 번호를 매겨 명확하고 실행 가능한 형태로 정리하세요.

포함할 내용:
- 시스템/인프라 개선 작업
- 모니터링/관제 강화 방안
- 프로세스/절차 개선
- 하드웨어/소프트웨어 업그레이드
- 교육/훈련 계획
- 자동화/표준화 구축
- 백업/복구 체계 강화

제외할 내용:
- 추상적이고 모호한 표현
- 단순 검토, 협의, 논의
- 일반적인 교육이나 인식개선
- 구체적 실행방안이 없는 과제
- 중복되거나 유사한 내용

출력 규칙:
- 레이블 없이 내용만 작성 (후속과제요약: 등의 표현 금지)
- 쌍따옴표, 따옴표 사용 금지
- 순수 텍스트만 출력

출력 형식:
1. [구체적 과제명] ([담당부서/완료목표] 포함)
2. [구체적 과제명] ([담당부서/완료목표] 포함)

예시:
원문: 방화벽 정책 작업 전 체크리스트 검증 이행, 관제 기능 강화, 정기적 교육 시행
출력: 
1. 방화벽 정책 작업 체크리스트 의무화 (인프라팀, 즉시 적용)
2. 실시간 관제 알람 기능 구현 (관제팀, 1개월 내)

원문: {cleaned_text}"""
        }
        
        response = client.chat.completions.create(
            model=azure_openai_model,
            messages=[
                {"role": "system", "content": "당신은 IT 인시던트 분석 전문가입니다. 제공된 텍스트를 간결하고 명확하게 요약해주세요."},
                {"role": "user", "content": prompt_templates[summary_type]}
            ],
            max_tokens=max_tokens,
            temperature=0.3
        )
        
        summary = response.choices[0].message.content.strip()
        return summary
        
    except Exception as e:
        st.error(f"요약 생성 중 오류가 발생했습니다: {str(e)}")
        return f"요약 실패: {str(e)}"

def process_excel_file(uploaded_file, max_tokens=150):
    """
    업로드된 Excel 파일을 처리하고 요약을 생성합니다.
    
    Args:
        uploaded_file: Streamlit의 업로드된 파일 객체
        max_tokens (int): 요약의 최대 토큰 수
    
    Returns:
        pandas.DataFrame: 요약이 포함된 데이터프레임
    """
    try:
        # Excel 파일 읽기
        df = pd.read_excel(uploaded_file)
        
        # 컬럼명 확인 및 매핑
        expected_columns = ['incident_id', 'root_cause', 'incident_repair', 'incident_plan']
        
        if not all(col in df.columns for col in expected_columns):
            st.error(f"Excel 파일에 필요한 컬럼이 없습니다. 필요한 컬럼: {expected_columns}")
            st.error(f"현재 파일의 컬럼: {list(df.columns)}")
            return None
        
        # 결과 데이터프레임 초기화
        result_df = pd.DataFrame()
        result_df['인시던트번호'] = df['incident_id']
        
        # 진행률 표시
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_rows = len(df)
        summaries = {
            '장애원인요약': [],
            '복구방법요약': [],
            '후속과제요약': []
        }
        
        # 각 행에 대해 요약 생성
        for idx, row in df.iterrows():
            status_text.text(f'처리 중: {idx + 1}/{total_rows} - {row["incident_id"]}')
            
            # 각 필드별 요약 생성
            root_cause_summary = summarize_text(row['root_cause'], "장애원인", max_tokens)
            repair_summary = summarize_text(row['incident_repair'], "복구방법", max_tokens)
            plan_summary = summarize_text(row['incident_plan'], "후속과제", max_tokens)
            
            summaries['장애원인요약'].append(root_cause_summary)
            summaries['복구방법요약'].append(repair_summary)
            summaries['후속과제요약'].append(plan_summary)
            
            # 진행률 업데이트
            progress_bar.progress((idx + 1) / total_rows)
        
        # 결과 데이터프레임에 요약 추가
        for key, value in summaries.items():
            result_df[key] = value
        
        status_text.text('완료!')
        progress_bar.progress(1.0)
        
        return result_df
        
    except Exception as e:
        st.error(f"파일 처리 중 오류가 발생했습니다: {str(e)}")
        return None

def main():
    """메인 애플리케이션"""
    
    # 사용법 안내를 메인 화면에 표시
    st.header("📋 사용법")
    
    # 사용법을 탭으로 구성
    tab1, tab2 = st.tabs(["🚀 빠른 시작", "📄 파일 형식"])
    
    with tab1:
        st.markdown("""
        #### 간단한 3단계로 인시던트 요약을 생성하세요!
        
        1. **Excel 파일 업로드** - 인시던트 데이터가 포함된 Excel 파일을 업로드하세요
        2. **요약 생성** - '요약 생성' 버튼을 클릭하여 AI 기반 요약을 생성하세요
        3. **결과 다운로드** - 생성된 요약을 확인하고 CSV 파일로 다운로드하세요
        """)
        
        # 진행 상태 체크
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            if client:
                st.success("✅ Azure OpenAI 연결됨")
            else:
                st.error("❌ Azure OpenAI 설정 필요")
        
        with col2:
            st.info("📁 Excel 파일 업로드 대기")
        
        with col3:
            st.info("⏳ 요약 생성 대기")
        
        with col4:
            st.info("📥 다운로드 대기")
    
    with tab2:
        st.markdown("""
        #### Excel 파일에 다음 컬럼이 포함되어야 합니다:
        """)
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown("""
            **필수 컬럼:**
            - `incident_id` 
            - `root_cause`
            - `incident_repair`
            - `incident_plan`
            """)
        
        with col2:
            st.markdown("""
            **컬럼 설명:**
            - 인시던트 고유 번호
            - 장애 원인 상세 내용
            - 복구 방법 및 조치사항
            - 후속 과제 및 개선사항
            """)
        
        st.info("💡 **팁:** 각 셀에는 상세한 텍스트 정보가 포함되어야 AI가 정확한 요약을 생성할 수 있습니다.")
    
    st.markdown("---")
    
    # 메인 작업 영역
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("📁 파일 업로드")
        uploaded_file = st.file_uploader(
            "인시던트 Excel 파일을 선택하세요",
            type=['xlsx', 'xls'],
            help="incident_id, root_cause, incident_repair, incident_plan 컬럼이 포함된 Excel 파일"
        )
        
        if uploaded_file is not None:
            # 파일 정보 표시
            st.success(f"파일이 업로드되었습니다: {uploaded_file.name}")
            
            # 파일 미리보기
            try:
                preview_df = pd.read_excel(uploaded_file, nrows=3)
                st.subheader("📊 파일 미리보기")
                st.dataframe(preview_df, use_container_width=True)
                
                # 파일 정보
                full_df = pd.read_excel(uploaded_file)
                st.info(f"총 {len(full_df)}개의 인시던트가 포함되어 있습니다.")
                
            except Exception as e:
                st.error(f"파일 미리보기 중 오류가 발생했습니다: {str(e)}")
    
    with col2:
        st.header("⚙️ 처리 옵션")
        
        # 요약 옵션
        max_tokens = st.slider(
            "최대 요약 길이 (토큰)",
            min_value=50,
            max_value=500,
            value=200,
            help="요약의 최대 길이를 설정합니다. 값이 클수록 더 상세한 요약이 생성됩니다."
        )
        
        st.markdown("---")
        
        # Azure OpenAI 클라이언트 확인
        if not client:
            st.warning("⚠️ Azure OpenAI 설정을 완료해주세요.")
        elif not uploaded_file:
            st.warning("⚠️ Excel 파일을 먼저 업로드해주세요.")
        else:
            st.success("✅ 모든 설정이 완료되었습니다.")
    
    # 요약 생성 버튼
    if st.button("🚀 요약 생성", type="primary", disabled=(not client or not uploaded_file)):
        if client and uploaded_file:
            with st.spinner("요약을 생성하는 중입니다. 잠시만 기다려주세요..."):
                result_df = process_excel_file(uploaded_file, max_tokens)
                
                if result_df is not None:
                    st.success("✅ 요약이 완료되었습니다!")
                    
                    # 결과 표시
                    st.header("📈 요약 결과")
                    st.dataframe(result_df, use_container_width=True)
                    
                    # CSV 다운로드
                    csv = result_df.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button(
                        label="📥 CSV 파일 다운로드",
                        data=csv,
                        file_name=f"incident_summary_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
                    
                    # 통계 정보
                    with st.expander("📊 처리 통계"):
                        st.metric("총 처리된 인시던트", len(result_df))
                        st.metric("생성된 요약", len(result_df) * 3)  # 각 인시던트당 3개의 요약
                        
                        # 평균 요약 길이
                        avg_lengths = {}
                        for col in ['장애원인요약', '복구방법요약', '후속과제요약']:
                            avg_length = result_df[col].str.len().mean()
                            avg_lengths[col] = f"{avg_length:.1f}자"
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("장애원인 평균 길이", avg_lengths['장애원인요약'])
                        with col2:
                            st.metric("복구방법 평균 길이", avg_lengths['복구방법요약'])
                        with col3:
                            st.metric("후속과제 평균 길이", avg_lengths['후속과제요약'])

if __name__ == "__main__":
    main()