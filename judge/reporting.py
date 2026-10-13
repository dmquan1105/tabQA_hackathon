from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import RunResult, Status


def write_result(path: Path, result: RunResult) -> None:
    path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_leaderboard(results_dir: Path, results: list[RunResult]) -> None:
    accepted = [item for item in results if item.status == Status.ACCEPTED]
    others = [item for item in results if item.status != Status.ACCEPTED]
    accepted.sort(
        key=lambda item: (
            -(item.correct or 0),
            item.average_seconds_per_question if item.average_seconds_per_question is not None else float("inf"),
            item.average_tokens_per_question if item.average_tokens_per_question is not None else float("inf"),
            item.submission_id,
        )
    )
    others.sort(key=lambda item: item.submission_id)
    fields = [
        "rank",
        "submission_id",
        "status",
        "correct",
        "total",
        "average_seconds_per_question",
        "average_tokens_per_question",
        "llm_cost_usd",
        "run_id",
    ]
    with (results_dir / "leaderboard.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for rank, item in enumerate(accepted, start=1):
            writer.writerow({"rank": rank, **{key: item.to_dict(public=True).get(key) for key in fields[1:]}})
        for item in others:
            writer.writerow({"rank": "", **{key: item.to_dict(public=True).get(key) for key in fields[1:]}})
