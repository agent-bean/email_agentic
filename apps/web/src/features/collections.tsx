import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, post } from '../lib/api';
import { useI18n } from '../lib/i18n';
import { ErrorMessage, Status } from '../components/status';

export function Collection({ kind, title }: { kind: string; title: string }) {
  const { t } = useI18n();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: [kind],
    queryFn: () => api<Record<string, unknown>[]>(`/${kind}`),
  });
  const sync = useMutation({
    mutationFn: (provider: string) => post(`/sync/${provider}`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: [kind] });
    },
  });
  return (
    <>
      <header>
        <div>
          <p className="eyebrow">{t("DỮ LIỆU CỦA BẠN", "YOUR DATA")}</p>
          <h1>{kind === 'companies' ? t('Doanh nghiệp', 'Companies') : title}</h1>
          <p className="muted">
            {kind === 'inputs'
              ? t("Email và lịch họp đã đồng bộ để tham khảo khi nghiên cứu.", "Synced emails and meetings for research reference.")
              : kind === 'companies'
                ? t("Các doanh nghiệp đã được lưu trong ứng dụng.", "Companies saved in the application.")
                : t("Các báo cáo đã được duyệt và lưu.", "Approved and saved reports.")}
          </p>
        </div>
        <div className="actions">
          <button
            className="secondary"
            disabled={query.isFetching}
            onClick={() => void query.refetch()}
          >
            {t("Làm mới", "Refresh")}
          </button>
          {kind === 'inputs' && (
            <div className="actions">
              <button
                disabled={sync.isPending}
                onClick={() => sync.mutate('email')}
              >
                {t("Đồng bộ email", "Sync email")}
              </button>
              <button
                className="secondary"
                disabled={sync.isPending}
                onClick={() => sync.mutate('calendar')}
              >
                {t("Đồng bộ lịch", "Sync calendar")}
              </button>
            </div>
          )}
        </div>
      </header>
      <ErrorMessage error={query.error || sync.error} />
      {sync.isSuccess && (
        <p role="status">
          {t("Đã nhận yêu cầu đồng bộ. Chọn Làm mới sau khi đồng bộ xong.", "Sync requested. Select Refresh when syncing finishes.")}
        </p>
      )}
      <section className="panel">
        {query.isPending ? (
          <p role="status">{t("Đang tải…", "Loading…")}</p>
        ) : query.isError ? (
          <p className="muted">
            {t("Không tải được danh sách. Chọn Làm mới để thử lại.", "Could not load the list. Select Refresh to retry.")}
          </p>
        ) : !query.data?.length ? (
          <div className="empty">
            <h2>{t("Chưa có dữ liệu", "No data yet")}</h2>
            <p>
              {kind === 'inputs'
                ? t("Đồng bộ email hoặc lịch để đưa dữ liệu vào ứng dụng.", "Sync email or calendar to bring data into the application.")
                : kind === 'knowledge'
                  ? t("Báo cáo sẽ xuất hiện ở đây sau khi được duyệt và chọn lưu vào kho tri thức.", "Reports appear here after approval and saving to the knowledge library.")
                  : t("Doanh nghiệp sẽ xuất hiện sau khi bắt đầu nghiên cứu.", "Companies appear after research begins.")}
            </p>
          </div>
        ) : (
          query.data.map((item, i) => (
            <article className="record" key={String(item.id ?? i)}>
              <h3>
                {String(
                  item.legal_name ??
                    (item.content && typeof item.content === 'object'
                      ? ((item.content as Record<string, unknown>).summary ??
                        (item.content as Record<string, unknown>).subject)
                      : null) ??
                    (item.kind === 'calendar'
                      ? t("Cuộc họp", "Meeting")
                      : item.kind === 'email'
                        ? 'Email'
                        : t("Báo cáo", "Report")),
                )}
              </h3>
              {item.status ? <Status value={String(item.status)} /> : null}
              <p className="preserve">
                {item.content && typeof item.content === 'string'
                  ? item.content
                  : String(item.domain ?? item.source_id ?? '')}
              </p>
              {typeof item.content === 'object' && (
                <details>
                  <summary>{t("Xem dữ liệu nguồn", "View source data")}</summary>
                  <pre>{JSON.stringify(item.content, null, 2)}</pre>
                </details>
              )}
            </article>
          ))
        )}
      </section>
    </>
  );
}

