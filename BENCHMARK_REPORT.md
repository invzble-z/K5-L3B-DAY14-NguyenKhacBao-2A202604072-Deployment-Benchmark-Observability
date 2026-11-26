# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** NguyenKhacBao (2A202604072)
**Ngày chạy:** 2026-11-26
**Môi trường:** Windows 11 + WSL2 Ubuntu 24.04.5 LTS (`posix`), Python 3.12.3, Docker 29.9.3 / Compose v5.7.0

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | `< 500 ms` | Mock LLM có latency cơ bản + retrieval ~150–250ms; ngưỡng 500ms đảm bảo 95% người dùng nhận phản hồi nhanh (real-time UX) đồng thời khớp ngưỡng `--slo-p95-ms 500` của `load_test.py` |
| Error rate `/ask` | `< 2 %` | Chừa biên an toàn (error budget 2%) cho ~1% lỗi upstream ngẫu nhiên (`MOCK_ERROR_RATE=0.01`), tránh báo động giả từ các lỗi thoáng qua |
| Accuracy trên golden dataset | `≥ 80 %` | Đảm bảo agent trả lời đúng đại đa số câu hỏi chuyên môn trên 23 mẫu chuẩn (CI quality gate siết lên `≥ 85%` hoặc `100%` kèm điều kiện **0 regression** so với baseline) |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

Chạy `python load_test.py --url http://localhost:8002 --requests 300 --concurrency <c> --out reports/load_v2_c<c>.json` (`MOCK_SLOW_RATE=0.03`, `MOCK_ERROR_RATE=0.01`):

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 3.99 | 191.6 | 223.6 | 1694.7 | 1.33% | PASS |
| 10 | 43.84 | 192.8 | 224.5 | 1667.7 | 0.67% | PASS |
| 50 | 105.22 | 212.8 | 278.3 | 1716.1 | 1.33% | PASS |
| 100 | 64.91 | 422.8 | 2807.9 | 3039.1 | 1.33% | FAIL |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

- **Không tăng tuyến tính ở mức tải cao.** Từ `c=1` (`3.99 req/s`) → `c=10` (`43.84 req/s`) → `c=50` (`105.22 req/s`), RPS tăng gần tuyến tính nhờ mô hình bất đồng bộ (`async/await`) cho phép 1 process `uvicorn` xử lý đồng thời nhiều coroutine đang chờ I/O (`asyncio.sleep`).
- Tuy nhiên khi tăng từ `c=50` lên `c=100`, **RPS tụt xuống `64.91 req/s`**, `p50` tăng gấp đôi (`212.8 ms` → `422.8 ms`), còn **`p95` vọt hơn 10 lần (`278.3 ms` → `2807.9 ms`, FAIL SLO)**. Nguyên nhân là hệ thống đã vượt ngưỡng bão hòa (saturation) trên 1 worker đơn lẻ: hàng đợi coroutine/event-loop và chuyển ngữ cảnh tăng mạnh (queueing delay theo định luật Little), chứng minh rằng chỉ chạy 1 instance/worker sẽ không gánh được concurrency lớn.

### 2.2 Tail latency

Chạy `python load_test.py --url http://localhost:8002 --requests 300 --concurrency 20` với 3 cấu hình `MOCK_SLOW_RATE`:

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 199.4 | 233.6 | 248.5 |
| 0.03 (mặc định) | 254.5 | 229.6 | 1708.1 |
| 0.1 | 350.9 | 1695.1 | 1717.6 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

