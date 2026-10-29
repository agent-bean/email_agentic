# Vận hành trên VPS

Ứng dụng chạy trên VPS qua Cloudflare Access. Đường truy cập và cấu hình thật nằm trong hướng dẫn vận hành riêng `docs/deployment-guide.md`. Worker local đã dừng để tránh hai bản DB cùng xử lý hộp thư. Không dùng `make up` cho production vì helper này chọn chế độ local.

## Bản source và thư mục

Commit xong, chạy `python3 scripts/prepare-release.py`. Script chỉ đóng gói source backend/web, infra, script backup và Docker ignore từ HEAD sạch. Archive và manifest SHA-256 nằm trong thư mục riêng `.runtime/releases/`; không chứa Git metadata, tài liệu riêng, evals, token hoặc dữ liệu đang chạy. Archive không bao gồm image; build trên VPS bằng lockfiles đã có. Không ghi đè archive đã chuẩn bị.

Đường dẫn vận hành trên VPS:

| Vị trí | Quyền và mục đích |
| --- | --- |
| `/opt/email-agentic/releases/<commit>` | Source thuộc root, không để user CI sửa; giữ bản trước để rollback. |
| `/opt/email-agentic/current` | Symlink tới release đang chạy. |
| `/etc/email-agentic` | Cấu hình thật, root đọc; tách khỏi source/archive, thư mục 700 và file 600. |
| `/var/backups/email-agentic` | Dump DB và file private, quyền 700; upload mã hóa tới R2. |

Chuyển archive qua SSH đã ghim host key; so SHA-256 trước giải nén. Google runtime token được chuyển riêng và mount read-only theo đường secret trong Compose; token seed, SSH key và Cloudflare API token không đi vào container. Cấu hình Tunnel thực tế cũng chuyển riêng, không nằm trong source public. Giữ user `deploy` không có Docker/sudo; lần đầu dùng tài khoản quản trị. Chưa cấp quyền CI triển khai.

## Cấu hình production

[Production overlay](../infra/compose.production.yaml) áp dụng lên [Compose gốc](../infra/compose.yaml), không kết hợp overlay local. Mỗi image gắn `RELEASE_ID` bằng full commit ID trong `.release-id`; API/worker/migrate cùng image backend, web có image riêng. Compose project là `email-agentic-vps`, khác local. Log xoay vòng 10 MB × 3/service; các dịch vụ chạy lâu tự restart. App và Grafana chỉ bind loopback; PostgreSQL không publish port.

Trước lệnh dưới đây, quản trị viên phải nạp cấu hình production qua cơ chế env-file của Compose, đặt `APP_ORIGIN` đúng HTTPS hostname đã có, `CF_TEAM_DOMAIN`/`CF_AUDIENCE` đúng Access và giữ scheduler tắt. Không `source` file dotenv thành shell code, không in `docker compose config` chứa secret. Kiểm bằng `config --quiet`.

```bash
cd /opt/email-agentic/current
export RELEASE_ID="$(cat .release-id)"
export COMPOSE_ENV_FILES=/etc/email-agentic/runtime.conf
compose=(docker compose -f infra/compose.yaml -f infra/compose.production.yaml)
"${compose[@]}" config --quiet
"${compose[@]}" build api web
"${compose[@]}" up -d --wait postgres
```

Chỉ tiếp tục sau khi xử lý dữ liệu bên dưới. Migration phải dùng image vừa build và backup trước mọi thay đổi schema; không tự chạy migration khi container API khởi động.

```bash
"${compose[@]}" run --rm migrate
"${compose[@]}" up -d --no-build --wait web api worker prometheus tempo grafana
curl --fail http://127.0.0.1:8000/health/ready
```

