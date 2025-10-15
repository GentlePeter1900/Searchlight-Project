# collector.py
# 데이터 수집을 담당하는 백엔드 스크립트입니다.

import os
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client
from googleapiclient.discovery import build
from pytrends.request import TrendReq

# --- .env 파일 로드 및 클라이언트 초기화 ---
load_dotenv()

try:
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY") # .env 파일의 키 이름과 일치시킵니다.
    YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")

    if not all([SUPABASE_URL, SUPABASE_KEY, YOUTUBE_API_KEY]):
        raise ValueError("필수 환경 변수가 .env 파일에 설정되지 않았습니다. (SUPABASE_URL, SUPABASE_ANON_KEY, YOUTUBE_API_KEY)")

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
    pytrends = TrendReq(hl='ko-KR', tz=540)
    
    print("Supabase, YouTube, Google Trends 클라이언트 초기화 완료.")
    
except Exception as e:
    print(f"클라이언트 초기화 중 에러 발생: {e}")


# --- 상수 정의 ---
# 최종 확정된 5개 카테고리 ID
TARGET_CATEGORY_IDS = ['15', '22', '23', '26', '28'] # 반려동물/동물, 인물/블로그, 코미디, 노하우/스타일, 과학기술

def fetch_popular_videos(region_code='KR', max_per_category=10):
    """
    지정된 카테고리 목록에 대해 유튜브 인기 급상승 동영상을 수집합니다.
    """
    print(f"선택된 {len(TARGET_CATEGORY_IDS)}개 카테고리에 대해 인기 동영상 수집을 시작합니다...")
    
    all_videos = []
    failed_categories = []

    for category_id in TARGET_CATEGORY_IDS:
        try:
            print(f"  - 카테고리 ID [{category_id}] 수집 중...")
            request = youtube.videos().list(
                part='snippet,contentDetails,statistics',
                chart='mostPopular',
                regionCode=region_code,
                videoCategoryId=category_id,
                maxResults=max_per_category
            )
            response = request.execute()
            all_videos.extend(response.get('items', []))
        except Exception as e:
            print(f"    -> 카테고리 ID [{category_id}] 수집 실패. (에러: {e})")
            failed_categories.append(category_id)
    
    print(f"\n총 {len(all_videos)}개의 영상을 성공적으로 수집했습니다.")

    if failed_categories:
        print(f"\n실패한 카테고리 ID: {failed_categories}")
        print("(해당 카테고리는 '인기 급상승' 차트를 제공하지 않을 수 있습니다.)")
    
    # --- 검증 단계: 수집된 영상 제목 일부를 출력 ---
    if all_videos:
        print("\n--- 수집된 영상 제목 (상위 5개) ---")
        for i, video in enumerate(all_videos[:5]):
            # 제목이 너무 길 경우 일부만 표시하고, 인코딩 오류 방지
            title = video['snippet']['title']
            title_short = (title[:70] + '...') if len(title) > 70 else title
            print(f"{i+1}. {title_short.encode('cp949', 'replace').decode('cp949')}")
        if len(all_videos) > 5:
            print("...")
        # -----------------------------------------

    return all_videos

def parse_iso8601_duration(duration_str):
    """ISO 8601 기간 문자열을 초로 변환합니다. (예: PT1M30S -> 90)"""
    if not duration_str:
        return 0
    try:
        # pandas의 to_timedelta를 사용하여 간편하게 변환
        return int(pd.to_timedelta(duration_str).total_seconds())
    except Exception:
        return 0

def save_videos_to_db(videos_list):
    """
    수집된 영상 리스트를 DB의 각 테이블에 맞게 가공하고 저장합니다.
    """
    if not videos_list:
        print("DB에 저장할 영상이 없습니다.")
        return

    print("\nDB 저장을 위해 데이터 가공을 시작합니다...")

    channels_to_upsert = {}
    videos_to_upsert = []
    stats_to_insert = []

    for video in videos_list:
        channel_id = video['snippet']['channelId']
        if channel_id not in channels_to_upsert:
            channels_to_upsert[channel_id] = {
                'channel_id': channel_id,
                'name': video['snippet']['channelTitle']
            }
        videos_to_upsert.append({
            'video_id': video['id'],
            'channel_id': channel_id,
            'title': video['snippet']['title'],
            'published_at': video['snippet']['publishedAt'],
            'tags': video['snippet'].get('tags'),
            'duration_sec': parse_iso8601_duration(video['contentDetails'].get('duration'))
        })
        stats = video.get('statistics', {})
        stats_to_insert.append({
            'video_id': video['id'],
            'view_count': int(stats.get('viewCount', 0)),
            'like_count': int(stats.get('likeCount', 0)),
            'comment_count': int(stats.get('commentCount', 0))
        })

    print(f"  - 가공 완료: {len(channels_to_upsert)}개 채널, {len(videos_to_upsert)}개 영상, {len(stats_to_insert)}개 통계")

    try:
        print("\nDB에 데이터를 저장합니다...")
        if channels_to_upsert:
            supabase.table('channels').upsert(list(channels_to_upsert.values())).execute()
            print("  - [성공] 채널 정보 저장 완료.")
        if videos_to_upsert:
            supabase.table('videos').upsert(videos_to_upsert).execute()
            print("  - [성공] 영상 정보 저장 완료.")
        if stats_to_insert:
            supabase.table('video_stats').insert(stats_to_insert).execute()
            print("  - [성공] 통계 정보 저장 완료.")
        print("\n모든 데이터가 성공적으로 DB에 저장되었습니다.")
    except Exception as e:
        print(f"\nDB 저장 중 에러 발생: {e}")

def fetch_channel_stats(channel_ids):
    """ 채널의 기본 통계를 수집합니다. """
    # print(f"\n(미구현) {channel_ids} 채널의 통계를 수집합니다.")
    pass

def fetch_google_trends(keywords):
    """ 구글 트렌드 데이터를 수집합니다. """
    # print(f"(미구현) '{keywords}' 키워드에 대한 구글 트렌드를 수집합니다.")
    pass

def main():
    """ 메인 데이터 수집 파이프라인 """
    print("\n========== 데이터 수집 파이프라인 시작 ==========")
    
    # 1. 인기 동영상 수집
    videos = fetch_popular_videos()
    
    # 2. 수집된 데이터를 DB에 저장
    if videos:
        save_videos_to_db(videos)
    
    # 3. (향후 구현) 채널 상세 통계 수집
    # 4. (향후 구현) 구글 트렌드 데이터 수집
    
    print("\n========== 데이터 수집 파이프라인 완료 ==========")

if __name__ == "__main__":
    main()
