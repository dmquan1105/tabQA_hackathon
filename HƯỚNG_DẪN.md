# Hướng dẫn nộp bài

## 1. Cấu trúc tệp nộp

Bài nộp là một thư mục hoặc tệp ZIP không quá 100 MB. `Dockerfile` và `run.sh` phải nằm ngay ở thư mục gốc:

```text
submission.zip
|-- Dockerfile
|-- README.md
|-- run.sh
`-- ...
```

Ảnh Docker phải chạy trên Linux `amd64`, không dùng GPU và chứa sẵn toàn bộ mã nguồn cùng thư viện cần thiết. Không đưa khóa API vào bài nộp.

## 2. Entrypoint bắt buộc

Ảnh Docker phải khai báo đúng:

```dockerfile
ENTRYPOINT ["/solution/run.sh"]
```

`run.sh` phải nằm tại `/solution/run.sh`, có shebang POSIX `/bin/sh`, có quyền thực thi và chuyển nguyên vẹn các tham số bằng `"$@"`. Ví dụ:

```sh
#!/bin/sh
set -eu
exec python /solution/main.py "$@"
```

Chương trình không được yêu cầu nhập liệu tương tác hoặc phụ thuộc vào thư mục làm việc hiện tại. Chỉ thoát với mã `0` sau khi đã ghi xong kết quả; khi lỗi phải thoát với mã khác `0`.

## 3. Các tham số đầu vào

Hệ thống gọi `/solution/run.sh` với đủ sáu tham số bắt buộc:

```text
--xlsx-dir /input/xlsx_files
--queries /input/queries.json
--output /output/submission.csv
--openrouter-key <key>
--openrouter-model qwen/qwen3.7-flash
--openrouter-base-url https://openrouter.ai/api/v1
```

Chương trình phải đọc bảng tính từ `--xlsx-dir`, đọc câu hỏi từ `--queries` và ghi CSV đúng đường dẫn `--output`. Không sửa nội dung trong `/input`. Nhật ký chỉ được ghi ra stdout hoặc stderr.

## 4. Định dạng submission.csv

Tệp kết quả phải là CSV UTF-8 với đúng hai cột theo đúng thứ tự:

```csv
id,answer
1,11
2,Ngo
```

Mỗi `id` trong `queries.json` phải xuất hiện đúng một lần. Không được thiếu, trùng hoặc thêm `id`. `answer` luôn được xem là văn bản và chỉ chứa đáp án cuối cùng, không kèm giải thích. Dùng quy tắc trích dẫn CSV chuẩn nếu đáp án có dấu phẩy hoặc dấu nháy kép.

## 5. Cách kiểm thử bằng Docker

Trong thư mục bài nộp, chạy:

```bash
docker build --platform linux/amd64 -t tabqa-local .

docker run --rm \
  --mount type=bind,src=<sample-data-absolute-path>/xlsx_files,dst=/input/xlsx_files,readonly \
  --mount type=bind,src=<sample-data-absolute-path>/queries.json,dst=/input/queries.json,readonly \
  --mount type=bind,src=<output-absolute-path>,dst=/output \
  tabqa-local \
  --xlsx-dir /input/xlsx_files \
  --queries /input/queries.json \
  --output /output/submission.csv \
  --openrouter-key <key> \
  --openrouter-model qwen/qwen3.7-flash \
  --openrouter-base-url https://openrouter.ai/api/v1
```

Đường dẫn máy chủ phải là đường dẫn tuyệt đối. Nên thử cả đường dẫn có khoảng trắng.

## 6. Giới hạn tài nguyên

- Nền tảng chính thức: Linux `amd64`, không GPU.
- Mỗi lượt chạy có tối đa 6 CPU, 1 GB RAM và 40 phút cho toàn bộ tập dữ liệu.
- Thời gian dựng ảnh không tính vào 40 phút chạy.
- Chi phí LLM tối đa là 0,10 USD nhân với số câu hỏi, tính cả lần gọi lại.
- Mô hình chính thức là `qwen/qwen3.7-flash` qua OpenRouter.

## 7. Danh sách kiểm tra trước khi nộp

- `Dockerfile` và `run.sh` nằm ở gốc thư mục hoặc tệp ZIP.
- `ENTRYPOINT` là chính xác `["/solution/run.sh"]`.
- `run.sh` dùng `/bin/sh`, có quyền thực thi và chuyển tham số bằng `"$@"`.
- Ảnh dựng được cho `linux/amd64` và không cần GPU.
- Chương trình nhận đủ sáu tham số, xử lý được đường dẫn có khoảng trắng và không sửa `/input`.
- `submission.csv` là UTF-8, có header chính xác `id,answer` và mỗi `id` xuất hiện đúng một lần.
- Bài nộp không chứa khóa API và không vượt quá 100 MB.
