import sqlite3
import streamlit as st
import os


def load_process_descriptions():
    db_path = "data/db/process_description.db"

    # 데이터베이스 파일이 존재하지 않는 경우
    if not os.path.exists(db_path):
        return []

    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute(
            "SELECT id, content FROM process_description ORDER BY id DESC LIMIT 2 "
        )
        rows = c.fetchall()
        conn.close()
        return rows
    except sqlite3.Error as e:
        # 데이터베이스 오류가 발생한 경우 (테이블이 없는 경우 등)
        st.error(f"데이터베이스 오류가 발생했습니다: {e}")
        return []
    except Exception as e:
        # 기타 예외 처리
        st.error(f"예상치 못한 오류가 발생했습니다: {e}")
        return []


st.title("💡 장애대응 프로세스 안내")
st.caption("회사 장애대응 프로세스에 대한 설명입니다.")

descriptions = load_process_descriptions()

if descriptions:
    for desc_id, content in descriptions:
        st.markdown(f"**ID: {desc_id}**")
        st.write(content)
        st.markdown("---")
else:
    st.info("저장된 프로세스 설명이 없습니다.")
