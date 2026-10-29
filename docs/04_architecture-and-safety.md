# Kiến trúc và ranh giới an toàn

[PRD](02_product-requirements.md) sở hữu phạm vi, lịch, retention và tiêu chí nghiệm thu. Tài liệu này sở hữu lý do thiết kế và ranh giới cần giữ; field/trạng thái/endpoint thuộc [migrations](../apps/backend/migrations/) và [API](../apps/backend/src/email_agentic/api/routes.py).

## Vì sao tổ chức như vậy?

Một repo chứa web React và backend FastAPI. Web có image riêng để cập nhật giao diện độc lập; API/worker dùng chung image vì cùng code/dependencies. Proxy cùng origin giữ một đường đăng nhập. Bảy vai trò là phân công nghiệp vụ, không phải bảy server hay bảy LLM call. [Bootstrap](../apps/backend/src/email_agentic/bootstrap.py), [workflow](../apps/backend/src/email_agentic/workflows/research.py) và [Compose](../infra/compose.yaml) là điểm vào thực thi.

Luồng do code điều phối giúp kiểm soát thứ tự, deadline và điểm chờ người. Không thêm supervisor, microservice, MCP/A2A, Redis/Celery hoặc broker khi nhu cầu chưa được chứng minh. PostgreSQL chứa nghiệp vụ, jobs và checkpoint để tránh hạ tầng queue riêng ở quy mô hiện tại; ba nhóm không có cùng thẩm quyền. Dữ liệu nghiệp vụ là nguồn chuẩn cho phê duyệt/kết quả gửi; checkpoint chỉ giúp chạy tiếp.

[Domains](../apps/backend/src/email_agentic/domains/) sở hữu giao dịch/quy tắc; agents hiểu/tổng hợp nội dung; tools sở hữu thao tác có quyền; integrations nối provider. Chỉ owner nghiệp vụ sửa dữ liệu của mình. Memory/KB bắt đầu bằng truy xuất PostgreSQL; chưa chọn vector DB/GraphRAG chỉ vì giáo trình có ví dụ. KB đã duyệt khác memory nháp, không tạo kho chuẩn thứ hai trong LangGraph Store.

## Danh tính, nguồn và nội dung

Không gộp pháp nhân theo tên hiển thị, email cá nhân hoặc quan hệ mẹ/con. Xác nhận doanh nghiệp khác duyệt phát hành. Email/lịch/PDF/web là dữ liệu không đáng tin, không tự cấp quyền hoặc ghi đè instruction. Agent chỉ nhận ngữ cảnh cần thiết; không lưu chain-of-thought hay đưa secret vào prompt, checkpoint, audit/telemetry.

Email nguồn giữ nguyên, tách khỏi yêu cầu nghiên cứu; snapshot Google do backend lấy theo owner, không tin metadata client. Calendar là nguồn riêng, cần kiểm phiên bản/thay đổi/hủy trước sử dụng. Owner: [ResearchService](../apps/backend/src/email_agentic/domains/research/service.py), [Gmail sync](../apps/backend/src/email_agentic/domains/inbox/sync.py), [Calendar automation](../apps/backend/src/email_agentic/domains/inbox/calendar.py).

Chỉ danh tính công ty/domain đã xác nhận đi vào tìm kiếm công khai; không gửi email/lịch/PDF riêng sang search/scrape provider. Trích đoạn/trang đọc thành công chưa là dữ kiện xác minh. Ngày thu thập không thay ngày xuất bản; tin cũ giữ riêng, công khai mâu thuẫn và phần thiếu. Nhu cầu tiềm năng là suy luận có căn cứ. [Web research](../apps/backend/src/email_agentic/agents/web_research.py) và [report generation](../apps/backend/src/email_agentic/agents/report_generation.py) sở hữu thu nguồn, prompt và citation.

Báo cáo nội bộ và email gửi khách có mục đích khác nhau. Email không mang đánh giá nội bộ, thông tin riêng của bên thứ ba hoặc năng lực/cam kết tự bịa. Dùng ngôn ngữ nghiệp vụ; provenance bộ thử giữ trong metadata, không biến thành lời gửi khách.