type SystemData = {
  mode: string;
  model: string;
  target_seconds: number;
  scheduler_enabled: boolean;
  connections: Record<string, string>;
  jobs: { kind: string; status: string; total: number }[];
};
export function System() {
  const { t } = useI18n();
  const connectionNames: Record<string, string> = {
    llm: t('Mô hình AI', 'AI model'), tavily: 'Tavily', duckduckgo: 'DuckDuckGo',
    firecrawl: 'Firecrawl', google: 'Google', google_drafts: t('Bản nháp Gmail', 'Gmail drafts'),
  };
  const jobNames: Record<string, string> = {
    research: t('Nghiên cứu', 'Research'), resume: t('Tiếp tục nghiên cứu', 'Resume research'),
    approval_resume: t('Tiếp tục sau duyệt', 'Resume after approval'), publish: t('Xuất bản', 'Publish'),
    scan_email: t('Quét email', 'Scan email'), email_intake: t('Tiếp nhận email', 'Email intake'),
    calendar_intake: t('Tiếp nhận lịch', 'Calendar intake'), gmail_draft: t('Lưu bản nháp Gmail', 'Save Gmail draft'),
    scan_calendar: t('Quét lịch', 'Scan calendar'),
  };
  const query = useQuery({
    queryKey: ['system'],
    queryFn: () => api<SystemData>('/system'),
    refetchInterval: 10000,
  });
  return (
    <>
      <header>
        <div>
          <p className="eyebrow">{t("TÌNH TRẠNG HỆ THỐNG", "SYSTEM STATUS")}</p>
          <h1>{t("Kết nối & vận hành", "Connections & operations")}</h1>
        </div>
      </header>
      <ErrorMessage error={query.error} />
      {query.isPending && (
        <section className="panel" role="status">
          {t("Đang tải trạng thái…", "Loading status…")}
        </section>
      )}
      {query.isError && (
        <button className="secondary" onClick={() => void query.refetch()}>
          {t("Thử lại", "Retry")}
        </button>
      )}
      {query.data && (
        <>
          <section className="panel">
            <h2>{t("Cấu hình hoạt động", "Configuration")}</h2>
            <p>{t("Mô hình", "Model")}: {query.data.model || t("Chưa cấu hình", "Not configured")}</p>
            <p>{t("Mục tiêu tạo báo cáo", "Report generation target")}: {query.data.target_seconds} {t("giây", "seconds")}</p>
            <p>
              {t('Lịch tự động', 'Automatic scheduling')}:{' '}
              {query.data.scheduler_enabled ? t("Đang bật", "Enabled") : t("Đang tắt", "Disabled")}
            </p>
            <p className="muted">
              {t("Đã cấu hình chưa có nghĩa là đã kết nối thành công.", "Configured does not mean a connection has succeeded.")}
            </p>
            {Object.entries(query.data.connections).map(([key, value]) => (
              <p key={key}>
                {connectionNames[key] ?? key}:{' '}
                {value === 'configured'
                  ? t("Đã cấu hình", "Configured")
                  : value === 'disabled'
                    ? t("Đang tắt", "Disabled")
                    : value === 'requires_consent'
                      ? t("Cần cấp quyền gmail.compose để lưu draft", "The gmail.compose permission is required to save drafts")
                      : t("Thiếu cấu hình", "Configuration missing")}
              </p>
            ))}
          </section>
          <section className="panel">
            <h2>{t("Hàng đợi", "Queue")}</h2>
            {query.data.jobs.length ? (
              query.data.jobs.map((job, i) => (
                <p key={i}>
                  {jobNames[job.kind] ?? job.kind} · <Status value={job.status} />: {job.total}
                </p>
              ))
            ) : (
              <p>{t("Chưa có tác vụ.", "No jobs yet.")}</p>
            )}
          </section>
        </>
      )}
    </>
  );
}
