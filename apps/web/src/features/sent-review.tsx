import { useI18n, type Translate } from '../lib/i18n';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { endpoints } from '../lib/api';
import type { components } from '../lib/api-schema';
import { ErrorMessage } from '../components/status';
import './sent-review.css';

type Row = components['schemas']['SentReviewRow'];

const getStatusLabels = (t: Translate): Record<string, string> => ({
  pending: t("Chờ gửi", "Waiting to send"), running: t("Đang xử lý", "Processing"), succeeded: t("Đã ghi nhận gửi", "Send recorded"),
  unknown: t("Cần kiểm tra", "Needs checking"), failed: t("Gửi gặp lỗi", "Send failed"), blocked: t("Đã chặn gửi", "Send blocked"),
});
const getVerificationLabels = (t: Translate): Record<string, string> => ({
  content_expired: t("Nội dung đã hết thời hạn lưu; không đủ dữ liệu để đối chiếu.", "The content retention period has expired; there is not enough data to compare."),
  matched: t("Email trong thư mục Đã gửi trên Gmail khớp phiên bản đã duyệt.", "The email in Gmail Sent matches the approved version."),
  mismatch: t("Email trên Gmail không khớp đầy đủ với phiên bản đã duyệt. Hãy kiểm tra trực tiếp trên Gmail.", "The email in Gmail does not fully match the approved version. Check it directly in Gmail."),
  not_found: t("Chưa tìm thấy trong thư mục Đã gửi. Điều này chưa chứng minh email chưa gửi. Không gửi lại khi kết quả chưa rõ.", "No email found in Sent. This does not prove it was not sent. Do not resend while the result is unclear."),
  multiple_matches: t("Có nhiều email tương ứng; hãy kiểm tra trực tiếp trên Gmail.", "Multiple matching emails found; check directly in Gmail."),
  too_large: t("Email quá lớn để kiểm tra đầy đủ; hãy kiểm tra trực tiếp trên Gmail.", "The email is too large to check fully; check directly in Gmail."),
});
const getFilters = (t: Translate) => [
  ['all', t("Tất cả", "All")], ['succeeded', t("Đã ghi nhận gửi", "Send recorded")],
  ['active', t("Đang xử lý", "Processing")], ['attention', t("Cần kiểm tra", "Needs checking")],
] as const;
const pageSize = 10;

