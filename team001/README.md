# team001

Naive TabQA baseline: each workbook is converted to CSV text and sent to the
configured OpenRouter model in one request per question.

```bash
docker build -t team001 .
docker run --rm team001 \
  --xlsx-dir /input/xlsx_files \
  --queries /input/queries.json \
  --output /output/submission.csv \
  --openrouter-key KEY \
  --openrouter-model qwen/qwen3.7-flash \
  --openrouter-base-url https://openrouter.ai/api/v1
```
