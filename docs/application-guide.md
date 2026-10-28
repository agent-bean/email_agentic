# Email Assistant: kiến trúc và chạy local

Đây là nền tảng ứng dụng, chưa phải bản hoàn tất các yêu cầu sản phẩm. Điểm bắt đầu cho đánh giá chất lượng là [hướng dẫn golden và eval](evaluation-guide.md); CI hiện có được mô tả tại [hướng dẫn CI](ci-guide.md).

## Kiến trúc đã chọn

Một repo chứa React web và FastAPI backend. API phục vụ giao diện cùng origin và nhận yêu cầu; worker chạy workflow LangGraph cố định. Bảy vai trò được giữ trong cùng backend, không dùng agent lead hoặc bảy dịch vụ riêng. Cách chia này giữ việc triển khai và điều tra lỗi vừa với phạm vi một người dùng, một hộp thư và một lịch.

| Điểm vào | Trách nhiệm |
|---|---|
| [Web](../apps/web/src/app/app.tsx) | Giao diện theo nghiệp vụ, xem/sửa và duyệt |
| [API](../apps/backend/src/email_agentic/main.py) | HTTP, xác thực và bản build React |
| [Worker](../apps/backend/src/email_agentic/worker.py) | Nhận việc, resume và lịch quét |
| [Workflow](../apps/backend/src/email_agentic/workflows/research.py) | Điều phối các bước và chờ người xác nhận |
| [Bootstrap](../apps/backend/src/email_agentic/bootstrap.py) | Nối domains, agents, tools và integrations |
| [Tool harness](../apps/backend/src/email_agentic/tools/harness.py) | Kiểm schema, danh tính, quyền, giới hạn và audit trước thực thi |
| [Migration](../apps/backend/src/email_agentic/platform/migrate.py) | Backup và áp dụng schema có checksum |
| [Compose](../infra/compose.yaml) | API, worker, PostgreSQL và monitoring |

`domains/` sở hữu quy tắc nghiệp vụ và giao dịch. `agents/` xử lý từng vai trò, `tools/` sở hữu thao tác có quyền hạn, `integrations/` gọi provider; `runtime/` và `platform/` giữ hạ tầng thực thi. PostgreSQL được dùng cho dữ liệu, jobs và checkpoint trong các bảng riêng để tránh thêm broker khi chưa có nhu cầu.

Xác nhận đúng doanh nghiệp khác với duyệt phát hành. Bản báo cáo, body email, người nhận và lựa chọn phát hành phải được duyệt đúng phiên bản; sửa thì duyệt lại. Email có kết quả gửi chưa rõ phải đối chiếu trước khi gửi lại. Golden dùng chấm độc lập, không được đưa cho runtime hoặc model làm đáp án.

## Chạy local

Cần Docker Compose, uv và Node.js/npm. Xem phiên bản runtime/dependency tại [Dockerfile](../infra/Dockerfile), [backend manifest](../apps/backend/pyproject.toml) và [web manifest](../apps/web/package.json).

Tạo `.env` theo [.env.example](../.env.example) nếu chưa có. Điền chủ hộp thư, mật khẩu PostgreSQL/Grafana, gateway/model và Tavily; đặt token OAuth runtime tại đường dẫn cấu hình. Không ghi đè cấu hình đã có. Model chỉ cần khai báo qua `LLM_MODEL`.

Helper [app-control.py](../scripts/app-control.py) chỉ thao tác stack local; không SSH hoặc triển khai VPS. Chạy từ root repo:

```sh
uv sync --project apps/backend
npm ci --prefix apps/web
uv run --project apps/backend python scripts/app-control.py check
uv run --project apps/backend python scripts/app-control.py db
uv run --project apps/backend python scripts/app-control.py build
uv run --project apps/backend python scripts/app-control.py migrate
APP_ORIGIN=http://127.0.0.1:8000 uv run --project apps/backend python scripts/app-control.py up
```

App ở `http://127.0.0.1:8000`, Grafana ở `http://127.0.0.1:3000`. Helper ưu tiên biến shell hơn `.env`; override origin ở lệnh trên không sửa file cấu hình. Local auth chỉ dành cho truy cập local. Production cần Cloudflare Access theo [config/auth](../apps/backend/src/email_agentic/platform/auth.py); chưa có bước deploy ứng dụng trong helper.

Token Google chỉ được mount read-only cho runtime. Container hiện chạy UID 1000; file phải đọc được bởi UID này, không đổi secret thành file cho mọi người đọc. Token seed không được mount. Không chạy seed lại trên dữ liệu demo đã chuẩn bị.

Migration phải chạy tường minh trước khi mở API/worker. Dump trước thay đổi nằm trong volume `app-data`, tại `/data/backups`; lỗi backup sẽ dừng migration. Không xóa volume để xử lý một lỗi khởi động thông thường.

## Kiểm tra và dừng

```sh
uv run --project apps/backend python scripts/app-control.py test
npm run build --prefix apps/web
uv run --project apps/backend python scripts/app-control.py status
uv run --project apps/backend python scripts/app-control.py down
```

`test` cần PostgreSQL và image đã dựng, tạo backup trước khi ghi dữ liệu và dùng DB riêng `email_agentic_test`. Lệnh này chỉ dành cho stack thử local. `down` dừng container và giữ volume/backup.

Hợp đồng HTTP do [OpenAPI/Pydantic](../apps/backend/src/email_agentic/api/routes.py) sở hữu; kiểu web được sinh tại [api-schema.ts](../apps/web/src/lib/api-schema.ts). Khi thay API, xuất OpenAPI ra `.runtime/openapi.json`, rồi dùng script `api:generate` trong web manifest. Chạy Vite riêng cần đặt origin backend theo origin Vite.

## Trạng thái và giới hạn

Đã kiểm chứng queue/checkpoint qua restart, version approval/outbox, lease, auth/Origin, golden hash và build. Google/Tavily đã đọc thật trong kiểm tra tích hợp. Báo cáo dài qua gateway vẫn gặp timeout hoặc response chưa đạt schema; chưa xác nhận toàn bộ luồng nghiên cứu chạy thành công hoặc đạt mục tiêu chất lượng/thời gian.

`REPORT_TARGET_SECONDS` là mục tiêu chất lượng theo từng lượt; `RESEARCH_TIMEOUT_SECONDS` là ngân sách xử lý. Tăng ngân sách không đồng nghĩa đạt mục tiêu. Số đo hiện còn tính thời gian chờ xác nhận của người dùng.

Chưa hoàn tất: tự kích hoạt nghiên cứu từ email/lịch, Gmail history cursor, PDF đầu vào, xuất PDF/Word và attachment bất biến, UI đối chiếu Sent, cleanup/retention, backup định kỳ và trace xuyên tiến trình. Scheduler mặc định tắt; dữ liệu đồng bộ chưa tự trở thành nghiên cứu. Golden còn nháp và frozen replay chưa triển khai; xem [hướng dẫn eval](evaluation-guide.md).

Tài liệu vận hành riêng, cấu hình thật, golden và kết quả thử được giữ ngoài Git theo [.gitignore](../.gitignore).
