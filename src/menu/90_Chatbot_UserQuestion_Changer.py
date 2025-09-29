import streamlit as st
import pandas as pd
import openpyxl
from datetime import datetime
import logging
from pathlib import Path
import tempfile
import os
from utils.reprompting_db_manager import RepromptingDBManager

class ExcelUploadManagerReprompting:
    """질문 재프롬프팅 처리 엑셀 업로드 관리 클래스"""
    
    def __init__(self):
        self.db_manager = RepromptingDBManager()
        self.allowed_extensions = ['.xlsx', '.xls']
        self.max_file_size = 10 * 1024 * 1024  # 10MB
        
        # 질문 유형 옵션들
        self.question_types = [
            "장애이력문의",
            "장애건수/통계문의", 
            "현상에대한 복구방법문의",
            "시스템 운영문의",
            "기타 기술지원문의",
            "직접입력"  # 사용자 정의 옵션
        ]
        
    def validate_excel_file(self, uploaded_file):
        """업로드된 엑셀 파일 유효성 검사"""
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': []
        }
        
        # 파일 크기 체크
        if uploaded_file.size > self.max_file_size:
            validation_result['is_valid'] = False
            validation_result['errors'].append(f"파일 크기가 너무 큽니다. 최대 {self.max_file_size // (1024*1024)}MB까지 허용됩니다.")
        
        # 파일 확장자 체크
        file_extension = Path(uploaded_file.name).suffix.lower()
        if file_extension not in self.allowed_extensions:
            validation_result['is_valid'] = False
            validation_result['errors'].append(f"지원하지 않는 파일 형식입니다. 허용 형식: {', '.join(self.allowed_extensions)}")
        
        return validation_result
    
    def validate_excel_structure(self, df):
        """엑셀 파일 구조 유효성 검사"""
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': []
        }
        
        # 필수 컬럼 체크 (새로운 구조)
        required_columns = ['질문유형', '질문', '맞춤형 프롬프트', '오답요약']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            validation_result['is_valid'] = False
            validation_result['errors'].append(f"필수 컬럼이 누락되었습니다: {', '.join(missing_columns)}")
        
        # 데이터 행 수 체크
        if len(df) == 0:
            validation_result['is_valid'] = False
            validation_result['errors'].append("데이터가 없습니다.")
        elif len(df) > 1000:
            validation_result['warnings'].append(f"데이터가 많습니다 ({len(df)}행). 처리에 시간이 걸릴 수 있습니다.")
        
        # 필수 컬럼의 빈 값 체크
        if validation_result['is_valid']:
            for col in required_columns:
                null_count = df[col].isnull().sum()
                if null_count > 0:
                    validation_result['warnings'].append(f"'{col}' 컬럼에 빈 값이 {null_count}개 있습니다. 해당 행은 제외됩니다.")
        
        # 중복 질문 체크
        if validation_result['is_valid'] and '질문' in df.columns:
            duplicate_questions = df['질문'].duplicated().sum()
            if duplicate_questions > 0:
                validation_result['warnings'].append(f"중복된 질문이 {duplicate_questions}개 있습니다. 최신 데이터로 업데이트됩니다.")
        
        return validation_result
    
    def validate_individual_input(self, question_type, question, custom_prompt, wrong_answer_summary):
        """개별 입력 데이터 유효성 검사"""
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': []
        }
        
        # 필수 필드 체크
        if not question_type or question_type.strip() == "":
            validation_result['is_valid'] = False
            validation_result['errors'].append("질문 유형을 선택하거나 입력해주세요.")
            
        if not question or question.strip() == "":
            validation_result['is_valid'] = False
            validation_result['errors'].append("질문을 입력해주세요.")
            
        if not custom_prompt or custom_prompt.strip() == "":
            validation_result['is_valid'] = False
            validation_result['errors'].append("맞춤형 프롬프트를 입력해주세요.")
        
        # 길이 체크
        if len(question) > 1000:
            validation_result['warnings'].append("질문이 너무 깁니다. (1000자 초과)")
            
        if len(custom_prompt) > 2000:
            validation_result['warnings'].append("맞춤형 프롬프트가 너무 깁니다. (2000자 초과)")
        
        # 중복 질문 체크
        existing_question = self.db_manager.check_reprompting_question(question)
        if existing_question['exists']:
            validation_result['warnings'].append("동일한 질문이 이미 존재합니다. 저장 시 기존 데이터가 업데이트됩니다.")
        
        return validation_result
    
    def preview_excel_data(self, uploaded_file, max_rows=10):
        """엑셀 파일 데이터 미리보기"""
        try:
            # 임시 파일로 저장
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_file_path = tmp_file.name
            
            # 엑셀 파일 읽기
            df = pd.read_excel(tmp_file_path)
            
            # 임시 파일 삭제
            os.unlink(tmp_file_path)
            
            # 미리보기 데이터 준비
            preview_data = {
                'total_rows': len(df),
                'columns': df.columns.tolist(),
                'sample_data': df.head(max_rows),
                'data_types': df.dtypes.to_dict()
            }
            
            return preview_data
            
        except Exception as e:
            logging.error(f"엑셀 미리보기 실패: {str(e)}")
            return None
    
    def process_upload(self, uploaded_file):
        """엑셀 파일 업로드 처리"""
        try:
            # 파일 유효성 검사
            file_validation = self.validate_excel_file(uploaded_file)
            if not file_validation['is_valid']:
                return {
                    'success': False,
                    'errors': file_validation['errors'],
                    'stage': 'file_validation'
                }
            
            # 임시 파일로 저장
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_file_path = tmp_file.name
            
            try:
                # 엑셀 파일 읽기
                df = pd.read_excel(tmp_file_path)
                
                # 구조 유효성 검사
                structure_validation = self.validate_excel_structure(df)
                if not structure_validation['is_valid']:
                    return {
                        'success': False,
                        'errors': structure_validation['errors'],
                        'warnings': structure_validation['warnings'],
                        'stage': 'structure_validation'
                    }
                
                # DB에 업로드
                upload_result = self.db_manager.upload_excel_to_db(
                    tmp_file_path, 
                    uploaded_file.name
                )
                
                # 결과에 구조 검사 경고 추가
                if structure_validation['warnings']:
                    upload_result['warnings'] = structure_validation['warnings']
                
                return upload_result
                
            finally:
                # 임시 파일 삭제
                if os.path.exists(tmp_file_path):
                    os.unlink(tmp_file_path)
                    
        except Exception as e:
            logging.error(f"엑셀 업로드 처리 실패: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'stage': 'processing'
            }
    
    def process_individual_input(self, question_type, question, custom_prompt, wrong_answer_summary):
        """개별 질문 입력 처리"""
        try:
            # 데이터 유효성 검사
            validation = self.validate_individual_input(question_type, question, custom_prompt, wrong_answer_summary)
            if not validation['is_valid']:
                return {
                    'success': False,
                    'errors': validation['errors'],
                    'warnings': validation.get('warnings', [])
                }
            
            # DB에 저장
            result = self.db_manager.add_single_reprompting_question(
                question_type=question_type.strip(),
                question=question.strip(),
                custom_prompt=custom_prompt.strip(),
                wrong_answer_summary=wrong_answer_summary.strip() if wrong_answer_summary else ""
            )
            
            if result['success']:
                return {
                    'success': True,
                    'message': '질문이 성공적으로 저장되었습니다.',
                    'action': result.get('action', 'inserted'),
                    'warnings': validation.get('warnings', [])
                }
            else:
                return {
                    'success': False,
                    'error': result.get('error', '저장 중 오류가 발생했습니다.')
                }
                
        except Exception as e:
            logging.error(f"개별 질문 입력 처리 실패: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def render_individual_input_interface(self):
        """개별 질문 입력 인터페이스 렌더링"""
        st.header("➕ 개별 질문 입력")
        
        # 입력 가이드
        with st.expander("📋 입력 가이드", expanded=True):
            st.markdown("""
            ### 개별 질문 입력 방법:
            
            **필수 입력 항목:**
            - **질문 유형**: 질문의 분류를 선택하거나 직접 입력
            - **질문**: 사용자가 입력한 실제 질문
            - **맞춤형 프롬프트**: 해당 질문에 대한 개선된 맞춤형 프롬프트
            
            **선택 입력 항목:**
            - **오답요약**: 기존 응답의 문제점이나 오답에 대한 요약
            
            **주의사항:**
            - 중복된 질문은 기존 데이터를 업데이트합니다
            - 모든 필수 항목을 입력해야 저장 가능합니다
            - 저장 후 바로 시스템에 반영됩니다
            """)
        
        # 입력 폼
        st.write("### 📝 질문 정보 입력")
        
        with st.form("individual_question_form", clear_on_submit=True):
            col1, col2 = st.columns([1, 2])
            
            with col1:
                # 질문 유형 선택
                question_type_option = st.selectbox(
                    "질문 유형 선택",
                    self.question_types,
                    index=0,
                    help="질문의 분류를 선택하세요. '직접입력'을 선택하면 직접 입력할 수 있습니다."
                )
                
                # 직접 입력 옵션
                if question_type_option == "직접입력":
                    custom_question_type = st.text_input(
                        "질문 유형 직접 입력",
                        placeholder="예: API 연동문의",
                        help="새로운 질문 유형을 입력하세요"
                    )
                    final_question_type = custom_question_type
                else:
                    final_question_type = question_type_option
            
            with col2:
                # 질문 입력
                question = st.text_area(
                    "질문 *",
                    height=100,
                    placeholder="사용자가 입력한 실제 질문을 입력하세요...",
                    help="실제 사용자가 입력한 질문을 그대로 입력하세요",
                    max_chars=1000
                )
            
            # 맞춤형 프롬프트 입력
            custom_prompt = st.text_area(
                "맞춤형 프롬프트 *",
                height=150,
                placeholder="해당 질문에 대한 개선된 맞춤형 프롬프트를 입력하세요...",
                help="질문에 대해 더 정확하고 유용한 답변을 생성하기 위한 프롬프트를 작성하세요",
                max_chars=2000
            )
            
            # 오답요약 입력 (선택사항)
            wrong_answer_summary = st.text_area(
                "오답요약 (선택사항)",
                height=100,
                placeholder="기존 응답의 문제점이나 오답에 대한 요약을 입력하세요...",
                help="기존 시스템의 잘못된 답변이나 문제점에 대한 요약 (선택사항)",
                max_chars=500
            )
            
            # 미리보기 및 저장 버튼
            col1, col2, col3 = st.columns([2, 1, 1])
            with col2:
                preview_button = st.form_submit_button("👀 미리보기", type="secondary")
            with col3:
                save_button = st.form_submit_button("💾 저장", type="primary")
        
        # 미리보기 기능
        if preview_button and question and custom_prompt:
            st.write("### 👀 입력 데이터 미리보기")
            
            preview_data = {
                "질문유형": final_question_type,
                "질문": question,
                "맞춤형 프롬프트": custom_prompt,
                "오답요약": wrong_answer_summary if wrong_answer_summary else "(입력 안함)"
            }
            
            # 미리보기 표시
            for key, value in preview_data.items():
                st.write(f"**{key}:**")
                st.write(f"└ {value}")
                st.write("")
            
            # 검증 결과 표시
            validation = self.validate_individual_input(final_question_type, question, custom_prompt, wrong_answer_summary)
            if not validation['is_valid']:
                st.error("❌ 입력 데이터에 오류가 있습니다:")
                for error in validation['errors']:
                    st.error(f"• {error}")
            else:
                st.success("✅ 입력 데이터가 유효합니다!")
                if validation.get('warnings'):
                    for warning in validation['warnings']:
                        st.warning(f"⚠️ {warning}")
        
        # 저장 처리
        if save_button:
            if not question or not custom_prompt or not final_question_type:
                st.error("❌ 필수 항목을 모두 입력해주세요!")
            else:
                with st.spinner("저장 중..."):
                    result = self.process_individual_input(
                        final_question_type, question, custom_prompt, wrong_answer_summary
                    )
                    self._display_individual_input_result(result)
    
    def _display_individual_input_result(self, result):
        """개별 입력 결과 표시"""
        if result['success']:
            st.success("✅ 질문이 성공적으로 저장되었습니다!")
            
            # 액션 타입에 따른 메시지
            if result.get('action') == 'updated':
                st.info("ℹ️ 기존 질문이 업데이트되었습니다.")
            else:
                st.info("ℹ️ 새로운 질문이 추가되었습니다.")
            
            # 경고사항 표시
            if result.get('warnings'):
                with st.expander("⚠️ 주의사항"):
                    for warning in result['warnings']:
                        st.warning(warning)
        else:
            st.error("❌ 저장에 실패했습니다.")
            
            if result.get('errors'):
                for error in result['errors']:
                    st.error(f"• {error}")
            
            if result.get('error'):
                st.error(f"• {result['error']}")
    
    def render_upload_interface(self):
        """업로드 인터페이스 렌더링"""
        st.header("📊 질문 재프롬프팅 데이터 업로드")
        
        # 업로드 가이드
        with st.expander("📋 업로드 가이드", expanded=True):
            st.markdown("""
            ### 엑셀 파일 형식 요구사항:
            
            **필수 컬럼:**
            - **질문유형**: 질문의 분류 (예: 장애이력문의, 장애건수/통계문의, 현상에대한 복구방법문의)
            - **질문**: 사용자가 입력한 실제 질문
            - **맞춤형 프롬프트**: 해당 질문에 대한 개선된 맞춤형 프롬프트
            - **오답요약**: 기존 응답의 문제점이나 오답에 대한 요약
            
            **파일 제한:**
            - 최대 파일 크기: 10MB
            - 지원 형식: .xlsx, .xls
            - 최대 행 수: 1,000행 (권장)
            
            **주의사항:**
            - 중복된 질문은 최신 데이터로 업데이트됩니다
            - 빈 값이 있는 행은 자동으로 제외됩니다
            """)
        
        # 파일 업로드
        uploaded_file = st.file_uploader(
            "엑셀 파일을 선택하세요",
            type=['xlsx', 'xls'],
            help="질문유형, 질문, 맞춤형 프롬프트, 오답요약 컬럼이 포함된 엑셀 파일을 업로드하세요"
        )
        
        if uploaded_file is not None:
            # 파일 정보 표시
            st.write("### 📄 파일 정보")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("파일명", uploaded_file.name)
            with col2:
                file_size_mb = uploaded_file.size / (1024 * 1024)
                st.metric("파일 크기", f"{file_size_mb:.2f} MB")
            with col3:
                st.metric("업로드 시간", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            
            # 미리보기
            st.write("### 👀 데이터 미리보기")
            preview_data = self.preview_excel_data(uploaded_file)
            
            if preview_data:
                st.write(f"**총 {preview_data['total_rows']}행의 데이터**")
                st.write(f"**컬럼:** {', '.join(preview_data['columns'])}")
                
                # 샘플 데이터 표시
                st.dataframe(preview_data['sample_data'], use_container_width=True)
                
                # 업로드 버튼
                col1, col2 = st.columns([3, 1])
                with col2:
                    if st.button("🚀 업로드 실행", type="primary"):
                        with st.spinner("업로드 중..."):
                            result = self.process_upload(uploaded_file)
                            self._display_upload_result(result)
            else:
                st.error("파일을 읽을 수 없습니다. 파일 형식을 확인해주세요.")
    
    def _display_upload_result(self, result):
        """업로드 결과 표시"""
        if result['success']:
            st.success("✅ 업로드가 완료되었습니다!")
            
            # 결과 통계
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("총 행 수", result['total_rows'])
            with col2:
                st.metric("성공", result['success_rows'], delta=result['success_rows'])
            with col3:
                if result['error_rows'] > 0:
                    st.metric("실패", result['error_rows'], delta=-result['error_rows'])
                else:
                    st.metric("실패", result['error_rows'])
            
            # 경고사항 표시
            if result.get('warnings'):
                with st.expander("⚠️ 주의사항"):
                    for warning in result['warnings']:
                        st.warning(warning)
            
            # 오류 상세 표시
            if result.get('error_details'):
                with st.expander("❌ 오류 상세"):
                    for error in result['error_details']:
                        st.error(error)
        else:
            st.error("❌ 업로드에 실패했습니다.")
            
            if result.get('errors'):
                for error in result['errors']:
                    st.error(f"• {error}")
            
            if result.get('error'):
                st.error(f"• {result['error']}")
            
            # 실패 단계 정보
            stage_messages = {
                'file_validation': '파일 유효성 검사 단계에서 실패',
                'structure_validation': '파일 구조 검사 단계에서 실패',
                'processing': '데이터 처리 단계에서 실패'
            }
            
            if result.get('stage'):
                st.info(f"🔍 {stage_messages.get(result['stage'], '알 수 없는 단계에서 실패')}")
    
    def render_statistics_interface(self):
        """통계 인터페이스 렌더링"""
        st.header("📈 재프롬프팅 데이터 통계")
        
        # 통계 조회
        stats = self.db_manager.get_reprompting_statistics()
        
        if stats:
            # 전체 통계
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("총 질문 수", stats['total_count'])
            with col2:
                st.metric("질문 유형 수", len(stats['type_statistics']))
            with col3:
                recent_uploads_count = len(stats['recent_uploads'])
                st.metric("최근 업로드 수", recent_uploads_count)
            
            # 질문 유형별 통계
            if stats['type_statistics']:
                st.write("### 📊 질문 유형별 분포")
                type_df = pd.DataFrame(stats['type_statistics'], columns=['질문유형', '건수'])
                
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.bar_chart(type_df.set_index('질문유형'))
                with col2:
                    st.dataframe(type_df)
            
            # 최근 업로드 이력
            if stats['recent_uploads']:
                st.write("### 📋 최근 업로드 이력")
                upload_df = pd.DataFrame(
                    stats['recent_uploads'], 
                    columns=['파일명', '총 행수', '성공', '실패', '업로드일시']
                )
                st.dataframe(upload_df)
        else:
            st.info("통계 데이터를 조회할 수 없습니다.")
    
    def render_management_interface(self):
        """관리 인터페이스 렌더링"""
        st.header("🛠️ 재프롬프팅 데이터 관리")
        
        # 하위 탭 구성
        sub_tab1, sub_tab2, sub_tab3 = st.tabs(["📋 데이터 조회", "🔍 검색", "🗑️ 삭제"])
        
        with sub_tab1:
            self._render_data_list()
        
        with sub_tab2:
            self._render_search_interface()
        
        with sub_tab3:
            self._render_delete_interface()
    
    def _render_data_list(self):
        """데이터 목록 표시"""
        st.write("### 📋 재프롬프팅 질문 목록")
        
        # 페이징 설정
        items_per_page = st.selectbox("페이지당 항목 수", [10, 20, 50, 100], index=1)
        
        # 데이터 조회
        questions = self.db_manager.get_all_reprompting_questions(limit=items_per_page)
        
        if questions:
            # 테이블 헤더
            header_cols = st.columns([1, 2, 3, 3, 2, 2, 1.5])
            with header_cols[0]:
                st.write("**ID**")
            with header_cols[1]:
                st.write("**질문유형**")
            with header_cols[2]:
                st.write("**질문**")
            with header_cols[3]:
                st.write("**맞춤형 프롬프트**")
            with header_cols[4]:
                st.write("**오답요약**")
            with header_cols[5]:
                st.write("**생성일시**")
            with header_cols[6]:
                st.write("**작업**")
            
            st.divider()
            
            # 각 행 표시
            for question in questions:
                # 삭제 확인 상태가 아닌 경우 - 일반 행 표시
                if not st.session_state.get(f'confirm_delete_{question["id"]}', False):
                    cols = st.columns([1, 2, 3, 3, 2, 2, 1.5])
                    
                    with cols[0]:
                        st.write(question['id'])
                    with cols[1]:
                        st.write(question['question_type'])
                    with cols[2]:
                        question_text = question['question'][:50] + '...' if len(question['question']) > 50 else question['question']
                        st.write(question_text)
                    with cols[3]:
                        prompt_text = question['custom_prompt'][:50] + '...' if len(question['custom_prompt']) > 50 else question['custom_prompt']
                        st.write(prompt_text)
                    with cols[4]:
                        summary_text = question['wrong_answer_summary']
                        if summary_text:
                            summary_text = summary_text[:30] + '...' if len(summary_text) > 30 else summary_text
                        else:
                            summary_text = '-'
                        st.write(summary_text)
                    with cols[5]:
                        created_at = pd.to_datetime(question['created_at']).strftime('%Y-%m-%d %H:%M')
                        st.write(created_at)
                    with cols[6]:
                        if st.button("🗑️ 삭제", key=f"delete_{question['id']}", type="secondary", use_container_width=True):
                            st.session_state[f'confirm_delete_{question["id"]}'] = True
                            st.rerun()
                
                # 삭제 확인 상태인 경우 - 확인 행 표시
                else:
                    cols = st.columns([1, 2, 3, 3, 2, 2, 1.5])
                    
                    with cols[0]:
                        st.write(question['id'])
                    with cols[1]:
                        st.write(question['question_type'])
                    with cols[2]:
                        st.warning("삭제하시겠습니까?")
                    with cols[3]:
                        question_preview = question['question'][:30] + '...' if len(question['question']) > 30 else question['question']
                        st.write(f"*{question_preview}*")
                    with cols[4]:
                        st.write("")
                    with cols[5]:
                        st.write("")
                    with cols[6]:
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("✅", key=f"confirm_yes_{question['id']}", help="삭제 확인", use_container_width=True):
                                result = self.db_manager.delete_reprompting_question(question['id'])
                                if result:
                                    st.success(f"ID {question['id']} 삭제됨")
                                    st.session_state[f'confirm_delete_{question["id"]}'] = False
                                    st.rerun()
                                else:
                                    st.error("삭제 실패")
                        with col2:
                            if st.button("❌", key=f"confirm_no_{question['id']}", help="취소", use_container_width=True):
                                st.session_state[f'confirm_delete_{question["id"]}'] = False
                                st.rerun()
                
                # 행 구분선
                st.write("---")
        else:
            st.info("등록된 재프롬프팅 질문이 없습니다.")
    
    def _render_search_interface(self):
        """검색 인터페이스"""
        st.write("### 🔍 질문 검색")
        
        search_query = st.text_input("검색할 질문을 입력하세요")
        
        if search_query:
            # 정확한 매칭 확인
            exact_result = self.db_manager.check_reprompting_question(search_query)
            
            if exact_result['exists']:
                st.success("✅ 정확히 매칭되는 질문을 찾았습니다!")
                st.write("**질문 유형:**", exact_result['question_type'])
                st.write("**원본 질문:**", exact_result['original_question'])
                st.write("**맞춤형 프롬프트:**", exact_result['custom_prompt'])
                st.write("**오답요약:**", exact_result['wrong_answer_summary'])
            else:
                # 유사한 질문 검색
                similar_questions = self.db_manager.find_similar_questions(search_query)
                
                if similar_questions:
                    st.info(f"🔍 유사한 질문 {len(similar_questions)}개를 찾았습니다.")
                    
                    for i, q in enumerate(similar_questions, 1):
                        with st.expander(f"유사 질문 {i}: {q['question'][:50]}..."):
                            st.write("**질문 유형:**", q['question_type'])
                            st.write("**질문:**", q['question'])
                            st.write("**맞춤형 프롬프트:**", q['custom_prompt'])
                            st.write("**오답요약:**", q['wrong_answer_summary'])
                else:
                    st.warning("매칭되는 질문을 찾을 수 없습니다.")
    
    def _render_delete_interface(self):
        """삭제 인터페이스 (ID로 직접 삭제)"""
        st.write("### 🗑️ ID로 직접 삭제")
        
        st.warning("⚠️ 삭제된 데이터는 복구할 수 없습니다.")
        st.info("💡 개별 질문 삭제는 '데이터 조회' 탭에서 각 질문의 삭제 버튼을 사용하는 것이 더 안전합니다.")
        
        question_id = st.number_input("삭제할 질문 ID", min_value=1, step=1)
        
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("🗑️ 삭제", type="secondary"):
                if st.session_state.get('confirm_delete_by_id') != question_id:
                    st.session_state['confirm_delete_by_id'] = question_id
                    st.warning("⚠️ 삭제를 확인하려면 다시 한 번 클릭하세요.")
                else:
                    result = self.db_manager.delete_reprompting_question(question_id)
                    if result:
                        st.success(f"✅ 질문 ID {question_id}가 삭제되었습니다.")
                        st.session_state['confirm_delete_by_id'] = None
                    else:
                        st.error("❌ 삭제에 실패했습니다. ID를 확인해주세요.")
    
    def render_main_interface(self):
        """메인 인터페이스 렌더링"""
        st.set_page_config(
            page_title="질문 재프롬프팅 관리 시스템",
            page_icon="📊",
            layout="wide"
        )
        
        st.title("📊 질문 재프롬프팅 관리 시스템")
        st.markdown("---")
        
        # 탭 구성 (사이드바 대신 탭 방식 사용)
        tab1, tab2, tab3, tab4 = st.tabs([
            "📤 데이터 업로드", 
            "➕ 개별 입력", 
            "📈 통계", 
            "🛠️ 데이터 관리"
        ])
        
        with tab1:
            self.render_upload_interface()
        
        with tab2:
            self.render_individual_input_interface()
        
        with tab3:
            self.render_statistics_interface()
        
        with tab4:
            self.render_management_interface()


# 메인 실행
if __name__ == "__main__":
    upload_manager = ExcelUploadManagerReprompting()
    upload_manager.render_main_interface()