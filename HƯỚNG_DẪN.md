# Hướng dẫn nộp bài

## 1. Cấu trúc tệp nộp

Bài nộp là một thư mục hoặc tệp ZIP không quá 100 MB. Chỉ `Dockerfile` bắt buộc phải nằm ngay ở thư mục gốc; tên và cấu trúc các tệp còn lại do đội tự chọn:

```text
team001.zip
|-- Dockerfile
`-- ...mã nguồn và tệp cần thiết...
```

Ảnh Docker phải chạy trên Linux `amd64`, không dùng GPU và chứa sẵn toàn bộ mã nguồn cùng thư viện cần thiết. Không đưa khóa API vào bài nộp.

## 2. Entrypoint

Ảnh Docker phải khai báo `ENTRYPOINT` để nhận các tham số dòng lệnh từ hệ thống chấm. Không bắt buộc ngôn ngữ hoặc tên tệp cụ thể.

Python:

```dockerfile
ENTRYPOINT ["python", "main.py"]
```

JavaScript:

```dockerfile
ENTRYPOINT ["node", "main.js"]
```

Rust:

```dockerfile
ENTRYPOINT ["./app"]
```

Chương trình được khai báo trong `ENTRYPOINT` phải nhận các tham số do hệ thống chấm cung cấp. Chương trình không được yêu cầu nhập liệu tương tác và chỉ thoát với mã `0` sau khi đã ghi xong kết quả; khi lỗi phải thoát với mã khác `0`.

## 3. Các tham số đầu vào

Hệ thống gọi entrypoint của ảnh Docker với đủ sáu tham số bắt buộc:

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
