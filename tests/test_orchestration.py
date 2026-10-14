from __future__ import annotations

import csv
import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

from judge.__main__ import judge_submission
from judge.docker_runner import BuildOutcome, RunOutcome
from judge.models import Limits, RuntimeConfig, Status, Submission
from judge.reporting import write_leaderboard


class FakeRunner:
    def __init__(self, rows: list[list[str]]) -> None:
        self.rows = rows

    def build(self, context: Path, image_tag: str, stdout_path: Path, stderr_path: Path) -> BuildOutcome:
        return BuildOutcome(None, 1.25, "sha256:image", 1234)

    def run(
        self,
        image_tag: str,
        container_name: str,
        xlsx_dir: Path,
        queries_path: Path,
        output_dir: Path,
        runtime: RuntimeConfig,
        stdout_path: Path,
        stderr_path: Path,
    ) -> RunOutcome:
        with (output_dir / "submission.csv").open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerows(self.rows)
        return RunOutcome(None, 2.0, 0)


class OrchestrationTests(unittest.TestCase):
    def test_success_writes_auditable_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "team"
            source.mkdir()
            (source / "Dockerfile").write_text("FROM scratch", encoding="utf-8")
            (source / "main.py").write_text("", encoding="utf-8")
            xlsx = root / "xlsx_files"
            xlsx.mkdir()
            queries = root / "queries.json"
            queries.write_text('[{"id": 1}]', encoding="utf-8")
            run_dir = root / "result"
            run_dir.mkdir()
            answers_dir = root / "answers"
            result = judge_submission(
                Submission("team", source, False),
                "run-1",
                run_dir,
                datetime.now(timezone.utc),
                xlsx,
                queries,
                ["1"],
                {"1": "yes"},
                RuntimeConfig("secret", "model", "url"),
                Limits(),
                FakeRunner([["id", "answer"], ["1", "yes"]]),  # type: ignore[arg-type]
                threading.Semaphore(1),
                answers_dir=answers_dir,
            )
            self.assertEqual(result.status, Status.ACCEPTED)
            self.assertEqual(result.correct, 1)
            stored = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["status"], "ACCEPTED")
            self.assertTrue((run_dir / "submission.csv").is_file())
            self.assertEqual(
                (answers_dir / "team" / "submission.csv").read_text(encoding="utf-8"),
                (run_dir / "submission.csv").read_text(encoding="utf-8"),
            )
            self.assertFalse((run_dir / "container-output").exists())

    def test_trusted_proxy_usage_enforces_cost_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "team"
            source.mkdir()
            (source / "Dockerfile").write_text("FROM scratch", encoding="utf-8")
            (source / "main.py").write_text("", encoding="utf-8")
            xlsx = root / "xlsx_files"
            xlsx.mkdir()
            queries = root / "queries.json"
            queries.write_text('[{"id": 1}]', encoding="utf-8")
            usage = root / "trusted-usage.json"
            usage.write_text('{"total_tokens": 20, "llm_cost_usd": 0.11}', encoding="utf-8")
            run_dir = root / "result"
            run_dir.mkdir()
            result = judge_submission(
                Submission("team", source, False),
                "run-1",
                run_dir,
                datetime.now(timezone.utc),
                xlsx,
                queries,
                ["1"],
                {"1": "yes"},
                RuntimeConfig("secret", "model", "url"),
                Limits(),
                FakeRunner([["id", "answer"], ["1", "yes"]]),  # type: ignore[arg-type]
                threading.Semaphore(1),
                usage,
            )
            self.assertEqual(result.status, Status.COST_LIMIT)
            self.assertEqual(result.total_tokens, 20)

    def test_leaderboard_uses_official_tie_breaks(self) -> None:
        from judge.models import RunResult

        first = RunResult("slow", "1", Status.ACCEPTED, correct=2, total=2, average_seconds_per_question=2.0)
        second = RunResult("fast", "2", Status.ACCEPTED, correct=2, total=2, average_seconds_per_question=1.0)
        failed = RunResult("broken", "3", Status.BUILD_ERROR)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_leaderboard(root, [first, failed, second])
            with (root / "leaderboard.csv").open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["submission_id"] for row in rows], ["fast", "slow", "broken"])
            self.assertEqual(rows[2]["rank"], "")
