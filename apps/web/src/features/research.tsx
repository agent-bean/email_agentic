import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, post, type Run, type ResearchInput } from "../lib/api";
import { ErrorMessage, Status } from "../components/status";
import { Attachments, MeetingSource, type SourceInput } from "./inbox";
import { Icon } from "../components/icon";
import { useI18n } from "../lib/i18n";

export function Overview() {
  const { t, locale } = useI18n();
  const filters = [
    ["all", t('Tất cả', 'All')],
    ["awaiting_identity", t('Cần xác nhận', 'Needs confirmation')],
    ["active", t('Đang xử lý', 'In progress')],
    ["draft_ready", t('Có báo cáo', 'Report ready')],
    ["failed", t('Có lỗi', 'Failed')],
  ] as const;
  const nextAction: Record<string, string> = {
    awaiting_identity: t('Xác nhận doanh nghiệp', 'Confirm company'),
    running: t('Theo dõi tiến độ', 'Track progress'),
    queued: t('Theo dõi hàng đợi', 'View queue'),
    draft_ready: t('Mở báo cáo & gói duyệt', 'Open report & approval package'),
    failed: t('Kiểm tra lỗi', 'Review error'),
  };

  const [params, setParams] = useSearchParams();
  const urlSearch = params.get("q") ?? "";
  const [search, setSearch] = useState(urlSearch);
  const pendingSearch = useRef<string | null>(null);
  useEffect(() => {
    // Router navigation may lag a keystroke; never replace newer input with its echo.
    if (pendingSearch.current !== null) {
      if (urlSearch === pendingSearch.current) pendingSearch.current = null;
      return;
    }
    setSearch(urlSearch);
  }, [urlSearch, search]);
  const filter = params.get("status") ?? "all";
  const updateFilter = (key: string, value: string) =>
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (value && !(key === "status" && value === "all"))
          next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true },
    );
  const query = useQuery({
    queryKey: ["runs"],
    queryFn: () => api<Run[]>("/runs"),
    refetchInterval: 5000,
  });
  const runs = query.data ?? [];
  const visibleRuns = [...runs]
    .filter((run) => {
      const matchesStatus =
        filter === "all" ||
        (filter === "active"
          ? ["queued", "running"].includes(run.status)
          : run.status === filter);
      return (
        matchesStatus &&
        `${run.company_name} ${run.domain}`
          .toLocaleLowerCase(locale)
          .includes(search.toLocaleLowerCase(locale).trim())
      );
    })
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  const pending = runs.filter((run) => run.status === "awaiting_identity");
  return (
    <>
      <header>
        <div>
          <p className="eyebrow">{t('KHÔNG GIAN LÀM VIỆC / TỔNG QUAN', 'WORKSPACE / OVERVIEW')}</p>
          <h1>{t('Sẵn sàng cho cuộc trao đổi tiếp theo.', 'Ready for your next conversation.')}</h1>
          <p className="muted">
            {t('Từ email đầu tiên đến báo cáo có nguồn và phản hồi được duyệt.', 'From the first email to a sourced report and an approved reply.')}
          </p>
        </div>
        <Link className="button" to="/research/new">
          <Icon name="research" />
          {t('Nghiên cứu mới', 'New research')}
        </Link>
      </header>
      <section className="workflow-banner" aria-label={t('Quy trình làm việc', 'Workflow')}>
        <div>
          <span className="step-number">01</span>
          <strong>{t('Thu thập & nghiên cứu', 'Collect & research')}</strong>
          <p>{t('Email, lịch họp và nguồn doanh nghiệp', 'Email, meetings and company sources')}</p>
        </div>
        <div>
          <span className="step-number">02</span>
          <strong>{t('Kiểm tra & duyệt', 'Review & approve')}</strong>
          <p>{t('Báo cáo nội bộ, email và người nhận', 'Internal report, email and recipients')}</p>
        </div>
        <div>
          <span className="step-number">03</span>
          <strong>{t('Gửi & lưu theo lựa chọn', 'Send & save your selection')}</strong>
          <p>{t('Chỉ thực hiện đúng gói đã duyệt', 'Only the approved package is executed')}</p>
        </div>
      </section>
      <section className="stats" aria-label={t('Tóm tắt nghiên cứu', 'Research summary')}>
        <article>
          <span>{t('Tổng nghiên cứu', 'Total research')}</span>
          <strong>{query.data ? runs.length : "—"}</strong>
        </article>
        <article>
          <span>{t('Cần xác nhận doanh nghiệp', 'Company confirmation needed')}</span>
          <strong>{query.data ? pending.length : "—"}</strong>
        </article>
        <article>
          <span>{t('Đã có bản báo cáo', 'Reports ready')}</span>
          <strong>
            {query.data
              ? runs.filter((r) => r.status === "draft_ready").length
              : "—"}
          </strong>
        </article>
      </section>
      {pending.length > 0 && (
        <section className="attention-strip">
          <div>
            <strong>{pending.length} {t('nghiên cứu đang chờ bạn xác nhận', 'research items await your confirmation')}</strong>
            <p>{t('Kiểm tra tên và domain để trợ lý bắt đầu thu thập thông tin.', 'Check the name and domain so the assistant can start gathering information.')}</p>
          </div>
          <Link className="button secondary" to={`/research/${pending[0].id}`}>
            {t('Xác nhận doanh nghiệp', 'Confirm company')}
            <Icon name="arrow" />
          </Link>
        </section>
      )}
      <section className="panel research-list-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">{t('DANH SÁCH CÔNG VIỆC', 'WORK LIST')}</p>
            <h2>{t('Nghiên cứu gần đây', 'Recent research')}</h2>
          </div>
          <span className="muted">{t('Mới nhất trước', 'Newest first')}</span>
        </div>
        <div className="list-toolbar">
          <label className="search-field">
            <span>{t('Tìm nghiên cứu', 'Search research')}</span>
            <input
              type="search"
              placeholder={t('Tên doanh nghiệp hoặc domain…', 'Company name or domain…')}
              value={search}
              onChange={(event) => {
                const value = event.target.value;
                pendingSearch.current = value;
                setSearch(value);
                updateFilter("q", value);
              }}
            />
          </label>
          <div className="filter-tabs" aria-label={t('Lọc trạng thái', 'Filter by status')}>
            {filters.map(([value, label]) => (
              <button
                key={value}
                className={filter === value ? "selected" : "secondary"}
                aria-pressed={filter === value}
                onClick={() => updateFilter("status", value)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <ErrorMessage error={query.error} />
        {query.isPending ? (
          <div className="loading-state" role="status">
            <span>{t('Đang tải nghiên cứu…', 'Loading research…')}</span>
            <div className="skeleton" />
            <div className="skeleton" />
            <div className="skeleton" />
          </div>
        ) : query.isError ? (
          <button className="secondary" onClick={() => void query.refetch()}>
            {t('Thử lại', 'Retry')}
          </button>
        ) : runs.length === 0 ? (
          <div className="empty">
            <Icon name="research" />
            <h3>{t('Bắt đầu từ một doanh nghiệp.', 'Start with a company.')}</h3>
            <p>
              {t('Chọn email, cuộc họp hoặc nhập thông tin để tạo nghiên cứu đầu tiên.', 'Choose an email or meeting, or enter details to create your first research.')}
            </p>
            <Link className="button secondary" to="/inputs">
              {t('Chọn email hoặc cuộc họp', 'Choose an email or meeting')}
              <Icon name="arrow" />
            </Link>
          </div>
        ) : visibleRuns.length === 0 ? (
          <div className="empty">
            <h3>{t('Không có nghiên cứu phù hợp', 'No matching research')}</h3>
            <p>{t('Thử tên hoặc domain khác, hoặc bỏ bộ lọc trạng thái.', 'Try another name or domain, or clear the status filter.')}</p>
            <button
              className="secondary"
              onClick={() => {
                pendingSearch.current = null;
                setSearch("");
                setParams({});
              }}
            >
              {t('Xóa bộ lọc', 'Clear filters')}
            </button>
          </div>
        ) : (
          <>
            <p className="list-count muted" role="status">
              {visibleRuns.length} / {runs.length} {t('nghiên cứu', 'research items')}
            </p>
            <div className="run-list">
              {visibleRuns.map((run) => (
                <Link to={`/research/${run.id}`} key={run.id}>
                  <div className="run-company">
                    <strong>{run.company_name}</strong>
                    <small>{run.domain}</small>
                  </div>
                  <div>
                    <Status value={run.status} />
                    <small>{nextAction[run.status] ?? t('Xem nghiên cứu', 'View research')}</small>
                  </div>
                  <span className="run-date muted">
                    {new Date(run.created_at).toLocaleString(locale)}
                  </span>
                  <span className="run-arrow">
                    <Icon name="arrow" />
                  </span>
                </Link>
              ))}
            </div>
          </>
        )}
      </section>
    </>
  );
}

export function NewResearch() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const sourceId = params.get("input");
  const source = useQuery({
    queryKey: ["input", sourceId],
    queryFn: () => api<SourceInput>(`/inputs/${sourceId}`),
    enabled: Boolean(sourceId),
  });
  const submission = useRef({ body: "", key: "" });
  const [input, setInput] = useState<ResearchInput>({
    company_name: "",
    domain: "",
    context: "",
  });
  const mutation = useMutation({
    mutationFn: () => {
      const payload = sourceId
        ? {
            ...input,
            ...(source.data?.kind === "meeting"
              ? { source_meeting_id: sourceId }
              : { source_input_id: sourceId }),
          }
        : input;
      const body = JSON.stringify(payload);
      if (submission.current.body !== body)
        submission.current = { body, key: crypto.randomUUID() };
      return post<{ id: string }>("/runs", payload, submission.current.key);
    },
    onSuccess: (value) => navigate(`/research/${value.id}`),
  });
  return (
    <>
      <header>
        <div>
          <p className="eyebrow">{t('NGHIÊN CỨU DOANH NGHIỆP', 'COMPANY RESEARCH')}</p>
          <h1>{t('Nghiên cứu mới', 'New research')}</h1>
          <p className="muted">
            {t('Xác nhận đúng doanh nghiệp, rồi thu thập thông tin có nguồn.', 'Confirm the company, then gather sourced information.')}
          </p>
        </div>
      </header>
      <form
        className="panel form"
        onSubmit={(event) => {
          event.preventDefault();
          mutation.mutate();
        }}
      >
        <fieldset disabled={mutation.isPending}>
          <legend>{t('Thông tin nghiên cứu', 'Research details')}</legend>
          <label>
            {t('Tên doanh nghiệp', 'Company name')}
            <input
              required
              minLength={2}
              maxLength={200}
              value={input.company_name}
              onChange={(e) =>
                setInput({ ...input, company_name: e.target.value })
              }
              placeholder={t('Ví dụ: FPT Software', 'For example: FPT Software')}
            />
          </label>
          <label>
            {t('Domain chính thức', 'Official domain')}
            <input
              required
              minLength={3}
              maxLength={253}
              autoCapitalize="none"
              spellCheck={false}
              value={input.domain}
              onChange={(e) => setInput({ ...input, domain: e.target.value })}
              placeholder="fptsoftware.com"
            />
            <small>{t('Chỉ nhập domain, không có https:// hoặc đường dẫn.', 'Enter only the domain, without https:// or a path.')}</small>
          </label>
          {sourceId ? (
            <section>
              <h2>
                {source.data?.kind === "meeting"
                  ? t('Cuộc họp từ Google Calendar', 'Meeting from Google Calendar')
                  : t('Email từ Gmail', 'Email from Gmail')}
              </h2>
              <ErrorMessage error={source.error} />
              {source.isError && (
                <button
                  type="button"
                  className="secondary"
                  disabled={source.isFetching}
                  onClick={() => void source.refetch()}
                >
                  {t('Tải lại nguồn', 'Reload source')}
                </button>
              )}
              {source.isPending ? (
                <p role="status">{t('Đang tải nguồn…', 'Loading source…')}</p>
              ) : (
                source.data && (
                  <>
                    {source.data.kind === "meeting" ? (
                      <MeetingSource event={source.data.content} />
                    ) : (
                      <pre className="preserve">
                        {source.data.content.source_text}
                      </pre>
                    )}
                    <Attachments
                      items={source.data.content.attachments ?? []}
                    />
                    <p className="muted">
                      {t('Ứng dụng giữ nguyên nguồn đã chọn. Nhập đúng doanh nghiệp cần nghiên cứu ở phía trên.', 'The selected source is preserved. Enter the company to research above.')}
                    </p>
                  </>
                )
              )}
            </section>
          ) : (
            <label>
              {t('Email gốc (không bắt buộc)', 'Original email (optional)')}
              <textarea
                rows={8}
                maxLength={30000}
                value={input.source_email ?? ""}
                onChange={(e) =>
                  setInput({
                    ...input,
                    source_email: e.target.value === "" ? null : e.target.value,
                  })
                }
                placeholder={t('Dán nguyên văn email khách gửi, gồm tiêu đề và nội dung…', 'Paste the customer email exactly, including its subject and body…')}
              />
              <small>
                {t('Chọn email trực tiếp từ Gmail tại', 'Choose an email directly from Gmail in')}{" "}
                <Link className="source-picker-link" to="/inputs">
                  {t('Email & cuộc họp', 'Email & meetings')}
                </Link>
                .
              </small>
            </label>
          )}
          <label>
            {t('Yêu cầu nghiên cứu (không bắt buộc)', 'Research instructions (optional)')}
            <textarea
              rows={5}
              maxLength={12000}
              value={input.context ?? ""}
              onChange={(e) => setInput({ ...input, context: e.target.value })}
              placeholder={t('Cần tìm hiểu gì về doanh nghiệp? Mục tiêu cuộc trao đổi là gì?', 'What should we find out about this company? What is the goal of the conversation?')}
            />
            <small>
              {t('Hướng dẫn riêng cho trợ lý; không phải lời khách gửi trong email.', 'Private instructions for the assistant, separate from the customer email.')}
            </small>
          </label>
        </fieldset>
        <ErrorMessage error={mutation.error} />
        <button
          disabled={
            mutation.isPending ||
            Boolean(
              sourceId &&
              (!source.data ||
                !["email", "meeting"].includes(source.data.kind)),
            )
          }
        >
          {mutation.isPending ? t('Đang tạo…', 'Creating…') : t('Tạo nghiên cứu', 'Create research')}
        </button>
      </form>
    </>
  );
}
