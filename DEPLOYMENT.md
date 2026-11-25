# Deployment — Day 14

**Nền tảng đã chuẩn bị:** Render Free. Blueprint ở `06-lab-complete/render.yaml` cấu hình web service dùng Dockerfile của Part 6 và một Key Value tương thích Redis qua mạng nội bộ.

**URL public:** [day14-agent-6vy4.onrender.com/health](https://day14-agent-6vy4.onrender.com/health)

**Kiểm tra ngày 25/11/2026 (GMT+7):** `GET /health` trả 200, `GET /ready` trả 200, `POST /ask` thiếu API key trả 401 và `POST /ask` có API key hợp lệ trả 200. Kết quả có API key do học viên xác minh trên Ubuntu WSL. Đường dẫn gốc `/` trả 404 vì agent chưa khai báo route này.

## Triển khai bằng Blueprint

1. Commit và push mã nguồn Part 6 lên bản fork.
2. Trong Render Dashboard, chọn **New → Blueprint**, kết nối bản fork và chọn nhánh `main`.
3. Đặt **Blueprint Path** là `06-lab-complete/render.yaml`. Xác nhận hai tài nguyên `day14-agent` và `day14-agent-cache` đều dùng gói Free rồi chọn **Deploy Blueprint**.
4. Khi web service chuyển sang **Live**, lấy URL `.onrender.com` của `day14-agent` và chạy bốn lệnh kiểm tra bên dưới.

[Hướng dẫn Blueprint của Render](https://render.com/docs/infrastructure-as-code#setup)

## Biến môi trường

| Biến | Cấu hình |
|---|---|
| `PORT` | Do nền tảng cấp. Dockerfile dùng 8000 nếu chưa đặt. |
| `ENVIRONMENT` | `production` |
| `AGENT_API_KEY` | Giá trị bí mật trong service agent |
| `REDIS_URL` | URL nội bộ của Redis trong cùng project |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `1.0` |

## Kiểm tra URL public

Trong terminal Bash, thay giá trị `BASE` bằng URL của service. Mở **day14-agent → Environment** để lấy giá trị `AGENT_API_KEY` mà Render đã tạo. `read -s` ẩn key khi nhập và các lệnh kiểm tra chỉ in HTTP status.

```bash
BASE='https://day14-agent-6vy4.onrender.com'
read -rsp 'AGENT_API_KEY: ' AGENT_API_KEY
echo
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'
unset AGENT_API_KEY
```

## Ảnh minh chứng

- [Dashboard Render](screenshots/dashboard.png)
- [Service Live trên Render](screenshots/running.png)
- [Kết quả HTTP 200, 200, 401, 200](screenshots/test.png)
