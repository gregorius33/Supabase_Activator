## BulChimBeon (Supabase 자동 깨우기)

이 저장소는 **Supabase 프로젝트가 1주일 이상 비활성화되어 일시 중지되는 것**을 막기 위해,
GitHub Actions와 Python 스크립트로 **주기적으로 Supabase에 간단한 DB 기록을 남기는** 용도의 프로젝트입니다.

- 사용하는 테이블 이름: **`BulChimBeon`**
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
- 각 실행 시마다 `last_ping`에 현재 시간(UTC 기준), `note`에 간단한 메모 문자열이 들어갑니다.
- 매 실행마다 **새로운 행을 INSERT**하는 방식이라, Table Editor에서 실행 이력을 쉽게 확인할 수 있습니다.

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
3. 아래 이름으로 **Repository secret** 추가

- `SUPABASE_URL` : Supabase 프로젝트 URL
- `SUPABASE_SERVICE_ROLE_KEY` : 서비스 롤 키
- (선택) `SUPABASE_TABLE` : 기본값 `BulChimBeon`을 그대로 쓸 경우 생략 가능

Python 스크립트 `BulChimBeon.py`는 위 값들을 **환경 변수**로부터 읽어와 Supabase REST API를 호출합니다.

---

## 3. Python 스크립트 개요 (`BulChimBeon.py`)

이 스크립트는 다음과 같이 동작합니다.

1. 환경 변수에서 Supabase URL, Service Role Key, 테이블 이름을 읽습니다.
2. `SUPABASE_URL/rest/v1/BulChimBeon` 엔드포인트로 `POST` 요청을 보냅니다.
3. 요청 바디에는:
   - `last_ping`: 현재 UTC 시각 (ISO 8601 문자열)
   - `note`: `"GitHub Actions BulChimBeon"` 같은 간단한 문자열
4. HTTP 요청이 실패하면 **비정상 종료(exit code != 0)** 하여
   - GitHub Actions에서 해당 실행을 **실패(빨간불)** 로 표시하게 합니다.

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

- Supabase 대시보드 → Table Editor → `BulChimBeon` 테이블을 열면
  - 각 실행 시점마다 추가된 행과 `last_ping` 값을 볼 수 있습니다.
- 실행 주기(월/목 9시 KST)에 맞게 행이 늘어나고 있으면, 자동 깨우기가 잘 동작하는 것입니다.

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
- 여러 Supabase 프로젝트를 동시에 살려두고 싶으면:
  - `BulChimBeon.py`에서 URL/KEY 목록을 돌며 여러 프로젝트에 대해 순차적으로 요청 보내도록 확장

