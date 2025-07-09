import os
from dotenv import load_dotenv
import streamlit as st
import sqlite3
import email
from email import policy
from email.message import EmailMessage
from azure.storage.blob import BlobServiceClient
import datetime
from io import StringIO
import tempfile
import pandas as pd

# 환경 변수 로드
load_dotenv()

# 데이터 캐시 비우기
st.cache_data.clear()
st.cache_resource.clear()

# 환경 변수에서 설정 값 직접 가져오기
STORAGE_CONN_STR = os.getenv("STORAGE_CONN_STR")
STORAGE_ACCOUNT_NAME = os.getenv("STORAGE_ACCOUNT_NAME")
EML_CONTAINER_NAME = os.getenv("EML_CONTAINER_NAME")
EML_DB_NAME = os.getenv("EML_DB_NAME")

# OpenAI 설정
openai_endpoint = os.getenv("OPENAI_ENDPOINT")
openai_api_key = os.getenv("OPENAI_KEY")
openai_model = os.getenv("OPENAI_MODEL")

# 환경 변수 유효성 검사
required_env_vars = {
    "STORAGE_CONN_STR": STORAGE_CONN_STR,
    "STORAGE_ACCOUNT_NAME": STORAGE_ACCOUNT_NAME,
    "EML_CONTAINER_NAME": EML_CONTAINER_NAME
}

missing_vars = [var for var, value in required_env_vars.items() if not value]

def validate_connection_string(connection_string):
    """연결 문자열 유효성 검사"""
    if not connection_string:
        return False, "연결 문자열이 비어있습니다."
    
    # 기본적인 Azure Storage 연결 문자열 형식 확인
    required_parts = ['AccountName=', 'AccountKey=']
    missing_parts = [part for part in required_parts if part not in connection_string]
    
    if missing_parts:
        return False, f"연결 문자열에 필수 요소가 누락되었습니다: {', '.join(missing_parts)}"
    
    return True, "유효한 연결 문자열입니다."

def test_azure_connection():
    """Azure Storage 연결 테스트"""
    if not STORAGE_CONN_STR:
        return False, "연결 문자열이 설정되지 않았습니다."
    
    try:
        # 연결 문자열 유효성 검사
        is_valid, message = validate_connection_string(STORAGE_CONN_STR)
        if not is_valid:
            return False, message
        
        # 실제 연결 테스트
        blob_service_client = BlobServiceClient.from_connection_string(STORAGE_CONN_STR)
        
        # 컨테이너 존재 확인 (없으면 생성)
        try:
            container_client = blob_service_client.get_container_client(EML_CONTAINER_NAME)
            container_client.get_container_properties()
        except Exception as e:
            if "ContainerNotFound" in str(e):
                # 컨테이너가 없으면 생성
                container_client.create_container()
                return True, "연결 성공 및 컨테이너 생성 완료"
            else:
                return False, f"컨테이너 접근 오류: {str(e)}"
        
        return True, "연결 성공"
    except Exception as e:
        return False, f"연결 테스트 실패: {str(e)}"

def init_database():
    """데이터베이스 초기화 및 테이블 생성"""
    try:
        conn = sqlite3.connect(EML_DB_NAME)
        cursor = conn.cursor()
        
        # 테이블 생성 SQL
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS eml_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_filename TEXT NOT NULL,
                blob_name TEXT NOT NULL,
                subject TEXT,
                sender TEXT,
                recipient TEXT,
                date_sent TEXT,
                body_text TEXT,
                body_html TEXT,
                attachments TEXT,
                file_size INTEGER,
                upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        return True, "데이터베이스 초기화 성공"
    except Exception as e:
        return False, f"데이터베이스 초기화 실패: {str(e)}"

def insert_eml_data(parsed_data, original_filename, blob_name, file_size):
    """EML 데이터를 데이터베이스에 삽입"""
    try:
        conn = sqlite3.connect(EML_DB_NAME)
        cursor = conn.cursor()
        
        # 첨부파일 리스트를 문자열로 변환
        attachments_str = ', '.join(parsed_data['attachments']) if parsed_data['attachments'] else ''
        
        # 데이터 삽입
        cursor.execute('''
            INSERT INTO eml_reports (
                original_filename, blob_name, subject, sender, recipient, 
                date_sent, body_text, body_html, attachments, file_size
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            original_filename,
            blob_name,
            parsed_data['subject'],
            parsed_data['from'],
            parsed_data['to'],
            parsed_data['date'],
            parsed_data['body_text'],
            parsed_data['body_html'],
            attachments_str,
            file_size
        ))
        
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return True, record_id, None
    except Exception as e:
        return False, None, f"데이터베이스 삽입 실패: {str(e)}"

def get_eml_record(record_id):
    """특정 ID의 EML 레코드 조회"""
    try:
        conn = sqlite3.connect(EML_DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM eml_reports WHERE id = ?
        ''', (record_id,))
        
        record = cursor.fetchone()
        conn.close()
        
        if record:
            # 컬럼명과 함께 딕셔너리로 반환
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, record))
        else:
            return None
    except Exception as e:
        st.error(f"데이터베이스 조회 실패: {str(e)}")
        return None

