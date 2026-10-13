from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from judge.submission_checker import InvalidOutput, load_query_ids, validate_submission


class CheckerTests(unittest.TestCase):
    def test_accepts_bom_and_quoted_answers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "queries.json").write_text('[{"id": 1}, {"id": "x"}]', encoding="utf-8")
            (root / "submission.csv").write_text(
                '\ufeffid,answer\n1,"a,b"\nx,"N\u00f3i ""\u0111\u00fang"""\n', encoding="utf-8"
            )
            ids = load_query_ids(root / "queries.json")
            self.assertEqual(
                validate_submission(root / "submission.csv", ids, 1000),
                {"1": "a,b", "x": 'N\u00f3i "\u0111\u00fang"'},
            )

    def test_rejects_missing_duplicate_unknown_and_wrong_header(self) -> None:
        cases = [
            ("id,answer\n1,a\n", "missing IDs"),
            ("id,answer\n1,a\n1,b\n2,c\n", "duplicate ID"),
            ("id,answer\n1,a\n2,b\n3,c\n", "unknown IDs"),
            ("answer,id\na,1\nb,2\n", "header"),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "submission.csv"
            for content, message in cases:
                with self.subTest(message=message):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaisesRegex(InvalidOutput, message):
                        validate_submission(path, ["1", "2"], 1000)
