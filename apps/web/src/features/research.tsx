import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, post, type Run, type ResearchInput } from "../lib/api";
import { ErrorMessage, Status } from "../components/status";
import { Attachments, MeetingSource, type SourceInput } from "./inbox";
import { Icon } from "../components/icon";

const filters = [
  ["all", "Tất cả"],
  ["awaiting_identity", "Cần xác nhận"],
  ["active", "Đang xử lý"],
  ["draft_ready", "Có báo cáo"],
  ["failed", "Có lỗi"],
] as const;
const nextAction: Record<string, string> = {
  awaiting_identity: "Xác nhận doanh nghiệp",
  running: "Theo dõi tiến độ",
  queued: "Theo dõi hàng đợi",
  draft_ready: "Mở báo cáo & gói duyệt",
  failed: "Kiểm tra lỗi",
};

export function Overview() {
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
          .toLocaleLowerCase("vi")
          .includes(search.toLocaleLowerCase("vi").trim())
      );
    })
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  const pending = runs.filter((run) => run.status === "awaiting_identity");
  return (
    <>
      <header>
        <div>
          <p className="eyebrow">KHÔNG GIAN LÀM VIỆC / TỔNG QUAN</p>
          <h1>Sẵn sàng cho cuộc trao đổi tiếp theo.</h1>
          <p className="muted">
            Từ email đầu tiên đến báo cáo có nguồn và phản hồi được duyệt.
          </p>
        </div>
        <Link className="button" to="/research/new">
          <Icon name="research" />
          Nghiên cứu mới
        </Link>
      </header>
      <section className="workflow-banner" aria-label="Quy trình làm việc">
        <div>
          <span className="step-number">01</span>
          <strong>Thu thập & nghiên cứu</strong>
          <p>Email, lịch họp và nguồn doanh nghiệp</p>
        </div>
        <div>
          <span className="step-number">02</span>
          <strong>Kiểm tra & duyệt</strong>
          <p>Báo cáo nội bộ, email và người nhận</p>
        </div>
        <div>
          <span className="step-number">03</span>
          <strong>Gửi & lưu theo lựa chọn</strong>
          <p>Chỉ thực hiện đúng gói đã duyệt</p>
        </div>
      </section>
      <section className="stats" aria-label="Tóm tắt nghiên cứu">
        <article>
          <span>Tổng nghiên cứu</span>
          <strong>{query.data ? runs.length : "—"}</strong>
        </article>
        <article>
          <span>Cần xác nhận doanh nghiệp</span>
          <strong>{query.data ? pending.length : "—"}</strong>
        </article>
        <article>
          <span>Đã có bản báo cáo</span>
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
            <strong>{pending.length} nghiên cứu đang chờ bạn xác nhận</strong>
            <p>Kiểm tra tên và domain để trợ lý bắt đầu thu thập thông tin.</p>
          </div>
          <Link className="button secondary" to={`/research/${pending[0].id}`}>
            Xác nhận doanh nghiệp
            <Icon name="arrow" />
          </Link>
        </section>
      )}
      <section className="panel research-list-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">DANH SÁCH CÔNG VIỆC</p>
            <h2>Nghiên cứu gần đây</h2>
          </div>
          <span className="muted">Mới nhất trước</span>
        </div>
        <div className="list-toolbar">
          <label className="search-field">
            <span>Tìm nghiên cứu</span>
            <input
              type="search"
              placeholder="Tên doanh nghiệp hoặc domain…"
              value={search}
              onChange={(event) => {
                const value = event.target.value;
                pendingSearch.current = value;
                setSearch(value);
                updateFilter("q", value);
              }}
            />
          </label>
          <div className="filter-tabs" aria-label="Lọc trạng thái">
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
            <span>Đang tải nghiên cứu…</span>
            <div className="skeleton" />
            <div className="skeleton" />
            <div className="skeleton" />
          </div>
        ) : query.isError ? (
          <button className="secondary" onClick={() => void query.refetch()}>
            Thử lại
          </button>
        ) : runs.length === 0 ? (
          <div className="empty">
            <Icon name="research" />
            <h3>Bắt đầu từ một doanh nghiệp.</h3>
            <p>
              Chọn email, cuộc họp hoặc nhập thông tin để tạo nghiên cứu đầu
              tiên.
            </p>
            <Link className="button secondary" to="/inputs">
              Chọn email hoặc cuộc họp
              <Icon name="arrow" />
            </Link>
          </div>
        ) : visibleRuns.length === 0 ? (
          <div className="empty">
            <h3>Không có nghiên cứu phù hợp</h3>
            <p>Thử tên hoặc domain khác, hoặc bỏ bộ lọc trạng thái.</p>
            <button
              className="secondary"
              onClick={() => {
                pendingSearch.current = null;
                setSearch("");
                setParams({});
              }}
            >
              Xóa bộ lọc
            </button>
          </div>
        ) : (
          <>
            <p className="list-count muted" role="status">
              {visibleRuns.length} / {runs.length} nghiên cứu
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
                    <small>{nextAction[run.status] ?? "Xem nghiên cứu"}</small>
                  </div>
                  <span className="run-date muted">
                    {new Date(run.created_at).toLocaleString("vi-VN")}
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
          <p className="eyebrow">NGHIÊN CỨU DOANH NGHIỆP</p>
          <h1>Nghiên cứu mới</h1>
          <p className="muted">
            Xác nhận đúng doanh nghiệp, rồi thu thập thông tin có nguồn.
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
          <legend>Thông tin nghiên cứu</legend>
          <label>
            Tên doanh nghiệp
            <input
              required
              minLength={2}
              maxLength={200}
              value={input.company_name}
              onChange={(e) =>
                setInput({ ...input, company_name: e.target.value })
              }
              placeholder="Ví dụ: FPT Software"
            />
          </label>
          <label>
            Domain chính thức
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
            <small>Chỉ nhập domain, không có https:// hoặc đường dẫn.</small>
          </label>
          {sourceId ? (
            <section>
              <h2>
                {source.data?.kind === "meeting"
                  ? "Cuộc họp từ Google Calendar"
                  : "Email từ Gmail"}
              </h2>
              <ErrorMessage error={source.error} />
              {source.isError && (
                <button
                  type="button"
                  className="secondary"
                  disabled={source.isFetching}
                  onClick={() => void source.refetch()}
                >
                  Tải lại nguồn
                </button>
              )}
              {source.isPending ? (
                <p role="status">Đang tải nguồn…</p>
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
                      Ứng dụng giữ nguyên nguồn đã chọn. Nhập đúng doanh nghiệp
                      cần nghiên cứu ở phía trên.
                    </p>
                  </>
                )
              )}
            </section>
          ) : (
            <label>
              Email gốc (không bắt buộc)
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
                placeholder="Dán nguyên văn email khách gửi, gồm tiêu đề và nội dung…"
              />
              <small>
                Chọn email trực tiếp từ Gmail tại{" "}
                <Link className="source-picker-link" to="/inputs">
                  Email & cuộc họp
                </Link>
                .
              </small>
            </label>
          )}
          <label>
            Yêu cầu nghiên cứu (không bắt buộc)
            <textarea
              rows={5}
              maxLength={12000}
              value={input.context ?? ""}
              onChange={(e) => setInput({ ...input, context: e.target.value })}
              placeholder="Cần tìm hiểu gì về doanh nghiệp? Mục tiêu cuộc trao đổi là gì?"
            />
            <small>
              Hướng dẫn riêng cho trợ lý; không phải lời khách gửi trong email.
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
          {mutation.isPending ? "Đang tạo…" : "Tạo nghiên cứu"}
        </button>
      </form>
    </>
  );
}
