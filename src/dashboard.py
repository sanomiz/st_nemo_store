import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
import ast

# 페이지 설정
st.set_page_config(
    page_title="Nemostore Greatness Dashboard",
    page_icon="🏢",
    layout="wide"
)

# 데이터 로드 및 심화 변수 생성
@st.cache_data
def load_data():
    import os
    # 배포 환경과 로컬 환경 모두에서 작동하도록 상대 경로 설정
    base_path = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_path, "..", "data", "nemo_store.db")
    conn = sqlite3.connect(db_path)
    query = "SELECT * FROM stores"
    df = pd.read_sql(query, conn)
    conn.close()
    
    # 1. 심화 파생 변수 생성
    df['monthlyRent'] = df['monthlyRent'].fillna(0)
    df['size'] = df['size'].fillna(1) # 분모 0 방지
    
    # 단위 면적당 월세 (가성비 지표: 만원/㎡)
    df['rent_per_area'] = df['monthlyRent'] / df['size']
    
    # 권리금 비율 (월세 대비 권리금 비중)
    df['premium'] = df['premium'].fillna(0)
    df['premium_ratio'] = df.apply(lambda x: x['premium'] / x['monthlyRent'] if x['monthlyRent'] > 0 else 0, axis=1)
    
    # 이미지 URL 파싱 (문자열 리스트 -> 실제 리스트)
    def parse_urls(val):
        try:
            if isinstance(val, str) and val.startswith('['):
                return ast.literal_eval(val)
            return []
        except:
            return []
    
    df['smallPhotoList'] = df['smallPhotoUrls'].apply(parse_urls)
    
    # 임시 좌표 생성 (지하철역 기반으로 그룹화하기 위해)
    # 실제 위경도가 없으므로 역별로 클러스터링된 임시 좌표 부여 (시각화용)
    station_coords = {
        '을지로입구역': [37.5660, 126.9822],
        '종각역': [37.5702, 126.9831],
        '광화문역': [37.5714, 126.9765],
        '시청역': [37.5657, 126.9768],
        '안국역': [37.5765, 126.9854],
        '을지로3가역': [37.5663, 126.9910],
        '명동역': [37.5609, 126.9863]
    }
    
    def get_lat_lon(station_str):
        if not station_str: return 37.5665, 126.9780
        for s, coords in station_coords.items():
            if s in station_str:
                return coords[0] + (hash(station_str) % 100) / 10000, coords[1] + (hash(station_str[::-1]) % 100) / 10000
        return 37.5665 + (hash(station_str) % 500) / 10000, 126.9780 + (hash(station_str[::-1]) % 500) / 10000

    coords = df['nearSubwayStation'].apply(get_lat_lon)
    df['lat'] = coords.apply(lambda x: x[0])
    df['lon'] = coords.apply(lambda x: x[1])
    
    return df

df = load_data()

# 커스텀 CSS (카드형 레이아웃 및 심미성)
st.markdown("""
<style>
    .stMetric { background-color: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 5px solid #1f77b4; }
    .gallery-card { border: 1px solid #ddd; border-radius: 10px; padding: 10px; margin-bottom: 20px; transition: 0.3s; }
    .gallery-card:hover { box-shadow: 0 4px 8px 0 rgba(0,0,0,0.2); transform: translateY(-5px); }
</style>
""", unsafe_allow_html=True)

# 사이드바: 통합 필터링
st.sidebar.header("📊 필터 및 검색")

# 제목/인근역 통합 검색
search_query = st.sidebar.text_input("📍 매물명 또는 인근역 검색", placeholder="예: 종각, 카페, 무권리")

# 업종 필터
all_biz_types = sorted(df['businessLargeCodeName'].unique().tolist())
selected_biz_types = st.sidebar.multiselect("🏙️ 업종 선택", all_biz_types, default=all_biz_types[:5])

with st.sidebar.expander("💰 가격 및 면적 조건", expanded=True):
    dep_range = st.slider("보증금(만원)", int(df['deposit'].min()), int(df['deposit'].max()), (int(df['deposit'].min()), int(df['deposit'].max())))
    rent_range = st.slider("월세(만원)", int(df['monthlyRent'].min()), int(df['monthlyRent'].max()), (int(df['monthlyRent'].min()), int(df['monthlyRent'].max())))
    size_range = st.slider("면적(㎡)", float(df['size'].min()), float(df['size'].max()), (float(df['size'].min()), float(df['size'].max())))

# 신축/구축 필터 (추가)
st.sidebar.subheader("🏗️ 건물 연식")
df['is_new'] = df['completionConfirmedDateUtc'].apply(lambda x: "신축급(5년내)" if isinstance(x, str) and "2020" in x or "2021" in x or "2022" in x or "2023" in x or "2024" in x or "2025" in x or "2026" in x else "일반/구축")
age_options = ["전체"] + sorted(df['is_new'].unique().tolist())
selected_age = st.sidebar.radio("건물 구분", age_options)

# 가성비 정렬 옵션 추가
sort_option = st.sidebar.selectbox("정렬 기준", ["최신 등록순", "월세 낮은순", "가성비 좋은순", "면적 넓은순"])

