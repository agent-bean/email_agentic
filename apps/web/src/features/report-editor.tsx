import { useCallback, useEffect, useRef, useState } from "react";
import { useBlocker } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { endpoints, ApiError, type Report, type ReportEdit } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { ErrorMessage } from "../components/status";

export function ReportEditor({
  report,
  runId,
  refresh,
  onDirty,
  readOnly = false,
}: {
  report: Report;
  runId: string;
  refresh: () => void;
  onDirty: (dirty: boolean) => void;
  readOnly?: boolean;
}) {
  const { t } = useI18n();
  const editor = useRef<HTMLDetailsElement>(null);
  const stayButton = useRef<HTMLButtonElement>(null);
  const [baseReport, setBaseReport] = useState(report);
  const [savedId, setSavedId] = useState<string | null>(null);
  const initial = reportEdit(baseReport);
  const [edit, setEdit] = useState(initial);
  const [recipientText, setRecipientText] = useState(recipientFields(baseReport));
  function adoptLatest() {
    setBaseReport(report);
    setEdit(reportEdit(report));
    setRecipientText(recipientFields(report));
    setSavedId(null);
    save.reset();
  }
  // Keep raw text while typing so commas and spaces are not removed mid-edit.
  const recipients = Object.fromEntries(
    Object.entries(recipientText).map(([kind, text]) => [
      kind,
      text
        .split(",")
        .map((address) => address.trim())
        .filter(Boolean),
    ]),
  );
  const editedReport = { ...edit, recipients };
  const dirty = JSON.stringify(initial) !== JSON.stringify(editedReport);
  const newerVersion = report.id !== baseReport.id;
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    dirty && currentLocation.pathname !== nextLocation.pathname);
  const save = useMutation({
    mutationFn: () => {
      if (readOnly) throw new Error(t('Dữ liệu đã hết hạn; không thể lưu.', 'The data has expired; saving is unavailable.'));
      return endpoints.editReport(runId, editedReport);
    },
    onSuccess: (result) => {
      setSavedId(result.id);
      refresh();
    },
    onError: (error) => {
      if (isVersionConflict(error)) refresh();
    },
  });
  const conflict = newerVersion || isVersionConflict(save.error);
  useEffect(() => {
    if ((conflict || (readOnly && dirty) || blocker.state === 'blocked') && editor.current) editor.current.open = true;
    if (blocker.state === 'blocked') stayButton.current?.focus();
  }, [conflict, blocker.state, readOnly, dirty]);
  useEffect(() => {
    if (newerVersion && (!dirty || (!readOnly && report.id === savedId))) adoptLatest();
  }, [report, newerVersion, dirty, savedId, readOnly]);
  useEffect(() => {
    onDirty(dirty || conflict);
    return () => onDirty(false);
  }, [dirty, conflict, onDirty]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  return (
    <details ref={editor} id="report-editor" className="panel editor">
      <summary>{t("Chỉnh sửa nội dung & tùy chọn", "Edit content & options")}</summary>
      {readOnly && <p role="alert" className="notice">{t('Dữ liệu nguồn hoặc báo cáo đã hết hạn lưu. Không thể lưu hoặc gửi bản chỉnh sửa này. Nội dung chưa lưu chỉ còn trong trang hiện tại; hãy sao chép phần cần giữ trước khi rời trang.', 'The source or report retention period has expired. These edits cannot be saved or sent. Unsaved content exists only on this page; copy anything you need before leaving.')}</p>}
      {readOnly && dirty && <label>{t('Sao chép nội dung chưa lưu', 'Copy unsaved content')}<textarea readOnly rows={12}
        value={[edit.markdown, edit.email_subject, edit.email_body, ...Object.entries(recipientText).map(([kind, value]) => `${kind.toUpperCase()}: ${value}`)].join('\n\n')} /></label>}
      {blocker.state === 'blocked' && <section role="alertdialog" aria-label={t('Thay đổi chưa lưu', 'Unsaved changes')}>
        <p>{t('Rời trang sẽ bỏ các thay đổi chưa lưu.', 'Leaving this page discards your unsaved changes.')}</p>
        <button ref={stayButton} type="button" onClick={() => blocker.reset()}>{t('Tiếp tục chỉnh sửa', 'Keep editing')}</button>
        <button type="button" className="secondary" onClick={() => blocker.proceed()}>{t('Bỏ thay đổi và rời trang', 'Discard and leave')}</button>
      </section>}
      {conflict && <section role="alert" className="notice">
        <p>{t('Phiên bản trên máy chủ đã thay đổi. Bản chỉnh sửa của bạn vẫn được giữ, nhưng không thể lưu đè. Sao chép nội dung cần giữ trước khi tải phiên bản mới.', 'The server version has changed. Your edits are preserved but cannot overwrite it. Copy any changes you want to keep before loading the latest version.')}</p>
        <button type="button" className="secondary" disabled={!newerVersion} onClick={() => {
          if (!dirty || window.confirm(t('Bỏ thay đổi chưa lưu và tải phiên bản mới?', 'Discard unsaved changes and load the latest version?'))) adoptLatest();
        }}>{t('Tải phiên bản mới', 'Load latest version')}</button>
        {!newerVersion && <button type="button" className="secondary" onClick={refresh}>{t('Làm mới', 'Refresh')}</button>}
      </section>}
      {savedId && !conflict && <p role="status">{t('Đã lưu. Đang tải phiên bản mới.', 'Saved. Loading the new version.')} <button type="button" className="secondary" onClick={refresh}>{t('Làm mới', 'Refresh')}</button></p>}
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          if (!readOnly && !conflict && !savedId) save.mutate();
        }}
      >
        <p className="muted">
          {t("Lưu sẽ tạo phiên bản mới và yêu cầu duyệt lại. Bản đang chỉnh sửa chưa được dùng để gửi.", "Saving creates a new version that requires approval again. Unsaved edits are not used for sending.")}
        </p>
        <fieldset disabled={readOnly || save.isPending || Boolean(savedId)}>
          <legend>{t("Báo cáo · nội bộ", "Report \u00b7 internal")}</legend>
          <label>
            {t("Nội dung Markdown", "Markdown content")}
            <textarea
              rows={16}
              value={edit.markdown}
              onChange={(e) => setEdit({ ...edit, markdown: e.target.value })}
            />
          </label>
        </fieldset>
        <fieldset disabled={readOnly || save.isPending || Boolean(savedId)}>
          <legend>{t("Email nháp · gửi khách / đối tác", "Draft email \u00b7 for customers / partners")}</legend>
          <label>
            {t("Tiêu đề email", "Email subject")}
            <input
              value={edit.email_subject}
              onChange={(e) =>
                setEdit({ ...edit, email_subject: e.target.value })
              }
            />
          </label>
          <label>
            {t("Nội dung email", "Email body")}
            <textarea
              rows={9}
              value={edit.email_body}
              onChange={(e) => setEdit({ ...edit, email_body: e.target.value })}
            />
          </label>
        </fieldset>
        <fieldset disabled={readOnly || save.isPending || Boolean(savedId)}>
          <legend>{t("Người nhận", "Recipients")}</legend>
          <p className="muted">{t("Phân cách các địa chỉ bằng dấu phẩy.", "Separate addresses with commas.")}</p>
          {(["to", "cc", "bcc"] as const).map((key) => (
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
        <fieldset disabled={readOnly || save.isPending || Boolean(savedId)}>
          <legend>{t("Sau khi duyệt", "After approval")}</legend>
          <label className="check">
            <input
              type="checkbox"
              checked={edit.send_email}
              onChange={(e) =>
                setEdit({ ...edit, send_email: e.target.checked })
              }
            />
            {t("Gửi email tới người nhận", "Send email to recipients")}
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={edit.save_kb}
              onChange={(e) => setEdit({ ...edit, save_kb: e.target.checked })}
            />
            {t("Lưu báo cáo vào kho tri thức", "Save report to knowledge library")}
          </label>
        </fieldset>
        <fieldset disabled={readOnly || save.isPending || Boolean(savedId)}>
          <legend>{t("File đính kèm email", "Email attachments")}</legend>
          <p className="notice">
            {t("Báo cáo chứa phân tích nội bộ. Chỉ chọn đính kèm khi nội dung phù hợp với người nhận. Lưu phiên bản mới rồi mở file bên dưới để kiểm tra trước khi duyệt.", "Reports contain internal analysis. Attach only when the content is suitable for the recipient. Save a new version, then open the file below to review it before approval.")}
          </p>
          {(["pdf", "docx", "md"] as const).map((format) => (
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
              {format === "docx" ? "Word" : format.toUpperCase()}
            </label>
          ))}
        </fieldset>
        <ErrorMessage error={save.error} />
        <div className="save-bar">
          <span className="muted" role="status">
            {dirty ? t("Có thay đổi chưa lưu", "Unsaved changes") : t("Chưa có thay đổi", "No changes")}
          </span>
          <button disabled={readOnly || save.isPending || Boolean(savedId) || !dirty || conflict}>
            {save.isPending ? t("Đang lưu…", "Saving\u2026") : t("Lưu phiên bản mới", "Save new version")}
          </button>
        </div>
      </form>
    </details>
  );
}

function recipientFields(report: Report) {
  return {
    to: (report.recipients.to ?? []).join(", "),
    cc: (report.recipients.cc ?? []).join(", "),
    bcc: (report.recipients.bcc ?? []).join(", "),
  };
}

function isVersionConflict(error: unknown) {
  return error instanceof ApiError && error.status === 409 && error.detail === 'Report version changed';
}

function reportEdit(report: Report): ReportEdit {
  return {
    version: report.version,
    markdown: report.markdown,
    email_subject: report.email_subject,
    email_body: report.email_body,
    recipients: { to: report.recipients.to ?? [], cc: report.recipients.cc ?? [], bcc: report.recipients.bcc ?? [] },
    send_email: report.send_email,
    save_kb: report.save_kb,
    attachment_formats: report.artifacts.map((artifact) => artifact.format),
  };
}

// Keep only the currently mounted draft through a retention transition; never persist it.
export function RetainedReportEditor({ report, readOnly, runId, refresh, onDirty }: {
  report?: Report;
  readOnly: boolean;
  runId: string;
  refresh: () => void;
  onDirty: (dirty: boolean) => void;
}) {
  const [lastReport, setLastReport] = useState(report);
  const [dirty, setDirty] = useState(false);
  const trackDirty = useCallback((value: boolean) => {
    setDirty(value);
    onDirty(value);
  }, [onDirty]);
  useEffect(() => {
    if (report) setLastReport(report);
    else if (!dirty) setLastReport(undefined);
  }, [report, dirty]);
  const current = report ?? (dirty ? lastReport : undefined);
  return current ? <ReportEditor report={current} readOnly={readOnly || !report}
    runId={runId} refresh={refresh} onDirty={trackDirty} /> : null;
}
