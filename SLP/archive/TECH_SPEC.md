# Searchlight: 데이터 흐름 및 기능 구현 기술 보고서 (TECH_SPEC.md)

이 문서는 Searchlight의 각 기능이 어떤 기술 요소를 통해, 어떤 데이터 처리 단계를 거쳐 사용자에게 최종 인사이트로 제공되는지에 대한 구체적인 기술 과정을 정의한다.

---

## 1. 데이터 탐색 및 수집 (Data Exploration & Collection)

이 단계의 목표는 인터넷에 흩어져 있는 데이터 원석을 찾아내 우리의 DB로 가져오는 것이다.

*   **1.1. 스케줄링 (Scheduling)**
    *   **기술:** `GitHub Actions`
    *   **프로세스:**
        1.  GitHub 서버에서 매일 00:00 UTC(한국 시간 오전 9시)에 `.github/workflows/collector.yml` 파일에 정의된 스케줄(`cron`)이 자동으로 트리거된다.
        2.  할당된 가상 머신에 `Python` 환경이 구성되고, `pip install -r requirements.txt` 명령어로 필요한 모든 라이브러리가 설치된다.
        3.  `collector.py` 스크립트가 실행된다.

*   **1.2. 탐색 대상 정의 (Defining Exploration Targets)**
    *   **기술:** `Python`, `Pytrends`
    *   **프로세스:**
        1.  `collector.py`는 코드에 미리 정의된 15개의 '대분류 키워드'와, Supabase DB에 저장된 사용자의 '특화 키워드' 10개를 로드한다.
        2.  `pytrends` 라이브러리를 사용하여 Google Trends에서 '대한민국 일일 급상승 검색어' 5개를 API로 가져온다.
        3.  위 세 그룹을 합쳐, 그날 탐색을 수행할 총 30개의 키워드 리스트를 동적으로 생성한다.

*   **1.3. 데이터 수집 (Data Collection)**
    *   **기술:** `google-api-python-client` (YouTube Data API v3)
    *   **프로세스:**
        1.  생성된 30개 키워드 각각에 대해 `youtube.search().list()` API 함수를 호출하여, 48시간 내 게시된 영상 중 조회수 상위 25개의 `videoId` 목록을 얻는다. (총 API 비용: 30회 × 100 unit = 3,000 unit)
        2.  수집된 최대 750개의 `videoId`를 50개씩 묶어 `youtube.videos().list()` API 함수를 호출한다. 이 때 `part` 파라미터에 `snippet,statistics,contentDetails`를 명시한다.
        3.  API 응답 결과로 각 영상의 [제목, 채널ID, 게시일, 카테고리ID, 영상길이, 태그](`snippet`), [조회수, 좋아요 수, 댓글 수](`statistics`) 등의 상세 데이터를 추출한다. (총 API 비용: 15회 × 1 unit = 15 unit)

*   **1.4. 데이터 저장 (Data Storage)**
    *   **기술:** `Supabase` (Python client library)
    *   **프로세스:**
        1.  수집된 영상 및 채널의 기본 정보는 `supabase.table('videos').upsert(...)` 함수를 사용하여 DB에 저장하거나 업데이트한다. ('upsert'는 데이터가 없으면 새로 삽입하고, 있으면 업데이트하는 기능이다.)
        2.  시간에 따라 변하는 통계 정보(조회수, 좋아요 등)는 `supabase.table('video_stats').insert(...)` 함수를 사용하여, 현재의 타임스탬프와 함께 별도의 통계 테이블에 계속 삽입한다. 이것이 모든 시계열 분석의 기반이 된다.

---

## 2. 데이터 분석 (Data Analysis)

이 단계의 목표는 저장된 날데이터(Raw Data)를 가공하여 의미 있는 지표(Metric)와 인사이트(Insight)를 만드는 것이다. 이 과정은 데이터 수집 직후 `collector.py` 내부에서 또는 별도의 분석 스크립트에서 수행될 수 있다.

*   **2.1. 핵심 지표 계산 (Core Metric Calculation)**
    *   **기술:** `Python`, `Pandas`
    *   **프로세스:**
        1.  **VPH 계산:** `video_stats` 테이블에서 특정 영상의 초기 72시간 동안의 기록들을 `Pandas` DataFrame으로 불러온다. 시간대별 조회수 증가량을 계산하여 VPH를 산출한다.
        2.  **참여도 점수 계산:** 최신 `video_stats` 기록에서 `(좋아요 + 댓글 * 5) / 조회수` 공식을 적용하여 점수를 계산한다.
        3.  **모멘텀 점수 계산:** 계산된 VPH와 참여도 점수를 정규화(0~1 값으로 변환)하고, 미리 정해진 가중치를 곱한 뒤, 게시일로부터의 경과 시간에 따른 '시간 감쇠 팩터'를 곱하여 최종 점수를 산출한다.

*   **2.2. AI 기반 추론 (AI-based Inference)**
    *   **기술:** `Google Gemini API`
    *   **프로세스:**
        1.  분석할 영상의 [제목, 설명, 태그] 텍스트를 Gemini API에 전달하고, "이 영상의 주 시청자층을 '키즈, 10대, 20대 남성...' 중에서 추론해줘" 라는 프롬프트를 보낸다.
        2.  API 응답으로 '타겟 시청자' 정보를 얻어 DB에 저장한다.
        3.  계산된 VPH, 모멘텀 점수와 함께 "이 영상의 바이럴 가능성을 100점 만점으로 예측해줘" 라는 프롬프트를 보내 '바이럴 예측 점수'를 얻고 DB에 저장한다.

---

## 3. 결과 산출 및 시각화 (Result Derivation & Visualization)

이 단계의 목표는 분석된 결과를 사용자가 이해하기 쉬운 형태로 웹 화면에 보여주는 것이다.

*   **3.1. 데이터 조회 (Data Retrieval)**
    *   **기술:** `Streamlit`, `Supabase` (Python client library)
    *   **프로세스:**
        1.  사용자가 웹 브라우저에서 Searchlight에 접속하면 `app.py`가 실행된다.
        2.  `app.py`는 `supabase.table('videos').select('*').order('momentum_score', desc=True).limit(100)` 와 같은 함수를 사용하여, 분석이 완료된 데이터베이스에서 필요한 데이터를 실시간으로 조회한다.

*   **3.2. 시각화 (Visualization)**
    *   **기술:** `Streamlit`, `Pandas`
    *   **프로세스:**
        1.  Supabase에서 가져온 데이터를 `Pandas DataFrame`으로 변환한다.
        2.  Streamlit의 내장 함수들을 사용하여 이 DataFrame을 사용자가 볼 수 있는 화면 요소로 변환한다.
            *   `st.dataframe(df)` → '영상 분석' 탭의 상호작용 가능한 표를 생성한다.
            *   `st.line_chart(df_history)` → '채널 상세 보고서'의 시계열 성장 그래프를 그린다.
            *   `st.metric(...)` → '위클리 리포트'의 요약 카드를 만듭니다.
            *   `st.selectbox(...)`, `st.slider(...)` → 사용자가 데이터를 필터링할 수 있는 UI 컨트롤을 생성한다.
