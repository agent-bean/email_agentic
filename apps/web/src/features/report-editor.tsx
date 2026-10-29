import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, type Report, type ReportEdit } from "../lib/api";
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
          "Có thay đổi chưa lưu. Rời trang và bỏ các thay đổi này?",
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
  }, [dirty]);
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
            Tiêu đề email
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
            {dirty ? "Có thay đổi chưa lưu" : "Chưa có thay đổi"}
          </span>
          <button disabled={save.isPending || !dirty}>
            {save.isPending ? "Đang lưu…" : "Lưu phiên bản mới"}
          </button>
        </div>
      </form>
    </details>
  );
}
