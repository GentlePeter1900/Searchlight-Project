# app.py
# Searchlight 프로젝트의 프론트엔드 웹 대시보드입니다.

import streamlit as st
import os
from dotenv import load_dotenv
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, timezone

# --- .env 파일 로드 및 클라이언트 초기화 ---
load_dotenv()

try:
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")
    STREAMLIT_APP_PASSWORD = os.environ.get("STREAMLIT_APP_PASSWORD")

    if not all([SUPABASE_URL, SUPABASE_KEY, STREAMLIT_APP_PASSWORD]):
        st.error("필수 환경 변수가 .env 파일에 설정되지 않았습니다. (SUPABASE_URL, SUPABASE_KEY, STREAMLIT_APP_PASSWORD)")
        st.stop()

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
except Exception as e:
    st.error(f"초기화 중 에러 발생: {e}")
    st.stop()


# --- 페이지 기본 설정 ---
st.set_page_config(
    page_title="Searchlight - Your YouTube Intelligence Platform",
    page_icon="🔦",
    layout="wide",
)

# --- 비밀번호 인증 (간단한 방식) ---
def check_password():
    """비밀번호가 맞는지 확인합니다."""
    if "password_entered" not in st.session_state:
        st.session_state.password_entered = False

    if st.session_state.password_entered:
        return True

    password = st.text_input("비밀번호를 입력하세요", type="password")
    
    # .env 파일에서 불러온 비밀번호와 비교
    if password == STREAMLIT_APP_PASSWORD: 
        st.session_state.password_entered = True
        st.rerun()
    elif password:
        st.error("비밀번호가 틀렸습니다.")
    return False

# --- 데이터 로딩 함수 ---
@st.cache_data(ttl=600) # 10분 동안 캐시
def fetch_video_ranking():
    """
    DB에서 데이터를 가져와 다양한 지표를 계산하고 랭킹을 반환합니다.
    """
    try:
        print("DB에서 종합 랭킹 데이터를 가져옵니다...")
        # 1. 각 테이블에서 데이터 가져오기
        videos_res = supabase.table('videos').select('video_id, channel_id, title, published_at, duration_sec').execute()
        stats_res = supabase.table('video_stats').select('video_id, view_count, like_count, comment_count').execute()
        channels_res = supabase.table('channels').select('channel_id, name').execute()

        # 2. Pandas DataFrame으로 변환
        videos_df = pd.DataFrame(videos_res.data)
        stats_df = pd.DataFrame(stats_res.data)
        channels_df = pd.DataFrame(channels_res.data)

        if videos_df.empty or stats_df.empty or channels_df.empty:
            st.warning("아직 데이터베이스에 분석할 데이터가 충분하지 않습니다.")
            return pd.DataFrame()

        # 3. 모든 DataFrame 병합
        df = pd.merge(videos_df, stats_df, on='video_id')
        df = pd.merge(df, channels_df, on='channel_id')

        # 4. 시간 관련 데이터 처리
        df['published_at'] = pd.to_datetime(df['published_at'])
        now_utc = datetime.now(timezone.utc)
        df['hours_since_published'] = (now_utc - df['published_at']).dt.total_seconds() / 3600
        
        # 5. 신규 지표 계산 (0으로 나누기 방지)
        df['VPH'] = (df['view_count'] / (df['hours_since_published'] + 1)).round(0).astype(int)
        df['like_rate'] = ((df['like_count'] / (df['view_count'] + 1)) * 100).round(2)
        df['comment_rate'] = ((df['comment_count'] / (df['view_count'] + 1)) * 100).round(2)
        df['views_per_minute'] = (df['view_count'] / ((df['duration_sec'] / 60) + 0.01)).round(0).astype(int)

        # 6. 화면에 표시할 컬럼 선택 및 이름 변경
        result_df = df[[
            'title', 'name', 'VPH', 'like_rate', 'comment_rate', 
            'views_per_minute', 'like_count', 'view_count', 'published_at'
        ]]
        result_df.columns = [
            '제목', '채널명', 'VPH', '좋아요율(%)', '댓글율(%)', 
            '분당조회수', '좋아요', '총조회수', '게시일'
        ]
        
        # 7. VPH 기준으로 내림차순 정렬
        result_df = result_df.sort_values(by='VPH', ascending=False)
        
        # 인덱스 리셋 (순위 표시용)
        result_df = result_df.reset_index(drop=True)
        result_df.index += 1

        print("데이터 로딩 및 가공 완료.")
        return result_df

    except Exception as e:
        st.error(f"데이터를 가져오는 중 오류가 발생했습니다: {e}")
        return pd.DataFrame()


# --- 메인 대시보드 로직 ---
def main_dashboard():
    st.title("🔦 Searchlight Dashboard")
    st.markdown("데이터로 당신의 감각에 확신을 더합니다.")

    # 탭 생성
    tab1, tab2, tab3, tab4 = st.tabs(["📈 위클리 리포트", "💡 기회 발굴", "🎬 영상 분석", "📺 채널 분석"])

    with tab1:
        st.header("주간 유튜브 동향 요약")
        st.write("이곳에 지난주 가장 중요한 트렌드 요약이 표시됩니다.")

    with tab2:
        st.header("새로운 콘텐츠 아이디어와 키워드")
        st.write("이곳에 구글 트렌드, 떡상 키워드 분석 결과가 표시됩니다.")

    with tab3:
        st.header("영상 성과 분석 (VPH 순 랭킹)")
        
        video_ranking_data = fetch_video_ranking()
        
        if not video_ranking_data.empty:
            st.dataframe(video_ranking_data, use_container_width=True)
        else:
            st.info("데이터를 표시할 수 없습니다. collector.py를 먼저 실행하여 데이터를 수집해주세요.")

    with tab4:
        st.header("채널 성장 분석 및 랭킹")
        st.write("이곳에 주간 구독자 성장률 기반의 채널 랭킹이 표시됩니다.")

# --- 앱 실행 ---
if __name__ == "__main__":
    if check_password():
        main_dashboard()