function Receipt({ row }: { row: Row }) {
  const { t, locale } = useI18n();
  const statusLabels = getStatusLabels(t);
  const verificationLabels = getVerificationLabels(t);
  // A mutation runs only on a click, never on focus, reconnect or mounting.
  const check = useMutation({
    mutationFn: async () => ({
      result: await endpoints.verifySent(row.id),
      checkedAt: new Date().toISOString(),
    }),
    retry: false,
    networkMode: 'always',
  });
  return (
    <article className="record sent-receipt">
      <div className="sent-receipt-heading">
        <h2>{row.email_subject || t("Email không có tiêu đề", "Untitled email")}</h2>
        <span className={`status status-${row.status}`}>{statusLabels[row.status] ?? t("Trạng thái khác", "Other status")}</span>
      </div>
      <p className="sent-recipients">
        {Object.entries(row.recipients).filter(([, values]) => values?.length).map(([kind, values]) => (
          <span key={kind}><strong>{({ to: t("Đến", "To"), cc: 'Cc', bcc: 'Bcc' } as Record<string, string>)[kind] ?? kind}: </strong>{values?.join(', ')}</span>
        ))}
      </p>
      <p className="muted meta">{t("Yêu cầu lúc", "Requested at") + ' '}<time dateTime={row.created_at}>{new Date(row.created_at).toLocaleString(locale, { timeZone: 'Asia/Bangkok' })}</time>{' ' + t("(UTC+7) · Phiên bản", "(UTC+7) · Version") + ' '}{row.version}</p>
      <details className="sent-body">
        <summary>{t("Đọc email đã duyệt", "Read approved email")}</summary>
        <div className="sent-email-text">{row.email_body || t("Nội dung không còn được lưu.", "The content is no longer retained.")}</div>
      </details>
      <div className="actions">
        <button className="secondary" disabled={check.isPending} onClick={() => check.mutate()}>
          {check.isPending ? t("Đang kiểm tra…", "Checking…") : t("Kiểm tra trên Gmail", "Check in Gmail")}
        </button>
        <Link to={`/research/${row.run_id}?view=email`}>{t("Mở nghiên cứu (bản mới nhất)", "Open research (latest version)")}</Link>
      </div>
      <p className="muted meta">{t("Chỉ đọc dữ liệu Gmail khi bạn bấm kiểm tra. Không gửi lại email hoặc thay đổi biên nhận.", "Gmail is read only when you click check. This never resends email or changes the receipt.")}</p>
      <ErrorMessage error={check.error} />
      {check.isError && <p className="muted">{t("Chưa kiểm tra được Gmail. Bạn có thể bấm kiểm tra để thử lại.", "Could not check Gmail. Click check to try again.")}</p>}
      {check.data && !check.isPending && !check.isError && (
        <div className="sent-verification" role="status">
          <strong>{t("Kết quả kiểm tra Gmail", "Gmail check result")}</strong>
          <p>{verificationLabels[check.data.result.verification] ?? t("Chưa thể kết luận. Hãy kiểm tra trực tiếp trên Gmail.", "The result is inconclusive. Check directly in Gmail.")}</p>
          <p className="muted meta">{t("Kiểm tra lúc", "Checked at") + ' '}{new Date(check.data.checkedAt).toLocaleString(locale, { timeZone: 'Asia/Bangkok' })}{' ' + t("(UTC+7). Trạng thái ứng dụng không thay đổi.", "(UTC+7). The application status has not changed.")}</p>
        </div>
      )}
      <details className="sent-technical">
        <summary>{t("Thông tin kỹ thuật", "Technical details")}</summary>
        <p>{t("Mã yêu cầu:", "Request ID:") + ' '}{row.id}</p>
        <p>{t("Trạng thái hệ thống:", "System status:") + ' '}{row.status}</p>
        {row.provider_id && <p>{t("Mã Gmail đã lưu:", "Stored Gmail ID:") + ' '}{row.provider_id}</p>}
        {row.error_code && <p>{t("Mã lỗi:", "Error code:") + ' '}{row.error_code}</p>}
        {check.data?.result.provider_id && <p>{t("Mã Gmail khi kiểm tra:", "Checked Gmail ID:") + ' '}{check.data.result.provider_id}</p>}
      </details>
    </article>
  );
}