- **Chỉ số nhạy nhất với request chậm là `p99`** (và tiếp đến là **`p95`** khi tỉ lệ chậm vượt 5%). Khi `MOCK_SLOW_RATE` tăng từ `0` lên `0.03` (3% request chậm), `avg` chỉ nhích nhẹ `+55.1 ms` (`199.4 → 254.5 ms`) và `p95` vẫn ổn định (`229.6 ms`), nhưng **`p99` nhảy vọt gần 7 lần lên `1708.1 ms`**. Khi `MOCK_SLOW_RATE=0.1` (10% request chậm), cả `p95` (`1695.1 ms` — FAIL SLO `≤ 500 ms`) lẫn `p99` (`1717.6 ms`) đều bùng nổ, trong khi **`avg` chỉ là `350.9 ms`** (nhìn bề ngoài vẫn tưởng đạt SLO `< 500 ms`!).
- **Vì sao SLO không đặt theo average?** Số trung bình bị 90–97% request nhanh kéo xuống, che giấu hoàn toàn trải nghiệm tệ hại của nhóm người dùng ở đuôi phân phối (tail latency). Đặt SLO theo **percentile (`p95` / `p99`)** phản ánh đúng trải nghiệm thực của đa số và nhóm xấu nhất.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.6 | 108.7 | 113.7 |
| Tổng cost (USD) | $0.000411 | $0.000756 | $0.000790 |
| Cost / câu đúng (USD) | $0.00041055 | $0.00003599 | $0.00003436 |
| Quality gate | FAIL | PASS | PASS |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm tài liệu kích hoạt bởi `["jwt"]` vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`) giải thích API key vs JWT có chữ ký số và thời điểm hết hạn |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm tài liệu kích hoạt bởi `["hpa", "kubernetes", "autoscal"]` vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`) mô tả Kubernetes HPA scale pod theo CPU, memory hoặc custom metrics |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- **v1 → v2:** Bổ sung bước retrieval (RAG) và đưa context vào prompt làm **avg tokens/câu tăng gần gấp đôi** (`57.6 → 108.7`, sau sửa KB là `113.7`), **tổng cost tăng ~1.9×** (`$0.000411 → $0.000790`) và **latency tăng nhẹ ~20 ms** (`p95: 190.7 → 211.9 ms`, bỏ qua 1 outlier tail spike ở lần chạy `eval_v2_fixed` làm `p95=1700 ms` vì cỡ mẫu 23 câu quá nhỏ để kết luận latency).
- Đổi lại, **Accuracy tăng vọt từ `4.3%` (1/23) lên `91.3%` (21/23) và `100.0%` (23/23)** với **0 regression**, giúp **`cost / câu đúng` giảm gần 12 lần** (từ `$0.00041055` xuống `$0.00003436`). Rõ ràng đầu tư thêm bước retrieval cực kỳ hiệu quả về chi phí trên mỗi câu trả lời đúng.

**Quality gate trong CI (`run_eval.py` exit code):**

- Script `eval/run_eval.py` trả về **exit code `0`** khi và chỉ khi `accuracy >= --min-accuracy` **và** `regressions == []` (không câu nào từng đúng ở `--baseline` bị trả lời sai); ngược lại trả **exit code `1`**.
- Đã kiểm chứng thực tế với `v1` đối chiếu `--baseline reports/eval_v2_fixed.json` (`--min-accuracy 0.85`): phát hiện **22 regressions** (`4.3% < 85%`), in `Quality gate ... ❌ FAIL` và trả về **exit code `1`**, giúp job GitHub Actions dưới đây fail và chặn merge Pull Request ngay lập tức:

```yaml
# Quality gate trong CI (.github/workflows/eval.yml)
name: quality-gate
on: [pull_request]
jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - name: Run agent & eval quality gate
        working-directory: 06-lab-complete/benchmark-observability/develop
        run: |
          pip install -r requirements.txt
          AGENT_VERSION=v2 MOCK_ERROR_RATE=0 python app.py &
          sleep 3
          python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85
```

---

## 4. Observability stack (production)

### 4.1 Screenshot & Quan sát Dashboard (Exercise 7.4)

