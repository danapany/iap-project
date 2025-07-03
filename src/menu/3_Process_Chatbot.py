import os
import sqlite3
import streamlit as st
from dotenv import load_dotenv
from openai import AzureOpenAI
from difflib import SequenceMatcher

# 환경 변수 로드
load_dotenv()
openai_endpoint = os.getenv("OPENAI_ENDPOINT")
openai_api_key = os.getenv("OPENAI_API_KEY")
chat_model = os.getenv("CHAT_MODEL")

# Azure OpenAI 클라이언트 초기화
chat_client = AzureOpenAI(
    api_version="2024-12-01-preview",
    azure_endpoint=openai_endpoint,
    api_key=openai_api_key,
)

# Streamlit UI 제목
st.title("\U0001f4ac 장애대응가이드 챗봇")

DB_PATH = "data/db/qa_pairs.db"


def init_main_db():
    """메인 DB 초기화"""
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS qa_pairs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT,
                answer TEXT
            )
        """
        )
        conn.commit()
        return conn, cursor
    except Exception as e:
        st.error(f"메인 DB 초기화 중 오류 발생: {str(e)}")
        return None, None


conn, cursor = init_main_db()


def similar(a, b):
    """문장 유사도 계산"""
    return SequenceMatcher(None, a, b).ratio()


def search_similar_question(user_question, threshold=0.8):
    """DB에서 유사 질문 검색"""
    if not conn or not cursor:
        return None, None, 0
    try:
        cursor.execute("SELECT question, answer FROM qa_pairs")
        for q, a in cursor.fetchall():
            score = similar(user_question, q)
            if score >= threshold:
                return a, q, score
        return None, None, 0
    except Exception as e:
        st.warning(f"DB 검색 중 오류 발생: {str(e)}")
        return None, None, 0


def generate_ai_answer(user_input):
    """AI 응답 생성 및 DB 저장"""
    system_message = {
        "role": "system",
        "content": (
            "당신은 장애 대응 가이드 전문가입니다.\n"
            "주어진 질문에 대해 회사 내부 기준에 따라 상세하고 신뢰할 수 있는 답변을 작성하세요.\n"
            "정보 부족시 '주어진 정보만으로는 답변하기 어렵습니다.'라고 답변하세요."
        ),
    }
    try:
        response = chat_client.chat.completions.create(
            model=chat_model,
            messages=[system_message, {"role": "user", "content": user_input}],
        )
        ai_answer = response.choices[0].message.content
        if conn and cursor:
            try:
                cursor.execute(
                    "INSERT INTO qa_pairs (question, answer) VALUES (?, ?)",
                    (user_input, ai_answer),
                )
                conn.commit()
            except Exception as e:
                st.warning(f"DB 저장 중 오류 발생: {str(e)}")
        return ai_answer
    except Exception as e:
        st.error(f"AI 응답 생성 중 오류 발생: {str(e)}")
        return "죄송합니다. 현재 응답을 생성할 수 없습니다. 잠시 후 다시 시도해주세요."


def get_recent_questions():
    """최근 고객 질문 5개 조회"""
    try:
        customer_db_path = "data/db/customer_qa.db"
        if not os.path.exists(customer_db_path):
            return get_default_questions()
        customer_conn = sqlite3.connect(customer_db_path)
        customer_cursor = customer_conn.cursor()
        customer_cursor.execute(
            """
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='customer_questions'
        """
        )
        if not customer_cursor.fetchone():
            customer_conn.close()
            return get_default_questions()
        customer_cursor.execute(
            """
            SELECT DISTINCT question 
            FROM customer_questions 
            ORDER BY created_at DESC 
            LIMIT 5
        """
        )
        results = customer_cursor.fetchall()
        customer_conn.close()
        return [row[0] for row in results] if results else get_default_questions()
    except Exception as e:
        st.warning(f"최근 질문 불러오기 오류: {str(e)}")
        return get_default_questions()


def get_default_questions():
    """기본 질문 리스트 반환"""
    return [
        "정보시스템 등급관리는 어떻게 하나요?",
        "정보시스템 등급산정 방식은 어떻게 되나요?",
        "장애상황관리는 어떻게 하나요?",
        "보안사고 대응절차는 무엇인가요?",
        "시스템 백업 정책은 어떻게 되나요?",
    ]


def process_question(user_message):
    """질문 처리 및 응답"""
    st.session_state.messages.append({"role": "user", "content": user_message})
    st.chat_message("user").write(user_message)
    with st.spinner("DB에서 기존 질문 검색 중..."):
        answer, matched_question, score = search_similar_question(user_message)
    if answer:
        st.write(
            f"기존 DB에서 유사 질문 발견 (유사도: {score:.2f}): {matched_question}"
        )
        st.chat_message("assistant").write(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})
    else:
        with st.spinner("AI가 답변 생성 중..."):
            ai_answer = generate_ai_answer(user_message)
        st.chat_message("assistant").write(ai_answer)
        st.session_state.messages.append({"role": "assistant", "content": ai_answer})
        st.write(
            "새로운 Q&A가 DB에 저장되었습니다."
            if conn and cursor
            else "AI 응답 생성 완료 (DB 저장 불가)"
        )


# 세션 상태 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []

# 기존 대화 출력
for message in st.session_state.messages:
    st.chat_message(message["role"]).write(message["content"])

# 중요 키워드 버튼
st.subheader("\U0001f50d 중요 키워드 빠른 검색")
recent_questions = get_recent_questions()
for i, question in enumerate(recent_questions):
    if st.button(question, key=f"keyword_button_{i}", use_container_width=True):
        process_question(question)

# 일반 입력창 처리
if user_input := st.chat_input("질문을 입력하세요 :"):
    process_question(user_input)

# 종료 시 DB 연결 종료
if conn:
    conn.close()
