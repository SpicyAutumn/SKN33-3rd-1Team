from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aks_data.workflows import validate_collection  # noqa: E402


def main() -> int:
    result = validate_collection(project_root=PROJECT_ROOT)
    print(
        "검증 완료: JSON {raw_json_count}건, 파싱 실패 {invalid_json_count}건, "
        "체크섬 불일치 {checksum_mismatch_count}건, manifest 오류 {manifest_api_error_count}건".format(**result)
    )
    return 0 if not any(
        result[key]
        for key in (
            "invalid_json_count",
            "response_eid_mismatch_count",
            "body_missing_count",
            "checksum_mismatch_count",
            "raw_without_manifest_count",
            "manifest_raw_missing_count",
        )
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
