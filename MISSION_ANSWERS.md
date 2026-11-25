# Day 14 Lab — Mission Answers

> **Môn học:** AICB-P1 · VinUniversity 2026  
> **Lớp:** K5-L3B

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns phát hiện trong `develop/app.py`

Đọc `01-localhost-vs-production/develop/app.py` và đối chiếu với `01-localhost-vs-production/production/app.py` + `production/config.py`, phát hiện **9 anti-patterns**:

1. **Hardcode secrets ngay trong source code** (`develop/app.py`, dòng 17–18): khai báo trực tiếp `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`. Nếu push lên Git public, secret bị lộ ngay lập tức và còn lưu mãi trong lịch sử commit.
   - *Đã sửa ở `production/config.py`, dòng 27–32 & 37–46:* đọc toàn bộ secret qua `os.getenv(...)`, kết hợp `.env.example` và `validate()` fail-fast khi chạy `ENVIRONMENT=production` mà thiếu `AGENT_API_KEY`.
2. **Bật cứng `DEBUG = True` và hardcode tham số cấu hình** (`develop/app.py`, dòng 21–22): `DEBUG = True`, `MAX_TOKENS = 500`, không tách cấu hình theo môi trường `development` / `staging` / `production`.
   - *Đã sửa ở `production/config.py`, dòng 19, 24, 29:* đọc `DEBUG` (mặc định `false`), `ENVIRONMENT`, `MAX_TOKENS` từ biến môi trường.
3. **Dùng `print()` thay cho structured logging** (`develop/app.py`, dòng 33, 38, 48): không có timestamp, log level hay định dạng JSON nên log aggregator (Loki, Datadog, ELK) khó parse, lọc và cảnh báo.
   - *Đã sửa ở `production/app.py`, dòng 28–32, 49–55, 111–122:* dùng module `logging` định dạng JSON có trường `time`, `level`, `msg` và payload sự kiện có cấu trúc.
4. **In trực tiếp secret ra log/stdout** (`develop/app.py`, dòng 34): `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` làm rò rỉ API key ngay trong terminal và hệ thống thu thập log.
   - *Đã sửa ở `production/app.py`, dòng 110–115:* chỉ log metadata (`event`, `question_length`, `client_ip`), tuyệt đối không log API key hay nội dung nhạy cảm.
5. **Không có Health Check và Readiness endpoint** (`develop/app.py`, dòng 42–43): thiếu `GET /health` và `GET /ready`, nên cloud platform hoặc load balancer không phát hiện được app treo để tự restart hay ngừng đẩy traffic.
   - *Đã sửa ở `production/app.py`, dòng 135–161:* bổ sung `GET /health` (liveness probe) và `GET /ready` (readiness probe trả HTTP 503 khi `is_ready = False`), kèm `GET /metrics` (dòng 164–173).
6. **Bind cứng `host="localhost"`** (`develop/app.py`, dòng 51): chỉ nhận kết nối loopback nội bộ, khi đóng gói vào Docker container hoặc triển khai lên cloud sẽ không thể truy cập từ bên ngoài.
   - *Đã sửa ở `production/config.py`, dòng 17 & `production/app.py`, dòng 196:* bind `host=settings.host` (mặc định `0.0.0.0`).
7. **Hardcode `port=8000`** (`develop/app.py`, dòng 52): không lắng nghe theo biến môi trường `PORT` do nền tảng cloud (Render/Railway/Cloud Run) cấp động.
   - *Đã sửa ở `production/config.py`, dòng 18 & `production/app.py`, dòng 197:* `port=int(os.getenv("PORT", "8000"))`.
8. **Bật cứng `reload=True` trong `uvicorn.run`** (`develop/app.py`, dòng 53): sinh thêm tiến trình file watcher (`WatchFiles`) tốn CPU/RAM và gây restart bất ngờ trên production.
   - *Đã sửa ở `production/app.py`, dòng 198:* `reload=settings.debug` (chỉ bật khi `DEBUG=true`).
9. **Không xử lý Graceful Shutdown (`lifespan` / `SIGTERM`)** (`develop/app.py` không có vòng đời shutdown): khi container dừng hoặc deploy bản mới, tiến trình bị ngắt đột ngột làm đứt request đang xử lý và không dọn dẹp kết nối.
   - *Đã sửa ở `production/app.py`, dòng 39–68 & 180–189:* quản lý startup/shutdown bằng `@asynccontextmanager async def lifespan(...)` (hạ cờ `is_ready = False`, chờ hoàn thành request đang chạy) và đăng ký `signal.SIGTERM`.
   *(Ngoài ra, `develop/app.py` dòng 30–31 nhận `question` qua query string không kiểm tra rỗng và thiếu CORS; `production/app.py` dòng 77–82 bổ sung `CORSMiddleware` giới hạn `ALLOWED_ORIGINS` và dòng 102–108 nhận JSON body có kiểm tra trả 422.)*

