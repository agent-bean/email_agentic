# Golden dataset và đánh giá

Golden là đáp án chuẩn do người review xác nhận, không phải email mẫu và không phải báo cáo do chính ứng dụng vừa tạo.

```mermaid
flowchart LR
    I["Email/lịch/PDF mẫu"] --> A["Ứng dụng"] --> R["Báo cáo thực tế"]
    S["Nguồn đối chiếu"] --> D["Golden nháp"] --> H["Người review"] --> G["Khóa phiên bản"]
    R --> E["Runner chấm độc lập"]
    G --> E
    E --> O["Kết quả và bằng chứng"]
```

## Đặt ở đâu?

| Đường dẫn | Vai trò |
|---|---|
| `evals/cases/` | Sáu ca TC-01–TC-06: yêu cầu và đầu vào, không chứa đáp án |
| `evals/fixtures/manifest.json` | Nguồn chuẩn của ca, phiên bản dataset và đường tới đầu vào riêng tư |
| `evals/golden/` | Dữ kiện chuẩn, file nguồn đối chiếu và bản khóa; dữ liệu riêng tư được Git ignore |
| `evals/runner/` | Xuất kết quả thật, kiểm đúng ca và gọi scoring |
| `evals/scoring/` | Chấm nguồn/thời gian tự động, gắn review dữ kiện/checklist |
| `evals/results/` | Bản xuất, review và kết quả; Git ignore |

Golden và runner không được đưa vào Docker image ứng dụng. Runtime không import evals và không nhận golden trong prompt, tool hoặc API. Email và lịch Google đã được chuẩn bị; không chạy seed lại.

Nguồn chuẩn của sáu ca là slide 5 trong `email_assistant.pptx`, không phải email đã được script đưa vào Gmail. File riêng tư `evals/fixtures/private/case-inputs.json` giữ tên liên hệ, công ty, câu email đúng đề, URL gốc và URL hiệu chỉnh đã chốt; kèm số slide và hash tài liệu. Các URL đã sửa vẫn được giữ, không cần trở về link lỗi. Không chèn địa chỉ email, ngày, subject, cảnh báo hoặc hướng dẫn nghiên cứu do bộ setup tạo vào email nguồn.

Lịch và attachment là phần bổ sung riêng trong `supplements`, có ghi nguồn và phần nào đề không cung cấp. Đề chỉ nhắc một hồ sơ PDF, không cung cấp nội dung file; PDF đã chuẩn bị không được gọi là hồ sơ chính thức hoặc email nguyên bản từ đề. Collector từ slide không nạp attachment này và không đưa nội dung PDF hoặc lịch vào body email. Luồng Gmail riêng có thể đọc PDF nhận kèm email. Lịch runtime vẫn được đọc qua Google Calendar. `bindings.json` và `.runtime/provenance/` giữ lịch sử dữ liệu Google để đối chiếu, không quyết định câu chữ của test case.

Dataset hiện tại là **version 2**. Các batch cũ trong `evals/results/` được giữ để truy vết và đánh dấu `excluded_from_current_evaluation`; không dùng chúng để nghiệm thu bộ ca này. Golden v1 không tự chuyển thành v2: cần đối chiếu và review lại trước khi tạo/khóa golden đúng phiên bản.

## Mỗi golden chứa gì?

Tên/domain đúng doanh nghiệp, mã ca/phiên bản, mốc thời gian và chế độ nguồn; danh sách dữ kiện bắt buộc có ID, mức quan trọng, file nguồn, hash và vị trí đối chiếu; checklist sẵn sàng; tên người review và trạng thái. Dữ kiện chưa có bằng chứng phải được bổ sung nguồn hoặc ghi yêu cầu xử lý thiếu dữ liệu trong checklist, không tự bịa đáp án.

Luồng là `draft → reviewed → locked`. CLI kiểm file nguồn tồn tại trong thư mục golden riêng tư, checksum và reviewer trước khi review/khóa. Khóa giúp phát hiện sửa ngoài ý muốn, không thay chữ ký/xác nhận người review. Khi nguồn hay đáp án thay đổi, tạo phiên bản mới và review lại.

