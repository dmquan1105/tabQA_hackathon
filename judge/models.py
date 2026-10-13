from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Status(StrEnum):
    ACCEPTED = "ACCEPTED"
    SUBMISSION_ERROR = "SUBMISSION_ERROR"
    BUILD_ERROR = "BUILD_ERROR"
    IMAGE_ERROR = "IMAGE_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    TIME_LIMIT = "TIME_LIMIT"
    MEMORY_LIMIT = "MEMORY_LIMIT"
    COST_LIMIT = "COST_LIMIT"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    JUDGE_ERROR = "JUDGE_ERROR"


@dataclass(frozen=True)
class Submission:
    submission_id: str
    source: Path
    is_archive: bool


@dataclass(frozen=True)
class RuntimeConfig:
    openrouter_key: str
    openrouter_model: str
    openrouter_base_url: str


@dataclass(frozen=True)
class Limits:
    submission_bytes: int = 104_857_600
    expanded_bytes: int = 524_288_000
    archive_files: int = 10_000
    image_bytes: int = 4_294_967_296
    build_seconds: int = 1_200
    run_seconds: int = 2_400
    memory_bytes: int = 1_073_741_824
    cpus: float = 6
    pids: int = 512
    log_bytes: int = 10_485_760
    output_bytes: int = 10_485_760
    cost_usd_per_question: float = 0.10


@dataclass
class RunResult:
    submission_id: str
    run_id: str
    status: Status = Status.JUDGE_ERROR
    submission_sha256: str = ""
    context_sha256: str = ""
    correct: int | None = None
    total: int | None = None
    build_seconds: float | None = None
    run_seconds: float | None = None
    average_seconds_per_question: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    average_tokens_per_question: float | None = None
    llm_cost_usd: float | None = None
    exit_code: int | None = None
    image_id: str | None = None
    image_size: int | None = None
    queued_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    queue_seconds: float | None = None
    error: str | None = None
    per_question: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self, *, public: bool = False) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        if public:
            value.pop("per_question", None)
        return value
