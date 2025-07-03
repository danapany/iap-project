import sqlite3
import streamlit as st
import os


def load_faq_from_db():
    try:
        # 데이터베이스 파일이 존재하는지 확인
        db_path = "data/db/faq.db"
        if not os.path.exists(db_path):
            # 디렉토리가 없으면 생성
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            return []

        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        # 테이블이 존재하는지 확인
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='faq'")
        if not c.fetchone():
            conn.close()
            return []

        c.execute("SELECT id, content FROM faq ORDER BY id DESC LIMIT 1")
        faqs = c.fetchall()
        conn.close()
        return faqs

    except sqlite3.Error as e:
        st.error(f"데이터베이스 오류: {e}")
        return []
    except Exception as e:
        st.error(f"예상치 못한 오류가 발생했습니다: {e}")
        return []


# === Streamlit 앱 ===
st.title("💡 장애대응절차 FAQ")
st.caption("회사 장애대응 절차에 대한 FAQ를 안내 합니다")

faqs = load_faq_from_db()

if faqs:
    for faq_id, content in faqs:
        st.markdown(f"**FAQ {faq_id}**")
        st.write(content)
        st.markdown("---")

else:
    st.info("저장된 FAQ가 없습니다.")
