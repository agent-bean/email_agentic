import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, type Report, type ReportEdit } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { ErrorMessage } from "../components/status";

export function ReportEditor({
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
  const { t } = useI18n();
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
      (a) => a.format as "pdf" | "docx" | "md",
    ),
  };
  const [edit, setEdit] = useState(initial);
  const [recipientText, setRecipientText] = useState({
    to: (report.recipients.to ?? []).join(", "),
    cc: (report.recipients.cc ?? []).join(", "),
    bcc: (report.recipients.bcc ?? []).join(", "),
  });
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
          ? event.target.closest("a[href]")
          : null;
      if (
        !(link instanceof HTMLAnchorElement) ||
        link.target === "_blank" ||
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
          t("Có thay đổi chưa lưu. Rời trang và bỏ các thay đổi này?", "You have unsaved changes. Leave this page and discard them?"),
        )
      ) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", warn);
    document.addEventListener("click", guardNavigation, true);
    return () => {
      window.removeEventListener("beforeunload", warn);
      document.removeEventListener("click", guardNavigation, true);
    };
  }, [dirty, t]);
  const save = useMutation({
    mutationFn: () =>
      api(`/runs/${runId}/report`, {
        method: "PUT",
        body: JSON.stringify(editedReport),
      }),
    onSuccess: refresh,
  });
  return (
    <details id="report-editor" className="panel editor">
      <summary>{t("Chỉnh sửa nội dung & tùy chọn", "Edit content & options")}</summary>
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <p className="muted">
          {t("Lưu sẽ tạo phiên bản mới và yêu cầu duyệt lại. Bản đang chỉnh sửa chưa được dùng để gửi.", "Saving creates a new version that requires approval again. Unsaved edits are not used for sending.")}
        </p>
        <fieldset disabled={save.isPending}>
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
        <fieldset disabled={save.isPending}>
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
        <fieldset disabled={save.isPending}>
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
        <fieldset disabled={save.isPending}>
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
        <fieldset disabled={save.isPending}>
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
          <button disabled={save.isPending || !dirty}>
            {save.isPending ? t("Đang lưu…", "Saving\u2026") : t("Lưu phiên bản mới", "Save new version")}
          </button>
        </div>
      </form>
    </details>
  );
}
