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
from aks_data.workflows import run_audit  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AKS 일반 항목 CSV와 공식 OpenAPI 상세 응답을 층화 표본 감사합니다.")
    parser.add_argument("--csv", type=Path, help="일반 항목 CSV 경로(생략 시 data/raw에서 헤더로 자동 탐색)")
    parser.add_argument("--sample-size", type=int, default=25, help="표본 수(20~30, 기본 25)")
    parser.add_argument("--seed", type=int, default=20260828, help="표본 seed")
    parser.add_argument("--timeout", type=float, default=30.0, help="API 요청 제한시간(초)")
    parser.add_argument("--retries", type=int, default=2, help="일시 오류 재시도 횟수")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_project_env(PROJECT_ROOT / ".env")
    discovered_csv, media_paths = discover_csv_files(PROJECT_ROOT / "data" / "raw")
    csv_path = args.csv.resolve() if args.csv else discovered_csv
    api_key = os.getenv("AKS_API_KEY", "")
    api_base_url = os.getenv("AKS_API_BASE_URL", DEFAULT_API_BASE_URL)
    try:
        audit = run_audit(
            project_root=PROJECT_ROOT,
            csv_path=csv_path,
            media_paths=media_paths,
            api_key=api_key,
            api_base_url=api_base_url,
            sample_size=args.sample_size,
            seed=args.seed,
            timeout=args.timeout,
            retries=args.retries,
        )
    except (OSError, ValueError) as exc:
        print(f"감사 실패: {exc}", file=sys.stderr)
        return 1
    summary = audit["comparison_summary"]
    print(
        f"감사 완료: 표본 {summary['sample_count']}건, API 성공 {summary['api_success_count']}건, "
        "outputs/csv_api_audit_report.md 확인"
    )
    if not audit["audit_metadata"]["api_key_present"]:
        print("안내: AKS_API_KEY가 없어 CSV 감사와 표본 선정만 수행했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
