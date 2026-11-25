# Benchmark & Observability Report — Day 14

**Họ tên:** Trương Hoàng Tùng (2A202603651)  
**Ngày chạy:** 25/11/2026  
**Môi trường:** Windows + WSL2 Ubuntu 24.04 (Python 3.12.3), Docker Desktop Engine 29.7.2

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | `< 500 ms` | Khớp cấu hình ngưỡng SLO mặc định của `load_test.py` (`p95_ms = 500`): phản hồi mock LLM thông thường mất ~180–220 ms, ngưỡng 500 ms giữ trải nghiệm hỏi đáp mượt mà cho 95% request nhưng vẫn đủ chặt để phát hiện nghẽn hàng đợi. |
| Error rate `/ask` | `< 2 %` | Cho phép error budget 2% để dung thứ nhiễu tạm thời từ upstream (`MOCK_ERROR_RATE = 0.01` mặc định), đồng thời cảnh báo sớm khi lỗi vượt ngưỡng bình thường. |
| Accuracy trên golden dataset | `≥ 80 %` (quality gate cuối `100 %`) | Ngưỡng tối thiểu `0.8` (`--min-accuracy 0.8`) chặn các thay đổi làm hỏng tri thức nền; với phiên bản v2 sau khi bổ sung knowledge base, đặt gate `1.0` (`23/23`) kèm `--baseline` để chặn tuyệt đối regression. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

Chạy `python load_test.py --url http://localhost:8002 --requests 300 --concurrency <c>` (300 requests mỗi mức), số liệu lấy trực tiếp từ `reports/load_v2_c1.json` đến `reports/load_v2_c100.json`:

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 4.4 | 191.5 | 219.1 | 1681.1 | 1.67% (5/300) | PASS |
| 10 | 38.32 | 192.6 | 222.3 | 1687.9 | 1.00% (3/300) | PASS |
| 50 | 104.6 | 194.9 | 1665.1 | 1716.0 | 1.00% (3/300) | FAIL |
| 100 | 61.17 | 600.4 | 3389.3 | 3663.3 | 1.33% (4/300) | FAIL |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

Không. RPS tăng gần tuyến tính ở vùng tải thấp (`4.4` → `38.32` RPS khi tăng concurrency từ `1` lên `10`, độ trễ p50/p95 hầu như không đổi), nhưng tăng chậm lại ở concurrency `50` (`104.6` RPS, p95 vọt lên `1665.1 ms` và bắt đầu rớt SLO) rồi **giảm ngược** xuống `61.17` RPS ở concurrency `100` (p50 tăng gấp 3 lần lên `600.4 ms`, p95 lên `3389.3 ms`). Nguyên nhân là server develop chỉ chạy 1 process Uvicorn: khi số kết nối đồng thời vượt ngưỡng xử lý tối ưu của event loop và giới hạn kết nối/socket OS, request phải xếp hàng chờ xử lý và chịu cộng dồn chi phí context-switch cũng như các request dính tail latency, làm thông lượng thực tế giảm mạnh.

### 2.2 Tail latency

Chạy cùng `--requests 300 --concurrency 20` trên `v2` với các mức `MOCK_SLOW_RATE` khác nhau (`reports/load_v2_slow_0.json`, `reports/load_v2_slow_0.03.json`, `reports/load_v2_slow_0.1.json`):

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---:|---:|---:|
| 0 | 187.8 | 215.9 | 227.7 |
| 0.03 (mặc định) | 222.7 | 230.6 | 1694.8 |
| 0.1 | 366.4 | 1696.3 | 1714.9 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

