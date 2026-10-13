from __future__ import annotations

import hashlib
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

from .models import Limits, Submission


class SubmissionError(ValueError):
    pass


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda p: p.as_posix()):
        relative = path.relative_to(root).as_posix().encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(hash_file(path)))
    return digest.hexdigest()


def _safe_members(archive: zipfile.ZipFile, limits: Limits) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    if len(members) > limits.archive_files:
        raise SubmissionError(f"archive contains more than {limits.archive_files} entries")
    expanded = 0
    names: set[str] = set()
    for member in members:
        path = PurePosixPath(member.filename.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            raise SubmissionError(f"unsafe archive path: {member.filename}")
        normalized = path.as_posix().rstrip("/")
        if normalized in names:
            raise SubmissionError(f"duplicate archive path: {member.filename}")
        names.add(normalized)
        unix_mode = member.external_attr >> 16
        if stat.S_ISLNK(unix_mode):
            raise SubmissionError(f"archive symlinks are not allowed: {member.filename}")
        expanded += member.file_size
        if expanded > limits.expanded_bytes:
            raise SubmissionError("archive expanded size exceeds the configured limit")
    return members


def _copy_directory(source: Path, target: Path, limits: Limits) -> None:
    total = 0
    count = 0
    for path in source.rglob("*"):
        if path.is_symlink():
            raise SubmissionError(f"submission symlinks are not allowed: {path.relative_to(source)}")
        if path.is_file():
            count += 1
            total += path.stat().st_size
            if count > limits.archive_files or total > limits.expanded_bytes:
                raise SubmissionError("submission exceeds the configured expanded limits")
    shutil.copytree(source, target)


def stage_submission(submission: Submission, target: Path, limits: Limits) -> tuple[str, str]:
    if target.exists():
        raise SubmissionError(f"staging target already exists: {target}")
    if submission.is_archive:
        size = submission.source.stat().st_size
        if size > limits.submission_bytes:
            raise SubmissionError("compressed submission exceeds the configured limit")
        submission_hash = hash_file(submission.source)
        target.mkdir(parents=True)
        try:
            with zipfile.ZipFile(submission.source) as archive:
                members = _safe_members(archive, limits)
                archive.extractall(target, members)
        except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
            raise SubmissionError(f"invalid ZIP archive: {exc}") from exc
    else:
        _copy_directory(submission.source, target, limits)
        submission_hash = hash_tree(submission.source)
    for required in ("Dockerfile",):
        if not (target / required).is_file():
            raise SubmissionError(f"{required} must exist at the submission root")
    return submission_hash, hash_tree(target)
