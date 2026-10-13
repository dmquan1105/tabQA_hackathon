from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .models import Limits, RuntimeConfig, Status


@dataclass
class BuildOutcome:
    status: Status | None
    seconds: float
    image_id: str | None = None
    image_size: int | None = None
    error: str | None = None


@dataclass
class RunOutcome:
    status: Status | None
    seconds: float
    exit_code: int | None = None
    error: str | None = None


class DockerRunner:
    def __init__(self, limits: Limits, platform: str = "linux/amd64") -> None:
        self.limits = limits
        self.platform = platform
        self._containers: set[str] = set()
        self._lock = threading.Lock()

    def _run_logged(
        self,
        command: list[str],
        stdout_path: Path,
        stderr_path: Path,
        timeout: int,
        secret: str | None = None,
    ) -> tuple[int | None, float, bool]:
        started = time.monotonic()
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
            try:
                exit_code = process.wait(timeout=timeout)
                timed_out = False
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                exit_code = None
                timed_out = True
        elapsed = time.monotonic() - started
        self._truncate_and_redact(stdout_path, secret)
        self._truncate_and_redact(stderr_path, secret)
        return exit_code, elapsed, timed_out

    def _truncate_and_redact(self, path: Path, secret: str | None) -> None:
        data = path.read_bytes()
        if len(data) > self.limits.log_bytes:
            marker = b"\n[log truncated by judge]\n"
            data = data[: max(0, self.limits.log_bytes - len(marker))] + marker
        if secret:
            data = data.replace(secret.encode(), b"[REDACTED]")
        path.write_bytes(data)

    def _docker_json(self, command: list[str]) -> dict:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "Docker inspection failed")
        return json.loads(completed.stdout)

    def build(
        self,
        context: Path,
        image_tag: str,
        stdout_path: Path,
        stderr_path: Path,
    ) -> BuildOutcome:
        command = [
            "docker",
            "build",
            "--platform",
            self.platform,
            "--tag",
            image_tag,
            str(context),
        ]
        try:
            exit_code, seconds, timed_out = self._run_logged(
                command, stdout_path, stderr_path, self.limits.build_seconds
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return BuildOutcome(Status.JUDGE_ERROR, 0.0, error=str(exc))
        if timed_out:
            return BuildOutcome(Status.BUILD_ERROR, seconds, error="Docker build timed out")
        if exit_code != 0:
            return BuildOutcome(Status.BUILD_ERROR, seconds, error=f"Docker build exited {exit_code}")
        try:
            image = self._docker_json(["docker", "image", "inspect", image_tag])[0]
            entrypoint = image.get("Config", {}).get("Entrypoint")
            image_id = image.get("Id")
            image_size = int(image.get("Size", 0))
        except (OSError, subprocess.SubprocessError, RuntimeError, ValueError, KeyError) as exc:
            return BuildOutcome(Status.JUDGE_ERROR, seconds, error=str(exc))
        if entrypoint != ["/solution/run.sh"]:
            return BuildOutcome(
                Status.IMAGE_ERROR,
                seconds,
                image_id,
                image_size,
                'image entrypoint must be exactly ["/solution/run.sh"]',
            )
        if image_size > self.limits.image_bytes:
            return BuildOutcome(
                Status.IMAGE_ERROR,
                seconds,
                image_id,
                image_size,
                "image exceeds the configured size limit",
            )
        return BuildOutcome(None, seconds, image_id, image_size)

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
        command = [
            "docker",
            "run",
            "--name",
            container_name,
            "--platform",
            self.platform,
            "--cpus",
            str(self.limits.cpus),
            "--memory",
            str(self.limits.memory_bytes),
            "--memory-swap",
            str(self.limits.memory_bytes),
            "--pids-limit",
            str(self.limits.pids),
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--tmpfs",
            "/tmp:rw,size=256m",
            "--mount",
            f"type=bind,src={xlsx_dir.resolve()},dst=/input/xlsx_files,readonly",
            "--mount",
            f"type=bind,src={queries_path.resolve()},dst=/input/queries.json,readonly",
            "--mount",
            f"type=bind,src={output_dir.resolve()},dst=/output",
            image_tag,
            "--xlsx-dir",
            "/input/xlsx_files",
            "--queries",
            "/input/queries.json",
            "--output",
            "/output/submission.csv",
            "--openrouter-key",
            runtime.openrouter_key,
            "--openrouter-model",
            runtime.openrouter_model,
            "--openrouter-base-url",
            runtime.openrouter_base_url,
        ]
        with self._lock:
            self._containers.add(container_name)
        try:
            try:
                exit_code, seconds, timed_out = self._run_logged(
                    command,
                    stdout_path,
                    stderr_path,
                    self.limits.run_seconds,
                    runtime.openrouter_key,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                return RunOutcome(Status.JUDGE_ERROR, 0.0, error=str(exc).replace(runtime.openrouter_key, "[REDACTED]"))
            if timed_out:
                subprocess.run(["docker", "rm", "--force", container_name], capture_output=True)
                return RunOutcome(Status.TIME_LIMIT, seconds, error="execution time limit exceeded")
            try:
                state = self._docker_json(["docker", "container", "inspect", container_name])[0]["State"]
            except (OSError, subprocess.SubprocessError, RuntimeError, KeyError, IndexError) as exc:
                return RunOutcome(Status.JUDGE_ERROR, seconds, exit_code, str(exc))
            if state.get("OOMKilled"):
                return RunOutcome(Status.MEMORY_LIMIT, seconds, exit_code, "container was OOM-killed")
            if exit_code != 0:
                return RunOutcome(Status.RUNTIME_ERROR, seconds, exit_code, f"container exited {exit_code}")
            return RunOutcome(None, seconds, exit_code)
        finally:
            subprocess.run(["docker", "rm", "--force", container_name], capture_output=True)
            with self._lock:
                self._containers.discard(container_name)

    def cleanup(self) -> None:
        with self._lock:
            names = list(self._containers)
        for name in names:
            subprocess.run(["docker", "rm", "--force", name], capture_output=True)
