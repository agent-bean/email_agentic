import { Link } from "react-router-dom";

export function ResearchProgress({
  status,
  hasReport,
  approvalStatus,
  expired,
  hasUnknownAction,
}: {
  status: string;
  hasReport: boolean;
  approvalStatus?: string;
  expired: boolean;
  hasUnknownAction: boolean;
}) {
  const approved = approvalStatus === "approved";
  const needsRevision =
    approvalStatus === "rejected" || approvalStatus === "superseded";
  function getMessage() {
    if (hasUnknownAction)
      return {
        title: "Cần đối chiếu kết quả gửi",
        description:
          "Chưa xác định được email đã gửi hay chưa. Đối chiếu Sent trước khi quyết định gửi lại.",
      };
    if (status === "awaiting_identity")
      return {
        title: "Bước tiếp theo: xác nhận đúng doanh nghiệp",
        description:
          "Kiểm tra tên và domain bên dưới. Xác nhận này chỉ bắt đầu nghiên cứu.",
      };
    if (status === "failed")
      return {
        title: "Nghiên cứu cần được kiểm tra",
        description:
          "Xem lỗi và tiến độ từng bước. Các kết quả đã lưu vẫn được giữ.",
      };
    if (approved)
      return {
        title: "Đã duyệt. Kiểm tra kết quả gửi / lưu.",
        description:
          "Phê duyệt và gửi thành công là hai trạng thái khác nhau. Xem kết quả thực hiện trong gói duyệt.",
      };
    if (needsRevision)
      return {
        title: "Cần lưu phiên bản mới trước khi duyệt",
        description:
          "Gói duyệt này đã bị từ chối hoặc được thay thế. Kiểm tra nội dung và lưu phiên bản mới nếu muốn tiếp tục.",
      };
    if (expired)
      return {
        title: "Quyền duyệt đã hết hạn",
        description: "Chỉnh sửa và lưu một phiên bản mới để yêu cầu duyệt lại.",
      };
    if (hasReport)
      return {
        title: "Bước tiếp theo: kiểm tra báo cáo và email nháp",
        description:
          "Báo cáo dành cho nội bộ. Email nháp dành cho khách. Kiểm tra cả hai trước khi duyệt.",
      };
    return {
      title: "Trợ lý đang chuẩn bị nghiên cứu",
      description:
          "Tiến độ tự cập nhật. Báo cáo và email nháp sẽ xuất hiện khi hoàn tất.",
    };
  }
  const { title, description } = getMessage();
  return (
    <section className="progress-workbench" aria-label="Tiến trình nghiên cứu">
      <ol className="progress-steps">
        <li className={hasReport ? "complete" : "current"}>
          <span>01</span>Nghiên cứu
        </li>
        <li className={hasReport ? (approved ? "complete" : "current") : ""}>
          <span>02</span>Kiểm tra & duyệt
        </li>
        <li className={approved ? "current" : ""}>
          <span>03</span>Kết quả gửi / lưu
        </li>
      </ol>
      <div className="next-action">
        <div>
          <strong>{title}</strong>
          <p>{description}</p>
        </div>
        {hasUnknownAction ? (
          <Link className="button secondary" to="/sent-review">
            Đối chiếu Sent
          </Link>
        ) : hasReport ? (
          <a className="button secondary" href="#review">
            Xem gói duyệt ↓
          </a>
        ) : null}
      </div>
    </section>
  );
}
