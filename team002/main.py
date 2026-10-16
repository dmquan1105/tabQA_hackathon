"""Entrypoint: answer every query in --queries using the workbooks in --xlsx-dir, write id,answer CSV.

The CSV is rewritten after every answered question, so a run that is stopped early still leaves a
complete file (unanswered ids have an empty answer).
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from agent import LLM, answer_question, choose_table, resolve_table, workbook_signature

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("main")

WORKERS = int(os.environ.get("WORKERS", "4"))
QUESTION_TIME_BUDGET_S = float(os.environ.get("QUESTION_TIME_BUDGET_S", "240"))


def load_queries(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    queries = data["queries"] if isinstance(data, dict) else data
    normalized = []
    for q in queries:
        text = q.get("question") or q.get("query") or q.get("Question") or ""
        normalized.append({**q, "_text": str(text)})
    return normalized


class SubmissionWriter:
    """Keeps all ids in input order and atomically rewrites the CSV whenever an answer arrives."""

    def __init__(self, path: Path, ids: list):
        self.path, self.ids = path, ids
        self.answers = {self._key(i): "" for i in ids}
        self.lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.flush()

    @staticmethod
    def _key(qid) -> str:
        return str(qid)

    def set(self, qid, answer: str) -> None:
        with self.lock:
            self.answers[self._key(qid)] = answer
            self.flush()

    def flush(self) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "answer"])
            for qid in self.ids:
                writer.writerow([qid, self.answers[self._key(qid)]])
        os.replace(tmp, self.path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx-dir", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("output/submission.csv"))
    parser.add_argument("--openrouter-key", required=True)
    parser.add_argument("--openrouter-model", required=True)
    parser.add_argument("--openrouter-base-url", required=True)
    args = parser.parse_args()

    start = time.time()
    queries = load_queries(args.queries)
    writer = SubmissionWriter(args.output, [q["id"] for q in queries])
    files = sorted(p for p in args.xlsx_dir.iterdir() if p.suffix.lower() in (".xlsx", ".xlsm") and not p.name.startswith("~$"))
    log.info("%d queries, %d workbooks, model=%s", len(queries), len(files), args.openrouter_model)
    if not files:
        log.error("no workbook found in %s", args.xlsx_dir)
        return 0

    llm = LLM(args.openrouter_base_url, args.openrouter_key, args.openrouter_model)
    # short descriptions of every workbook, only needed when some query does not name its file
    signatures: dict[Path, str] = {}
    if len(files) > 1 and any(resolve_table(q, args.xlsx_dir) is None for q in queries):
        signatures = {p: workbook_signature(p) for p in files}

    def solve(q: dict) -> tuple:
        table = resolve_table(q, args.xlsx_dir) or choose_table(llm, q["_text"], files, signatures)
        t0 = time.time()
        answer = answer_question(llm, q["_text"], table, QUESTION_TIME_BUDGET_S)
        return q["id"], table.name, answer, time.time() - t0

    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(solve, q): q["id"] for q in queries}
        for fut in as_completed(futures):
            qid = futures[fut]
            try:
                qid, table_name, answer, seconds = fut.result()
                writer.set(qid, answer)
                log.info("[%d/%d] id=%s table=%s %.0fs answer=%r", done + 1, len(queries), qid, table_name, seconds, answer)
            except Exception as exc:
                log.exception("id=%s failed: %s", qid, exc)
            done += 1

    log.info("finished in %.0fs, tokens prompt=%d completion=%d -> %s",
             time.time() - start, llm.prompt_tokens, llm.completion_tokens, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
