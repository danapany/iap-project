import sqlite3
import pandas as pd
import logging
from datetime import datetime
from pathlib import Path
import difflib
import os
from dotenv import load_dotenv
import re

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
        """데이터베이스 초기화 및 테이블 생성 - 단어 치환 지원 추가"""
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 기존 테이블에 replacement_mode 컬럼 추가
                tables = [
                    """CREATE TABLE IF NOT EXISTS reprompting_questions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        question_type TEXT NOT NULL,
                        question TEXT NOT NULL UNIQUE,
                        custom_prompt TEXT NOT NULL,
                        wrong_answer_summary TEXT,
                        replacement_mode TEXT DEFAULT 'full',  -- 'full' 또는 'word'
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )""",
                    # 엑셀 업로드 이력 테이블
                    """CREATE TABLE IF NOT EXISTS upload_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_name TEXT NOT NULL,
                        file_size INTEGER,
                        total_rows INTEGER,
                        processed_rows INTEGER,
                        new_count INTEGER,
                        update_count INTEGER,
                        skipped_rows INTEGER,
                        success_rows INTEGER,
                        error_rows INTEGER,
                        upload_status TEXT,
                        upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        error_message TEXT
                    )""",
                    
                    # 개별 입력 이력 테이블
                    """CREATE TABLE IF NOT EXISTS individual_input_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        question_id INTEGER,
                        action_type TEXT,
                        input_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (question_id) REFERENCES reprompting_questions(id)
                    )"""
                ]
                
                for table in tables:
                    cursor.execute(table)
                
                # 기존 테이블에 replacement_mode 컬럼이 없으면 추가
                try:
                    cursor.execute("ALTER TABLE reprompting_questions ADD COLUMN replacement_mode TEXT DEFAULT 'full'")
                    print("INFO: replacement_mode 컬럼 추가됨")
                except sqlite3.OperationalError as e:
                    if "duplicate column" not in str(e).lower():
                        print(f"WARNING: 컬럼 추가 실패: {e}")
                
                # 인덱스 생성
                indexes = [
                    "CREATE INDEX IF NOT EXISTS idx_question_type ON reprompting_questions(question_type)",
                    "CREATE INDEX IF NOT EXISTS idx_question ON reprompting_questions(question)",
                    "CREATE INDEX IF NOT EXISTS idx_replacement_mode ON reprompting_questions(replacement_mode)",
                    "CREATE INDEX IF NOT EXISTS idx_created_at ON reprompting_questions(created_at)",
                    "CREATE INDEX IF NOT EXISTS idx_updated_at ON reprompting_questions(updated_at)"
                ]
                
                for index in indexes:
                    cursor.execute(index)
                
                conn.commit()
                logging.info("데이터베이스 초기화 완료")
                
        except Exception as e:
            logging.error(f"데이터베이스 초기화 실패: {str(e)}")
            raise

    def find_similar_questions_enhanced(self, user_query, similarity_threshold=0.6, limit=5):
        """
        개선된 유사 질문 찾기 - 단어 치환 모드 지원
        
        Args:
            user_query: 사용자 질문
            similarity_threshold: 유사도 임계값
            limit: 반환할 최대 결과 수
        
        Returns:
            list: 유사 질문 목록 (유사도 순으로 정렬)
        """
        try:
            all_questions = self._execute_query("""
                SELECT id, question_type, question, custom_prompt, wrong_answer_summary, replacement_mode
                FROM reprompting_questions
            """, fetch_all=True)
            
            similar_questions = []
            user_query_lower = user_query.lower()
            
            for q_data in all_questions:
                q_id, q_type, question, custom_prompt, summary, mode = q_data
                mode = mode or 'full'  # 기본값
                
                if mode == 'word':
                    # 단어 치환 모드: 부분 문자열 매칭
                    question_lower = question.lower()
                    
                    # 1. 정확한 단어 경계 매칭 (가장 높은 우선순위)
                    word_boundary_pattern = r'\b' + re.escape(question_lower) + r'\b'
                    if re.search(word_boundary_pattern, user_query_lower):
                        similar_questions.append({
                            'id': q_id,
                            'question_type': q_type,
                            'question': question,
                            'custom_prompt': custom_prompt,
                            'wrong_answer_summary': summary,
                            'replacement_mode': mode,
                            'similarity': 1.0,  # 정확한 단어 매칭
                            'match_type': 'word_boundary'
                        })
                        continue
                    
                    # 2. 부분 문자열 매칭 (구두점 포함)
                    if question_lower in user_query_lower:
                        # 위치 기반 유사도 계산 (문장 앞쪽에 있을수록 높은 점수)
                        position = user_query_lower.find(question_lower)
                        position_score = 1.0 - (position / len(user_query_lower))
                        
                        # 길이 기반 유사도 (매칭된 단어가 전체에서 차지하는 비율)
                        length_score = len(question_lower) / len(user_query_lower)
                        
                        # 최종 유사도: 위치(30%) + 길이(70%)
                        similarity = position_score * 0.3 + length_score * 0.7
                        
                        similar_questions.append({
                            'id': q_id,
                            'question_type': q_type,
                            'question': question,
                            'custom_prompt': custom_prompt,
                            'wrong_answer_summary': summary,
                            'replacement_mode': mode,
                            'similarity': similarity,
                            'match_type': 'substring'
                        })
                        continue
                    
                    # 3. 토큰 기반 유사도 (fallback)
                    user_tokens = set(re.findall(r'\w+', user_query_lower))
                    question_tokens = set(re.findall(r'\w+', question_lower))
                    
                    if user_tokens and question_tokens:
                        intersection = len(user_tokens.intersection(question_tokens))
                        union = len(user_tokens.union(question_tokens))
                        token_similarity = intersection / union if union > 0 else 0
                        
                        if token_similarity >= similarity_threshold * 0.5:  # 더 낮은 임계값
                            similar_questions.append({
                                'id': q_id,
                                'question_type': q_type,
                                'question': question,
                                'custom_prompt': custom_prompt,
                                'wrong_answer_summary': summary,
                                'replacement_mode': mode,
                                'similarity': token_similarity,
                                'match_type': 'token'
                            })
                
                else:  # mode == 'full'
                    # 전체 질문 매칭 모드 (기존 로직)
                    similarity = difflib.SequenceMatcher(None, user_query_lower, question.lower()).ratio()
                    
                    if similarity >= similarity_threshold:
                        similar_questions.append({
                            'id': q_id,
                            'question_type': q_type,
                            'question': question,
                            'custom_prompt': custom_prompt,
                            'wrong_answer_summary': summary,
                            'replacement_mode': mode,
                            'similarity': similarity,
                            'match_type': 'full_question'
                        })
            
            # 유사도 순으로 정렬
            return sorted(similar_questions, key=lambda x: (x['similarity'], len(x['question'])), 
                        reverse=True)[:limit]
        
        except Exception as e:
            logging.error(f"유사 질문 검색 실패: {str(e)}")
            return []

    def check_and_transform_query_with_reprompting(self, user_query):
        """개선된 재프롬프팅 - 단어 치환 지원"""
        if not user_query:
            return {
                'transformed': False,
                'original_query': user_query,
                'transformed_query': user_query,
                'match_type': 'none'
            }
        
        try:
            # 1단계: 정확한 매칭 시도
            exact_result = self.reprompting_db_manager.check_reprompting_question(user_query)
            if exact_result['exists']:
                if not self.debug_mode:
                    st.success("✅ 맞춤형 프롬프트를 적용하여 더 정확한 답변을 제공합니다.")
                return {
                    'transformed': True,
                    'original_query': user_query,
                    'transformed_query': exact_result['custom_prompt'],
                    'question_type': exact_result['question_type'],
                    'wrong_answer_summary': exact_result['wrong_answer_summary'],
                    'match_type': 'exact',
                    'replacement_mode': 'full'
                }
            
            # 2단계: 유사 질문 검색 (개선된 메서드 사용)
            similar_questions = self.reprompting_db_manager.find_similar_questions_enhanced(
                user_query, similarity_threshold=0.6, limit=5
            )
            
            if similar_questions:
                best_match = similar_questions[0]
                
                # 치환 모드에 따른 처리
                if best_match['replacement_mode'] == 'word':
                    # 단어 치환 모드: 질문 내의 특정 단어만 치환
                    transformed_query = self._apply_word_replacement(
                        user_query, 
                        best_match['question'], 
                        best_match['custom_prompt']
                    )
                else:
                    # 전체 질문 치환 모드: 기존 로직
                    try:
                        transformed_query = re.sub(
                            re.escape(best_match['question']),
                            best_match['custom_prompt'],
                            user_query,
                            flags=re.IGNORECASE
                        )
                    except:
                        transformed_query = user_query.replace(
                            best_match['question'],
                            best_match['custom_prompt']
                        )
                
                is_transformed = transformed_query != user_query
                
                if is_transformed:
                    if not self.debug_mode:
                        st.info(f"📋 유사 질문 패턴을 감지하여 질문을 최적화했습니다. "
                            f"(유사도: {best_match['similarity']:.2f}, "
                            f"매칭: {best_match['match_type']})")
                    
                    if self.debug_mode:
                        print(f"DEBUG: 재프롬프팅 적용")
                        print(f"  - 원본: {user_query}")
                        print(f"  - 변환: {transformed_query}")
                        print(f"  - 모드: {best_match['replacement_mode']}")
                        print(f"  - 매칭: {best_match['match_type']}")
                        print(f"  - 유사도: {best_match['similarity']:.2f}")
                
                return {
                    'transformed': is_transformed,
                    'original_query': user_query,
                    'transformed_query': transformed_query,
                    'question_type': best_match['question_type'],
                    'wrong_answer_summary': best_match['wrong_answer_summary'],
                    'similarity': best_match['similarity'],
                    'similar_question': best_match['question'],
                    'match_type': best_match['match_type'],
                    'replacement_mode': best_match['replacement_mode']
                }
            
            return {
                'transformed': False,
                'original_query': user_query,
                'transformed_query': user_query,
                'match_type': 'none'
            }
            
        except Exception as e:
            print(f"ERROR: 재프롬프팅 처리 실패: {e}")
            import traceback
            traceback.print_exc()
            return {
                'transformed': False,
                'original_query': user_query,
                'transformed_query': user_query,
                'match_type': 'error',
                'error': str(e)
            }

    def _apply_word_replacement(self, user_query, search_word, replacement_word):
        """
        사용자 질문에서 특정 단어를 찾아 치환
        
        Args:
            user_query: 원본 사용자 질문
            search_word: 찾을 단어
            replacement_word: 치환할 단어
        
        Returns:
            str: 치환된 질문
        """
        try:
            # 1. 정확한 단어 경계 매칭 시도 (가장 정확)
            word_boundary_pattern = r'\b' + re.escape(search_word) + r'\b'
            if re.search(word_boundary_pattern, user_query, re.IGNORECASE):
                return re.sub(word_boundary_pattern, replacement_word, user_query, flags=re.IGNORECASE)
            
            # 2. 부분 문자열 매칭 (구두점/특수문자 포함)
            # "aaaa~" 같은 경우를 처리하기 위해
            search_lower = search_word.lower()
            query_lower = user_query.lower()
            
            if search_lower in query_lower:
                # 대소문자 보존하면서 치환
                start_idx = query_lower.find(search_lower)
                end_idx = start_idx + len(search_lower)
                
                return (user_query[:start_idx] + 
                    replacement_word + 
                    user_query[end_idx:])
            
            # 3. 매칭 실패 - 원본 반환
            return user_query
            
        except Exception as e:
            print(f"ERROR: 단어 치환 실패: {e}")
            return user_query


    def add_single_reprompting_question(self, question_type, question, custom_prompt, 
                                    wrong_answer_summary="", replacement_mode="full"):
        """
        단일 재프롬프팅 질문 추가 또는 업데이트 - replacement_mode 지원
        
        Args:
            question_type: 질문 유형
            question: 원본 질문 (word 모드일 경우 치환할 단어)
            custom_prompt: 맞춤형 프롬프트 (word 모드일 경우 치환될 단어)
            wrong_answer_summary: 오답 요약
            replacement_mode: 'full' (전체 질문 치환) 또는 'word' (단어 치환)
        """
        try:
            existing_id = self._execute_query(
                "SELECT id FROM reprompting_questions WHERE question = ?",
                (question,), fetch_one=True
            )
            
            if existing_id:
                self._execute_query("""
                    UPDATE reprompting_questions 
                    SET question_type = ?, custom_prompt = ?, wrong_answer_summary = ?, 
                        replacement_mode = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE question = ?
                """, (question_type, custom_prompt, wrong_answer_summary, replacement_mode, question))
                
                self._execute_query(
                    "INSERT INTO individual_input_history (question_id, action_type) VALUES (?, 'update')",
                    (existing_id[0],)
                )
                
                return {
                    'success': True,
                    'action': 'updated',
                    'message': f'기존 질문이 업데이트되었습니다. (모드: {replacement_mode})'
                }
            else:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO reprompting_questions 
                        (question_type, question, custom_prompt, wrong_answer_summary, replacement_mode)
                        VALUES (?, ?, ?, ?, ?)
                    """, (question_type, question, custom_prompt, wrong_answer_summary, replacement_mode))
                    
                    question_id = cursor.lastrowid
                    cursor.execute(
                        "INSERT INTO individual_input_history (question_id, action_type) VALUES (?, 'insert')",
                        (question_id,)
                    )
                    conn.commit()
                
                return {
                    'success': True,
                    'action': 'inserted',
                    'message': f'새 질문이 추가되었습니다. (모드: {replacement_mode})'
                }
                
        except sqlite3.IntegrityError:
            return {
                'success': False,
                'error': '데이터 무결성 오류가 발생했습니다. 중복된 질문일 수 있습니다.'
            }
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
                SELECT rq.question_type, rq.question, iih.action_type, iih.input_date
                FROM individual_input_history iih
                JOIN reprompting_questions rq ON iih.question_id = rq.id
                ORDER BY iih.input_date DESC LIMIT 10
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
                SELECT file_name, total_rows, success_rows, error_rows, upload_date
                FROM upload_history ORDER BY upload_date DESC LIMIT 10
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