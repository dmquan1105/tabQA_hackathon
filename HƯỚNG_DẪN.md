# Hướng dẫn nộp bài

## 1. Cấu trúc tệp nộp

Bài nộp sử dụng Python và được đóng gói thành một thư mục hoặc tệp ZIP không quá 100 MB. `Dockerfile` và `main.py` phải nằm ngay ở thư mục gốc:

```text
team001.zip
|-- Dockerfile
|-- README.md
|-- main.py
`-- ...
```

Ảnh Docker phải chạy trên Linux `amd64`, không dùng GPU và chứa sẵn toàn bộ mã nguồn cùng thư viện cần thiết. Không đưa khóa API vào bài nộp.

## 2. Lệnh khởi động bắt buộc

Ảnh Docker phải khai báo đúng:

```dockerfile
ENTRYPOINT ["python", "main.py"]
```

Khi container khởi động, Docker chạy trực tiếp `main.py`. Tệp này phải nhận các tham số dòng lệnh do hệ thống chấm cung cấp và chỉ thoát với mã `0` sau khi đã ghi xong kết quả.

Chương trình không được yêu cầu nhập liệu tương tác hoặc phụ thuộc vào thư mục làm việc hiện tại. Chỉ thoát với mã `0` sau khi đã ghi xong kết quả; khi lỗi phải thoát với mã khác `0`.

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
