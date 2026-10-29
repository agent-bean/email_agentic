# GitHub Actions: kiểm tra đường triển khai

Workflow [VPS connectivity](../.github/workflows/vps-connectivity.yml) chỉ thử kết nối SSH và quyền của user `deploy`; chưa build hoặc triển khai ứng dụng.

Xem [hướng dẫn ứng dụng](application-guide.md) để chạy nền tảng local và truy cập tài liệu kiến trúc/eval.

Chạy trong GitHub → Actions → VPS connectivity → Run workflow → nhánh `main`. Environment `vps` chỉ cho phép nhánh `main`. Không chạy trên pull request. Key không có quyền sudo hoặc Docker.

Environment secrets: `VPS_HOST`, `VPS_PORT`, `VPS_DEPLOY_SSH_KEY`, `VPS_KNOWN_HOSTS`. Host key được ghim từ kết nối quản trị đã xác minh; không thay bằng việc tự tin cậy kết quả ssh-keyscan trong CI. Khi đổi máy/key host, quản trị viên đối chiếu fingerprint qua console trước khi cập nhật secret.

Quản trị secrets tại Settings → Environments → vps. Khi lỗi, xem job SSH trong Actions; không in secret để chẩn đoán. Runner dùng thư mục key tạm và xóa khi kết thúc. Cấu hình thật, báo cáo setup, dữ liệu riêng và tài liệu có đường dẫn local được giữ ngoài repo public qua ignore.
