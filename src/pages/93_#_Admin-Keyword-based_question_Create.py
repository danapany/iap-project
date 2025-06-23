import os
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.ai.textanalytics import TextAnalyticsClient
from azure.search.documents import SearchClient
from openai import AzureOpenAI
import streamlit as st
import sqlite3
from datetime import datetime

# Load environment variables
load_dotenv()

# Azure Text Analytics 설정
language_endpoint = os.getenv("AZURE_LANGUAGE_ENDPOINT")
language_key = os.getenv("AZURE_LANGUAGE_KEY")

# Azure OpenAI 설정
openai_endpoint = os.getenv("OPENAI_ENDPOINT")
openai_api_key = os.getenv("OPENAI_API_KEY")
chat_model = os.getenv("CHAT_MODEL")

# Azure AI Search 설정
search_endpoint = os.getenv("SEARCH_ENDPOINT")
search_key = os.getenv("SEARCH_API_KEY")

# Initialize Azure Text Analytics client
text_analytics_client = TextAnalyticsClient(
    endpoint=language_endpoint, credential=AzureKeyCredential(language_key)
)

# Initialize Azure OpenAI client
openai_client = AzureOpenAI(
    api_version="2024-12-01-preview",
    azure_endpoint=openai_endpoint,
    api_key=openai_api_key,
)

# Initialize Azure AI Search client
search_client_cust = SearchClient(
    endpoint=search_endpoint,
    index_name="danapany-cust-index",
    credential=AzureKeyCredential(search_key),
)


def search_and_extract_text(search_client, query="*", top=50):
    """Azure AI Search에서 문서를 검색하고 텍스트를 추출합니다."""
    try:
        results = search_client.search(search_text=query, top=top, select=["content"])

        combined_text = ""
        doc_count = 0

        for result in results:
            if "content" in result:
                combined_text += result["content"] + "\n"
                doc_count += 1

        st.info(f"검색된 문서 수: {doc_count}")
        return combined_text

    except Exception as e:
        st.error(f"검색 중 오류 발생: {str(e)}")
        return ""


def analyze_text_with_azure_language(text):
    """Azure AI Language를 사용하여 텍스트를 분석합니다."""
    if not text.strip():
        return []

    # 텍스트가 너무 길면 청크로 나누어 처리
    max_length = 5000
    chunks = [text[i : i + max_length] for i in range(0, len(text), max_length)]

    all_key_phrases = []

    for chunk in chunks:
        if chunk.strip():
            try:
                documents = [chunk]
                response = text_analytics_client.extract_key_phrases(documents)

                for doc in response:
                    if not doc.is_error:
                        all_key_phrases.extend(doc.key_phrases)
            except Exception as e:
                st.warning(f"키워드 추출 중 오류: {str(e)}")
                continue

    # 중복 제거
    return list(set(all_key_phrases))


