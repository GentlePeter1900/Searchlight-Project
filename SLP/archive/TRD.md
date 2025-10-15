# TRD: Searchlight (서치라이트) - 기술 요구사항 정의서

## 1. 개요 (Introduction)
본 문서는 'Searchlight' 프로젝트의 기술적 아키텍처, 구현 방식, 데이터 모델, 그리고 배포 전략을 정의한다. PRD에 명시된 요구사항을 기술적으로 구현하기 위한 설계도 역할을 한다.

## 2. 시스템 아키텍처 (System Architecture)
본 시스템은 3-Tier 아키텍처를 기반으로 하며, 각 컴포넌트는 비용 최소화를 위해 무료 티어 서비스 위에서 동작한다.

```
+----------------------+      (HTTPS)      +-------------------------+      (DB Connection)      +---------------------+
|   User (Creator)     | <---------------> |  Streamlit Cloud (Web)  | <----------------------> |  Supabase (DB)      |
| (Web Browser)        |                   |   - Frontend (UI)       |                          |  - PostgreSQL       |
+----------------------+                   |   - Data Visualization  |                          |  - Data Storage     |
                                           +-------------------------+                          +----------^----------+
                                                                                                            |
                                                                                              (Data Write)  |
                                                                           +--------------------------------|----------------+
                                                                           |         GitHub Actions (Backend)                |
                                                                           | - Python Data Collection Script (Scheduled)     |
                                                                           | - Calls YouTube/Google Trends APIs              |
                                                                           +-------------------------------------------------+
```

- **Frontend:** Streamlit 애플리케이션. Streamlit Community Cloud를 통해 호스팅 및 배포.
- **Backend (Data Collection):** Python 스크립트. GitHub Actions에 의해 스케줄링되어 주기적으로 실행.
- **Database:** Supabase PostgreSQL. 수집된 모든 데이터를 저장.

## 3. 기술 스택 (Technology Stack)
- **언어:** Python 3.10+
- **프레임워크:** Streamlit
- **데이터베이스:** PostgreSQL (on Supabase)
- **데이터 수집/처리:**
    - `google-api-python-client`: YouTube Data API v3 연동
    - `pandas`: 데이터 가공 및 분석
    - `pytrends`: Google Trends 데이터 수집
- **백엔드 실행 환경:** GitHub Actions (Scheduled Cron Job)
- **배포 환경:** Streamlit Community Cloud

## 4. 데이터 모델 (Data Schema)
Supabase PostgreSQL에 생성될 주요 테이블의 스키마는 다음과 같다.

- **`channels`**
    - `channel_id` (PK, TEXT): 유튜브 채널 ID
    - `name` (TEXT): 채널명
    - `thumbnail_url` (TEXT): 썸네일 URL
    - `created_at` (TIMESTAMPTZ): 레코드 생성 시각
    - `updated_at` (TIMESTAMPTZ): 레코드 업데이트 시각

- **`channel_stats`**
    - `stat_id` (PK, BIGSERIAL)
    - `channel_id` (FK, TEXT): `channels.channel_id` 참조
    - `timestamp` (TIMESTAMPTZ): 데이터 수집 시각
    - `subscriber_count` (BIGINT): 구독자 수
    - `view_count` (BIGINT): 누적 조회수

- **`videos`**
    - `video_id` (PK, TEXT): 유튜브 영상 ID
    - `channel_id` (FK, TEXT): `channels.channel_id` 참조
    - `title` (TEXT): 영상 제목
    - `published_at` (TIMESTAMPTZ): 영상 게시 시각
    - `tags` (TEXT[]): 영상 태그 배열

- **`video_stats`**
    - `stat_id` (PK, BIGSERIAL)
    - `video_id` (FK, TEXT): `videos.video_id` 참조
    - `timestamp` (TIMESTAMPTZ): 데이터 수집 시각
    - `view_count` (BIGINT): 조회수
    - `like_count` (BIGINT): 좋아요 수
    - `comment_count` (BIGINT): 댓글 수

## 5. API 연동 (API Integration)
- **YouTube Data API v3:**
    - `search.list`: 특정 키워드로 영상/채널 검색
    - `videos.list`: 영상의 상세 정보 및 통계(조회수, 좋아요 등) 조회
    - `channels.list`: 채널의 상세 정보 및 통계(구독자 수 등) 조회
    - `videoCategories.list`: 카테고리 목록 조회
- **Pytrends (Google Trends Unofficial API):**
    - `interest_over_time`: 키워드의 시간별 관심도 추이
    - `related_queries`: 연관 및 급상승 검색어

## 6. 핵심 로직 구현 (Core Logic)
- **데이터 수집:**
    - GitHub Actions의 `schedule` 트리거(`cron: '0 0 * * *'`)를 사용하여 매일 자정(UTC)에 데이터 수집 스크립트(`collect_data.py`)를 실행한다.
    - 스크립트는 지정된 채널 및 키워드 목록에 대해 API를 호출하고, 수집된 데이터를 Supabase DB에 저장한다.
- **핵심 지표 계산:**
    - **VPH (Views Per Hour):** `video_stats` 테이블에서 영상 게시 후 초기 24시간 동안의 `view_count` 변화량을 시간으로 나누어 계산.
    - **Engagement Rate:** `(like_count + comment_count) / view_count`
    - **Momentum Score:** `(w1 * VPH_norm) + (w2 * ER_norm)) * time_decay_factor`. 가중치(w1, w2)와 정규화(norm), 시간 감쇠 팩터(time_decay)는 초기값 설정 후 테스트를 통해 튜닝한다.

## 7. 배포 및 보안 (Deployment & Security)
- **Frontend (Streamlit):**
    - `main` 브랜치에 코드가 푸시되면 Streamlit Community Cloud가 자동으로 앱을 재배포한다.
    - `requirements.txt` 파일에 필요한 라이브러리를 명시한다.
- **Backend (GitHub Actions):**
    - `.github/workflows/collector.yml` 파일에 스케줄 및 실행 스크립트를 정의한다.
- **보안:**
    - YouTube API 키, Supabase DB 접속 정보 등 모든 민감 정보는 GitHub Secrets 및 Streamlit Secrets에 저장한다. 코드에 하드코딩하지 않는다.
    - Streamlit 앱에는 간단한 비밀번호 기반의 인증 로직을 추가하여 허가된 사용자(크리에이터)만 접근할 수 있도록 한다.
