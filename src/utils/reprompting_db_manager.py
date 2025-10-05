import sqlite3
import pandas as pd
import logging
from datetime import datetime
from pathlib import Path
import difflib
import os
from dotenv import load_dotenv

load_dotenv()

def get_reprompting_db_path():
    """환경변수에서 재프롬프팅 DB 경로 가져오기"""
    base_path = os.getenv('DB_BASE_PATH', 'data/db')
    return os.path.join(base_path, 'reprompting_questions.db')

class RepromptingDBManager:
    """질문 재프롬프팅 데이터베이스 관리 클래스"""
    
    def __init__(self, db_path=None):
        self.db_path = db_path or get_reprompting_db_path()
        self.init_database()
    
    def _execute_query(self, query, params=None, fetch_one=False, fetch_all=False):
        """공통 쿼리 실행 헬퍼"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(query, params or ())
                
                if fetch_one:
                    return cursor.fetchone()
                elif fetch_all:
                    return cursor.fetchall()
                else:
                    conn.commit()
                    return cursor.rowcount
        except Exception as e:
            logging.error(f"쿼리 실행 실패: {str(e)}")
            raise
    
    def init_database(self):
        """데이터베이스 초기화 및 테이블 생성"""
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 테이블 생성
                tables = [
                    """CREATE TABLE IF NOT EXISTS reprompting_questions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        question_type TEXT NOT NULL,
                        question TEXT NOT NULL UNIQUE,
                        custom_prompt TEXT NOT NULL,
                        wrong_answer_summary TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )""",
                    """CREATE TABLE IF NOT EXISTS upload_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_name TEXT NOT NULL,
                        total_rows INTEGER,
                        success_rows INTEGER,
                        error_rows INTEGER,
                        upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        upload_status TEXT
                    )""",
                    """CREATE TABLE IF NOT EXISTS individual_input_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        question_id INTEGER,
                        action_type TEXT NOT NULL,
                        input_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (question_id) REFERENCES reprompting_questions (id)
                    )"""
                ]
                
                # 인덱스 생성
                indexes = [
                    "CREATE INDEX IF NOT EXISTS idx_question_type ON reprompting_questions(question_type)",
                    "CREATE INDEX IF NOT EXISTS idx_question ON reprompting_questions(question)",
                    "CREATE INDEX IF NOT EXISTS idx_created_at ON reprompting_questions(created_at)",
                    "CREATE INDEX IF NOT EXISTS idx_updated_at ON reprompting_questions(updated_at)"
                ]
                
                for table in tables:
                    cursor.execute(table)
                for index in indexes:
                    cursor.execute(index)
                
                conn.commit()
                logging.info("데이터베이스 초기화 완료")
                
        except Exception as e:
            logging.error(f"데이터베이스 초기화 실패: {str(e)}")
            raise
    
    def add_single_reprompting_question(self, question_type, question, custom_prompt, wrong_answer_summary=""):
        """단일 재프롬프팅 질문 추가 또는 업데이트"""
        try:
            existing_id = self._execute_query(
                "SELECT id FROM reprompting_questions WHERE question = ?", 
                (question,), fetch_one=True
            )
            
            if existing_id:
                self._execute_query("""
                    UPDATE reprompting_questions 
                    SET question_type = ?, custom_prompt = ?, wrong_answer_summary = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE question = ?
                """, (question_type, custom_prompt, wrong_answer_summary, question))
                
                self._execute_query(
                    "INSERT INTO individual_input_history (question_id, action_type) VALUES (?, 'update')", 
                    (existing_id[0],)
                )
                
                return {'success': True, 'action': 'updated', 'message': '기존 질문이 업데이트되었습니다.'}
            else:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO reprompting_questions 
                        (question_type, question, custom_prompt, wrong_answer_summary)
                        VALUES (?, ?, ?, ?)
                    """, (question_type, question, custom_prompt, wrong_answer_summary))
                    
                    question_id = cursor.lastrowid
                    cursor.execute(
                        "INSERT INTO individual_input_history (question_id, action_type) VALUES (?, 'insert')", 
                        (question_id,)
                    )
                    conn.commit()
                
                return {'success': True, 'action': 'inserted', 'message': '새 질문이 추가되었습니다.'}
                
        except sqlite3.IntegrityError:
            return {'success': False, 'error': '데이터 무결성 오류가 발생했습니다. 중복된 질문일 수 있습니다.'}
        except Exception as e:
            logging.error(f"질문 추가/업데이트 실패: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_individual_input_statistics(self):
        """개별 입력 통계 조회"""
        try:
            total = self._execute_query("SELECT COUNT(*) FROM individual_input_history", fetch_one=True)[0]
            actions = self._execute_query(
                "SELECT action_type, COUNT(*) FROM individual_input_history GROUP BY action_type", 
                fetch_all=True
            )
            recent = self._execute_query("""
                SELECT rq.question_type, rq.question, iih.action_type, iih.input_time
                FROM individual_input_history iih
                JOIN reprompting_questions rq ON iih.question_id = rq.id
                ORDER BY iih.input_time DESC LIMIT 10
            """, fetch_all=True)
            
            return {
                'total_individual_inputs': total,
                'action_statistics': actions,
                'recent_individual_inputs': recent
            }
        except Exception as e:
            logging.error(f"개별 입력 통계 조회 실패: {str(e)}")
            return None
    
    def upload_excel_to_db(self, excel_file_path, file_name):
        """엑셀 파일을 데이터베이스에 업로드"""
        try:
            df = pd.read_excel(excel_file_path)
            df.columns = df.columns.str.strip()
            
            required_columns = ['질문유형', '질문', '맞춤형 프롬프트', '오답요약']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                return {'success': False, 'error': f"필수 컬럼이 누락되었습니다: {', '.join(missing_columns)}"}
            
            df_clean = df.dropna(subset=required_columns)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                success_rows = error_rows = 0
                error_details = []
                
                for index, row in df_clean.iterrows():
                    try:
                        cursor.execute("""
                            INSERT INTO reprompting_questions 
                            (question_type, question, custom_prompt, wrong_answer_summary, updated_at)
                            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                            ON CONFLICT(question) DO UPDATE SET
                                question_type = excluded.question_type,
                                custom_prompt = excluded.custom_prompt,
                                wrong_answer_summary = excluded.wrong_answer_summary,
                                updated_at = CURRENT_TIMESTAMP
                        """, (
                            str(row['질문유형']).strip(),
                            str(row['질문']).strip(),
                            str(row['맞춤형 프롬프트']).strip(),
                            str(row['오답요약']).strip() if pd.notna(row['오답요약']) else ""
                        ))
                        success_rows += 1
                    except Exception as e:
                        error_rows += 1
                        error_details.append(f"행 {index + 2}: {str(e)}")
                
                cursor.execute("""
                    INSERT INTO upload_history 
                    (file_name, total_rows, success_rows, error_rows, upload_status)
                    VALUES (?, ?, ?, ?, ?)
                """, (file_name, len(df_clean), success_rows, error_rows, 
                     'success' if error_rows == 0 else 'partial_success'))
                
                conn.commit()
                
                return {
                    'success': True,
                    'total_rows': len(df_clean),
                    'success_rows': success_rows,
                    'error_rows': error_rows,
                    'error_details': error_details
                }
                
        except Exception as e:
            logging.error(f"엑셀 업로드 실패: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_reprompting_statistics(self):
        """재프롬프팅 데이터 통계 조회"""
        try:
            total_count = self._execute_query("SELECT COUNT(*) FROM reprompting_questions", fetch_one=True)[0]
            type_statistics = self._execute_query("""
                SELECT question_type, COUNT(*) FROM reprompting_questions 
                GROUP BY question_type ORDER BY COUNT(*) DESC
            """, fetch_all=True)
            recent_uploads = self._execute_query("""
                SELECT file_name, total_rows, success_rows, error_rows, upload_time
                FROM upload_history ORDER BY upload_time DESC LIMIT 10
            """, fetch_all=True)
            
            return {
                'total_count': total_count,
                'type_statistics': type_statistics,
                'recent_uploads': recent_uploads,
                'individual_input_stats': self.get_individual_input_statistics()
            }
        except Exception as e:
            logging.error(f"통계 조회 실패: {str(e)}")
            return None
    
    def check_reprompting_question(self, question):
        """특정 질문이 재프롬프팅 DB에 있는지 확인"""
        try:
            result = self._execute_query("""
                SELECT question_type, question, custom_prompt, wrong_answer_summary
                FROM reprompting_questions WHERE question = ?
            """, (question.strip(),), fetch_one=True)
            
            if result:
                return {
                    'exists': True,
                    'question_type': result[0],
                    'original_question': result[1],
                    'custom_prompt': result[2],
                    'wrong_answer_summary': result[3]
                }
            return {'exists': False}
        except Exception as e:
            logging.error(f"질문 확인 실패: {str(e)}")
            return {'exists': False, 'error': str(e)}
    
    def find_similar_questions(self, question, similarity_threshold=0.6, limit=5):
        """유사한 질문 찾기"""
        try:
            all_questions = self._execute_query("""
                SELECT id, question_type, question, custom_prompt, wrong_answer_summary
                FROM reprompting_questions
            """, fetch_all=True)
            
            similar_questions = []
            for q_data in all_questions:
                similarity = difflib.SequenceMatcher(None, question.lower(), q_data[2].lower()).ratio()
                if similarity >= similarity_threshold:
                    similar_questions.append({
                        'id': q_data[0],
                        'question_type': q_data[1],
                        'question': q_data[2],
                        'custom_prompt': q_data[3],
                        'wrong_answer_summary': q_data[4],
                        'similarity': similarity
                    })
            
            return sorted(similar_questions, key=lambda x: x['similarity'], reverse=True)[:limit]
        except Exception as e:
            logging.error(f"유사 질문 검색 실패: {str(e)}")
            return []
    
    def get_all_reprompting_questions(self, limit=100, offset=0):
        """모든 재프롬프팅 질문 조회"""
        try:
            results = self._execute_query("""
                SELECT id, question_type, question, custom_prompt, wrong_answer_summary, 
                       created_at, updated_at
                FROM reprompting_questions ORDER BY updated_at DESC LIMIT ? OFFSET ?
            """, (limit, offset), fetch_all=True)
            
            columns = ['id', 'question_type', 'question', 'custom_prompt', 
                      'wrong_answer_summary', 'created_at', 'updated_at']
            
            return [dict(zip(columns, row)) for row in results]
        except Exception as e:
            logging.error(f"질문 목록 조회 실패: {str(e)}")
            return []
    
    def delete_reprompting_question(self, question_id):
        """재프롬프팅 질문 삭제"""
        try:
            self._execute_query("DELETE FROM individual_input_history WHERE question_id = ?", (question_id,))
            deleted = self._execute_query("DELETE FROM reprompting_questions WHERE id = ?", (question_id,))
            
            if deleted > 0:
                logging.info(f"질문 ID {question_id} 삭제 완료")
                return True
            else:
                logging.warning(f"질문 ID {question_id}를 찾을 수 없습니다")
                return False
        except Exception as e:
            logging.error(f"질문 삭제 실패: {str(e)}")
            return False
    
    def get_question_by_type(self, question_type):
        """질문 유형별 질문 조회"""
        try:
            results = self._execute_query("""
                SELECT id, question, custom_prompt, wrong_answer_summary, created_at
                FROM reprompting_questions WHERE question_type = ? ORDER BY created_at DESC
            """, (question_type,), fetch_all=True)
            
            columns = ['id', 'question', 'custom_prompt', 'wrong_answer_summary', 'created_at']
            return [dict(zip(columns, row)) for row in results]
        except Exception as e:
            logging.error(f"질문 유형별 조회 실패: {str(e)}")
            return []
    
    def get_custom_prompt_for_question(self, question):
        """특정 질문에 대한 맞춤형 프롬프트 조회"""
        try:
            result = self._execute_query("""
                SELECT custom_prompt, wrong_answer_summary
                FROM reprompting_questions WHERE question = ?
            """, (question.strip(),), fetch_one=True)
            
            if result:
                return {'found': True, 'custom_prompt': result[0], 'wrong_answer_summary': result[1]}
            return {'found': False}
        except Exception as e:
            logging.error(f"맞춤형 프롬프트 조회 실패: {str(e)}")
            return {'found': False, 'error': str(e)}
    
    def update_reprompting_question(self, question_id, question_type=None, question=None, 
                                   custom_prompt=None, wrong_answer_summary=None):
        """재프롬프팅 질문 업데이트"""
        try:
            update_fields, update_values = [], []
            
            for field, value in [('question_type', question_type), ('question', question),
                               ('custom_prompt', custom_prompt), ('wrong_answer_summary', wrong_answer_summary)]:
                if value is not None:
                    update_fields.append(f"{field} = ?")
                    update_values.append(value)
            
            if not update_fields:
                return False
            
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            update_values.append(question_id)
            
            updated = self._execute_query(
                f"UPDATE reprompting_questions SET {', '.join(update_fields)} WHERE id = ?",
                update_values
            )
            
            if updated > 0:
                self._execute_query(
                    "INSERT INTO individual_input_history (question_id, action_type) VALUES (?, 'update')",
                    (question_id,)
                )
                logging.info(f"질문 ID {question_id} 업데이트 완료")
                return True
            else:
                logging.warning(f"질문 ID {question_id}를 찾을 수 없습니다")
                return False
        except Exception as e:
            logging.error(f"질문 업데이트 실패: {str(e)}")
            return False
    
    def export_to_excel(self, output_path=None):
        """데이터베이스 데이터를 엑셀로 내보내기"""
        try:
            if output_path is None:
                output_path = f"reprompting_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query("""
                    SELECT question_type as '질문유형', 
                           question as '질문',
                           custom_prompt as '맞춤형 프롬프트',
                           wrong_answer_summary as '오답요약',
                           created_at as '생성일시',
                           updated_at as '수정일시'
                    FROM reprompting_questions ORDER BY updated_at DESC
                """, conn)
                
                df.to_excel(output_path, index=False, engine='openpyxl')
                logging.info(f"데이터 내보내기 완료: {output_path}")
                return True, output_path
        except Exception as e:
            logging.error(f"데이터 내보내기 실패: {str(e)}")
            return False, str(e)
    
    def get_question_types(self):
        """등록된 모든 질문 유형 조회"""
        try:
            results = self._execute_query(
                "SELECT DISTINCT question_type FROM reprompting_questions ORDER BY question_type",
                fetch_all=True
            )
            return [row[0] for row in results]
        except Exception as e:
            logging.error(f"질문 유형 조회 실패: {str(e)}")
            return []
    
    def bulk_delete_questions(self, question_ids):
        """여러 질문을 한번에 삭제"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                deleted_count = 0
                
                for question_id in question_ids:
                    cursor.execute("DELETE FROM individual_input_history WHERE question_id = ?", (question_id,))
                    cursor.execute("DELETE FROM reprompting_questions WHERE id = ?", (question_id,))
                    if cursor.rowcount > 0:
                        deleted_count += 1
                
                conn.commit()
                logging.info(f"{deleted_count}개의 질문이 삭제되었습니다")
                return True, deleted_count
        except Exception as e:
            logging.error(f"대량 삭제 실패: {str(e)}")
            return False, 0