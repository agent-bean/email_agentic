# Release và vận hành

Ứng dụng chạy trên VPS qua Cloudflare Access. Đường truy cập và cấu hình thật nằm trong hướng dẫn vận hành riêng `docs/07_private-operations.md`. Không chạy worker local và VPS trên hai bản DB cùng xử lý hộp thư. Không dùng `make up` cho production vì helper này chọn chế độ local.

## Bản source và thư mục

[Release packager](../scripts/prepare-release.py) (qua `make release`) sở hữu đóng gói source từ commit sạch, manifest/checksum và các loại file bị loại. Archive không chứa secret/dữ liệu runtime và không bao gồm image; build theo lockfiles. Đây là đường chuẩn bị source thủ công, không thay quy trình CI fetch commit bên dưới.

Đường dẫn vận hành trên VPS:

| Vị trí | Quyền và mục đích |
| --- | --- |
| `/opt/email-agentic/releases/<commit>` | Source thuộc root, không để user CI sửa; giữ bản trước để rollback. |
| `/opt/email-agentic/current` | Symlink tới release đang chạy. |
| `/etc/email-agentic` | Cấu hình thật, root đọc; tách khỏi source/archive, thư mục 700 và file 600. |
| `/var/backups/email-agentic` | Dump DB và file private, quyền 700; upload mã hóa tới R2. |

