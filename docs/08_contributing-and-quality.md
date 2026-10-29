# Đóng góp và kiểm chứng chất lượng

Luồng chuẩn là nhánh công việc → pull request → CI đạt → squash merge → CI trên `main` → deploy đúng commit. Không push trực tiếp vào `main`. [Workflow](../.github/workflows/ci-cd.yml) sở hữu lệnh kiểm tra và điều kiện deploy; [vận hành](06_release-and-operations.md) sở hữu backup, rollback và quyền production.

## Nhánh, commit và PR

Tạo nhánh từ `main` mới nhất, đặt tên `<type>/<mo-ta-ngan>` như `feat/review-workspace`, `fix/approval-expiry`, `test/publication`. Các type được kiểm tại [script convention](../scripts/check-pr-conventions.py). Commit và tiêu đề PR dùng Conventional Commits, ví dụ `feat(web): improve report review`. Scope không bắt buộc; breaking change phải nêu rõ contract và migration. Giữ commit tập trung, không ghi tham chiếu AI hoặc mã phase/audit vào code hay commit.

```bash
git fetch origin
git switch -c feat/review-workspace origin/main
make hooks-install
# Chỉnh sửa, kiểm thử, review diff rồi commit các file thuộc phạm vi.
git push -u origin feat/review-workspace
gh pr create --base main --title 'feat(web): improve report review' --body-file /path/to/pr-body.txt
```

`make hooks-install` là lựa chọn local, chặn mọi ref push đến `main`, kể cả khi nhánh nguồn có tên khác. Installer từ chối thay thế hook/cấu hình hiện hữu; khi đó tích hợp guard thủ công. Hook không thay bảo vệ GitHub vì có thể bị bỏ qua bằng `--no-verify`.

Nội dung PR nên theo mẫu sau, điền bằng kết quả thực:

```text
Vấn đề và hành vi sau thay đổi:

Phạm vi / contract / migration bị ảnh hưởng:

Kiểm chứng (lệnh, kết quả, phần chưa chạy và lý do):

Rủi ro và cách rollback:

Ảnh trước/sau khi có thay đổi giao diện:
```

Không đưa email, dữ liệu người dùng, token, `.env`, private fixture, log production hoặc ảnh có dữ liệu thật vào PR/artifact. Kiểm `git diff --cached` trước commit. Review correctness, ownership, phê duyệt, retry và ảnh hưởng migration; pass tests không thay nghiệm thu sản phẩm. Chỉ squash merge khi check `verify` đạt và conversation đã xử lý. Repo một owner không yêu cầu một reviewer thứ hai không thể đáp ứng.

## Lớp kiểm thử và module

Khi làm việc với agent, controller luôn giao các phần việc có ranh giới rõ cho subagent: nêu mục tiêu, file được đọc/sửa, tiêu chí đạt và skill phù hợp đã chọn. Chỉ chạy song song khi ownership không chồng nhau; không để nhiều agent sửa cùng file/config hoặc điều khiển cùng DB/process. Controller giữ quyết định tích hợp, review diff, kiểm chứng xuyên module và báo cáo cuối; delegate không tự mở rộng phạm vi hay hoàn tác thay đổi của người khác.

[EditorConfig](../.editorconfig) thống nhất UTF-8, LF, newline cuối file và indentation. Backend lint bằng Ruff, web kiểm TypeScript cho cả source, tests và config. Dependency thay đổi phải cập nhật lockfile; CI cài ở chế độ frozen/clean.

Backend tổ chức theo `apps/backend/tests/{unit,integration,e2e}/<module>/`; marker tự gán theo lớp. Unit kiểm quy tắc riêng; integration kiểm DB/renderer/process thật; E2E đi qua public API và persistence. Web có unit, integration component và E2E browser với backend/DB thật. Dùng doubles ở ranh giới provider trong test, không thay triển khai runtime bằng dữ liệu giả. Không gọi provider production trong CI.