## Phê duyệt bảo vệ điều gì?

Người dùng duyệt đúng phiên bản nội dung, To/Cc/Bcc, tệp và lựa chọn gửi/lưu. Sửa phần được duyệt cần phiên bản/quyết định mới. Sau duyệt không gọi model viết lại. Tệp giữ đúng bytes/checksum; tải riêng không tự chọn attachment. Owner: [approvals](../apps/backend/src/email_agentic/domains/approvals/service.py), [reports](../apps/backend/src/email_agentic/domains/reports/), [publication](../apps/backend/src/email_agentic/domains/publication/).

Quyết định và công việc phát hành phải bền vững cùng giao dịch; checkpoint/resume payload hay boolean frontend không chứng minh được duyệt. Hành động cũ chưa bắt đầu bị chặn khi gói bị thay. Khi lời gọi gửi đã bắt đầu, không hứa thu hồi; giữ kết quả thật ngay cả khi người dùng sửa tiếp.

Xuất Gmail Draft không cấp quyền gửi/KB. Draft có thể bị sửa bên ngoài; gửi phải kiểm đúng nội dung/thread/attachment. Draft mất/đổi không cho phép chuyển sang email mới. Gửi mơ hồ cần đối chiếu, không retry mù. Message-ID giúp tìm lại, không bảo đảm Gmail chống trùng. Email thành công nhưng KB lỗi không được làm gửi lại. [Publication](../apps/backend/src/email_agentic/domains/publication/) và [Google integration](../apps/backend/src/email_agentic/integrations/google.py) sở hữu xử lý cụ thể.

## Công cụ, quyền và phục hồi

[Tool harness](../apps/backend/src/email_agentic/tools/harness.py) sở hữu sáu gate theo thứ tự PRD, kể cả worker/scheduler. Danh tính/owner/role do runtime cấp; quyền chung không thay duyệt theo gói. Tool gửi/KB chỉ dành cho runtime sau duyệt, không trong allowlist LLM. Audit lỗi phải chặn thực thi; audit nghiệp vụ khác trace và không bị sampling bỏ mất.

Jobs cần chống trùng/lease; không giữ DB transaction qua mạng hoặc chờ người. DB và checkpoint không tự commit cùng nhau: replay cần khóa và đối chiếu. Lease hết hạn không thu hồi request Gmail đã rời máy. Retry dùng ngân sách chung thay vì nhân lồng SDK/node/worker. Owner: [runtime](../apps/backend/src/email_agentic/runtime/), [worker](../apps/backend/src/email_agentic/worker.py), [workflow](../apps/backend/src/email_agentic/workflows/research.py).

Cloudflare Access không thay kiểm owner, phiên bản, Origin hay phê duyệt. OAuth Google nối hộp thư/lịch, khác đăng nhập ứng dụng. Parse/export có giới hạn và không tải tài nguyên tùy ý từ nội dung model. Owner: [auth](../apps/backend/src/email_agentic/platform/auth.py), [report files](../apps/backend/src/email_agentic/domains/reports/files.py), [renderer](../apps/backend/src/email_agentic/integrations/report_export.py).

Không xóa dữ liệu còn cần xử lý/đối chiếu gửi. [Retention](../apps/backend/src/email_agentic/platform/retention.py) sở hữu cleanup; [vận hành](06_release-and-operations.md) sở hữu backup/restore. Trace không chứng minh quyền/duyệt; giá dịch vụ chưa biết phải để chưa xác định, không coi là miễn phí.

## Kiểm chứng khi thay đổi

[Backend tests](../apps/backend/tests/) kiểm ownership, sửa/duyệt cạnh tranh, hết hạn, restart, lease, gửi chưa rõ, KB lỗi sau gửi và quyền file. Contract mới cần kiểm web theo [hướng dẫn ứng dụng](03_application-guide.md). Tích hợp thật và [đánh giá sản phẩm](05_evaluation-guide.md) có mục đích khác nhau; pass tests không tự chứng minh chất lượng briefing hoặc quyền mở rộng dữ liệu production.
