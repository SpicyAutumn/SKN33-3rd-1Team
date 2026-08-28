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
from aks_data.workflows import collect_selected  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="명시적으로 선택한 AKS EID의 상세 JSON 원본만 수집합니다.")
    parser.add_argument("--csv", type=Path, help="일반 항목 CSV 경로")
    parser.add_argument(
        "--selected",
        type=Path,
        default=PROJECT_ROOT / "data" / "selection" / "selected_eids.csv",
        help="eid 열을 가진 선택 CSV",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="API 요청 제한시간(초)")
    parser.add_argument("--retries", type=int, default=2, help="일시 오류 재시도 횟수")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_project_env(PROJECT_ROOT / ".env")
    discovered_csv, _media_paths = discover_csv_files(PROJECT_ROOT / "data" / "raw")
    csv_path = args.csv.resolve() if args.csv else discovered_csv
    try:
        result = collect_selected(
            project_root=PROJECT_ROOT,
            csv_path=csv_path,
            selected_path=args.selected.resolve(),
            api_key=os.getenv("AKS_API_KEY", ""),
            api_base_url=os.getenv("AKS_API_BASE_URL", DEFAULT_API_BASE_URL),
            timeout=args.timeout,
            retries=args.retries,
        )
    except (OSError, ValueError) as exc:
        print(f"선택 수집 실패: {exc}", file=sys.stderr)
        return 1
    print(
        f"선택 수집 완료: 선택 {result['selected_count']}건, 성공 {result['success_count']}건, "
        f"실패 {result['error_count']}건"
    )
    return 0 if result["error_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
