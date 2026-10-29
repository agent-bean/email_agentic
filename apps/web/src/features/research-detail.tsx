import { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  api,
  post,
  type Detail,
  type Report,
  type ReportEdit,
} from '../lib/api';
import { ErrorMessage, Status } from '../components/status';
import {
  Attachments,
  MeetingSource,
  type MeetingEvent,
  type SourceMessage,
} from './inbox';

const qualityLabels: Record<string, string> = {
  cited_sources: 'Nguồn trích dẫn',
  source_target_met: 'Đủ số nguồn mục tiêu',
  elapsed_seconds: 'Thời gian xử lý chủ động (giây)',
  target_seconds: 'Mục tiêu thời gian (giây)',
  time_target_met: 'Xử lý chủ động trong mục tiêu',
  prd_elapsed_seconds: 'Thời gian nhận yêu cầu đến có nháp (giây)',
  prd_time_target_met: 'Đạt mục tiêu thời gian đầu-cuối',
  identity_wait_seconds: 'Thời gian chờ xác nhận đã loại trừ (giây)',
  timing_basis: 'Cách đo thời gian xử lý',
  prd_timing_basis: 'Cách đo thời gian đầu-cuối',
  markdown_ready_at: 'Thời điểm có nháp',
  factual_accuracy: 'Độ chính xác',
  completeness: 'Độ đầy đủ',
  readiness: 'Sẵn sàng sử dụng',
  branch_failures: 'Bước gặp lỗi',
  search_failures: 'Lỗi tìm kiếm',
  page_reads: 'Đọc trang web',
  citation_correction_attempted: 'Đã yêu cầu sửa link nguồn',
  human_edited: 'Đã chỉnh sửa',
  content_review: 'Kiểm tra nội dung',
  succeeded: 'Thành công',
  failed: 'Lỗi',
  not_selected: 'Không chọn đọc',
};
function qualityValue(value: unknown): string {
  if (value == null) return '—';
  if (typeof value === 'boolean') return value ? 'Có' : 'Không';
  if (Array.isArray(value))
    return value.map(qualityValue).join(', ') || 'Không có';
  if (typeof value === 'object')
    return Object.entries(value)
      .map(
        ([key, item]) => `${qualityLabels[key] ?? key}: ${qualityValue(item)}`,
      )
      .join(' · ');
  if (typeof value === 'number')
    return Number.isInteger(value) ? String(value) : value.toFixed(1);
  return (
    (
      {
        active_processing: 'Chỉ tính xử lý; không gồm queue và chờ xác nhận',
        received_to_markdown_excluding_identity_wait:
          'Gồm queue; loại thời gian chờ xác nhận đã ghi nhận',
        requires_review: 'Cần kiểm tra',
        required: 'Cần kiểm tra',
        not_evaluated: 'Chưa đánh giá',
      } as Record<string, string>
    )[String(value)] ?? String(value)
  );
}
const branchLabels: Record<string, string> = {
  company: 'Doanh nghiệp',
  email: 'Email',
  calendar: 'Lịch họp',
  web: 'Nguồn web',
  memory: 'Ngữ cảnh đã lưu',
  knowledge: 'Kho tri thức',
};
const dateTime = (value: string) => new Date(value).toLocaleString('vi-VN');

