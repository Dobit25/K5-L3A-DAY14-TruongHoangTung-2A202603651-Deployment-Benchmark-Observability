# Day 14 · Mission answers

## Part 1 · Hai phiên bản của cùng một API

Gọi `POST /ask?question=Hello` trên bản develop trả HTTP 200 và một câu trả lời mock. Bản production mở `GET /health` với trạng thái `ok`, version `1.0.0` và environment `development`.

| Quan sát trong `01-localhost-vs-production/develop/app.py` | Cách xử lý trong bản production | Tác động |
|---|---|---|
| Dòng 17–18 đặt khóa giả và chuỗi kết nối ngay trong source | `config.py` đọc biến môi trường | Tách quyền truy cập khỏi lịch sử Git và có thể đổi theo môi trường. |
| Dòng 34 in cả khóa ra stdout | Log sự kiện có tên và metadata | Người xem log vận hành không cần quyền xem bí mật. |
| Cờ debug cố định và tự reload ở entry point | Cấu hình debug riêng | Tránh khởi chạy lại worker ngoài ý muốn. |
| Bind localhost, cố định cổng 8000 | Bind theo HOST và PORT | Router của cloud gọi được container đúng cổng. |
| Chỉ có trang gốc và endpoint hỏi đáp | Có health và readiness riêng | Điều phối viên quyết định restart hoặc rút instance khỏi luồng traffic. |
| Thiếu vòng đời quản lý tài nguyên | Lifespan đánh dấu ready lúc startup và dọn lúc shutdown | Request mới chỉ đến khi agent sẵn sàng. |

Trong phép thử bằng CLI Uvicorn, handler SIGTERM riêng của app mẫu Part 1 chỉ ghi log, process phải nhận thêm tín hiệu để thoát. Part 6 giao việc ngừng nhận và đợi request cho Uvicorn, sau đó đóng Redis trong lifespan.

## Part 2 · Docker

1. Dockerfile develop dùng `python:3.11` và đặt thư mục làm việc là `/app`.
2. Copy manifest yêu cầu và cài trước khi copy ứng dụng để sửa code vẫn tái sử dụng layer dependency.
3. `ENTRYPOINT` định nghĩa chương trình chính. `CMD` cho lệnh hoặc đối số mặc định và có thể ghi đè khi chạy container. Bản develop dùng `CMD ["python","app.py"]`.
4. Bản advanced cài dependency ở builder, chuyển phần runtime cần dùng sang Python slim, rồi chạy Uvicorn dưới user không phải root.

| Tag build từ gốc repo | `docker images`, dung lượng hiển thị | `docker image inspect`, trường Size |
|---|---:|---:|
| `day14-tung:develop` | 1.67 GB (xấp xỉ 1.670 MB theo đơn vị thập phân) | 426.320.040 byte |
| `day14-tung:advanced` | 240 MB | 57.409.115 byte |

Theo cùng cột `docker images`, dung lượng giảm khoảng **85,6%**. Hai lệnh của Docker Desktop hiển thị cách tính dung lượng khác nhau. Container develop trả lời được yêu cầu query. Trong Compose, **client → Nginx → agent**, agent được cấu hình tới Redis và Qdrant trên mạng nội bộ. Nginx trả `/health` với `status=ok, version=2.0.0` và `POST /ask` trả một câu trả lời mock. Hai endpoint được gọi qua Nginx sau khi dependency của stack sẵn sàng.

## Part 3 · Deploy

Dịch vụ Part 6 chạy trên Render Singapore. Bốn phép thử public, cấu hình và ảnh có trong [DEPLOYMENT.md](DEPLOYMENT.md).

Ví dụ Railway cấu hình builder Nixpacks, lệnh start, đường dẫn health và chính sách restart cho ứng dụng. Ví dụ Render mô tả một danh sách dịch vụ, bao gồm web, Redis, vùng chạy, plan và cách cấp secret. Trong bài này Blueprint dùng Dockerfile của Part 6, Key Value private và `connectionString` qua mạng nội bộ. Cùng một image có thể dùng ở local và Render.

**Pipeline Cloud Run.** Bước test trong `cloudbuild.yaml` cài dependency và chạy pytest. Bước build gắn tag commit SHA và `latest`, rồi push lên registry. Bước deploy dùng image theo SHA, khai báo vùng, CPU, RAM và Secret Manager. `service.yaml` mô tả revision, concurrency 80, quy mô 1–10 instance, startup probe `/ready` và liveness `/health`.

