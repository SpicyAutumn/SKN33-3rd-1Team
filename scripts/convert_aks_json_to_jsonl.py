"""data/raw/api의 EID별 상세 JSON을 JSONL 한 파일로 변환한다."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = PROJECT_ROOT / "data" / "raw" / "api"
OUTPUT_FILE = PROJECT_ROOT / "data" / "raw" / "aks_full_content.jsonl"


def main() -> int:
    json_files = sorted(INPUT_DIR.glob("E*.json"))
    if not json_files:
        raise SystemExit(f"상세 JSON 파일이 없습니다: {INPUT_DIR}")

    temporary_file = OUTPUT_FILE.with_suffix(".jsonl.tmp")
    written = 0
    skipped: list[tuple[str, str]] = []

    with temporary_file.open("w", encoding="utf-8", newline="\n") as output:
        for index, json_file in enumerate(json_files, start=1):
            try:
                payload = json.loads(json_file.read_text(encoding="utf-8"))
                if payload.get("eid") != json_file.stem:
                    raise ValueError("파일명 EID와 JSON 내부 eid가 다릅니다.")
                output.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
                output.write("\n")
                written += 1
            except (OSError, ValueError, json.JSONDecodeError) as error:
                skipped.append((json_file.name, str(error)))

            if index % 1000 == 0 or index == len(json_files):
                print(f"변환: {index}/{len(json_files)}, 저장 {written}, 제외 {len(skipped)}", flush=True)

    temporary_file.replace(OUTPUT_FILE)
    if skipped:
        errors_path = PROJECT_ROOT / "data" / "raw" / "aks_full_content_conversion_errors.json"
        errors_path.write_text(
            json.dumps({"skipped": [{"file": name, "error": error} for name, error in skipped]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(f"완료: {OUTPUT_FILE} ({written}건)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