def display_db_record(record):
    """데이터베이스 레코드를 화면에 표시"""
    st.subheader("💾 데이터베이스 등록 정보")
    
    # 기본 정보를 두 컬럼으로 표시
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**📋 기본 정보**")
        st.write(f"• **ID**: {record['id']}")
        st.write(f"• **원본 파일명**: {record['original_filename']}")
        st.write(f"• **저장된 파일명**: {record['blob_name']}")
        st.write(f"• **파일 크기**: {record['file_size']:,} bytes")
    
    with col2:
        st.write("**📧 이메일 정보**")
        st.write(f"• **제목**: {record['subject']}")
        st.write(f"• **발신자**: {record['sender']}")
        st.write(f"• **수신자**: {record['recipient']}")
        st.write(f"• **발송일시**: {record['date_sent']}")
    
    # 본문 내용
    if record['body_text']:
        with st.expander("📄 본문 내용 보기"):
            st.text_area("텍스트 본문", record['body_text'], height=200, disabled=True)
    
    # 첨부파일 정보
    if record['attachments']:
        st.write("**📎 첨부파일**")
        attachments = record['attachments'].split(', ')
        for attachment in attachments:
            st.write(f"  • {attachment}")
    
    # 등록 시간
    st.write(f"**🕐 등록 시간**: {record['upload_time']}")

def parse_eml_file(eml_content):
    """EML 파일 내용을 파싱하여 구조화된 데이터로 반환"""
    try:
        # EML 파일 파싱
        msg = email.message_from_string(eml_content, policy=policy.default)
        
        # 기본 헤더 정보 추출
        parsed_data = {
            'from': msg.get('From', ''),
            'to': msg.get('To', ''),
            'cc': msg.get('Cc', ''),
            'subject': msg.get('Subject', ''),
            'date': msg.get('Date', ''),
            'message_id': msg.get('Message-ID', ''),
            'body_text': '',
            'body_html': '',
            'attachments': []
        }
        
        # 본문 내용 추출
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                
                # 첨부파일이 아닌 경우
                if "attachment" not in content_disposition:
                    if content_type == "text/plain":
                        try:
                            parsed_data['body_text'] = part.get_content()
                        except:
                            parsed_data['body_text'] = str(part.get_payload(decode=True), 'utf-8', errors='ignore')
                    elif content_type == "text/html":
                        try:
                            parsed_data['body_html'] = part.get_content()
                        except:
                            parsed_data['body_html'] = str(part.get_payload(decode=True), 'utf-8', errors='ignore')
                else:
                    # 첨부파일 정보
                    filename = part.get_filename()
                    if filename:
                        parsed_data['attachments'].append(filename)
        else:
            # 단일 파트 메시지
            content_type = msg.get_content_type()
            if content_type == "text/plain":
                try:
                    parsed_data['body_text'] = msg.get_content()
                except:
                    parsed_data['body_text'] = str(msg.get_payload(decode=True), 'utf-8', errors='ignore')
            elif content_type == "text/html":
                try:
                    parsed_data['body_html'] = msg.get_content()
                except:
                    parsed_data['body_html'] = str(msg.get_payload(decode=True), 'utf-8', errors='ignore')
        
        return parsed_data, None
    except Exception as e:
        return None, str(e)

def upload_to_azure_eml_blob(file_content, filename):
    """Azure Blob Storage에 파일 업로드"""
    try:
        if not STORAGE_CONN_STR:
            return False, None, "Azure Storage 연결 문자열이 설정되지 않았습니다."
        
        # 연결 문자열 유효성 검사
        is_valid, message = validate_connection_string(STORAGE_CONN_STR)
        if not is_valid:
            return False, None, f"연결 문자열 오류: {message}"
        
        # Blob Service Client 생성
        blob_service_client = BlobServiceClient.from_connection_string(STORAGE_CONN_STR)
        
        # 타임스탬프를 포함한 고유한 파일명 생성
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        blob_name = f"{timestamp}_{filename}"
        
        # 컨테이너 존재 확인 및 생성
        try:
            container_client = blob_service_client.get_container_client(EML_CONTAINER_NAME)
            container_client.get_container_properties()
        except Exception as e:
            if "ContainerNotFound" in str(e):
                container_client.create_container()
        
        # Blob 업로드
        blob_client = blob_service_client.get_blob_client(
            container=EML_CONTAINER_NAME, 
            blob=blob_name
        )
        
        # 파일 내용이 bytes가 아닌 경우 변환
        if isinstance(file_content, str):
            file_content = file_content.encode('utf-8')
        
        blob_client.upload_blob(file_content, overwrite=True)
        
        return True, blob_name, None
    except Exception as e:
        error_message = str(e)
        if "Connection string is either blank or malformed" in error_message:
            error_message = "Azure Storage 연결 문자열이 올바르지 않습니다. 설정을 확인해주세요."
        return False, None, error_message

