from __future__ import annotations

import re
from pathlib import Path

from .models import Submission


def sanitize_submission_id(name: str) -> str:
    value = re.sub(r"[^a-z0-9_.-]+", "-", name.lower()).strip("-._")
    if not value:
        raise ValueError(f"submission name {name!r} has no usable characters")
    return value[:80]


def submission_from_path(path: Path) -> Submission:
    path = path.resolve()
    if path.is_dir():
        source_name = path.name
        is_archive = False
    elif path.is_file() and path.suffix.lower() == ".zip":
        source_name = path.stem
        is_archive = True
    else:
        raise ValueError(f"unsupported submission: {path}")
    return Submission(sanitize_submission_id(source_name), path, is_archive)


def discover_submissions(directory: Path, pattern: str = "*") -> list[Submission]:
    if not directory.is_dir():
        raise ValueError(f"solutions directory does not exist: {directory}")
    submissions: list[Submission] = []
    for child in directory.iterdir():
        if not child.match(pattern):
            continue
        if child.is_dir() and (child / "Dockerfile").is_file():
            submissions.append(submission_from_path(child))
        elif child.is_file() and child.suffix.lower() == ".zip":
            submissions.append(submission_from_path(child))
    submissions.sort(key=lambda item: item.submission_id)
    ids = [item.submission_id for item in submissions]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        raise ValueError(f"duplicate submission IDs: {', '.join(duplicates)}")
    return submissions