**p99** là chỉ số nhạy nhất: chỉ cần 3% request bị chậm bất thường (`MOCK_SLOW_RATE=0.03`), p99 đã tăng vọt gấp **7.4 lần** (từ `227.7 ms` lên `1694.8 ms`), trong khi `avg` chỉ nhích nhẹ +18.6% (từ `187.8 ms` lên `222.7 ms`). Khi tăng lên 10% (`0.1`), cả p95 cũng nhảy lên `1696.3 ms` và vi phạm SLO (`< 500 ms`), nhưng `avg` (`366.4 ms`) vẫn nằm dưới ngưỡng 500 ms. Vì vậy đặt SLO theo trung bình sẽ che giấu hoàn toàn tail latency: 90–97% request nhanh kéo giá trị trung bình xuống thấp, khiến đội vận hành tưởng hệ thống bình thường trong khi nhóm người dùng ở đuôi phân phối phải chịu trễ hơn 1.6 giây.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Số liệu tổng hợp từ `reports/eval_v1.json`, `reports/eval_v2.json` và `reports/eval_v2_fixed.json` trên `23` câu hỏi của `eval/golden_dataset.jsonl`:

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---:|---:|---:|
| Accuracy | 4.35% (1/23) | 91.30% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.3 | 108.8 | 112.3 |
| Tổng cost (USD) | $0.000406 | $0.000758 | $0.000779 |
| Cost / câu đúng (USD) | $0.00040635 | $0.00003607 | $0.00003387 |
| Quality gate | FAIL (`min=0.8`) | PASS (`min=0.8`) | PASS (`min=1.0`, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry `(["jwt", "json web token"], "API key là bí mật cố định, còn JWT là token có chữ ký và thời điểm hết hạn; dịch vụ xác minh chữ ký và thời hạn trước khi chấp nhận yêu cầu.")` vào `KNOWLEDGE_BASE` trong `06-lab-complete/benchmark-observability/develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`). |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry `(["hpa", "horizontal pod autoscaler"], "Kubernetes HPA điều chỉnh số pod theo CPU, memory hoặc custom metrics, ví dụ độ dài hàng đợi.")` vào `KNOWLEDGE_BASE`. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

Agent `v2` bổ sung bước retrieval (RAG) từ `KNOWLEDGE_BASE`, khiến prompt dài hơn: `avg_tokens` tăng gần gấp đôi (từ `57.3` lên `108.8–112.3` tokens/câu), tổng chi phí 23 câu tăng từ `$0.000406` lên `$0.000779` (~1.9 lần) và p95 latency trong lần chạy eval tăng từ `175.5 ms` lên `214.7 ms`. Tuy nhiên đổi lại accuracy nhảy vọt từ **4.35%** lên **100%**, kéo **cost / câu đúng** giảm **12 lần** (từ `$0.00040635` xuống còn `$0.00003387`). Điều này chứng minh chỉ nhìn tổng chi phí hoặc chi phí mỗi request là sai lầm nếu câu trả lời không đạt chất lượng.

**Quality gate trong CI/CD (`.github/workflows/quality-gate.yml`):**

