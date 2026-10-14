from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from typing import TextIO

from .models import Limits, Status


@dataclass
class ProgressEntry:
    stage: str
    queued_at: float
    stage_started_at: float
    started_at: float | None = None
    stage_limit: float | None = None
    finished: bool = False


def format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class ProgressReporter:
    def __init__(
        self,
        submission_ids: list[str],
        limits: Limits,
        interval_seconds: float = 5,
        stream: TextIO = sys.stdout,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("progress interval must be positive")
        now = time.monotonic()
        self.entries = {
            submission_id: ProgressEntry("QUEUED", now, now)
            for submission_id in submission_ids
        }
        self.limits = limits
        self.interval_seconds = interval_seconds
        self.stream = stream
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def __enter__(self) -> ProgressReporter:
        self._write(f"[progress] tracking {len(self.entries)} submission(s)")
        for submission_id in self.entries:
            self._write_line(submission_id, time.monotonic())
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join()

    def update(self, submission_id: str, stage: str) -> None:
        now = time.monotonic()
        with self.lock:
            entry = self.entries[submission_id]
            entry.stage = stage
            entry.stage_started_at = now
            entry.stage_limit = self._stage_limit(stage)
            if entry.started_at is None and stage != "QUEUED":
                entry.started_at = now
            self._write_line_unlocked(submission_id, now)

    def finish(self, submission_id: str, status: Status) -> None:
        now = time.monotonic()
        with self.lock:
            entry = self.entries[submission_id]
            entry.stage = status.value
            entry.stage_started_at = now
            entry.stage_limit = None
            entry.finished = True
            self._write_line_unlocked(submission_id, now)

    def _stage_limit(self, stage: str) -> float | None:
        if stage == "BUILDING":
            return self.limits.build_seconds
        if stage == "RUNNING":
            return self.limits.run_seconds
        return None

    def _run(self) -> None:
        while not self.stop_event.wait(self.interval_seconds):
            now = time.monotonic()
            with self.lock:
                for submission_id, entry in self.entries.items():
                    if not entry.finished:
                        self._write_line_unlocked(submission_id, now)

    def _write_line(self, submission_id: str, now: float) -> None:
        with self.lock:
            self._write_line_unlocked(submission_id, now)

    def _write_line_unlocked(self, submission_id: str, now: float) -> None:
        entry = self.entries[submission_id]
        stage_elapsed = now - entry.stage_started_at
        if entry.stage == "QUEUED":
            timing = f"queued {format_duration(stage_elapsed)}"
        elif entry.finished:
            started_at = entry.started_at or entry.queued_at
            timing = f"total {format_duration(now - started_at)}"
        else:
            timing = f"stage {format_duration(stage_elapsed)}"
            if entry.stage_limit is not None:
                timing += f" / {format_duration(entry.stage_limit)}"
            if entry.started_at is not None:
                total_limit = self.limits.build_seconds + self.limits.run_seconds
                timing += (
                    f" | total {format_duration(now - entry.started_at)}"
                    f" / {format_duration(total_limit)}"
                )
        finished = sum(item.finished for item in self.entries.values())
        self._write(
            f"[progress] {submission_id} | {entry.stage} | {timing}"
            f" | completed {finished}/{len(self.entries)}"
        )

    def _write(self, message: str) -> None:
        print(message, file=self.stream, flush=True)
