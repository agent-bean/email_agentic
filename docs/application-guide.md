# Email Assistant: kiến trúc và chạy local

Đây là nền tảng ứng dụng, chưa phải bản hoàn tất các yêu cầu sản phẩm. Điểm bắt đầu cho đánh giá chất lượng là [hướng dẫn golden và eval](evaluation-guide.md); CI hiện có được mô tả tại [hướng dẫn CI](ci-guide.md).

## Kiến trúc đã chọn

Một repo chứa React web và FastAPI backend. Web và backend có image riêng để cập nhật/rollback giao diện độc lập; API và worker dùng chung image backend vì dùng cùng code và dependencies. Web chuyển tiếp API cùng origin để giữ một đường đăng nhập. Worker chạy workflow LangGraph cố định. Bảy vai trò được giữ trong cùng backend, không dùng agent lead hoặc bảy dịch vụ riêng.

| Điểm vào | Trách nhiệm |
|---|---|
| [Web](../apps/web/src/app/app.tsx) | Giao diện theo nghiệp vụ, xem/sửa và duyệt |
| [Web server](../apps/web/nginx.conf) | React, SPA fallback và proxy API cùng origin |
| [API](../apps/backend/src/email_agentic/main.py) | HTTP và xác thực |
| [Worker](../apps/backend/src/email_agentic/worker.py) | Nhận việc, resume và lịch quét |
| [Workflow](../apps/backend/src/email_agentic/workflows/research.py) | Điều phối các bước và chờ người xác nhận |
| [Bootstrap](../apps/backend/src/email_agentic/bootstrap.py) | Nối domains, agents, tools và integrations |
| [Tool harness](../apps/backend/src/email_agentic/tools/harness.py) | Kiểm schema, danh tính, quyền, giới hạn và audit trước thực thi |
| [Migration](../apps/backend/src/email_agentic/platform/migrate.py) | Backup và áp dụng schema có checksum |
| [Compose](../infra/compose.yaml) | API, worker, PostgreSQL và monitoring |

`domains/` sở hữu quy tắc nghiệp vụ và giao dịch. `agents/` xử lý từng vai trò, `tools/` sở hữu thao tác có quyền hạn, `integrations/` gọi provider; `runtime/` và `platform/` giữ hạ tầng thực thi. PostgreSQL được dùng cho dữ liệu, jobs và checkpoint trong các bảng riêng để tránh thêm broker khi chưa có nhu cầu.

Xác nhận đúng doanh nghiệp khác với duyệt phát hành. Bản báo cáo, body email, người nhận và lựa chọn phát hành phải được duyệt đúng phiên bản; sửa thì duyệt lại. Email có kết quả gửi chưa rõ phải đối chiếu trước khi gửi lại. Golden dùng chấm độc lập, không được đưa cho runtime hoặc model làm đáp án.

Báo cáo và email dùng cách diễn đạt nghiệp vụ bình thường; nhãn nguồn gốc bộ kiểm thử chỉ giữ trong dữ liệu nội bộ. Nội dung từ email, lịch và hồ sơ được dẫn theo nguồn cung cấp, phân biệt với dữ kiện công khai đã xác minh. Quy tắc tạo nội dung nằm tại [ReportGenerationAgent](../apps/backend/src/email_agentic/agents/report_generation.py).

Nghiên cứu web chia thành năm chủ đề: pháp nhân/quy mô, sản phẩm/công nghệ, triển khai/khách hàng, đối tác và tin mới. [WebResearchAgent](../apps/backend/src/email_agentic/agents/web_research.py) chỉ đưa tên/domain đã xác nhận vào tìm kiếm công khai; nội dung email/lịch được dùng khi tổng hợp. Lượt mới tìm cả năm chủ đề qua Tavily và DuckDuckGo, tối đa ba tác vụ tìm kiếm đồng thời. [Tavily](../apps/backend/src/email_agentic/integrations/tavily.py) dùng advanced; [DuckDuckGo](../apps/backend/src/email_agentic/integrations/duckduckgo.py) dùng thư viện DDGS với backend cố định `duckduckgo`, tối đa tám kết quả/truy vấn, một request hoạt động mỗi tiến trình và timeout HTTP 10 giây. Tin tức dùng bộ lọc tháng; ngày không rõ vẫn để trống. DDGS chạy trong thread để không chặn event loop; khi hủy workflow phải đợi request hữu hạn đang chạy kết thúc trước khi giải phóng slot. Không chuyển sang search engine khác. `DUCKDUCKGO_ENABLED=true` mặc định, không cần API key; đặt false để tắt. Một nguồn lỗi vẫn giữ kết quả nguồn còn lại, lỗi theo provider nằm trong `research_coverage` và `search_provider_failures`. DuckDuckGo có thể chặn/rate-limit; trạng thái cấu hình không phải cam kết kết nối thành công.

