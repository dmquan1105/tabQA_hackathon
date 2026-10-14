from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from .config import load_execution, load_judge_runtime, load_limits, load_paths, load_runtime_file, resolve_runtime_config
from .discovery import discover_submissions, submission_from_path
from .docker_runner import DockerRunner
from .models import Limits, RunResult, RuntimeConfig, Status, Submission
from .progress import ProgressReporter
from .reporting import write_leaderboard, write_result
from .scorer import load_answers, score_answers
from .staging import SubmissionError, stage_submission
from .submission_checker import InvalidOutput, load_query_ids, validate_submission


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def make_run_id() -> str:
    return f"{utc_now():%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"


def validate_dataset(dataset: Path, answers_path: Path) -> tuple[Path, Path, list[str], dict[str, str]]:
    xlsx_dir = dataset / "xlsx_files"
    queries_path = dataset / "queries.json"
    if not xlsx_dir.is_dir():
        raise ValueError(f"dataset xlsx_files directory does not exist: {xlsx_dir}")
    if not queries_path.is_file():
        raise ValueError(f"dataset queries.json does not exist: {queries_path}")
    query_ids = load_query_ids(queries_path)
    expected = load_answers(answers_path)
    if set(query_ids) != set(expected):
        raise ValueError("answers.csv IDs do not match queries.json IDs")
    return xlsx_dir, queries_path, query_ids, expected


def read_usage(path: Path, limits: Limits) -> dict[str, object]:
    usage = {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "llm_cost_usd": None,
    }
    if not path.is_file() or path.is_symlink() or path.stat().st_size > limits.output_bytes:
        return usage
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        for key in usage:
            if key in raw:
                usage[key] = float(raw[key]) if key == "llm_cost_usd" else int(raw[key])
    except (OSError, UnicodeError, ValueError, TypeError):
        return usage
    if usage["total_tokens"] is None and usage["prompt_tokens"] is not None and usage["completion_tokens"] is not None:
        usage["total_tokens"] = int(usage["prompt_tokens"]) + int(usage["completion_tokens"])
    return usage


def apply_usage(result: RunResult, usage: dict[str, object], query_count: int) -> None:
    result.prompt_tokens = usage["prompt_tokens"] if isinstance(usage["prompt_tokens"], int) else None
    result.completion_tokens = usage["completion_tokens"] if isinstance(usage["completion_tokens"], int) else None
    result.total_tokens = usage["total_tokens"] if isinstance(usage["total_tokens"], int) else None
    result.llm_cost_usd = usage["llm_cost_usd"] if isinstance(usage["llm_cost_usd"], float) else None
    if result.total_tokens is not None:
        result.average_tokens_per_question = result.total_tokens / query_count if query_count else 0.0


