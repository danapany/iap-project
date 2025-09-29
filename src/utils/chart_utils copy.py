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
    
    def _detect_explicitly_requested_stats(self, query_lower):
        """사용자가 명시적으로 요청한 통계 유형 정확히 파악 - 우선순위 강화"""
        requested_stats = []
        
        stat_patterns = {
            'yearly': [
                r'\b(년도별|연도별|년별|연별)\s*(통계|건수|현황|장애|차트|그래프)',
                r'\b(\d{4})년?\s*~?\s*(\d{4})년?\b',
                r'\b년도\s*(통계|건수|현황|장애|차트|그래프)\b',
                r'\b연별\s*(통계|건수|현황|장애|차트|그래프)\b',
                r'\b\d{4}년\s*(통계|건수|현황|장애|차트|그래프)\b'
            ],
            'monthly': [
                r'\b(\d+)월?\s*~?\s*(\d+)월?\b',
                r'\b(\d+)\s*~\s*(\d+)월?\s*(통계|건수|현황|장애|차트|그래프)\b',
                r'\b월별\s*(통계|건수|현황|장애|차트|그래프)\b',
                r'\b(\d+)개월?\s*(통계|건수|현황|장애|차트|그래프)\b',
                r'\b월\s*(통계|건수|현황|장애|차트|그래프)\b'
            ],
            'time_period': [
                r'\b시간대별\s*(통계|건수|현황|장애|차트|그래프)\b',
                r'\b(주간|야간)\s*(통계|건수|현황|장애|차트|그래프)\b',
                r'\b(주간|야간)\s*장애\b',
                r'\b시간대\s*(통계|건수|현황|장애|차트|그래프)\b'
            ],
            'weekday': [
                r'\b요일별\s*(통계|건수|현황|장애|차트|그래프)\b',
                r'\b(월요일|화요일|수요일|목요일|금요일|토요일|일요일)\s*(통계|건수|현황|장애|차트|그래프)\b',
                r'\b(평일|주말)\s*(통계|건수|현황|장애|차트|그래프)\b',
                r'\b요일\s*(통계|건수|현황|장애|차트|그래프)\b'
            ],
            'department': [
                r'\b부서별\s*(통계|건수|현황|장애|차트|그래프)\b',
                r'\b팀별\s*(통계|건수|현황|장애|차트|그래프)\b',
                r'\b부서\s*(통계|건수|현황|장애|차트|그래프)\b'
            ],
            'grade': [
                r'\b등급별\s*(통계|건수|현황|장애|차트|그래프|비율|분포)\b',
                r'\b장애등급별?\s*(통계|건수|현황|장애|차트|그래프|비율|분포)\b',
                r'\b(\d+등급)\s*(통계|건수|현황|장애|차트|그래프)\b',
                r'\b등급\s*(통계|건수|현황|장애|차트|그래프|비율|분포)\b'
            ],
            'service': [
                r'\b서비스별\s*(통계|건수|현황|장애|차트|그래프)\b',
                r'\b서비스\s*(통계|건수|현황|장애|차트|그래프)\b'
            ],
            'cause_type': [
                r'\b원인유형별\s*(통계|건수|현황|장애|차트|그래프)\b',
                r'\b원인별\s*(통계|건수|현황|장애|차트|그래프)\b',
                r'\b원인\s*유형\s*(통계|건수|현황|장애|차트|그래프)\b'
            ]
        }
        
        # 패턴 매칭 - 순서대로 확인
        for stat_type, patterns in stat_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    if stat_type not in requested_stats:
                        requested_stats.append(stat_type)
                        print(f"DEBUG: Detected {stat_type} from pattern: {pattern}")
                    break
        
        # 특별 처리: 년도 범위 패턴이 있으면 yearly를 최우선으로
        year_range_pattern = r'\b(\d{4})년?\s*~\s*(\d{4})년?\b'
        if re.search(year_range_pattern, query_lower):
            if 'yearly' not in requested_stats:
                requested_stats.insert(0, 'yearly')
                print(f"DEBUG: Detected yearly from year range pattern")
        
        # 특별 처리: "년도별", "연도별" 키워드가 있으면 yearly를 최우선으로
        if any(keyword in query_lower for keyword in ['년도별', '연도별', '년별', '연별']):
            if 'yearly' in requested_stats:
                requested_stats.remove('yearly')
            requested_stats.insert(0, 'yearly')
            print(f"DEBUG: Prioritized yearly due to explicit keyword")
        
        # 특별 처리: 월 범위 패턴이 있으면 monthly 우선 (단, yearly보다는 낮은 우선순위)
        month_range_pattern = r'\b(\d+)월?\s*~\s*(\d+)월?\b'
        if re.search(month_range_pattern, query_lower):
            if 'monthly' not in requested_stats:
                # yearly가 이미 있으면 그 다음에 추가
                if 'yearly' in requested_stats:
                    yearly_idx = requested_stats.index('yearly')
                    requested_stats.insert(yearly_idx + 1, 'monthly')
                else:
                    requested_stats.insert(0, 'monthly')
                print(f"DEBUG: Detected monthly from month range pattern")
        
        print(f"DEBUG: Final detected explicit stat requests: {requested_stats}")
        return requested_stats

    def detect_chart_suitable_query(self, query, documents):
        """명시적으로 차트/그래프를 요청한 경우에만 차트 생성"""
        print(f"DEBUG: Chart detection for query: {query}")
        print(f"DEBUG: Documents count: {len(documents) if documents else 0}")
        
        if not query:
            return False, None, None
        
        if documents is None:
            documents = []
        
        query_lower = query.lower()
        
        explicit_chart_requests = {
            'pie': ['파이차트', '파이 차트', '원형차트', '원형 차트', '파이그래프', '비율차트', '퍼센트차트'],
            'horizontal_bar': ['가로막대차트', '가로막대', '가로 막대차트', '가로 막대', '수평막대차트', '수평막대', '수평 막대차트'],
            'bar': ['세로막대차트', '세로막대', '세로 막대차트', '세로 막대', '막대차트', '막대그래프', '바차트'],
            'line': ['선차트', '선 차트', '선그래프', '라인차트', '라인그래프', '꺾은선차트', '꺾은선그래프']
        }
        
        requested_chart_type = None
        for chart_type, keywords in explicit_chart_requests.items():
            if any(keyword in query_lower for keyword in keywords):
                requested_chart_type = chart_type
                print(f"DEBUG: Explicit chart type requested: {chart_type}")
                break
        
        # 명시적인 차트/그래프 요청 키워드만 확인
        general_chart_keywords = ['차트', '그래프', '시각화', '그려', '그려줘', '보여줘', '시각적으로', '도표', '도식화']
        
        # 차트 요청 여부 확인 (명시적 요청만)
        has_explicit_chart_request = any(keyword in query_lower for keyword in general_chart_keywords) or requested_chart_type is not None
        
        print(f"DEBUG: Has explicit chart request: {has_explicit_chart_request}")
        print(f"DEBUG: Requested chart type: {requested_chart_type}")
        
        # 명시적으로 차트를 요청한 경우에만 차트 생성
        if has_explicit_chart_request:
            if documents and len(documents) >= 1:
                chart_type, chart_data = self._analyze_query_and_extract_data(query_lower, documents, requested_chart_type)
                
                print(f"DEBUG: Chart type determined: {chart_type}")
                print(f"DEBUG: Chart data extracted: {bool(chart_data)}")
                
                if chart_data and len(chart_data) > 0:
                    return True, chart_type, chart_data
                else:
                    print("DEBUG: Chart data extraction failed, trying fallback")
                    chart_data = {'전체 장애': len(documents)}
                    chart_type = requested_chart_type or 'bar'
                    print(f"DEBUG: Using fallback data: {chart_data}")
                    return True, chart_type, chart_data
            else:
                print("DEBUG: No documents, creating empty chart")
                return True, 'no_data', {'데이터 없음': 0}
        
        print("DEBUG: No explicit chart request found")
        return False, None, None
    
    def _analyze_query_and_extract_data(self, query_lower, documents, requested_chart_type=None):
        """질문 분석을 통한 지능적 차트 타입 및 데이터 결정 - 명시적 요청 최우선"""
        
        requested_stats = self._detect_explicitly_requested_stats(query_lower)
        print(f"DEBUG: Explicitly requested stats: {requested_stats}")
        
        # 명시적으로 요청된 통계가 있으면 최우선으로 처리
        if requested_stats:
            for stat_type in requested_stats:
                print(f"DEBUG: Trying to extract {stat_type} data...")
                
                if stat_type == 'yearly':
                    data = self._extract_yearly_data(documents)
                    if data and len(data) > 0:
                        print(f"DEBUG: Successfully extracted yearly data: {data}")
                        return requested_chart_type or 'line', data
                        
                elif stat_type == 'monthly':
                    data = self._extract_monthly_data(documents, query_lower)
                    if data and len(data) > 0:
                        print(f"DEBUG: Successfully extracted monthly data: {data}")
                        return requested_chart_type or 'line', data
                        
                elif stat_type == 'time_period':
                    data = self._extract_time_period_data(documents)
                    if data and len(data) > 0:
                        print(f"DEBUG: Successfully extracted time period data: {data}")
                        return requested_chart_type or 'bar', data
                        
                elif stat_type == 'weekday':
                    data = self._extract_weekday_data(documents)
                    if data and len(data) > 0:
                        print(f"DEBUG: Successfully extracted weekday data: {data}")
                        return requested_chart_type or 'bar', data
                        
                elif stat_type == 'department':
                    data = self._extract_department_data(documents)
                    if data and len(data) > 0:
                        print(f"DEBUG: Successfully extracted department data: {data}")
                        return requested_chart_type or 'horizontal_bar', data
                        
                elif stat_type == 'grade':
                    data = self._extract_grade_data(documents)
                    if data and len(data) > 0:
                        print(f"DEBUG: Successfully extracted grade data: {data}")
                        return requested_chart_type or 'pie', data
                        
                elif stat_type == 'service':
                    data = self._extract_service_data(documents)
                    if data and len(data) > 0:
                        print(f"DEBUG: Successfully extracted service data: {data}")
                        return requested_chart_type or 'horizontal_bar', data
                        
                elif stat_type == 'cause_type':
                    data = self._extract_cause_type_data(documents)
                    if data and len(data) > 0:
                        print(f"DEBUG: Successfully extracted cause_type data: {data}")
                        return requested_chart_type or 'horizontal_bar', data
        
        print("DEBUG: No explicit request or no data for requested stats, trying priority approach")
        
        # 명시적 요청이 없거나 실패한 경우, 키워드 기반 우선순위 처리
        extraction_priority = [
            ('연도', ['년도별', '연도별', '년도', '년', '연별'], self._extract_yearly_data, requested_chart_type or 'line'),
            ('월', ['월별', '월'], lambda docs: self._extract_monthly_data(docs, query_lower), requested_chart_type or 'line'),
            ('시간대', ['시간대별', '주간', '야간'], self._extract_time_period_data, requested_chart_type or 'bar'),
            ('요일', ['요일별', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일'], self._extract_weekday_data, requested_chart_type or 'bar'),
            ('부서', ['부서별', '부서', '팀'], self._extract_department_data, requested_chart_type or 'horizontal_bar'),
            ('등급', ['등급별', '등급', '1등급', '2등급', '3등급', '4등급'], self._extract_grade_data, requested_chart_type or 'pie'),
            ('서비스', ['서비스별', '서비스'], self._extract_service_data, requested_chart_type or 'horizontal_bar'),
            ('원인유형', ['원인유형별', '원인별', '원인유형', '원인'], self._extract_cause_type_data, requested_chart_type or 'horizontal_bar'),
        ]
        
        for category, keywords, extract_method, chart_type in extraction_priority:
            if any(keyword in query_lower for keyword in keywords):
                print(f"DEBUG: Found {category} keywords in query")
                data = extract_method(documents)
                if data and len(data) > 0:
                    print(f"DEBUG: Successfully extracted {category} data: {data}")
                    return chart_type, data
        
        print("DEBUG: No specific keywords found, trying data availability approach")
        for category, keywords, extract_method, chart_type in extraction_priority:
            try:
                data = extract_method(documents)
                if data and len(data) > 1:
                    print(f"DEBUG: Fallback extraction successful with {category} data: {data}")
                    return chart_type, data
            except Exception as e:
                print(f"DEBUG: Extraction method {category} failed: {e}")
                continue
        
        return requested_chart_type or 'bar', self._create_intelligent_fallback_data(query_lower, documents)

    def _create_intelligent_fallback_data(self, query_lower, documents):
        """질문 분석 기반 지능적 폴백 데이터 생성"""
        if not documents:
            return {'데이터 없음': 0}
        
        try:
            if any(keyword in query_lower for keyword in ['월별', '월']):
                monthly_data = self._extract_monthly_data(documents, query_lower)
                if monthly_data:
                    return monthly_data
            
            if any(keyword in query_lower for keyword in ['연도별', '년도별', '연도', '년']):
                yearly_data = self._extract_yearly_data(documents)
                if yearly_data:
                    return yearly_data
                    
            if any(keyword in query_lower for keyword in ['시간대별', '주간', '야간']):
                time_data = self._extract_time_period_data(documents)
                if time_data:
                    return time_data
                    
            if any(keyword in query_lower for keyword in ['요일별']):
                weekday_data = self._extract_weekday_data(documents)
                if weekday_data:
                    return weekday_data
            
            for extract_method in [
                lambda docs: self._extract_monthly_data(docs, query_lower),
                self._extract_yearly_data,
                self._extract_time_period_data,
                self._extract_weekday_data,
                self._extract_grade_data,
                self._extract_department_data,
                self._extract_service_data
            ]:
                try:
                    data = extract_method(documents)
                    if data and len(data) > 1:
                        return data
                except:
                    continue
            
            return {'전체 장애': len(documents)}
            
        except Exception as e:
            print(f"DEBUG: Intelligent fallback failed: {e}")
            return {'전체 장애': len(documents)}

    def _determine_simple_chart_type(self, query_lower):
        """개선된 차트 타입 결정 로직"""
        
        if any(keyword in query_lower for keyword in ['연도별', '년도별', '월별', '추이', '변화', '시간', '기간별']):
            return 'line'
        
        elif any(keyword in query_lower for keyword in ['비율', '등급별', '분포', '구성', '%', '퍼센트']):
            return 'pie'
        
        elif any(keyword in query_lower for keyword in ['부서별', '서비스별']) and any(keyword in query_lower for keyword in ['많은', '순위', '상위', 'top']):
            return 'horizontal_bar'
        
        else:
            return 'bar'
    
    def _extract_service_data(self, documents):
        """서비스별 데이터 추출"""
        if not documents:
            return {}
        
        service_count = {}
        for doc in documents:
            if doc is None:
                continue
            service_name = doc.get('service_name', '').strip()
            if service_name:
                service_count[service_name] = service_count.get(service_name, 0) + 1
        
        if not service_count:
            return {}
            
        sorted_service = dict(sorted(service_count.items(), key=lambda x: x[1], reverse=True)[:10])
        print(f"DEBUG: Service data extracted: {sorted_service}")
        return sorted_service
    
    def _extract_yearly_data(self, documents):
        """연도별 데이터 추출"""
        if not documents:
            return {}
            
        yearly_count = {}
        
        for doc in documents:
            if doc is None:
                continue
            
            year = None
            
            if doc.get('year'):
                try:
                    year = str(doc.get('year')).strip()
                    if year.isdigit() and len(year) == 4:
                        year_num = int(year)
                        if 2000 <= year_num <= 2030:
                            year = year
                except:
                    year = None
            
            if not year and doc.get('error_date'):
                try:
                    error_date = str(doc.get('error_date')).strip()
                    if len(error_date) >= 4:
                        potential_year = error_date[:4]
                        if potential_year.isdigit():
                            year_num = int(potential_year)
                            if 2000 <= year_num <= 2030:
                                year = potential_year
                except:
                    year = None
            
            if year and year.isdigit() and len(year) == 4:
                year_label = f"{year}년"
                yearly_count[year_label] = yearly_count.get(year_label, 0) + 1
        
        if not yearly_count:
            return {}
        
        sorted_yearly = dict(sorted(yearly_count.items()))
        print(f"DEBUG: Yearly data extracted: {sorted_yearly}")
        return sorted_yearly
    
    def _extract_monthly_data(self, documents, query_context=None):
        """월별 데이터 추출 - 정확성 보장 버전 (장애시간 통계 지원)"""
        if not documents:
            return {}
        
        print(f"DEBUG: Extracting monthly data from {len(documents)} documents")
        print(f"DEBUG: Query context: {query_context}")
        
        is_error_time_query = False
        if query_context:
            error_time_keywords = ['장애시간', '장애 시간', 'error_time', '시간 통계', '시간 합계', '시간 합산']
            is_error_time_query = any(keyword in query_context.lower() for keyword in error_time_keywords)
            print(f"DEBUG: Is error time query: {is_error_time_query}")
        
        target_year = None
        start_month = None
        end_month = None
        
        if query_context:
            year_match = re.search(r'\b(202[0-9]|201[0-9])\b', query_context)
            if year_match:
                target_year = year_match.group(1)
                print(f"DEBUG: Target year from query: {target_year}")
            
            month_range_match = re.search(r'\b(\d+)월?\s*~\s*(\d+)월?\b', query_context)
            if month_range_match:
                start_month = int(month_range_match.group(1))
                end_month = int(month_range_match.group(2))
                print(f"DEBUG: Month range from query: {start_month}-{end_month}")
        
        monthly_data = {}
        processed_docs = 0
        
        for doc in documents:
            if doc is None:
                continue
            
            doc_year = None
            doc_month = None
            
            if doc.get('year'):
                try:
                    doc_year = str(doc.get('year')).strip()
                    print(f"DEBUG: Doc year from 'year' field: {doc_year}")
                except:
                    doc_year = None
            
            if not doc_year and doc.get('error_date'):
                try:
                    error_date = str(doc.get('error_date')).strip()
                    if '-' in error_date and len(error_date) >= 4:
                        doc_year = error_date[:4]
                        print(f"DEBUG: Doc year from 'error_date': {doc_year}")
                except:
                    doc_year = None
            
            if doc.get('month'):
                try:
                    month_val = str(doc.get('month')).strip()
                    if month_val.isdigit():
                        month_num = int(month_val)
                        if 1 <= month_num <= 12:
                            doc_month = month_num
                            print(f"DEBUG: Doc month from 'month' field: {doc_month}")
                except:
                    doc_month = None
            
            if doc_month is None and doc.get('error_date'):
                try:
                    error_date = str(doc.get('error_date')).strip()
                    if '-' in error_date and len(error_date) >= 7:
                        parts = error_date.split('-')
                        if len(parts) >= 2 and parts[1].isdigit():
                            month_num = int(parts[1])
                            if 1 <= month_num <= 12:
                                doc_month = month_num
                                print(f"DEBUG: Doc month from 'error_date': {doc_month}")
                except:
                    doc_month = None
            
            skip_doc = False
            
            if target_year and doc_year != target_year:
                print(f"DEBUG: Skipping doc - year mismatch: {doc_year} != {target_year}")
                skip_doc = True
            
            if start_month is not None and end_month is not None and doc_month is not None:
                if not (start_month <= doc_month <= end_month):
                    print(f"DEBUG: Skipping doc - month out of range: {doc_month} not in {start_month}-{end_month}")
                    skip_doc = True
            
            if skip_doc:
                continue
            
            if doc_month and 1 <= doc_month <= 12:
                month_key = f"{doc_month}월"
                
                if is_error_time_query:
                    error_time = doc.get('error_time', 0)
                    try:
                        error_time = int(error_time) if error_time is not None else 0
                    except (ValueError, TypeError):
                        error_time = 0
                    
                    monthly_data[month_key] = monthly_data.get(month_key, 0) + error_time
                    print(f"DEBUG: Added {error_time} minutes to {month_key}, total: {monthly_data[month_key]} minutes")
                else:
                    monthly_data[month_key] = monthly_data.get(month_key, 0) + 1
                    print(f"DEBUG: Added doc to {month_key}, total: {monthly_data[month_key]} 건")
                
                processed_docs += 1
        
        print(f"DEBUG: Processed {processed_docs} documents for monthly data")
        print(f"DEBUG: Raw monthly data: {monthly_data}")
        print(f"DEBUG: Data type: {'장애시간 합산(분)' if is_error_time_query else '발생 건수'}")
        
        if not monthly_data:
            print("DEBUG: No monthly data found")
            return {}
        
        month_order = [f"{i}월" for i in range(1, 13)]
        ordered_monthly = {}
        for month in month_order:
            if month in monthly_data:
                ordered_monthly[month] = monthly_data[month]
        
        print(f"DEBUG: Final ordered monthly data: {ordered_monthly}")
        print(f"DEBUG: Query context - Year: {target_year}, Month range: {start_month}-{end_month}")
        print(f"DEBUG: Statistics type: {'장애시간 합산(분)' if is_error_time_query else '발생 건수'}")
        
        return ordered_monthly
    
    def _extract_time_period_data(self, documents):
        """시간대별 데이터 추출"""
        if not documents:
            return {}
            
        time_count = {}
        for doc in documents:
            if doc is None:
                continue
            daynight = doc.get('daynight', '').strip()
            if daynight:
                time_count[daynight] = time_count.get(daynight, 0) + 1
        
        print(f"DEBUG: Time period data extracted: {time_count}")
        return time_count
    
    def _extract_weekday_data(self, documents):
        """요일별 데이터 추출"""
        if not documents:
            return {}
            
        weekday_count = {}
        for doc in documents:
            if doc is None:
                continue
            week = doc.get('week', '').strip()
            if week:
                if week in ['월', '화', '수', '목', '금', '토', '일']:
                    week_display = f"{week}요일"
                else:
                    week_display = week
                weekday_count[week_display] = weekday_count.get(week_display, 0) + 1
        
        if not weekday_count:
            return {}
        
        week_order = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일', '평일', '주말']
        ordered_weekday = {}
        for day in week_order:
            if day in weekday_count:
                ordered_weekday[day] = weekday_count[day]
        
        print(f"DEBUG: Weekday data extracted: {ordered_weekday}")
        return ordered_weekday
    
    def _extract_department_data(self, documents):
        """부서별 데이터 추출"""
        if not documents:
            return {}
            
        dept_count = {}
        for doc in documents:
            if doc is None:
                continue
            owner_depart = doc.get('owner_depart', '').strip()
            if owner_depart:
                dept_count[owner_depart] = dept_count.get(owner_depart, 0) + 1
        
        if not dept_count:
            return {}
        
        sorted_dept = dict(sorted(dept_count.items(), key=lambda x: x[1], reverse=True)[:10])
        print(f"DEBUG: Department data extracted: {sorted_dept}")
        return sorted_dept
    
    def _extract_grade_data(self, documents):
        """등급별 데이터 추출"""
        if not documents:
            return {}
            
        grade_count = {}
        for doc in documents:
            if doc is None:
                continue
            incident_grade = doc.get('incident_grade', '').strip()
            if incident_grade:
                grade_count[incident_grade] = grade_count.get(incident_grade, 0) + 1
        
        if not grade_count:
            return {}
        
        grade_order = ['1등급', '2등급', '3등급', '4등급']
        ordered_grades = {}
        for grade in grade_order:
            if grade in grade_count:
                ordered_grades[grade] = grade_count[grade]
        
        for grade, count in grade_count.items():
            if grade not in ordered_grades:
                ordered_grades[grade] = count
                
        print(f"DEBUG: Grade data extracted: {ordered_grades}")
        return ordered_grades
    
    def _extract_cause_type_data(self, documents):
        """원인유형별 데이터 추출"""
        if not documents:
            return {}
        
        cause_type_count = {}
        for doc in documents:
            if doc is None:
                continue
            cause_type = doc.get('cause_type', '').strip()
            if cause_type:
                cause_type_count[cause_type] = cause_type_count.get(cause_type, 0) + 1
        
        if not cause_type_count:
            return {}
        
        # 건수 순으로 정렬
        sorted_cause_types = dict(sorted(cause_type_count.items(), key=lambda x: x[1], reverse=True)[:10])
        print(f"DEBUG: Cause type data extracted: {sorted_cause_types}")
        return sorted_cause_types
    
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
    
    def _generate_chart_title(self, query, chart_type):
        """차트 제목 생성"""
        title_map = {
            'yearly': '연도별 장애 발생 현황',
            'monthly': '월별 장애 발생 현황',
            'time_period': '시간대별 장애 발생 분포',
            'weekday': '요일별 장애 발생 분포',
            'department': '부서별 장애 처리 현황',
            'service': '서비스별 장애 발생 현황',
            'grade': '장애등급별 발생 비율',
            'cause_type': '장애원인 유형별 분포',
            'general': '장애 발생 통계'
        }
        
        base_title = title_map.get(chart_type, '장애 통계')
        
        import re
        year_match = re.search(r'\b(202[0-9]|201[0-9])\b', query)
        if year_match:
            year = year_match.group(1)
            base_title = f"{year}년 {base_title}"
        
        if '시간' in query.lower():
            base_title = base_title.replace('발생', '시간')
            base_title = base_title.replace('건수', '시간')
        
        if '야간' in query:
            base_title += ' (야간)'
        elif '주간' in query:
            base_title += ' (주간)'
        
        if any(day in query for day in ['월요일', '화요일', '수요일', '목요일', '금요일']):
            base_title += ' (평일)'
        elif '주말' in query:
            base_title += ' (주말)'
            
        return base_title