- [x] Dashboard Grafana khi đang có tải (thấy rõ 4 Golden Signals): [grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): [jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception`): [jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với ít nhất 2 alert đang **firing**: [prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

**Trả lời câu hỏi Exercise 7.4 (dưới tải 30 users, 2 instances):**
1. **p95 và avg đang là bao nhiêu? Khoảng cách giữa chúng nói lên điều gì?**
   Tại thời điểm chụp `grafana-dashboard.png` (`Traffic = 7.0 req/s`, `Error rate = 1.81%`, `In-flight = 6`, `Instances up = 2`, `LLM cost 1h = $0.8000`) và snapshot PromQL cùng lúc: **`Latency p95 = 294.79 ms`**, **`avg = 240.0 ms`** (trên biểu đồ chuỗi thời gian, `p99 ≈ 1.8–1.9s`). Khoảng cách giữa `avg`/`p95` (~240–295 ms) với `p99` (~1.85s) phản ánh **tail latency**: ~3% request chậm bất thường kéo p99 lên gần 2 giây dù đa số request và giá trị trung bình trông rất nhanh.
2. **Panel "Requests/s theo instance": Nginx có chia đều traffic cho 2 instance không?**
   Có — Nginx phân phối đều theo round-robin giữa 2 container (`172.20.0.4:8000 ≈ 4.85 req/s`, `172.20.0.8:8000 ≈ 4.58 req/s` trên snapshot PromQL, hai đường trên panel chồng khớp nhau).
3. **Vì sao input tokens/s lớn hơn output tokens/s?**
   Snapshot PromQL ghi nhận **`input ≈ 721.7 tok/s`** so với **`output ≈ 375.5 tok/s`** (~1.9×) vì agent v2 ghép `SYSTEM_PROMPT` + tài liệu context từ retrieval + câu hỏi làm input prompt gửi LLM, còn output chỉ là câu trả lời ngắn gọn.
4. **`curl http://localhost:8080/metrics` trả về gì? Vì sao?**
   Trả về **`HTTP 404 Not Found`** vì `nginx/nginx.conf` chủ động chặn `location = /metrics { return 404; }` nhằm bảo mật, tránh lộ chỉ số nội bộ (lưu lượng, route, chi phí, số instance) ra ngoài; chỉ Prometheus trong mạng nội bộ `obs_net` mới scrape trực tiếp `agent:8000/metrics`.

### 4.2 Thí nghiệm "phá hệ thống"

Chạy tải nền liên tục 30 users bằng Locust và lần lượt áp dụng các thay đổi cấu hình qua `.env` / `docker pause`:

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`for: 1m`) | **72.5s** *(pending lúc 15.1s)* | `Error rate`, `Requests/s theo status code`, `LLM calls theo kết quả` |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`for: 2m`) | **141.9s** *(pending lúc 21.2s)* | `Latency p95`, `Latency /ask — p50 / p95 / p99`, `LLM latency p95 theo model` |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`for: 2m`) | **142.0s** *(pending lúc 21.1s)* | `Cost burn rate (USD/giờ)`, `LLM cost (1h)`, `LLM latency p95 theo model` |
| D | `docker pause` 1 instance (`agent-1`) | `AgentInstanceDown` (`for: 30s`) | **39.3s** *(pending lúc 12.1s)* | `Instances up` (tụt 2 → 1), `Requests/s theo instance` (mất đường `agent-1`) |
| E | `AGENT_VERSION=v1` | Không có alert mới firing | — *(không firing)* | `Retrieval hit ratio (agent v2)` (tụt mất hit), `Tokens/s` (giảm), bảng `Phiên bản đang chạy` (`v1`) |

*(Ở thí nghiệm A + D kết hợp, chụp `screenshots/prometheus-alert-firing.png` cho thấy đồng thời **2 alert firing**: `AgentHighErrorRate` và `AgentInstanceDown`. Ngoài ra, chạy `promtool test rules /p/alert_rules_test.yml` đạt `SUCCESS`.)*

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

- Khi đổi nhầm sang `AGENT_VERSION=v1`, HTTP status vẫn là `200`, error rate và latency hạ tầng vẫn xanh nhưng chất lượng trả lời tụt từ `100%` xuống `4.3%`.
- Để phát hiện cần kết hợp: (1) **CI/CD Quality Gate** (`eval/run_eval.py` trên golden dataset + `--baseline`) chặn ngay từ bước pull request; (2) **Alert trên metric nghiệp vụ/RAG** (ví dụ tỉ lệ `agent_retrieval_total{result="miss"}` vượt ngưỡng hoặc đột ngột mất retrieval hit); (3) **Online evaluation & user feedback** (chấm ngẫu nhiên mẫu traffic thật bằng LLM-as-judge, theo dõi tỉ lệ thumbs-down và giám sát `agent_info{version=...}` sau khi deploy).

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất tìm được trong Jaeger (`service=observable-agent`):

- `trace_id`: `44c7380b6c4e110926381faa08bffb27`
- Tổng thời gian: **`1725.94 ms`** (Jaeger UI hiển thị `1.7s`)
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (**`1697.26 ms`**, **`98.3%`** tổng thời gian — trong khi `agent.retrieve_context` chỉ mất `24.56 ms`, `1.4%`, và `agent.run` là `1722.16 ms`, `99.8%`)
- Dòng log tương ứng (grep theo `trace_id` trong `docker compose -p k5-day14-observability logs agent`):

```json
{"ts": "2026-11-26T07:28:25.225856+00:00", "level": "INFO", "service": "observable-agent", "instance": "d32aabb2c528", "event": "llm_call", "trace_id": "44c7380b6c4e110926381faa08bffb27", "span_id": "f2d01a586356dd87", "request_id": "1af1f68aff3b", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 83, "output_tokens": 44, "cost_usd": 3.9e-05, "llm_ms": 1695.7}
```

