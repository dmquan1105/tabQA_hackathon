from __future__ import annotations

import csv
import json
import stat
from pathlib import Path


class InvalidOutput(ValueError):
    pass


def canonical_id(value: object) -> str:
    if value is None or isinstance(value, (dict, list)):
        raise ValueError(f"invalid query ID: {value!r}")
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def load_query_ids(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    rows = data.get("queries") if isinstance(data, dict) and "queries" in data else data
    if not isinstance(rows, list):
        raise ValueError("queries.json must be a list or an object containing a queries list")
    ids: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or "id" not in row:
            raise ValueError("every query must be an object containing id")
        ids.append(canonical_id(row["id"]))
    if len(ids) != len(set(ids)):
        raise ValueError("queries.json contains duplicate canonical IDs")
    return ids


def validate_submission(path: Path, query_ids: list[str], max_bytes: int) -> dict[str, str]:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        raise InvalidOutput("submission.csv is missing or is not a regular file")
    if not stat.S_ISREG(mode):
        raise InvalidOutput("submission.csv is missing or is not a regular file")
    if path.stat().st_size > max_bytes:
        raise InvalidOutput("submission.csv exceeds the configured size limit")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            try:
                header = next(reader)
            except StopIteration as exc:
                raise InvalidOutput("submission.csv is empty") from exc
            if header != ["id", "answer"]:
                raise InvalidOutput("CSV header must be exactly id,answer")
            answers: dict[str, str] = {}
            for line_number, row in enumerate(reader, start=2):
                if len(row) != 2:
                    raise InvalidOutput(f"row {line_number} must contain exactly two columns")
                row_id, answer = row
                if row_id in answers:
                    raise InvalidOutput(f"duplicate ID: {row_id}")
                answers[row_id] = answer
    except UnicodeDecodeError as exc:
        raise InvalidOutput("submission.csv must be UTF-8") from exc
    except csv.Error as exc:
        raise InvalidOutput(f"malformed CSV: {exc}") from exc
    expected = set(query_ids)
    actual = set(answers)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise InvalidOutput(f"missing IDs: {', '.join(missing)}")
    if unknown:
        raise InvalidOutput(f"unknown IDs: {', '.join(unknown)}")
    return answers
