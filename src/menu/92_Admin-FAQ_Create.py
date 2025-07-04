import streamlit as st
import os
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizableTextQuery
from langchain_openai import AzureChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import ToolMessage, SystemMessage
import sqlite3  # 추가

# === .env 파일 로드 ===
load_dotenv()

# === 환경 변수 설정 ===
OPENAI_ENDPOINT = os.getenv("OPENAI_ENDPOINT")
OPENAI_API_KEY = os.getenv("OPENAI_KEY")
CHAT_MODEL = os.getenv("CHAT_MODEL")
SEARCH_ENDPOINT = os.getenv("SEARCH_ENDPOINT")
SEARCH_API_KEY = os.getenv("SEARCH_API_KEY")
INDEX_NAME = os.getenv("INDEX_GUIDE_NAME")

# === Azure OpenAI 설정 ===
from openai import AzureOpenAI

client = AzureOpenAI(
    api_version="2024-12-01-preview",
    azure_endpoint=OPENAI_ENDPOINT,
    api_key=OPENAI_API_KEY,
)
deployment = CHAT_MODEL

# === Azure Cognitive Search 설정 ===
search_client = SearchClient(
    endpoint=SEARCH_ENDPOINT,
    index_name=INDEX_NAME,
    credential=AzureKeyCredential(SEARCH_API_KEY),
)

# === 검색 도구 정의 ===
from langchain_core.tools import tool


@tool
def search_guide(query, top_k=3):
    """
    회사의 장애대응 지침정보를 검색합니다.

    Args:
        query (str): 검색할 키워드 또는 질문입니다. 예시: '장애대응 절차에 대해 알려주세요'
        top_k (int, optional): 반환할 결과의 개수입니다. 기본값은 3입니다. 예시: 5

    Returns:
        list: 검색 결과 (점수, 텍스트) 리스트
    """
    vector_query = VectorizableTextQuery(
        text=query, k_nearest_neighbors=top_k, fields="text_vector"
    )
    results = search_client.search(
        search_text=query, vector_queries=[vector_query], filter=None, top=top_k
    )

    return [(doc["@search.score"], doc["chunk"]) for doc in results]


# === LangChain 및 LangGraph 설정 ===
llm = AzureChatOpenAI(
    azure_deployment=deployment,
    api_version="2024-12-01-preview",
    azure_endpoint=OPENAI_ENDPOINT,
    temperature=0.0,
    api_key=OPENAI_API_KEY,
)

agent_engine = llm.bind_tools(tools=[search_guide])
tool_node = ToolNode([search_guide])


class AgentState(MessagesState): ...


def should_continue(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1]

    if last_message.tool_calls:
        return "tools"

    return END


def call_model(state: AgentState):
    sys_prompt = SystemMessage(
        """[지침]
        - 컨텍스트에 있는 정보만을 사용하여 답변할 것
        - 외부 지식이나 정보를 사용하지 말 것
        - 컨텍스트에서 답을 찾을 수 없는 경우 "주어진 정보만으로는 답변하기 어렵습니다."라고 응답할 것
        - 불확실한 경우 명확히 그 불확실성을 표현할 것
        - 답변은 논리적이고 구조화된 형태로 제공할 것
        - 답변은 한국어를 사용할 것"""
    )

    response = agent_engine.invoke([sys_prompt] + state["messages"])

    return {"messages": [response]}


def save_faq_to_db(content):
    conn = sqlite3.connect("data/db/faq.db")
    c = conn.cursor()
    # 테이블이 없으면 생성
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS faq (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL
        )
    """
    )
    # FAQ 내용 저장
    c.execute("INSERT INTO faq (content) VALUES (?)", (content,))
    conn.commit()
    conn.close()


# === 워크플로우 정의 ===
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, ["tools", END])
workflow.add_edge("tools", "agent")

graph = workflow.compile()


# === Streamlit 앱 ===
st.title("💡 장애대응절차 FAQ 생성 (관리용)")
st.caption("회사 장애대응 절차에 대한 FAQ를 20개 생성합니다")

question = "장애대응절차에 대해서 FAQ 20개를 생성해줘."

if question:
    st.info("FAQ 생성 중입니다...")
    inputs = {"messages": [("user", question)]}
    stream = graph.stream(inputs, stream_mode="values")

    for s in stream:
        message = s["messages"][-1]

    # FAQ 결과 DB에 저장
    save_faq_to_db(message.content)

    # Display the generated FAQ messages
    st.write(message.content)

    st.info("FAQ 생성 완료되었습니다")