def generate_questions_with_openai(key_phrases):
    """Azure OpenAI를 사용하여 예상 질문을 생성합니다."""
    prompt = f"""
    아래는 고객사의 관리체계에 대한 주요 키워드입니다:
    
    키워드: {', '.join(key_phrases[:50])}
    
    이 키워드들을 바탕으로 사용자가 고객사의 장애관리체계에 대해 궁금해할 만한 주요 질문 5개를 생성해주세요.
    
    질문은 다음과 같은 형태로 작성해주세요:
    - 실무진이 실제로 궁금해할 만한 구체적인 질문
    - 관리체계의 운영, 절차, 정책에 관련된 질문
    - 각 질문은 한 줄로 작성
    
    예시:
    1. 장애 발생 시 초기 대응 절차는 어떻게 되나요?
    2. 변경 관리 승인 프로세스는 어떤 단계를 거치나요?
    3. 보안 관리체계에서 접근 권한은 어떻게 관리되나요?
    4. 백업 및 복구 정책의 주기는 어떻게 설정되어 있나요?
    5. 시스템 모니터링은 어떤 도구와 방법으로 진행되나요?
    
    위와 같은 형식으로 5개의 질문 생성해주세요.
    """

    try:
        response = openai_client.chat.completions.create(
            model=chat_model,
            messages=[
                {
                    "role": "system",
                    "content": "당신은 IT 관리체계 전문가입니다. 고객사의 관리체계 키워드를 바탕으로 실무진이 궁금해할 만한 실용적인 질문들을 생성합니다.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=1000,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"질문 생성 중 오류가 발생했습니다: {str(e)}"


def parse_questions(questions_text):
    """생성된 질문 텍스트를 파싱하여 리스트로 변환합니다."""
    lines = questions_text.strip().split("\n")
    questions = []

    for line in lines:
        line = line.strip()
        if line and (line[0].isdigit() or line.startswith("-") or line.startswith("•")):
            # 번호나 불릿 포인트 제거
            question = line
            if ". " in line:
                question = (
                    line.split(". ", 1)[1] if len(line.split(". ", 1)) > 1 else line
                )
            elif "- " in line:
                question = (
                    line.split("- ", 1)[1] if len(line.split("- ", 1)) > 1 else line
                )
            elif "• " in line:
                question = (
                    line.split("• ", 1)[1] if len(line.split("• ", 1)) > 1 else line
                )

            questions.append(question.strip())

    return questions[:5]  # 최대 5개만 반환


def save_questions_to_db(questions, keywords):
    """생성된 질문을 새로운 데이터베이스에 저장합니다."""
    try:
        # data 디렉토리가 없으면 생성
        os.makedirs("data", exist_ok=True)
        os.makedirs("data/db", exist_ok=True)

        conn = sqlite3.connect("data/db/customer_qa.db")
        c = conn.cursor()

        # 테이블이 없으면 생성
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS customer_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                keywords TEXT,
                generation_date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # 질문들 저장
        generation_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        keywords_str = ", ".join(keywords[:50])  # 상위 50개 키워드만 저장

        question_ids = []
        for question in questions:
            c.execute(
                """
                INSERT INTO customer_questions 
                (question, keywords, generation_date) 
                VALUES (?, ?, ?)
            """,
                (question, keywords_str, generation_date),
            )
            question_ids.append(c.lastrowid)

        conn.commit()
        conn.close()

        return question_ids

    except Exception as e:
        st.error(f"데이터베이스 저장 중 오류 발생: {str(e)}")
        return None


def load_questions_history():
    """저장된 질문 이력을 조회합니다."""
    try:
        conn = sqlite3.connect("data/db/customer_qa.db")
        c = conn.cursor()

        c.execute(
            """
            SELECT id, question, generation_date, created_at 
            FROM customer_questions 
            ORDER BY created_at DESC 
            LIMIT 20
        """
        )

        results = c.fetchall()
        conn.close()

        return results

    except Exception as e:
        st.error(f"이력 조회 중 오류 발생: {str(e)}")
        return []


def get_questions_by_date(generation_date):
    """특정 날짜에 생성된 질문들을 조회합니다."""
    try:
        conn = sqlite3.connect("data/db/customer_qa.db")
        c = conn.cursor()

        c.execute(
            """
            SELECT question, keywords
            FROM customer_questions 
            WHERE generation_date = ?
            ORDER BY id
        """,
            (generation_date,),
        )

        results = c.fetchall()
        conn.close()

        return results

    except Exception as e:
        st.error(f"질문 조회 중 오류 발생: {str(e)}")
        return []


# Streamlit App
st.title("❓ 고객사 관리체계 주요 질문 생성 (관리용)")
st.caption(
    "Azure AI Search 인덱스를 활용하여 고객사 관리체계 키워드 기반으로 예상 질문을 생성합니다."
)

# 탭 생성
tab1, tab2 = st.tabs(["🎯 질문 생성", "📋 질문 이력"])

with tab1:
    # 질문 생성 시작 버튼
    if st.button("질문 생성 시작", type="primary"):
        with st.spinner(
            "Azure AI Search에서 데이터를 검색하고 질문을 생성 중입니다..."
        ):

            # 1. Azure AI Search에서 텍스트 추출
            st.subheader("1단계: 고객사 데이터 검색")

            st.info("고객사 데이터 검색 중...")
            cust_text = search_and_extract_text(search_client_cust, query="관리체계")
            st.success(f"고객사 텍스트 길이: {len(cust_text)} 문자")

            if not cust_text:
                st.error("검색된 데이터가 없습니다. 인덱스와 검색 조건을 확인해주세요.")
                st.stop()

            # 2. 키워드 추출
            st.subheader("2단계: 키워드 추출")

            st.info("고객사 키워드 추출 중...")
            cust_key_phrases = analyze_text_with_azure_language(cust_text)
            st.success(f"추출된 키워드 수: {len(cust_key_phrases)}")
            if cust_key_phrases:
                st.write("주요 키워드:", ", ".join(cust_key_phrases[:20]))

            # 3. 예상 질문 생성
            st.subheader("3단계: 예상 질문 생성")

            if cust_key_phrases:
                st.info("OpenAI를 통해 예상 질문 생성 중...")
                questions_text = generate_questions_with_openai(cust_key_phrases)

                # 질문 파싱
                questions = parse_questions(questions_text)

                if questions:
                    st.success(f"✅ {len(questions)}개의 질문이 생성되었습니다!")

                    # 생성된 질문 표시
                    st.subheader("🎯 생성된 예상 질문들:")
                    for i, question in enumerate(questions, 1):
                        st.write(f"{i}. {question}")

                    # 4. 데이터베이스에 저장
                    st.subheader("4단계: 질문 저장")
                    st.info("생성된 질문을 데이터베이스에 저장 중...")
                    question_ids = save_questions_to_db(questions, cust_key_phrases)

                    if question_ids:
                        st.success(
                            f"✅ {len(question_ids)}개의 질문이 데이터베이스에 저장되었습니다."
                        )
                        st.write(f"저장된 질문 ID: {', '.join(map(str, question_ids))}")
                    else:
                        st.warning("⚠️ 데이터베이스 저장에 실패했습니다.")
                else:
                    st.warning("질문 파싱에 실패했습니다. 원문을 확인해주세요:")
                    st.text(questions_text)
            else:
                st.warning("키워드가 추출되지 않아 질문을 생성할 수 없습니다.")

with tab2:
    st.subheader("📋 질문 생성 이력")

    # 이력 조회 버튼
    if st.button("이력 새로고침"):
        st.rerun()

    # 질문 이력 표시
    history = load_questions_history()

    if history:
        st.write(f"최근 {len(history)}개의 생성된 질문:")

        # 날짜별로 그룹화
        dates = list(set([record[2] for record in history]))
        dates.sort(reverse=True)

        for date in dates:
            date_questions = [record for record in history if record[2] == date]

            with st.expander(f"📅 {date} ({len(date_questions)}개 질문)"):
                questions_data = get_questions_by_date(date)

                if questions_data:
                    # 키워드 표시 (첫 번째 질문의 키워드 사용)
                    if questions_data[0][1]:
                        st.write("**관련 키워드:**")
                        st.write(questions_data[0][1])
                        st.write("---")

                    st.write("**생성된 질문들:**")
                    for i, (question, _) in enumerate(questions_data, 1):
                        st.write(f"{i}. {question}")
                else:
                    st.write("질문 데이터를 불러올 수 없습니다.")
    else:
        st.info("저장된 질문 이력이 없습니다. 새 질문을 생성해보세요.")
