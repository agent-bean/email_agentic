import { Link } from "react-router-dom";
import { useI18n } from "../lib/i18n";

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
  const { t } = useI18n();
  const approved = approvalStatus === "approved";
  const needsRevision =
    approvalStatus === "rejected" || approvalStatus === "superseded";
  function getMessage() {
    if (hasUnknownAction)
      return {
        title: t('Cần kiểm tra email đã gửi', 'Check whether the email was sent'),
        description:
          t('Chưa xác định được email đã gửi hay chưa. Kiểm tra lịch sử gửi trước khi quyết định gửi lại.', 'It is not yet clear whether the email was sent. Check the sending history before deciding to resend.'),
      };
    if (status === "awaiting_identity")
      return {
        title: t('Bước tiếp theo: xác nhận đúng doanh nghiệp', 'Next: confirm the company'),
        description:
          t('Kiểm tra tên và domain bên dưới. Xác nhận này chỉ bắt đầu nghiên cứu.', 'Check the name and domain below. This confirmation only starts research.'),
      };
    if (status === "failed")
      return {
        title: t('Nghiên cứu cần được kiểm tra', 'Research needs attention'),
        description:
          t('Xem lỗi và tiến độ từng bước. Các kết quả đã lưu vẫn được giữ.', 'Review errors and progress for each step. Saved results are preserved.'),
      };
    if (approved)
      return {
        title: t('Đã duyệt. Kiểm tra kết quả gửi / lưu.', 'Approved. Check sending / saving results.'),
        description:
          t('Phê duyệt và gửi thành công là hai trạng thái khác nhau. Xem kết quả thực hiện trong gói duyệt.', 'Approval and successful sending are separate states. Check execution results in the approval package.'),
      };
    if (needsRevision)
      return {
        title: t('Cần lưu phiên bản mới trước khi duyệt', 'Save a new version before approval'),
        description:
          t('Gói duyệt này đã bị từ chối hoặc được thay thế. Kiểm tra nội dung và lưu phiên bản mới nếu muốn tiếp tục.', 'This approval package was rejected or superseded. Review the content and save a new version to continue.'),
      };
    if (expired)
      return {
        title: t('Quyền duyệt đã hết hạn', 'Approval has expired'),
        description: t('Chỉnh sửa và lưu một phiên bản mới để yêu cầu duyệt lại.', 'Edit and save a new version to request approval again.'),
      };
    if (hasReport)
      return {
        title: t('Bước tiếp theo: kiểm tra báo cáo và email nháp', 'Next: review the report and email draft'),
        description:
          t('Báo cáo dành cho nội bộ. Email nháp dành cho khách. Kiểm tra cả hai trước khi duyệt.', 'The report is for internal use. The email draft is for the customer. Review both before approval.'),
      };
    return {
      title: t('Trợ lý đang chuẩn bị nghiên cứu', 'The assistant is preparing research'),
      description:
          t('Tiến độ tự cập nhật. Báo cáo và email nháp sẽ xuất hiện khi hoàn tất.', 'Progress updates automatically. The report and email draft will appear when ready.'),
    };
  }
  const { title, description } = getMessage();
  return (
    <section className="progress-workbench" aria-label={t('Tiến trình nghiên cứu', 'Research progress')}>
      <ol className="progress-steps">
        <li className={hasReport ? "complete" : "current"}>
          <span>01</span>{t('Nghiên cứu', 'Research')}
        </li>
        <li className={hasReport ? (approved ? "complete" : "current") : ""}>
          <span>02</span>{t('Kiểm tra & duyệt', 'Review & approve')}
        </li>
        <li className={approved ? "current" : ""}>
          <span>03</span>{t('Kết quả gửi / lưu', 'Sending / saving results')}
        </li>
      </ol>
      <div className="next-action">
        <div>
          <strong>{title}</strong>
          <p>{description}</p>
        </div>
        {hasUnknownAction ? (
          <Link className="button secondary" to="/sent-review">
            {t('Kiểm tra lịch sử gửi', 'Check sending history')}
          </Link>
        ) : hasReport ? (
          <a className="button secondary" href="#review">
            {t('Xem gói duyệt ↓', 'View approval package ↓')}
          </a>
        ) : null}
      </div>
    </section>
  );
}
