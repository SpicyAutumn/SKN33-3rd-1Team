from __future__ import annotations

import unittest

from rag_indexing.pinecone_store import EMBEDDING_INPUT_VERSION, _flat_metadata, embedding_text
from rag_indexing.pipeline import build_chunks


PAYLOAD = {
    "eid": "E0002452",
    "status": "success",
    "url": "https://encykorea.aks.ac.kr/Article/E0002452",
    "headword": "경복궁 향원정",
    "field": "예술·체육/건축",
    "era": "조선/조선 후기",
    "primaryType": "유적/건물",
    "definition": "서울특별시 종로구 경복궁에 있는 조선후기 궁궐 건물.",
    "body": "향원정은 왕과 가족의 휴식처로 이용되었다.",
    "articleAliases": [{"word": "향원정"}],
}


class PineconeStoreTests(unittest.TestCase):
    def test_embedding_input_uses_selected_fields_and_records_version(self) -> None:
        chunk = build_chunks([PAYLOAD])[0]
        text = embedding_text(chunk)
        self.assertIn("제목: 경복궁 향원정", text)
        self.assertIn("구역: 정의", text)
        self.assertIn("시대: 조선/조선 후기", text)
        self.assertIn("유형: 유적/건물", text)
        self.assertIn("이칭: 향원정", text)
        self.assertIn("본문:", text)
        self.assertEqual(_flat_metadata(chunk)["embedding_input_version"], EMBEDDING_INPUT_VERSION)


if __name__ == "__main__":
    unittest.main()
