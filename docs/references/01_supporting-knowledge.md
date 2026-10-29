# Tham khảo giáo trình và code mẫu

Tài liệu gốc được tìm qua danh mục riêng `docs/references/02_private-source-catalog.md` trên máy quản trị. Giáo trình/code mẫu không phải thiết kế đã chọn hoặc bằng chứng hệ thống chạy thành công. [PRD](../02_product-requirements.md) sở hữu phạm vi; [kiến trúc](../04_architecture-and-safety.md) sở hữu quyết định hiện hành.

## Chỉ đọc khi cần đối chiếu nguồn gốc

Đề Email Assistant là nguồn yêu cầu. Các bài Tool Harness, Orchestration, Security/Governance, Evaluation và AgentOps giúp hiểu cơ sở thiết kế; ví dụ Drive, Fulfillment, coding agent và chăm sóc khách hàng không mở rộng nghiệp vụ Email Assistant.

Code mẫu có tool loop, Gmail/Calendar, RAG và telemetry để tham khảo, nhưng không tự đáp ứng bảy vai trò, phê duyệt đúng phiên bản hoặc gửi chống trùng. Gmail send trực tiếp trong mẫu phải được đặt sau quyền/duyệt; đổi prompt không tạo ranh giới an toàn. Tool tạo/sửa/xóa lịch hoặc trạng thái email trong mẫu không phải quyền mặc định của dự án.

Registry mẫu có TODO về schema/auth/scopes/rate/audit hoặc chỉ lưu user/rate/audit trong RAM; không dùng làm bằng chứng về bảo vệ production. Một số mẫu dùng CRM mô phỏng. Cache/BM25 trong RAM không tự chứng minh memory bền vững sau restart. Ví dụ GraphRAG, vector DB, MCP/A2A và agent manager là lựa chọn tham khảo, chưa phải yêu cầu.

Stack monitoring mẫu bật anonymous Admin không phù hợp demo công khai; port/model/giá trong slide không là cấu hình hiện hành. Không giải nén nguyên bộ mẫu vào repo: một số archive có dotenv/token, không đọc hoặc tái sử dụng credential từ đó. Inventory, nhận xét từng file và kết quả kiểm tra tĩnh thuộc báo cáo nghiên cứu, không phải hướng dẫn vận hành.

## Các bẫy khi dùng công thức đánh giá

- Hit@K kiểm có ít nhất một kết quả đúng; Recall@K tính tỷ lệ mục đúng tìm thấy trên toàn bộ mục liên quan. Chúng chỉ trùng khi mỗi query có một mục đúng.
- Slide Evaluation S23 có phép chia `4 / 6 = 0.5` sai; kết quả đúng khoảng 0.667. Nhãn Context Relevance/Recall và Precision/Recall có chỗ lẫn; đối chiếu mẫu số trước áp dụng.
- Exact Match, BLEU/ROUGE và trùng từ không tự đo tính đúng của briefing mở. LLM-as-a-judge không thay nguồn/đáp án độc lập và human review đã chốt.
- Benchmark tổng quát và pass@k không thay sáu case nghiệp vụ hoặc tỷ lệ email xử lý đúng.

Khi quyết định phụ thuộc thư viện/API, đọc tài liệu hiện hành và kiểm bằng source/test của dự án. Giáo trình chưa được thực thi đầy đủ và không chứng nhận dependency, auth hoặc chất lượng tích hợp. Quy trình chấm của dự án nằm tại [đánh giá](../05_evaluation-guide.md).
