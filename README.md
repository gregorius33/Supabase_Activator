## BulChimBeon (Supabase 자동 깨우기)

이 저장소는 **Supabase 프로젝트가 1주일 이상 비활성화되어 일시 중지되는 것**을 막기 위해,
GitHub Actions와 Python 스크립트로 **주기적으로 Supabase에 간단한 DB 기록을 남기는** 용도의 프로젝트입니다.

- 사용하는 테이블 이름: **`BulChimBeon`** (프로젝트별로 다른 테이블 이름 지정 가능)
- **단일 프로젝트** 또는 **여러 프로젝트** 모두 지원합니다.
- 실행 주기(기본): **매주 월요일, 목요일 오전 9시 (한국 시간, KST)**  
  - GitHub Actions cron 기준: `0 0 * * 1,4` (UTC 0시 → KST 9시)

---

## 1. Supabase 테이블 `BulChimBeon` 생성

Supabase 대시보드에서 **SQL Editor**를 열고, 아래와 비슷한 SQL을 한 번 실행하여
`BulChimBeon` 테이블을 만들어 주세요.

```sql
create table if not exists public."BulChimBeon" (
  id uuid primary key default uuid_generate_v4(),
  last_ping timestamptz not null,
  note text
);
```

- 스키마는 기본값인 `public`을 가정합니다.
- **동작:** 첫 실행 시 한 행을 **INSERT**하고, 이후 실행부터는 같은 행을 **UPDATE**합니다.  
  따라서 테이블에는 항상 **한 행만** 유지되며, `last_ping`이 매 실행 시각(UTC)으로 갱신됩니다.
- Supabase REST API의 UPSERT(`Prefer: resolution=merge-duplicates`)를 사용하며, 고정된 `id` 한 개로 같은 행을 덮어씁니다.

> RLS(행 레벨 보안)를 사용하는 경우, 이 프로젝트는 **Service Role Key**로만 접근합니다.  
> Service Role Key는 서버용 비밀키이므로, **절대 클라이언트 코드에 넣지 말고 GitHub Secrets로만 사용**하세요.

---

## 2. 환경 변수 / GitHub Secrets 설정

### Supabase에서 URL과 API 키 얻기

