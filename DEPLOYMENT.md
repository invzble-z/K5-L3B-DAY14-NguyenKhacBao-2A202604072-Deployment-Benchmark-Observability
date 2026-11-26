# Deployment Information

## Public URL
https://day14-production-agent-lypk.onrender.com

## Platform
Render (Web Service — Docker runtime, Singapore region, Free plan + Render Key Value Redis)

## Test Commands

### Health & Readiness Checks
```bash
curl https://day14-production-agent-lypk.onrender.com/health
# Expected (200): {"status":"ok","environment":"production","uptime_seconds":...}

curl https://day14-production-agent-lypk.onrender.com/ready
# Expected (200): {"status":"ready","redis":"connected"}
```

### API Test (Authentication: 401 without key, 200 with X-API-Key)
```bash
# Without X-API-Key -> Expected: HTTP 401
curl -i -X POST https://day14-production-agent-lypk.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'

# With valid X-API-Key -> Expected: HTTP 200
curl -i -X POST https://day14-production-agent-lypk.onrender.com/ask \
  -H "X-API-Key: YOUR_AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "What is deployment?"}'
```

### CP6 Self-Check Script (4 status checks)
```bash
BASE="https://day14-production-agent-lypk.onrender.com"
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

## Environment Variables Set on Render Dashboard
*(Giá trị secret đặt trực tiếp trên Render Dashboard, không commit vào Git)*
- `PORT` *(do Render tự cấp — chạy ở port 10000)*
- `REDIS_URL` *(Internal Key Value URL của Render Key Value cùng region Singapore)*
- `AGENT_API_KEY` *(secret key để xác thực header `X-API-Key`)*
- `ENVIRONMENT=production`
- `LOG_LEVEL=INFO`
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=10.0`

## Screenshots
- [Deployment dashboard & environment variables](screenshots/dashboard.png)
- [Service running logs](screenshots/running.png)
- [Public endpoint test results](screenshots/test.png)
