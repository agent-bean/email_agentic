import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { endpoints, type Report } from '../lib/api';
import { useI18n } from '../lib/i18n';
import { ErrorMessage } from '../components/status';

export function ReportDownloads({ report, runId }: { report: Report; runId: string }) {
  const { t } = useI18n();
  const [file, setFile] = useState<{ id: string; filename: string } | null>(
    null,
  );
  const download = useMutation({
    mutationFn: (format: "pdf" | "docx" | "md") =>
      endpoints.exportReport(runId, report.id, format),
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

