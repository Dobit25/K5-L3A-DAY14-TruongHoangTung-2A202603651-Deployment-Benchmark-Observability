# Triển khai agent Day 14

**URL công khai:** https://day14-tung-agent.onrender.com · **API explorer:** https://day14-tung-agent.onrender.com/docs

Dịch vụ Docker `day14-tung-agent` và Key Value `day14-tung-state` chạy gói Free tại Singapore. Code triển khai từ `main`, thư mục `06-lab-complete/`, commit ứng dụng `726e2f5`. Blueprint trong thư mục đó đã được Render CLI xác thực. Hai tài nguyên thực tế được tạo bằng CLI tương ứng với cấu hình Blueprint. Health check của nền tảng dùng `/health`.

| Biến | Cách cấp |
|---|---|
| `PORT` | Render cấp, Uvicorn lắng nghe trên `0.0.0.0`. |
| `ENVIRONMENT` | `production` |
| `AGENT_API_KEY` | Secret ngẫu nhiên đặt ở web service. |
| `REDIS_URL` | Địa chỉ nội bộ của Key Value cùng vùng, không cho phép client Internet kết nối trực tiếp. |
| `RATE_LIMIT_PER_MINUTE` | 10 request / API key |
| `DAILY_BUDGET_USD`, `MONTHLY_BUDGET_USD` | 1 và 10 USD mô phỏng |

## Tự kiểm

Đặt `AGENT_API_KEY` trong terminal bằng giá trị từ kho bí mật của người vận hành. Các lệnh dưới đây chỉ in mã trạng thái.

```bash
BASE=https://day14-tung-agent.onrender.com
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"What is Docker?"}'
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"What is Docker?"}'
```

Lần kiểm ngày 25/11/2026 lúc 11:38:47 UTC cho kết quả **200, 200, 401, 200**. Readiness đã ping được Redis; request có key nhận câu trả lời từ mock LLM.

[Dashboard](screenshots/dashboard.png) · [Dịch vụ đang chạy](screenshots/running.png) · [Bốn phép thử HTTP](screenshots/test.png)