export function SentReview() {
  const { t } = useI18n();
  const filters = getFilters(t);
  const [params, setParams] = useSearchParams();
  const search = params.get('q') ?? '';
  const selected = params.get('status') ?? 'all';
  const status = filters.some(([value]) => value === selected) ? selected : 'all';
  const query = useQuery({ queryKey: ['sent-review'], queryFn: ({ signal }) => endpoints.sentReview(signal), refetchInterval: (query) => query.state.data?.some((row) => ['pending', 'running', 'unknown'].includes(row.status)) ? 5000 : 30000 });
  const rows = [...(query.data ?? [])].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  const matches = rows.filter((row) => {
    const searchable = [row.email_subject, ...Object.values(row.recipients).flat()].join(' ').toLocaleLowerCase('vi');
    const statusMatches = status === 'all' || row.status === status ||
      (status === 'active' && ['pending', 'running'].includes(row.status)) ||
      (status === 'attention' && !['pending', 'running', 'succeeded'].includes(row.status));
    return statusMatches && searchable.includes(search.trim().toLocaleLowerCase('vi'));
  });
  const pages = Math.max(1, Math.ceil(matches.length / pageSize));
  const requestedPage = Number(params.get('page') ?? 1);
  const page = Number.isInteger(requestedPage) ? Math.max(1, Math.min(pages, requestedPage)) : 1;
  function update(key: string, value: string) {
    setParams((current) => {
      const next = new URLSearchParams(current);
      if (!value || (key === 'status' && value === 'all') || (key === 'page' && value === '1')) next.delete(key);
      else next.set(key, value);
      if (key !== 'page') next.delete('page');
      return next;
    }, { replace: key === 'q' });
  }
  function clear() {
    setParams((current) => { const next = new URLSearchParams(current); ['q', 'status', 'page'].forEach((key) => next.delete(key)); return next; });
  }
  return (
    <>
      <header>
        <div>
          <p className="eyebrow">{t("EMAIL ĐÃ DUYỆT", "APPROVED EMAIL")}</p>
          <h1>{t("Lịch sử gửi email", "Email send history")}</h1>
          <p className="muted">{t("Các yêu cầu gửi và trạng thái ứng dụng ghi nhận, gồm cả yêu cầu đang xử lý hoặc gặp lỗi. Không phải mọi email trong danh sách đều đã gửi.", "Send requests and their recorded application status, including requests still processing or with errors. Not every email listed has been sent.")}</p>
        </div>
        <button className="secondary" onClick={() => void query.refetch()} disabled={query.isFetching}>{t("Tải lại danh sách", "Refresh list")}</button>
      </header>
      <section className="panel sent-history" aria-label={t("Các yêu cầu gửi email", "Email send requests")}>
        <div className="list-toolbar">
          <label className="search-field">{t("Tìm email", "Find email")}<input type="search" value={search} placeholder={t("Tiêu đề hoặc người nhận", "Subject or recipient")} onChange={(event) => update('q', event.target.value)} /></label>
          <div className="filter-tabs" aria-label={t("Lọc trạng thái gửi", "Filter send status")}>
            {filters.map(([value, label]) => <button key={value} className={status === value ? 'selected' : ''} aria-pressed={status === value} onClick={() => update('status', value)}>{label}</button>)}
          </div>
        </div>
        <ErrorMessage error={query.error} />
        {query.isError && <button className="secondary" disabled={query.isFetching} onClick={() => void query.refetch()}>{t("Thử lại", "Try again")}</button>}
        {query.isPending ? <p role="status">{t("Đang tải lịch sử gửi email…", "Loading email send history…")}</p> : query.data && <>
          <p className="muted list-count" role="status">{matches.length} / {rows.length}{' ' + t("yêu cầu · Trong tối đa 100 yêu cầu gần nhất", "requests · From up to 100 latest requests")}</p>
          {rows.length === 0 ? <div className="empty"><h2>{t("Chưa có yêu cầu gửi email", "No email send requests yet")}</h2><p>{t("Email xuất hiện tại đây sau khi bạn duyệt yêu cầu gửi trong nghiên cứu.", "Emails appear here after you approve a send request in research.")}</p><Link to="/">{t("Mở danh sách nghiên cứu", "Open research list")}</Link></div> : matches.length === 0 ? <div className="empty"><h2>{t("Không có email phù hợp", "No matching emails")}</h2><p>{t("Thử tiêu đề, người nhận hoặc trạng thái khác.", "Try another subject, recipient or status.")}</p><button className="secondary" onClick={clear}>{t("Xóa bộ lọc", "Clear filters")}</button></div> : <>
            {matches.slice((page - 1) * pageSize, page * pageSize).map((row) => <Receipt key={row.id} row={row} />)}
            {pages > 1 && <div className="actions sent-pagination" aria-label={t("Phân trang lịch sử", "History pagination")}><button className="secondary" disabled={page === 1} onClick={() => update('page', String(page - 1))}>{t("Trang trước", "Previous page")}</button><span>{t("Trang", "Page") + ' '}{page} / {pages}</span><button className="secondary" disabled={page === pages} onClick={() => update('page', String(page + 1))}>{t("Trang sau", "Next page")}</button></div>}
          </>}
        </>}
      </section>
    </>
  );
}
