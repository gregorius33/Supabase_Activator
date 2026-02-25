---
name: supabase_keepalive_github_actions
overview: Supabase 프로젝트가 1주일 이상 비활성화되어 일시 중지되는 것을 막기 위해, GitHub Actions와 Python 스크립트로 정해진 요일/시간에 Supabase 테이블에 자동으로 기록을 남기는 구조를 만든다.
todos:
  - id: design-heartbeat-table
    content: Supabase에 heartbeat용 테이블 구조 정의 및 생성 방법 정리
    status: completed
  - id: python-script-bulchimbeon
    content: Supabase REST API로 heartbeat 레코드를 삽입하는 Python 스크립트 BulChimBeon.py 설계
    status: completed
  - id: github-secrets-mapping
    content: Supabase URL과 Service Role Key를 GitHub Actions Secrets로 사용하는 구조 설계
    status: completed
  - id: workflow-cron-schedule
    content: 매주 월/목 오전 9시 KST에 맞는 GitHub Actions cron 스케줄과 워크플로우 단계 정의
    status: completed
  - id: test-and-verify
    content: workflow_dispatch를 통한 테스트 시나리오와 Supabase 테이블에서 결과 확인 방법 정리
    status: completed
isProject: false
---

### 목표

- **Supabase 프로젝트**가 1주일 동안 활동이 없어서 자동으로 일시 중지되는 것을 막기 위해,
- **GitHub Actions + Python 스크립트(`BulChimBeon.py`)**로
- **매주 월요일, 목요일 오전 9시(한국 시간, KST)**에 Supabase에 간단한 DB 업데이트(heartbeat)를 수행한다.

---

### 전체 구조 요약

- **GitHub 저장소** 하나 생성 (예: `supabase-bulchimbeon`)
- 저장소 안에 **Python 스크립트 `BulChimBeon.py`** 작성
  - Supabase REST API를 사용해서 특정 테이블(예: `heartbeat`)에 `last_ping` 값을 현재 시간으로 INSERT 또는 UPSERT
- GitHub 저장소의 **Secrets**에 Supabase 접속 정보(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY 등) 저장
- `.github/workflows/BulChimBeon.yml` GitHub Actions 워크플로우 파일을 만들어
  - **cron 스케줄**로 매주 월/목 9시(KST)에 실행되도록 설정
  - Python 세팅 후 `BulChimBeon.py` 실행

시간대 변환: KST(UTC+9) 기준 오전 9시 → **UTC 0시**

- GitHub Actions cron 표현식: `0 0 * * 1,4` (매주 월요일, 목요일 00:00 UTC)

---

### 1. Supabase 쪽 준비 계획

- **1-1. Heartbeat 테이블 설계 (추천)**
  - Supabase 프로젝트에서 SQL Editor로 다음과 비슷한 테이블 하나 생성 (한 번만 수행):
    - 테이블 이름: `heartbeat`
    - 주요 컬럼 예시:
      - `id` (uuid, PK, default `uuid_generate_v4()`)
      - `last_ping` (timestamptz, not null)
      - `note` (text, nullable) – 선택 사항
  - RLS(행 레벨 보안)를 사용하는 경우, **Service Role Key**로만 접근할 것이므로, RLS 정책은 최소한으로 설정하거나, Service Role에는 제한을 느슨하게 두어도 됨.
- **1-2. Supabase 키 및 URL 정리**
  - Supabase Dashboard → Project Settings → API에서 다음 값 확인:
    - `SUPABASE_URL` (예: `https://xxxx.supabase.co`)
    - `SUPABASE_SERVICE_ROLE_KEY` (Service role secret – **노출 주의, GitHub에는 Secret으로만 저장**)
  - 이 값들은 나중에 GitHub 리포지토리의 **Secrets**로 설정한다.

---

### 2. GitHub 리포지토리 구조 계획

- 루트 디렉터리 예시:
  - `BulChimBeon.py` (Supabase에 heartbeat를 보내는 Python 스크립트)
  - `requirements.txt` (필요한 Python 패키지 목록 – 예: `requests`)
  - `.github/workflows/BulChimBeon.yml` (GitHub Actions 워크플로우 파일)
