import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
import os
import urllib.request
import platform
from datetime import datetime
import re

def setup_korean_font():
    """한글 폰트 설정 함수 - 개선된 버전"""
    try:
        # matplotlib 기본 설정
        plt.rcParams['axes.unicode_minus'] = False
        
        # 시스템별 폰트 경로 시도
        system = platform.system()
        
        # 기본 폰트들 시도
        fallback_fonts = ['DejaVu Sans', 'Arial', 'sans-serif']
        
        if system == 'Windows':
            font_candidates = [
                'Malgun Gothic', 'Microsoft YaHei', 'SimHei',
                'C:/Windows/Fonts/malgun.ttf',
                'C:/Windows/Fonts/gulim.ttc'
            ]
        elif system == 'Darwin':  # macOS
            font_candidates = [
                'AppleGothic', 'Helvetica', 'Arial Unicode MS',
                '/System/Library/Fonts/AppleGothic.ttf'
            ]
        else:  # Linux and others
            font_candidates = [
                'NanumGothic', 'DejaVu Sans', 'Liberation Sans',
                '/usr/share/fonts/truetype/nanum/NanumGothic.ttf'
            ]
        
        # 폰트 설정 시도
        for font in font_candidates:
            try:
                if font.endswith(('.ttf', '.ttc', '.otf')):
                    # 파일 경로인 경우
                    if os.path.exists(font):
                        fm.fontManager.addfont(font)
                        prop = fm.FontProperties(fname=font)
                        plt.rcParams['font.family'] = prop.get_name()
                        print(f"폰트 설정 성공: {prop.get_name()}")
                        return prop.get_name()
                else:
                    # 폰트 이름인 경우
                    plt.rcParams['font.family'] = font
                    # 테스트 차트로 확인
                    fig, ax = plt.subplots(figsize=(1, 1))
                    ax.text(0.5, 0.5, '테스트', fontsize=10)
                    plt.close(fig)
                    print(f"폰트 설정 성공: {font}")
                    return font
            except Exception as e:
                continue
        
        # 모든 폰트 설정 실패시 기본 폰트 사용
        plt.rcParams['font.family'] = 'DejaVu Sans'
        print("기본 폰트 사용: DejaVu Sans")
        return 'DejaVu Sans'
        
    except Exception as e:
        print(f"폰트 설정 중 오류: {e}")
        plt.rcParams['font.family'] = 'DejaVu Sans'
        plt.rcParams['axes.unicode_minus'] = False
        return 'DejaVu Sans'

