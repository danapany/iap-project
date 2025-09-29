import sqlite3
import pandas as pd
import logging
from datetime import datetime
from pathlib import Path
import difflib

class RepromptingDBManager:
    """질문 재프롬프팅 데이터베이스 관리 클래스"""
    
    def __init__(self, db_path="data/db/reprompting_questions.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """데이터베이스 초기화 및 테이블 생성"""
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS reprompting_questions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        question_type TEXT NOT NULL,
                        question TEXT NOT NULL UNIQUE,
                        custom_prompt TEXT NOT NULL,
                        wrong_answer_summary TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS upload_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_name TEXT NOT NULL,
                        total_rows INTEGER,
                        success_rows INTEGER,
                        error_rows INTEGER,
                        upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        upload_status TEXT
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS individual_input_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        question_id INTEGER,
                        action_type TEXT NOT NULL,
                        input_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (question_id) REFERENCES reprompting_questions (id)
                    )
                """)
                
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_question_type ON reprompting_questions(question_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_question ON reprompting_questions(question)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON reprompting_questions(created_at)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_updated_at ON reprompting_questions(updated_at)")
                
                conn.commit()
                logging.info("데이터베이스 초기화 완료")
                
        except Exception as e:
            logging.error(f"데이터베이스 초기화 실패: {str(e)}")
            raise
    
    def add_single_reprompting_question(self, question_type, question, custom_prompt, wrong_answer_summary=""):
        """단일 재프롬프팅 질문 추가 또는 업데이트"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("SELECT id FROM reprompting_questions WHERE question = ?", (question,))
                existing_question = cursor.fetchone()
                
                if existing_question:
                    cursor.execute("""
                        UPDATE reprompting_questions 
                        SET question_type = ?, custom_prompt = ?, wrong_answer_summary = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE question = ?
                    """, (question_type, custom_prompt, wrong_answer_summary, question))
                    
                    cursor.execute("""
                        INSERT INTO individual_input_history (question_id, action_type)
                        VALUES (?, 'update')
                    """, (existing_question[0],))
                    
                    action = 'updated'
                    message = '기존 질문이 업데이트되었습니다.'
                else:
                    cursor.execute("""
                        INSERT INTO reprompting_questions 
                        (question_type, question, custom_prompt, wrong_answer_summary)
                        VALUES (?, ?, ?, ?)
                    """, (question_type, question, custom_prompt, wrong_answer_summary))
                    
                    question_id = cursor.lastrowid
                    
                    cursor.execute("""
                        INSERT INTO individual_input_history (question_id, action_type)
                        VALUES (?, 'insert')
                    """, (question_id,))
                    
                    action = 'inserted'
                    message = '새 질문이 추가되었습니다.'
                
                conn.commit()
                logging.info(f"질문 {action}: {question[:50]}...")
                
                return {
                    'success': True,
                    'action': action,
                    'message': message
                }
                
        except sqlite3.IntegrityError as e:
            logging.error(f"데이터 무결성 오류: {str(e)}")
            return {
                'success': False,
                'error': '데이터 무결성 오류가 발생했습니다. 중복된 질문일 수 있습니다.'
            }
        except Exception as e:
            logging.error(f"질문 추가/업데이트 실패: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_individual_input_statistics(self):
        """개별 입력 통계 조회"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("SELECT COUNT(*) FROM individual_input_history")
                total_individual_inputs = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT action_type, COUNT(*) 
                    FROM individual_input_history 
                    GROUP BY action_type
                """)
                action_statistics = cursor.fetchall()
                
                cursor.execute("""
                    SELECT rq.question_type, rq.question, iih.action_type, iih.input_time
                    FROM individual_input_history iih
                    JOIN reprompting_questions rq ON iih.question_id = rq.id
                    ORDER BY iih.input_time DESC
                    LIMIT 10
                """)
                recent_individual_inputs = cursor.fetchall()
                
                return {
                    'total_individual_inputs': total_individual_inputs,
                    'action_statistics': action_statistics,
                    'recent_individual_inputs': recent_individual_inputs
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
                return {
                    'success': False,
                    'error': f"필수 컬럼이 누락되었습니다: {', '.join(missing_columns)}"
                }
            
            df_clean = df.dropna(subset=required_columns)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                total_rows = len(df_clean)
                success_rows = 0
                error_rows = 0
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
                        error_msg = f"행 {index + 2}: {str(e)}"
                        error_details.append(error_msg)
                        logging.error(error_msg)
                
                cursor.execute("""
                    INSERT INTO upload_history 
                    (file_name, total_rows, success_rows, error_rows, upload_status)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    file_name,
                    total_rows,
                    success_rows,
                    error_rows,
                    'success' if error_rows == 0 else 'partial_success'
                ))
                
                conn.commit()
                
                return {
                    'success': True,
                    'total_rows': total_rows,
                    'success_rows': success_rows,
                    'error_rows': error_rows,
                    'error_details': error_details
                }
                
        except Exception as e:
            logging.error(f"엑셀 업로드 실패: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_reprompting_statistics(self):
        """재프롬프팅 데이터 통계 조회"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("SELECT COUNT(*) FROM reprompting_questions")
                total_count = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT question_type, COUNT(*) 
                    FROM reprompting_questions 
                    GROUP BY question_type 
                    ORDER BY COUNT(*) DESC
                """)
                type_statistics = cursor.fetchall()
                
                cursor.execute("""
                    SELECT file_name, total_rows, success_rows, error_rows, upload_time
                    FROM upload_history 
                    ORDER BY upload_time DESC 
                    LIMIT 10
                """)
                recent_uploads = cursor.fetchall()
                
                individual_stats = self.get_individual_input_statistics()
                
                return {
                    'total_count': total_count,
                    'type_statistics': type_statistics,
                    'recent_uploads': recent_uploads,
                    'individual_input_stats': individual_stats
                }
                
        except Exception as e:
            logging.error(f"통계 조회 실패: {str(e)}")
            return None
    
    def check_reprompting_question(self, question):
        """특정 질문이 재프롬프팅 DB에 있는지 확인"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT question_type, question, custom_prompt, wrong_answer_summary
                    FROM reprompting_questions 
                    WHERE question = ?
                """, (question.strip(),))
                
                result = cursor.fetchone()
                
                if result:
                    return {
                        'exists': True,
                        'question_type': result[0],
                        'original_question': result[1],
                        'custom_prompt': result[2],
                        'wrong_answer_summary': result[3]
                    }
                else:
                    return {'exists': False}
                    
        except Exception as e:
            logging.error(f"질문 확인 실패: {str(e)}")
            return {'exists': False, 'error': str(e)}
    
    def find_similar_questions(self, question, similarity_threshold=0.6, limit=5):
        """유사한 질문 찾기"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, question_type, question, custom_prompt, wrong_answer_summary
                    FROM reprompting_questions
                """)
                
                all_questions = cursor.fetchall()
                similar_questions = []
                
                for q_data in all_questions:
                    q_id, q_type, q_text, q_prompt, q_summary = q_data
                    similarity = difflib.SequenceMatcher(None, question.lower(), q_text.lower()).ratio()
                    
                    if similarity >= similarity_threshold:
                        similar_questions.append({
                            'id': q_id,
                            'question_type': q_type,
                            'question': q_text,
                            'custom_prompt': q_prompt,
                            'wrong_answer_summary': q_summary,
                            'similarity': similarity
                        })
                
                similar_questions.sort(key=lambda x: x['similarity'], reverse=True)
                return similar_questions[:limit]
                
        except Exception as e:
            logging.error(f"유사 질문 검색 실패: {str(e)}")
            return []
    
    def get_all_reprompting_questions(self, limit=100, offset=0):
        """모든 재프롬프팅 질문 조회"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, question_type, question, custom_prompt, wrong_answer_summary, 
                           created_at, updated_at
                    FROM reprompting_questions 
                    ORDER BY updated_at DESC
                    LIMIT ? OFFSET ?
                """, (limit, offset))
                
                columns = ['id', 'question_type', 'question', 'custom_prompt', 
                          'wrong_answer_summary', 'created_at', 'updated_at']
                questions = []
                
                for row in cursor.fetchall():
                    question_dict = dict(zip(columns, row))
                    questions.append(question_dict)
                
                return questions
                
        except Exception as e:
            logging.error(f"질문 목록 조회 실패: {str(e)}")
            return []
    
    def delete_reprompting_question(self, question_id):
        """재프롬프팅 질문 삭제"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("DELETE FROM individual_input_history WHERE question_id = ?", (question_id,))
                cursor.execute("DELETE FROM reprompting_questions WHERE id = ?", (question_id,))
                
                if cursor.rowcount > 0:
                    conn.commit()
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, question, custom_prompt, wrong_answer_summary, created_at
                    FROM reprompting_questions 
                    WHERE question_type = ?
                    ORDER BY created_at DESC
                """, (question_type,))
                
                columns = ['id', 'question', 'custom_prompt', 'wrong_answer_summary', 'created_at']
                questions = []
                
                for row in cursor.fetchall():
                    question_dict = dict(zip(columns, row))
                    questions.append(question_dict)
                
                return questions
                
        except Exception as e:
            logging.error(f"질문 유형별 조회 실패: {str(e)}")
            return []
    
    def get_custom_prompt_for_question(self, question):
        """특정 질문에 대한 맞춤형 프롬프트 조회"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT custom_prompt, wrong_answer_summary
                    FROM reprompting_questions 
                    WHERE question = ?
                """, (question.strip(),))
                
                result = cursor.fetchone()
                
                if result:
                    return {
                        'found': True,
                        'custom_prompt': result[0],
                        'wrong_answer_summary': result[1]
                    }
                else:
                    return {'found': False}
                    
        except Exception as e:
            logging.error(f"맞춤형 프롬프트 조회 실패: {str(e)}")
            return {'found': False, 'error': str(e)}
    
    def update_reprompting_question(self, question_id, question_type=None, question=None, 
                                   custom_prompt=None, wrong_answer_summary=None):
        """재프롬프팅 질문 업데이트"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                update_fields = []
                update_values = []
                
                if question_type is not None:
                    update_fields.append("question_type = ?")
                    update_values.append(question_type)
                
                if question is not None:
                    update_fields.append("question = ?")
                    update_values.append(question)
                
                if custom_prompt is not None:
                    update_fields.append("custom_prompt = ?")
                    update_values.append(custom_prompt)
                
                if wrong_answer_summary is not None:
                    update_fields.append("wrong_answer_summary = ?")
                    update_values.append(wrong_answer_summary)
                
                if not update_fields:
                    return False
                
                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                update_values.append(question_id)
                
                query = f"""
                    UPDATE reprompting_questions 
                    SET {', '.join(update_fields)}
                    WHERE id = ?
                """
                
                cursor.execute(query, update_values)
                
                if cursor.rowcount > 0:
                    cursor.execute("""
                        INSERT INTO individual_input_history (question_id, action_type)
                        VALUES (?, 'update')
                    """, (question_id,))
                    
                    conn.commit()
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
                    FROM reprompting_questions 
                    ORDER BY updated_at DESC
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT DISTINCT question_type 
                    FROM reprompting_questions 
                    ORDER BY question_type
                """)
                
                question_types = [row[0] for row in cursor.fetchall()]
                return question_types
                
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