# menu/admin_monitoring.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import os
from collections import defaultdict, Counter
from auth_manager import AuthManager
from utils.monitoring_manager import MonitoringManager
from utils.chart_utils import ChartManager

def main():
    """관리자 모니터링 메인 화면"""
    
    # 관리자 인증 확인
    auth_manager = AuthManager()
    if not auth_manager.is_admin_logged_in():
        st.error("관리자 권한이 필요합니다.")
        st.info("좌측 메뉴에서 '관리자 로그인'을 먼저 진행해주세요.")
        return
    
    # 페이지 설정
    st.set_page_config(
        page_title="관리자 모니터링",
        page_icon="📊",
        layout="wide"
    )
    
    st.title("📊 사용자 활동 모니터링 대시보드")
    
    # 모니터링 매니저 초기화
    monitoring_manager = MonitoringManager()
    chart_manager = ChartManager()
    
    # 상단 검색 조건 영역
    st.markdown("### 🔍 검색 조건")
    
    # 첫 번째 행: 날짜 범위와 모니터링 유형
    col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
    
    with col1:
        start_date = st.date_input(
            "📅 시작 날짜",
            value=datetime.now() - timedelta(days=7),
            max_value=datetime.now()
        )
    
    with col2:
        end_date = st.date_input(
            "📅 종료 날짜", 
            value=datetime.now(),
            max_value=datetime.now()
        )
    
    with col3:
        monitoring_type = st.selectbox(
            "📊 모니터링 유형",
            ["전체", "일별 통계", "월별 통계", "IP별 통계", "질문 유형별 통계"]
        )
    
    with col4:
        st.markdown("<br>", unsafe_allow_html=True)  # 버튼 위치 조정을 위한 여백
        if st.button("🔄 새로고침", use_container_width=True):
            st.rerun()
    
    st.markdown("---")  # 구분선
    
    # 메인 콘텐츠 영역
    try:
        # 로그 데이터 로드
        logs_data = monitoring_manager.get_logs_in_range(start_date, end_date)
        
        if not logs_data:
            st.warning("선택한 기간에 로그 데이터가 없습니다.")
            return
        
        # 탭 구성
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📈 대시보드 개요", 
            "📊 일별/월별 통계", 
            "🌐 IP 분석", 
            "❓ 질문 분석", 
            "📋 상세 로그"
        ])
        
        with tab1:
            show_dashboard_overview(monitoring_manager, logs_data, chart_manager)
        
        with tab2:
            show_time_statistics(monitoring_manager, logs_data, chart_manager)
        
        with tab3:
            show_ip_analysis(monitoring_manager, logs_data, chart_manager)
        
        with tab4:
            show_question_analysis(monitoring_manager, logs_data, chart_manager)
        
        with tab5:
            show_detailed_logs(monitoring_manager, logs_data)
            
    except Exception as e:
        st.error(f"모니터링 데이터 로드 중 오류가 발생했습니다: {str(e)}")
        st.info("시스템 관리자에게 문의하세요.")

def show_dashboard_overview(monitoring_manager, logs_data, chart_manager):
    """대시보드 개요 화면"""
    st.header("📈 대시보드 개요")
    
    # 핵심 지표 카드
    col1, col2, col3, col4 = st.columns(4)
    
    total_queries = len(logs_data)
    unique_ips = len(set(log['ip_address'] for log in logs_data))
    avg_daily_queries = monitoring_manager.calculate_daily_average(logs_data)
    top_query_type = monitoring_manager.get_top_query_type(logs_data)
    
    with col1:
        st.metric(
            label="총 질문 수",
            value=f"{total_queries:,}",
            delta=f"+{monitoring_manager.get_growth_rate(logs_data, 'total')}%"
        )
    
    with col2:
        st.metric(
            label="고유 IP 수",
            value=f"{unique_ips:,}",
            delta=f"+{monitoring_manager.get_growth_rate(logs_data, 'ip')}%"
        )
    
    with col3:
        st.metric(
            label="일평균 질문 수",
            value=f"{avg_daily_queries:.1f}",
            delta=f"+{monitoring_manager.get_growth_rate(logs_data, 'daily')}%"
        )
    
    with col4:
        st.metric(
            label="인기 질문 유형",
            value=top_query_type,
            delta="최다 사용"
        )
    
    st.markdown("---")
    
    # 시간대별 활동 패턴
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📅 일별 활동 패턴")
        daily_stats = monitoring_manager.get_daily_statistics(logs_data)
        
        if daily_stats:
            df_daily = pd.DataFrame(daily_stats)
            fig_daily = px.line(
                df_daily, 
                x='date', 
                y='count',
                title="일별 질문 수 추이",
                markers=True
            )
            fig_daily.update_layout(height=400)
            st.plotly_chart(fig_daily, use_container_width=True)
    
    with col2:
        st.subheader("🕐 시간대별 활동 패턴")
        hourly_stats = monitoring_manager.get_hourly_statistics(logs_data)
        
        if hourly_stats:
            df_hourly = pd.DataFrame(hourly_stats)
            fig_hourly = px.bar(
                df_hourly,
                x='hour',
                y='count',
                title="시간대별 질문 수 분포"
            )
            fig_hourly.update_layout(height=400)
            st.plotly_chart(fig_hourly, use_container_width=True)