class ChartManager:
    """차트 생성 및 관리 클래스 - 통계-차트 일치성 보장"""
    
    def __init__(self):
        """ChartManager 초기화 - 안정성 강화"""
        # 폰트 설정
        self.font_name = setup_korean_font()
        
        # 색상 팔레트
        self.colors = ['#4CAF50', '#2196F3', '#FF9800', '#F44336', '#9C27B0', 
                    '#00BCD4', '#FFEB3B', '#795548', '#607D8B', '#E91E63']
        
        # 차트 크기 설정
        self.chart_width_px = 850
        self.chart_height_px = 600
        self.pie_size_px = 700
        
        self.dpi = 100
        self.default_figsize = (self.chart_width_px / self.dpi, self.chart_height_px / self.dpi)
        self.pie_figsize = (self.pie_size_px / self.dpi, self.pie_size_px / self.dpi)
        
        # matplotlib 기본 설정 - 안전하게 처리
        try:
            plt.style.use('default')
            plt.rcParams['figure.facecolor'] = 'white'
            plt.rcParams['axes.facecolor'] = 'white'
            plt.rcParams['savefig.facecolor'] = 'white'
            plt.rcParams['font.size'] = 10
            plt.rcParams['axes.unicode_minus'] = False
        except Exception as e:
            print(f"matplotlib 설정 중 오류: {e}")
        
        # 폰트 테스트
        self._test_korean_font()
        
    def _test_korean_font(self):
        """한글 폰트 정상 작동 테스트"""
        try:
            fig, ax = plt.subplots(figsize=(1, 1))
            ax.text(0.5, 0.5, '한글테스트', fontsize=10, ha='center')
            plt.close(fig)
            print(f"한글 폰트 테스트 성공: {self.font_name}")
        except Exception as e:
            print(f"한글 폰트 테스트 실패: {e}")
            self.font_name = setup_korean_font()

    def _sort_chart_data(self, data, title=""):
        """차트 데이터 정렬 - 년도는 시간순, 나머지는 값 순서로"""
        if not data:
            return data
        
        # 년도 데이터인지 확인
        is_year_data = self._is_year_data(data, title)
        
        if is_year_data:
            # 년도 데이터는 오름차순 정렬 (2022 -> 2023 -> 2024 -> 2025)
            try:
                sorted_items = sorted(data.items(), key=lambda x: int(str(x[0]).replace('년', '')))
                print(f"DEBUG: 년도 데이터 오름차순 정렬 적용: {sorted_items}")
            except:
                # 년도 변환 실패시 원본 순서 유지
                sorted_items = list(data.items())
        else:
            # 월 데이터 확인
            is_month_data = self._is_month_data(data, title)
            if is_month_data:
                # 월 데이터는 1월부터 12월 순서로 정렬
                month_order = {'1월': 1, '2월': 2, '3월': 3, '4월': 4, '5월': 5, '6월': 6,
                              '7월': 7, '8월': 8, '9월': 9, '10월': 10, '11월': 11, '12월': 12}
                try:
                    sorted_items = sorted(data.items(), 
                                        key=lambda x: month_order.get(x[0], 99))
                    print(f"DEBUG: 월 데이터 순서 정렬 적용: {sorted_items}")
                except:
                    sorted_items = list(data.items())
            else:
                # 요일 데이터 확인
                is_weekday_data = self._is_weekday_data(data, title)
                if is_weekday_data:
                    # 요일 데이터는 월요일부터 일요일 순서로 정렬
                    weekday_order = {'월요일': 1, '화요일': 2, '수요일': 3, '목요일': 4, 
                                   '금요일': 5, '토요일': 6, '일요일': 7, '평일': 8, '주말': 9}
                    try:
                        sorted_items = sorted(data.items(), 
                                            key=lambda x: weekday_order.get(x[0], 99))
                        print(f"DEBUG: 요일 데이터 순서 정렬 적용: {sorted_items}")
                    except:
                        sorted_items = list(data.items())
                else:
                    # 기타 데이터는 값 기준 내림차순 정렬 (큰 값부터)
                    sorted_items = sorted(data.items(), key=lambda x: x[1], reverse=True)
                    print(f"DEBUG: 일반 데이터 값 기준 내림차순 정렬 적용: {sorted_items}")
        
        return dict(sorted_items)

    def _is_year_data(self, data, title):
        """년도 데이터인지 확인"""
        # 제목에 년도 관련 키워드가 있거나
        if any(keyword in title.lower() for keyword in ['년도', '연도', 'year', '년별']):
            return True
        
        # 데이터 키가 모두 년도 형태인지 확인
        year_pattern = re.compile(r'^(19|20)\d{2}년?$')
        keys = list(data.keys())
        
        if len(keys) >= 2:  # 최소 2개 이상의 데이터가 있을 때만 판단
            year_count = sum(1 for key in keys if year_pattern.match(str(key)))
            return year_count >= len(keys) * 0.7  # 70% 이상이 년도 형태면 년도 데이터로 판단
        
        return False

    def _is_month_data(self, data, title):
        """월 데이터인지 확인"""
        # 제목에 월 관련 키워드가 있거나
        if any(keyword in title.lower() for keyword in ['월별', 'month', '월']):
            return True
        
        # 데이터 키가 모두 월 형태인지 확인
        month_pattern = re.compile(r'^(1[0-2]|[1-9])월?$')
        keys = list(data.keys())
        
        if len(keys) >= 2:
            month_count = sum(1 for key in keys if month_pattern.match(str(key)))
            return month_count >= len(keys) * 0.7
        
        return False

    def _is_weekday_data(self, data, title):
        """요일 데이터인지 확인"""
        # 제목에 요일 관련 키워드가 있거나
        if any(keyword in title.lower() for keyword in ['요일', 'week', '주간', '평일', '주말']):
            return True
        
        # 데이터 키가 요일 형태인지 확인
        weekdays = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일', '평일', '주말']
        keys = list(data.keys())
        
        if len(keys) >= 2:
            weekday_count = sum(1 for key in keys if str(key) in weekdays)
            return weekday_count >= len(keys) * 0.7
        
        return False
    
    def create_chart(self, chart_type, chart_data, title="장애 통계", color_palette=None):
        """차트 생성 - 안정성 강화 및 정렬 기능 추가"""
        print(f"DEBUG: Creating chart - type: {chart_type}, data: {chart_data}")
        
        # 폰트 재설정 (안전장치)
        try:
            if not plt.rcParams.get('font.family') or plt.rcParams.get('font.family') == ['sans-serif']:
                self.font_name = setup_korean_font()
        except Exception as e:
            print(f"DEBUG: Font setup warning: {e}")
            pass
        
        # 데이터 유효성 검사
        if not chart_data:
            print("DEBUG: No chart data provided")
            return self._create_no_data_chart(title)
        
        if not isinstance(chart_data, dict):
            print(f"DEBUG: Invalid data type: {type(chart_data)}")
            return self._create_no_data_chart(title)
        
        # 빈 값 제거 및 데이터 정리
        clean_data = {}
        for k, v in chart_data.items():
            try:
                if v is not None and isinstance(v, (int, float)) and v > 0:
                    clean_data[str(k)] = float(v)
            except Exception as e:
                print(f"DEBUG: Skipping invalid data point {k}:{v} - {e}")
                continue
        
        if not clean_data:
            print("DEBUG: No valid data after cleaning")
            return self._create_no_data_chart(title)
        
        # 데이터 정렬 적용
        sorted_data = self._sort_chart_data(clean_data, title)
        print(f"DEBUG: Sorted data: {sorted_data}")
        
        try:
            # 차트 타입별 처리
            chart_type = str(chart_type).lower().strip()
            
            if chart_type == 'no_data':
                return self._create_no_data_chart(title)
            elif chart_type == 'line':
                return self._create_line_chart(sorted_data, title)
            elif chart_type == 'pie':
                return self._create_pie_chart(sorted_data, title)
            elif chart_type == 'horizontal_bar':
                return self._create_horizontal_bar_chart(sorted_data, title)
            else:
                return self._create_bar_chart(sorted_data, title)
                
        except Exception as e:
            print(f"DEBUG: Chart creation failed: {e}")
            import traceback
            traceback.print_exc()
            # 실패시 기본 차트 시도
            return self._create_simple_chart(sorted_data, title)
    
    def _get_chart_unit(self, title, values):
        """차트 단위 결정"""
        is_time = '시간' in title or any(v > 100 for v in values if isinstance(v, (int, float)))
        return '분' if is_time else '건'
    
    def _style_axis(self, ax, title, xlabel, ylabel, categories):
        """축 스타일링"""
        ax.set_title(title, fontsize=18, fontweight='bold', pad=25, color='#2c3e50')
        ax.set_xlabel(xlabel, fontsize=13, fontweight='bold', color='#34495e')
        ax.set_ylabel(ylabel, fontsize=13, fontweight='bold', color='#34495e')
        
        if len(categories) > 6 or any(len(str(c)) > 8 for c in categories):
            plt.xticks(rotation=45, ha='right')
        
        ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
        ax.set_axisbelow(True)
    
    def _create_bar_chart(self, data, title):
        """기본 세로 막대차트 생성 - 안정성 강화"""
        try:
            print(f"DEBUG: _create_bar_chart called with data: {data}")
            
            if not data or all(v == 0 for v in data.values()):
                return self._create_no_data_chart(title)
            
            fig, ax = plt.subplots(figsize=self.default_figsize, dpi=self.dpi)
            
            categories = list(data.keys())
            values = list(data.values())
            print(f"DEBUG: Categories: {categories}, Values: {values}")
            
            if not values or all(v == 0 for v in values):
                plt.close(fig)
                return self._create_no_data_chart(title)
            
            colors = (self.colors * (len(categories) // len(self.colors) + 1))[:len(categories)]
            bars = ax.bar(categories, values, color=colors, alpha=0.8, edgecolor='white', linewidth=1.5)
            
            unit = self._get_chart_unit(title, values)
            max_value = max(values) if values else 1
            
            # 값 라벨 추가
            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    ax.text(bar.get_x() + bar.get_width()/2., height + max_value*0.01,
                        f'{int(height)}{unit}', ha='center', va='bottom', 
                        fontweight='bold', fontsize=10, color='#2c3e50')
            
            ylabel = f'장애 시간({unit})' if unit == '분' else '장애 건수'
            self._style_axis(ax, title, '구분', ylabel, categories)
            
            if max_value > 0:
                ax.set_ylim(0, max_value * 1.15)
            
            plt.tight_layout()
            print("DEBUG: Bar chart created successfully")
            return fig
            
        except Exception as e:
            print(f"DEBUG: Bar chart creation failed: {e}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            return self._create_simple_chart(data, title)
    
    def _create_line_chart(self, data, title):
        """선 그래프 생성"""
        try:
            fig, ax = plt.subplots(figsize=self.default_figsize, dpi=self.dpi)
            categories, values = list(data.keys()), list(data.values())
            print(f"DEBUG: Creating line chart with categories: {categories}, values: {values}")
            
            ax.plot(categories, values, marker='o', linewidth=3, markersize=8, 
                   color=self.colors[0], markerfacecolor=self.colors[1], 
                   markeredgecolor='white', markeredgewidth=2)
            ax.fill_between(categories, values, alpha=0.3, color=self.colors[0])
            
            unit = self._get_chart_unit(title, values)
            for x, y in zip(categories, values):
                ax.annotate(f'{int(y)}{unit}', (x, y), textcoords="offset points", 
                           xytext=(0,15), ha='center', fontweight='bold', 
                           fontsize=10, color='#2c3e50')
            
            ylabel = f'장애 시간({unit})' if unit == '분' else '장애 건수'
            self._style_axis(ax, title, '기간', ylabel, categories)
            
            plt.tight_layout()
            return fig
        except Exception as e:
            print(f"DEBUG: Line chart creation failed: {e}")
            return self._create_bar_chart(data, title)
    
    def _create_horizontal_bar_chart(self, data, title):
        """가로 막대차트 생성"""
        try:
            print(f"DEBUG: _create_horizontal_bar_chart called with data: {data}")
            limited_data = dict(list(data.items())[:10])
            
            if not limited_data or all(v == 0 for v in limited_data.values()):
                return self._create_no_data_chart(title)
            
            fig, ax = plt.subplots(figsize=self.default_figsize, dpi=self.dpi)
            
            categories = list(limited_data.keys())
            values = list(limited_data.values())
            colors = (self.colors * (len(categories) // len(self.colors) + 1))[:len(categories)]
            
            y_pos = np.arange(len(categories))
            bars = ax.barh(y_pos, values, color=colors, alpha=0.8, edgecolor='white', linewidth=1.5)
            
            unit = self._get_chart_unit(title, values)
            max_value = max(values) if values else 1
            
            for bar, value in zip(bars, values):
                if value > 0:
                    ax.text(bar.get_width() + max_value*0.01, bar.get_y() + bar.get_height()/2.,
                           f'{int(value)}{unit}', ha='left', va='center', 
                           fontweight='bold', fontsize=10, color='#2c3e50')
            
            ax.set_title(title, fontsize=18, fontweight='bold', pad=25, color='#2c3e50')
            xlabel = f'장애 시간({unit})' if unit == '분' else '장애 건수'
            ax.set_xlabel(xlabel, fontsize=13, fontweight='bold', color='#34495e')
            ax.set_ylabel('카테고리', fontsize=13, fontweight='bold', color='#34495e')
            ax.set_yticks(y_pos)
            ax.set_yticklabels(categories)
            ax.grid(True, alpha=0.3, axis='x', linestyle='--', linewidth=0.5)
            ax.set_axisbelow(True)
            
            if max_value > 0:
                ax.set_xlim(0, max_value * 1.15)
            
            plt.tight_layout()
            print("DEBUG: Horizontal bar chart created successfully")
            return fig
            
        except Exception as e:
            print(f"DEBUG: Horizontal bar chart creation failed: {e}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            return self._create_bar_chart(data, title)
    
    def _create_pie_chart(self, data, title):
        """원형 그래프 생성"""
        try:
            print(f"DEBUG: _create_pie_chart called with data: {data}")
            
            if not data or all(v == 0 for v in data.values()):
                return self._create_no_data_chart(title)
            
            fig, ax = plt.subplots(figsize=self.pie_figsize, dpi=self.dpi)
            labels = list(data.keys())
            sizes = list(data.values())
            total = sum(sizes)
            
            if total <= 0:
                plt.close(fig)
                return self._create_no_data_chart(title)
            
            # 5% 미만 항목들은 '기타'로 묶기
            threshold = total * 0.05
            new_labels, new_sizes = [], []
            others_sum = 0
            
            for label, size in zip(labels, sizes):
                if size >= threshold:
                    new_labels.append(label)
                    new_sizes.append(size)
                else:
                    others_sum += size
            
            if others_sum > 0:
                new_labels.append('기타')
                new_sizes.append(others_sum)
            
            colors = self.colors[:len(new_labels)]
            
            def make_autopct(values):
                def my_autopct(pct):
                    return f'{pct:.1f}%' if pct > 3 else ''
                return my_autopct
            
            wedges, texts, autotexts = ax.pie(new_sizes, labels=new_labels, colors=colors,
                                             autopct=make_autopct(new_sizes), startangle=90,
                                             textprops={'fontweight': 'bold', 'fontsize': 11})
            
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontsize(10)
                autotext.set_fontweight('bold')
            
            for text in texts:
                text.set_fontsize(10)
                text.set_color('#2c3e50')
            
            ax.set_title(title, fontsize=18, fontweight='bold', pad=30, color='#2c3e50')
            plt.tight_layout()
            print("DEBUG: Pie chart created successfully")
            return fig
            
        except Exception as e:
            print(f"DEBUG: Pie chart creation failed: {e}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            return self._create_bar_chart(data, title)
    
    def _create_no_data_chart(self, title):
        """데이터가 없을 때의 기본 차트"""
        try:
            fig, ax = plt.subplots(figsize=self.default_figsize, dpi=self.dpi)
            
            ax.text(0.5, 0.5, '조건에 맞는 데이터가 없습니다', 
                    ha='center', va='center', fontsize=16, 
                    transform=ax.transAxes, color='#7f8c8d',
                    bbox=dict(boxstyle="round,pad=0.3", facecolor='lightblue', alpha=0.3))
            
            ax.set_title(title, fontsize=18, fontweight='bold', pad=25, color='#2c3e50')
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
            
            plt.tight_layout()
            return fig
            
        except Exception as e:
            print(f"DEBUG: No data chart creation failed: {e}")
            return None
    
    def _create_simple_chart(self, data, title):
        """최후의 수단 - 가장 단순한 차트"""
        try:
            print("DEBUG: Creating simple fallback chart")
            fig, ax = plt.subplots(figsize=(8, 6))
            
            if data and len(data) > 0:
                # 데이터 준비
                categories = list(data.keys())[:5]  # 최대 5개만
                values = [float(v) for v in list(data.values())[:5]]  # float 변환
                
                if any(v > 0 for v in values):
                    # 간단한 막대 차트
                    bars = ax.bar(range(len(categories)), values, color='skyblue', alpha=0.7)
                    
                    # 값 표시
                    unit = '분' if '시간' in title or any(v > 100 for v in values) else '건'
                    for i, (bar, v) in enumerate(zip(bars, values)):
                        if v > 0:
                            ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + max(values)*0.01, 
                                   f'{int(v)}{unit}', ha='center', va='bottom')
                    
                    # 축 설정
                    ax.set_xticks(range(len(categories)))
                    ax.set_xticklabels(categories)
                    ax.set_title(title, fontsize=14, fontweight='bold')
                    ax.set_ylabel(f'시간({unit})' if unit == '분' else '건수')
                    
                    # 긴 레이블 회전
                    if any(len(str(c)) > 8 for c in categories):
                        plt.xticks(rotation=45, ha='right')
                else:
                    # 데이터가 모두 0인 경우
                    ax.text(0.5, 0.5, '유효한 데이터가 없습니다', ha='center', va='center', 
                           transform=ax.transAxes, fontsize=14)
                    ax.set_title(title, fontsize=14, fontweight='bold')
                    ax.axis('off')
            else:
                # 데이터가 없는 경우
                ax.text(0.5, 0.5, '데이터가 없습니다', ha='center', va='center', 
                       transform=ax.transAxes, fontsize=14)
                ax.set_title(title, fontsize=14, fontweight='bold')
                ax.axis('off')
            
            plt.tight_layout()
            print("DEBUG: Simple chart created successfully")
            return fig
            
        except Exception as e:
            print(f"DEBUG: Simple chart creation failed: {e}")
            # 최종 fallback
            try:
                fig, ax = plt.subplots(figsize=(6, 4))
                ax.text(0.5, 0.5, '차트 생성 실패', ha='center', va='center', 
                       transform=ax.transAxes, fontsize=12)
                ax.set_title(title if title else '차트', fontsize=12)
                ax.axis('off')
                plt.tight_layout()
                return fig
            except:
                return None

    def display_chart_with_data(self, chart, chart_data, chart_type, query=""):
        """차트와 데이터 테이블 표시 - 안정성 강화"""
        
        if not chart_data:
            st.warning("차트를 생성할 데이터가 없습니다.")
            return
        
        # 세션 상태에 데이터 안정적으로 저장
        chart_session_key = "stable_chart_data"
        
        try:
            if (chart_session_key not in st.session_state or 
                st.session_state[chart_session_key] != chart_data):
                st.session_state[chart_session_key] = dict(chart_data)  # dict로 복사
                st.session_state["stable_chart_query"] = str(query)
        except Exception as e:
            print(f"DEBUG: Session state error: {e}")
            st.session_state[chart_session_key] = dict(chart_data)
            st.session_state["stable_chart_query"] = str(query)
        
        stable_data = st.session_state[chart_session_key]
        stable_query = st.session_state.get("stable_chart_query", query)
        
        # 차트 표시 - 70% 가로 크기
        if chart is not None:
            try:
                col_chart = st.columns([0.15, 0.7, 0.15])
                with col_chart[1]:
                    st.pyplot(chart, use_container_width=False, clear_figure=True)
                print("DEBUG: Chart displayed successfully")
            except Exception as e:
                print(f"DEBUG: Failed to display chart: {e}")
                st.error(f"차트 표시 중 오류가 발생했습니다: {str(e)}")
            finally:
                try:
                    plt.close(chart)
                except:
                    pass
        else:
            st.warning("차트를 생성할 수 없습니다.")
        
        # 데이터 테이블 표시 (기존 로직 유지)
        st.markdown("---")
        with st.expander("📊 상세 데이터 보기"):
            try:
                if stable_data:
                    is_time_chart = '시간' in stable_query.lower() or any(val > 100 for val in stable_data.values() if isinstance(val, (int, float)))
                    value_column = '시간(분)' if is_time_chart else '건수'
                    
                    df = pd.DataFrame(list(stable_data.items()), columns=['구분', value_column])
                    
                    total = df[value_column].sum()
                    if total > 0:
                        df['비율(%)'] = (df[value_column] / total * 100).round(1)
                    
                    st.dataframe(df, use_container_width=True)
                    
                    # 요약 통계
                    col1, col2, col3 = st.columns(3)
                    total_label = f"총 {value_column.split('(')[0]}"
                    total_unit = '분' if is_time_chart else '건'
                    
                    with col1:
                        st.metric(total_label, f"{total:,}{total_unit}")
                    with col2:
                        st.metric("평균", f"{df[value_column].mean():.1f}{total_unit}")  
                    with col3:
                        st.metric("항목 수", f"{len(df)}개")
                    
                    # CSV 다운로드
                    try:
                        csv = df.to_csv(index=False, encoding='utf-8-sig')
                        filename_suffix = "장애시간통계" if is_time_chart else "장애건수통계"
                        st.download_button(
                            label="📥 CSV 다운로드",
                            data=csv,
                            file_name=f"{filename_suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                    except Exception as e:
                        print(f"DEBUG: CSV download error: {e}")
                        
            except Exception as e:
                print(f"DEBUG: Data table display error: {e}")
                st.error("데이터 테이블 표시 중 오류가 발생했습니다.")