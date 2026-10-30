import { useI18n } from '../lib/i18n';
import { ApiError } from '../lib/api';

export function Status({ value }: { value: string }) {
  const { t } = useI18n();
  const labels: Record<string, string> = {
    queued: t('Đang chờ', 'Queued'),
    running: t('Đang chạy', 'Running'),
    awaiting_identity: t('Cần xác nhận doanh nghiệp', 'Company confirmation needed'),
    draft_ready: t('Có bản nháp', 'Draft ready'),
    failed: t('Có lỗi', 'Failed'),
    pending: t('Chờ duyệt', 'Awaiting approval'),
    approved: t('Đã duyệt', 'Approved'),
    rejected: t('Đã từ chối', 'Rejected'),
    expired: t('Hết hạn', 'Expired'),
    superseded: t('Đã có bản mới', 'Superseded'),
    partial: t('Thiếu một phần', 'Partial'),
    skipped: t('Bỏ qua', 'Skipped'),
    skipped_known_company: t('Đã có doanh nghiệp', 'Known company'),
    draft: t('Bản nháp', 'Draft'),
    succeeded: t('Thành công', 'Succeeded'),
    unknown: t('Cần đối chiếu', 'Needs verification'),
    blocked: t('Đã chặn', 'Blocked'),
    sent: t('Đã gửi', 'Sent'),
  };

  return (
    <span className={`status status-${value}`}>{labels[value] ?? value}</span>
  );
}
export function ErrorMessage({ error }: { error: unknown }) {
  const { t } = useI18n();
  return error ? (
    <p className="error" role="alert">
      {error instanceof ApiError && error.detail === null
        ? t(`Yêu cầu không thành công (${error.status}).`, `Request failed (${error.status}).`)
        : error instanceof Error ? error.message : t('Không tải được dữ liệu.', 'Unable to load data.')}
    </p>
  ) : null;
}