function ReportDownloads({ report, runId }: { report: Report; runId: string }) {
  const [file, setFile] = useState<{ id: string; filename: string } | null>(
    null,
  );
  const download = useMutation({
    mutationFn: (format: string) =>
      post<{ id: string; filename: string }>(
        `/runs/${runId}/reports/${report.id}/exports/${format}`,
      ),
    onSuccess: setFile,
  });
  return (
    <section className="panel">
      <h2>Tải báo cáo</h2>
      <p className="muted">
        Xuất đúng phiên bản v{report.version}. Tải file không duyệt hoặc gửi
        email.
      </p>
      <div className="actions">
        {(['pdf', 'docx', 'md'] as const).map((format) => (
          <button
            className="secondary"
            key={format}
            disabled={download.isPending}
            onClick={() => download.mutate(format)}
          >
            {download.isPending && download.variables === format
              ? 'Đang tạo file…'
              : format === 'docx'
                ? 'Word'
                : format.toUpperCase()}
          </button>
        ))}
      </div>
      <ErrorMessage error={download.error} />
      {file && (
        <a
          href={`/api/v1/files/${file.id}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          Tải {file.filename}
        </a>
      )}
    </section>
  );
}

function ReportEditor({
  report,
  runId,
  refresh,
  onDirty,
}: {
  report: Report;
  runId: string;
  refresh: () => void;
  onDirty: (dirty: boolean) => void;
}) {
  const initial: ReportEdit = {
    version: report.version,
    markdown: report.markdown,
    email_subject: report.email_subject,
    email_body: report.email_body,
    recipients: {
      to: report.recipients.to ?? [],
      cc: report.recipients.cc ?? [],
      bcc: report.recipients.bcc ?? [],
    },
    send_email: report.send_email,
    save_kb: report.save_kb,
    attachment_formats: report.artifacts.map(
      (a) => a.format as 'pdf' | 'docx' | 'md',
    ),
  };
  const [edit, setEdit] = useState(initial);
  const [recipientText, setRecipientText] = useState({
    to: (report.recipients.to ?? []).join(', '),
    cc: (report.recipients.cc ?? []).join(', '),
    bcc: (report.recipients.bcc ?? []).join(', '),
  });
  // Keep raw text while typing so commas and spaces are not removed mid-edit.
  const recipients = Object.fromEntries(
    Object.entries(recipientText).map(([kind, text]) => [
      kind,
      text
        .split(',')
        .map((address) => address.trim())
        .filter(Boolean),
    ]),
  );
  const editedReport = { ...edit, recipients };
  const dirty = JSON.stringify(initial) !== JSON.stringify(editedReport);
  useEffect(() => {
    onDirty(dirty);
    return () => onDirty(false);
  }, [dirty, onDirty]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    const guardNavigation = (event: MouseEvent) => {
      const link =
        event.target instanceof Element
          ? event.target.closest('a[href]')
          : null;
      if (
        !(link instanceof HTMLAnchorElement) ||
        link.target === '_blank' ||
        event.ctrlKey ||
        event.metaKey ||
        event.shiftKey ||
        event.altKey
      )
        return;
      const target = new URL(link.href);
      if (
        target.pathname === window.location.pathname &&
        target.search === window.location.search
      )
        return;
      if (
        !window.confirm(
          'Có thay đổi chưa lưu. Rời trang và bỏ các thay đổi này?',
        )
      ) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener('beforeunload', warn);
    document.addEventListener('click', guardNavigation, true);
    return () => {
      window.removeEventListener('beforeunload', warn);
      document.removeEventListener('click', guardNavigation, true);
    };
  }, [dirty]);
  const save = useMutation({
    mutationFn: () =>
      api(`/runs/${runId}/report`, {
        method: 'PUT',
        body: JSON.stringify(editedReport),
      }),
    onSuccess: refresh,
  });
  return (
    <details id="report-editor" className="panel editor">
      <summary>Chỉnh sửa nội dung & tùy chọn</summary>
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <p className="muted">
          Lưu sẽ tạo phiên bản mới và yêu cầu duyệt lại. Bản đang chỉnh sửa chưa
          được dùng để gửi.
        </p>
        <fieldset disabled={save.isPending}>
          <legend>Báo cáo · nội bộ</legend>
          <label>
            Nội dung Markdown
            <textarea
              rows={16}
              value={edit.markdown}
              onChange={(e) => setEdit({ ...edit, markdown: e.target.value })}
            />
          </label>
        </fieldset>
        <fieldset disabled={save.isPending}>
          <legend>Email nháp · gửi khách / đối tác</legend>
          <label>
            Tiêu đề
            <input
              value={edit.email_subject}
              onChange={(e) =>
                setEdit({ ...edit, email_subject: e.target.value })
              }
            />
          </label>
          <label>
            Nội dung email
            <textarea
              rows={9}
              value={edit.email_body}
              onChange={(e) => setEdit({ ...edit, email_body: e.target.value })}
            />
          </label>
        </fieldset>
        <fieldset disabled={save.isPending}>
          <legend>Người nhận</legend>
          <p className="muted">Phân cách các địa chỉ bằng dấu phẩy.</p>
          {(['to', 'cc', 'bcc'] as const).map((key) => (
            <label key={key}>
              {key.toUpperCase()}
              <input
                type="email"
                multiple
                value={recipientText[key]}
                onChange={(e) =>
                  setRecipientText({ ...recipientText, [key]: e.target.value })
                }
              />
            </label>
          ))}
        </fieldset>
        <fieldset disabled={save.isPending}>
          <legend>Sau khi duyệt</legend>
          <label className="check">
            <input
              type="checkbox"
              checked={edit.send_email}
              onChange={(e) =>
                setEdit({ ...edit, send_email: e.target.checked })
              }
            />
            Gửi email tới người nhận
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={edit.save_kb}
              onChange={(e) => setEdit({ ...edit, save_kb: e.target.checked })}
            />
            Lưu báo cáo vào kho tri thức
          </label>
        </fieldset>
        <fieldset disabled={save.isPending}>
          <legend>File đính kèm email</legend>
          <p className="notice">
            Báo cáo chứa phân tích nội bộ. Chỉ chọn đính kèm khi nội dung phù
            hợp với người nhận. Lưu phiên bản mới rồi mở file bên dưới để kiểm
            tra trước khi duyệt.
          </p>
          {(['pdf', 'docx', 'md'] as const).map((format) => (
            <label className="check" key={format}>
              <input
                type="checkbox"
                checked={(edit.attachment_formats ?? []).includes(format)}
                onChange={(e) =>
                  setEdit({
                    ...edit,
                    attachment_formats: e.target.checked
                      ? [...(edit.attachment_formats ?? []), format]
                      : edit.attachment_formats?.filter((f) => f !== format),
                  })
                }
              />
              {format === 'docx' ? 'Word' : format.toUpperCase()}
            </label>
          ))}
        </fieldset>
        <ErrorMessage error={save.error} />
        <div className="save-bar">
          <span className="muted" role="status">
            {dirty ? 'Có thay đổi chưa lưu' : 'Chưa có thay đổi'}
          </span>
          <button disabled={save.isPending || !dirty}>
            {save.isPending ? 'Đang lưu…' : 'Lưu phiên bản mới'}
          </button>
        </div>
      </form>
    </details>
  );
}

export function ResearchDetail() {
  const id = useParams().id!;
  const [params, setParams] = useSearchParams();
  const view = params.get('view') === 'email' ? 'email' : 'report';
  const [dirty, setDirty] = useState(false);
  const client = useQueryClient();
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ['run', id] });
    void client.invalidateQueries({ queryKey: ['runs'] });
  };
  const query = useQuery({
    queryKey: ['run', id],
    queryFn: () => api<Detail>(`/runs/${id}`),
    refetchInterval: 3000,
  });
  const confirm = useMutation({
    mutationFn: (identity: { company_name: string; domain: string }) =>
      post(`/runs/${id}/identity`, {
        version: query.data?.run.version,
        ...identity,
      }),
    onSuccess: refresh,
  });
  const decision = useMutation({
    mutationFn: ({
      approvalId,
      approve,
    }: {
      approvalId: string;
      approve: boolean;
    }) => post(`/approvals/${approvalId}/decision`, { approve }),
    onSuccess: refresh,
  });
  const exportDraft = useMutation({
    mutationFn: () =>
      post(`/runs/${id}/gmail-draft`, {
        version: query.data?.reports[0]?.version,
      }),
    onSuccess: refresh,
  });
  if (query.isPending)
    return (
      <section className="panel loading" role="status">
        Đang tải nghiên cứu…
      </section>
    );
  if (!query.data)
    return (
      <>
        <Link className="back-link" to="/">
          ← Nghiên cứu
        </Link>
        <ErrorMessage error={query.error} />
        <button className="secondary" onClick={() => void query.refetch()}>
          Thử lại
        </button>
      </>
    );
  const { run, reports, approvals, evidence, actions, branches, gmail_drafts } =
    query.data;
  const gmailSource = run.source_message as SourceMessage | null;
  const meeting = run.source_meeting as MeetingEvent | null;
  const report = run.history_purged_at ? undefined : reports[0];
  const emailAlreadySent = gmail_drafts.some(
    (d) => d.status === 'sent' && d.matches_current === true,
  );
  const currentDraft = gmail_drafts.find(
    (draft) =>
      draft.report_id === report?.id &&
      !['unknown', 'failed'].includes(String(draft.status)),
  );
  const hasUnknownDraft = gmail_drafts.some(
    (draft) => draft.report_id === report?.id && draft.status === 'unknown',
  );
  const hasMatchingDraft = gmail_drafts.some(
    (draft) => draft.matches_current === true && draft.status === 'succeeded',
  );
  let gmailDraftLabel = 'Lưu vào Gmail Drafts';
  if (emailAlreadySent) gmailDraftLabel = 'Email đã gửi';
  else if (exportDraft.isPending) gmailDraftLabel = 'Đang yêu cầu…';
  else if (hasUnknownDraft) gmailDraftLabel = 'Đối chiếu Gmail Draft';
  else if (hasMatchingDraft) gmailDraftLabel = 'Đã lưu Gmail Drafts';
  const approval = approvals.find((item) => item.report_id === report?.id);
  const approvalLabel = report?.send_email
    ? `Duyệt và gửi email v${report.version}`
    : report?.save_kb
      ? `Duyệt và lưu báo cáo v${report.version}`
      : `Duyệt nội dung v${report?.version}`;
  const expired = approval
    ? new Date(approval.expires_at).getTime() <= Date.now()
    : false;
  return (
    <>
      <Link className="back-link" to="/">
        ← Nghiên cứu
      </Link>
      <header>
        <div>
          <p className="eyebrow">NGHIÊN CỨU DOANH NGHIỆP</p>
          <h1>{run.company_name}</h1>
          <p className="muted">
            {run.domain} <span className="separator">/</span>{' '}
            {dateTime(run.created_at)}
          </p>
        </div>
        <Status value={run.status} />
      </header>
      <ErrorMessage
        error={
          query.error || confirm.error || decision.error || exportDraft.error
        }
      />
      {run.raw_purged_at && (
        <p className="notice">
          Dữ liệu nguồn đã hết thời hạn lưu.{' '}
          {run.history_purged_at
            ? 'Nội dung báo cáo và file cũng đã hết thời hạn lưu.'
            : 'Báo cáo được giữ đến hết thời hạn lưu báo cáo.'}
        </p>
      )}
      {meeting && (
        <section className="panel">
          <h2>Cuộc họp nguồn</h2>
          <MeetingSource event={meeting} />
          <p className="muted">
            Đây là lịch họp, không phải email gốc. Thay đổi lịch cần đồng bộ và
            xác nhận đề xuất mới.
          </p>
        </section>
      )}
      {run.status === 'awaiting_identity' && (
        <section className="panel notice">
          <h2>Xác nhận doanh nghiệp</h2>
          <p>
            Tên và domain đang là đề xuất. Kiểm tra nguồn gốc, sửa nếu cần rồi
            xác nhận để bắt đầu nghiên cứu.
          </p>
          <form
            key={run.version}
            className="form"
            onSubmit={(event) => {
              event.preventDefault();
              const values = new FormData(event.currentTarget);
              confirm.mutate({
                company_name: String(values.get('company_name')),
                domain: String(values.get('domain')),
              });
            }}
          >
            <label>
              Tên doanh nghiệp
              <input
                name="company_name"
                required
                minLength={2}
                maxLength={200}
                defaultValue={run.company_name}
              />
            </label>
            <label>
              Domain chính thức
              <input
                name="domain"
                required
                minLength={3}
                maxLength={253}
                defaultValue={run.domain}
              />
              <small>Chỉ nhập domain, không có https:// hoặc đường dẫn.</small>
            </label>
            <button disabled={confirm.isPending}>
              {confirm.isPending ? 'Đang xác nhận…' : 'Xác nhận và nghiên cứu'}
            </button>
          </form>
        </section>
      )}
      {run.error_code && (
        <p role="alert" className="error">
          Nghiên cứu gặp lỗi: {run.error_code}. Kết quả đã lưu vẫn được giữ.
        </p>
      )}
      <div className="detail-grid">
        <div className="detail-content">
          {report && (
            <ReportDownloads key={report.id} report={report} runId={run.id} />
          )}
          {report && (
            <nav className="view-switch" aria-label="Nội dung nghiên cứu">
              {(['report', 'email'] as const).map((tab) => (
                <button
                  key={tab}
                  className={view === tab ? 'selected' : ''}
                  aria-current={view === tab ? 'page' : undefined}
                  onClick={() =>
                    setParams((previous) => {
                      const next = new URLSearchParams(previous);
                      next.set('view', tab);
                      return next;
                    })
                  }
                >
                  {tab === 'report' ? 'Báo cáo' : 'Email nháp'}
                </button>
              ))}
              <a className="review-link" href="#review">
                {approvalLabel} ↓
              </a>
            </nav>
          )}
          {(view === 'email' || !report) && (
            <>
              {!meeting && (
                <section
                  className="panel reading-panel"
                  aria-labelledby="source-email-title"
                >
                  <p className="eyebrow">NỘI DUNG NGUỒN</p>
                  <h2 id="source-email-title">Email gốc</h2>
                  {run.source_email != null ? (
                    <>
                      <p className="surface-description">
                        {gmailSource
                          ? 'Email lấy trực tiếp từ Gmail; giữ nội dung và thread gốc.'
                          : 'Email được cung cấp khi tạo nghiên cứu, hiển thị nguyên văn.'}
                      </p>
                      <div className="preserve source-email-body">
                        {run.source_email}
                      </div>
                      {gmailSource && (
                        <>
                          <a
                            href={`https://mail.google.com/mail/u/?authuser=${encodeURIComponent(gmailSource.mailbox ?? '')}#all/${gmailSource.thread_id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            Mở thread Gmail
                          </a>
                          <Attachments items={gmailSource.attachments ?? []} />
                        </>
                      )}
                    </>
                  ) : (
                    <p className="muted">
                      Lượt này chưa có email nguồn riêng. Nội dung ở phần yêu
                      cầu nghiên cứu không được coi là email gốc.
                    </p>
                  )}
                </section>
              )}
              <section
                className="panel reading-panel"
                aria-labelledby="research-context-title"
              >
                <p className="eyebrow">HƯỚNG DẪN CHO TRỢ LÝ</p>
                <h2 id="research-context-title">Yêu cầu nghiên cứu</h2>
                {run.context ? (
                  <div className="preserve research-context-body">
                    {run.context}
                  </div>
                ) : (
                  <p className="muted">Chưa có yêu cầu bổ sung.</p>
                )}
              </section>
            </>
          )}

          {report ? (
            <>
              <section className="panel reading-panel">
                <div className="surface-heading">
                  <div>
                    <p className="eyebrow">
                      {view === 'report'
                        ? 'DÙNG NỘI BỘ'
                        : 'GỬI KHÁCH / ĐỐI TÁC'}
                    </p>
                    <h2>{view === 'report' ? 'Báo cáo' : 'Email nháp'}</h2>
                  </div>
                  <span className="version">v{report.version}</span>
                </div>
                {view === 'report' ? (
                  <>
                    <p className="surface-description">
                      Thông tin doanh nghiệp, nguồn tham khảo và phân tích để
                      chuẩn bị trao đổi.
                    </p>
                    <div className="markdown">
                      <Markdown
                        remarkPlugins={[remarkGfm]}
                        skipHtml
                        disallowedElements={['img']}
                        components={{
                          table: ({ children }) => (
                            <div
                              className="table-scroll"
                              role="region"
                              aria-label="Bảng báo cáo; cuộn ngang để xem thêm"
                              tabIndex={0}
                            >
                              <table>{children}</table>
                            </div>
                          ),
                        }}
                      >
                        {report.markdown}
                      </Markdown>
                    </div>
                  </>
                ) : (
                  <>
                    <p className="surface-description">
                      {gmailSource
                        ? 'Có thể lưu phiên bản này vào Gmail Drafts trong thread gốc. Thao tác này chưa gửi email.'
                        : 'Bản nháp đang lưu trong ứng dụng. Chọn email từ Gmail để tạo reply trong đúng thread.'}
                    </p>
                    {Number(run.config.prompt_version ?? 0) < 5 && (
                      <p className="notice inline-notice">
                        <strong>Email này được soạn theo hướng dẫn cũ;</strong>{' '}
                        cần soạn lại trước khi gửi khách.
                      </p>
                    )}
                    <dl className="email-addresses">
                      {(['to', 'cc', 'bcc'] as const).map((key) => (
                        <div key={key}>
                          <dt>{key.toUpperCase()}</dt>
                          <dd>
                            {(report.recipients[key] ?? []).join(', ') ||
                              (key === 'to' ? 'Chưa chọn người nhận' : '—')}
                          </dd>
                        </div>
                      ))}
                    </dl>
                    {gmailSource && (
                      <div className="panel">
                        <button
                          className="secondary"
                          disabled={
                            dirty ||
                            emailAlreadySent ||
                            !query.data.gmail_drafts_available ||
                            exportDraft.isPending ||
                            Boolean(currentDraft)
                          }
                          onClick={() => exportDraft.mutate()}
                        >
                          {gmailDraftLabel}
                        </button>
                        <p className="muted">
                          {!query.data.gmail_drafts_available &&
                            'Cần cấp bổ sung quyền Gmail để lưu draft. Xem trang Kết nối & vận hành. '}
                          Nội dung không đổi sẽ dùng lại draft đã xuất. Bản đã
                          xuất không tự cập nhật khi chỉnh sửa trong ứng dụng
                          hoặc Gmail. Gửi từ ứng dụng sẽ dùng draft khớp nội
                          dung đã duyệt; draft biến mất khỏi Gmail khi gửi thành
                          công.
                        </p>
                        {gmail_drafts.map((d) => (
                          <p key={String(d.id)}>
                            {d.report_id === report.id
                              ? `Phiên bản ${report.version}`
                              : 'Phiên bản trước'}
                            :{' '}
                            {d.status === 'pending' ? (
                              <span>Đang chờ tạo draft</span>
                            ) : (
                              <Status value={String(d.status)} />
                            )}
                            {Boolean(d.error_code) && (
                              <span> · {String(d.error_code)}</span>
                            )}
                          </p>
                        ))}
                      </div>
                    )}
                    <h3 className="email-subject">
                      {report.email_subject || 'Chưa có tiêu đề'}
                    </h3>
                    <div className="preserve email-body">
                      {report.email_body || 'Chưa có nội dung email.'}
                    </div>
                  </>
                )}
              </section>
              {!run.raw_purged_at && (
                <ReportEditor
                  key={report.id}
                  report={report}
                  runId={id}
                  refresh={refresh}
                  onDirty={setDirty}
                />
              )}
              <details className="panel source-panel">
                <summary>
                  Nguồn tham khảo{' '}
                  <span className="muted">({evidence.length})</span>
                </summary>
                {evidence.length ? (
                  <ol className="source-list">
                    {evidence.map((e, i) => (
                      <li key={i}>
                        <a
                          href={String(e.url)}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {String(e.title || e.url)}
                        </a>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="muted">Chưa có nguồn tham khảo.</p>
                )}
              </details>
            </>
          ) : (
            <section className="panel">
              <h2>Tiến độ nghiên cứu</h2>
              <p className="muted">
                {run.status === 'failed'
                  ? 'Chưa tạo được báo cáo. Xem lỗi và tiến độ từng bước bên cạnh.'
                  : 'Báo cáo và email nháp sẽ xuất hiện sau khi nghiên cứu hoàn tất.'}
              </p>
            </section>
          )}
        </div>
        <div className="detail-sidebar">
          {report && (
            <section id="review" className="panel review-panel">
              <p className="eyebrow">KIỂM TRA & DUYỆT</p>
              <div className="surface-heading">
                <h2>Phiên bản {report.version}</h2>
                {approval && (
                  <Status
                    value={
                      expired && approval.status === 'pending'
                        ? 'expired'
                        : approval.status
                    }
                  />
                )}
              </div>
              <p className="muted">
                Kiểm tra báo cáo, email, người nhận và các tùy chọn bên dưới
                trước khi duyệt.
              </p>
              {approval?.status === 'approved' && (
                <div className="notice inline-notice" role="status">
                  <strong>
                    {report.send_email
                      ? 'Đã duyệt yêu cầu gửi email.'
                      : 'Đã duyệt nội dung; không yêu cầu gửi email từ ứng dụng.'}
                  </strong>
                  {!report.send_email && (
                    <p>
                      Muốn gửi: mở Chỉnh sửa nội dung &amp; tùy chọn, bật Gửi
                      email, lưu phiên bản mới rồi chọn Duyệt và gửi email.
                      Gmail Drafts vẫn là bản nháp.
                    </p>
                  )}
                </div>
              )}
              <dl className="review-summary">
                <div>
                  <dt>Báo cáo & email</dt>
                  <dd>v{report.version}</dd>
                </div>
                {(['to', 'cc', 'bcc'] as const).map((key) => (
                  <div key={key}>
                    <dt>{key.toUpperCase()}</dt>
                    <dd>{(report.recipients[key] ?? []).join(', ') || '—'}</dd>
                  </div>
                ))}
                {report.artifacts.length > 0 && (
                  <div>
                    <dt>File sẽ đính kèm</dt>
                    <dd>
                      <p>
                        Kiểm tra từng file trước khi duyệt. Đây là toàn bộ báo
                        cáo, có thể chứa thông tin nội bộ.
                      </p>
                      {report.artifacts.map((file) => (
                        <p key={String(file.id)}>
                          <a
                            href={`/api/v1/files/${String(file.id)}?inline=true`}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {String(file.filename)}
                          </a>
                          <small> · SHA-256: {String(file.sha256)}</small>
                        </p>
                      ))}
                    </dd>
                  </div>
                )}
                <div>
                  <dt>Gửi email</dt>
                  <dd>{report.send_email ? 'Có' : 'Không gửi'}</dd>
                </div>
                <div>
                  <dt>Lưu kho tri thức</dt>
                  <dd>{report.save_kb ? 'Có' : 'Không lưu'}</dd>
                </div>
              </dl>
              {Number(run.config.prompt_version ?? 0) < 5 && (
                <p className="inline-notice notice">
                  Email này được soạn theo hướng dẫn cũ; cần soạn lại trước khi
                  gửi khách.
                </p>
              )}
              <p className="review-consequence">
                {report.send_email
                  ? 'Duyệt sẽ cho phép gửi email này tới người nhận đã chọn.'
                  : 'Đang tắt gửi email. Duyệt phiên bản này sẽ không gửi email.'}
              </p>
              {approval && (
                <>
                  <p className="muted meta">
                    Hết hạn: {dateTime(approval.expires_at)}
                  </p>
                  {expired && approval.status === 'pending' && (
                    <p className="inline-notice notice">
                      Quyền duyệt đã hết hạn. Chỉnh sửa và lưu phiên bản mới để
                      yêu cầu duyệt lại.
                    </p>
                  )}
                  {approval.status === 'pending' && !expired && (
                    <div className="actions review-actions">
                      <button
                        disabled={decision.isPending || dirty}
                        onClick={() =>
                          decision.mutate({
                            approvalId: approval.id,
                            approve: true,
                          })
                        }
                      >
                        {decision.isPending ? 'Đang xử lý…' : approvalLabel}
                      </button>
                      <button
                        className="secondary"
                        disabled={decision.isPending || dirty}
                        onClick={() =>
                          decision.mutate({
                            approvalId: approval.id,
                            approve: false,
                          })
                        }
                      >
                        Từ chối
                      </button>
                    </div>
                  )}
                </>
              )}
              {dirty && (
                <p role="status" className="inline-notice notice">
                  Lưu thay đổi trước khi duyệt phiên bản mới.
                </p>
              )}
              {actions.length > 0 && (
                <div className="action-results">
                  <h3>Kết quả gửi / lưu</h3>
                  {actions.map((action) => (
                    <p key={action.id}>
                      {action.kind}: <Status value={action.status} />
                    </p>
                  ))}
                </div>
              )}
            </section>
          )}
          <section className="panel">
            <h2>Tiến độ từng bước</h2>
            {branches.length === 0 ? (
              <p className="muted">Chưa có kết quả.</p>
            ) : (
              branches.map((b, i) => (
                <div className="row" key={i}>
                  <span>
                    {branchLabels[String(b.branch)] ?? String(b.branch)}
                  </span>
                  <Status
                    value={String(
                      (b.result as Record<string, unknown>)?.status ??
                        'pending',
                    )}
                  />
                </div>
              ))
            )}
          </section>
          {report && (
            <details className="panel quality-panel">
              <summary>Kiểm tra chất lượng</summary>
              <p className="muted">
                Cần kiểm tra dữ kiện và nguồn trước khi sử dụng.
              </p>
              <dl>
                {Object.entries(report.quality).map(([key, value]) => (
                  <div key={key}>
                    <dt>{qualityLabels[key] ?? key}</dt>
                    <dd>{qualityValue(value)}</dd>
                  </div>
                ))}
              </dl>
            </details>
          )}
        </div>
      </div>
    </>
  );
}
