import tempfile
import unittest
from pathlib import Path

from aks_data.core import CsvItem, extract_eid, load_article_csv, stratified_sample


class AksCoreTests(unittest.TestCase):
    def test_extract_eid_supports_csv_and_current_article_urls(self) -> None:
        self.assertEqual(extract_eid("http://encykorea.aks.ac.kr/Contents/Item/E0000002"), "E0000002")
        self.assertEqual(extract_eid("https://encykorea.aks.ac.kr/Article/E0000002"), "E0000002")
        self.assertIsNone(extract_eid("https://example.com/Article/E0000002"))
        self.assertIsNone(extract_eid("not-a-url"))

    def test_load_article_csv_marks_bad_urls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "articles.csv"
            path.write_text(
                "항목명,분야,웹사이트 주소\n"
                "정상,역사/조선시대사,http://encykorea.aks.ac.kr/Contents/Item/E0000002\n"
                "오류,생활/식생활,not-a-url\n",
                encoding="utf-8-sig",
            )
            rows = load_article_csv(path)
        self.assertEqual(rows[0].eid, "E0000002")
        self.assertIsNone(rows[1].eid)
        self.assertEqual(rows[1].url_error, "malformed_url")

    def test_stratified_sample_is_reproducible_and_covers_strata(self) -> None:
        items = []
        eid_number = 1
        for field in ("역사/조선", "생활/식생활", "예술·체육/공예"):
            for index in range(10):
                eid = f"E{eid_number:07d}"
                items.append(
                    CsvItem(
                        index + 2,
                        f"제목{eid}",
                        field,
                        f"https://encykorea.aks.ac.kr/Article/{eid}",
                        eid,
                    )
                )
                eid_number += 1
        first, allocation = stratified_sample(items, sample_size=20, seed=20260828)
        second, _ = stratified_sample(items, sample_size=20, seed=20260828)
        self.assertEqual([item.eid for item in first], [item.eid for item in second])
        self.assertEqual(set(item.stratum for item in first), {"역사", "생활", "예술·체육"})
        self.assertEqual(sum(allocation.values()), 20)


if __name__ == "__main__":
    unittest.main()
