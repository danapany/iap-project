# utils/db_utils.py - 공통 DB 경로 관리 유틸리티
import os
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

def get_base_db_path():
    """기본 DB 디렉토리 경로 가져오기"""
    return os.getenv('DB_BASE_PATH', 'data/db')

def get_qa_pairs_db_path():
    """QA Pairs DB 경로 가져오기"""
    base_path = get_base_db_path()
    return os.path.join(base_path, 'qa_pairs.db')

def get_eml_reports_db_path():
    """EML Reports DB 경로 가져오기"""
    base_path = get_base_db_path()
    return os.path.join(base_path, 'eml_reports.db')

def get_incident_db_path():
    """인시던트 DB 경로 가져오기"""
    base_path = get_base_db_path()
    return os.path.join(base_path, 'incident_data.db')

def get_reprompting_db_path():
    """재프롬프팅 DB 경로 가져오기"""
    base_path = get_base_db_path()
    return os.path.join(base_path, 'reprompting_questions.db')

def get_monitoring_db_path():
    """모니터링 DB 경로 가져오기"""
    base_path = get_base_db_path()
    return os.path.join(base_path, 'monitoring.db')

def ensure_db_directory():
    """DB 디렉토리 생성 (존재하지 않는 경우)"""
    base_path = get_base_db_path()
    os.makedirs(base_path, exist_ok=True)
    return base_path

# 모든 DB 경로를 한번에 가져오는 딕셔너리
def get_all_db_paths():
    """모든 DB 경로를 딕셔너리로 반환"""
    return {
        'qa_pairs': get_qa_pairs_db_path(),
        'eml_reports': get_eml_reports_db_path(),
        'incident_data': get_incident_db_path(),
        'reprompting_questions': get_reprompting_db_path(),
        'monitoring': get_monitoring_db_path()
    }