Trong `eval/run_eval.py`, điều kiện pass là `gate_ok = report["accuracy"] >= args.min_accuracy and not regressions`. Khi đạt, script thoát với `exit code 0`; ngược lại (accuracy dưới ngưỡng hoặc có bất kỳ câu nào ở baseline pass mà bản mới fail) sẽ thoát với `exit code 1`. Workflow CI `.github/workflows/quality-gate.yml` kích hoạt trên `pull_request`, lấy `reports/eval_v2.json` của commit gốc làm `--baseline`, khởi động agent v2 và chạy `python eval/run_eval.py --url http://localhost:8002 --min-accuracy 0.85 --baseline "$RUNNER_TEMP/baseline.json"`. Nếu exit code bằng `1`, CI job báo fail và chặn merge PR vào nhánh chính.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): [jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception`): [jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với ít nhất 2 alert đang **firing**: [prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

Quan sát Golden Signals trên [grafana-dashboard.png](screenshots/grafana-dashboard.png) (trích thời điểm cuối đợt tải):
- **Traffic:** `17.9 req/s` (đỉnh đạt ~60 req/s trong biểu đồ `Requests/s theo status code`).
- **Errors:** `1.04%` (hiển thị cả đường `200` và `503`).
- **Latency p95:** `291.68 ms` (trong đồ thị `Latency /ask — p50 / p95 / p99`, đường p99 nằm quanh ~1.8s phía trên ngưỡng 1s).
- **Saturation:** `1` (request đang xử lý đồng thời), **Instances:** `2`, **LLM cost tích lũy:** `$0.5464` (cost burn rate đạt đỉnh ~$6/giờ khi chạy tải cao).

### 4.2 Thí nghiệm "phá hệ thống"

Các biến lỗi được tiêm vào stack `k5-day14-observability` (`--scale agent=2`) kèm tải Locust (`-u 30 -r 10`) và theo dõi chu kỳ đánh giá `evaluation_interval: 5s` qua `/api/v1/alerts`:

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`for: 1m`) | `86.7s` (pending lúc `26.6s`) | `Error rate` và `Requests/s theo status code` |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`for: 2m`) | `146.9s` (pending lúc `26.6s`) | `Latency p95` và `Latency /ask — p50 / p95 / p99` |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`for: 2m`) | `166.9s` (pending lúc `46.6s`) | `Cost burn rate (USD/giờ)` và `LLM latency p95 theo model` |
| D | `docker pause` 1 instance (`agent-2`) | `AgentInstanceDown` (`for: 30s`) | `50.1s` sau khi pause (pending lúc `20.0s`) | `Instances...` (tụt từ `2` xuống `1`) |
| E | `AGENT_VERSION=v1` | Không có alert nào firing | Không firing | Chỉ đổi label `version="v1"` ở gauge `agent_info` (và token/latency giảm nhẹ) |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Đây là dạng **silent quality degradation** (hệ thống vẫn trả HTTP 200 nhanh, không tăng lỗi hay chi phí, nên các alert hạ tầng đều im lặng). Để phát hiện trong production cần kết hợp:
1. **Quality gate trước khi deploy & eval định kỳ:** chạy `run_eval.py` trên golden dataset trong CI/CD trước mỗi bản release và chạy định kỳ trên môi trường staging/canary để phát hiện tụt accuracy ngay lập tức.
2. **Alert theo metadata phiên bản:** theo dõi metric `agent_info{version=...}` (ví dụ cảnh báo khi version triển khai lệch bản chuẩn hoặc bất thường sau rollout).
3. **Online quality monitoring:** lấy mẫu log sản xuất để chấm bằng LLM-as-judge, theo dõi phân phối độ dài câu trả lời (v1 trả lời ngắn bất thường do thiếu context), và theo dõi tỷ lệ phản hồi tiêu cực / hỏi lại của người dùng (user thumbs-down, re-ask rate).

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất tìm được (khớp [jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)):

- `trace_id`: `43c02b7425c485af32ac2c250a1509d2`
- Tổng thời gian: `1952.0 ms` (Jaeger hiển thị `2.0s`)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-large` (`1932.4 ms`, chiếm **99.0%** tổng thời gian; span `agent.retrieve_context` chỉ mất `17.3 ms` ≈ 0.9%)
- Dòng log tương ứng (grep từ `docker logs k5-day14-observability-agent-1` theo `trace_id`):

```json
{"ts": "2026-11-25T14:53:14.773084+00:00", "level": "INFO", "service": "observable-agent", "instance": "a5812119f393", "event": "llm_call", "trace_id": "43c02b7425c485af32ac2c250a1509d2", "span_id": "fcd41517c21b14d6", "request_id": "17cf9bfc94e7", "model": "mock-llm-large", "agent_version": "v2", "input_tokens": 74, "output_tokens": 37, "cost_usd": 0.000555, "llm_ms": 1932.4}
{"ts": "2026-11-25T14:53:14.773472+00:00", "level": "INFO", "service": "observable-agent", "instance": "a5812119f393", "event": "http_request", "trace_id": "43c02b7425c485af32ac2c250a1509d2", "span_id": "fcd41517c21b14d6", "request_id": "17cf9bfc94e7", "method": "POST", "route": "/ask", "status": 200, "ms": 1952.0}
```

*(Ngoài ra, [jaeger-error-trace.png](screenshots/jaeger-error-trace.png) ghi nhận trace lỗi `ef96440` tổng `113 ms` trả HTTP `503` với event `exception` tại span `chat mock-llm-small`: `Upstream LLM error: 503 Service Unavailable (mock)`.)*

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu `POST /ask` trích trực tiếp từ `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` (tổng hợp cả `/ask` và `/health` lần lượt đạt `64.19` RPS trên `7849` request và `64.45` RPS trên `7882` request):

| Số instance | RPS (`POST /ask`) | p50 (ms) | p95 (ms) | p99 (ms) | Failures (`POST /ask`) |
|---:|---:|---:|---:|---:|---:|
| 1 | 58.20 | 190 | 240 | 1700 | 64 / 7116 (0.90%) |
| 3 | 58.54 | 190 | 230 | 1700 | 75 / 7159 (1.05%) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Scale từ 1 lên 3 instance chỉ cải thiện rất nhẹ p95 (`240 ms` → `230 ms`), còn RPS (~`58.2` vs `58.5` req/s), p50 (`190 ms`) và p99 (`1700 ms`) gần như giữ nguyên. Có hai nguyên nhân chính:
1. **Tải sinh ra chưa chạm trần CPU của 1 instance:** 100 Locust user có thời gian nghỉ `wait_time = between(0.5, 2)` giây nên lượng request đồng thời thực tế chỉ tạo ra ~`58 req/s` cho `/ask`, hoàn toàn nằm trong khả năng xử lý bất đồng bộ (`asyncio`) của 1 container Uvicorn.
2. **Nút thắt nằm ở upstream LLM:** phần lớn độ trễ và toàn bộ lỗi 503 (`~1%`) đến từ lời gọi `mock_llm` (`asyncio.sleep` ~120 ms mặc định và 3% request chậm ~1500 ms gây ra p99 = `1700 ms`). Việc tăng thêm replica cho agent không thể làm giảm độ trễ xử lý của từng lời gọi upstream LLM.

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. **Average đánh lừa khi đo hiệu năng:** chỉ một tỷ lệ nhỏ request chậm (`3%`) đã kéo `p99` lên hơn `1.6s` trong khi `avg` vẫn bình thường; luôn cần đo `p95`/`p99` và tách riêng kiểm thử tải với kiểm thử tail latency.
  2. **Đo chất lượng và chi phí phải đi cùng nhau:** `v2` tốn nhiều token và đắt hơn mỗi request so với `v1`, nhưng nhờ accuracy tăng từ `4.35%` lên `100%` nên **cost / câu đúng** lại rẻ hơn ~12 lần; đồng thời cần quality gate trong CI vì các alert Prometheus không thể phát hiện lỗi giảm chất lượng âm thầm.
  3. **Ba trụ cột Metrics + Traces + Logs phải liên kết được với nhau:** Grafana/Prometheus cho biết *khi nào* hệ thống lỗi hoặc chậm (`Error rate`, `p95`, `Cost burn rate`), Jaeger chỉ ra *span nào* chiếm thời gian (`chat mock-llm-large` 99%), còn `trace_id` trong JSON log giúp đối chiếu nhanh input/model/cost/instance cụ thể.
- **Nếu đưa agent này lên production thật, cần thêm metric / alert nào nữa?**
  - **Metrics & alert cho Redis (dependency):** độ trễ ping/lệnh Redis, tỉ lệ lỗi kết nối Redis và cảnh báo `/ready` trả `503` kéo dài.
  - **Metrics & alert bảo mật & ngân sách:** bộ đếm số request bị chặn `429` (rate limit) và `402` (vượt ngân sách ngày/tháng) để phát hiện tấn công brute-force hoặc khách hàng cạn quota sớm.
  - **Metrics & alert upstream LLM:** số lần timeout/retry, breakdown lỗi theo mã trạng thái upstream (`429` vs `503`), và metric accuracy định kỳ từ canary eval để cảnh báo sớm hiện tượng suy giảm chất lượng.
