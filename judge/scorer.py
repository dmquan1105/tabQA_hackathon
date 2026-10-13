from __future__ import annotations

import csv
from pathlib import Path


def load_answers(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError("answers.csv is empty") from exc
        if header != ["id", "answer"]:
            raise ValueError("answers.csv header must be exactly id,answer")
        answers: dict[str, str] = {}
        for row in reader:
            if len(row) != 2:
                raise ValueError("answers.csv rows must contain exactly two columns")
            if row[0] in answers:
                raise ValueError(f"duplicate answer ID: {row[0]}")
            answers[row[0]] = row[1]
    return answers


def score_answers(
    expected: dict[str, str], submitted: dict[str, str]
) -> tuple[int, list[dict[str, object]]]:
    if set(expected) != set(submitted):
        raise ValueError("expected and submitted ID sets differ")
    audit = [
        {"id": row_id, "correct": submitted[row_id] == expected[row_id]}
        for row_id in expected
    ]
    return sum(bool(row["correct"]) for row in audit), audit
