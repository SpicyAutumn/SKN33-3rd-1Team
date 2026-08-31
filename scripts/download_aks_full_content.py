"""한국민족문화대백과사전 OpenAPI의 '항목 내용'에 해당하는 JSON을 data/raw/api에 저장한다.
 > GET https://devin.aks.ac.kr:8080/api/articles/{eid}

이는 EID에 대해 상세 API(/articles/{eid})를 호출하며 body, reference, relatedArticles 등의 상세 내용이 포함된 것으로,
EID 목록은 기존 data/raw/api_list_metadata의 파일명에서 읽는다.

"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
                raw = response.read()
            if not raw:
                raise ValueError("API가 빈 응답을 반환했습니다.")
            return json.loads(raw.decode("utf-8"))
        except (HTTPError, URLError, ValueError, json.JSONDecodeError) as error:
            last_error = error
            if attempt < retries:
                time.sleep(2**attempt)
    raise RuntimeError(str(last_error))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def metadata_eids(metadata_dir: Path) -> list[str]:
    return sorted({path.stem for path in metadata_dir.glob("E*.json") if path.stem})


def list_api_eids(base_url: str, api_key: str, page_size: int, timeout: float, retries: int) -> list[str]:
    page = 1
    total_pages: int | None = None
    eids: set[str] = set()
    while total_pages is None or page <= total_pages:
        query = urlencode({"p": page, "ps": page_size})
        payload = get_json(f"{base_url}/articles?{query}", api_key, timeout, retries)
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValueError("목록 API 응답에 items 배열이 없습니다.")
        total_pages = int(payload["totalPage"])
        eids.update(str(item.get("eid", "")).strip() for item in items if item.get("eid"))
        print(f"[목록] 페이지 {page}/{total_pages}: EID {len(eids)}건", flush=True)
        page += 1
    return sorted(eids)


def remove_existing_json(output_dir: Path) -> int:
    if not output_dir.exists():
        return 0
    paths = list(output_dir.glob("E*.json"))
    for path in paths:
        path.unlink()
    return len(paths)


def fetch_one(eid: str, base_url: str, api_key: str, output_dir: Path, timeout: float, retries: int) -> tuple[str, str]:
    try:
        payload = get_json(f"{base_url}/articles/{eid}", api_key, timeout, retries)
        response_eid = str(payload.get("eid", "")).strip()
        if response_eid != eid:
            raise ValueError(f"응답 EID 불일치: 요청={eid}, 응답={response_eid or '없음'}")
        write_json(output_dir / f"{eid}.json", payload)
        return eid, "ok"
    except (RuntimeError, ValueError) as error:
        return eid, str(error)


def main() -> int:
    parser = argparse.ArgumentParser(description="AKS OpenAPI 상세 JSON 전체 수집")
    parser.add_argument("--fresh", action="store_true", help="기존 data/raw/api/E*.json을 지우고 처음부터 수집")
    parser.add_argument("--workers", type=int, default=3, help="동시 상세 요청 수(기본 3, 과도하게 높이지 말 것)")
    parser.add_argument("--timeout", type=float, default=30.0, help="요청 제한시간(초)")
    parser.add_argument("--retries", type=int, default=2, help="일시 오류 재시도 횟수")
    parser.add_argument("--page-size", type=int, default=100, help="목록 API 페이지 크기(기본 100)")
    parser.add_argument("--max-items", type=int, help="점검용 상세 수집 상한")
    args = parser.parse_args()

    if args.workers < 1:
        raise SystemExit("--workers는 1 이상이어야 합니다.")

    load_env(PROJECT_ROOT / ".env")
    api_key = os.getenv("AKS_API_KEY")
    if not api_key:
        raise SystemExit("AKS_API_KEY가 프로젝트 최상위 .env에 없습니다.")

    base_url = os.getenv("AKS_API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")
    output_dir = PROJECT_ROOT / "data" / "raw" / "api"
    metadata_dir = PROJECT_ROOT / "data" / "raw" / "api_list_metadata"

    if args.fresh:
        print(f"기존 상세 JSON 삭제: {remove_existing_json(output_dir)}건")

    eids = metadata_eids(metadata_dir)
    if eids:
        print(f"EID 출처: {metadata_dir} ({len(eids)}건)")
    else:
        print("EID 출처: OpenAPI 전체 목록")
        eids = list_api_eids(base_url, api_key, args.page_size, args.timeout, args.retries)

    if args.max_items:
        eids = eids[: args.max_items]
    pending = [eid for eid in eids if args.fresh or not (output_dir / f"{eid}.json").exists()]
    print(f"상세 요청 대상: {len(pending)}건 / 전체 EID: {len(eids)}건", flush=True)

    success = 0
    failures: list[tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(fetch_one, eid, base_url, api_key, output_dir, args.timeout, args.retries): eid
            for eid in pending
        }
        for index, future in enumerate(as_completed(futures), start=1):
            eid, result = future.result()
            if result == "ok":
                success += 1
            else:
                failures.append((eid, result))
            if index % 100 == 0 or index == len(pending):
                print(f"[상세] {index}/{len(pending)} 완료, 성공 {success}, 실패 {len(failures)}", flush=True)

    if failures:
        error_path = PROJECT_ROOT / "data" / "raw" / "api_detail_failures.json"
        write_json(error_path, {"failed": [{"eid": eid, "error": error} for eid, error in failures]})
        print(f"실패 목록 저장: {error_path}")

    print(f"종료: 성공 {success}, 실패 {len(failures)}, 기존 파일 건너뜀 {len(eids) - len(pending)}")
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
