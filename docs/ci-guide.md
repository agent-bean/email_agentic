# CI/CD trên GitHub Actions

[CI and VPS deploy](../.github/workflows/ci-cd.yml) chạy khi push `main`, mở/cập nhật pull request hoặc chạy thủ công. Job `verify` cài dependencies từ lockfiles, chạy lint, typecheck/build web, build hai Docker image, backup/migrate PostgreSQL riêng và chạy backend tests. Không dùng tài khoản Google, golden, API key hoặc dữ liệu production trong CI. Kiểm đóng gói release cũng phải pass.

Job `deploy` chỉ chạy sau `verify` thành công, trên `main` và environment `vps`. Pull request không nhận secrets triển khai. Các action được ghim bằng commit; không hủy một deployment đang chạy khi có push mới. VPS còn giữ khóa deploy riêng để chặn hai phiên SSH triển khai đồng thời. Commit cũ hơn HEAD của `main` bị từ chối trước cutover.

## Quyền triển khai

Environment secrets vẫn là `VPS_HOST`, `VPS_PORT`, `VPS_DEPLOY_SSH_KEY`, `VPS_KNOWN_HOSTS`. Host key được ghim từ kết nối quản trị đã xác minh; không tự tin cậy `ssh-keyscan` trong CI. Khi đổi máy/key, quản trị viên đối chiếu fingerprint qua console trước khi cập nhật secret.

User `deploy` không thuộc nhóm Docker/sudo và không có quyền sudo tổng quát. [Sudoers giới hạn](../infra/sudoers/email-agentic-deploy) chỉ cho phép gọi `/usr/local/sbin/email-agentic-deploy`, bản root-owned của [script deploy](../scripts/deploy-production.sh). Script chỉ nhận một full commit ID hoặc `--check`; tự fetch từ repo cố định và xác nhận commit đúng HEAD `main`. CI không upload script, archive hoặc cấu hình để root thực thi. Thay đổi chính entry point này cần quản trị viên cài lại từ source đã review; CI không tự sửa quyền của mình.

Quản trị viên cài script bằng `install -o root -g root -m 755 scripts/deploy-production.sh /usr/local/sbin/email-agentic-deploy`, kiểm file sudoers bằng `visudo -cf infra/sudoers/email-agentic-deploy`, rồi cài nó với mode 440 vào `/etc/sudoers.d/email-agentic-deploy`. Chạy `sudo -n /usr/local/sbin/email-agentic-deploy --check` dưới user `deploy` để kiểm đường gọi. [VPS connectivity](../.github/workflows/vps-connectivity.yml) kiểm thêm user, ranh giới quyền và entry point; không deploy ứng dụng.

## Cutover và xử lý lỗi

Deploy build image trước, chờ jobs hiện tại kết thúc, dừng worker để ngừng nhận việc mới và cho tác vụ đã nhận ghi xong receipt. Sau đó encrypted backup phải thành công trước migration. App chuyển sang release mới, khởi động web/API/worker và kiểm readiness. Cấu hình, token và volumes giữ ngoài source.

Khi rollout lỗi và migration không đổi, script khởi động lại code trước. Nếu migration đã đổi, script dừng API/worker để quản trị viên kiểm tra backup và schema; không tự restore DB có thể làm mất receipt gửi email. Chi tiết backup/rollback nằm trong [hướng dẫn VPS](vps-release-guide.md).

Log Actions chỉ ghi các mốc triển khai. Log chi tiết thuộc root tại `/var/log/email-agentic-deploy/<commit>.log`; không đưa log có dữ liệu riêng lên issue hoặc PR. Quản trị secrets ở Settings → Environments → vps. Cấu hình thật và báo cáo vận hành nằm ngoài repo public.
