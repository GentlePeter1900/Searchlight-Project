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
        videos_res = supabase.table('videos').select('video_id, channel_id, title, published_at, duration_sec, tags, thumbnail_url').execute()
        stats_res = supabase.table('video_stats').select('video_id, view_count, like_count, comment_count, timestamp').execute()
        channels_res = supabase.table('channels').select('channel_id, name').execute()

        # 2. Pandas DataFrame으로 변환
        videos_df = pd.DataFrame(videos_res.data)
        stats_df = pd.DataFrame(stats_res.data)
        channels_df = pd.DataFrame(channels_res.data)

        if videos_df.empty or stats_df.empty or channels_df.empty:
            st.warning("아직 데이터베이스에 분석할 데이터가 충분하지 않습니다.")
            return pd.DataFrame()

        # 각 video_id별 최신 통계만 유지
        stats_df = stats_df.sort_values(by='timestamp', ascending=False).drop_duplicates(subset=['video_id'])

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
            'video_id', 'channel_id', 'title', 'name', 'VPH', 'like_rate', 'comment_rate', 
            'views_per_minute', 'like_count', 'view_count', 'published_at', 'duration_sec', 'tags', 'thumbnail_url'
        ]]
        result_df.columns = [
            'video_id', 'channel_id', '제목', '채널명', 'VPH', '좋아요율(%)', '댓글율(%)', 
            '분당조회수', '좋아요', '총조회수', '게시일', '영상길이(초)', '태그', '썸네일URL'
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

@st.cache_data(ttl=600) # 10분 동안 캐시
def fetch_video_details(video_id: str):
    """
    특정 video_id에 대한 상세 정보를 DB에서 가져와 반환합니다.
    """
    try:
        print(f"DB에서 video_id: {video_id} 에 대한 상세 데이터를 가져옵니다...")
        
        # 1. 각 테이블에서 데이터 가져오기
        video_res = supabase.table('videos').select('video_id, channel_id, title, published_at, tags, duration_sec, thumbnail_url').eq('video_id', video_id).single().execute()
        # 최신 통계만 가져오도록 수정
        stats_res = supabase.table('video_stats').select('view_count, like_count, comment_count').eq('video_id', video_id).order('timestamp', desc=True).limit(1).execute()
        channel_res = supabase.table('channels').select('name').eq('channel_id', video_res.data['channel_id']).single().execute()

        video_data = video_res.data
        stats_data = stats_res.data[0] if stats_res.data else {}
        channel_data = channel_res.data

        if not video_data:
            st.warning(f"video_id: {video_id} 에 대한 데이터를 찾을 수 없습니다.")
            return None

        # 데이터 병합
        details = {**video_data, **stats_data, **channel_data}

        # 2. 시간 관련 데이터 처리
        details['published_at'] = pd.to_datetime(details['published_at'])
        now_utc = datetime.now(timezone.utc)
        details['hours_since_published'] = (now_utc - details['published_at']).total_seconds() / 3600
        
        # 3. 신규 지표 계산 (0으로 나누기 방지)
        details['VPH'] = int(round(details['view_count'] / (details['hours_since_published'] + 1)))
        details['like_rate'] = round((details['like_count'] / (details['view_count'] + 1)) * 100, 2)
        details['comment_rate'] = round((details['comment_count'] / (details['view_count'] + 1)) * 100, 2)
        details['views_per_minute'] = int(round(details['view_count'] / ((details['duration_sec'] / 60) + 0.01)))

        print(f"video_id: {video_id} 에 대한 상세 데이터 로딩 및 가공 완료.")
        return details

    except Exception as e:
        st.error(f"video_id: {video_id} 상세 데이터를 가져오는 중 오류가 발생했습니다: {e}")
        return None


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
            st.subheader("전체 영상 랭킹")
            
            # 헤더 컬럼
            col_header_idx, col_header_title, col_header_channel, col_header_vph, col_header_button = st.columns([0.5, 3, 1.5, 1, 1])
            with col_header_idx:
                st.markdown("<p style='font-size: 18px;'><b>순위</b></p>", unsafe_allow_html=True)
            with col_header_title:
                st.markdown("<p style='font-size: 18px;'><b>제목</b></p>", unsafe_allow_html=True)
            with col_header_channel:
                st.markdown("<p style='font-size: 18px;'><b>채널명</b></p>", unsafe_allow_html=True)
            with col_header_vph:
                st.markdown("<p style='font-size: 18px;'><b>VPH</b></p>", unsafe_allow_html=True)
            with col_header_button:
                st.write(" ") # 버튼 컬럼 헤더

            st.markdown("---")

            # 각 영상에 대한 정보와 버튼을 표시
            for index, row in video_ranking_data.iterrows():
                col_idx, col_title, col_channel, col_vph, col_button = st.columns([0.5, 3, 1.5, 1, 1])
                
                with col_idx:
                    st.markdown(f"<p style='font-size: 18px;'>{index}</p>", unsafe_allow_html=True)
                with col_title:
                    st.markdown(f"<p style='font-size: 18px;'>{row['제목']}</p>", unsafe_allow_html=True)
                with col_channel:
                    st.markdown(f"<p style='font-size: 18px;'>{row['채널명']}</p>", unsafe_allow_html=True)
                with col_vph:
                    st.markdown(f"<p style='font-size: 18px;'>{row['VPH']:,}</p>", unsafe_allow_html=True)
                with col_button:
                    if st.button("상세 보기", key=f"detail_button_{row['video_id']}"):
                        st.session_state['selected_video_id'] = row['video_id']
                        st.rerun()
            
            # 선택된 영상 상세 정보 표시
            if 'selected_video_id' in st.session_state and st.session_state.selected_video_id:
                selected_video_id = st.session_state.selected_video_id
                selected_row = video_ranking_data[video_ranking_data['video_id'] == selected_video_id].iloc[0]

                st.markdown("---") # 구분선
                st.subheader(f"🎬 {selected_row['제목']} 상세 분석")
                video_details = fetch_video_details(selected_video_id)

                if video_details:
                    st.markdown(f"<h3 style='font-size: 18px;'><a href='https://www.youtube.com/watch?v={video_details['video_id']}' target='_blank'>{video_details['title']}</a></h3>", unsafe_allow_html=True)
                    col1, col2 = st.columns([1, 2])
                    with col1:
                        if video_details.get('thumbnail_url'):
                            st.image(video_details['thumbnail_url'], caption=f"{video_details['title']} 영상 썸네일", use_container_width=True)
                        else:
                            st.info("영상 썸네일 이미지를 찾을 수 없습니다.")
                        st.markdown(f"<p style='font-size: 18px;'><b>채널명:</b> <a href='https://www.youtube.com/channel/{video_details['channel_id']}' target='_blank'>{video_details.get('name', 'N/A')}</a></p>", unsafe_allow_html=True)
                        st.markdown(f"<p style='font-size: 18px;'><b>게시일:</b> {video_details['published_at'].strftime('%Y년 %m월 %d일 %H시%M분')}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p style='font-size: 18px;'><b>영상 길이:</b> {video_details['duration_sec'] // 60}분 {video_details['duration_sec'] % 60}초</p>", unsafe_allow_html=True)
                    with col2:
                        st.markdown(f"<p style='font-size: 18px; color: #FF4B4B;'><b>총 조회수:</b> {video_details.get('view_count', 0):,}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p style='font-size: 18px; color: #FF4B4B;'><b>좋아요 수:</b> {video_details.get('like_count', 0):,}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p style='font-size: 18px; color: #FF4B4B;'><b>댓글 수:</b> {video_details.get('comment_count', 0):,}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p style='font-size: 18px; color: #26B2FF;'><b>VPH (시간당 조회수):</b> {video_details.get('VPH', 0):,}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p style='font-size: 18px; color: #26B2FF;'><b>좋아요율:</b> {video_details.get('like_rate', 0):.2f}%</p>", unsafe_allow_html=True)
                        st.markdown(f"<p style='font-size: 18px; color: #26B2FF;'><b>댓글율:</b> {video_details.get('comment_rate', 0):.2f}%</p>", unsafe_allow_html=True)
                        st.markdown(f"<p style='font-size: 18px; color: #26B2FF;'><b>분당 조회수:</b> {video_details.get('views_per_minute', 0):,}</p>", unsafe_allow_html=True)
                    
                    if video_details.get('tags'):
                        st.markdown(f"<p style='font-size: 18px;'><b>태그:</b> {', '.join(video_details['tags'])}</p>", unsafe_allow_html=True)
                    else:
                        st.info("이 영상에 대한 태그 정보가 없습니다.")
                else:
                    st.warning("선택된 영상의 상세 정보를 불러올 수 없습니다.")
            
        else:
            st.info("데이터를 표시할 수 없습니다. collector.py를 먼저 실행하여 데이터를 수집해주세요.")

    with tab4:
        st.header("채널 성장 분석 및 랭킹")
        st.write("이곳에 주간 구독자 성장률 기반의 채널 랭킹이 표시됩니다.")

# --- 앱 실행 ---
if __name__ == "__main__":
    if check_password():
        main_dashboard()
