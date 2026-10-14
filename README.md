# TabQA Judge

Requires Python 3.12 and Docker. Folder paths and concurrency are configured in
`organizer-config/judge.toml`. OpenRouter credentials are configured in the ignored
`organizer-config/run-config.local.toml`. Keep each contestant directory at the repository
root with its `Dockerfile` at the contestant directory root. Ensure `data/` contains
`xlsx_files/`, `queries.json`, and `answers.csv`, then run:

```bash
python -m judge run-all
```

The configured `team*` glob selects contestant directories and ignores judge support folders.
Each team's latest answer is written to `answers/<team>/submission.csv`.
Individual reports and `leaderboard.csv` are written under `results/`.
Live progress shows each team's current stage, elapsed time, configured time budget,
and the number of completed submissions. Its refresh interval is configured by
`execution.progress_interval_seconds` in `organizer-config/judge.toml`.