def check_host_memory(max_concurrent: int, limits: Limits) -> None:
    meminfo = Path("/proc/meminfo")
    if not meminfo.is_file():
        return
    values = {}
    for line in meminfo.read_text(encoding="ascii").splitlines():
        name, value = line.split(":", 1)
        values[name] = int(value.strip().split()[0]) * 1024
    available = values.get("MemAvailable")
    required = max_concurrent * limits.memory_bytes
    reserve = max(1_073_741_824, available // 5) if available else 0
    if available is not None and required + reserve > available:
        raise ValueError(
            f"requested concurrency needs {required} bytes plus {reserve} bytes host reserve, "
            f"but only {available} bytes are available"
        )


def judge_submission(
    submission: Submission,
    run_id: str,
    run_dir: Path,
    queued_at: datetime,
    xlsx_dir: Path,
    queries_path: Path,
    query_ids: list[str],
    expected: dict[str, str],
    runtime: RuntimeConfig,
    limits: Limits,
    runner: DockerRunner,
    build_semaphore: threading.Semaphore,
    usage_path: Path | None = None,
    answers_dir: Path | None = None,
    progress: ProgressReporter | None = None,
) -> RunResult:
    result = RunResult(submission.submission_id, run_id, total=len(query_ids), queued_at=iso(queued_at))
    if progress is not None:
        progress.update(submission.submission_id, "STAGING")
    started_at = utc_now()
    result.started_at = iso(started_at)
    result.queue_seconds = (started_at - queued_at).total_seconds()
    output_dir = run_dir / "container-output"
    output_dir.mkdir()
    for log_name in ("build.stdout.log", "build.stderr.log", "run.stdout.log", "run.stderr.log"):
        (run_dir / log_name).touch()
    try:
        with tempfile.TemporaryDirectory(prefix=f"tabqa-{submission.submission_id}-") as temporary:
            context = Path(temporary) / "context"
            try:
                result.submission_sha256, result.context_sha256 = stage_submission(submission, context, limits)
            except SubmissionError as exc:
                result.status = Status.SUBMISSION_ERROR
                result.error = str(exc)
                return result

            image_tag = f"tabqa-{submission.submission_id}:{result.context_sha256[:12]}"
            if progress is not None:
                progress.update(submission.submission_id, "WAITING_FOR_BUILD")
            with build_semaphore:
                if progress is not None:
                    progress.update(submission.submission_id, "BUILDING")
                build = runner.build(
                    context,
                    image_tag,
                    run_dir / "build.stdout.log",
                    run_dir / "build.stderr.log",
                )
            result.build_seconds = build.seconds
            result.image_id = build.image_id
            result.image_size = build.image_size
            if build.status is not None:
                result.status = build.status
                result.error = build.error
                return result

            container_name = f"tabqa-{submission.submission_id}-{run_id}".lower()
            if progress is not None:
                progress.update(submission.submission_id, "RUNNING")
            outcome = runner.run(
                image_tag,
                container_name,
                xlsx_dir,
                queries_path,
                output_dir,
                runtime,
                run_dir / "run.stdout.log",
                run_dir / "run.stderr.log",
            )
            result.run_seconds = outcome.seconds
            result.exit_code = outcome.exit_code
            usage = read_usage(usage_path, limits) if usage_path is not None else {
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
                "llm_cost_usd": None,
            }
            apply_usage(result, usage, len(query_ids))
            if result.llm_cost_usd is not None and result.llm_cost_usd > len(query_ids) * limits.cost_usd_per_question:
                result.status = Status.COST_LIMIT
                result.error = "proxy-reported LLM cost exceeds the configured limit"
                return result
            if outcome.status is not None:
                result.status = outcome.status
                result.error = outcome.error
                return result

            if progress is not None:
                progress.update(submission.submission_id, "VALIDATING")
            try:
                submitted = validate_submission(output_dir / "submission.csv", query_ids, limits.output_bytes)
            except InvalidOutput as exc:
                result.status = Status.INVALID_OUTPUT
                result.error = str(exc)
                return result
            if progress is not None:
                progress.update(submission.submission_id, "SCORING")
            result.correct, result.per_question = score_answers(expected, submitted)
            result.average_seconds_per_question = result.run_seconds / result.total if result.total else 0.0
            if progress is not None:
                progress.update(submission.submission_id, "SAVING_RESULTS")
            shutil.copy2(output_dir / "submission.csv", run_dir / "submission.csv")
            if answers_dir is not None:
                team_answers = answers_dir / submission.submission_id
                team_answers.mkdir(parents=True, exist_ok=True)
                shutil.copy2(output_dir / "submission.csv", team_answers / "submission.csv")
            result.status = Status.ACCEPTED
            return result
    except Exception as exc:
        result.status = Status.JUDGE_ERROR
        result.error = str(exc).replace(runtime.openrouter_key, "[REDACTED]")
        return result
    finally:
        result.finished_at = iso(utc_now())
        shutil.rmtree(output_dir, ignore_errors=True)
        write_result(run_dir / "result.json", result)
        if progress is not None:
            progress.finish(submission.submission_id, result.status)


def add_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--openrouter-key")
    parser.add_argument("--openrouter-model")
    parser.add_argument("--openrouter-base-url")
    parser.add_argument(
        "--runtime-config",
        type=Path,
        default=Path("organizer-config/run-config.local.toml"),
    )
    parser.add_argument("--judge-config", type=Path, default=Path("organizer-config/judge.toml"))
    parser.add_argument("--answers", type=Path)
    parser.add_argument(
        "--usage-dir",
        type=Path,
        help="organizer-only proxy metrics root: <submission-id>/<run-id>.json",
    )


def effective_config_path(path: Path) -> Path | None:
    return path if path.is_file() else None


def configured_path(cli_value: Path | None, paths: dict[str, Path], name: str) -> Path:
    value = cli_value or paths.get(name)
    if value is None:
        option = "answers-dir" if name == "answers" else name
        raise ValueError(f"missing required path {name!r}; set --{option} or [paths].{name}")
    return value


def execute_one(args: argparse.Namespace) -> int:
    submission = submission_from_path(args.solution)
    config_path = effective_config_path(args.judge_config)
    limits = load_limits(config_path)
    execution = load_execution(config_path)
    judge_runtime = load_judge_runtime(config_path)
    paths = load_paths(config_path)
    dataset = configured_path(args.dataset, paths, "dataset")
    results = configured_path(args.results, paths, "results")
    answers_dir = configured_path(args.answers_dir, paths, "answers")
    runtime_file = load_runtime_file(args.runtime_config)
    runtime = resolve_runtime_config(
        submission.submission_id,
        runtime_file,
        args.openrouter_key,
        args.openrouter_model or judge_runtime.get("model"),
        args.openrouter_base_url or judge_runtime.get("openrouter_base_url"),
    )
    answers_path = args.answers or dataset / "answers.csv"
    xlsx_dir, queries_path, query_ids, expected = validate_dataset(dataset, answers_path)
    run_id = make_run_id()
    run_dir = results / submission.submission_id / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    runner = DockerRunner(limits, str(judge_runtime.get("platform", "linux/amd64")))
    try:
        with ProgressReporter(
            [submission.submission_id],
            limits,
            float(execution.get("progress_interval_seconds", 5)),
        ) as progress:
            result = judge_submission(
                submission,
                run_id,
                run_dir,
                utc_now(),
                xlsx_dir,
                queries_path,
                query_ids,
                expected,
                runtime,
                limits,
                runner,
                threading.Semaphore(1),
                args.usage_dir / submission.submission_id / f"{run_id}.json" if args.usage_dir else None,
                answers_dir,
                progress,
            )
    finally:
        runner.cleanup()
    print(json.dumps(result.to_dict(public=True), ensure_ascii=False, indent=2))
    return 0 if result.status == Status.ACCEPTED else 1


def execute_all(args: argparse.Namespace) -> int:
    config_path = effective_config_path(args.judge_config)
    limits = load_limits(config_path)
    execution = load_execution(config_path)
    judge_runtime = load_judge_runtime(config_path)
    paths = load_paths(config_path)
    solutions = configured_path(args.solutions, paths, "solutions")
    dataset = configured_path(args.dataset, paths, "dataset")
    answers_dir = configured_path(args.answers_dir, paths, "answers")
    results_dir = configured_path(args.results, paths, "results")
    submissions = discover_submissions(solutions, str(execution.get("solution_glob", "*")))
    max_concurrent = args.max_concurrent or int(execution.get("max_concurrent", 1))
    max_builds = args.max_concurrent_builds or int(execution.get("max_concurrent_builds", 1))
    if max_concurrent < 1 or max_builds < 1:
        raise ValueError("concurrency values must be positive")
    check_host_memory(max_concurrent, limits)
    runtime_file = load_runtime_file(args.runtime_config)
    runtimes = {
        item.submission_id: resolve_runtime_config(
            item.submission_id,
            runtime_file,
            args.openrouter_key,
            args.openrouter_model or judge_runtime.get("model"),
            args.openrouter_base_url or judge_runtime.get("openrouter_base_url"),
        )
        for item in submissions
    }
    answers_path = args.answers or dataset / "answers.csv"
    xlsx_dir, queries_path, query_ids, expected = validate_dataset(dataset, answers_path)
    results_dir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for submission in submissions:
        run_id = make_run_id()
        run_dir = results_dir / submission.submission_id / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        jobs.append((submission, run_id, run_dir, utc_now()))

    runner = DockerRunner(limits, str(judge_runtime.get("platform", "linux/amd64")))
    build_semaphore = threading.Semaphore(max_builds)
    results: list[RunResult] = []
    try:
        with ProgressReporter(
            [submission.submission_id for submission, _, _, _ in jobs],
            limits,
            float(execution.get("progress_interval_seconds", 5)),
        ) as progress:
            with ThreadPoolExecutor(max_workers=max_concurrent) as pool:
                futures = [
                    pool.submit(
                        judge_submission,
                        submission,
                        run_id,
                        run_dir,
                        queued_at,
                        xlsx_dir,
                        queries_path,
                        query_ids,
                        expected,
                        runtimes[submission.submission_id],
                        limits,
                        runner,
                        build_semaphore,
                        args.usage_dir / submission.submission_id / f"{run_id}.json" if args.usage_dir else None,
                        answers_dir,
                        progress,
                    )
                    for submission, run_id, run_dir, queued_at in jobs
                ]
                for future in as_completed(futures):
                    results.append(future.result())
    finally:
        runner.cleanup()
    write_leaderboard(results_dir, results)
    return 0 if all(item.status == Status.ACCEPTED for item in results) else 1


def execute_validate(args: argparse.Namespace) -> int:
    query_ids = load_query_ids(args.queries)
    answers = validate_submission(args.submission, query_ids, args.max_bytes)
    print(json.dumps({"valid": True, "rows": len(answers)}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m judge")
    commands = parser.add_subparsers(dest="command", required=True)

    run_one = commands.add_parser("run-one", help="judge one directory or ZIP submission")
    run_one.add_argument("--solution", type=Path, required=True)
    run_one.add_argument("--dataset", type=Path)
    run_one.add_argument("--answers-dir", type=Path)
    run_one.add_argument("--results", type=Path)
    add_runtime_arguments(run_one)
    run_one.set_defaults(handler=execute_one)

    run_all = commands.add_parser("run-all", help="judge every submission in a directory")
    run_all.add_argument("--solutions", type=Path)
    run_all.add_argument("--dataset", type=Path)
    run_all.add_argument("--answers-dir", type=Path)
    run_all.add_argument("--results", type=Path)
    run_all.add_argument("--max-concurrent", type=int)
    run_all.add_argument("--max-concurrent-builds", type=int)
    add_runtime_arguments(run_all)
    run_all.set_defaults(handler=execute_all)

    validate = commands.add_parser("validate", help="validate a submission CSV")
    validate.add_argument("--queries", type=Path, required=True)
    validate.add_argument("--submission", type=Path, required=True)
    validate.add_argument("--max-bytes", type=int, default=10_485_760)
    validate.set_defaults(handler=execute_validate)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.handler(args)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
