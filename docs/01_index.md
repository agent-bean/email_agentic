# Đọc tài liệu Email Assistant

## Người mới

1. [Yêu cầu sản phẩm](02_product-requirements.md): mục tiêu, phạm vi và tiêu chí nghiệm thu đã chốt.
2. [Ứng dụng và phát triển local](03_application-guide.md): bắt đầu chạy, sử dụng và tìm đúng source.
3. [Kiến trúc và an toàn](04_architecture-and-safety.md): lý do thiết kế, quyền hạn và các bất biến khi sửa code.

## Người bảo trì

- [Đánh giá chất lượng](05_evaluation-guide.md): input, golden, review, hồi quy và nghiệm thu.
- [Release và vận hành](06_release-and-operations.md): CI, triển khai, backup, retention và rollback.
- [Đóng góp và chất lượng](08_contributing-and-quality.md): nhánh/PR, convention, các lớp test và bảo vệ `main`.
- Hướng dẫn riêng tại `docs/07_private-operations.md`: đường truy cập, cấu hình và quyền vận hành; chỉ có trên máy quản trị, ngoài Git.
- [Tham khảo giáo trình](references/01_supporting-knowledge.md): giới hạn khi tái sử dụng tài liệu/code mẫu; không cần đọc để chạy ứng dụng.
- Danh mục riêng tại `docs/references/02_private-source-catalog.md`: đường tìm tài liệu gốc trên máy quản trị, ngoài Git.

## Nguồn có thẩm quyền

PRD sở hữu yêu cầu và quyết định sản phẩm. Source, schema, cấu hình và kiểm thử sở hữu hành vi thực thi; tài liệu dẫn tới owner thay vì chép lại API hay danh mục lệnh. Kiến trúc giải thích lý do và ranh giới, không chứng nhận nghiệm thu. Kết quả chạy, đo thời gian, audit và lịch sử triển khai nằm trong `plans/reports/`; không thay yêu cầu sản phẩm. Tài liệu riêng, golden và dữ liệu vận hành được bảo vệ bởi [.gitignore](../.gitignore).