Chuyển archive qua SSH đã ghim host key; so SHA-256 trước giải nén. Google runtime token được chuyển riêng và mount read-only theo đường secret trong Compose; token seed, SSH key và Cloudflare API token không đi vào container. Cấu hình Tunnel thực tế cũng chuyển riêng, không nằm trong source public. User `deploy` không có Docker hoặc sudo tổng quát. CI chỉ gọi entry point root-owned giới hạn theo [quyền triển khai](#quyền-triển-khai); cài mới hoặc thay đổi entry point bằng tài khoản quản trị.

## Cấu hình production

[Production overlay](../infra/compose.production.yaml) kết hợp [Compose gốc](../infra/compose.yaml); không dùng overlay/helper local cho production. [Deploy script](../scripts/deploy-production.sh) sở hữu thứ tự build, drain, backup, migrate, cutover và readiness. Không chép lại chuỗi lệnh đó để vận hành một bản khác với script đã review.

Cấu hình thật được nạp qua env-file Compose, không `source` dotenv thành shell code hoặc in `docker compose config` chứa secret; chỉ kiểm bằng `config --quiet`. Migration tường minh, backup trước mọi thay đổi schema. Giữ scheduler tắt khi thiết lập/chuyển dữ liệu cho đến khi đã xác nhận đúng DB, token và mailbox.

Cài Docker Engine/Compose từ nguồn chính thức phù hợp Ubuntu hiện tại; kiểm phiên bản và nền tảng CPU trước khi build. Cài cloudflared trên host, validate ingress/JWT Access rồi chạy như service theo [tài liệu Cloudflare](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/as-a-service/linux/). Không mở thêm cổng firewall. Overlay theo [hướng dẫn Docker production](https://docs.docker.com/compose/how-tos/production/).

## Chuyển dữ liệu và kiểm tra

Giữ lịch sử nghiên cứu, approvals, Gmail Draft IDs và publication receipts khi chuyển local sang VPS. Trước dump cuối phải dừng tác vụ mới và local worker, chờ các lệnh gửi đang chạy hoàn tất; `running`/`unknown` cần đối chiếu riêng. Không chạy hai worker trên hai bản DB cùng điều khiển hộp thư. Backup cả nguồn và DB đích trước restore; đích mới vẫn dump baseline trước khi ghi. Không copy nóng thư mục PostgreSQL.

Dùng `pg_dump --format=custom --no-owner --no-acl`, kiểm `pg_restore --list`, rồi restore vào DB thử riêng. Đối chiếu số run/report/approval/action, trạng thái sent/unknown, checkpoint và nội dung báo cáo; không resume jobs hoặc gửi email trong DB thử. Sau khi đạt mới chuyển sang DB production và chỉ chạy worker tại VPS. Bytes report exports/attachment nằm trong PostgreSQL và đi cùng dump; app-data vẫn đi cùng snapshot.

Nghiệm thu rollout: readiness 200; không có Access JWT thì API bị từ chối; hostname đưa về đăng nhập Access; tài khoản owner vào được web/Grafana, tài khoản khác bị chặn. Kiểm nguồn email, report/draft và receipt gửi hiện hữu. Không gửi email để thử; chỉ dùng email tiếp theo được người dùng duyệt. Kiểm restart container vẫn giữ dữ liệu và không gửi lặp. Build/config validation không thay thế các kiểm tra thực tế này.

## Backup và rollback

Backup do [script](../scripts/backup-production.sh), [service](../infra/systemd/email-agentic-backup.service) và [timer](../infra/systemd/email-agentic-backup.timer) sở hữu lịch và thời gian giữ backup. Dump DB nhất quán và archive app-data, loại migration dump trùng; ghi release ID cùng bản backup. Dùng restic mã hóa lên R2 đã chuẩn bị, chỉ áp retention sau upload thành công; không áp lifecycle R2 xóa object restic theo tuổi. [Cách backup restic](https://restic.readthedocs.io/en/stable/040_backup.html). Khôi phục vào DB/volume thử riêng, so dữ liệu và receipt trước khi bật lịch; file dump tồn tại chưa chứng minh restore đạt.

Service nhận cấu hình backup từ `/etc/default/email-agentic-backup`; mật khẩu restic nằm riêng tại `/etc/email-agentic/restic-password`. Chỉ root đọc các file này. Dùng `systemctl status email-agentic-backup.timer` để kiểm lịch, `systemctl start email-agentic-backup.service` để chạy ngay và `journalctl -u email-agentic-backup.service --since "1 hour ago" --no-pager` để xem kết quả. Đối chiếu snapshot bằng restic rồi restore vào DB/volume riêng; không restore trực tiếp lên production để thử. Mất mật khẩu restic sẽ không khôi phục được backup; giữ bản mật khẩu quản trị riêng an toàn.

Retention do [script](../scripts/retention-production.sh), [service](../infra/systemd/email-agentic-retention.service) và [timer](../infra/systemd/email-agentic-retention.timer) sở hữu, chạy sau lịch backup hằng ngày. Cài unit vào `/etc/systemd/system`, chạy `systemctl daemon-reload` và `systemctl enable --now email-agentic-retention.timer`. Kiểm bằng `systemctl status email-agentic-retention.timer` và `journalctl -u email-agentic-retention.service`. Backup lỗi phải chặn cleanup; thứ tự dừng/khởi worker và dọn dump do script sở hữu. CLI mặc định dry-run; cách gọi xem `python -m email_agentic.platform.retention --help` trong image backend. Bản backup giữ theo lịch riêng nên payload đã cleanup có thể còn trong backup cho đến khi backup hết hạn. Cleanup không xóa email/lịch phía Google.

Rollback code: tắt retention timer nếu quay về release chưa hỗ trợ cleanup, dừng worker, chuyển `current` về release trước và dùng image mang đúng release ID, khởi chạy bằng `--no-build`; không xóa volume hoặc prune image trước khi ổn định. Chỉ làm vậy nếu schema tương thích. Khi không tương thích, backup trạng thái hiện tại rồi restore DB/app-data đồng bộ từ bản đã kiểm thử, đối chiếu các email đã gửi sau thời điểm backup trước khi chạy worker; không tự lặp các publication đã xảy ra. Bản triển khai đầu chưa có release trước để quay lại: dừng ứng dụng/connector, giữ volumes và backup để sửa.

Log deploy tự động nằm ở `/var/log/email-agentic-deploy/<commit>.log`, chỉ root đọc. Tra log ứng dụng bằng `docker compose ... logs --tail 100 <service>`, cloudflared qua `journalctl -u cloudflared`; không xuất raw email/prompt/token ra log. Chi tiết account/host/credential nằm trong hướng dẫn vận hành riêng ở máy quản trị.

## CI/CD và quyền triển khai

[CI/CD workflow](../.github/workflows/ci-cd.yml) sở hữu trigger, kiểm tra và điều kiện deploy; manifests/lockfiles sở hữu dependency. Kiểm tra chạy với DB riêng, không dùng Google, golden, credential hay dữ liệu production. Pass CI không thay nghiệm thu tích hợp hoặc chất lượng PRD.

Mọi thay đổi đi từ nhánh công việc qua PR và check `verify`, rồi squash merge vào `main`; xem [quy ước đóng góp và chất lượng](08_contributing-and-quality.md). Verify kiểm convention PR, lint/build, test unit/integration/E2E backend và web, script vận hành, container build, migration trên DB riêng và release packaging. DB thiếu phải fail các lớp bắt buộc. Browser E2E chạy API và PostgreSQL test thật; không cấp secret production cho PR.

Deploy chỉ sau verify trên nhánh/environment được workflow cho phép. Pull request không nhận secrets triển khai. Không hủy deployment đang chạy; khóa VPS và kiểm commit HEAD tránh cutover đè bởi phiên cũ. Cơ chế chính xác thuộc script/workflow.

Deploy và retention cùng giữ `/run/lock/email-agentic-deploy.lock` trước khi chọn release/dừng worker; tác vụ còn lại từ chối chạy khi khóa đang giữ. Khi nâng cấp từ bản dùng hai khóa riêng, quản trị viên dừng lịch retention, chờ tác vụ hiện tại kết thúc, cài lại entry point deploy root-owned theo phần dưới và cập nhật script retention đã review trước khi bật lại lịch. Thay source trong repo chưa tự cập nhật entry point đã cài trên VPS.

## Quyền triển khai

Environment secrets vẫn là `VPS_HOST`, `VPS_PORT`, `VPS_DEPLOY_SSH_KEY`, `VPS_KNOWN_HOSTS`. Host key được ghim từ kết nối quản trị đã xác minh; không tự tin cậy `ssh-keyscan` trong CI. Khi đổi máy/key, quản trị viên đối chiếu fingerprint qua console trước khi cập nhật secret.

User `deploy` không thuộc nhóm Docker/sudo và không có quyền sudo tổng quát. [Sudoers giới hạn](../infra/sudoers/email-agentic-deploy) chỉ cho phép gọi `/usr/local/sbin/email-agentic-deploy`, bản root-owned của [script deploy](../scripts/deploy-production.sh). Script chỉ nhận một full commit ID hoặc `--check`; tự fetch từ repo cố định và xác nhận commit đúng HEAD `main`. CI không upload script, archive hoặc cấu hình để root thực thi. Thay đổi chính entry point này cần quản trị viên cài lại từ source đã review; CI không tự sửa quyền của mình.

Quản trị viên cài script bằng `install -o root -g root -m 755 scripts/deploy-production.sh /usr/local/sbin/email-agentic-deploy`, kiểm file sudoers bằng `visudo -cf infra/sudoers/email-agentic-deploy`, rồi cài nó với mode 440 vào `/etc/sudoers.d/email-agentic-deploy`. Chạy `sudo -n /usr/local/sbin/email-agentic-deploy --check` dưới user `deploy` để kiểm đường gọi. [VPS connectivity](../.github/workflows/vps-connectivity.yml) kiểm thêm user, ranh giới quyền và entry point; không deploy ứng dụng.

## Khi deployment lỗi

[Deploy script](../scripts/deploy-production.sh) sở hữu phục hồi tự động; khi schema thay đổi, không tự restore DB vì có thể mất receipt gửi email. Quản trị viên dùng quy trình backup/rollback phía trên để đối chiếu dữ liệu trước khi bật worker. [Connectivity workflow](../.github/workflows/vps-connectivity.yml) chỉ kiểm đường kết nối/quyền, không deploy.

Quản trị secrets CI ở Settings → Environments → vps. Cấu hình/account/host thật và quyền truy cập nằm trong hướng dẫn riêng; không đưa log riêng lên issue/PR. Xem log triển khai theo commit tại đường đã nêu ở phần backup/rollback.
