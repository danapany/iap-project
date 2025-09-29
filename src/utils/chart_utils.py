import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns
import numpy as np
import re
import os
import urllib.request
import platform
from datetime import datetime
from collections import Counter

def setup_korean_font():
    """한글 폰트 설정 함수 - Azure 웹앱 환경 최적화"""
    try:
        fonts_dir = "./fonts"
        if not os.path.exists(fonts_dir):
            os.makedirs(fonts_dir)
        
        font_file_path = os.path.join(fonts_dir, "NanumGothic.ttf")
        
        if not os.path.exists(font_file_path):
            try:
                font_url = "https://github.com/naver/nanumfont/raw/master/fonts/NanumGothic.ttf"
                urllib.request.urlretrieve(font_url, font_file_path)
                print("한글 폰트를 다운로드했습니다.")
            except Exception as e:
                print(f"폰트 다운로드 실패: {e}")
        
        if os.path.exists(font_file_path):
            try:
                fm.fontManager.addfont(font_file_path)
                font_prop = fm.FontProperties(fname=font_file_path)
                font_name = font_prop.get_name()
                
                plt.rcParams['font.family'] = font_name
                plt.rcParams['axes.unicode_minus'] = False
                
                print(f"다운로드된 폰트 설정 완료: {font_name}")
                return font_name
            except Exception as e:
                print(f"다운로드된 폰트 설정 실패: {e}")
        
        if platform.system() == 'Windows':
            font_paths = [
                "C:/Windows/Fonts/malgun.ttf",
                "C:/Windows/Fonts/gulim.ttc",
                "C:/Windows/Fonts/batang.ttc"
            ]
        elif platform.system() == 'Darwin':
            font_paths = [
                "/System/Library/Fonts/AppleGothic.ttf",
                "/Library/Fonts/AppleGothic.ttf"
            ]
        else:
            font_paths = [
                "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                font_file_path
            ]
        
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    if font_path.endswith('.ttf') or font_path.endswith('.ttc'):
                        fm.fontManager.addfont(font_path)
                    font_prop = fm.FontProperties(fname=font_path)
                    font_name = font_prop.get_name()
                    plt.rcParams['font.family'] = font_name
                    plt.rcParams['axes.unicode_minus'] = False
                    print(f"시스템 폰트 설정 완료: {font_name}")
                    return font_name
                except Exception:
                    continue
        
        korean_fonts = []
        for font in fm.fontManager.ttflist:
            if any(keyword in font.name.lower() for keyword in ['nanum', 'malgun', 'gothic', 'batang', 'gulim']):
                korean_fonts.append(font.name)
        
        if korean_fonts:
            font_name = korean_fonts[0]
            plt.rcParams['font.family'] = font_name
            plt.rcParams['axes.unicode_minus'] = False
            print(f"검색된 한글 폰트 설정 완료: {font_name}")
            return font_name
        
        fallback_fonts = ['DejaVu Sans', 'Arial Unicode MS', 'Lucida Grande']
        for font in fallback_fonts:
            try:
                plt.rcParams['font.family'] = font
                plt.rcParams['axes.unicode_minus'] = False
                print(f"Fallback 폰트 설정 완료: {font}")
                return font
            except:
                continue
                
        plt.rcParams['font.family'] = 'DejaVu Sans'
        plt.rcParams['axes.unicode_minus'] = False
        print("기본 폰트 설정 적용: DejaVu Sans")
        return 'DejaVu Sans'
        
    except Exception as e:
        plt.rcParams['font.family'] = 'DejaVu Sans'
        plt.rcParams['axes.unicode_minus'] = False
        print(f"폰트 설정 중 오류 발생: {e}")
        return 'DejaVu Sans'