def show_time_statistics(monitoring_manager, logs_data, chart_manager):
    """일별/월별 통계 화면"""
    st.header("📊 일별/월별 통계")
    
    # 통계 기간 선택
    period_type = st.selectbox("통계 기간", ["일별", "주별", "월별"])
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader(f"📈 {period_type} 질문 수 통계")
        
        if period_type == "일별":
            time_stats = monitoring_manager.get_daily_statistics(logs_data)
        elif period_type == "주별":
            time_stats = monitoring_manager.get_weekly_statistics(logs_data)
        else:
            time_stats = monitoring_manager.get_monthly_statistics(logs_data)
        
        if time_stats:
            df_time = pd.DataFrame(time_stats)
            
            fig = px.line(
                df_time,
                x='date' if period_type == "일별" else 'period',
                y='count',
                title=f"{period_type} 질문 수 추이",
                markers=True
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # 통계 테이블
            st.subheader("📋 상세 통계")
            df_display = df_time.copy()
            df_display['증감률'] = df_display['count'].pct_change().fillna(0) * 100
            df_display['증감률'] = df_display['증감률'].round(2)
            st.dataframe(df_display, use_container_width=True)
    
    with col2:
        st.subheader(f"📊 {period_type} IP 수 통계")
        
        if period_type == "일별":
            ip_stats = monitoring_manager.get_daily_ip_statistics(logs_data)
        elif period_type == "주별":
            ip_stats = monitoring_manager.get_weekly_ip_statistics(logs_data)
        else:
            ip_stats = monitoring_manager.get_monthly_ip_statistics(logs_data)
        
        if ip_stats:
            df_ip = pd.DataFrame(ip_stats)
            
            fig_ip = px.bar(
                df_ip,
                x='date' if period_type == "일별" else 'period',
                y='unique_ips',
                title=f"{period_type} 고유 IP 수"
            )
            st.plotly_chart(fig_ip, use_container_width=True)
            
            # IP 통계 테이블
            st.subheader("📋 IP 통계")
            st.dataframe(df_ip, use_container_width=True)

def show_ip_analysis(monitoring_manager, logs_data, chart_manager):
    """IP 분석 화면"""
    st.header("🌐 IP 분석")
    
    # IP 통계 계산
    ip_stats = monitoring_manager.get_ip_statistics(logs_data)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 상위 IP 주소")
        
        top_ips = sorted(ip_stats.items(), key=lambda x: x[1]['count'], reverse=True)[:20]
        
        if top_ips:
            df_top_ips = pd.DataFrame([
                {
                    'IP 주소': ip,
                    '질문 수': data['count'],
                    '첫 접속': data['first_seen'],
                    '마지막 접속': data['last_seen'],
                    '질문 유형': ', '.join(data['query_types'][:3])
                }
                for ip, data in top_ips
            ])
            
            # 막대 차트
            fig_ip = px.bar(
                df_top_ips.head(10),
                x='질문 수',
                y='IP 주소',
                orientation='h',
                title="상위 10개 IP 주소별 질문 수"
            )
            st.plotly_chart(fig_ip, use_container_width=True)
            
            # 상세 테이블
            st.dataframe(df_top_ips, use_container_width=True)
    
    with col2:
        st.subheader("🔍 IP 활동 패턴")
        
        # IP별 활동 시간 분석
        ip_activity = monitoring_manager.get_ip_activity_patterns(logs_data)
        
        if ip_activity:
            # 시간대별 IP 분포
            hourly_ip_count = defaultdict(int)
            for log in logs_data:
                hour = datetime.fromisoformat(log['timestamp']).hour
                hourly_ip_count[hour] += 1
            
            df_hourly_ip = pd.DataFrame([
                {'시간': hour, '접속 수': count}
                for hour, count in sorted(hourly_ip_count.items())
            ])
            
            fig_hourly = px.line(
                df_hourly_ip,
                x='시간',
                y='접속 수',
                title="시간대별 IP 접속 패턴",
                markers=True
            )
            st.plotly_chart(fig_hourly, use_container_width=True)
        
        # 의심스러운 IP 탐지
        st.subheader("⚠️ 의심스러운 활동")
        suspicious_ips = monitoring_manager.detect_suspicious_ips(logs_data)
        
        if suspicious_ips:
            df_suspicious = pd.DataFrame([
                {
                    'IP 주소': ip,
                    '의심 사유': data['reason'],
                    '활동 점수': data['score'],
                    '질문 수': data['count']
                }
                for ip, data in suspicious_ips.items()
            ])
            st.dataframe(df_suspicious, use_container_width=True)
        else:
            st.success("의심스러운 활동이 감지되지 않았습니다.")

def show_question_analysis(monitoring_manager, logs_data, chart_manager):
    """질문 분석 화면"""
    st.header("❓ 질문 분석")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 질문 유형별 분포")
        
        query_type_stats = monitoring_manager.get_query_type_statistics(logs_data)
        
        if query_type_stats:
            df_types = pd.DataFrame([
                {'질문 유형': qtype, '건수': count}
                for qtype, count in query_type_stats.items()
            ])
            
            # 파이 차트
            fig_pie = px.pie(
                df_types,
                values='건수',
                names='질문 유형',
                title="질문 유형별 비율"
            )
            st.plotly_chart(fig_pie, use_container_width=True)
    
    with col2:
        st.subheader("📈 인기 키워드")
        
        keywords = monitoring_manager.extract_popular_keywords(logs_data)
        
        if keywords:
            df_keywords = pd.DataFrame([
                {'키워드': keyword, '빈도': count}
                for keyword, count in keywords[:20]
            ])
            
            # 워드 클라우드 대신 막대 차트
            fig_keywords = px.bar(
                df_keywords.head(10),
                x='빈도',
                y='키워드',
                orientation='h',
                title="상위 10개 인기 키워드"
            )
            st.plotly_chart(fig_keywords, use_container_width=True)
    
    # 질문 길이 분석
    st.subheader("📏 질문 길이 분석")
    
    col3, col4 = st.columns(2)
    
    with col3:
        length_stats = monitoring_manager.get_question_length_statistics(logs_data)
        
        if length_stats:
            df_length = pd.DataFrame([
                {'길이 구간': range_name, '건수': count}
                for range_name, count in length_stats.items()
            ])
            
            fig_length = px.bar(
                df_length,
                x='길이 구간',
                y='건수',
                title="질문 길이별 분포"
            )
            st.plotly_chart(fig_length, use_container_width=True)
    
    with col4:
        # 응답 시간 분석
        response_time_stats = monitoring_manager.get_response_time_statistics(logs_data)
        
        if response_time_stats:
            df_response = pd.DataFrame([
                {'응답 시간 구간': range_name, '건수': count}
                for range_name, count in response_time_stats.items()
            ])
            
            fig_response = px.bar(
                df_response,
                x='응답 시간 구간',
                y='건수',
                title="응답 시간별 분포"
            )
            st.plotly_chart(fig_response, use_container_width=True)

def show_detailed_logs(monitoring_manager, logs_data):
    """상세 로그 화면"""
    st.header("📋 상세 로그")
    
    # 필터 옵션
    col1, col2, col3 = st.columns(3)
    
    with col1:
        ip_filter = st.text_input("IP 주소 필터", placeholder="예: 192.168.1.1")
    
    with col2:
        query_type_filter = st.selectbox(
            "질문 유형 필터",
            ["전체", "repair", "cause", "similar", "inquiry", "default"]
        )
    
    with col3:
        search_keyword = st.text_input("질문 내용 검색", placeholder="키워드 입력")
    
    # 로그 필터링
    filtered_logs = logs_data
    
    if ip_filter:
        filtered_logs = [log for log in filtered_logs if ip_filter in log['ip_address']]
    
    if query_type_filter != "전체":
        filtered_logs = [log for log in filtered_logs if log.get('query_type') == query_type_filter]
    
    if search_keyword:
        filtered_logs = [log for log in filtered_logs if search_keyword.lower() in log['question'].lower()]
    
    st.info(f"총 {len(filtered_logs)}개의 로그가 조회되었습니다.")
    
    # 페이지네이션
    page_size = 50
    total_pages = (len(filtered_logs) + page_size - 1) // page_size
    
    if total_pages > 1:
        page = st.selectbox("페이지", range(1, total_pages + 1))
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_logs = filtered_logs[start_idx:end_idx]
    else:
        page_logs = filtered_logs
    
    # 로그 테이블
    if page_logs:
        df_logs = pd.DataFrame([
            {
                '시간': log['timestamp'],
                'IP 주소': log['ip_address'],
                '질문 유형': log.get('query_type', 'unknown'),
                '질문 내용': log['question'][:100] + ('...' if len(log['question']) > 100 else ''),
                '응답 시간(초)': log.get('response_time', 0),
                '문서 수': log.get('document_count', 0)
            }
            for log in page_logs
        ])
        
        st.dataframe(df_logs, use_container_width=True)
        
        # 로그 다운로드
        if st.button("📥 로그 다운로드 (CSV)"):
            csv = df_logs.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="다운로드",
                data=csv,
                file_name=f"monitoring_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    else:
        st.warning("조회된 로그가 없습니다.")

if __name__ == "__main__":
    main()