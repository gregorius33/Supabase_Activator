import json
import os
import sys
from datetime import datetime, timezone

import requests


def get_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or value.strip() == "":
        raise ValueError(f"환경 변수 {name} 가 설정되어 있지 않습니다.")
    return value


# BulChimBeon 테이블에서 항상 갱신할 단일 행의 고정 ID (첫 실행 시 INSERT, 이후 UPDATE)
HEARTBEAT_ROW_ID = "11111111-1111-1111-1111-111111111111"


def send_heartbeat(url: str, secret_key: str, table_name: str, index: int | None = None) -> bool:
    """한 프로젝트에 대해 UPSERT 요청을 보내고 성공 여부를 반환합니다."""
    endpoint = url.rstrip("/") + f"/rest/v1/{table_name}"
    now_utc = datetime.now(timezone.utc).isoformat()
    payload = {
        "id": HEARTBEAT_ROW_ID,
        "last_ping": now_utc,
        "note": "GitHub Actions BulChimBeon",
    }
    headers = {
        "apikey": secret_key,
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation,resolution=merge-duplicates",
    }
    label = f"프로젝트 {index}" if index is not None else "프로젝트"
    print(f"[BulChimBeon] {label} 엔드포인트: {endpoint}")
    print(f"[BulChimBeon] {label} 전송 시각(UTC): {now_utc} (UPSERT)")

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=10)
    except requests.RequestException as e:
        print(f"[BulChimBeon] {label} HTTP 요청 실패: {e}", file=sys.stderr)
        return False

    print(f"[BulChimBeon] {label} 응답 코드: {response.status_code}")
    if not response.ok:
        print(f"[BulChimBeon] {label} 응답 본문: {response.text}", file=sys.stderr)
        return False

    try:
        data = response.json()
        print(f"[BulChimBeon] {label} 응답 JSON: {data}")
    except ValueError:
        print(f"[BulChimBeon] {label} 응답 본문: {response.text}")
    print(f"[BulChimBeon] {label} 완료.")
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

    # 단일 프로젝트 (기존 방식)
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
    print(f"[BulChimBeon] 대상 프로젝트 수: {n}")

    failed = 0
    for i, proj in enumerate(projects, start=1):
        ok = send_heartbeat(
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
