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

def fetch_popular_videos(api_key, category_id, region_code='KR', max_results=15):
    """
    지정된 카테고리에 대해 유튜브 인기 급상승 동영상을 수집합니다.
    """
    videos_to_insert = []
    channels_to_insert = []
    stats_to_insert = []
    existing_channel_ids = set() # 중복 채널 저장을 피하기 위함

    try:
        request = youtube.videos().list(
            part='snippet,contentDetails,statistics',
            chart='mostPopular',
            regionCode=region_code,
            videoCategoryId=category_id,
            maxResults=max_results
        )
        response = request.execute()

        for item in response.get('items', []):
            # 영상 데이터
            video_data = {
                "video_id": item["id"],
                "channel_id": item["snippet"]["channelId"],
                "title": item["snippet"]["title"],
                "published_at": item["snippet"]["publishedAt"],
                "tags": item["snippet"].get("tags", []), # tags가 없을 수도 있음
                "duration_sec": parse_iso8601_duration(item["contentDetails"]["duration"]),
                "thumbnail_url": item["snippet"]["thumbnails"]["high"]["url"] # 썸네일 URL 추가
            }
            videos_to_insert.append(video_data)

            # 채널 정보 (중복 방지)
            if item["snippet"]["channelId"] not in existing_channel_ids:
                channel_data = {
                    "channel_id": item["snippet"]["channelId"],
                    "name": item["snippet"]["channelTitle"],
                    "thumbnail_url": "" # 채널 썸네일은 별도 API 호출 필요 시 추가 (현재는 빈 값)
                }
                channels_to_insert.append(channel_data)
                existing_channel_ids.add(item["snippet"]["channelId"])

            # 통계 정보
            stats_to_insert.append({
                "video_id": item["id"],
                "view_count": item["statistics"].get("viewCount", 0),
                "like_count": item["statistics"].get("likeCount", 0),
                "comment_count": item["statistics"].get("commentCount", 0),
            })

    except Exception as e:
        print(f"    -> 카테고리 ID [{category_id}] 수집 실패. (에러: {e})")
        # 실패 시 빈 리스트 반환
        return [], [], []
    
    return videos_to_insert, channels_to_insert, stats_to_insert

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
            video_data = {
                "video_id": item["id"],
                "channel_id": item["snippet"]["channelId"],
                "title": item["snippet"]["title"],
                "published_at": item["snippet"]["publishedAt"],
                "tags": item["snippet"].get("tags", []), # tags가 없을 수도 있음
                "duration_sec": parse_iso8601_duration(item["contentDetails"]["duration"]),
                "thumbnail_url": item["snippet"]["thumbnails"]["high"]["url"] # 썸네일 URL 추가
            }
            videos_to_insert.append(video_data)

            # 채널 정보 수집 (중복 방지)
            if item["snippet"]["channelId"] not in existing_channel_ids:
                channel_data = {
                    "channel_id": item["snippet"]["channelId"],
                    "name": item["snippet"]["channelTitle"],
                    "thumbnail_url": "" # 채널 썸네일은 별도 API 호출 필요 시 추가
                }
                channels_to_insert.append(channel_data)
                existing_channel_ids.add(item["snippet"]["channelId"])

            # 통계 정보 수집
            stats_to_insert.append({
                "video_id": item["id"],
                "view_count": item["statistics"].get("viewCount", 0),
                "like_count": item["statistics"].get("likeCount", 0),
                "comment_count": item["statistics"].get("commentCount", 0),
            })

    return videos_to_insert, channels_to_insert, stats_to_insert

def save_videos_to_db(videos_data, channels_data, stats_data):
    """
    수집된 영상, 채널, 통계 데이터를 Supabase DB에 저장합니다.
    """
    print("DB에 데이터 저장을 시작합니다...")
    try:
        # 채널 데이터 저장 (중복 시 업데이트)
        if channels_data:
            supabase.table('channels').upsert(channels_data, on_conflict='channel_id').execute()
            print(f"{len(channels_data)}개 채널 정보 저장/업데이트 완료.")

        # 영상 데이터 저장 (중복 시 업데이트)
        if videos_data:
            supabase.table('videos').upsert(videos_data, on_conflict='video_id').execute()
            print(f"{len(videos_data)}개 영상 정보 저장/업데이트 완료.")

        # 통계 데이터 저장 (항상 새로 추가)
        if stats_data:
            supabase.table('video_stats').insert(stats_data).execute()
            print(f"{len(stats_data)}개 영상 통계 저장 완료.")

        print("DB 저장 완료.")
    except Exception as e:
        print(f"DB 저장 중 오류 발생: {e}")


if __name__ == "__main__":
    load_dotenv()
    YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

    if not all([YOUTUBE_API_KEY, SUPABASE_URL, SUPABASE_ANON_KEY]):
        print("오류: 필수 환경 변수가 .env 파일에 설정되지 않았습니다.")
        exit(1)

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY) # youtube 클라이언트 초기화

    all_videos, all_channels, all_stats = [], [], []
    failed_categories = []

    print("\n========== 데이터 수집 파이프라인 시작 ==========")
    for category_id in TARGET_CATEGORY_IDS:
        print(f"카테고리 ID {category_id}의 인기 동영상 수집 중...")
        videos, channels, stats = fetch_popular_videos(YOUTUBE_API_KEY, category_id, region_code='KR', max_results=15)
        if videos:
            all_videos.extend(videos)
            all_channels.extend(channels)
            all_stats.extend(stats)
        else:
            failed_categories.append(category_id)

    # 중복 채널 제거
    unique_channels = {}
    for channel in all_channels:
        unique_channels[channel["channel_id"]] = channel
    final_channels = list(unique_channels.values())

    print(f"\n총 {len(all_videos)}개의 영상을 성공적으로 수집했습니다.")
    if failed_categories:
        print(f"실패한 카테고리 ID: {failed_categories}")
        print("(해당 카테고리는 '인기 급상승' 차트를 제공하지 않을 수 있습니다.)")

    save_videos_to_db(all_videos, final_channels, all_stats)
    print("\n========== 데이터 수집 파이프라인 완료 ==========")