- **2-1. `BulChimBeon.py` 스크립트 역할**
  - 환경변수에서 다음 값들을 읽음:
    - `SUPABASE_URL`
    - `SUPABASE_SERVICE_ROLE_KEY`
    - (옵션) `SUPABASE_SCHEMA` (기본값 `public`)
    - (옵션) `SUPABASE_TABLE` (기본값 `heartbeat`)
  - Supabase REST endpoint(`/rest/v1/{테이블명}`)로 `POST` 요청을 보내 현재 시간을 담은 레코드를 INSERT 또는 UPSERT
    - 예: `{"last_ping": <현재 UTC 시간>, "note": "GitHub Actions BulChimBeon"}`
    - 헤더: `apikey`, `Authorization: Bearer <service_role_key>`, `Content-Type: application/json`, `Prefer: return=representation`
  - 요청 성공/실패를 로그로 출력해서, Actions에서 결과를 쉽게 확인할 수 있게 함.
- **2-2. `requirements.txt`**
  - 최소 구성:
    - `requests` (HTTP 요청)
  - 필요하다면 나중에 로깅/타임존 관련 패키지 추가 가능.

---

### 3. GitHub Secrets 설정 계획

- GitHub 리포지토리 → Settings → Secrets and variables → Actions에서 다음 Secrets 추가:
  - `SUPABASE_URL` : Supabase 프로젝트 URL
  - `SUPABASE_SERVICE_ROLE_KEY` : 서비스 롤 키
  - (옵션) `SUPABASE_SCHEMA` : 기본값 `public`이면 생략 가능
  - (옵션) `SUPABASE_TABLE` : 기본값 `heartbeat`이면 생략 가능
- 워크플로우에서는 이 Secrets를 환경변수 형태로 Python 스크립트에 전달한다.

---

### 4. GitHub Actions 워크플로우(`BulChimBeon.yml`) 계획

- 위치: `.github/workflows/BulChimBeon.yml`
- 주요 내용:
  - **트리거 설정**
    - `on.schedule` → cron: `0 0 * * 1,4` (월/목 00:00 UTC → KST 09:00)
    - (옵션) `on.workflow_dispatch` 도 추가해서, 수동으로도 테스트 실행 가능하게 함.
  - **잡 설정**
    - `runs-on: ubuntu-latest`
    - 단계:
      1. `actions/checkout`으로 코드 체크아웃
      2. `actions/setup-python`으로 Python 3.x 설치
      3. `pip install -r requirements.txt`
      4. 환경변수에 GitHub Secrets를 매핑한 뒤 `python BulChimBeon.py` 실행
  - 실패 시 GitHub Actions에서 알람(빨간불)로 확인 가능.

---

### 5. 테스트 및 검증 계획

- **5-1. 수동 실행 테스트**
  - `workflow_dispatch`를 이용해서 GitHub Actions 탭에서 직접 워크플로우를 한 번 실행.
  - 로그에서 Python 스크립트 출력 확인 (Supabase 요청 성공 여부 확인).
- **5-2. Supabase에서 결과 확인**
  - Supabase Table Editor에서 `heartbeat` 테이블을 열어, `last_ping`이 새로 들어왔는지 확인.
  - 몇 분 후 다시 GitHub Actions 스케줄이 제대로 도는지, 월/목 아침 이후에 레코드가 추가되거나 갱신되는지 확인.

---

### 6. 유지보수 및 확장 아이디어 (선택)

- Supabase 측 정책이 바뀌거나, 주기가 더 촘촘해야 한다고 느껴지면:
  - cron 스케줄을 `0 0` * * * (매일 00:00 UTC → 매일 오전 9시 KST) 등으로 변경.
- 여러 Supabase 프로젝트를 동시에 살려 두고 싶으면:
  - 하나의 `BulChimBeon.py`에서 프로젝트별 설정 리스트를 돌면서 여러 URL/KEY에 대해 요청 보내도록 확장.
- 로그를 더 자세히 남기고 싶으면:
  - Python `logging` 모듈을 사용해 성공/실패 이유를 더 구조적으로 출력.

