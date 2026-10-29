const labels: Record<string, string> = {
  queued: 'Đang chờ', running: 'Đang chạy', awaiting_identity: 'Cần xác nhận doanh nghiệp',
  draft_ready: 'Có bản nháp', failed: 'Có lỗi', pending: 'Chờ duyệt', approved: 'Đã duyệt',
  rejected: 'Đã từ chối', expired: 'Hết hạn', superseded: 'Đã có bản mới',
  partial: 'Thiếu một phần', skipped: 'Bỏ qua', skipped_known_company: 'Đã có doanh nghiệp', draft: 'Bản nháp', succeeded: 'Thành công', unknown: 'Cần đối chiếu', blocked: 'Đã chặn',
};
export function Status({ value }: { value: string }) {
  return <span className={`status status-${value}`}>{labels[value] ?? value}</span>;
}
export function ErrorMessage({ error }: { error: unknown }) {
  return error ? <p className="error" role="alert">{error instanceof Error ? error.message : 'Không tải được dữ liệu.'}</p> : null;
}
