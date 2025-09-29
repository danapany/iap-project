import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime
import chardet
import io

# 페이지 설정
st.set_page_config(
    page_title="인시던트 데이터 관리",
    page_icon="🔧",
    layout="wide"
)

# 데이터베이스 경로 설정
DB_DIR = "data/db"
DB_PATH = os.path.join(DB_DIR, "incident_data.db")

# 데이터베이스 디렉토리 생성
os.makedirs(DB_DIR, exist_ok=True)

# 데이터베이스 초기화
def init_database():
    """데이터베이스 테이블 생성"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id TEXT,
            service_name TEXT,
            error_time INTEGER,
            effect TEXT,
            symptom TEXT,
            repair_notice TEXT,
            error_date DATE,
            week TEXT,
            daynight TEXT,
            root_cause TEXT,
            incident_repair TEXT,
            incident_plan TEXT,
            cause_type TEXT,
            done_type TEXT,
            incident_grade TEXT,
            owner_depart TEXT,
            year TEXT,
            month TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# UTF-8 인코딩 체크 함수
def check_encoding(file_content):
    """파일 인코딩 체크"""
    try:
        detected = chardet.detect(file_content)
        encoding = detected['encoding']
        confidence = detected['confidence']
        
        if encoding and encoding.lower() in ['utf-8', 'utf-8-sig']:
            return True, encoding, confidence
        else:
            return False, encoding, confidence
    except Exception as e:
        return False, None, 0

# CSV 파일 업로드 함수
def upload_csv_data(df):
    """CSV 데이터를 데이터베이스에 저장"""
    conn = sqlite3.connect(DB_PATH)
    
    try:
        # 컬럼명 매핑 (필요시)
        expected_columns = [
            'incident_id', 'service_name', 'error_time', 'effect', 'symptom',
            'repair_notice', 'error_date', 'week', 'daynight', 'root_cause',
            'incident_repair', 'incident_plan', 'cause_type', 'done_type',
            'incident_grade', 'owner_depart', 'year', 'month'
        ]
        
        # 컬럼 체크
        if not all(col in df.columns for col in expected_columns):
            missing_cols = [col for col in expected_columns if col not in df.columns]
            return False, f"누락된 컬럼: {', '.join(missing_cols)}"
        
        # 데이터 삽입
        df.to_sql('incidents', conn, if_exists='append', index=False)
        return True, f"{len(df)}개의 레코드가 성공적으로 업로드되었습니다."
        
    except Exception as e:
        return False, f"데이터 업로드 중 오류 발생: {str(e)}"
    finally:
        conn.close()

# 데이터 조회 함수
def get_incidents(limit=100, search_term=""):
    """인시던트 데이터 조회"""
    conn = sqlite3.connect(DB_PATH)
    
    if search_term:
        query = """
        SELECT * FROM incidents 
        WHERE incident_id LIKE ? OR service_name LIKE ? OR effect LIKE ?
        ORDER BY created_at DESC LIMIT ?
        """
        df = pd.read_sql_query(query, conn, params=[f'%{search_term}%', f'%{search_term}%', f'%{search_term}%', limit])
    else:
        query = "SELECT * FROM incidents ORDER BY created_at DESC LIMIT ?"
        df = pd.read_sql_query(query, conn, params=[limit])
    
    conn.close()
    return df

# 개별 레코드 추가 함수
def add_incident(data):
    """새 인시던트 추가"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO incidents (
                incident_id, service_name, error_time, effect, symptom,
                repair_notice, error_date, week, daynight, root_cause,
                incident_repair, incident_plan, cause_type, done_type,
                incident_grade, owner_depart, year, month
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', data)
        
        conn.commit()
        return True, "인시던트가 성공적으로 추가되었습니다."
    except Exception as e:
        return False, f"추가 중 오류 발생: {str(e)}"
    finally:
        conn.close()

# 레코드 업데이트 함수
def update_incident(incident_id, data):
    """인시던트 업데이트"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE incidents SET
                incident_id=?, service_name=?, error_time=?, effect=?, symptom=?,
                repair_notice=?, error_date=?, week=?, daynight=?, root_cause=?,
                incident_repair=?, incident_plan=?, cause_type=?, done_type=?,
                incident_grade=?, owner_depart=?, year=?, month=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        ''', data + [incident_id])
        
        conn.commit()
        return True, "인시던트가 성공적으로 업데이트되었습니다."
    except Exception as e:
        return False, f"업데이트 중 오류 발생: {str(e)}"
    finally:
        conn.close()

# 레코드 삭제 함수
def delete_incident(incident_id):
    """인시던트 삭제"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('DELETE FROM incidents WHERE id=?', (incident_id,))
        conn.commit()
        
        if cursor.rowcount > 0:
            return True, "인시던트가 성공적으로 삭제되었습니다."
        else:
            return False, "삭제할 인시던트를 찾을 수 없습니다."
    except Exception as e:
        return False, f"삭제 중 오류 발생: {str(e)}"
    finally:
        conn.close()

# 메인 애플리케이션
def main():
    st.title("🔧 인시던트 데이터 관리 시스템")
    
    # 데이터베이스 초기화
    init_database()
    
    # 탭 구성
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 데이터 조회", 
        "📤 CSV 업로드", 
        "➕ 인시던트 추가", 
        "✏️ 인시던트 수정", 
        "🗑️ 인시던트 삭제"
    ])
    
    with tab1:
        st.header("📋 인시던트 데이터 조회")
        
        col1, col2 = st.columns([2, 1])
        with col1:
            search_term = st.text_input("검색어 (인시던트 ID, 서비스명, 영향도)", "")
        with col2:
            limit = st.number_input("조회 건수", min_value=10, max_value=1000, value=100, step=10)
        
        if st.button("조회"):
            df = get_incidents(limit, search_term)
            if not df.empty:
                st.success(f"{len(df)}건의 데이터를 조회했습니다.")
                st.dataframe(df, use_container_width=True)
                
                # 다운로드 기능
                csv = df.to_csv(index=False)
                st.download_button(
                    label="CSV 다운로드",
                    data=csv,
                    file_name=f"incident_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            else:
                st.info("조회된 데이터가 없습니다.")
    
    with tab2:
        st.header("📤 CSV 파일 업로드")
        st.info("CSV 파일은 반드시 UTF-8 인코딩이어야 합니다.")
        
        uploaded_file = st.file_uploader(
            "CSV 파일을 선택하세요", 
            type=['csv'],
            help="UTF-8 인코딩된 CSV 파일만 업로드 가능합니다."
        )
        
        if uploaded_file is not None:
            # 파일 내용 읽기
            file_content = uploaded_file.getvalue()
            
            # 인코딩 체크
            is_utf8, encoding, confidence = check_encoding(file_content)
            
            st.write(f"**파일 정보:**")
            st.write(f"- 파일명: {uploaded_file.name}")
            st.write(f"- 파일 크기: {len(file_content)} bytes")
            st.write(f"- 감지된 인코딩: {encoding} (신뢰도: {confidence:.2f})")
            
            if not is_utf8:
                st.error("❌ UTF-8 인코딩이 아닙니다. UTF-8로 인코딩된 파일을 업로드해주세요.")
                st.stop()
            
            st.success("✅ UTF-8 인코딩이 확인되었습니다.")
            
            try:
                # CSV 파일 읽기
                df = pd.read_csv(io.StringIO(file_content.decode('utf-8')))
                
                st.write("**파일 미리보기:**")
                st.dataframe(df.head(10))
                st.write(f"총 {len(df)}개의 레코드")
                
                if st.button("업로드 실행"):
                    success, message = upload_csv_data(df)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                        
            except Exception as e:
                st.error(f"CSV 파일 처리 중 오류 발생: {str(e)}")
    
    with tab3:
        st.header("➕ 새 인시던트 추가")
        
        with st.form("add_incident_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                incident_id = st.text_input("인시던트 ID*")
                service_name = st.text_input("서비스명*")
                error_time = st.number_input("오류 시간", min_value=0, value=0)
                effect = st.text_input("영향도")
                symptom = st.text_area("증상")
                repair_notice = st.text_area("수리 알림")
                error_date = st.date_input("오류 날짜")
                week = st.selectbox("요일", ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"])
                daynight = st.selectbox("주야", ["주간", "야간"])
            
            with col2:
                root_cause = st.text_area("근본 원인")
                incident_repair = st.text_area("인시던트 수리")
                incident_plan = st.text_area("인시던트 계획")
                cause_type = st.selectbox("원인 유형", ["하드웨어", "소프트웨어", "네트워크", "인적오류", "기타"])
                done_type = st.selectbox("완료 유형", ["완료", "진행중", "보류", "취소"])
                incident_grade = st.selectbox("인시던트 등급", ["Critical", "High", "Medium", "Low"])
                owner_depart = st.text_input("담당 부서")
                year = st.text_input("연도", value=str(datetime.now().year))
                month = st.text_input("월", value=str(datetime.now().month))
            
            submitted = st.form_submit_button("추가")
            
            if submitted:
                if incident_id and service_name:
                    data = [
                        incident_id, service_name, error_time, effect, symptom,
                        repair_notice, error_date.strftime('%Y-%m-%d'), week, daynight, root_cause,
                        incident_repair, incident_plan, cause_type, done_type,
                        incident_grade, owner_depart, year, month
                    ]
                    
                    success, message = add_incident(data)
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
                else:
                    st.error("인시던트 ID와 서비스명은 필수 항목입니다.")
    
    with tab4:
        st.header("✏️ 인시던트 수정")
        
        # 수정할 인시던트 선택
        df = get_incidents(limit=1000)
        if not df.empty:
            incident_options = [(row['id'], f"{row['incident_id']} - {row['service_name']}") 
                               for _, row in df.iterrows()]
            
            selected = st.selectbox(
                "수정할 인시던트 선택",
                options=incident_options,
                format_func=lambda x: x[1]
            )
            
            if selected:
                selected_id = selected[0]
                incident_data = df[df['id'] == selected_id].iloc[0]
                
                with st.form("update_incident_form"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        incident_id = st.text_input("인시던트 ID*", value=incident_data['incident_id'])
                        service_name = st.text_input("서비스명*", value=incident_data['service_name'])
                        error_time = st.number_input("오류 시간", value=int(incident_data['error_time']) if pd.notna(incident_data['error_time']) else 0)
                        effect = st.text_input("영향도", value=incident_data['effect'] if pd.notna(incident_data['effect']) else "")
                        symptom = st.text_area("증상", value=incident_data['symptom'] if pd.notna(incident_data['symptom']) else "")
                        repair_notice = st.text_area("수리 알림", value=incident_data['repair_notice'] if pd.notna(incident_data['repair_notice']) else "")
                        error_date = st.date_input("오류 날짜", value=pd.to_datetime(incident_data['error_date']).date() if pd.notna(incident_data['error_date']) else datetime.now().date())
                        week = st.selectbox("요일", ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"], 
                                          index=["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"].index(incident_data['week']) if pd.notna(incident_data['week']) and incident_data['week'] in ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"] else 0)
                        daynight = st.selectbox("주야", ["주간", "야간"], 
                                              index=["주간", "야간"].index(incident_data['daynight']) if pd.notna(incident_data['daynight']) and incident_data['daynight'] in ["주간", "야간"] else 0)
                    
                    with col2:
                        root_cause = st.text_area("근본 원인", value=incident_data['root_cause'] if pd.notna(incident_data['root_cause']) else "")
                        incident_repair = st.text_area("인시던트 수리", value=incident_data['incident_repair'] if pd.notna(incident_data['incident_repair']) else "")
                        incident_plan = st.text_area("인시던트 계획", value=incident_data['incident_plan'] if pd.notna(incident_data['incident_plan']) else "")
                        cause_type = st.selectbox("원인 유형", ["하드웨어", "소프트웨어", "네트워크", "인적오류", "기타"], 
                                                index=["하드웨어", "소프트웨어", "네트워크", "인적오류", "기타"].index(incident_data['cause_type']) if pd.notna(incident_data['cause_type']) and incident_data['cause_type'] in ["하드웨어", "소프트웨어", "네트워크", "인적오류", "기타"] else 4)
                        done_type = st.selectbox("완료 유형", ["완료", "진행중", "보류", "취소"], 
                                               index=["완료", "진행중", "보류", "취소"].index(incident_data['done_type']) if pd.notna(incident_data['done_type']) and incident_data['done_type'] in ["완료", "진행중", "보류", "취소"] else 1)
                        incident_grade = st.selectbox("인시던트 등급", ["Critical", "High", "Medium", "Low"], 
                                                    index=["Critical", "High", "Medium", "Low"].index(incident_data['incident_grade']) if pd.notna(incident_data['incident_grade']) and incident_data['incident_grade'] in ["Critical", "High", "Medium", "Low"] else 2)
                        owner_depart = st.text_input("담당 부서", value=incident_data['owner_depart'] if pd.notna(incident_data['owner_depart']) else "")
                        year = st.text_input("연도", value=incident_data['year'] if pd.notna(incident_data['year']) else "")
                        month = st.text_input("월", value=incident_data['month'] if pd.notna(incident_data['month']) else "")
                    
                    submitted = st.form_submit_button("수정")
                    
                    if submitted:
                        if incident_id and service_name:
                            data = [
                                incident_id, service_name, error_time, effect, symptom,
                                repair_notice, error_date.strftime('%Y-%m-%d'), week, daynight, root_cause,
                                incident_repair, incident_plan, cause_type, done_type,
                                incident_grade, owner_depart, year, month
                            ]
                            
                            success, message = update_incident(selected_id, data)
                            if success:
                                st.success(message)
                                st.rerun()
                            else:
                                st.error(message)
                        else:
                            st.error("인시던트 ID와 서비스명은 필수 항목입니다.")
        else:
            st.info("수정할 인시던트가 없습니다.")
    
    with tab5:
        st.header("🗑️ 인시던트 삭제")
        
        df = get_incidents(limit=1000)
        if not df.empty:
            incident_options = [(row['id'], f"{row['incident_id']} - {row['service_name']}") 
                               for _, row in df.iterrows()]
            
            selected = st.selectbox(
                "삭제할 인시던트 선택",
                options=incident_options,
                format_func=lambda x: x[1]
            )
            
            if selected:
                selected_id = selected[0]
                incident_data = df[df['id'] == selected_id].iloc[0]
                
                st.warning("**삭제할 인시던트 정보:**")
                st.write(f"- 인시던트 ID: {incident_data['incident_id']}")
                st.write(f"- 서비스명: {incident_data['service_name']}")
                st.write(f"- 생성일: {incident_data['created_at']}")
                
                if st.button("삭제 확인", type="primary"):
                    success, message = delete_incident(selected_id)
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
        else:
            st.info("삭제할 인시던트가 없습니다.")
    
    # 사이드바 통계 정보 표시
    st.sidebar.subheader("📊 통계 정보")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        total_count = pd.read_sql_query("SELECT COUNT(*) as count FROM incidents", conn)
        recent_count = pd.read_sql_query("SELECT COUNT(*) as count FROM incidents WHERE date(created_at) = date('now')", conn)
        conn.close()
        
        st.sidebar.metric("전체 인시던트", total_count['count'].iloc[0])
        st.sidebar.metric("오늘 등록", recent_count['count'].iloc[0])
    except:
        st.sidebar.metric("전체 인시던트", 0)
        st.sidebar.metric("오늘 등록", 0)

if __name__ == "__main__":
    main()