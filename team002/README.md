# Giải pháp: code agent cho hỏi đáp trên Excel

## Cách hoạt động

Với mỗi câu hỏi:

1. **Chọn bảng**: nếu câu hỏi có `file_name` (hoặc `file`, `table`...) thì dùng tệp đó; nếu không, mô hình chọn trong danh sách bảng tính dựa trên tên sheet và vài dòng đầu (dự phòng: so khớp từ khoá).
2. **Code agent** (tối đa 8 bước): mô hình nhận bản xem trước của workbook (tên sheet, kích thước, ô gộp, 20 dòng đầu kèm số dòng/chữ cột) và câu hỏi, rồi viết code pandas/openpyxl. Mỗi khối code chạy trong một tiến trình Python riêng (timeout 60 s), stdout được gửi lại cho mô hình. Khi chắc chắn, mô hình trả `FINAL ANSWER: ...`.
3. **Dự phòng**: nếu agent không cho ra đáp án, gửi toàn bộ bảng (CSV từng sheet, tối đa 300k ký tự) trong một prompt.
4. **Chuẩn hoá đáp án**: một dòng, bỏ markdown, dấu chấm cuối, giải thích.

Các câu hỏi chạy song song (`WORKERS`, mặc định 4). Tệp `submission.csv` được ghi lại (atomic) sau mỗi câu trả lời, nên nếu bị dừng giữa chừng vẫn có tệp đầy đủ các `id` (câu chưa xong có đáp án rỗng).

## Chạy

```bash
docker build --platform linux/amd64 -t team-solution .
docker run --rm -v /path/data:/input:ro -v /path/out:/output team-solution \
  --xlsx-dir /input/xlsx_files --queries /input/queries.json --output /output/submission.csv \
  --openrouter-key $OPENROUTER_KEY --openrouter-model qwen/qwen3.7-flash \
  --openrouter-base-url https://openrouter.ai/api/v1
```

Biến môi trường tuỳ chọn: `WORKERS` (số câu chạy song song, mặc định 4), `QUESTION_TIME_BUDGET_S` (thời gian tối đa cho vòng lặp agent mỗi câu, mặc định 240 s).

`queries.json` có thể là danh sách hoặc `{"queries": [...]}`; trường câu hỏi là `question` hoặc `query`.

Không chứa khoá API; mọi lời gọi mô hình dùng các tham số `--openrouter-*` do hệ thống chấm cung cấp.
