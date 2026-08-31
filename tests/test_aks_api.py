import json
import tempfile
import unittest
from pathlib import Path

from aks_data.api import AksApiClient, parse_article
from aks_data.workflows import collect_all, collect_selected, validate_collection


FIXTURE = Path(__file__).parent / "fixtures" / "aks_article_E0000002.json"


class AksApiTests(unittest.TestCase):
    def test_client_uses_header_and_parses_mock_response(self) -> None:
        raw = FIXTURE.read_bytes()
        observed = {}

        def transport(url: str, headers: dict[str, str], timeout: float) -> bytes:
            observed.update(url=url, headers=headers, timeout=timeout)
            return raw

        client = AksApiClient("test-key", transport=transport, retries=0)
        response = client.fetch_article("E0000002")
        parsed = parse_article(response.payload)

        self.assertEqual(observed["headers"]["X-API-Key"], "test-key")
        self.assertTrue(observed["url"].endswith("/articles/E0000002"))
        self.assertEqual(parsed["eid"], "E0000002")
        self.assertEqual(parsed["title"], "ㄱ")
        self.assertEqual(parsed["field"], "언어/언어·문자")
        self.assertTrue(parsed["has_body"])
        self.assertGreater(parsed["content_length"], 0)
        self.assertEqual(parsed["api_only_fields"], ["lastModifiedTime", "writerInfo"])

    def test_fixture_is_valid_json(self) -> None:
        self.assertEqual(json.loads(FIXTURE.read_text(encoding="utf-8"))["eid"], "E0000002")

    def test_selected_collection_saves_exact_raw_and_manifest(self) -> None:
        raw = FIXTURE.read_bytes()

        def transport(_url: str, _headers: dict[str, str], _timeout: float) -> bytes:
            return raw

        client = AksApiClient("test-key", transport=transport, retries=0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "articles.csv"
            csv_path.write_text(
                "항목명,분야,웹사이트 주소\n"
                "ㄱ,언어/언어·문자,http://encykorea.aks.ac.kr/Contents/Item/E0000002\n",
                encoding="utf-8-sig",
            )
            selected_path = root / "selected.csv"
            selected_path.write_text("eid\nE0000002\n", encoding="utf-8-sig")
            result = collect_selected(
                project_root=root,
                csv_path=csv_path,
                selected_path=selected_path,
                api_key="test-key",
                client=client,
            )
            saved = root / "data" / "raw" / "api" / "E0000002.json"
            manifest = root / "data" / "manifest.csv"
            self.assertEqual(saved.read_bytes(), raw)
            self.assertTrue(manifest.exists())
        self.assertEqual(result["selected_count"], 1)
        self.assertEqual(result["success_count"], 1)

    def test_full_collection_is_restart_safe_for_existing_raw(self) -> None:
        raw = FIXTURE.read_bytes()
        calls = []

        def transport(url: str, _headers: dict[str, str], _timeout: float) -> bytes:
            calls.append(url)
            return raw

        client = AksApiClient("test-key", transport=transport, retries=0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "articles.csv"
            csv_path.write_text(
                "항목명,분야,웹사이트 주소\n"
                "ㄱ,언어/언어·문자,http://encykorea.aks.ac.kr/Contents/Item/E0000002\n",
                encoding="utf-8-sig",
            )
            first = collect_all(
                project_root=root,
                csv_path=csv_path,
                api_key="test-key",
                client=client,
                delay_seconds=0,
                batch_size=1,
            )
            second = collect_all(
                project_root=root,
                csv_path=csv_path,
                api_key="test-key",
                client=client,
                delay_seconds=0,
                batch_size=1,
            )
        self.assertEqual(first["fetched"], 1)
        self.assertEqual(second["skipped_existing"], 1)
        self.assertEqual(len(calls), 1)

    def test_collection_validation_checks_raw_manifest_link(self) -> None:
        raw = FIXTURE.read_bytes()

        def transport(_url: str, _headers: dict[str, str], _timeout: float) -> bytes:
            return raw

        client = AksApiClient("test-key", transport=transport, retries=0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "articles.csv"
            csv_path.write_text(
                "항목명,분야,웹사이트 주소\n"
                "ㄱ,언어/언어·문자,http://encykorea.aks.ac.kr/Contents/Item/E0000002\n",
                encoding="utf-8-sig",
            )
            collect_all(
                project_root=root,
                csv_path=csv_path,
                api_key="test-key",
                client=client,
                delay_seconds=0,
                batch_size=1,
            )
            result = validate_collection(project_root=root)
        self.assertEqual(result["valid_json_count"], 1)
        self.assertEqual(result["checksum_mismatch_count"], 0)
        self.assertEqual(result["response_eid_mismatch_count"], 0)


if __name__ == "__main__":
    unittest.main()
