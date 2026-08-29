from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rag_indexing.pipeline import ChunkingConfig, build_chunks, load_aks_jsonl, normalize_text, write_chunks_jsonl


PAYLOAD = {
    "eid": "E0002452",
    "status": "success",
    "url": "https://encykorea.aks.ac.kr/Article/E0002452",
    "headword": "경복궁 향원정",
    "field": "예술·체육/건축",
    "era": "조선/조선 후기",
    "primaryType": "유적/건물",
    "definition": "서울특별시 종로구 경복궁에 있는 조선후기 궁궐 건물.",
    "body": "# 내용\n향원정은 왕과 가족의 휴식처로 이용되었다.\n\n[경복궁](E0000001)에 있다.",
    "articleAliases": [{"word": "향원정"}],
    "lastModifiedTime": "2023-02-07T08:15:00.847",
}


class RagIndexingTests(unittest.TestCase):
    def test_normalize_text_preserves_paragraphs_and_link_labels(self) -> None:
        self.assertEqual(normalize_text("# 제목\r\n첫 줄\r\n\r\n[둘째](E1)"), "제목 첫 줄\n\n둘째")

    def test_chunk_ids_are_reproducible_and_preserve_contract(self) -> None:
        config = ChunkingConfig(max_chars=120, overlap_chars=10)
        first = build_chunks([PAYLOAD], config)
        second = build_chunks([PAYLOAD], config)
        self.assertEqual([chunk.chunk_id for chunk in first], [chunk.chunk_id for chunk in second])
        self.assertEqual(first[0].document_id, "aks:E0002452")
        self.assertEqual(first[0].source_url, PAYLOAD["url"])
        self.assertTrue(all(chunk.section in {"definition", "body"} for chunk in first))
        self.assertIn("aliases", first[0].metadata)

    def test_load_and_write_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            source.write_text(
                json.dumps({"eid": "E0002452", "payload": PAYLOAD, "status": "success"}, ensure_ascii=False) + "\n"
                + json.dumps({"eid": "E0002453", "payload": {"status": "api_error"}}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            payloads = list(load_aks_jsonl(source, limit=10))
            output = root / "chunks.jsonl"
            count = write_chunks_jsonl(output, build_chunks(payloads))
            rows = output.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(payloads), 1)
        self.assertEqual(count, len(rows))
        self.assertGreater(count, 0)

    def test_load_aks_jsonl_supports_raw_api_payload_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "raw-api-payloads.jsonl"
            source.write_text(json.dumps(PAYLOAD, ensure_ascii=False) + "\n", encoding="utf-8")
            payloads = list(load_aks_jsonl(source))
        self.assertEqual([payload["eid"] for payload in payloads], ["E0002452"])

    def test_body_missing_payload_is_excluded_from_corpus(self) -> None:
        no_body = {**PAYLOAD, "body": "", "definition": "짧지 않은 정의입니다."}
        self.assertEqual(build_chunks([no_body]), [])

if __name__ == "__main__":
    unittest.main()