*(Trace lỗi đối chiếu trong `screenshots/jaeger-error-trace.png` có `trace_id = 31c7822616205edac7d126342b059f4d`, tổng `106.43 ms`, span `chat mock-llm-small` mất `82.77 ms` kèm event `exception: Upstream LLM error: 503 Service Unavailable (mock)`, khớp dòng log `llm_error` cùng `trace_id`.)*

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Chạy Locust headless `--headless -u 100 -r 10 -t 2m` qua Nginx (dùng `--no-deps` để giữ nguyên đúng 1 vs 3 container agent thật; số liệu trích chính xác từ `benchmark-results/scale_1_stats.csv` và `scale_3_stats.csv` cho endpoint `POST /ask`, kèm số `Aggregated` trong ngoặc):

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 56.41 *(Agg: 61.92)* | 210 | 1000 | 1800 | 54 / 6741 *(0.80%)* |
| 3 | 59.69 *(Agg: 65.77)* | 200 | 250 | 1700 | 67 / 7121 *(0.94%)* |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

- **Scale cải thiện p95 cực kỳ rõ rệt (giảm 4 lần, từ `1000 ms` xuống `250 ms`).** Với 1 instance giới hạn `0.5 CPU`, 100 user đồng thời tạo áp lực hàng đợi và tranh chấp CPU/event-loop (`GET /health` cũng bị đẩy lên `p95 = 410 ms`). Khi scale lên 3 instances qua Nginx load balancer, tải chia đều nên hàng đợi ở tầng agent biến mất (`p95` của `/ask` giảm còn `250 ms` và `/health` giảm còn `23 ms`).
- **Vì sao RPS chỉ tăng nhẹ (`56.4 → 59.7 req/s`) và `p50` (`~200 ms`) / `p99` (`1700–1800 ms`) gần như không đổi?** Thứ nhất, 100 virtual users trong Locust có `wait_time = between(0.5, 2)` nên tổng nhu cầu sinh tải bị giới hạn quanh ~65 req/s. Thứ hai, khi hết hàng đợi ở agent, **nút thắt còn lại nằm ở thời gian chờ upstream LLM** (`MOCK_LATENCY_MS=120 + jitter + retrieval ≈ 200 ms`, và 3% request chậm `+1500 ms → 1700 ms`). Scale ngang tầng agent giúp tăng khả năng chịu tải (capacity) và loại bỏ queueing delay, nhưng không rút ngắn được latency nội tại của mỗi lần gọi LLM.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Không đánh giá hiệu năng bằng average hay bộ eval nhỏ:** `avg` che giấu tail latency (`p95`/`p99` phản ánh đúng nhóm người dùng chờ lâu), còn eval 23 câu chỉ đo chất lượng chứ không đo được latency dưới tải cao.
  2. **Ba trụ cột Metrics – Traces – Logs phải liên kết được với nhau:** Grafana phát hiện biến động Golden Signals → Jaeger chỉ ra đúng span gây chậm/lỗi (`chat mock-llm-small` chiếm 98.3%) → `trace_id` tra ngược chính xác dòng JSON log chi tiết.
  3. **Alert hạ tầng không bắt được lỗi suy giảm chất lượng AI:** Đổi nhầm `AGENT_VERSION=v1` làm accuracy tụt từ 100% còn 4.3% nhưng không alert hạ tầng nào kêu; bắt buộc phải có eval quality gate tự động trong CI/CD và theo dõi metric RAG/LLM.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?
  - Theo dõi ở tầng **Edge/Load Balancer (Nginx)** (alert `5xx`/`504 Gateway Timeout` rate, vì lỗi 504 tại proxy không xuất hiện trên metric của agent).
  - Alert theo **chỉ số chất lượng RAG & bảo vệ ví**: cảnh báo khi tỉ lệ `agent_retrieval_total{result="miss"}` tăng vọt đột biến, cảnh báo tỉ lệ `429` (rate limit) / `402` (cost guard) bất thường, và nối Alertmanager tới Slack/PagerDuty.
  - Theo dõi **Redis health & latency** (trạng thái kết nối `/ready`, độ trễ lệnh `ZSET`/`INCRBYFLOAT`) và đặt ngưỡng sampling trace (vd 10% request bình thường + 100% trace lỗi/chậm) để tiết kiệm chi phí lưu trữ Jaeger khi traffic lớn.