## Part 4 · API security

Bản develop kiểm header trong dependency `verify_api_key`. Thiếu key trả 401, key sai được code mẫu xử lý bằng 403. Đổi biến môi trường và restart process để xoay key. Part 6 xử lý cả hai trường hợp bằng 401 theo hợp đồng riêng.

Bản production cấp JWT ở `POST /auth/token`, ký HS256, có hạn 60 phút. Gọi `POST /ask` bằng Bearer token của tài khoản demo student thành công 10 lần trong cửa sổ 60 giây, lần 11 bị chặn. Limiter dùng deque timestamp theo user, loại timestamp cũ trước khi đếm. Role admin có trần 100/phút. Mẫu Part 4 giữ state trong process, Part 6 dùng sorted set Redis và thực hiện kiểm tra/cập nhật nguyên tử.

Trích output thực từ `curl -i` (lược bớt các header thông thường):

```http
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

HTTP/1.1 200 OK
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}

HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
retry-after: 59
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

Rate limit tính lượt trong một phút. Cost guard tính tiền theo input/output tokens và ngân sách, nên hai request cùng tính một lượt vẫn có thể khác chi phí. Mẫu Part 4 kiểm ngân sách ngày của user và ngân sách toàn hệ thống rồi ghi usage. Part 6 giữ ngân sách ngày và tháng theo UTC trong Redis. Trước khi gọi mock, mỗi worker giữ trước mức chi tối đa có thể phát sinh rồi hoàn lại phần dư sau khi có câu trả lời. Checker cấp budget rất nhỏ và quan sát 402 ở request đầu.

## Part 5 · Scaling và reliability

- Trong bản develop, `GET /health` trả `status=ok`, `/ready` trả `ready=true`. Request đã bắt đầu trước SIGTERM vẫn nhận câu trả lời. Handler trong ví dụ giữ process sống, còn checker Part 6 kiểm riêng cả thoát process lẫn trả lời request.
- Chạy Compose với `--scale agent=3`, dùng `test_stateless.py` qua Nginx ở cổng 8080. Năm câu trong cùng session được phục vụ bởi `instance-011358`, `instance-996031` và `instance-d8b5d1`. Đọc lại được **10 message** gồm đủ 5 cặp hỏi/đáp.
- Nginx phân phối request giữa các worker, Redis giữ lịch sử theo session. Nếu lưu danh sách trong RAM, worker thứ hai sẽ chỉ thấy phần request do chính nó từng xử lý. Script mẫu kiểm chia tải và đọc lại history, không dừng instance giữa chừng. Bằng chứng state tồn tại sau restart ở Part 6 là lần restart worker vẫn trả 429 trong cửa sổ cũ.

## Part 6 · Checklist deliverable

Lệnh chạy trong Ubuntu WSL2, thư mục `06-lab-complete/`: `python check_production_ready.py`. Image được checker đo 58 MB. Redis mất kết nối tạo `/ready=503` trong khi `/health=200`. Lượt SIGTERM giữ request đang chạy trả 200, process thoát 0; `docker stop` thoát 0 sau 0,7 giây.

```text
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 42/42 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

## AI log

| Yêu cầu gửi Codex | Hỗ trợ đã dùng | Kiểm chứng trong phiên làm bài |
|---|---|---|
| Đọc repo và đối chiếu luật K5 | Phân chia checkpoint, chọn WSL2 và xác định đúng thư mục nộp | Kiểm Python POSIX, thử server, Docker Linux và đối chiếu SUBMISSION/CHECKPOINTS. |
| Hoàn thiện Part 6 và deploy Render | Codex viết app, hai bộ kiểm Redis, Docker và cấu hình deploy | Chạy checker gốc 42 phép kiểm, gọi bốn endpoint public, đối chiếu HTTP và secret. |
| Chạy lab, sửa retrieval, benchmark và tổng hợp báo cáo | Codex chạy dịch vụ, thu JSON/CSV, viết phần giải thích và đối chiếu số liệu | So eval trước/sau trên cùng bộ câu hỏi, kiểm chất lượng 23/23, đối chiếu từng bảng với artifact đo của repo. |

Các lần chạy và chỉnh sửa trong bảng do Codex thực hiện trên máy bài lab. Đây là khai báo nguồn hỗ trợ, không phải xác nhận học viên đã tự chạy lại.
