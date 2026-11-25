# Benchmark & Observability Report — Day 14

**Họ tên:** Hà Quang Vinh
**Ngày chạy:** 25/11/2026 (GMT+7)
**Môi trường:** Windows, Ubuntu WSL2, Python 3.11.18, Docker Engine 29.9.3. Mock LLM.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | ≤ 500 ms | Ngưỡng mặc định của load test, giới hạn độ trễ của phần lớn request. |
| Error rate `/ask` | ≤ 2% | Ngưỡng mặc định của load test cho lỗi HTTP. |
| Accuracy trên golden dataset | ≥ 85% | Ngưỡng CI của đề. Lượt xác minh sửa KB đặt ngưỡng 100%. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.06 | 195.8 | 225.9 | 1692.0 | 2.00% | PASS |
| 10 | 33.52 | 204.9 | 395.1 | 1713.7 | 1.67% | PASS |
| 50 | 43.26 | 445.7 | 3913.3 | 5325.0 | 0.67% | FAIL |
| 100 | 37.93 | 1486.7 | 6069.0 | 7017.6 | 0.67% | FAIL |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

Tăng concurrency từ 1 lên 100 đưa throughput từ 4.06 lên 37.93 RPS (9.3 lần). Với lô 300 câu, thời gian hoàn tất còn phụ thuộc request chậm cuối lô. HTTP client, event loop và CPU cũng sử dụng tài nguyên chung.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 312.8 | 574.2 | 685.1 |
| 0.03 (mặc định) | 269.1 | 392.3 | 1713.5 |
| 0.1 | 374.4 | 1705.1 | 1740.2 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

Từ slow rate 0 lên 0.1, avg đổi +61.6 ms, p95 đổi +1130.9 ms và p99 đổi +1055.1 ms. Average bị kéo về nhóm request nhanh, trong khi percentile đo trực tiếp đuôi độ trễ.

---

### Metric và cardinality

Counter `http_requests_total` đếm request. Gauge `agent_in_flight_requests` thay đổi theo lượng request đang xử lý. Histogram `http_request_duration_seconds` gom độ trễ vào bucket và `agent_question_length_chars` ghi phân bố độ dài câu hỏi. Label route dùng mẫu route và gom URL lạ vào `unmatched` để giới hạn số time series, bộ nhớ và chi phí truy vấn.

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Các lượt eval đặt `MOCK_ERROR_RATE=0` để đo riêng chất lượng câu trả lời. Bộ 23 câu giữ nguyên.

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35% | 91.30% | 100.00% |
| Avg tokens / câu | 57.1 | 108.7 | 114.2 |
| Tổng cost (USD) | 0.000404 | 0.000756 | 0.000795 |
| Cost / câu đúng (USD) | 0.00040395 | 0.00003599 | 0.00003456 |
| Quality gate | FAIL | PASS | PASS |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| security-02 | token, hết hạn, chữ ký | JWT có chữ ký và hạn, khác API key cố định. |
| scaling-03 | cpu, memory, custom metrics | HPA scale pod theo CPU, memory hoặc custom metrics. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

Retrieval tăng token trung bình từ 57.1 lên 108.7 và p95 eval từ 194.5 lên 216.5 ms. Cost trên mỗi câu đúng giảm từ 0.00040395 xuống 0.00003599 USD vì v2 đúng 21/23 câu. Sau sửa, v2 đúng 23/23 và có 0 regression.

---

CI khởi động v2 với `MOCK_ERROR_RATE=0`, đợi `/health` trả 200, rồi chạy `python eval/run_eval.py --url http://localhost:8002 --min-accuracy 0.85`. Đặt job làm required check để exit code 1 chặn merge khi accuracy dưới ngưỡng hoặc có regression với baseline được cung cấp.

## 4. Observability stack (production)

### 4.1 Screenshot