1. [Supabase 대시보드](https://supabase.com/dashboard)에 로그인한 뒤, 사용할 **프로젝트**를 선택합니다.
2. 왼쪽 사이드바 맨 아래 **톱니바퀴 아이콘** → **Project Settings**로 이동합니다.
3. 왼쪽 메뉴에서 **API**를 클릭합니다.
4. **Project API keys** 섹션에서:
   - **Project URL** → 이 값이 `SUPABASE_URL`입니다. (예: `https://xxxx.supabase.co`)
   - **서버용 비밀 키**는 다음 중 하나를 사용합니다.
     - **새 API 키 사용 시:** **Secret** 키 (`sb_secret_...` 로 시작) 옆 **Reveal** → 이 값을 GitHub Secret `SUPABASE_SERVICE_ROLE_KEY` 또는 `SUPABASE_SECRET_KEY`에 넣습니다.
     - **레거시 키 사용 시:** **service_role** 키 옆 **Reveal** → 이 값을 `SUPABASE_SERVICE_ROLE_KEY`에 넣습니다.

> **"Legacy API keys are disabled" 오류가 나는 경우**  
> Supabase에서 레거시 키(anon, service_role)를 끈 프로젝트입니다. 같은 **Project Settings → API** 페이지에서 **Secret** 키(`sb_secret_...`)를 복사해, GitHub 리포지토리 Secrets에 **`SUPABASE_SERVICE_ROLE_KEY`** 이름으로 그대로 넣어 주세요. (기존 이름 유지해도 동작합니다.)

> **주의:** Secret / service_role 키는 RLS를 우회할 수 있는 강력한 비밀키입니다.  
> 브라우저나 앱 코드에 넣지 말고, **GitHub Secrets처럼 서버/CI 전용**으로만 사용하세요.

GitHub 리포지토리에서:

1. `Settings` 탭 이동
2. 왼쪽 메뉴에서 `Secrets and variables` → `Actions` 선택
3. 아래 중 **하나의 방식**으로 설정합니다.

#### 방식 A: 단일 프로젝트 (기존과 동일)

- `SUPABASE_URL` : Supabase 프로젝트 URL
- `SUPABASE_SERVICE_ROLE_KEY` 또는 `SUPABASE_SECRET_KEY` : 서버용 비밀 키
- (선택) `SUPABASE_TABLE` : 기본값 `BulChimBeon`을 그대로 쓸 경우 생략 가능

#### 방식 B: 2개 이상의 프로젝트 (다중 프로젝트)

- **`SUPABASE_PROJECTS`** 하나만 추가합니다. 값은 **JSON 배열** 문자열입니다.
- 각 항목은 `url`, `secret_key` 가 필수이고, `table` 은 선택(기본값 `BulChimBeon`)입니다.

예시 (한 줄로 넣어도 됨):

```json
[
  {"url": "https://프로젝트1.supabase.co", "secret_key": "sb_secret_..."},
  {"url": "https://프로젝트2.supabase.co", "secret_key": "sb_secret_..."}
]
```

- `SUPABASE_PROJECTS` 가 설정되어 있으면 **방식 A는 무시**되고, 배열에 적은 모든 프로젝트에 순서대로 UPSERT 요청을 보냅니다.
- 각 프로젝트의 Supabase 대시보드 → **Project Settings → API**에서 **Project URL**과 **Secret** 키를 복사해 위 형식으로 넣으면 됩니다.

Python 스크립트 `BulChimBeon.py`는 위 값들을 **환경 변수**로부터 읽어와 Supabase REST API를 호출합니다.

---

## 3. Python 스크립트 개요 (`BulChimBeon.py`)

이 스크립트는 다음과 같이 동작합니다.

1. **설정 읽기**
   - `SUPABASE_PROJECTS` (JSON 배열)가 있으면 → 그 목록에 있는 **모든 프로젝트**에 대해 순서대로 요청을 보냅니다.
   - 없으면 → 기존처럼 `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`(또는 `SUPABASE_SECRET_KEY`) 로 **단일 프로젝트**만 대상으로 합니다.
2. 각 대상에 대해 `SUPABASE_URL/rest/v1/테이블명` 엔드포인트로 **UPSERT** 요청을 보냅니다.
3. 요청 바디에는:
   - `id`: 고정 UUID (한 행만 유지하기 위한 키)
   - `last_ping`: 현재 UTC 시각 (ISO 8601 문자열)
   - `note`: `"GitHub Actions BulChimBeon"` 같은 간단한 문자열
4. 첫 실행 시 해당 행이 없으면 **INSERT**, 있으면 **UPDATE**되어 행이 늘어나지 않습니다.
5. **다중 프로젝트**인 경우 하나라도 실패하면 전체가 실패(exit code 1)로 처리됩니다.

이렇게 하면:

- Supabase `BulChimBeon` 테이블에서 **언제 실행되었는지 이력**을 볼 수 있고,
- GitHub Actions에서 **각 실행의 성공/실패 로그**를 확인할 수 있습니다.

---

## 4. GitHub Actions 워크플로우 개요 (`.github/workflows/BulChimBeon.yml`)

워크플로우는 대략 다음과 같이 동작합니다.

- **트리거**
  - `schedule`: `0 0 * * 1,4` → 매주 월/목 00:00 UTC (KST 09:00)
  - `workflow_dispatch`: GitHub UI에서 수동으로 실행할 수 있는 트리거

- **작업 내용**
  1. 저장소 체크아웃 (`actions/checkout`)
  2. Python 3.x 설정 (`actions/setup-python`)
  3. `pip install -r requirements.txt`
  4. GitHub Secrets를 환경 변수로 전달한 뒤 `python BulChimBeon.py` 실행

---

## 5. 실행 이력 확인 방법

### 5-1. Supabase에서 확인

- Supabase 대시보드 → Table Editor → **각 프로젝트**에서 `BulChimBeon` 테이블을 열면
  - 테이블에는 **한 행만** 있으며, 그 행의 `last_ping`이 매 실행 시각으로 갱신됩니다.
- **다중 프로젝트**를 쓰는 경우, 모든 프로젝트의 테이블에서 `last_ping`이 갱신되는지 확인하면 됩니다.
- 월/목 9시(KST) 이후에 `last_ping`이 해당 시각 근처로 바뀌어 있으면 자동 깨우기가 잘 동작하는 것입니다.

### 5-2. GitHub Actions에서 확인

- GitHub 리포지토리 → `Actions` 탭으로 이동합니다.
- `BulChimBeon` 워크플로우를 선택하면:
  - 초록 ✔️ : 성공
  - 빨간 ❌ : 실패
- 각 실행(run)을 클릭하면 Python 스크립트 출력 로그와 HTTP 응답 내용 등을 확인할 수 있습니다.

---

## 6. 실패 시 알림

GitHub 계정의 **알림 설정**에 따라 실패 시 알림을 받을 수 있습니다.

- GitHub 계정 설정에서 **Actions 실패 알림**을 메일/웹/모바일 앱으로 켜 두면,
  - 워크플로우가 실패할 때마다 알림을 받을 수 있습니다.
- 더 강한 알림(예: Slack, Discord 등)을 원한다면,
  - 워크플로우에 `if: failure()` 조건을 가진 Webhook 전송 스텝을 추가하여 확장할 수 있습니다.

---

## 7. 확장 아이디어 (선택)

- 실행 주기를 늘리거나 줄이고 싶으면:
  - `BulChimBeon.yml`의 `cron` 값을 조정 (`0 0 * * *` → 매일 09:00 KST 등)
- 프로젝트를 더 추가하려면:
  - GitHub Secrets의 `SUPABASE_PROJECTS` JSON 배열에 항목을 추가하면 됩니다.

