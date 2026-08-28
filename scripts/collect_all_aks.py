from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aks_data.api import DEFAULT_API_BASE_URL  # noqa: E402
from aks_data.config import load_project_env  # noqa: E402
from aks_data.core import discover_csv_files  # noqa: E402
from aks_data.workflows import collect_all  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="일반 항목 CSV의 유효 고유 EID 전체를 AKS OpenAPI로 수집합니다.")
    parser.add_argument("--all", action="store_true", help="전체 수집을 명시적으로 승인합니다(필수).")
    parser.add_argument("--csv", type=Path, help="일반 항목 CSV 경로")
    parser.add_argument("--delay", type=float, default=0.1, help="API 요청 사이 대기 시간(초, 기본 0.1)")
    parser.add_argument("--batch-size", type=int, default=500, help="manifest/진행 상태 저장 단위(기본 500)")
    parser.add_argument("--max-items", type=int, help="점검용 수집 상한; 생략하면 전체")
    parser.add_argument("--timeout", type=float, default=30.0, help="API 요청 제한시간(초)")
    parser.add_argument("--retries", type=int, default=2, help="일시 오류 재시도 횟수")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.all:
        print("전체 수집은 대량 API 요청입니다. 실행하려면 --all을 명시하세요.", file=sys.stderr)
        return 2
    load_project_env(PROJECT_ROOT / ".env")
    discovered_csv, _media_paths = discover_csv_files(PROJECT_ROOT / "data" / "raw")
    csv_path = args.csv.resolve() if args.csv else discovered_csv

    def report(progress: dict[str, object]) -> None:
        print(
            "진행: {processed}/{total}, 새 수집 {fetched}, 기존 건너뜀 {skipped_existing}, 오류 {api_error}, "
            "마지막 {last_eid}".format(**progress),
            flush=True,
        )

    try:
        result = collect_all(
            project_root=PROJECT_ROOT,
            csv_path=csv_path,
            api_key=os.getenv("AKS_API_KEY", ""),
            api_base_url=os.getenv("AKS_API_BASE_URL", DEFAULT_API_BASE_URL),
            delay_seconds=args.delay,
            batch_size=args.batch_size,
            max_items=args.max_items,
            timeout=args.timeout,
            retries=args.retries,
            progress_callback=report,
        )
    except (OSError, ValueError) as exc:
        print(f"전체 수집 실패: {exc}", file=sys.stderr)
        return 1
    print(
        "전체 수집 종료: 처리 {processed}/{total}, 새 수집 {fetched}, 기존 건너뜀 {skipped_existing}, 오류 {api_error}".format(
            **result
        )
    )
    return 130 if result["interrupted"] else (0 if result["api_error"] == 0 else 2)


if __name__ == "__main__":
    raise SystemExit(main())