- [ ] `grafana-dashboard.png` từ dashboard Golden Signals khi đang có tải. [Grafana](http://localhost:3000/d/day14-agent-overview/day-14-ai-agent-overview)
- [ ] `jaeger-slow-trace.png` mở span `chat mock-llm-small`. [Trace chậm](http://localhost:16686/trace/c7f910db2015921506afd2f2701d10db)
- [ ] `jaeger-error-trace.png` mở event `exception` của span `chat mock-llm-small`. [Trace lỗi](http://localhost:16686/trace/c8a43205f84199ddbae5569369da4071)
- [ ] `prometheus-alert-firing.png` hiển thị ít nhất hai alert cùng **Firing**. [Prometheus Alerts](http://localhost:9090/alerts)

Mẫu Prometheus khi đang gây lỗi có p95 1.888 s và avg 0.545 s. Traffic từng instance trong cửa sổ một phút: 172.24.0.4:8000 (5.05 req/s), 172.24.0.8:8000 (5.29 req/s), 172.24.0.9:8000 (5.25 req/s). Input 919.6 token/s, output 487.8 token/s. Prompt gồm câu hỏi và tài liệu truy xuất. Lượng token đầu ra phụ thuộc các lời đáp mock. Nginx trả HTTP/1.1 404 Not Found cho /metrics. Prometheus scrape nội bộ.

### 4.2 Thí nghiệm "phá hệ thống"

Áp dụng cả hai tham số lỗi và độ trễ trên cùng một lần chạy Locust 30 users, ramp-up 5 users/s. Thời gian tính từ lúc bắt đầu cập nhật Compose tới lần đầu Prometheus API trả trạng thái firing của từng alert.

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | 101.5 s | Error rate |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` | 157.8 s | Latency p95 |
| C | `LLM_MODEL=mock-llm-large` | Bài mở rộng | — | — |
| D | `docker pause` 1 instance | Bài mở rộng | — | — |
| E | `AGENT_VERSION=v1` | Bài mở rộng | — | — |

Prometheus API xác nhận cả `AgentHighErrorRate` và `AgentHighLatencyP95` cùng ở trạng thái `firing`.

Quality gate trên golden dataset phát hiện regression khi chuyển từ v2 sang v1. Có thể định kỳ chạy tập câu hỏi đại diện trên phiên bản đã deploy để quan sát chất lượng theo thời gian.

### 4.3 Debug bằng trace

Trace chậm `c7f910db2015921506afd2f2701d10db` có tổng 1727.5 ms. Span `chat mock-llm-small` chiếm 1698.1 ms (98.3%).

Trace lỗi `c8a43205f84199ddbae5569369da4071` có event exception tại span `chat mock-llm-small`. Hai dòng log có cùng trace_id với trace tương ứng.

```json
{"ts": "2026-11-25T09:03:38.022762+00:00", "level": "INFO", "service": "observable-agent", "instance": "3899cc7bf184", "event": "llm_call", "trace_id": "c7f910db2015921506afd2f2701d10db", "span_id": "d72a7a62245a4050", "request_id": "528b1d2c8c40", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1697.7}
{"ts": "2026-11-25T09:02:53.755777+00:00", "level": "INFO", "service": "observable-agent", "instance": "07f1502ab7a4", "event": "llm_error", "trace_id": "c8a43205f84199ddbae5569369da4071", "span_id": "e4ba0fb74e33a018", "request_id": "97043136269c", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Dùng `docker compose run --rm --no-deps locust` để giữ đúng số replica đã đặt. Kiểm tra số container sau mỗi lượt. Lỗi mock vẫn được ghi trong CSV.

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 64.98 | 200 | 530 | 1700 | 74 |
| 3 | 65.82 | 190 | 230 | 1700 | 58 |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Qua Nginx, p95 chuyển từ 530 ms sang 230 ms, throughput từ 64.98 sang 65.82 RPS. Tải này có thời gian nghỉ của user giả lập và độ trễ của mock LLM. Cần đọc p95 cùng throughput để đánh giá scale và dùng trace hoặc metric CPU để khoanh vùng nút thắt.

---

## 6. Kết luận

1. Percentile giúp thấy nhóm request chậm trong cùng workload.
2. Cost/câu đúng kết hợp chi phí với kết quả người dùng nhận được. Accuracy và lỗi HTTP đo hai khía cạnh riêng.
3. Metrics phát hiện sự cố. Trace và log có cùng trace_id giúp khoanh vùng bước gây lỗi hoặc chậm.

Khi đưa lên production, bổ sung đo latency tại load balancer và bài kiểm tra end-to-end định kỳ. Số đo ở agent chỉ bao phủ request đến được agent.