Ví dụ từ root repo:

```sh
uv run --project apps/backend python -m evals.golden draft evals/golden/tc-01/v1.json --case TC-01 --company 'FPT Software' --domain fptsoftware.com --source-mode live
# Điền facts/checklist, lưu nguồn đối chiếu trong thư mục tc-01.
uv run --project apps/backend python -m evals.golden review evals/golden/tc-01/v1.json --reviewer 'Tên người review'
uv run --project apps/backend python -m evals.golden lock evals/golden/tc-01/v1.json
uv run --project apps/backend python -m evals.golden verify evals/golden/tc-01/v1.json
```

## Chấm thế nào?

Trước khi golden được khóa, có thể thu báo cáo live để review bằng [collector](../evals/runner/collect.py). Lệnh sau tạo nghiên cứu và xác nhận đúng danh tính ca đã chọn; không duyệt báo cáo, gửi mail hoặc phát hành KB:

```sh
uv run --project apps/backend python -m evals.runner.collect --case evals/cases/tc-01.json --output-directory evals/results/firecrawl-live --confirm-identities
```

Các ca có `fixture_status=requires_case_source` được collector nối với đầu vào chuẩn bằng case ID, dataset version và danh tính doanh nghiệp. `--case-inputs` chọn nguồn riêng tư, mặc định `evals/fixtures/private/case-inputs.json`. Nguồn thiếu/sai ca/sai phiên bản hoặc thiếu câu email sẽ dừng trước tạo run. Collector không đọc Gmail hay golden để lấy câu email và từ chối bộ `requires_fixture_binding` cũ.

Collector chuẩn bị toàn bộ ca trước khi tạo run, lưu riêng tư `tc-XX-source.json` gồm nội dung nguồn, metadata slide/URL và checksum, cùng `tc-XX-input.json` chứa đầu vào thực dùng để chạy/chấm. Email nguồn chỉ gồm người liên hệ/công ty, website đã hiệu chỉnh và câu email từ đề. `context` vẫn là yêu cầu nghiên cứu riêng; collector kiểm API trả đúng `source_email` đã gửi. Khi chấm, dùng file `tc-XX-input.json` đã xuất; runner từ chối ca chưa nối nguồn để tránh bỏ qua kiểm email. Không viết lại run/báo cáo cũ.

Lặp `--case` để chọn nhiều ca. Collector chạy tuần tự, lưu output riêng tư, checksum và trạng thái từng ca; manifest luôn ghi `human_review=pending`. Không đọc golden hoặc đưa đáp án vào ứng dụng. Đây là thu kết quả, chưa phải chấm nghiệm thu. Metadata đọc trang giúp review nguồn Firecrawl/fallback; đếm trang đọc được không chứng minh độ sâu hoặc nguồn độc lập. Ca cần PDF phải ghi thiếu nếu lượt chạy không có attachment thực tế; không đưa dữ kiện từ golden vào context để làm ca đạt.

Runner kiểm đúng ca, đầu vào, phiên bản và chế độ nguồn. Golden phải bao gồm các mục required_checks của ca trong checklist. Báo cáo export được hash; review phải gắn cả hash output lẫn hash golden. Review chứa `reviewer`, `reviewer_kind` (nếu có phải là `human` để đủ điều kiện), `output_sha256`, `golden_sha256`, `facts` (mỗi ID có verdict `correct_with_evidence` khi đúng và có bằng chứng), `readiness` (từng mục boolean), `distinct_sources_verified` và `news_freshness_passed`.

Scoring tự kiểm link Markdown và URL viết trực tiếp; số nguồn lấy từ report, còn URL ngoài evidence bị kiểm trong cả report và email. Evaluator không import implementation kiểm link của runtime. Không có human review hợp lệ thì các kiểm tra cấu trúc vẫn không tạo ra accuracy hoặc kết quả nghiệm thu.

