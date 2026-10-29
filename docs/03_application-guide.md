# Ứng dụng và phát triển local

Đọc [yêu cầu sản phẩm](02_product-requirements.md) để hiểu mục tiêu; [kiến trúc và an toàn](04_architecture-and-safety.md) giải thích ranh giới khi thay đổi ứng dụng. Kết quả chạy thực tế thuộc `plans/reports/`, không phải cam kết mọi tiêu chí đã đạt.

## Bắt đầu local

Cần Python/uv, Node/npm và Docker Compose; phiên bản/dependencies thuộc [backend manifest](../apps/backend/pyproject.toml), [web manifest](../apps/web/package.json) và lockfiles tương ứng. Cấu hình theo [.env.example](../.env.example); không đưa credential vào Git hoặc in cấu hình đã resolve.

[Makefile](../Makefile) là danh mục lệnh: chạy `make help` từ root. Lần đầu đi theo thứ tự `setup`, `check`, `db`, `build`, `migrate`, rồi `up`; backup phải thành công trước khi thay schema. [Local helper](../scripts/app-control.py) sở hữu thực thi, [local Compose](../infra/compose.local.yaml) sở hữu địa chỉ/port. Helper chỉ dành cho local; production theo [hướng dẫn release](06_release-and-operations.md).

Không khởi worker local với cùng hộp thư và bản sao DB production: hai DB độc lập không thể chống gửi trùng cho nhau. Không chạy lại seed trên bộ Google đã chuẩn bị. Token runtime mount read-only, chỉ cấp quyền đọc cho user container cần dùng; token seed không vào runtime. Không xóa volume để chữa lỗi khởi động thông thường.

Dùng `make test`, `make lint`, `make web-build` phù hợp thay đổi; test dùng DB riêng và cần image/PostgreSQL local. `make status` kiểm tiến trình, `make down` dừng stack và giữ volume. Chỉ dừng tiến trình mình đã khởi hoặc được giao quản lý.

## Hành trình sử dụng

1. Từ **Email & cuộc họp**, đồng bộ rồi chọn nguồn cần nghiên cứu. Với nhập tay, giữ nguyên email khách ở **Email gốc**, tách hướng dẫn vào **Yêu cầu nghiên cứu**. Khi nguồn không tải được, dùng **Tải lại nguồn**.
2. Kiểm pháp nhân/domain trước **Xác nhận và nghiên cứu**. Đây là xác nhận danh tính, chưa cấp quyền gửi. Không dựng email nguồn từ context cũ.
3. Review **Báo cáo** nội bộ và **Email nháp** cho khách riêng biệt. Kiểm nguồn, phần thiếu/mâu thuẫn và suy luận nhu cầu; có nháp chưa đồng nghĩa đủ chất lượng.
4. Kiểm To/Cc/Bcc, nội dung và file trước khi lưu phiên bản/duyệt. Nhiều địa chỉ cách nhau bằng dấu phẩy được kiểm khi lưu. Tải báo cáo không tự chọn attachment gửi khách. Đề nghị hết hạn cần lưu phiên bản chỉnh sửa mới để đề nghị lại.
5. **Lưu vào Gmail Drafts** cần scope compose; không duyệt, gửi hoặc ghi KB. Draft cũ và chỉnh sửa trực tiếp trong Gmail cần được đối chiếu; không gửi cùng nội dung ở cả Gmail và ứng dụng.
6. Gửi/lưu KB chỉ theo gói đã duyệt. Khi gửi chưa rõ, dùng **Đối chiếu Sent** trước quyết định gửi lại. Không tìm thấy ngay không chứng minh chưa gửi.

Automation mới cần cutoff để tránh xử lý hàng loạt thư cũ. Cấu hình/default thuộc [Settings](../apps/backend/src/email_agentic/platform/config.py); đường bật/tắt môi trường thật thuộc hướng dẫn riêng.

## Tìm source theo việc cần sửa

| Công việc | Owner |
| --- | --- |
| Giao diện, điều hướng | [Web app](../apps/web/src/app/app.tsx), [features](../apps/web/src/features/) |
| HTTP và quyền | [API](../apps/backend/src/email_agentic/api/routes.py), [auth](../apps/backend/src/email_agentic/platform/auth.py) |
| Khởi tạo, xử lý job | [Bootstrap](../apps/backend/src/email_agentic/bootstrap.py), [worker](../apps/backend/src/email_agentic/worker.py) |
| Nghiên cứu, nội dung | [Workflow](../apps/backend/src/email_agentic/workflows/research.py), [agents](../apps/backend/src/email_agentic/agents/) |
| Dữ liệu, quy tắc | [Domains](../apps/backend/src/email_agentic/domains/), [migrations](../apps/backend/migrations/) |
| Provider, công cụ | [Integrations](../apps/backend/src/email_agentic/integrations/), [harness](../apps/backend/src/email_agentic/tools/harness.py) |

Khi thay HTTP contract, [web manifest](../apps/web/package.json) sở hữu lệnh `api:generate` từ OpenAPI sang [kiểu web](../apps/web/src/lib/api-schema.ts); không sửa kiểu sinh bằng tay. Web/backend có image riêng nên phải giữ tương thích API khi cập nhật độc lập.

## Giới hạn cần hiểu

Mục tiêu thời gian khác timeout xử lý. Tăng timeout không chứng minh đạt mốc PRD. [Đánh giá](05_evaluation-guide.md) sở hữu cách đọc số đo/nghiệm thu; không suy ra chất lượng từ một lượt thành công, số URL hay một gói được duyệt.

Nguồn có thể thiếu, cũ hoặc bị provider chặn. Citation thuộc evidence chỉ chứng minh URL đã thu, chưa chứng minh dữ kiện đúng. PDF/OCR có thể lỗi hoặc thiếu trang; cần review phần không đọc được. Giới hạn thực thi thuộc [web research](../apps/backend/src/email_agentic/agents/web_research.py), [integrations](../apps/backend/src/email_agentic/integrations/) và Settings.

[Retention](../apps/backend/src/email_agentic/platform/retention.py) sở hữu cleanup và điều kiện bảo vệ dữ liệu chờ xử lý. Nguồn hết hạn làm giảm khả năng kiểm tra lại; bản lưu cũ không tự thành bằng chứng hiện hành. Cleanup app không xóa email/lịch Google; backup có vòng đời riêng theo [vận hành](06_release-and-operations.md).
