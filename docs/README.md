# Tài liệu dự án Email Assistant

- [Hướng dẫn ứng dụng](application-guide.md): kiến trúc trong source, chạy local, kiểm tra và giới hạn đã công bố; được lưu cùng source trong Git.
- [PRD](project-overview-pdr.md): mục tiêu, phạm vi, yêu cầu, tiêu chí nghiệm thu và các quyết định đã chốt; làm căn cứ thiết kế kiến trúc.
- [Kiến trúc](system-architecture.md): apps/web và apps/backend, ranh giới agents/tools/domains, workflow, queue và vòng đời duyệt/phát hành; đã chốt, nền tảng đã dựng local; xem phần trạng thái triển khai trong tài liệu.
- [Quy tắc dữ liệu và xử lý](technical-contracts.md): dữ liệu, trạng thái, tool, phê duyệt, chống trùng và các bất biến cần kiểm thử.
- [Đánh giá chất lượng](evaluation-guide.md): đầu vào mẫu, golden riêng tư, review/khóa và giới hạn của runner.
- [Chuẩn bị VPS](vps-release-guide.md): source archive, production config, chuyển dữ liệu và rollback; chưa rollout.
- Checklist setup riêng tại `docs/deployment-guide.md`: đường quản trị và trạng thái tài nguyên; chỉ lưu local, không có trong bản clone public.
- [Tri thức hỗ trợ](references/supporting-knowledge.md): kiến thức và nhận xét code mẫu để tham khảo khi thảo luận kỹ thuật.
- Danh mục nguồn riêng tại `docs/references/source-catalog.md`: đường dẫn tài liệu gốc trên máy; chỉ lưu local.

PRD sở hữu yêu cầu sản phẩm; tài liệu kiến trúc/hợp đồng/setup sở hữu các quyết định thiết kế tương ứng, chưa chứng minh triển khai thành công. Theo preset classic, roadmap và các tài liệu khác chỉ được tạo khi có nội dung được xác lập. Kết quả thực thi và kiểm chứng nằm trong `plans/reports/`, không thay thế yêu cầu hoặc thiết kế.
