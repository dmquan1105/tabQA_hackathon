from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from judge.discovery import discover_submissions
from judge.models import Limits, Submission
from judge.staging import SubmissionError, stage_submission


class StagingTests(unittest.TestCase):
    def test_rejects_zip_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "bad.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("../escape", "bad")
            submission = Submission("bad", archive, True)
            with self.assertRaisesRegex(SubmissionError, "unsafe archive path"):
                stage_submission(submission, root / "stage", Limits())

    def test_stages_valid_root_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "Team Alpha"
            source.mkdir()
            (source / "Dockerfile").write_text("FROM scratch", encoding="utf-8")
            (source / "main.py").write_text("", encoding="utf-8")
            found = discover_submissions(root)
            self.assertEqual(found[0].submission_id, "team-alpha")
            source_hash, context_hash = stage_submission(found[0], root / "stage", Limits())
            self.assertEqual(source_hash, context_hash)

    def test_rejects_missing_required_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "team"
            source.mkdir()
            (source / "Dockerfile").write_text("FROM scratch", encoding="utf-8")
            with self.assertRaisesRegex(SubmissionError, "main.py"):
                stage_submission(Submission("team", source, False), root / "stage", Limits())
