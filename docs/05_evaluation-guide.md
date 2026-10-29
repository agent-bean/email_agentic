# Đánh giá chất lượng

[PRD](02_product-requirements.md) sở hữu sáu case, ngưỡng và quyết định nghiệm thu. Golden là đáp án có bằng chứng được người review xác nhận; email mẫu hoặc báo cáo vừa sinh không phải golden. Đáp án nằm ngoài runtime/image, không được đưa vào prompt, tool hoặc API để làm bài đạt.

## Chọn đúng nguồn và phép kiểm

| Việc cần làm | Owner thực thi |
| --- | --- |
| Chọn case và dữ liệu đầu vào | [Cases](../evals/cases/), [fixtures](../evals/fixtures/) |
| Tạo, review, khóa/verify golden | [Golden CLI](../evals/golden.py) |
| Thu lượt live chưa duyệt | [Collector](../evals/runner/collect.py) |
| Xuất/chấm output gắn với review | [Runner](../evals/runner/run.py), [scoring](../evals/scoring/) |
| Đọc nguồn và dữ kiện để review | [Review reader](../evals/review_bundle.py) |
| Bảo vệ snapshot đã được duyệt | [Regression CLI](../evals/regression.py) |
| Record/replay sinh báo cáo | [Generation replay](../evals/runner/replay.py) |
| Record/replay thu thập web | [Web replay](../evals/runner/web_replay.py) |

Xem `--help` của module tương ứng trong môi trường backend để lấy tham số hiện hành. Golden nằm trong `evals/golden/`, output/cassette/review trong `evals/results/`, đầu vào riêng tại `evals/fixtures/private/`; đều ngoài Git. Không ghi đè artifact để làm kiểm tra pass. Không chạy lại Google seed đã chuẩn bị.

## Quy trình review và nghiệm thu

1. Chốt input đúng case/phiên bản và danh tính doanh nghiệp. Nguồn chuẩn là slide đề gốc; email đã seed trong Gmail không quyết định câu chữ của case. URL đã hiệu chỉnh vẫn được giữ. Không thêm subject, ngày họp hay hướng dẫn setup vào email nguồn.
2. Tách lịch/PDF bổ sung khỏi email nguồn và ghi provenance. Đề không cung cấp bytes hồ sơ PDF; tài liệu tự chuẩn bị không được gọi là hồ sơ chính thức của doanh nghiệp. Ca thiếu attachment thực phải ghi thiếu, không bù bằng golden trong context.
3. Chuẩn bị facts/checklist từ nguồn độc lập, lưu vị trí/checksum và review trước khi khóa. Dữ kiện chưa có nguồn phải bổ sung bằng chứng hoặc yêu cầu xử lý thiếu dữ liệu; không bịa đáp án. Đổi nguồn/đáp án cần phiên bản mới và review lại.
4. Thu output live theo input đã chốt. Xác nhận danh tính khi chạy collector không phải duyệt báo cáo/gửi mail/KB. Collector không đọc golden; dùng effective input đã xuất khi chấm, không tự thay bằng email mới nhận.
5. Review đúng output cố định và đúng golden, gắn checksum cả hai. Người review kiểm từng dữ kiện, mức quan trọng, checklist sẵn sàng, nguồn độc lập và ngày tin tức; review sai phiên bản không chuyển sang lượt mới.
6. Chấm bằng scorer. Khi thiếu human review hợp lệ, chỉ báo kiểm tra cấu trúc, không tự báo accuracy/completeness hoặc nghiệm thu. Review độc lập của agent hỗ trợ đối chiếu nhưng không thay xác nhận của người dùng.

Checksum phát hiện sửa ngoài ý muốn, không là chữ ký chống người sửa cả nội dung/hash. Reviewer/khóa không được tự gán chỉ vì batch cũ từng được chấp thuận. Dataset/output cũ không tự trở thành phiên bản mới; lịch sử batch ở `plans/reports/` và artifact riêng.

## Phán đoán chất lượng

Đếm URL không chứng minh nguồn độc lập hoặc đúng dữ kiện. Citation thuộc evidence chưa đủ: nguồn phải hỗ trợ đúng pháp nhân, thời điểm và nội dung. Ngày header/cập nhật/truy xuất không tự chứng minh ngày xuất bản. Tin ngoài cửa sổ giữ ở bối cảnh, không tính đạt độ mới. Dữ kiện ngoài golden bị sai vẫn phải ghi vào review, không chỉ chấm phần hệ thống nhớ được.

Review độ sâu qua sản phẩm có tên/công dụng, triển khai/đối tác có bằng chứng, số liệu đúng phạm vi, tin mới liên quan cuộc trao đổi và câu hỏi cụ thể để xác nhận phần chưa biết. Thiếu nguồn thì đánh giá cách nêu khoảng trống, không yêu cầu model điền cho đủ số. Nhận định nhu cầu phải dẫn căn cứ và giữ nhãn phân tích.

Review email riêng: nội dung viết cho khách/đối tác, reply khi có email khách hoặc mở đầu khi chưa có; không lộ nghiên cứu nội bộ/thông tin riêng hay bịa năng lực/cam kết. Nội dung được duyệt để gửi không tự chứng minh đáp ứng toàn bộ PRD.

Mục tiêu thời gian và timeout có ý nghĩa khác nhau. Phép đo PRD gồm queue/retry đến khi Markdown lưu xong; thời gian chờ xác nhận danh tính chỉ được tách khi có đủ mốc hợp lệ. Thời gian xử lý chủ động không thay số đo đầu-cuối. Output cũ thiếu mốc không được hồi tố hoặc tuyên bố đạt. Công thức/field thuộc [scoring](../evals/scoring/); không đổi ngưỡng sau chạy để làm đạt.

## Giới hạn từng loại hồi quy

Reference báo cáo đã duyệt bảo vệ snapshot input/người nhận/lựa chọn/nội dung. Nó không chứng minh lượt sinh mới có cùng chất lượng; thay nội dung cần review lại, không tự cập nhật reference.

Generation replay kiểm đường dựng prompt/schema/sửa citation với response provider đã ghi và input đóng băng. Web replay kiểm logic thu thập với response search/scrape đã ghi. Không lấy report cũ giả làm response provider, không fallback mạng khi replay sai input/cassette. Record gọi provider thật, có chi phí và cần phạm vi dữ liệu được phép.

Hai phạm vi replay không tự chứng minh toàn workflow: SQL, auth/audit DB, Google, checkpoint/approval và transport/retry provider cần kiểm riêng. Cassette chứa dữ liệu riêng tư; không chứa credential. Replay không đo stochastic stability, nguồn live, latency production hoặc factual accuracy. Bằng chứng thực thi thuộc `plans/reports/`, không phải tài liệu evergreen.
