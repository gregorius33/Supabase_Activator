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


def main() -> None:
    try:
        supabase_url = get_env("SUPABASE_URL")
        # 새 API 키(Secret) 또는 레거시 service_role 키 지원
        service_role_key = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not service_role_key or not service_role_key.strip():
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY 또는 SUPABASE_SECRET_KEY 중 하나를 설정해 주세요.")
        table_name = (os.getenv("SUPABASE_TABLE") or "").strip() or "BulChimBeon"
    except ValueError as e:
        print(f"[BulChimBeon] 환경 변수 오류: {e}", file=sys.stderr)
        sys.exit(1)

    endpoint = supabase_url.rstrip("/") + f"/rest/v1/{table_name}"

    now_utc = datetime.now(timezone.utc).isoformat()
    payload = {
        "id": HEARTBEAT_ROW_ID,
        "last_ping": now_utc,
        "note": "GitHub Actions BulChimBeon",
    }

    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation,resolution=merge-duplicates",
    }

    print(f"[BulChimBeon] Supabase 엔드포인트: {endpoint}")
    print(f"[BulChimBeon] 전송 시각(UTC): {now_utc} (UPSERT: 기존 행 있으면 UPDATE, 없으면 INSERT)")

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=10)
    except requests.RequestException as e:
        print(f"[BulChimBeon] HTTP 요청 실패: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[BulChimBeon] 응답 코드: {response.status_code}")
    if not response.ok:
        print(f"[BulChimBeon] 응답 본문: {response.text}", file=sys.stderr)
        sys.exit(1)

    try:
        data = response.json()
        print(f"[BulChimBeon] 응답 JSON: {data}")
    except ValueError:
        print("[BulChimBeon] 응답 JSON 파싱 실패 (본문을 그대로 출력합니다.)")
        print(response.text)

    print("[BulChimBeon] 요청이 성공적으로 완료되었습니다.")


if __name__ == "__main__":
    main()

