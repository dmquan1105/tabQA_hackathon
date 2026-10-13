# TabQA Judge

Requires Python 3.12 and Docker. Place submission ZIPs or directories in `solutions/`, then run:

```bash
python -m judge run-all --solutions ./solutions --dataset ./data/hidden --results ./results --openrouter-key <key> --openrouter-model qwen/qwen3.7-flash --openrouter-base-url https://openrouter.ai/api/v1
```

Individual reports and `leaderboard.csv` are written under `results/`.
