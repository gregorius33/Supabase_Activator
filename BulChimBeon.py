import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

# 1단계: 최근 10일 평균을 note에 넣어 UPSERT하는 행의 고정 id (2단계 20건과 id 체계 분리)
HEARTBEAT_SUMMARY_ROW_ID = "22222222-2222-2222-2222-222222222222"

# 2단계: 매 실행마다 새 uuid로 INSERT (고정 id 없음)
_batch_raw = (os.getenv("BULCHIMBEON_BATCH_INSERT_COUNT") or "20").strip()
BATCH_INSERT_COUNT = max(1, int(_batch_raw))


def get_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or value.strip() == "":
        raise ValueError(f"환경 변수 {name} 가 설정되어 있지 않습니다.")
    return value


def auth_headers(secret_key: str) -> dict[str, str]:
    return {
        "apikey": secret_key,
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def iso_utc_z(dt: datetime) -> str:
    """PostgREST 필터용 UTC (Z 접미사)."""
    s = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    return s


def previous_month_range_utc(now: datetime | None = None) -> tuple[str, str]:
    """전월 [시작, 다음달 시작) 구간을 UTC ISO 문자열로 반환 (DELETE 필터용)."""
    now = now or datetime.now(timezone.utc)
    first_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_prev_end = first_this - timedelta(microseconds=1)
    y, m = last_prev_end.year, last_prev_end.month
    first_prev = datetime(y, m, 1, tzinfo=timezone.utc)
    first_next = first_this
    return iso_utc_z(first_prev), iso_utc_z(first_next)


def fetch_created_at_last_10_days(
    base_endpoint: str, secret_key: str, summary_row_id: str
) -> list[datetime]:
    """최근 10일간 insert된 행의 created_at 목록 (요약 행 id 제외)."""
    since = datetime.now(timezone.utc) - timedelta(days=10)
    since_s = iso_utc_z(since)
    url = f"{base_endpoint}"
    params = {
        "select": "created_at",
        "created_at": f"gte.{since_s}",
        "id": f"neq.{summary_row_id}",
    }
    headers = auth_headers(secret_key)
    headers["Accept"] = "application/json"
    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
    except requests.RequestException as e:
        raise RuntimeError(f"10일 구간 조회 GET 실패: {e}") from e
    if not r.ok:
        raise RuntimeError(f"10일 구간 조회 실패 HTTP {r.status_code}: {r.text}")
    rows = r.json()
    out: list[datetime] = []
    for row in rows:
        raw = row.get("created_at")
        if not raw:
            continue
        if isinstance(raw, str):
            raw = raw.replace("Z", "+00:00")
            out.append(datetime.fromisoformat(raw))
        else:
            continue
    return out


def average_created_at_iso(rows: list[datetime]) -> str | None:
    """created_at 시각들의 epoch 평균을 ISO 문자열로 (없으면 None)."""
    if not rows:
        return None
    epochs = [r.timestamp() for r in rows]
    avg_e = sum(epochs) / len(epochs)
    return datetime.fromtimestamp(avg_e, tz=timezone.utc).isoformat()


def run_project_sequence(
    url: str, secret_key: str, table_name: str, index: int | None = None
) -> bool:
    base = url.rstrip("/") + f"/rest/v1/{table_name}"
    label = f"프로젝트 {index}" if index is not None else "프로젝트"
    now_utc = datetime.now(timezone.utc)
    now_s = iso_utc(now_utc)
    h_upsert = {
        **auth_headers(secret_key),
        "Prefer": "return=representation,resolution=merge-duplicates",
    }
    h_json = auth_headers(secret_key)

    print(f"[BulChimBeon] {label} 엔드포인트: {base}")

    # --- 1) 최근 10일 created_at 평균 → 요약 행 UPSERT (고정 id) ---
    try:
        created_list = fetch_created_at_last_10_days(base, secret_key, HEARTBEAT_SUMMARY_ROW_ID)
    except RuntimeError as e:
        print(f"[BulChimBeon] {label} 1단계 조회 오류: {e}", file=sys.stderr)
        return False

    avg_s = average_created_at_iso(created_list)
    if avg_s is None:
        note_summary = "avg_last_10d: (no rows, excluding summary row)"
    else:
        note_summary = f"avg_last_10d_insert_time_utc: {avg_s}"

    payload_summary = {
        "id": HEARTBEAT_SUMMARY_ROW_ID,
        "last_ping": now_s,
        "note": note_summary,
    }
    print(f"[BulChimBeon] {label} 1단계 UPSERT 요약행 note={note_summary[:120]}")

    try:
        r1 = requests.post(base, json=payload_summary, headers=h_upsert, timeout=30)
    except requests.RequestException as e:
        print(f"[BulChimBeon] {label} 1단계 POST 실패: {e}", file=sys.stderr)
        return False
    if not r1.ok:
        print(f"[BulChimBeon] {label} 1단계 실패 {r1.status_code}: {r1.text}", file=sys.stderr)
        return False

    # --- 2) 새 행 BATCH_INSERT_COUNT건 INSERT (id 생략 → DB 기본값) ---
    batch = [
        {
            "last_ping": now_s,
            "note": f"GitHub Actions BulChimBeon batch {i + 1}/{BATCH_INSERT_COUNT}",
            "created_at": now_s,
        }
        for i in range(BATCH_INSERT_COUNT)
    ]
    h_batch = {**h_json, "Prefer": "return=minimal"}
    print(f"[BulChimBeon] {label} 2단계 INSERT {BATCH_INSERT_COUNT}건")
    try:
        r2 = requests.post(base, json=batch, headers=h_batch, timeout=60)
    except requests.RequestException as e:
        print(f"[BulChimBeon] {label} 2단계 POST 실패: {e}", file=sys.stderr)
        return False
    if not r2.ok:
        print(f"[BulChimBeon] {label} 2단계 실패 {r2.status_code}: {r2.text}", file=sys.stderr)
        return False

    # --- 3) 전월 insert 분 DELETE ---
    start_prev, end_prev_exclusive = previous_month_range_utc(now_utc)
    # PostgREST: and=(created_at.gte.X,created_at.lt.Y)
    and_filter = f"(created_at.gte.{start_prev},created_at.lt.{end_prev_exclusive})"
    del_params = {"and": and_filter}
    h_del = {**h_json, "Prefer": "return=representation"}
    print(f"[BulChimBeon] {label} 3단계 DELETE 전월 [{start_prev} ~ {end_prev_exclusive})")
    try:
        r3 = requests.delete(base, headers=h_del, params=del_params, timeout=60)
    except requests.RequestException as e:
        print(f"[BulChimBeon] {label} 3단계 DELETE 실패: {e}", file=sys.stderr)
        return False
    if not r3.ok:
        print(f"[BulChimBeon] {label} 3단계 실패 {r3.status_code}: {r3.text}", file=sys.stderr)
        return False

    print(f"[BulChimBeon] {label} 완료 (1 UPSERT + {BATCH_INSERT_COUNT} INSERT + DELETE 전월).")
    return True


def load_projects_from_env() -> list[dict]:
    """SUPABASE_PROJECTS(JSON) 또는 단일 프로젝트(SUPABASE_URL 등)에서 설정 목록을 만듭니다."""
    raw = (os.getenv("SUPABASE_PROJECTS") or "").strip()
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"SUPABASE_PROJECTS JSON 파싱 실패: {e}") from e
        if not isinstance(data, list) or len(data) == 0:
            raise ValueError("SUPABASE_PROJECTS 는 비어 있지 않은 배열이어야 합니다.")
        projects = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                raise ValueError(f"SUPABASE_PROJECTS[{i}] 항목은 객체여야 합니다.")
            url = (item.get("url") or "").strip()
            secret_key = (item.get("secret_key") or "").strip()
            if not url or not secret_key:
                raise ValueError(
                    f"SUPABASE_PROJECTS[{i}] 에 'url' 과 'secret_key' 가 필요합니다."
                )
            table = (item.get("table") or "").strip() or "BulChimBeon"
            projects.append({"url": url, "secret_key": secret_key, "table": table})
        return projects

    url = (os.getenv("SUPABASE_URL") or "").strip()
    secret_key = (
        (os.getenv("SUPABASE_SECRET_KEY") or "").strip()
        or (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    )
    if not url or not secret_key:
        raise ValueError(
            "다중 프로젝트: SUPABASE_PROJECTS(JSON) 를 설정하거나, "
            "단일 프로젝트: SUPABASE_URL 과 SUPABASE_SERVICE_ROLE_KEY(또는 SUPABASE_SECRET_KEY) 를 설정하세요."
        )
    table = (os.getenv("SUPABASE_TABLE") or "").strip() or "BulChimBeon"
    return [{"url": url, "secret_key": secret_key, "table": table}]


def main() -> None:
    try:
        projects = load_projects_from_env()
    except ValueError as e:
        print(f"[BulChimBeon] 설정 오류: {e}", file=sys.stderr)
        sys.exit(1)

    n = len(projects)
    print(f"[BulChimBeon] 대상 프로젝트 수: {n}, 배치 INSERT 건수: {BATCH_INSERT_COUNT}")

    failed = 0
    for i, proj in enumerate(projects, start=1):
        ok = run_project_sequence(
            proj["url"],
            proj["secret_key"],
            proj["table"],
            index=i if n > 1 else None,
        )
        if not ok:
            failed += 1

    if failed > 0:
        print(f"[BulChimBeon] 실패: {failed}/{n} 프로젝트", file=sys.stderr)
        sys.exit(1)
    print("[BulChimBeon] 모든 프로젝트 요청이 성공적으로 완료되었습니다.")


if __name__ == "__main__":
    main()
