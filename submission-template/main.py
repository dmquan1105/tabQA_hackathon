from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx-dir", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--openrouter-key", required=True)
    parser.add_argument("--openrouter-model", required=True)
    parser.add_argument("--openrouter-base-url", required=True)
    args = parser.parse_args()

    data = json.loads(args.queries.read_text(encoding="utf-8-sig"))
    queries = data.get("queries", data) if isinstance(data, dict) else data
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "answer"])
        for query in queries:
            # Replace this placeholder with the team's TabQA implementation.
            writer.writerow([query["id"], ""])


if __name__ == "__main__":
    main()
