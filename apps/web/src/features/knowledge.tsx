import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { endpoints } from '../lib/api';
import { ErrorMessage, Status } from '../components/status';
import './knowledge.css';
import { useI18n, type Translate } from '../lib/i18n';

const pageSize = 12;

function reportTitle(content: string, t: Translate) {
  const heading = content.match(/^#{1,6}\s+(.+?)\s*#*$/m)?.[1];
  return (heading ?? content.split('\n').find((line) => line.trim()) ?? t('Báo cáo chưa có tiêu đề', 'Untitled report'))
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[*_`]/g, '').trim().slice(0, 180);
}

function savedDate(value: string, locale: string, t: Translate) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? t('Chưa có ngày lưu', 'Save date unavailable') : date.toLocaleString(locale);
}

export function Knowledge() {
  const { t, locale } = useI18n();
  const [params, setParams] = useSearchParams();
  const titleRef = useRef<HTMLHeadingElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const previousReport = useRef<string | null>(null);
  const reportId = params.get('report');
  const search = params.get('q') ?? '';
  const status = ['draft', 'approved'].includes(params.get('status') ?? '') ? params.get('status')! : '';
  const query = useQuery({ queryKey: ['knowledge'], queryFn: ({ signal }) => endpoints.knowledge(signal) });
  const reports = query.data ?? [];
  const filtered = reports.filter((report) => (!status || report.status === status)
    && `${reportTitle(report.content, t)}\n${report.content}`.toLocaleLowerCase(locale).includes(search.trim().toLocaleLowerCase(locale)));
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const rawPage = Number(params.get('page') ?? 1);
  const page = Math.min(pageCount, Math.max(1, Number.isSafeInteger(rawPage) ? rawPage : 1));
  const selected = reports.find((report) => report.id === reportId);
  const listParams = new URLSearchParams(params);
  listParams.delete('report');
  const listUrl = `/knowledge${listParams.size ? `?${listParams}` : ''}`;

  useEffect(() => {
    if (reportId && !query.isPending) titleRef.current?.focus();
    if (!reportId && previousReport.current) searchRef.current?.focus();
    previousReport.current = reportId;
  }, [reportId, query.isPending]);

  function updateFilter(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    next.delete('page');
    setParams(next, { replace: true });
  }

  return <div className="knowledge-workspace">
    <header>
      <div><p className="eyebrow">{t("NGỮ CẢNH ĐƯỢC LƯU GIỮ", "SAVED CONTEXT")}</p><h1>{t("Kho tri thức", "Knowledge library")}</h1>
        <p className="muted">{t("Báo cáo lưu lại để tham khảo trong các nghiên cứu tiếp theo. Thông tin cần được đối chiếu lại khi sử dụng.", "Reports retained for future research. Recheck the information before using it.")}</p></div>
      <button className="secondary" disabled={query.isFetching} onClick={() => void query.refetch()}>{t("Làm mới", "Refresh")}</button>
    </header>
    <ErrorMessage error={query.error} />
    {query.isPending ? <section className="panel" role="status">{t("Đang tải báo cáo…", "Loading reports\u2026")}</section>
      : query.isError ? <section className="panel"><p>{t("Không tải được kho tri thức. Chọn Làm mới để thử lại.", "Could not load the knowledge library. Select Refresh to retry.")}</p></section>
      : reportId ? <section className="panel knowledge-reader">
        <Link className="knowledge-back" to={listUrl}>{t("← Danh sách báo cáo", "\u2190 Report library")}</Link>
        {selected ? <>
          <h2 ref={titleRef} tabIndex={-1}>{reportTitle(selected.content, t)}</h2>
          <div className="knowledge-meta"><Status value={selected.status} /><span>{t('Lưu', 'Saved')} {savedDate(selected.created_at, locale, t)}</span>
            <Link to={`/research/${encodeURIComponent(selected.run_id)}`}>{t("Mở nghiên cứu gốc", "Open original research")}</Link></div>
          <p className="knowledge-context">{selected.status === 'approved'
            ? t("Đã duyệt và lưu: ngữ cảnh tham khảo có thể được dùng lại cho nghiên cứu sau, không phải xác nhận rằng mọi thông tin vẫn còn đúng.", "Approved and saved: context can be reused in future research. Approval does not confirm that all information is still current.")
            : selected.status === 'draft' ? t("Bản nháp được lưu tự động, chưa được duyệt. Kiểm tra nghiên cứu gốc trước khi sử dụng.", "Automatically saved draft, not yet approved. Check the original research before using it.")
              : t("Kiểm tra trạng thái và nghiên cứu gốc trước khi sử dụng nội dung này.", "Check the status and original research before using this content.")}</p>
          {selected.content.trim() ? <article className="markdown" aria-label={t("Nội dung báo cáo", "Report content")}>
            <Markdown remarkPlugins={[remarkGfm]} skipHtml disallowedElements={['img']} components={{
              table: ({ children }) => <div className="table-scroll" role="region" aria-label={t("Bảng báo cáo; cuộn ngang để xem thêm", "Report table; scroll horizontally to see more")} tabIndex={0}><table>{children}</table></div>,
            }}>{selected.content}</Markdown>
          </article> : <p>{t("Báo cáo này chưa có nội dung.", "This report has no content yet.")}</p>}
        </> : <><h2 ref={titleRef} tabIndex={-1}>{t("Không tìm thấy báo cáo", "Report not found")}</h2><p>{t("Báo cáo không nằm trong danh sách hiện có (tối đa 100 bản gần nhất). Mở lại danh sách hoặc làm mới để kiểm tra.", "This report is not in the current list (up to 100 most recent records). Return to the library or refresh to check.")}</p></>}
      </section> : <section className="panel knowledge-library" aria-label={t("Thư viện báo cáo", "Report library")}>
        <div className="knowledge-filters">
          <label>{t("Tìm trong báo cáo", "Search reports")}<input ref={searchRef} type="search" value={search} placeholder={t("Tiêu đề hoặc nội dung…", "Title or content\u2026")} onChange={(event) => updateFilter('q', event.target.value)} /></label>
          <label>{t("Trạng thái", "Status")}<select value={status} onChange={(event) => updateFilter('status', event.target.value)}><option value="">{t("Tất cả", "All")}</option><option value="approved">{t("Đã duyệt", "Approved")}</option><option value="draft">{t("Bản nháp", "Draft")}</option></select></label>
          {(search || status) && <button className="secondary" onClick={() => setParams({})}>{t("Xóa bộ lọc", "Clear filters")}</button>}
        </div>
        <p className="muted" role="status">{filtered.length} / {reports.length} {t('báo cáo · Tối đa 100 bản gần nhất', 'reports · Up to 100 most recent records')}</p>
        {!reports.length ? <div className="empty"><h2>{t("Chưa có báo cáo được lưu", "No saved reports yet")}</h2><p>{t("Bản nháp được lưu khi tạo báo cáo. Bản đã duyệt xuất hiện sau khi duyệt và lưu vào kho tri thức.", "Drafts are saved when reports are generated. Approved versions appear after approval and saving to the knowledge library.")}</p><Link to="/">{t("Mở danh sách nghiên cứu", "Open research list")}</Link></div>
          : !filtered.length ? <div className="empty"><h2>{t("Không có báo cáo phù hợp", "No matching reports")}</h2><p>{t("Thử từ khóa khác hoặc xóa bộ lọc.", "Try another search or clear the filters.")}</p></div>
            : <>
              <ul className="knowledge-list">{filtered.slice((page - 1) * pageSize, page * pageSize).map((report) => {
                const target = new URLSearchParams(params);
                target.set('report', report.id);
                return <li key={report.id}><Link to={`/knowledge?${target}`} className="knowledge-card">
                  <span className="knowledge-card-title">{reportTitle(report.content, t)}</span>{' '}
                  <span className="knowledge-meta"><Status value={report.status} />{' '}<span>{t('Lưu', 'Saved')} {savedDate(report.created_at, locale, t)}</span></span>{' '}
                  <span className="knowledge-open">{t("Đọc báo cáo →", "Read report \u2192")}</span>
                </Link></li>;
              })}</ul>
              {pageCount > 1 && <nav className="knowledge-pagination" aria-label={t("Trang báo cáo", "Report pages")}>
                <button className="secondary" disabled={page === 1} onClick={() => { const next = new URLSearchParams(params); next.set('page', String(page - 1)); setParams(next); }}>{t("Trang trước", "Previous page")}</button>
                <span>{t('Trang', 'Page')} {page} / {pageCount}</span>
                <button className="secondary" disabled={page === pageCount} onClick={() => { const next = new URLSearchParams(params); next.set('page', String(page + 1)); setParams(next); }}>{t("Trang sau", "Next page")}</button>
              </nav>}
            </>}
      </section>}
  </div>;
}