def display_eml_content(parsed_data):
    """파싱된 EML 데이터를 시각적으로 표시"""
    st.subheader("📧 이메일 내용 미리보기")
    
    # 제목만 표시
    st.write("**제목:**")
    st.text(parsed_data['subject'])
    
    # 본문 내용 표시
    st.write("**본문:**")
    if parsed_data['body_text']:
        st.text_area(
            "텍스트 본문", 
            parsed_data['body_text'], 
            height=300,
            disabled=True
        )
    
    if parsed_data['body_html']:
        with st.expander("HTML 본문 보기"):
            st.code(parsed_data['body_html'], language='html')
    
    # 첨부파일 정보 표시
    if parsed_data['attachments']:
        st.write("**첨부파일:**")
        for attachment in parsed_data['attachments']:
            st.write(f"📎 {attachment}")


# === Streamlit 앱 ===
st.title("💡 장애보고서 초안 생성 (1단계)")
st.caption("복구보고(eml)을 업로드하면 장애보고서 초안을 생성 합니다")
st.caption("- 1단계 : EML 파일 업로드 및 분석")


# 필수 환경변수 누락시 경고 표시 및 중단
if missing_vars:
    st.error(f"⚠️ 다음 환경변수가 설정되지 않았습니다: {', '.join(missing_vars)}")
    st.error("`.env` 파일을 확인하고 필요한 환경변수를 설정해주세요.")
    st.info("파일 업로드 기능을 사용하려면 위 환경변수들을 설정해주세요.")
    st.stop()

# 데이터베이스 초기화
db_success, db_message = init_database()
if not db_success:
    st.error(f"⚠️ 데이터베이스 초기화 오류: {db_message}")
else:
    st.success("✅ 데이터베이스 연결 성공")

# Azure 연결 상태 확인
connection_test_result, connection_message = test_azure_connection()

if not connection_test_result:
    st.error(f"⚠️ Azure Storage 연결 오류: {connection_message}")
else:
    st.success(f"✅ Azure Storage 연결 성공: {connection_message}")

st.divider()

# 파일 업로드 섹션
st.subheader("📁 EML 파일 업로드")

uploaded_file = st.file_uploader(
    "EML 파일을 선택하세요",
    type=['eml'],
    help="복구 보고서가 포함된 EML 파일을 업로드해주세요"
)

if uploaded_file is not None:
    # 파일 내용 읽기
    file_content = uploaded_file.read()
    file_content_str = file_content.decode('utf-8', errors='ignore')
    
    # EML 파일 파싱
    with st.spinner('EML 파일을 분석 중입니다...'):
        parsed_data, parse_error = parse_eml_file(file_content_str)
    
    if parse_error:
        st.error(f"❌ EML 파일 파싱 중 오류가 발생했습니다: {parse_error}")
    else:
        # 파싱된 내용 표시
        display_eml_content(parsed_data)
        
        st.divider()
        
        # 업로드 확인 섹션
        st.subheader("☁️ Azure Storage 업로드")
        
        col1, col2 = st.columns([1, 3])
        
        with col1:
            upload_button = st.button(
                "✅ 확인 및 업로드", 
                type="primary",
                disabled=not (connection_test_result and db_success)
            )
        
        with col2:
            if not connection_test_result:
                st.warning("Azure Storage 연결이 설정되지 않아 업로드할 수 없습니다.")
            elif not db_success:
                st.warning("데이터베이스 연결이 설정되지 않아 업로드할 수 없습니다.")
            else:
                st.info("업로드 준비 완료")
        
        # 업로드 실행
        if upload_button and connection_test_result and db_success:
            with st.spinner('Azure Storage에 업로드 중입니다...'):
                success, blob_name, upload_error = upload_to_azure_eml_blob(
                    file_content, 
                    uploaded_file.name
                )
            
            if success:
                st.success(f"✅ 파일이 성공적으로 업로드되었습니다!")
                st.info(f"📍 **업로드 위치**: {STORAGE_ACCOUNT_NAME}/{EML_CONTAINER_NAME}/{blob_name}")
                
                # 데이터베이스에 정보 저장
                with st.spinner('데이터베이스에 정보를 저장 중입니다...'):
                    db_success_insert, record_id, db_error = insert_eml_data(
                        parsed_data, 
                        uploaded_file.name, 
                        blob_name, 
                        len(file_content)
                    )
                
                if db_success_insert:
                    st.success(f"✅ 데이터베이스에 성공적으로 등록되었습니다! (ID: {record_id})")
                    
                    # 등록된 데이터 조회 및 표시
                    registered_record = get_eml_record(record_id)
                    if registered_record:
                        st.divider()
                        display_db_record(registered_record)
                    
                    # 성공 효과
                    st.balloons()
                    
                else:
                    st.error(f"❌ 데이터베이스 등록 중 오류가 발생했습니다: {db_error}")
                    
                    # 업로드는 성공했으므로 기본 정보는 표시
                    with st.expander("업로드 상세 정보"):
                        st.write(f"**원본 파일명**: {uploaded_file.name}")
                        st.write(f"**저장된 파일명**: {blob_name}")
                        st.write(f"**파일 크기**: {len(file_content):,} bytes")
                        st.write(f"**업로드 시간**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                st.error(f"❌ 업로드 중 오류가 발생했습니다: {upload_error}")