class ChartManager:
    """차트 생성 및 관리 클래스 - 통계-차트 일치성 보장"""
    
    def __init__(self):
        self.font_name = setup_korean_font()
        
        self.colors = ['#4CAF50', '#2196F3', '#FF9800', '#F44336', '#9C27B0', 
                      '#00BCD4', '#FFEB3B', '#795548', '#607D8B', '#E91E63']
        
        self.chart_width_px = 850
        self.chart_height_px = 600
        self.pie_size_px = 700
        
        self.dpi = 100
        self.default_figsize = (self.chart_width_px / self.dpi, self.chart_height_px / self.dpi)
        self.pie_figsize = (self.pie_size_px / self.dpi, self.pie_size_px / self.dpi)
        
        plt.style.use('default')
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
    
    def create_chart(self, chart_type, chart_data, title="장애 통계", color_palette=None):
        """차트 생성 - 항상 성공하는 차트 생성 (한글 폰트 보장)"""
        print(f"DEBUG: Creating chart - type: {chart_type}, data: {chart_data}")
        
        if not plt.rcParams.get('font.family') or plt.rcParams.get('font.family') == ['sans-serif']:
            self.font_name = setup_korean_font()
        
        if not chart_data:
            return self._create_no_data_chart(title)
        
        try:
            if chart_type == 'no_data':
                return self._create_no_data_chart(title)
            elif chart_type == 'line':
                return self._create_line_chart(chart_data, title)
            elif chart_type == 'pie':
                return self._create_pie_chart(chart_data, title)
            elif chart_type == 'horizontal_bar':
                return self._create_horizontal_bar_chart(chart_data, title)
            else:
                return self._create_bar_chart(chart_data, title)
                
        except Exception as e:
            print(f"DEBUG: Chart creation failed: {e}")
            return self._create_bar_chart(chart_data, title)
    
    def _create_bar_chart(self, data, title):
        """기본 세로 막대차트 생성"""
        try:
            fig, ax = plt.subplots(figsize=self.default_figsize, dpi=self.dpi)
            
            categories = list(data.keys())
            values = list(data.values())
            
            print(f"DEBUG: Creating bar chart with categories: {categories}, values: {values}")
            
            colors = self.colors[:len(categories)] if len(categories) <= len(self.colors) else self.colors * (len(categories) // len(self.colors) + 1)
            
            bars = ax.bar(categories, values, color=colors[:len(categories)], alpha=0.8, 
                         edgecolor='white', linewidth=1.5)
            
            is_time_chart = '시간' in title or any('분' in str(val) for val in values if isinstance(val, str))
            unit = '분' if is_time_chart else '건'
            
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height + max(values)*0.01,
                       f'{int(height)}{unit}', ha='center', va='bottom', 
                       fontweight='bold', fontsize=10, color='#2c3e50')
            
            ax.set_title(title, fontsize=18, fontweight='bold', pad=25, color='#2c3e50')
            ax.set_xlabel('구분', fontsize=13, fontweight='bold', color='#34495e')
            ylabel = '장애 시간(분)' if is_time_chart else '장애 건수'
            ax.set_ylabel(ylabel, fontsize=13, fontweight='bold', color='#34495e')
            
            if len(categories) > 6 or any(len(cat) > 8 for cat in categories):
                plt.xticks(rotation=45, ha='right')
            
            ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
            ax.set_axisbelow(True)
            
            if max(values) > 0:
                ax.set_ylim(0, max(values) * 1.15)
            
            plt.tight_layout()
            return fig
            
        except Exception as e:
            print(f"DEBUG: Bar chart creation failed: {e}")
            return self._create_simple_chart(data, title)
    
    def _create_line_chart(self, data, title):
        """선 그래프 생성"""
        try:
            fig, ax = plt.subplots(figsize=self.default_figsize, dpi=self.dpi)
            
            categories = list(data.keys())
            values = list(data.values())
            
            print(f"DEBUG: Creating line chart with categories: {categories}, values: {values}")
            
            ax.plot(categories, values, marker='o', linewidth=3, markersize=8, 
                   color=self.colors[0], markerfacecolor=self.colors[1], 
                   markeredgecolor='white', markeredgewidth=2)
            
            ax.fill_between(categories, values, alpha=0.3, color=self.colors[0])
            
            is_time_chart = '시간' in title or any(val > 100 for val in values)
            unit = '분' if is_time_chart else '건'
            
            for i, (x, y) in enumerate(zip(categories, values)):
                ax.annotate(f'{int(y)}{unit}', (x, y), textcoords="offset points", 
                           xytext=(0,15), ha='center', fontweight='bold', 
                           fontsize=10, color='#2c3e50')
            
            ax.set_title(title, fontsize=18, fontweight='bold', pad=25, color='#2c3e50')
            ax.set_xlabel('기간', fontsize=13, fontweight='bold', color='#34495e')
            ylabel = '장애 시간(분)' if is_time_chart else '장애 건수'
            ax.set_ylabel(ylabel, fontsize=13, fontweight='bold', color='#34495e')
            
            if len(categories) > 6:
                plt.xticks(rotation=45, ha='right')
            
            ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
            ax.set_axisbelow(True)
            
            plt.tight_layout()
            return fig
            
        except Exception as e:
            print(f"DEBUG: Line chart creation failed: {e}")
            return self._create_bar_chart(data, title)
    
    def _create_horizontal_bar_chart(self, data, title):
        """가로 막대차트 생성"""
        try:
            limited_data = dict(list(data.items())[:10])
            
            fig, ax = plt.subplots(figsize=self.default_figsize, dpi=self.dpi)
            
            categories = list(limited_data.keys())
            values = list(limited_data.values())
            
            colors = self.colors[:len(categories)] if len(categories) <= len(self.colors) else self.colors * (len(categories) // len(self.colors) + 1)
            
            y_pos = np.arange(len(categories))
            bars = ax.barh(y_pos, values, color=colors[:len(categories)], alpha=0.8, 
                          edgecolor='white', linewidth=1.5)
            
            is_time_chart = '시간' in title or any(val > 100 for val in values)
            unit = '분' if is_time_chart else '건'
            
            for i, (bar, value) in enumerate(zip(bars, values)):
                width = bar.get_width()
                ax.text(width + max(values)*0.01, bar.get_y() + bar.get_height()/2.,
                       f'{int(value)}{unit}', ha='left', va='center', 
                       fontweight='bold', fontsize=10, color='#2c3e50')
            
            ax.set_title(title, fontsize=18, fontweight='bold', pad=25, color='#2c3e50')
            xlabel = '장애 시간(분)' if is_time_chart else '장애 건수'
            ax.set_xlabel(xlabel, fontsize=13, fontweight='bold', color='#34495e')
            ax.set_ylabel('카테고리', fontsize=13, fontweight='bold', color='#34495e')
            ax.set_yticks(y_pos)
            ax.set_yticklabels(categories)
            
            ax.grid(True, alpha=0.3, axis='x', linestyle='--', linewidth=0.5)
            ax.set_axisbelow(True)
            
            plt.tight_layout()
            return fig
            
        except Exception as e:
            print(f"DEBUG: Horizontal bar chart creation failed: {e}")
            return self._create_bar_chart(data, title)
    
    def _create_pie_chart(self, data, title):
        """원형 그래프 생성"""
        try:
            fig, ax = plt.subplots(figsize=self.pie_figsize, dpi=self.dpi)
            
            labels = list(data.keys())
            sizes = list(data.values())
            
            total = sum(sizes)
            if total > 0:
                threshold = total * 0.05
                
                new_labels = []
                new_sizes = []
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
                
                wedges, texts, autotexts = ax.pie(new_sizes, labels=new_labels, colors=colors,
                                                 autopct='%1.1f%%', startangle=90,
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
            return fig
            
        except Exception as e:
            print(f"DEBUG: Pie chart creation failed: {e}")
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
            fig, ax = plt.subplots(figsize=(8, 6))
            
            if data and len(data) > 0:
                categories = list(data.keys())[:5]
                values = list(data.values())[:5]
                
                ax.bar(categories, values, color='skyblue', alpha=0.7)
                
                is_time_chart = '시간' in title or any(val > 100 for val in values)
                unit = '분' if is_time_chart else '건'
                
                for i, v in enumerate(values):
                    ax.text(i, v + max(values)*0.01, f'{int(v)}{unit}', ha='center', va='bottom')
                
                ax.set_title(title, fontsize=14, fontweight='bold')
                ylabel = '시간(분)' if is_time_chart else '건수'
                ax.set_ylabel(ylabel)
                
                if len(max(categories, key=len)) > 8:
                    plt.xticks(rotation=45, ha='right')
                    
            else:
                ax.text(0.5, 0.5, '데이터가 없습니다', ha='center', va='center', 
                       transform=ax.transAxes, fontsize=14)
                ax.set_title(title, fontsize=14, fontweight='bold')
                ax.axis('off')
            
            plt.tight_layout()
            return fig
            
        except Exception as e:
            print(f"DEBUG: Simple chart creation failed: {e}")
            return None

    def display_chart_with_data(self, chart, chart_data, chart_type, query=""):
        """차트와 데이터 테이블 표시 - 완전 고정 크기 보장 + 텍스트 시각화 제거"""
        
        if not chart_data:
            st.warning("차트를 생성할 데이터가 없습니다.")
            return
        
        chart_session_key = "stable_chart_data"
        
        if (chart_session_key not in st.session_state or 
            st.session_state[chart_session_key] != chart_data):
            st.session_state[chart_session_key] = chart_data.copy()
            st.session_state["stable_chart_query"] = query
        
        stable_data = st.session_state[chart_session_key]
        stable_query = st.session_state.get("stable_chart_query", query)
        
        if chart:
            st.pyplot(chart, use_container_width=False, clear_figure=True)
            plt.close(chart)
        
        st.markdown("---")
        with st.expander("📊 상세 데이터 보기"):
            if stable_data:
                is_time_chart = '시간' in stable_query.lower() or any(val > 100 for val in stable_data.values() if isinstance(val, (int, float)))
                value_column = '시간(분)' if is_time_chart else '건수'
                
                df = pd.DataFrame(list(stable_data.items()), columns=['구분', value_column])
                
                total = df[value_column].sum()
                if total > 0:
                    df['비율(%)'] = (df[value_column] / total * 100).round(1)
                
                st.dataframe(df, use_container_width=True)
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    total_label = f"총 {value_column.split('(')[0]}"
                    total_unit = '분' if is_time_chart else '건'
                    st.metric(total_label, f"{total:,}{total_unit}")
                with col2:
                    avg_label = f"평균"
                    st.metric(avg_label, f"{df[value_column].mean():.1f}{total_unit}")  
                with col3:
                    st.metric("항목 수", f"{len(df)}개")
                
                csv = df.to_csv(index=False, encoding='utf-8-sig')
                filename_suffix = "장애시간통계" if is_time_chart else "장애건수통계"
                st.download_button(
                    label="📥 CSV 다운로드",
                    data=csv,
                    file_name=f"{filename_suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )