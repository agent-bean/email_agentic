import { useI18n, type Translate } from '../lib/i18n';
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, post, type Detail, type Report } from "../lib/api";
import { ErrorMessage, Status } from "../components/status";
import { ReportEditor } from "./report-editor";
import { ResearchProgress } from "../components/research-progress";
import {
  Attachments,
  MeetingSource,
  type MeetingEvent,
  type SourceMessage,
} from "./inbox";

const getQualityLabels = (t: Translate): Record<string, string> => ({
  cited_sources: t("Nguồn trích dẫn", "Cited sources"),
  source_target_met: t("Đủ số nguồn mục tiêu", "Source target met"),
  elapsed_seconds: t("Thời gian xử lý chủ động (giây)", "Active processing time (seconds)"),
  target_seconds: t("Mục tiêu thời gian (giây)", "Time target (seconds)"),
  time_target_met: t("Xử lý chủ động trong mục tiêu", "Active processing target met"),
  prd_elapsed_seconds: t("Thời gian nhận yêu cầu đến có nháp (giây)", "Request-to-draft time (seconds)"),
  prd_time_target_met: t("Đạt mục tiêu thời gian đầu-cuối", "End-to-end time target met"),
  identity_wait_seconds: t("Thời gian chờ xác nhận đã loại trừ (giây)", "Excluded identity confirmation wait (seconds)"),
  timing_basis: t("Cách đo thời gian xử lý", "Processing time measurement"),
  prd_timing_basis: t("Cách đo thời gian đầu-cuối", "End-to-end time measurement"),
  markdown_ready_at: t("Thời điểm có nháp", "Draft ready at"),
  factual_accuracy: t("Độ chính xác", "Factual accuracy"),
  completeness: t("Độ đầy đủ", "Completeness"),
  readiness: t("Sẵn sàng sử dụng", "Readiness"),
  branch_failures: t("Bước gặp lỗi", "Failed steps"),
  search_failures: t("Lỗi tìm kiếm", "Search failures"),
  page_reads: t("Đọc trang web", "Page reads"),
  citation_correction_attempted: t("Đã yêu cầu sửa link nguồn", "Citation correction requested"),
  human_edited: t("Đã chỉnh sửa", "Edited"),
  content_review: t("Kiểm tra nội dung", "Content review"),
  succeeded: t("Thành công", "Succeeded"),
  failed: t("Lỗi", "Failed"),
  not_selected: t("Không chọn đọc", "Not selected for reading"),
});
function qualityValue(value: unknown, t: Translate, locale: string): string {
  const qualityLabels = getQualityLabels(t);
  if (value == null) return "—";
  if (typeof value === "boolean") return value ? t("Có", "Yes") : t("Không", "No");
  if (Array.isArray(value))
    return value.map((item) => qualityValue(item, t, locale)).join(", ") || t("Không có", "None");
  if (typeof value === "object")
    return Object.entries(value)
      .map(
        ([key, item]) => `${qualityLabels[key] ?? key}: ${qualityValue(item, t, locale)}`,
      )
      .join(" · ");
  if (typeof value === "number")
    return value.toLocaleString(locale, { maximumFractionDigits: 1 });
  return (
    (
      {
        active_processing: t("Chỉ tính xử lý; không gồm queue và chờ xác nhận", "Processing only; excludes queue and identity confirmation wait"),
        received_to_markdown_excluding_identity_wait:
          t("Gồm queue; loại thời gian chờ xác nhận đã ghi nhận", "Includes queue; excludes recorded identity confirmation wait"),
        requires_review: t("Cần kiểm tra", "Needs checking"),
        required: t("Cần kiểm tra", "Needs checking"),
        not_evaluated: t("Chưa đánh giá", "Not evaluated"),
      } as Record<string, string>
    )[String(value)] ?? String(value)
  );
}
const getBranchLabels = (t: Translate): Record<string, string> => ({
  company: t("Doanh nghiệp", "Company"),
  email: "Email",
  calendar: t("Lịch họp", "Calendar"),
  web: t("Nguồn web", "Web sources"),
  memory: t("Ngữ cảnh đã lưu", "Saved context"),
  knowledge: t("Kho tri thức", "Knowledge"),
});

function ReportDownloads({ report, runId }: { report: Report; runId: string }) {
  const { t } = useI18n();
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
      <h2>{t("Tải báo cáo", "Download report")}</h2>
      <p className="muted">{' ' + t("Xuất đúng phiên bản v", "Export version v")}{report.version}{t(". Tải file không duyệt hoặc gửi email.", ". Downloading does not approve or send email.") + ' '}</p>
      <div className="actions">
        {(["pdf", "docx", "md"] as const).map((format) => (
          <button
            className="secondary"
            key={format}
            disabled={download.isPending}
            onClick={() => download.mutate(format)}
          >
            {download.isPending && download.variables === format
              ? t("Đang tạo file…", "Creating file…")
              : format === "docx"
                ? "Word"
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
        >{' ' + t("Tải", "Download") + ' '}{file.filename}
        </a>
      )}
    </section>
  );
}

export function ResearchDetail() {
  const { t, locale } = useI18n();
  const qualityLabels = getQualityLabels(t);
  const branchLabels = getBranchLabels(t);
  const dateTime = (value: string) => new Date(value).toLocaleString(locale, { timeZone: "Asia/Bangkok" }) + " (UTC+7)";
  const id = useParams().id!;
  const [params, setParams] = useSearchParams();
  const view = params.get("view") === "email" ? "email" : "report";
  const [dirty, setDirty] = useState(false);
  const client = useQueryClient();
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["run", id] });
    void client.invalidateQueries({ queryKey: ["runs"] });
  };
  const query = useQuery({
    queryKey: ["run", id],
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
      <section className="panel loading" role="status">{' ' + t("Đang tải nghiên cứu…", "Loading research…") + ' '}</section>
    );
  if (!query.data)
    return (
      <>
        <Link className="back-link" to="/">{' ' + t("← Nghiên cứu", "← Research") + ' '}</Link>
        <ErrorMessage error={query.error} />
        <button className="secondary" onClick={() => void query.refetch()}>{' ' + t("Thử lại", "Try again") + ' '}</button>
      </>
    );
  const { run, reports, approvals, evidence, actions, branches, gmail_drafts } =
    query.data;
  const gmailSource = run.source_message as SourceMessage | null;
  const meeting = run.source_meeting as MeetingEvent | null;
  const report = run.history_purged_at ? undefined : reports[0];
  const emailAlreadySent = gmail_drafts.some(
    (d) => d.status === "sent" && d.matches_current === true,
  );
  const currentDraft = gmail_drafts.find(
    (draft) =>
      draft.report_id === report?.id &&
      !["unknown", "failed"].includes(String(draft.status)),
  );
  const hasUnknownDraft = gmail_drafts.some(
    (draft) => draft.report_id === report?.id && draft.status === "unknown",
  );
  const hasMatchingDraft = gmail_drafts.some(
    (draft) => draft.matches_current === true && draft.status === "succeeded",
  );
  let gmailDraftLabel = t("Lưu vào Gmail Drafts", "Save to Gmail Drafts");
  if (emailAlreadySent) gmailDraftLabel = t("Email đã gửi", "Email sent");
  else if (exportDraft.isPending) gmailDraftLabel = t("Đang yêu cầu…", "Requesting…");
  else if (hasUnknownDraft) gmailDraftLabel = t("Đối chiếu Gmail Draft", "Check Gmail draft");
  else if (hasMatchingDraft) gmailDraftLabel = t("Đã lưu Gmail Drafts", "Saved to Gmail Drafts");
  const approval = approvals.find((item) => item.report_id === report?.id);
  const approvalLabel = report?.send_email
    ? t(`Duyệt và gửi email v${report.version}`, `Approve and send email v${report.version}`)
    : report?.save_kb
      ? t(`Duyệt và lưu báo cáo v${report.version}`, `Approve and save report v${report.version}`)
      : t(`Duyệt nội dung v${report?.version}`, `Approve content v${report?.version}`);
  const expired = approval
    ? new Date(approval.expires_at).getTime() <= Date.now()
    : false;
  return (
    <>
      <Link className="back-link" to="/">{' ' + t("← Nghiên cứu", "← Research") + ' '}</Link>
      <header>
        <div>
          <p className="eyebrow">{t("NGHIÊN CỨU DOANH NGHIỆP", "COMPANY RESEARCH")}</p>
          <h1>{run.company_name}</h1>
          <p className="muted">
            {run.domain} <span className="separator">/</span>{" "}
            {dateTime(run.created_at)}
          </p>
        </div>
        <Status value={run.status} />
      </header>
      {!run.history_purged_at && (
        <ResearchProgress
          status={run.status}
          hasReport={Boolean(report)}
          approvalStatus={approval?.status}
          expired={expired && approval?.status === "pending"}
          hasUnknownAction={actions.some(
            (action) => action.status === "unknown",
          )}
        />
      )}
      <ErrorMessage
        error={
          query.error || confirm.error || decision.error || exportDraft.error
        }
      />
      {run.raw_purged_at && (
        <p className="notice">{' ' + t("Dữ liệu nguồn đã hết thời hạn lưu.", "The source data retention period has expired.")}{" "}
          {run.history_purged_at
            ? t("Nội dung báo cáo và file cũng đã hết thời hạn lưu.", "The report and file retention periods have also expired.")
            : t("Báo cáo được giữ đến hết thời hạn lưu báo cáo.", "Reports are kept until the report retention period expires.")}
        </p>
      )}
      {meeting && (
        <section className="panel">
          <h2>{t("Cuộc họp nguồn", "Source meeting")}</h2>
          <MeetingSource event={meeting} />
          <p className="muted">{' ' + t("Đây là lịch họp, không phải email gốc. Thay đổi lịch cần đồng bộ và xác nhận đề xuất mới.", "This is a calendar event, not a source email. Schedule changes require syncing and confirming a new proposal.") + ' '}</p>
        </section>
      )}
      {run.status === "awaiting_identity" && (
        <section className="panel notice">
          <h2>{t("Xác nhận doanh nghiệp", "Confirm company")}</h2>
          <p>{' ' + t("Tên và domain đang là đề xuất. Kiểm tra nguồn gốc, sửa nếu cần rồi xác nhận để bắt đầu nghiên cứu.", "The name and domain are suggestions. Check the source, edit if needed, then confirm to start research.") + ' '}</p>
          <form
            key={run.version}
            className="form"
            onSubmit={(event) => {
              event.preventDefault();
              const values = new FormData(event.currentTarget);
              confirm.mutate({
                company_name: String(values.get("company_name")),
                domain: String(values.get("domain")),
              });
            }}
          >
            <label>{' ' + t("Tên doanh nghiệp", "Company name") + ' '}<input
                name="company_name"
                required
                minLength={2}
                maxLength={200}
                defaultValue={run.company_name}
              />
            </label>
            <label>{' ' + t("Domain chính thức", "Official domain") + ' '}<input
                name="domain"
                required
                minLength={3}
                maxLength={253}
                defaultValue={run.domain}
              />
              <small>{t("Chỉ nhập domain, không có https:// hoặc đường dẫn.", "Enter only the domain, without https:// or a path.")}</small>
            </label>
            <button disabled={confirm.isPending}>
              {confirm.isPending ? t("Đang xác nhận…", "Confirming…") : t("Xác nhận và nghiên cứu", "Confirm and research")}
            </button>
          </form>
        </section>
      )}
      {run.error_code && (
        <p role="alert" className="error">{' ' + t("Nghiên cứu gặp lỗi:", "Research failed:") + ' '}{run.error_code}{t(". Kết quả đã lưu vẫn được giữ.", ". Saved results are retained.") + ' '}</p>
      )}
      <div className="detail-grid">
        <div className="detail-content">
          {report && (
            <nav className="view-switch" aria-label={t("Nội dung nghiên cứu", "Research content")}>
              {(["report", "email"] as const).map((tab) => (
                <button
                  key={tab}
                  className={view === tab ? "selected" : ""}
                  aria-current={view === tab ? "page" : undefined}
                  onClick={() =>
                    setParams((previous) => {
                      const next = new URLSearchParams(previous);
                      next.set("view", tab);
                      return next;
                    })
                  }
                >
                  <span>
                    {tab === "report" ? t("Báo cáo", "Report") : t("Email nháp", "Email draft")}
                    <small>
                      {tab === "report" ? t("Dùng nội bộ", "Internal use") : t("Gửi khách / đối tác", "For customers / partners")}
                    </small>
                  </span>
                </button>
              ))}
              <a className="review-link" href="#review">
                {approvalLabel} ↓
              </a>
            </nav>
          )}
          {(view === "email" || !report) && (
            <>
              {!meeting && (
                <section
                  className="panel reading-panel"
                  aria-labelledby="source-email-title"
                >
                  <p className="eyebrow">{t("NỘI DUNG NGUỒN", "SOURCE CONTENT")}</p>
                  <h2 id="source-email-title">{t("Email gốc", "Source email")}</h2>
                  {run.source_email != null ? (
                    <>
                      <p className="surface-description">
                        {gmailSource
                          ? t("Email lấy trực tiếp từ Gmail; giữ nội dung và thread gốc.", "Email retrieved directly from Gmail; the original content and thread are preserved.")
                          : t("Email được cung cấp khi tạo nghiên cứu, hiển thị nguyên văn.", "Email provided when creating the research, shown verbatim.")}
                      </p>
                      <div className="preserve source-email-body">
                        {run.source_email}
                      </div>
                      {gmailSource && (
                        <>
                          <a
                            href={`https://mail.google.com/mail/u/?authuser=${encodeURIComponent(gmailSource.mailbox ?? "")}#all/${gmailSource.thread_id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                          >{' ' + t("Mở thread Gmail", "Open Gmail thread") + ' '}</a>
                          <Attachments items={gmailSource.attachments ?? []} />
                        </>
                      )}
                    </>
                  ) : (
                    <p className="muted">{' ' + t("Lượt này chưa có email nguồn riêng. Nội dung ở phần yêu cầu nghiên cứu không được coi là email gốc.", "This run has no separate source email. Research instructions are not treated as the source email.") + ' '}</p>
                  )}
                </section>
              )}
              <section
                className="panel reading-panel"
                aria-labelledby="research-context-title"
              >
                <p className="eyebrow">{t("HƯỚNG DẪN CHO TRỢ LÝ", "ASSISTANT INSTRUCTIONS")}</p>
                <h2 id="research-context-title">{t("Yêu cầu nghiên cứu", "Research instructions")}</h2>
                {run.context ? (
                  <div className="preserve research-context-body">
                    {run.context}
                  </div>
                ) : (
                  <p className="muted">{t("Chưa có yêu cầu bổ sung.", "No additional instructions.")}</p>
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
                      {view === "report"
                        ? t("DÙNG NỘI BỘ", "INTERNAL USE")
                        : t("GỬI KHÁCH / ĐỐI TÁC", "FOR CUSTOMERS / PARTNERS")}
                    </p>
                    <h2>{view === "report" ? t("Báo cáo", "Report") : t("Email nháp", "Email draft")}</h2>
                  </div>
                  <span className="version">v{report.version}</span>
                </div>
                {view === "report" ? (
                  <>
                    <p className="surface-description">{' ' + t("Thông tin doanh nghiệp, nguồn tham khảo và phân tích để chuẩn bị trao đổi.", "Company information, references and analysis to prepare for your conversation.") + ' '}</p>
                    <div className="markdown">
                      <Markdown
                        remarkPlugins={[remarkGfm]}
                        skipHtml
                        disallowedElements={["img"]}
                        components={{
                          table: ({ children }) => (
                            <div
                              className="table-scroll"
                              role="region"
                              aria-label={t("Bảng báo cáo; cuộn ngang để xem thêm", "Report table; scroll horizontally to see more")}
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
                        ? t("Có thể lưu phiên bản này vào Gmail Drafts trong thread gốc. Thao tác này chưa gửi email.", "You can save this version to Gmail Drafts in the original thread. This does not send the email.")
                        : t("Bản nháp đang lưu trong ứng dụng. Chọn email từ Gmail để tạo reply trong đúng thread.", "This draft is stored in the application. Select an email from Gmail to create a reply in the correct thread.")}
                    </p>
                    {Number(run.config.prompt_version ?? 0) < 5 && (
                      <p className="notice inline-notice">
                        <strong>{t("Email này được soạn theo hướng dẫn cũ;", "This email was drafted using older instructions;")}</strong>{" "}{' ' + t("cần soạn lại trước khi gửi khách.", "redraft it before sending it to a customer.") + ' '}</p>
                    )}
                    <dl className="email-addresses">
                      {(["to", "cc", "bcc"] as const).map((key) => (
                        <div key={key}>
                          <dt>{key.toUpperCase()}</dt>
                          <dd>
                            {(report.recipients[key] ?? []).join(", ") ||
                              (key === "to" ? t("Chưa chọn người nhận", "No recipient selected") : "—")}
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
                            t("Cần cấp bổ sung quyền Gmail để lưu draft. Xem trang Kết nối & vận hành.", "Additional Gmail permissions are required to save drafts. See Connections & operations.")}{' ' + t("Nội dung không đổi sẽ dùng lại draft đã xuất. Bản đã xuất không tự cập nhật khi chỉnh sửa trong ứng dụng hoặc Gmail. Gửi từ ứng dụng sẽ dùng draft khớp nội dung đã duyệt; draft biến mất khỏi Gmail khi gửi thành công.", "Unchanged content reuses the exported draft. Exported drafts do not update automatically after edits in the application or Gmail. Sending from the application uses the draft matching the approved content; the draft disappears from Gmail after a successful send.") + ' '}</p>
                        {gmail_drafts.map((d) => (
                          <p key={String(d.id)}>
                            {d.report_id === report.id
                              ? t(`Phiên bản ${report.version}`, `Version ${report.version}`)
                              : t("Phiên bản trước", "Previous version")}
                            :{" "}
                            {d.status === "pending" ? (
                              <span>{t("Đang chờ tạo draft", "Waiting to create draft")}</span>
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
                      {report.email_subject || t("Chưa có tiêu đề", "No subject yet")}
                    </h3>
                    <div className="preserve email-body">
                      {report.email_body || t("Chưa có nội dung email.", "No email content yet.")}
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
                <summary>{' ' + t("Nguồn tham khảo", "References")}{" "}
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
                  <p className="muted">{t("Chưa có nguồn tham khảo.", "No references yet.")}</p>
                )}
              </details>
            </>
          ) : (
            <section className="panel">
              <h2>{t("Tiến độ nghiên cứu", "Research progress")}</h2>
              <p className="muted">
                {run.status === "failed"
                  ? t("Chưa tạo được báo cáo. Xem lỗi và tiến độ từng bước bên cạnh.", "The report could not be created. See the error and step progress alongside.")
                  : t("Báo cáo và email nháp sẽ xuất hiện sau khi nghiên cứu hoàn tất.", "The report and email draft will appear after research is complete.")}
              </p>
            </section>
          )}
        </div>
        <div className="detail-sidebar">
          {report && (
            <section id="review" className="panel review-panel">
              <p className="eyebrow">{t("GÓI DUYỆT · QUYẾT ĐỊNH CỦA BẠN", "APPROVAL PACKAGE · YOUR DECISION")}</p>
              <div className="surface-heading">
                <h2>{t("Phiên bản", "Version") + ' '}{report.version}</h2>
                {approval && (
                  <Status
                    value={
                      expired && approval.status === "pending"
                        ? "expired"
                        : approval.status
                    }
                  />
                )}
              </div>
              <p className="muted">{' ' + t("Kiểm tra báo cáo, email, người nhận và các tùy chọn bên dưới trước khi duyệt.", "Review the report, email, recipients and options below before approving.") + ' '}</p>
              {approval?.status === "approved" && (
                <div className="notice inline-notice" role="status">
                  <strong>
                    {report.send_email
                      ? t("Đã duyệt yêu cầu gửi email.", "The email send request has been approved.")
                      : t("Đã duyệt nội dung; không yêu cầu gửi email từ ứng dụng.", "Content approved; sending email from the application was not requested.")}
                  </strong>
                  {!report.send_email && (
                    <p>{' ' + t("Muốn gửi: mở Chỉnh sửa nội dung & tùy chọn, bật Gửi email, lưu phiên bản mới rồi chọn Duyệt và gửi email. Gmail Drafts vẫn là bản nháp.", "To send: open Edit content & options, enable Send email, save a new version, then select Approve and send email. Gmail Drafts remain drafts.") + ' '}</p>
                  )}
                </div>
              )}
              <dl className="review-summary">
                <div>
                  <dt>{t("Báo cáo & email", "Report & email")}</dt>
                  <dd>v{report.version}</dd>
                </div>
                {(["to", "cc", "bcc"] as const).map((key) => (
                  <div key={key}>
                    <dt>{key.toUpperCase()}</dt>
                    <dd>{(report.recipients[key] ?? []).join(", ") || "—"}</dd>
                  </div>
                ))}
                {report.artifacts.length > 0 && (
                  <div>
                    <dt>{t("File sẽ đính kèm", "Files to attach")}</dt>
                    <dd>
                      <p>{' ' + t("Kiểm tra từng file trước khi duyệt. Đây là toàn bộ báo cáo, có thể chứa thông tin nội bộ.", "Check each file before approving. These contain the full report and may include internal information.") + ' '}</p>
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
                  <dt>{t("Gửi email", "Send email")}</dt>
                  <dd>{report.send_email ? t("Có", "Yes") : t("Không gửi", "Do not send")}</dd>
                </div>
                <div>
                  <dt>{t("Lưu kho tri thức", "Save to knowledge")}</dt>
                  <dd>{report.save_kb ? t("Có", "Yes") : t("Không lưu", "Do not save")}</dd>
                </div>
              </dl>
              {Number(run.config.prompt_version ?? 0) < 5 && (
                <p className="inline-notice notice">{' ' + t("Email này được soạn theo hướng dẫn cũ; cần soạn lại trước khi gửi khách.", "This email was drafted using older instructions; redraft it before sending it to a customer.") + ' '}</p>
              )}
              <p className="review-consequence">
                {report.send_email
                  ? t("Duyệt sẽ cho phép gửi email này tới người nhận đã chọn.", "Approval authorizes sending this email to the selected recipients.")
                  : t("Đang tắt gửi email. Duyệt phiên bản này sẽ không gửi email.", "Email sending is disabled. Approving this version will not send email.")}
              </p>
              {approval && (
                <>
                  <p className="muted meta">{' ' + t("Hết hạn:", "Expires:") + ' '}{dateTime(approval.expires_at)}
                  </p>
                  {expired && approval.status === "pending" && (
                    <p className="inline-notice notice">{' ' + t("Quyền duyệt đã hết hạn. Chỉnh sửa và lưu phiên bản mới để yêu cầu duyệt lại.", "Approval has expired. Edit and save a new version to request approval again.") + ' '}</p>
                  )}
                  {approval.status === "pending" && !expired && (
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
                        {decision.isPending ? t("Đang xử lý…", "Processing…") : approvalLabel}
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
                      >{' ' + t("Từ chối", "Reject") + ' '}</button>
                    </div>
                  )}
                </>
              )}
              {dirty && (
                <p role="status" className="inline-notice notice">{' ' + t("Lưu thay đổi trước khi duyệt phiên bản mới.", "Save changes before approving the new version.") + ' '}</p>
              )}
              {actions.length > 0 && (
                <div className="action-results">
                  <h3>{t("Kết quả gửi / lưu", "Send / save results")}</h3>
                  {actions.map((action) => (
                    <p key={action.id}>
                      {(
                        {
                          send_email: t("Gửi email", "Send email"),
                          save_kb: t("Lưu kho tri thức", "Save to knowledge"),
                        } as Record<string, string>
                      )[action.kind] ?? action.kind}
                      : <Status value={action.status} />
                    </p>
                  ))}
                </div>
              )}
            </section>
          )}
          <section className="panel">
            <h2>{t("Tiến độ từng bước", "Step progress")}</h2>
            {branches.length === 0 ? (
              <p className="muted">{t("Chưa có kết quả.", "No results yet.")}</p>
            ) : (
              branches.map((b, i) => (
                <div className="row" key={i}>
                  <span>
                    {branchLabels[String(b.branch)] ?? String(b.branch)}
                  </span>
                  <Status
                    value={String(
                      (b.result as Record<string, unknown>)?.status ??
                        "pending",
                    )}
                  />
                </div>
              ))
            )}
          </section>
          {report && (
            <ReportDownloads key={report.id} report={report} runId={run.id} />
          )}
          {report && (
            <details className="panel quality-panel">
              <summary>{t("Kiểm tra chất lượng", "Quality review")}</summary>
              <p className="muted">{' ' + t("Cần kiểm tra dữ kiện và nguồn trước khi sử dụng.", "Check facts and sources before use.") + ' '}</p>
              <dl>
                {Object.entries(report.quality).map(([key, value]) => (
                  <div key={key}>
                    <dt>{qualityLabels[key] ?? key}</dt>
                    <dd>{qualityValue(value, t, locale)}</dd>
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
