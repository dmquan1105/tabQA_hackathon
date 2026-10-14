from __future__ import annotations

import os
import tomllib
from dataclasses import fields
from pathlib import Path
from typing import Any

from .models import Limits, RuntimeConfig


DEFAULT_MODEL = "qwen/qwen3.7-flash"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def _read_toml(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_limits(path: Path | None) -> Limits:
    raw = _read_toml(path).get("limits", {})
    allowed = {item.name for item in fields(Limits)}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"unknown limit settings: {', '.join(sorted(unknown))}")
    return Limits(**raw)


def load_execution(path: Path | None) -> dict[str, Any]:
    return _read_toml(path).get("execution", {})


def load_judge_runtime(path: Path | None) -> dict[str, Any]:
    return _read_toml(path).get("runtime", {})


def load_paths(path: Path | None) -> dict[str, Path]:
    raw = _read_toml(path).get("paths", {})
    allowed = {"solutions", "dataset", "answers", "results"}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"unknown path settings: {', '.join(sorted(unknown))}")
    base = path.resolve().parent if path is not None else Path.cwd()
    paths: dict[str, Path] = {}
    for name, value in raw.items():
        configured = Path(str(value))
        paths[name] = configured.resolve() if configured.is_absolute() else (base / configured).resolve()
    return paths


def load_runtime_file(path: Path | None) -> dict[str, Any]:
    return _read_toml(path)


def resolve_runtime_config(
    submission_id: str,
    runtime_file: dict[str, Any],
    cli_key: str | None,
    cli_model: str | None,
    cli_base_url: str | None,
) -> RuntimeConfig:
    defaults = runtime_file.get("defaults", {})
    solution = runtime_file.get("solutions", {}).get(submission_id, {})

    def choose(name: str, cli_value: str | None, env_name: str) -> str:
        value = solution.get(name) or defaults.get(name) or cli_value or os.getenv(env_name)
        if not value:
            raise ValueError(f"missing required runtime value {name!r} for {submission_id}")
        return str(value)

    return RuntimeConfig(
        openrouter_key=choose("openrouter_key", cli_key, "OPENROUTER_API_KEY"),
        openrouter_model=choose("openrouter_model", cli_model, "OPENROUTER_MODEL"),
        openrouter_base_url=choose("openrouter_base_url", cli_base_url, "OPENROUTER_BASE_URL"),
    )
