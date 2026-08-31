import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "validate_aks_chunks.py"
SPEC = importlib.util.spec_from_file_location("validate_aks_chunks", SCRIPT_PATH)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def valid_chunk(*, chunk_id: str = "aks:E0000001:abc:def:0001", document_id: str = "aks:E0000001") -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "title": "검증 항목",
        "content": "검증용 본문입니다.",
        "source_url": "https://encykorea.aks.ac.kr/Article/E0000001",
        "section": "body",
        "metadata": {
            "aliases": [],
            "chunking_version": "v2",
            "chunking_fingerprint": "fingerprint",
            "document_fingerprint": "document",
            "chunking_max_chars": 1500,
            "chunking_overlap_chars": 200,
        },
    }


class ValidateAksChunksTests(unittest.TestCase):
    def write_jsonl(self, directory: Path, chunks: list[dict]) -> Path:
        path = directory / "chunks.jsonl"
        path.write_text("".join(json.dumps(chunk, ensure_ascii=False) + "\n" for chunk in chunks), encoding="utf-8")
        return path

    def expected_ids(self, directory: Path, rows: list[tuple[str, str, str]]) -> set[str]:
        manifest = directory / "manifest.csv"
        contents = "document_id,has_body,status\n" + "".join(
            f"{document_id},{has_body},{status}\n" for document_id, has_body, status in rows
        )
        manifest.write_text(contents, encoding="utf-8")
        return validator.load_expected_document_ids(manifest)

    def test_valid_chunks_pass_manifest_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            expected = self.expected_ids(directory, [("aks:E0000001", "true", "ok")])
            report = validator.validate_chunks(self.write_jsonl(directory, [valid_chunk()]), expected)

        self.assertEqual(report["unique_document_ids"], 1)
        self.assertEqual(report["documents_missing_from_chunks"], 0)
        self.assertEqual(report["documents_not_eligible_in_manifest"], 0)
        self.assertFalse(validator.has_failures(report, manifest_checked=True))

    def test_missing_manifest_document_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            expected = self.expected_ids(
                directory,
                [("aks:E0000001", "true", "ok"), ("aks:E0000002", "true", "ok")],
            )
            report = validator.validate_chunks(self.write_jsonl(directory, [valid_chunk()]), expected)

        self.assertEqual(report["documents_missing_from_chunks"], 1)
        self.assertTrue(validator.has_failures(report, manifest_checked=True))

    def test_ineligible_document_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            expected = self.expected_ids(directory, [("aks:E0000001", "true", "ok")])
            report = validator.validate_chunks(
                self.write_jsonl(directory, [valid_chunk(document_id="aks:E0000002")]), expected
            )

        self.assertEqual(report["documents_not_eligible_in_manifest"], 1)
        self.assertTrue(validator.has_failures(report, manifest_checked=True))

    def test_duplicate_chunk_id_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            expected = self.expected_ids(directory, [("aks:E0000001", "true", "ok")])
            first = valid_chunk()
            second = valid_chunk()
            report = validator.validate_chunks(self.write_jsonl(directory, [first, second]), expected)

        self.assertEqual(report["duplicate_chunk_id"], 1)
        self.assertTrue(validator.has_failures(report, manifest_checked=True))

    def test_invalid_field_values_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            expected = self.expected_ids(directory, [("aks:E0000001", "true", "ok")])
            chunk = valid_chunk()
            chunk["title"] = None
            chunk["source_url"] = 123
            chunk["section"] = "other"
            chunk["metadata"] = {"aliases": "not-a-list", "chunking_version": 2}
            report = validator.validate_chunks(self.write_jsonl(directory, [chunk]), expected)

        self.assertEqual(report["invalid_title"], 1)
        self.assertEqual(report["invalid_source_url"], 1)
        self.assertEqual(report["invalid_section"], 1)
        self.assertGreater(report["invalid_metadata_values"], 0)
        self.assertTrue(validator.has_failures(report, manifest_checked=True))


if __name__ == "__main__":
    unittest.main()