| Phạm vi | Lệnh từ root |
| --- | --- |
| Backend unit | `make test-unit` |
| Backend integration | `make test-integration` |
| Backend E2E | `make test-e2e` |
| Toàn bộ backend | `make test` |
| Chọn module/test | `make test PYTEST_ARGS='-m integration -k publication'` |
| Script vận hành/Git | `make test-scripts` |
| Web unit | `npm run test:unit --prefix apps/web` |
| Web integration | `npm run test:integration --prefix apps/web` |
| Toàn bộ web, tự chuẩn bị DB test | `make web-test` |
| Web E2E | `npm run test:e2e --prefix apps/web` |
| Lint / build | `make lint web-build` |

`make setup` cài dependency. Trước backend integration/E2E local, chuẩn bị Docker, `.env` theo hướng dẫn ứng dụng rồi `make db build`; helper test backup/migrate DB local trước khi tạo/migrate DB riêng `email_agentic_test`. Không trỏ test vào DB production. CI dùng PostgreSQL service riêng và `--require-database` để thiếu DB trở thành lỗi thay vì skip. Backend unit không cần DB.

Sau `make db build`, dùng `make web-test` để chạy web unit/integration rồi E2E. Helper dùng chung bước backup/migrate DB local và tạo/migrate `email_agentic_test` với backend test, tự cấp `TEST_DATABASE_URL` cho browser runner mà không in credential; không cần tự export DSN. Backup hoặc migration lỗi thì không chạy E2E. Lệnh npm E2E trực tiếp dành cho CI/DB test đã chuẩn bị và cần `TEST_DATABASE_URL` tường minh.

Web E2E cần Chromium: chạy `cd apps/web && npx --no-install playwright install --with-deps chromium` một lần. Runner quản lý API/Vite test; đóng các process mình khởi tạo khi kết thúc. CI cài browser từ dependency đã lock, không tải một bản Playwright khác qua `npx` tự động. Không upload browser trace/log chứa dữ liệu nhạy cảm.

## Bảo vệ main trên GitHub

[Cấu hình khai báo](../.github/main-protection.json) yêu cầu PR, check `verify` cập nhật với base, giải quyết conversation, linear history; cấm force push/xóa và áp dụng cả admin. Không yêu cầu approval thứ hai. Đây là cấu hình mong muốn, file tồn tại không chứng minh đã áp dụng trên remote.

Ngày 30/10/2026 đã áp dụng cấu hình này và đọc lại thành công từ GitHub. Checkout triển khai cũng đã bật pre-push guard. Máy clone khác vẫn cần chạy `make hooks-install`; trạng thái remote có thể thay đổi nên cần đọc lại bằng lệnh kiểm bên dưới khi audit.

[Cấu hình merge](../.github/repository-settings.json) chỉ cho squash merge, dùng tiêu đề PR làm commit title và tự xóa nhánh sau merge. Các thiết lập này cũng đã áp dụng ngày 30/10/2026, để convention tiêu đề PR được giữ khi vào `main`. Bản cấu hình trước thay đổi được lưu ở `.runtime/merge-settings-before-quality.json` trên máy thực hiện.

Quản trị viên review cấu hình rồi áp dụng bằng `gh` khi được phép:

```bash
gh api --method PUT repos/agent-bean/email_agentic/branches/main/protection --input .github/main-protection.json
gh api repos/agent-bean/email_agentic/branches/main/protection
gh api --method PATCH repos/agent-bean/email_agentic --input .github/repository-settings.json
```

Tên check `verify` là contract với bảo vệ nhánh; khi đổi job phải cập nhật cấu hình cùng lúc. Dùng squash merge để tiêu đề PR thành commit chính; không merge commit khi yêu cầu linear history. Bảo vệ nhánh không thay quản lý environment `vps` và secret. Thay workflow hoặc production entry point phải được review theo ranh giới quyền trong hướng dẫn vận hành.