# 데이터 필터링 적용
mask = (
    (df['title'].str.contains(search_query, case=False, na=False) | df['nearSubwayStation'].str.contains(search_query, case=False, na=False)) &
    (df['businessLargeCodeName'].isin(selected_biz_types)) &
    (df['deposit'].between(dep_range[0], dep_range[1])) &
    (df['monthlyRent'].between(rent_range[0], rent_range[1])) &
    (df['size'].between(size_range[0], size_range[1]))
)
if selected_age != "전체":
    mask = mask & (df['is_new'] == selected_age)

filtered_df = df[mask].copy()

# ... (중략: 상세 페이지 및 추천 로직 추가 부분) ...

        with d_col2:
            st.title(detail['title'])
            st.markdown("---")
            
            # Benchmarking
            station_avg_rent = df[df['nearSubwayStation'] == detail['nearSubwayStation']]['monthlyRent'].mean()
            s_diff_pct = ((detail['monthlyRent'] - station_avg_rent) / station_avg_rent) * 100 if station_avg_rent > 0 else 0
            
            biz_avg_rent = df[df['businessLargeCodeName'] == detail['businessLargeCodeName']]['monthlyRent'].mean()
            b_diff_pct = ((detail['monthlyRent'] - biz_avg_rent) / biz_avg_rent) * 100 if biz_avg_rent > 0 else 0

            biz_avg_premium = df[df['businessLargeCodeName'] == detail['businessLargeCodeName']]['premium'].mean()
            p_diff_pct = ((detail['premium'] - biz_avg_premium) / biz_avg_premium) * 100 if biz_avg_premium > 0 else 0
            
            c1, c2, c3 = st.columns(3)
            c1.metric("지역 평균 대비 월세", f"{detail['monthlyRent']:,}만원", delta=f"{s_diff_pct:+.1f}%", delta_color="inverse")
            c2.metric("업종 평균 대비 월세", f"{detail['monthlyRent']:,}만원", delta=f"{b_diff_pct:+.1f}%", delta_color="inverse")
            c3.metric("업종 평균 대비 권리금", f"{detail['premium']:,}만원", delta=f"{p_diff_pct:+.1f}%", delta_color="inverse")
            
            st.markdown("---")
            st.write(f"🏢 **보증금**: {detail['deposit']:,}만원 | 📏 **면적**: {detail['size']}㎡ | 🪜 **층수**: {detail['floor']}층")
            st.write(f"🚉 **인근역**: {detail['nearSubwayStation']} | 🏗️ **건물상태**: {detail['is_new']}")
            
            # Smart Recommendation (유사 매물 추천)
            st.subheader("💡 현재 매물과 유사한 추천 매물")
            # 기준: 동일 업종 내에서 월세 ±20%, 면적 ±30% 차이 나는 매물 중 가성비 좋은 순 3개
            same_biz_df = df[(df['businessLargeCodeName'] == detail['businessLargeCodeName']) & (df['id'] != detail['id'])]
            similar_df = same_biz_df[
                (same_biz_df['monthlyRent'].between(detail['monthlyRent']*0.8, detail['monthlyRent']*1.2)) &
                (same_biz_df['size'].between(detail['size']*0.7, detail['size']*1.3))
            ].sort_values('rent_per_area').head(3)
            
            if not similar_df.empty:
                rec_cols = st.columns(len(similar_df))
                for r_idx, (r_id, r_row) in enumerate(similar_df.iterrows()):
                    with rec_cols[r_idx]:
                        st.caption(f"[{r_row['nearSubwayStation']}]")
                        st.write(f"**{r_row['monthlyRent']:,} / {r_row['deposit']:,}**")
                        if st.button("보기", key=f"rec_{r_row['id']}"):
                            st.session_state.selected_item_id = r_row['id']
                            st.rerun()
            else:
                st.caption("유사한 매물을 찾을 수 없습니다.")

            if st.button("닫기", use_container_width=True):
                st.session_state.selected_item_id = None
                st.rerun()

with tab_map:
    st.header("🗺️ 매물 위치 및 지역 밀집도")
    st.info("지도상의 포인트 크기는 매물 면적을, 색상은 가성비(단위 임대료)를 나타냅니다.")
    if not filtered_df.empty:
        # Plotly Scatter Mapbox
        fig_map = px.scatter_mapbox(filtered_df, lat="lat", lon="lon", 
                                    hover_name="title", 
                                    hover_data={
                                        "lat": False, "lon": False,
                                        "monthlyRent": ":,d", "deposit": ":,d", "size": ":.2f"
                                    },
                                    color="rent_per_area", size="size",
                                    color_continuous_scale=px.colors.sequential.RdYlGn_r, 
                                    size_max=15, zoom=13, height=600)
        fig_map.update_layout(mapbox_style="open-street-map")
        fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
        st.plotly_chart(fig_map, use_container_width=True)
        
        # 지역별 밀집도 테이블 (추가)
        st.subheader("📊 지역별 매물 밀집도")
        density = filtered_df.groupby('nearSubwayStation').size().reset_index(name='매물수')
        st.bar_chart(density.set_index('nearSubwayStation'))
    else:
        st.warning("지도에 표시할 매물이 없습니다.")