Sau tìm kiếm, [Firecrawl integration](../apps/backend/src/email_agentic/integrations/firecrawl.py) đọc nội dung chính của các trang được chọn luân phiên theo thứ hạng trong từng chủ đề, khử URL trùng/fragment. `FIRECRAWL_API_KEY` đi qua Compose đến settings; `FIRECRAWL_MAX_PAGES` mặc định 12, nhận 0–30, đặt 0 để tắt. Thiếu key vẫn dùng các trích đoạn từ search provider. Hai trang được đọc đồng thời, mỗi request tối đa 15 giây trong ngân sách đọc tổng 45 giây; deadline toàn workflow vẫn áp dụng. Không dùng crawler đệ quy, phiên đăng nhập hoặc parser PDF/ảnh trong bước này.

Trang lỗi hoặc không được chọn vẫn giữ nội dung từ search provider. Hai nguồn tìm kiếm dùng chung giới hạn đọc Firecrawl, không nhân đôi số trang; URL trùng được gộp trước đọc và khi lưu evidence. Metadata `page_read` trong kết quả nhánh và `page_reads` trong quality phân biệt thành công/thất bại/chưa chọn; đọc thành công không có nghĩa nguồn đã được kiểm chứng độc lập. Báo cáo nhận phần nội dung có giới hạn cùng metadata để nêu khoảng trống. Công cụ `web.scrape` dùng chung schema/quyền/audit của tool harness; chỉ chuyển URL công khai sang Firecrawl, không chuyển email/lịch hay key trong payload tổng hợp. Lượt mới lưu workflow 4, prompt 7, cờ DuckDuckGo và giới hạn đọc, không lưu credential; lượt cũ thiếu cờ không tự thêm DuckDuckGo. Tắt cấu hình hiện tại cũng chặn DuckDuckGo cho lượt đang resume. Lượt cũ không tự thêm bước Firecrawl.

Validator kiểm URL trong cả báo cáo và email, gồm link Markdown và URL viết trực tiếp. Nếu link nằm ngoài evidence, hệ thống yêu cầu model sửa đúng một lượt trong deadline hiện tại; còn sai thì dừng, không lưu báo cáo. Quality ghi `citation_correction_attempted`. Kiểm URL chỉ xác nhận nguồn thuộc tập đã thu, chưa xác nhận nguồn hỗ trợ đúng dữ kiện; phần đó cần review. Request Firecrawl tắt parser PDF/ảnh, nhưng provider vẫn có thể trả nội dung đã cache của URL PDF công khai; điều này không thay bước đọc attachment email.

Báo cáo cần có ví dụ cụ thể có nguồn, phân biệt công ty con với tập đoàn, giải thích liên hệ với nhu cầu và đề xuất câu hỏi cùng bước tiếp theo. Chỉ suy ra vai trò mua/bán từ bối cảnh rõ ràng; không mặc định công ty đang nghiên cứu là bên bán giải pháp cho người dùng. Liên hệ nghiệp vụ phải được ghi là phân tích, không biến thành nhu cầu đã xác nhận. Mục tin gần đây giới hạn 30 ngày; bối cảnh cũ ghi riêng kèm ngày. Báo cáo phải nêu rõ phần thiếu bằng chứng hoặc không thu thập được. Trích đoạn có giới hạn nên báo cáo chưa thay việc đọc toàn văn nguồn. Tìm kiếm advanced và đọc trang có thể tăng chi phí và thời gian; mục tiêu 42 giây vẫn được đo riêng với deadline.

UI tách **Báo cáo** dùng nội bộ và **Email nháp** gửi khách/đối tác. Từ prompt 6, `source_email` chứa email khách được cung cấp riêng, còn `context` là yêu cầu nghiên cứu. Model dùng email nguồn để soạn reply; khi không có email khách thì soạn email mở đầu theo chủ đề, không bịa một email nguồn. Dữ liệu context-only cũ vẫn được xử lý nhưng không được trình bày như email lấy từ Gmail. Email hướng tới 80–140 từ, gọi người nhận trực tiếp và đề nghị bước tiếp theo; không kể lại thông tin công ty khách, chèn link nghiên cứu, chép report, đánh giá nội bộ, lỗi nguồn, thông tin riêng của bên thứ ba hoặc tự bịa năng lực/người gửi/cam kết. Đây là hướng dẫn model, chưa phải bảo đảm kiểm duyệt nội dung tự động. Bản cũ không tự viết lại. Nháp đang lưu trong app, chưa đồng bộ Gmail Drafts hoặc gắn reply vào thread Gmail; gửi vẫn cần chọn người nhận và duyệt.

Trang nghiên cứu giữ lựa chọn qua `?view=report` hoặc `?view=email`. Phần review email tách ba vùng: **Email gốc**, **Yêu cầu nghiên cứu**, **Email nháp**. Khi tạo nghiên cứu, dán nguyên văn tiêu đề/nội dung email vào ô Email gốc, nhập hướng dẫn riêng vào Yêu cầu nghiên cứu. `source_email` được lưu và trả nguyên chuỗi, tối đa 30.000 ký tự; không lọc nhãn, bỏ dòng, trim hoặc phân tích lại nội dung khi xem nguồn. Đây là bản người dùng cung cấp, chưa lấy trực tiếp từ Gmail. Run cũ có trường này bằng null; UI báo chưa có nguồn riêng, không tự tách email từ context hoặc gán mail theo domain. Màn hình dữ liệu nguồn cũng giữ nguyên nội dung; các nhãn nghiệp vụ được xử lý lúc chuẩn bị đầu vào, không qua bộ lọc hiển thị. Báo cáo và email nháp giữ đúng phiên bản đã lưu; chỉnh sửa phải tạo phiên bản mới và duyệt riêng. Khung duyệt hiển thị phiên bản, To/Cc/Bcc và lựa chọn gửi/lưu. Khi có chỉnh sửa chưa lưu, UI tắt nút duyệt và nhắc khi rời trang qua liên kết hoặc đóng tab; backend vẫn kiểm phiên bản khi lưu/duyệt. UI hỗ trợ desktop, tablet và điện thoại.

[LLM integration](../apps/backend/src/email_agentic/integrations/llm.py) yêu cầu JSON schema. Khi provider trả nội dung hoàn chỉnh nhưng sai JSON/fields, integration yêu cầu sửa định dạng đúng một lần, chỉ chuyển đầu ra lỗi và schema vào lượt sửa, không gửi lại toàn bộ context. Hai lần dùng chung ngân sách request; deadline workflow vẫn áp dụng. Kết quả vẫn phải qua schema và kiểm nguồn; lỗi tiếp tục thì dừng. Token provider công bố được lưu kể cả lần tạo nội dung sai định dạng, không log nội dung hoặc credential.

## Chạy local

Cần Make, Docker Compose, uv và Node.js/npm. Xem build/runtime tại [web Dockerfile](../apps/web/Dockerfile), [backend Dockerfile](../apps/backend/Dockerfile), [backend manifest](../apps/backend/pyproject.toml) và [web manifest](../apps/web/package.json).

Tạo `.env` theo [.env.example](../.env.example) nếu chưa có. Điền chủ hộp thư, mật khẩu PostgreSQL/Grafana, gateway/model và Tavily; đặt token OAuth runtime tại đường dẫn cấu hình. Không ghi đè cấu hình đã có. Model chỉ cần khai báo qua `LLM_MODEL`.

[Makefile](../Makefile) gọi helper [app-control.py](../scripts/app-control.py) để thao tác stack local; không SSH hoặc triển khai VPS. Xem các lệnh tại `make help`. Chạy tuần tự từ root repo:

```sh
make setup
make check
make db
make build
make migrate
make up
```

App ở `http://127.0.0.1:8000`, Grafana ở `http://127.0.0.1:3000`. Port app thuộc web; API chỉ ở mạng Compose. `make up` mặc định origin local; có thể override bằng biến shell `APP_ORIGIN`, không sửa `.env`. Local auth chỉ dành cho truy cập local, tin địa chỉ web cố định trong [local Compose](../infra/compose.local.yaml); không tin header giả địa chỉ client. Production cần Cloudflare Access bảo vệ toàn bộ hostname theo [config/auth](../apps/backend/src/email_agentic/platform/auth.py); chưa có bước deploy ứng dụng trong helper.

Web và backend phải giữ tương thích hợp đồng API khi cập nhật riêng. Nếu API dừng, giao diện vẫn tải được nhưng các thao tác cần API sẽ lỗi. Health của web chỉ xác nhận web server; `/health/ready` kiểm tra API/DB qua proxy. Metrics backend chỉ dành cho mạng nội bộ.

Token Google chỉ được mount read-only cho runtime. Container hiện chạy UID 1000; file phải đọc được bởi UID này, không đổi secret thành file cho mọi người đọc. Token seed không được mount. Không chạy seed lại trên bộ dữ liệu đã chuẩn bị.

Migration phải chạy tường minh trước khi mở API/worker. Dump trước thay đổi nằm trong volume `app-data`, tại `/data/backups`; lỗi backup sẽ dừng migration. Không xóa volume để xử lý một lỗi khởi động thông thường.

## Kiểm tra và dừng

```sh
make test
make lint
make web-build
make status
make down
```

`test` cần PostgreSQL và image đã dựng, tạo backup trước khi ghi dữ liệu và dùng DB riêng `email_agentic_test`. Lệnh này chỉ dành cho stack thử local. `down` dừng container và giữ volume/backup.

Hợp đồng HTTP do [OpenAPI/Pydantic](../apps/backend/src/email_agentic/api/routes.py) sở hữu; kiểu web được sinh tại [api-schema.ts](../apps/web/src/lib/api-schema.ts). Khi thay API, xuất OpenAPI ra `.runtime/openapi.json`, rồi dùng script `api:generate` trong web manifest. Chạy Vite riêng cần đặt origin backend theo origin Vite.

## Trạng thái và giới hạn

Đã kiểm chứng queue/checkpoint qua restart, version approval/outbox, lease, auth/Origin, golden hash và build. Luồng local với Google/Tavily và gateway thật đã đi qua tạo nghiên cứu, xác nhận doanh nghiệp, tạo nháp, sửa và duyệt phiên bản mới với gửi email/lưu KB tắt. Đây là kiểm tra một ca, chưa phải nghiệm thu sáu ca hoặc chất lượng nội dung.

`REPORT_TARGET_SECONDS` là mục tiêu chất lượng theo từng lượt; `RESEARCH_TIMEOUT_SECONDS` là ngân sách xử lý. Tăng ngân sách không đồng nghĩa đạt mục tiêu. Số đo hiện còn tính thời gian chờ xác nhận của người dùng.

Request LLM dùng ngân sách cấu hình tại [LLM integration](../apps/backend/src/email_agentic/integrations/llm.py), thay vì bị timeout mặc định của HTTP client cắt ngắn. Khi cấu hình riêng có ngân sách quá thấp, có thể chạy local bằng `RESEARCH_TIMEOUT_SECONDS=180 make up`; override không được lưu vào file cấu hình. Lỗi mạng từ provider vẫn có thể xảy ra và không chứng minh model thiếu hỗ trợ schema.

Chưa hoàn tất: tự kích hoạt nghiên cứu từ email/lịch, Gmail history cursor, PDF đầu vào, xuất PDF/Word và attachment bất biến, UI đối chiếu Sent, cleanup/retention, backup định kỳ và trace xuyên tiến trình. Scheduler mặc định tắt; dữ liệu đồng bộ chưa tự trở thành nghiên cứu. Golden còn nháp và frozen replay chưa triển khai; xem [hướng dẫn eval](evaluation-guide.md).

Tài liệu sản phẩm/kiến trúc được theo dõi trong Git. Checklist vận hành riêng và danh mục đường dẫn tài liệu gốc trên máy, cấu hình thật, golden và kết quả thử được giữ ngoài Git theo [.gitignore](../.gitignore).