```sh
uv run --project apps/backend python -m evals.runner.run --case evals/results/firecrawl-live/tc-01-input.json --golden evals/golden/tc-01/v2.json --api http://127.0.0.1:8000 --run-id RUN_ID --output evals/results/tc-01-output.json --result evals/results/tc-01-score.json
# Review bản output cố định, sau đó chấm lại file đó với --review.
uv run --project apps/backend python -m evals.runner.run --case evals/results/firecrawl-live/tc-01-input.json --golden evals/golden/tc-01/v2.json --output evals/results/tc-01-output.json --review evals/results/tc-01-review.json --result evals/results/tc-01-score.json
```

Không có review hợp lệ: `eligible=false`, không báo phần trăm đầy đủ. Điều kiện đạt: ≥98% dữ kiện chuẩn, mọi dữ kiện quan trọng đúng/có bằng chứng, checklist đạt, ≥12 nguồn thực sự được trích dẫn và đã kiểm tính độc lập, không URL ngoài evidence, tin tức được review đạt mốc 30 ngày, thời gian PRD trong ngưỡng config của lượt chạy. Scorer tự tính lại `prd_elapsed_seconds` từ `config.timing` phiên bản 1 (`received_at`, `identity_wait_started_at`, `identity_confirmed_at`) và `reports[0].quality.markdown_ready_at`, bao gồm queue/retry và chỉ trừ khoảng chờ xác nhận danh tính có đủ hai mốc. Mốc kết thúc được ghi sau khi Markdown đã lưu thành công. Các timestamp phải có múi giờ và đúng thứ tự; thiếu/sai mốc thì `prd_elapsed_seconds=null`, `time_target_met=null`, không thể đạt nghiệm thu dù `elapsed_seconds` chủ động dưới ngưỡng. Không hồi tố số đo cho export cũ. Đếm URL không chứng minh chất lượng hay nguồn độc lập. Review cần ghi nhận cả dữ kiện ngoài golden bị sai vào checklist chất lượng, tránh chỉ chấm phần hệ thống nhớ được.

Khi review độ sâu nghiên cứu, kiểm thêm: sản phẩm được gọi tên và giải thích công dụng; ví dụ triển khai/đối tác có bằng chứng; số liệu đúng pháp nhân và thời điểm; tin mới có ý nghĩa với cuộc trao đổi; cơ hội được giải thích từ nhu cầu và nguồn công khai; câu hỏi cụ thể để xác nhận phần chưa biết. Nếu thiếu nguồn, đánh giá cách báo cáo nêu khoảng trống thay vì yêu cầu model tự điền. Bổ sung dữ kiện/checklist vào golden còn nháp sau khi đối chiếu nguồn; không dùng chính báo cáo sinh ra làm đáp án hoặc tự khóa golden.

Review email riêng với report: email phải viết cho khách/đối tác, chọn reply khi có email khách hoặc email mở đầu khi chưa có. Không chấp nhận bản tóm tắt nghiên cứu gửi nội bộ, lộ đánh giá/thông tin riêng, hoặc tự bịa năng lực người gửi và cam kết. Các ca prompt cũ chưa chứng minh tiêu chí email mới; cần chạy lại bằng prompt hiện tại và review nội dung. Luồng Gmail hỗ trợ chọn input, đọc PDF có lớp text và xuất draft theo phiên bản vào thread gốc. Các ca từ slide vẫn dùng nguồn chuẩn riêng; không tự đổi sang email mới nhận hoặc tự khóa golden sau khi chạy Gmail.

