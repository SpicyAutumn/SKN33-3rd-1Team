"""한국민족문화대백과사전 OpenAPI의 '전체 항목 리스트'에 해당하는 JSON을 data/raw/api_list_metadata에 저장한다.
 > GET https://devin.aks.ac.kr:8080/api/articles?p={pageNo}&ps={pageSize}

body·reference·연관 항목은 비어 있으므로 이 결과는 최종 corpus가 아니다.
상세 API JSON과 구분하기 위해 data/raw/api_list_metadata에 저장한다.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API_BASE_URL = "https://devin.aks.ac.kr:8080/api"


def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_json(url: str, api_key: str, timeout: float, retries: int) -> dict:
    request = Request(
        url,
        headers={"X-API-Key": api_key, "Accept": "application/json"},
        method="GET",
    )
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read()
            if not body:
                raise ValueError("API가 빈 응답을 반환했습니다.")
            return json.loads(body.decode("utf-8"))
        except (HTTPError, URLError, ValueError, json.JSONDecodeError) as error:
            last_error = error
            if attempt < retries:
                time.sleep(2**attempt)
    raise RuntimeError(str(last_error))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def clear_existing_json(output_dir: Path) -> int:
    if not output_dir.exists():
        return 0
    paths = list(output_dir.glob("*.json"))
    for path in paths:
        path.unlink()
    return len(paths)


def main() -> int:
    parser = argparse.ArgumentParser(description="AKS OpenAPI 목록 API 기반 전체 JSON 수집")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="기존 data/raw/api_list_metadata/*.json을 지우고 처음부터 저장",
    )
    parser.add_argument("--page-size", type=int, default=100, help="목록 API 페이지 크기(기본 100)")
    parser.add_argument("--delay", type=float, default=0.1, help="페이지 요청 사이 대기 시간(초)")
    parser.add_argument("--timeout", type=float, default=30.0, help="요청 제한시간(초)")
    parser.add_argument("--retries", type=int, default=2, help="일시 오류 재시도 횟수")
    parser.add_argument("--max-pages", type=int, help="점검용 최대 페이지 수")
    args = parser.parse_args()

    if args.page_size < 1:
        raise SystemExit("--page-size는 1 이상이어야 합니다.")

    load_env(PROJECT_ROOT / ".env")
    api_key = os.getenv("AKS_API_KEY")
    if not api_key:
        raise SystemExit("AKS_API_KEY가 프로젝트 최상위 .env에 없습니다.")

    base_url = os.getenv("AKS_API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")
    output_dir = PROJECT_ROOT / "data" / "raw" / "api_list_metadata"
    if args.fresh:
        print(f"기존 JSON 삭제: {clear_existing_json(output_dir)}건")

    page = 1
    total_pages: int | None = None
    saved = 0
    failed_pages: list[int] = []

    while total_pages is None or page <= total_pages:
        if args.max_pages and page > args.max_pages:
            break

        query = urlencode({"p": page, "ps": args.page_size})
        try:
            payload = get_json(f"{base_url}/articles?{query}", api_key, args.timeout, args.retries)
            items = payload.get("items")
            if not isinstance(items, list):
                raise ValueError("목록 API 응답에 items 배열이 없습니다.")

            total_pages = int(payload["totalPage"])
            for item in items:
                eid = str(item.get("eid", "")).strip()
                if not eid:
                    continue
                write_json(output_dir / f"{eid}.json", item)
                saved += 1

            print(f"[OK] 페이지 {page}/{total_pages}: {len(items)}건, 누적 저장 {saved}건", flush=True)
        except (RuntimeError, ValueError, KeyError) as error:
            failed_pages.append(page)
            print(f"[FAIL] 페이지 {page}: {error}", flush=True)
        page += 1
        if total_pages is not None and page <= total_pages:
            time.sleep(args.delay)

    summary = {
        "source": "AKS OpenAPI GET /articles",
        "saved_items": saved,
        "failed_pages": failed_pages,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    write_json(PROJECT_ROOT / "outputs" / "api_only_collection_summary.json", summary)
    print(f"완료: 저장 {saved}건, 실패 페이지 {len(failed_pages)}건")
    return 0 if not failed_pages else 2


if __name__ == "__main__":
    raise SystemExit(main())
