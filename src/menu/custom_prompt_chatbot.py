# 기존 코드 상단에 기본 프롬프트 정의
DEFAULT_PROMPT = """당신은 IT 시스템 장애 전문가입니다. 
사용자의 질문에 대해 제공된 장애 이력 문서를 기반으로 정확하고 유용한 답변을 제공해주세요.
답변은 한국어로 작성하며, 구체적인 해결방안이나 원인을 명시해주세요.
장애 ID, 서비스명, 원인, 복구방법 등의 구체적인 정보를 포함해주세요.
만약 제공된 문서에서 관련 정보를 찾을 수 없다면, 그렇게 명시해주세요."""

# 버튼 유형에 따른 프롬프트 반환 함수 추가
def get_prompt_by_button_type(button_type):
    if button_type == "guide":
        return """당신은 IT 대응 가이드 전문가입니다. 
사용자의 서비스와 현상을 바탕으로 명확하고 실용적인 대응 방안을 제공하세요."""
    elif button_type == "cause":
        return """당신은 장애 원인 분석 전문가입니다. 
사용자의 질문에 대해 대표적인 장애 원인을 간결하게 설명하세요."""
    elif button_type == "history":
        return """당신은 과거 장애 이력 분석 전문가입니다. 
유사한 과거 장애 사례를 찾아 요약하세요."""
    elif button_type == "similar":
        return """당신은 유사 사례 추천 전문가입니다. 
다른 서비스에서 유사한 장애 현상이 어떻게 처리됐는지 설명하세요."""
    else:
        return DEFAULT_PROMPT

# generate_rag_response 함수 수정

def generate_rag_response(azure_openai_client, query, documents, model_name, system_prompt):
    try:
        context_parts = []
        for i, doc in enumerate(documents):
            context_parts.append(f"""문서 {i+1}:
장애 ID: {doc['incident_id']}
도메인: {doc['domain_name']}
서비스명: {doc['service_name']}
서비스 등급: {doc['service_grade']}
장애 범위: {doc['error_range']}
제목: {doc['subject']}
공지사항: {doc['notice_text']}
장애 원인: {doc['incident_cause']}
복구 방법: {doc['incident_repair']}
개선 계획: {doc['incident_plan']}
원인 유형: {doc['cause_type']}
처리 유형: {doc['done_type']}
장애 등급: {doc['incident_grade']}
담당 부서: {doc['owner_depart']}""")
        context = "\n\n".join(context_parts)

        user_prompt = f"""
다음 장애 이력 문서들을 참고하여 질문에 답변해주세요:

{context}

질문: {query}

답변:"""

        response = azure_openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )

        return response.choices[0].message.content

    except Exception as e:
        st.error(f"응답 생성 실패: {str(e)}")
        return "죄송합니다. 응답을 생성하는 중 오류가 발생했습니다."

# 주요 질문 버튼 처리 부분 수정
with col1:
    if st.button("서비스와 현상에 대해 대응가이드 안내"):
        st.session_state.sample_prompt = get_prompt_by_button_type("guide")
        st.session_state.sample_query = f"{service_name} {incident_symptom}에 대한 대응가이드 안내" if service_name and incident_symptom else "서비스와 현상에 대해 대응가이드 안내"

    if st.button("현상에 대한 대표 원인 안내"):
        st.session_state.sample_prompt = get_prompt_by_button_type("cause")
        st.session_state.sample_query = f"{service_name} {incident_symptom} 현상에 대한 대표 원인 안내" if service_name and incident_symptom else "현상에 대한 대표 원인 안내"

with col2:
    if st.button("서비스와 현상에 대한 과거 대응방법"):
        st.session_state.sample_prompt = get_prompt_by_button_type("history")
        st.session_state.sample_query = f"{service_name} {incident_symptom}에 대한 과거 대응방법" if service_name and incident_symptom else "서비스와 현상에 대한 과거 대응방법"

    if st.button("타 서비스에 동일 현상에 대한 대응이력조회"):
        st.session_state.sample_prompt = get_prompt_by_button_type("similar")
        st.session_state.sample_query = f"타 서비스에서 {incident_symptom} 동일 현상에 대한 대응이력조회" if incident_symptom else "타 서비스에 동일 현상에 대한 대응이력조회"

# sample_query 처리 시 prompt도 함께 처리
if 'sample_query' in st.session_state:
    query = st.session_state.sample_query
    system_prompt = st.session_state.get("sample_prompt", DEFAULT_PROMPT)

    del st.session_state.sample_query
    st.session_state.pop("sample_prompt", None)

    st.session_state.messages.append({"role": "user", "content": query})

    with st.chat_message("user"):
        st.write(query)

    with st.chat_message("assistant"):
        with st.spinner("검색 중..."):
            documents = semantic_search_documents(search_client, query, search_count) if search_type == "시맨틱 검색 (권장)" else search_documents(search_client, query, search_count)
            if documents:
                with st.expander("검색된 문서 보기"):
                    display_documents(documents)
                with st.spinner("답변 생성 중..."):
                    response = generate_rag_response(azure_openai_client, query, documents, azure_openai_model, system_prompt)
                    st.write(response)
                    st.session_state.messages.append({"role": "assistant", "content": response})
            else:
                error_msg = "관련 문서를 찾을 수 없습니다."
                st.write(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})

    st.rerun()