Cài Docker Engine/Compose từ nguồn chính thức phù hợp Ubuntu hiện tại; kiểm phiên bản và nền tảng CPU trước khi build. Cài cloudflared trên host, validate ingress/JWT Access rồi chạy như service theo [tài liệu Cloudflare](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/as-a-service/linux/). Không mở thêm cổng firewall. Overlay theo [hướng dẫn Docker production](https://docs.docker.com/compose/how-tos/production/).

## Chuyển dữ liệu và kiểm tra

Giữ lịch sử nghiên cứu, approvals, Gmail Draft IDs và publication receipts khi chuyển local sang VPS. Trước dump cuối phải dừng tác vụ mới và local worker, chờ các lệnh gửi đang chạy hoàn tất; `running`/`unknown` cần đối chiếu riêng. Không chạy hai worker trên hai bản DB cùng điều khiển hộp thư. Backup cả nguồn và DB đích trước restore; đích mới vẫn dump baseline trước khi ghi. Không copy nóng thư mục PostgreSQL.

Dùng `pg_dump --format=custom --no-owner --no-acl`, kiểm `pg_restore --list`, rồi restore vào DB thử riêng. Đối chiếu số run/report/approval/action, trạng thái sent/unknown, checkpoint và nội dung báo cáo; không resume jobs hoặc gửi email trong DB thử. Sau khi đạt mới chuyển sang DB production và chỉ chạy worker tại VPS. App-data đi cùng snapshot; hiện chưa có chức năng xuất file báo cáo nên migration dumps không thay cho attachment/report backup về sau.

Nghiệm thu rollout: readiness 200; không có Access JWT thì API bị từ chối; hostname đưa về đăng nhập Access; tài khoản owner vào được web/Grafana, tài khoản khác bị chặn. Kiểm nguồn email, report/draft và trạng thái Bosch đã gửi. Không gửi email để thử; chỉ dùng email tiếp theo được người dùng duyệt. Kiểm restart container vẫn giữ dữ liệu và không gửi lặp. Build/config validation không thay thế các kiểm tra thực tế này.

## Backup và rollback

Backup do [script](../scripts/backup-production.sh), [service](../infra/systemd/email-agentic-backup.service) và [timer](../infra/systemd/email-agentic-backup.timer) sở hữu: 02:00 Asia/Bangkok hằng ngày, giữ bảy bản theo ngày. Dump DB nhất quán và archive app-data, loại migration dump trùng; ghi release ID cùng bản backup. Dùng restic mã hóa lên R2 đã chuẩn bị, chỉ áp retention sau upload thành công; không áp lifecycle R2 xóa object restic theo tuổi. [Cách backup restic](https://restic.readthedocs.io/en/stable/040_backup.html). Khôi phục vào DB/volume thử riêng, so dữ liệu và receipt trước khi bật lịch; file dump tồn tại chưa chứng minh restore đạt.

Service nhận cấu hình backup từ `/etc/default/email-agentic-backup`; mật khẩu restic nằm riêng tại `/etc/email-agentic/restic-password`. Chỉ root đọc các file này. Dùng `systemctl status email-agentic-backup.timer` để kiểm lịch, `systemctl start email-agentic-backup.service` để chạy ngay và `journalctl -u email-agentic-backup.service --since "1 hour ago" --no-pager` để xem kết quả. Đối chiếu snapshot bằng restic rồi restore vào DB/volume riêng; không restore trực tiếp lên production để thử. Mất mật khẩu restic sẽ không khôi phục được backup; giữ bản mật khẩu quản trị riêng an toàn.

Rollback code: dừng worker, chuyển `current` về release trước và dùng image mang đúng release ID, khởi chạy bằng `--no-build`; không xóa volume hoặc prune image trước khi ổn định. Chỉ làm vậy nếu schema tương thích. Khi không tương thích, backup trạng thái hiện tại rồi restore DB/app-data đồng bộ từ bản đã kiểm thử, đối chiếu các email đã gửi sau thời điểm backup trước khi chạy worker; không tự lặp các publication đã xảy ra. Bản triển khai đầu chưa có release trước để quay lại: dừng ứng dụng/connector, giữ volumes và backup để sửa.

Tra log bằng `docker compose ... logs --tail 100 <service>`, cloudflared qua `journalctl -u cloudflared`; không xuất raw email/prompt/token ra log. Chi tiết account/host/credential nằm trong hướng dẫn vận hành riêng ở máy quản trị.