with tab_analytics:
    st.header("📈 시장 데이터 심무 분석")
    
    a_col1, a_col2 = st.columns(2)
    with a_col1:
        # 층별 임대료 분석 (정제)
        floor_rent = filtered_df.groupby('floor')['monthlyRent'].mean().sort_index().reset_index()
        fig_floor = px.bar(floor_rent, x='floor', y='monthlyRent', 
                           title="층별 평균 월세 분석", 
                           labels={'floor': '층수 (F)', 'monthlyRent': '평균 월세 (만원)'},
                           color='monthlyRent', color_continuous_scale='Blues')
        st.plotly_chart(fig_floor, use_container_width=True)
        
    with a_col2:
        # 인기 매물 분석 (조회수/찜수)
        fig_pop = px.scatter(filtered_df, x='viewCount', y='favoriteCount', size='monthlyRent', 
                             color='businessLargeCodeName', hover_name='title',
                             title="매물 관심도 분석 (X: 조회수, Y: 찜수)",
                             labels={'viewCount': '조회수', 'favoriteCount': '관심(찜)수'})
        st.plotly_chart(fig_pop, use_container_width=True)

    # 역세권별 가성비 트리맵
    st.subheader("🚉 역세권별 가성비 효율성 맵")
    fig_tree = px.treemap(filtered_df, path=['nearSubwayStation', 'businessLargeCodeName'], values='size',
                          color='rent_per_area', color_continuous_scale='RdYlGn_r',
                          title="역세권/업종별 면적 비중 및 가성비 (색상이 붉을수록 가성비 낮음)",
                          labels={'rent_per_area': '단위당 임대료'})
    st.plotly_chart(fig_tree, use_container_width=True)

with tab_compare:
    st.header("⚖️ 매물 벤치마킹 분석")
    st.info("비교하고 싶은 매물을 다중 선택하여 지역/업종별 가치를 객관적으로 비교해 보세요.")
    
    compare_titles = st.multiselect("비교 대상 선택", filtered_df['title'].tolist(), max_selections=3)
    
    if compare_titles:
        c_cols = st.columns(len(compare_titles))
        for idx, t in enumerate(compare_titles):
            c_item = df[df['title'] == t].iloc[0]
            with c_cols[idx]:
                st.image(c_item['previewPhotoUrl'] if c_item['previewPhotoUrl'] else "https://via.placeholder.com/150", use_container_width=True)
                st.subheader(c_item['title'])
                
                # 가성비 벤치마킹 게이지 (Plotly)
                station_avg_rpa = df[df['nearSubwayStation'] == c_item['nearSubwayStation']]['rent_per_area'].mean()
                rpa_diff_pct = ((c_item['rent_per_area'] - station_avg_rpa) / station_avg_rpa) * 100 if station_avg_rpa > 0 else 0
                
                st.metric("단위당 임대료 가점", f"{c_item['rent_per_area']:.2f}만원/㎡", 
                          delta=f"{rpa_diff_pct:+.1f}% (지역평균대비)", delta_color="inverse")
                
                # 상세 데이터 카드 (한글 변환)
                st.markdown("---")
                st.write(f"🏢 **업종**: {c_item['businessLargeCodeName']}")
                st.write(f"💰 **보증금**: {c_item['deposit']:,}만원")
                st.write(f"🏢 **월세**: {c_item['monthlyRent']:,}만원")
                st.write(f"📏 **면적**: {c_item['size']}㎡")
                
                # Gauge Chart
                fig_g = go.Figure(go.Indicator(
                    mode = "gauge+number", value = c_item['rent_per_area'],
                    title = {'text': "가성비 게이지", 'font': {'size': 14}},
                    gauge = {
                        'axis': {'range': [0, df['rent_per_area'].max()]},
                        'bar': {'color': "#1f77b4"},
                        'steps': [{'range': [0, station_avg_rpa], 'color': "rgba(0, 255, 0, 0.2)"}],
                        'threshold': {'line': {'color': "red", 'width': 4}, 'value': station_avg_rpa}
                    }
                ))
                fig_g.update_layout(height=200, margin=dict(l=10, r=10, t=40, b=10))
                st.plotly_chart(fig_g, use_container_width=True)
    else:
        st.warning("상단에서 비교할 매물을 선택해 주세요.")

st.markdown("---")
# 데이터 테이블 (마지막에 위치하여 전체 데이터 확인용)
with st.expander("📂 검색 결과 전체 데이터 보기"):
    st.dataframe(filtered_df[['title', 'businessLargeCodeName', 'nearSubwayStation', 'deposit', 'monthlyRent', 'premium', 'size', 'floor']].rename(columns={
        'title': '매물명',
        'businessLargeCodeName': '대분류 업종',
        'nearSubwayStation': '인근 지하철역',
        'deposit': '보증금(만원)',
        'monthlyRent': '월세(만원)',
        'premium': '권리금(만원)',
        'size': '전용면적(㎡)',
        'floor': '해당층'
    }), use_container_width=True)