### Exercise 1.2: Kết quả chạy bản `develop`

Chạy trong WSL2 Ubuntu-24.04 (`01-localhost-vs-production/develop/app.py`), gọi đúng quy ước K5 (truyền `question` qua query param):

```bash
curl -sS -i http://localhost:8000/
```
```text
HTTP/1.1 200 OK
content-type: application/json

{"message":"Hello! Agent is running on my machine :)"}
```

```bash
curl -sS -i -X POST "http://localhost:8000/ask?question=Hello"
```
```text
HTTP/1.1 200 OK
content-type: application/json

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

Log thực tế từ stdout của `develop/app.py` cho thấy rõ 2 vấn đề: tiến trình reloader chạy trên `localhost:8000` và dòng `[DEBUG] Using key:` làm lộ thẳng API key:
```text
INFO:     Uvicorn running on http://localhost:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [3561] using WatchFiles
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.
```

### Exercise 1.3: Chạy bản `production` & bảng so sánh `develop` vs `production`

Chạy `01-localhost-vs-production/production/app.py` (tạo `.env` từ `.env.example`, không commit `.env`):
- `GET /health` → `200 OK`: `{"status":"ok","uptime_seconds":0.2,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T19:17:37.163596+00:00"}`
- `GET /ready` → `200 OK`: `{"ready":true}`
- `POST /ask` (`{"question": "Hello"}`) → `200 OK`: `{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","model":"gpt-4o-mini"}`
- Khi dừng server: `INFO: Shutting down` → `Waiting for application shutdown.` → `Application shutdown complete.` → `Finished server process`.

| Feature | Develop (`develop/app.py`) | Production (`production/app.py` + `config.py`) | Tại sao quan trọng? |
|---|---|---|---|
| **Config & Secrets** | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG=True`, `MAX_TOKENS=500` trong code (dòng 17–22) | Tập trung trong `Settings` đọc từ biến môi trường (`os.getenv`), fail-fast qua `validate()` khi chạy production (dòng 14–50 `config.py`), dùng `.env.example` | Đạt 12-Factor: đổi cấu hình giữa dev/staging/prod không cần sửa code; không commit secret lên Git tránh bị khai thác và phát sinh chi phí trái phép |
| **Network Binding & Port** | `host="localhost"`, `port=8000`, `reload=True` cố định (dòng 51–53) | `host=0.0.0.0` và `port` đọc từ `PORT` env var, `reload=settings.debug` (mặc định `false`) (dòng 196–198) | Container/cloud bắt buộc bind `0.0.0.0` mới nhận traffic bên ngoài và phải nghe đúng cổng `PORT` do nền tảng cấp; tắt `reload` để ổn định và tiết kiệm tài nguyên |
| **Health & Readiness Check** | Không có endpoint `/health` hay `/ready` | Có `GET /health` (liveness), `GET /ready` (readiness trả 503 khi chưa sẵn sàng), `GET /metrics` (dòng 135–173) | Orchestrator/cloud biết khi nào cần tự restart container bị treo (`/health`) và load balancer chỉ đẩy traffic khi app thực sự sẵn sàng (`/ready`) |
| **Logging** | `print()` tự do và in thẳng `OPENAI_API_KEY` ra stdout (dòng 33–38) | Structured JSON logging qua `logging`, không log secret, chỉ ghi metadata request/response (dòng 28–32, 110–122) | Dễ thu thập, tìm kiếm, phân tích sự cố trên hệ thống log tập trung (Loki/Datadog) và đảm bảo an toàn thông tin bí mật |
| **Graceful Shutdown** | Không có `lifespan` hay xử lý `SIGTERM`, tắt đột ngột | Có `lifespan` quản lý startup/shutdown (`is_ready = False`, hoàn thành request đang chạy) và đăng ký `SIGTERM` (dòng 39–68, 180–189) | Cho phép zero-downtime rolling deploy: không cắt ngang request của người dùng và đóng kết nối DB/Redis sạch sẽ trước khi thoát |
| **API Input & CORS** | Nhận query param `?question=`, không validate, không CORS | Nhận JSON body, trả HTTP 422 khi thiếu `question`, cấu hình `CORSMiddleware` theo `ALLOWED_ORIGINS` (dòng 77–82, 102–108) | Chuẩn hoá hợp đồng API, chặn request không hợp lệ từ sớm và bảo vệ dịch vụ khỏi truy cập cross-origin trái phép |

---

## Part 2: Docker Containerization

### Exercise 2.1: Trả lời 4 câu hỏi về `02-docker/develop/Dockerfile`

1. **Base image là gì?**
   - `FROM python:3.11` (bản đầy đủ trên Debian kèm compiler, thư viện hệ thống và toàn bộ bộ phân phối Python, kích thước gốc lớn ~1+ GB).
2. **Working directory là gì?**
   - `WORKDIR /app` — thư mục làm việc mặc định bên trong container; mọi lệnh `COPY`, `RUN`, `CMD` phía sau đều chạy tương đối từ `/app`.
3. **Tại sao phải `COPY requirements.txt` trước khi `COPY` source code (`app.py`)?**
   - Để tận dụng **Docker build layer cache**: Docker build từng lệnh thành một layer bất biến. Khi chỉ sửa code `app.py` mà không đổi `requirements.txt`, Docker tái sử dụng lại layer `RUN pip install -r requirements.txt` đã cache (không tải/cài lại thư viện mỗi lần build), rút ngắn thời gian build từ vài phút xuống vài giây.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?**
   - **`ENTRYPOINT`** cố định chương trình thực thi chính của container (khó bị ghi đè trừ khi truyền cờ `--entrypoint`), biến container thành một executable chuyên dụng.
   - **`CMD`** cung cấp lệnh hoặc tham số mặc định cho container và **dễ dàng bị ghi đè** khi người dùng truyền thêm lệnh ở cuối `docker run <image> <command>`. Khi dùng chung cả hai, `CMD` đóng vai trò làm tham số mặc định truyền vào `ENTRYPOINT`.

### Exercise 2.2: Build và chạy `my-agent:develop`

Build từ gốc repo (`docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .`), chạy container trên cổng 8000 và gọi thử (bản develop nhận `question` qua query param):

```bash
curl -sS -i http://localhost:8000/health
```
```text
HTTP/1.1 200 OK
content-type: application/json

{"status":"ok","uptime_seconds":0.4,"container":true}
```

```bash
curl -sS -i -X POST "http://localhost:8000/ask?question=What+is+Docker"
```
```text
HTTP/1.1 200 OK
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

### Exercise 2.3: Multi-stage build & so sánh kích thước image đo thực tế

**Phân tích `02-docker/production/Dockerfile`:**
- **Stage 1 (`builder` — `FROM python:3.11-slim AS builder`):** Cài công cụ biên dịch (`gcc`, `libpq-dev`) và cài toàn bộ Python packages vào `/root/.local` (`pip install --no-cache-dir --user -r requirements.txt`). Image stage này chỉ dùng để build, **không** đưa lên production.
- **Stage 2 (`runtime` — `FROM python:3.11-slim AS runtime`):** Tạo user non-root `appuser`, chỉ `COPY --from=builder` các package đã cài sang `/home/appuser/.local`, copy `main.py` và `utils/mock_llm.py`, bổ sung `HEALTHCHECK` và chạy `uvicorn` với 2 worker dưới quyền `appuser`.
- **Tại sao image nhỏ hơn và an toàn hơn?** Stage runtime dùng base `python:3.11-slim` thay vì full `python:3.11`, đồng thời bỏ lại toàn bộ build toolchain (`gcc`, `libpq-dev`, headers, cache apt/pip) ở stage 1 nên giảm mạnh dung lượng và thu nhỏ bề mặt tấn công (attack surface).

**Kết quả đo thực tế bằng `docker images` và `docker image inspect`:**

```text
REPOSITORY   TAG        IMAGE ID       SIZE
my-agent     develop    79733c3ded12   1.67GB
my-agent     advanced   863c02f55d4f   240MB
```

- **Develop (`my-agent:develop`):** `1,667.8 MB` (`1,590.5 MiB`)
- **Production (`my-agent:advanced`):** `239.8 MB` (`228.7 MiB`)
- **Chênh lệch:** Giảm **`1,428.0 MB`** (giảm **`85.6%`** dung lượng image)

### Exercise 2.4: Docker Compose stack & sơ đồ kiến trúc

Chạy trong `02-docker/production/` (tạo `.env.local` rỗng và đặt tên project riêng `-p k5-day14-docker`):
- Các service khởi chạy: **`nginx`** (`nginx:alpine`, expose cổng `80`/`443` ra host), **`agent`** (build từ stage `runtime`, cổng nội bộ `8000`, `depends_on` điều kiện healthy của `redis` và `qdrant`), **`redis`** (`redis:7-alpine`, cổng nội bộ `6379`, volume `redis_data`), **`qdrant`** (`qdrant/qdrant:v1.9.0`, cổng nội bộ `6333`, volume `qdrant_data`).
- Tất cả kết nối qua bridge network cô lập `internal` (chỉ có Nginx mở cổng ra ngoài, giải quyết tên miền nội bộ qua Docker DNS: `agent:8000`, `redis:6379`, `qdrant:6333`).

**Sơ đồ kiến trúc:**
```text
                        ┌──────────────────────────────────────────────────────┐
                        │            Docker Network: internal (bridge)         │
                        │                                                      │
  ┌──────────┐  :80/:443│  ┌─────────────┐  HTTP :8000  ┌──────────────────┐   │
  │  Client  │──────────┼─▶│    Nginx    │─────────────▶│   Agent (FastAPI)│   │
  └──────────┘          │  │ (Reverse    │  rate-limit  │   uvicorn x2     │   │
                        │  │  Proxy/LB)  │  + headers   └────────┬─────────┘   │
                        │  └─────────────┘                       │             │
                        │                          ┌─────────────┴─────────┐   │
                        │                          ▼ :6379                 ▼ :6333
                        │                   ┌─────────────┐        ┌──────────────┐
                        │                   │    Redis    │        │    Qdrant    │
                        │                   │(redis_data) │        │(qdrant_data) │
                        │                   └─────────────┘        └──────────────┘
                        └──────────────────────────────────────────────────────┘
```

**Kết quả test thực tế qua Nginx (`http://localhost`):**
```bash
curl -sS -i http://localhost/health
```
```text
HTTP/1.1 200 OK
Server: nginx
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Content-Type: application/json

{"status":"ok","uptime_seconds":1.2,"version":"2.0.0","timestamp":"2026-11-25T19:32:08.840881"}
```

```bash
curl -sS -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question": "Explain microservices"}'
```
```text
HTTP/1.1 200 OK
Server: nginx
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Content-Type: application/json

{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```
*(Đã dọn stack bằng `docker compose -p k5-day14-docker down -v` sau khi test.)*

---

## Part 3: Cloud Deployment (Agent Part 6)

### Exercise 3.1 / 3.2: Deploy lên Render & kiểm thử URL public

*(Đang chờ thực hiện ở CP6)*

### So sánh `railway.toml` vs `render.yaml`

| Tiêu chí | `railway.toml` (Railway) | `render.yaml` (Render Blueprint) | Vì sao có sự khác biệt này? |
|---|---|---|---|
| **Định dạng & phạm vi** | TOML, cấu hình **một service duy nhất** (mục `[build]` và `[deploy]`) | YAML, khai báo **Infrastructure as Code (IaC) đa service** dưới mảng `services:` (Web Service, Redis/Key Value, Worker, Cron, Disk…) | Railway hướng tới triển khai nhanh từng service riêng và nối add-on qua UI/CLI; Render Blueprint quản lý toàn bộ stack hạ tầng trong 1 file để sync tự động từ Git |
| **Build & Runtime** | `builder = "DOCKERFILE"` (hoặc `"NIXPACKS"` / `"RAILPACK"`), chỉ định `dockerfilePath` | `type: web`, `runtime: docker` (hoặc `python`), hỗ trợ chọn `region` (vd `singapore`) và `plan` (`free`, `starter`…) ngay trong file | Render cho phép phiên bản hoá cả loại tài nguyên, vùng địa lý (region) và gói cước ngay trong repo |
| **Health check & Restart** | `healthcheckPath = "/health"`, `healthcheckTimeout = 30`, `restartPolicyType = "ON_FAILURE"`, `restartPolicyMaxRetries = 3` | `healthCheckPath: /health`, `autoDeploy: true` (Render tự quản lý restart khi health check fail) | Cả hai đều cần `/health` để kiểm tra container sẵn sàng khi rolling deploy, nhưng Railway cho cấu hình trực tiếp chính sách retry |
| **Biến môi trường & Secrets** | **Không** khai báo env vars trong `railway.toml`; đặt qua CLI (`railway variables set`) hoặc Dashboard | Khai báo danh sách `envVars:` ngay trong YAML; biến nhạy cảm dùng `generateValue: true` (tự sinh random) hoặc `sync: false` (nhập thủ công trên Dashboard) | Cả hai đều tuân thủ nguyên tắc không commit secret thật vào Git, nhưng Render chuẩn hoá luôn lược đồ các biến bắt buộc để người deploy không bị quên biến |

### Exercise 3.3: Pipeline CI/CD GCP Cloud Run (`cloudbuild.yaml` & `service.yaml`)

Đọc `03-cloud-deployment/production-cloud-run/cloudbuild.yaml` và `service.yaml`, pipeline CI/CD tự động khi push lên nhánh `main` đi qua **4 bước tuần tự** (`waitFor`):
1. **Test (`test`):** Dùng container `python:3.11-slim` cài `requirements.txt` + `pytest` và chạy `pytest tests/ -v`; nếu test fail sẽ chặn toàn bộ pipeline không cho build/deploy.
2. **Build (`build`):** Dùng `gcr.io/cloud-builders/docker` build image từ `Dockerfile`, gắn 2 tag (`$COMMIT_SHA` để truy vết/rollback và `latest`) và dùng `--cache-from` để tăng tốc nhờ layer cache.
3. **Push (`push`):** Đẩy toàn bộ các tag của image lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **Deploy (`deploy`):** Chạy `gcloud run deploy` triển khai image gắn `$COMMIT_SHA` lên Cloud Run (`asia-southeast1`), cấu hình tài nguyên (`512Mi` RAM, `1` CPU), autoscaling (`min-instances=1` tránh cold start, `max-instances=10`), timeout `60s`, và nạp secret an toàn từ **Secret Manager** (`--set-secrets`). File `service.yaml` (chuẩn Knative `serving.knative.dev/v1`) mô tả cấu hình tương đương dưới dạng IaC kèm `containerConcurrency: 80`, `livenessProbe` (`/health`), `startupProbe` (`/ready`) và `secretKeyRef`.

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop`)

**Phân tích `04-api-gateway/develop/app.py`:**
- **API key được kiểm tra ở đâu?** Trong dependency `verify_api_key()` (dòng 39–54), đọc header `X-API-Key` qua `APIKeyHeader(name="X-API-Key", auto_error=False)` và inject vào endpoint `POST /ask` bằng `Depends(verify_api_key)` (dòng 70). Các endpoint `/`, `/health` để public để platform kiểm tra sức khoẻ.
- **Điều gì xảy ra nếu thiếu hoặc sai key?** Thiếu header `X-API-Key` → trả `HTTP 401 Unauthorized`; gửi sai key → trả `HTTP 403 Forbidden` (lưu ý: ở Part 6, hợp đồng chuẩn yêu cầu cả thiếu lẫn sai key đều trả `401` để tránh lộ thông tin).
- **Làm sao rotate key không downtime?** Không hardcode key; hỗ trợ một danh sách/tập nhiều key hợp lệ cùng lúc (ví dụ đọc `AGENT_API_KEYS` phân tách bằng dấu phẩy hoặc lưu trong Secret Manager/Redis): (1) thêm key mới song song với key cũ, (2) cập nhật key mới phía client, (3) xác nhận traffic key cũ về 0 rồi mới thu hồi key cũ.

**Kết quả test thực tế (`AGENT_API_KEY=secret-key-123 python app.py`):**

1. **Không có API key → `401 Unauthorized`:**
```text
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```
2. **Sai API key (`X-API-Key: wrong-key`) → `403 Forbidden`:**
```text
HTTP/1.1 403 Forbidden
content-type: application/json

{"detail":"Invalid API key."}
```
3. **Đúng API key (`X-API-Key: secret-key-123`) → `200 OK`:**
```text
HTTP/1.1 200 OK
content-type: application/json

{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production`)

**Phân tích `auth.py` và `rate_limiter.py`:**
- **JWT flow (`auth.py`):** Client gửi `username`/`password` tới `POST /auth/token` → server xác thực và ký JWT bằng `HS256` chứa `sub` (username), `role`, `iat`, `exp` (hết hạn sau 60 phút). Các request sau gửi `Authorization: Bearer <token>`, server verify chữ ký stateless bằng `SECRET_KEY` mà không cần truy vấn DB mỗi request.
- **Thuật toán Rate Limiting (`rate_limiter.py`):** **Sliding Window Log/Counter** lưu deque các timestamp request trong cửa sổ `window_seconds = 60` giây cho từng `user_id`; mỗi lần gọi sẽ loại bỏ timestamp cũ hơn `now - 60`, kiểm tra `len(window) >= max_requests` → trả `HTTP 429` kèm `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`. *(Bản mẫu lưu in-memory `dict[str, deque]`; trong production đa instance phải chuyển sang Redis Sorted Set như ở Part 6.)*
- **Giới hạn requests/minute:** `rate_limiter_user` = **10 req/phút** (`student`, role `user`); `rate_limiter_admin` = **100 req/phút** (`teacher`, role `admin`).
- **Làm sao bypass hoặc nâng limit cho admin?** Kiểm tra `user["role"]` trích xuất từ payload JWT (dòng 141 `production/app.py`): nếu `role == "admin"` thì định tuyến sang `rate_limiter_admin` (100 req/phút) hoặc trả qua luôn không kiểm tra limiter nếu muốn bypass hoàn toàn.

**Kết quả test thực tế (`curl -i`, đã che JWT token):**

1. **Gọi `/ask` không có Bearer token → `401 Unauthorized`:**
```text
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin
content-type: application/json

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
```

2. **Lấy token tại `POST /auth/token` (`student` / `demo123`):**
```text
Token nhận được (đã che): eyJhbGciOiJIUzI1Ni...[REDACTED]
```

3. **Gọi `/ask` lần 1 với `Authorization: Bearer eyJhbGciOiJIUzI1Ni...[REDACTED]` → `200 OK`:**
```text
HTTP/1.1 200 OK
x-content-type-options: nosniff
x-frame-options: DENY
content-type: application/json

{"question":"Explain JWT","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}
```

4. **Vòng lặp gọi liên tiếp (Req #2 → #11) để kiểm thử Rate Limit (`10 req/phút`):**
```text
Req #2  -> HTTP/1.1 200 OK
Req #3  -> HTTP/1.1 200 OK
Req #4  -> HTTP/1.1 200 OK
Req #5  -> HTTP/1.1 200 OK
Req #6  -> HTTP/1.1 200 OK
Req #7  -> HTTP/1.1 200 OK
Req #8  -> HTTP/1.1 200 OK
Req #9  -> HTTP/1.1 200 OK
Req #10 -> HTTP/1.1 200 OK
Req #11 -> HTTP/1.1 429 Too Many Requests
```

**Output chi tiết `HTTP 429` ở Req #11:**
```text
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795635280
retry-after: 59
x-content-type-options: nosniff
x-frame-options: DENY
content-type: application/json

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

5. **Kiểm tra usage (`GET /me/usage`) sau 10 request thành công:**
```text
HTTP/1.1 200 OK
{"user_id":"student","date":"2026-11-26","requests":10,"input_tokens":40,"output_tokens":320,"cost_usd":0.000198,"budget_usd":1.0,"budget_remaining_usd":0.999802,"budget_used_pct":0.0}
```

### Exercise 4.4: Cost Guard (`cost_guard.py`)

- **Cơ chế hoạt động:** `cost_guard.py` tính chi phí từng request từ số `input_tokens` (đơn giá `0.00015 USD / 1K tokens`) và `output_tokens` (`0.0006 USD / 1K tokens`). Trước khi gọi LLM sẽ gọi `check_budget(user_id)`: vượt ngân sách cá nhân (`daily_budget_usd = $1/ngày`) trả **`HTTP 402 Payment Required`**, vượt ngân sách toàn hệ thống (`global_daily_budget_usd = $10/ngày`) trả **`HTTP 503`**, chạm ngưỡng 80% thì ghi log cảnh báo (`WARNING`). Sau khi gọi LLM xong sẽ gọi `record_usage()` cộng dồn token và chi phí.
- **Triển khai chuẩn Production với Redis (stateless):** Thay dict `_records` trong RAM bằng key theo kỳ thời gian trong Redis (vd `cost:daily:YYYY-MM-DD` hoặc `budget:{user_id}:{YYYY-MM}`), dùng lệnh nguyên tử `INCRBYFLOAT` để cộng dồn chi phí từ nhiều worker/instance và đặt `EXPIRE` (2 ngày cho daily / 32–35 ngày cho monthly) để tự động reset khi sang kỳ mới.
- **Vì sao cần CẢ Rate Limiting VÀ Cost Guard?**
  - **Rate Limiting** bảo vệ **tốc độ/lưu lượng (RPS)** chống spam, DoS và quá tải server/upstream.
  - **Cost Guard** bảo vệ **ngân sách (tiền)** — vì với LLM, chỉ cần vài request chậm rãi hợp lệ (vẫn dưới ngưỡng 10 req/phút) nhưng prompt rất dài hoặc dùng model đắt (`gpt-4o`, `mock-llm-large`) vẫn có thể đốt sạch hóa đơn API. Kết hợp cả hai lớp mới ngăn được cả quá tải lẫn vượt ngân sách.

---

## Part 5: Scaling & Reliability

### Exercise 5.1 & 5.2: Health / Readiness checks & Graceful shutdown (`05-scaling-reliability/develop`)

**Phân biệt Liveness (`/health`) vs Readiness (`/ready`):**
- **Liveness (`GET /health`):** Trả lời *"Process/container còn sống không?"*. Nếu fail (non-200 hoặc timeout), orchestrator (Docker/Kubernetes/Render) sẽ **khởi động lại (restart)** container. Vì vậy `/health` **không nên phụ thuộc vào Redis/DB bên ngoài** — nếu Redis chết tạm thời mà `/health` trả 503 thì toàn bộ container bị restart loop vô ích.
- **Readiness (`GET /ready`):** Trả lời *"Instance có sẵn sàng nhận traffic ngay lúc này không?"*. Khi đang startup (chưa nạp xong model), đang shutdown (`_is_ready = False`), hoặc mất kết nối Redis/DB thì trả **`HTTP 503`** để load balancer tạm **ngừng đẩy traffic mới** vào instance đó (nhưng không restart).

**Kết quả test thực tế trên `05-scaling-reliability/develop/app.py` (WSL2):**

```bash
curl -sS -i http://localhost:8000/health
```
```text
HTTP/1.1 200 OK
content-type: application/json

{"status":"ok","uptime_seconds":0.8,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T19:35:07.706132+00:00","checks":{"memory":{"status":"ok","used_percent":13.0}}}
```

```bash
curl -sS -i http://localhost:8000/ready
```
```text
HTTP/1.1 200 OK
content-type: application/json

{"ready":true,"in_flight_requests":1}
```

**Test Graceful Shutdown (`POST /ask?question=Long+task` song song `kill -TERM <PID>`):**
- Request đang chạy vẫn hoàn thành và trả **`HTTP/1.1 200 OK`** (`{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}`) thay vì bị ngắt kết nối.
- Log xác nhận trình tự shutdown an toàn (`uvicorn` ngừng nhận kết nối mới → hoàn thành request in-flight → chạy `lifespan` teardown → thoát sạch):
```text
INFO:     Shutting down
INFO:     127.0.0.1:59660 - "POST /ask?question=Long+task HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
2026-11-26 02:35:10,864 INFO 🔄 Graceful shutdown initiated...
2026-11-26 02:35:10,864 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [4470]
```

### Exercise 5.3: Stateless design với Redis

- **Vì sao state lưu trong RAM bị hỏng khi chạy nhiều instance?** Khi scale lên 3 instance sau Nginx load balancer, mỗi container có vùng nhớ RAM riêng biệt. Nếu `conversation_history` hay bộ đếm rate limit lưu trong `dict` của Python, request 1 của user A vào Instance 1 sẽ ghi state ở RAM Instance 1, nhưng request 2 lại bị Nginx chuyển sang Instance 2 → **không tìm thấy lịch sử trò chuyện** (hoặc user vượt quá rate limit gấp 3 lần). Ngoài ra, khi container restart hoặc deploy bản mới, toàn bộ state trong RAM bị mất sạch.
- **Giải pháp stateless (`05-scaling-reliability/production/app.py`):** Đưa toàn bộ session/history ra lưu chung tại **Redis** (`save_session` dùng `SETEX session:{session_id} 3600 <json>`, `load_session` dùng `GET`). Mọi instance đều đọc/ghi cùng một kho dữ liệu dùng chung, nên bất kỳ instance nào cũng xử lý được request tiếp theo và có thể thêm/bớt/restart instance mà không mất dữ liệu người dùng.

### Exercise 5.4 & 5.5: Load balancing (3 instances) & kết quả `test_stateless.py`

Chạy trong `05-scaling-reliability/production/` theo quy ước K5 (tạo `.env.local`, cổng **8080**, endpoint **`POST /chat`**, đặt tên project `-p k5-day14-scaling`):

```bash
docker compose -p k5-day14-scaling up -d --build --scale agent=3
python test_stateless.py
docker compose -p k5-day14-scaling down -v
```

**Kết quả thực tế từ `python test_stateless.py`:**
```text
============================================================
Stateless Scaling Demo
============================================================

Session ID: ca2aa53c-2c3d-41d6-8775-daf4fb38a8ea

Request 1: [instance-273e24]
  Q: What is Docker?
  A: Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!...

Request 2: [instance-9c0620]
  Q: Why do we need containers?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

Request 3: [instance-273e24]
  Q: What is Kubernetes?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

Request 4: [instance-ab2ff3]
  Q: How does load balancing work?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 5: [instance-9c0620]
  Q: What is Redis used for?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-ab2ff3', 'instance-9c0620', 'instance-273e24'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

**Giải thích kết quả:**
- Nginx phân tải round-robin (dùng Docker DNS `resolver 127.0.0.11`, `proxy_next_upstream error timeout http_503`) làm 5 request liên tiếp của **cùng một `session_id`** đi qua đủ **cả 3 instance khác nhau** (`instance-273e24`, `instance-9c0620`, `instance-ab2ff3`).
- Khi gọi `GET /chat/ca2aa53c-2c3d-41d6-8775-daf4fb38a8ea/history` (được xử lý bởi `agent-3`), lịch sử trả về **đủ cả 10 tin nhắn** (5 câu hỏi user + 5 câu trả lời assistant), chứng minh kiến trúc stateless với Redis hoạt động chính xác khi scale ngang. *(Đã dọn stack bằng `docker compose -p k5-day14-scaling down -v`.)*

---

## Part 6: Final Project — Output `check_production_ready.py`

Chạy chế độ đầy đủ (có Docker, trên WSL2 Ubuntu-24.04 `os.name == 'posix'`) tại thư mục `06-lab-complete/`:

```bash
python check_production_ready.py
```

- **Docker image:** `270 MB` (< 500 MB), build `34s`, `python:3.11-slim` multi-stage, user non-root `appuser`, `HEALTHCHECK`.
- **Rate limit & Stateless:** `429` sau đúng 5 request (`RATE_LIMIT_PER_MINUTE=5`, kèm `Retry-After`) và vẫn giữ `429` sau khi restart agent (lưu Redis Sorted Set).
- **Readiness & Cost guard:** `/ready` trả `200` khi Redis sống và `503` khi mất kết nối Redis (trong khi `/health` vẫn `200`); vượt ngân sách trả `402`.
- **Structured logging:** 17 dòng log JSON hợp lệ (`JsonFormatter`).
- **Graceful shutdown:** `SIGTERM` lúc đang có in-flight request vẫn trả `200` và thoát `exit code 0`; `docker stop` thoát `exit code 0` trong `0.9s` (< 10s).

```text
================================================================
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
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI Log

| Thời điểm | Mốc | Đã hỏi AI gì | AI gợi ý gì | Tự kiểm tra & chỉnh sửa |
|-----------|-----|--------------|-------------|-------------------------|
| 2026-11-26 | CP0 | Đọc tài liệu repo, lập lộ trình K5, hướng dẫn cài WSL2 Ubuntu-24.04 + tích hợp Docker và chuẩn bị tài khoản Render (Key Value + GitHub) | Hướng dẫn lệnh cài WSL2 Ubuntu-24.04, bật Docker WSL Integration, tạo Key Value Free region Singapore và nối GitHub trên Render | Tự cài đặt WSL2 Ubuntu-24.04, tạo venv `~/.venvs/day14`, tạo Key Value trên Render, nối GitHub và chạy lệnh xác minh `os.name == 'posix'`, `docker run --rm hello-world`, repo Public HTTP 200 |
| 2026-11-26 | CP1 | Phân tích anti-patterns trong `01-localhost-vs-production/develop/app.py`, đối chiếu với `production/app.py` + `config.py` và chạy kiểm thử cả hai bản | Liệt kê 9 anti-patterns kèm dòng code và gợi ý trình bày bảng so sánh theo nguyên tắc 12-Factor | Chạy thực tế cả hai app trong WSL2, kiểm chứng output `POST /ask?question=Hello`, `/health`, `/ready`, `/ask` JSON và log shutdown, đối chiếu từng số dòng trước khi ghi vào bài |
| 2026-11-26 | CP2 | Đọc `02-docker/` Dockerfile & `docker-compose.yml`, chạy build từ gốc repo, so sánh dung lượng image và test stack Compose qua Nginx | Trả lời 4 câu hỏi Dockerfile, giải thích multi-stage và vẽ sơ đồ kiến trúc 4 service (`nginx`, `agent`, `redis`, `qdrant`) | Tự chạy `docker build`, `docker images`, `docker compose -p k5-day14-docker up -d` trong WSL2, đo trực tiếp 1,667.8 MB vs 239.8 MB (giảm 85.6%) và kiểm chứng HTTP 200 qua Nginx |
| 2026-11-26 | CP3 | Phân tích `04-api-gateway/` (`auth.py`, `rate_limiter.py`, `cost_guard.py`) và chạy kiểm thử API Key, JWT, Rate Limit và Cost Guard | Giải thích luồng JWT, Sliding Window, thiết kế Redis Cost Guard và lý do kết hợp Rate Limit + Cost Guard | Chạy thực tế cả hai app `develop` và `production` trong WSL2, tự lấy JWT qua `/auth/token` (`student`/`demo123`), xác nhận `401`/`403`/`200`/`429` (`Retry-After: 59`) và che token trước khi dán |
| 2026-11-26 | CP4 | Phân tích liveness/readiness, SIGTERM graceful shutdown và thiết kế stateless trong `05-scaling-reliability/`, chạy stack 3 instance với Nginx & Redis | Giải thích khác biệt `/health` vs `/ready`, cơ chế Redis `SETEX`/`GET` và cấu hình Nginx upstream `proxy_next_upstream` | Chạy thực tế `develop/app.py` (xác nhận in-flight request vẫn trả 200 sau `kill -TERM`), bật `docker compose -p k5-day14-scaling up -d --build --scale agent=3` và chạy `test_stateless.py` xác nhận 3 instance phục vụ chung 1 session (10 tin nhắn) |
| 2026-11-26 | CP5 | Hoàn thiện các file TODO trong `06-lab-complete/` (`config.py`, `redis_client.py`, `auth.py`, `rate_limiter.py`, `cost_guard.py`, `main.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`) | Thiết kế các module đạt đủ hợp đồng 12 tiêu chí (Redis ZSET sliding window, Redis daily/monthly budget 402, `JsonFormatter`, `lifespan` + chuyển tiếp `SIGTERM`, multi-stage venv `/opt/venv` + `exec uvicorn`) | Kiểm tra tĩnh (`--static-only` 28/28) rồi chạy kiểm tra đầy đủ `python check_production_ready.py` trong WSL2 Ubuntu-24.04 với Docker, đạt `PASS 12/12` (43/43 checks, image 270 MB, `docker stop` 0.9s) và xác minh không sửa `check_production_ready.py` |
