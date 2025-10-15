# create_tables.py
# Supabase에 Searchlight 프로젝트의 테이블 스키마를 생성하는 스크립트입니다.

import os
from dotenv import load_dotenv
from supabase import create_client, Client

# .env 파일에서 환경 변수 로드
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    print("오류: .env 파일에서 Supabase URL 또는 ANON Key를 찾을 수 없습니다.")
    print("Supabase_URL과 SUPABASE_ANON_KEY가 올바르게 설정되었는지 확인해주세요.")
    exit(1)

# SQL Schema Definition
sql_schema = """
-- channels 테이블
CREATE TABLE channels (
    channel_id TEXT PRIMARY KEY,
    name TEXT,
    thumbnail_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    ai_persona JSONB, -- v2.0: AI가 추정한 시청자 페르소나
    tag_dna_consistency FLOAT8, -- v2.0: 태그 DNA 일관성 점수
    growth_acceleration FLOAT8 -- v2.0: 채널 성장 가속도 점수
);

-- channel_stats 테이블
CREATE TABLE channel_stats (
    stat_id BIGSERIAL PRIMARY KEY,
    channel_id TEXT REFERENCES channels(channel_id),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    subscriber_count BIGINT,
    view_count BIGINT
);

-- videos 테이블
CREATE TABLE videos (
    video_id TEXT PRIMARY KEY,
    channel_id TEXT REFERENCES channels(channel_id),
    title TEXT,
    published_at TIMESTAMPTZ,
    tags TEXT[],
    duration_sec INTEGER, -- 영상 길이 (초)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    content_format TEXT, -- v2.0: AI가 분류한 콘텐츠 포맷
    lifecycle_prediction TEXT, -- v2.0: AI가 예측한 영상 수명 주기
    momentum_score FLOAT8, -- v2.0: 모멘텀 점수
    viral_score INTEGER, -- v2.0: 바이럴 예측 점수
    ai_recipe JSONB, -- v2.0: AI가 생성한 콘텐츠 레시피
    ai_comment_analysis JSONB -- v2.0: AI 댓글 분석 결과
);

-- video_stats 테이블
CREATE TABLE video_stats (
    stat_id BIGSERIAL PRIMARY KEY,
    video_id TEXT REFERENCES videos(video_id),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    view_count BIGINT,
    like_count BIGINT,
    comment_count BIGINT
);

-- keywords 테이블
CREATE TABLE keywords (
    keyword TEXT PRIMARY KEY,
    saturation_index FLOAT8, -- v2.0: 콘텐츠 포화도 지수
    contagion_index FLOAT8, -- v2.0: 토픽 전염성 지수
    last_updated TIMESTAMPTZ DEFAULT NOW()
);
"""

# Supabase 클라이언트 초기화 (실제 DDL 실행은 수동으로)
# try:
#     supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
#     print("Supabase 클라이언트 연결 성공.")
#     # 여기서 DDL을 직접 실행하는 것은 supabase-py 클라이언트의 주 목적이 아님.
#     # 대신, SQL 스크립트를 출력하여 사용자가 직접 실행하도록 안내.
# except Exception as e:
#     print(f"Supabase 클라이언트 연결 실패: {e}")

print("--- Searchlight Supabase 테이블 생성 SQL 스크립트 ---")
print(sql_schema)
print("--------------------------------------------------")
print("\n위 SQL 스크립트를 복사하여 Supabase 대시보드의 'SQL Editor'에 붙여넣고 실행해주세요.")
print("실행이 완료되면 저에게 알려주세요.")