Trạng thái review/khóa được lưu trong từng file golden riêng tư; xác nhận của người review và hash của đầu ra đã xem được lưu trong `evals/results/`. Không suy ra nghiệm thu hoặc điểm dữ kiện từ một xác nhận duyệt đầu ra tổng thể. Nguồn đối chiếu có thể là ghi chú hoặc trích đoạn tìm kiếm, không phải bản lưu đầy đủ của website; giữ rõ giới hạn truy cập trong bằng chứng review. Runner chấm hỗ trợ lượt live. Replay provider ở bước thu thập web và sinh báo cáo đã có bên dưới; scoring toàn workflow với golden `frozen` vẫn bị từ chối vì hai cassette chưa replay toàn bộ workflow và không thể dùng thời gian replay thay latency thật. Lượt live dùng kiểm nguồn/tin mới. Các lượt có `timing_basis=active_processing` loại thời gian chờ người và queue; scorer giữ `elapsed_seconds` này để chẩn đoán, không dùng cho gate PRD. `recent_dated_sources` chỉ đếm ngày do evidence cung cấp trong cửa sổ 30 ngày, chưa xác minh đó là ngày xuất bản bài thay vì header/trang tuyển dụng/provider metadata. Gate tin mới vẫn cần review người đã gắn hash qua `news_freshness_passed`; gate nguồn vẫn cần `distinct_sources_verified` để loại bài đăng lại/ngôn ngữ khác của cùng tài liệu. Ý nghĩa số đo xem [hướng dẫn ứng dụng](application-guide.md#trạng-thái-và-giới-hạn).

## Accepted regression references

Kết quả đã được owner duyệt có thể giữ làm mốc phát hiện regression. Đây là bản nội dung đã chấp nhận, không phải golden dữ kiện độc lập và không chứng minh mức accuracy hay điều kiện nghiệm thu sản phẩm. File riêng tư nằm dưới `evals/results/approved-regression/`, ngoài Git và image runtime.

[CLI regression](../evals/regression.py) tạo reference có checksum, từ chối ghi đè và chỉ nhận report đã duyệt. Chạy `python -m evals.regression --help` từ môi trường backend để xem lệnh `capture` và `check`. Sau khi xuất snapshot riêng tư, `check` đối chiếu đầu vào, người nhận, lựa chọn gửi/lưu, URL và nội dung với reference. Nội dung thay đổi phải được review lại; không tự cập nhật reference để làm kiểm tra pass. Các tình huống sửa nội dung/nguồn/action và checksum thuộc [kiểm tra regression](../apps/backend/tests/test_accepted_regression.py).

Reference không thay replay provider frozen: nó phát hiện thay đổi snapshot và bảo vệ nội dung đã duyệt, chưa chứng minh một lượt sinh mới có chất lượng tương đương. Kết quả luôn ghi `factual_accuracy` và `product_acceptance` là `not_evaluated`.


### Bản đối chiếu dễ review

[Review reader](../evals/review_bundle.py) tạo một file HTML riêng tư từ các golden nháp, kiểm checksum nguồn, hiển thị từng dữ kiện và mở nội dung nguồn tại chỗ. Chạy `python -m evals.review_bundle --help` trong môi trường backend; lặp `--golden` cho từng ca, `--output` phải là file mới. Reader không sửa golden, không gán reviewer và không khóa đáp án. Nguồn web cũ vẫn cần mở lại để xác nhận trước khi khóa.

Bộ nháp v2 dùng câu email gốc từ dataset 2; bỏ giờ họp và số liệu PDF cũ không gắn với đầu vào hiện tại, thay bằng checklist yêu cầu nguồn thực hoặc ghi thiếu; trạng thái duyệt và hash đã khóa xem trong từng file golden riêng tư. Bản đọc riêng tư hiện ở `evals/results/golden-review-v2/review-current.html`, ngoài Git và Docker. Không dùng bản này để tuyên bố đạt accuracy trước review/lock và chấm output tương ứng.

## Replay provider cho bước sinh báo cáo

[CLI replay](../evals/runner/replay.py) chạy lại `ReportGenerationAgent` thật với `run`, `evidence`, `branches` đã xuất và ngày `as_of` cố định. `record` gọi integration LLM/model đã cấu hình, lưu response có cấu trúc và usage thực trong cassette riêng tư (mode 0600); không ghi database ứng dụng. Không đọc golden, không dùng report cũ làm response provider, không gửi mail hoặc duyệt nội dung. Chọn timeout phù hợp với runtime qua config; lệnh không tự đổi model.

```sh
APP_ENV=local uv run --project apps/backend python -m evals.runner.replay record --input evals/results/BATCH/tc-01-output.json --cassette evals/results/PRIVATE/tc-01-cassette.json --output evals/results/PRIVATE/tc-01-record.json
uv run --project apps/backend python -m evals.runner.replay replay --input evals/results/BATCH/tc-01-output.json --cassette evals/results/PRIVATE/tc-01-cassette.json --output evals/results/PRIVATE/tc-01-replay.json
```

`replay` không tạo HTTP client/provider live; kiểm checksum cassette, hash toàn đầu vào, model/schema/system/payload của mỗi call, schema response, số call tiêu thụ và hash bản sinh lại. Thay email gốc, context, evidence, prompt hoặc schema sẽ dừng; không fallback mạng. Cassette chứa dữ liệu riêng tư, không có auth header/API key và phải ở thư mục bị ignore. Hash chỉ phát hiện thay đổi ngoài ý muốn, không phải chữ ký hay xác thực chống người sửa cả nội dung lẫn hash. Không ghi đè artifact hiện có.

Phạm vi là hồi quy lắp prompt, schema và đường sửa citation ở ranh giới structured LLM. Nguồn/branch là đầu vào đã đóng băng; không chạy lại web collection, tool harness, DB hoặc toàn workflow. Nó không đo độ ổn định stochastic của model, chất lượng nguồn live hay latency sản phẩm. Output ghi `factual_accuracy`, `product_acceptance`, `collection_replay` là `not_evaluated`. Export cũ không có cassette provider không thể hồi tố thành bằng chứng generation replay.

Review độc lập của agent có thể ghi `reviewer_kind=independent_agent`, hash output/golden, từng fact và vị trí đối chiếu; scorer giữ `eligible=false`, `completeness=null`. `missing` là thiếu dữ kiện trong báo cáo, `partially_present` là chưa đủ nội dung, không tự đồng nghĩa dữ kiện sai. Readiness chưa kiểm dùng `null` trong review độc lập; chỉ boolean true sau khi người review xác nhận mới đạt checklist. Không chuyển chấp thuận tổng thể của batch trước sang output mới.

### Replay thu thập web

[CLI web replay](../evals/runner/web_replay.py) gọi `WebResearchAgent` thật và các integration Tavily, DuckDuckGo, Firecrawl hiện có ở chế độ record. Chỉ danh tính công ty/domain từ effective case input đi vào truy vấn; không đọc golden, Gmail hoặc DB. Giới hạn `--read-pages` từ0đến12 (mặc định2) áp dụng riêng cho lần ghi, không sửa config production.

```sh
APP_ENV=local uv run --project apps/backend python -m evals.runner.web_replay record --input evals/results/BATCH/tc-02-input.json --cassette evals/results/PRIVATE/tc-02-web-cassette.json --output evals/results/PRIVATE/tc-02-web-record.json --read-pages 2
uv run --project apps/backend python -m evals.runner.web_replay replay --input evals/results/BATCH/tc-02-input.json --cassette evals/results/PRIVATE/tc-02-web-cassette.json --output evals/results/PRIVATE/tc-02-web-replay.json
```

Tape kiểm schema Search/Scrape và ToolContext web, khớp request cộng số lần xuất hiện thay vì thứ tự hoàn thành async; từ chối call thiếu/dư hoặc input/checksum thay đổi. Kết quả được copy trước khi agent bổ sung page_read. Lỗi ProviderFailure/ToolDenied được lưu và raise lại; cooldown/rate-limit được replay qua kết quả tool đã quan sát, không tính lại cooldown theo tốc độ replay. Đồng hồ quan sát riêng của agent cũng được lưu để tái tạo timeout argument và quyết định bỏ đọc khi hết deadline; không đổi đồng hồ event loop hoặc timer/retry provider. Replay không khởi tạo HTTP/DDG provider và không fallback. Hash branch phải khớp.

Phạm vi đã bao phủ logic thu thập của WebResearchAgent và, bằng CLI riêng phía trên, dựng/sửa báo cáo tại structured LLM. Hai cassette không tự chứng minh toàn workflow: chưa chạy SQL persistence, auth/rate limit/audit DB trong ToolExecutor, Google branches, checkpoint/approval hoặc HTTP parsing/retry nội bộ provider trong replay. Thời gian record/replay không thay số đo production42s; cả hai output giữ product_acceptance/factual_accuracy là not_evaluated.
