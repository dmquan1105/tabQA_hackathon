from __future__ import annotations

import io
import unittest

from judge.models import Limits, Status
from judge.progress import ProgressReporter


class ProgressReporterTests(unittest.TestCase):
    def test_reports_stage_budget_and_completion(self) -> None:
        stream = io.StringIO()
        limits = Limits(build_seconds=120, run_seconds=240)

        with ProgressReporter(["team001"], limits, interval_seconds=60, stream=stream) as progress:
            progress.update("team001", "BUILDING")
            progress.finish("team001", Status.ACCEPTED)

        output = stream.getvalue()
        self.assertIn("team001 | BUILDING", output)
        self.assertIn("stage 00:00:00 / 00:02:00", output)
        self.assertIn("total 00:00:00 / 00:06:00", output)
        self.assertIn("team001 | ACCEPTED", output)
        self.assertIn("completed 1/1", output)

    def test_rejects_non_positive_interval(self) -> None:
        with self.assertRaisesRegex(ValueError, "progress interval"):
            ProgressReporter([], Limits(), interval_seconds=0)
