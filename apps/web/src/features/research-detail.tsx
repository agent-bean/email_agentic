import { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Markdown from 'react-markdown';
import { api, post, type Detail, type Report, type ReportEdit } from '../lib/api';
import { ErrorMessage, Status } from '../components/status';
import { businessDisplayText } from '../lib/business-display';

const qualityLabels: Record<string, string> = { cited_sources: 'Nguồn trích dẫn', source_target_met: 'Đủ số nguồn mục tiêu', elapsed_seconds: 'Thời gian tạo nháp (giây)', target_seconds: 'Mục tiêu thời gian (giây)', time_target_met: 'Đạt mục tiêu thời gian', factual_accuracy: 'Độ chính xác', completeness: 'Độ đầy đủ', readiness: 'Sẵn sàng sử dụng', branch_failures: 'Bước gặp lỗi', search_failures: 'Lỗi tìm kiếm', page_reads: 'Đọc trang web', citation_correction_attempted: 'Đã yêu cầu sửa link nguồn', human_edited: 'Đã chỉnh sửa', content_review: 'Kiểm tra nội dung', succeeded: 'Thành công', failed: 'Lỗi', not_selected: 'Không chọn đọc' };
function qualityValue(value: unknown): string {
  if (value == null) return '—';
  if (typeof value === 'boolean') return value ? 'Có' : 'Không';
  if (Array.isArray(value)) return value.map(qualityValue).join(', ') || 'Không có';
  if (typeof value === 'object') return Object.entries(value).map(([key, item]) => `${qualityLabels[key] ?? key}: ${qualityValue(item)}`).join(' · ');
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(1);
  return ({ requires_review: 'Cần kiểm tra', required: 'Cần kiểm tra', not_evaluated: 'Chưa đánh giá' } as Record<string, string>)[String(value)] ?? String(value);
}
const branchLabels: Record<string, string> = { company: 'Doanh nghiệp', email: 'Email', calendar: 'Lịch họp', web: 'Nguồn web', memory: 'Ngữ cảnh đã lưu', knowledge: 'Kho tri thức' };
const dateTime = (value: string) => new Date(value).toLocaleString('vi-VN');

function ReportEditor({ report, runId, refresh, onDirty }: { report: Report; runId: string; refresh: () => void; onDirty: (dirty: boolean) => void }) {
  const initial: ReportEdit = { version: report.version, markdown: report.markdown, email_subject: report.email_subject, email_body: report.email_body, recipients: { to: report.recipients.to ?? [], cc: report.recipients.cc ?? [], bcc: report.recipients.bcc ?? [] }, send_email: report.send_email, save_kb: report.save_kb };
  const [edit, setEdit] = useState(initial);
  const dirty = JSON.stringify(initial) !== JSON.stringify(edit);
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    const guardNavigation = (event: MouseEvent) => {
      const link = event.target instanceof Element ? event.target.closest('a[href]') : null;
      if (!(link instanceof HTMLAnchorElement) || link.target === '_blank' || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const target = new URL(link.href);
      if (target.pathname === window.location.pathname && target.search === window.location.search) return;
      if (!window.confirm('Có thay đổi chưa lưu. Rời trang và bỏ các thay đổi này?')) { event.preventDefault(); event.stopPropagation(); }
    };
    window.addEventListener('beforeunload', warn);
    document.addEventListener('click', guardNavigation, true);
    return () => { window.removeEventListener('beforeunload', warn); document.removeEventListener('click', guardNavigation, true); };
  }, [dirty]);
  const save = useMutation({ mutationFn: () => api(`/runs/${runId}/report`, { method: 'PUT', body: JSON.stringify(edit) }), onSuccess: refresh });
  return <details className="panel editor"><summary>Chỉnh sửa nội dung & tùy chọn</summary><form className="form" onSubmit={e => { e.preventDefault(); save.mutate(); }}>
    <p className="muted">Lưu sẽ tạo phiên bản mới và yêu cầu duyệt lại. Bản đang chỉnh sửa chưa được dùng để gửi.</p>
    <fieldset disabled={save.isPending}><legend>Báo cáo · nội bộ</legend><label>Nội dung Markdown<textarea rows={16} value={edit.markdown} onChange={e => setEdit({ ...edit, markdown: e.target.value })} /></label></fieldset>
    <fieldset disabled={save.isPending}><legend>Email nháp · gửi khách / đối tác</legend><label>Tiêu đề<input value={edit.email_subject} onChange={e => setEdit({ ...edit, email_subject: e.target.value })} /></label><label>Nội dung email<textarea rows={9} value={edit.email_body} onChange={e => setEdit({ ...edit, email_body: e.target.value })} /></label></fieldset>
    <fieldset disabled={save.isPending}><legend>Người nhận</legend><p className="muted">Phân cách các địa chỉ bằng dấu phẩy.</p>{(['to', 'cc', 'bcc'] as const).map(key => <label key={key}>{key.toUpperCase()}<input value={(edit.recipients?.[key] ?? []).join(', ')} onChange={e => setEdit({ ...edit, recipients: { ...edit.recipients, [key]: e.target.value.split(',').map(v => v.trim()).filter(Boolean) } })} /></label>)}</fieldset>
    <fieldset disabled={save.isPending}><legend>Sau khi duyệt</legend><label className="check"><input type="checkbox" checked={edit.send_email} onChange={e => setEdit({ ...edit, send_email: e.target.checked })} />Gửi email tới người nhận</label><label className="check"><input type="checkbox" checked={edit.save_kb} onChange={e => setEdit({ ...edit, save_kb: e.target.checked })} />Lưu báo cáo vào kho tri thức</label></fieldset>
    <ErrorMessage error={save.error} /><div className="save-bar"><span className="muted" role="status">{dirty ? 'Có thay đổi chưa lưu' : 'Chưa có thay đổi'}</span><button disabled={save.isPending || !dirty}>{save.isPending ? 'Đang lưu…' : 'Lưu phiên bản mới'}</button></div>
  </form></details>;
}

export function ResearchDetail() {
  const id = useParams().id!;
  const [params, setParams] = useSearchParams();
  const view = params.get('view') === 'email' ? 'email' : 'report';
  const [dirty, setDirty] = useState(false);
  const client = useQueryClient();
  const refresh = () => { void client.invalidateQueries({ queryKey: ['run', id] }); void client.invalidateQueries({ queryKey: ['runs'] }); };
  const query = useQuery({ queryKey: ['run', id], queryFn: () => api<Detail>(`/runs/${id}`), refetchInterval: 3000 });
  const confirm = useMutation({ mutationFn: () => post(`/runs/${id}/identity`, { version: query.data?.run.version }), onSuccess: refresh });
  const decision = useMutation({ mutationFn: ({ approvalId, approve }: { approvalId: string; approve: boolean }) => post(`/approvals/${approvalId}/decision`, { approve }), onSuccess: refresh });
  if (query.isPending) return <section className="panel loading" role="status">Đang tải nghiên cứu…</section>;
  if (!query.data) return <><Link className="back-link" to="/">← Nghiên cứu</Link><ErrorMessage error={query.error} /><button className="secondary" onClick={() => void query.refetch()}>Thử lại</button></>;
  const { run, reports, approvals, evidence, actions, branches } = query.data;
  const report = reports[0];
  const approval = approvals.find(item => item.report_id === report?.id);
  const expired = approval ? new Date(approval.expires_at).getTime() <= Date.now() : false;
  return <><Link className="back-link" to="/">← Nghiên cứu</Link><header><div><p className="eyebrow">NGHIÊN CỨU DOANH NGHIỆP</p><h1>{businessDisplayText(run.company_name)}</h1><p className="muted">{run.domain} <span className="separator">/</span> {dateTime(run.created_at)}</p></div><Status value={run.status} /></header>
    <ErrorMessage error={query.error || confirm.error || decision.error} />
    {run.status === 'awaiting_identity' && <section className="panel notice"><h2>Xác nhận doanh nghiệp</h2><p><strong>{run.domain}</strong> có đúng doanh nghiệp bạn muốn nghiên cứu?</p><button disabled={confirm.isPending} onClick={() => confirm.mutate()}>{confirm.isPending ? 'Đang xác nhận…' : 'Xác nhận doanh nghiệp'}</button></section>}
    {run.error_code && <p className="error">Nghiên cứu gặp lỗi: {run.error_code}. Kết quả đã lưu vẫn được giữ.</p>}
    <div className="detail-grid"><div className="detail-content">
      {report ? <><nav className="view-switch" aria-label="Nội dung nghiên cứu">{(['report', 'email'] as const).map(tab => <button key={tab} className={view === tab ? 'selected' : ''} aria-current={view === tab ? 'page' : undefined} onClick={() => setParams(previous => { const next = new URLSearchParams(previous); next.set('view', tab); return next; })}>{tab === 'report' ? 'Báo cáo' : 'Email nháp'}</button>)}<a className="review-link" href="#review">Duyệt v{report.version} ↓</a></nav>
      {view === 'email' && <section className="panel reading-panel original-context" aria-labelledby="original-context-title"><p className="eyebrow">ĐỐI CHIẾU TRƯỚC KHI DUYỆT</p><h2 id="original-context-title">Mail gốc / bối cảnh đầu vào</h2><p className="surface-description">Nội dung được cung cấp khi tạo nghiên cứu. Ứng dụng chưa liên kết nghiên cứu này với mail gốc trên Gmail.</p>{run.context?.trim() ? <div className="preserve original-context-body">{businessDisplayText(run.context)}</div> : <p className="muted">Chưa có mail gốc hoặc bối cảnh trao đổi. Cần nội dung mail khách để đối chiếu bản trả lời.</p>}</section>}
      <section className="panel reading-panel"><div className="surface-heading"><div><p className="eyebrow">{view === 'report' ? 'DÙNG NỘI BỘ' : 'GỬI KHÁCH / ĐỐI TÁC'}</p><h2>{view === 'report' ? 'Báo cáo' : 'Email nháp'}</h2></div><span className="version">v{report.version}</span></div>
        {view === 'report' ? <><p className="surface-description">Thông tin doanh nghiệp, nguồn tham khảo và phân tích để chuẩn bị trao đổi.</p><div className="markdown"><Markdown skipHtml disallowedElements={['img']}>{report.markdown}</Markdown></div></> : <><p className="surface-description">Bản nháp đang lưu trong ứng dụng, chưa lưu vào Gmail hoặc gắn với cuộc trao đổi trên Gmail.</p>{Number(run.config.prompt_version ?? 0) < 5 && <p className="notice inline-notice"><strong>Email này được soạn theo hướng dẫn cũ;</strong> cần soạn lại trước khi gửi khách.</p>}<dl className="email-addresses">{(['to', 'cc', 'bcc'] as const).map(key => <div key={key}><dt>{key.toUpperCase()}</dt><dd>{(report.recipients[key] ?? []).join(', ') || (key === 'to' ? 'Chưa chọn người nhận' : '—')}</dd></div>)}</dl><h3 className="email-subject">{report.email_subject || 'Chưa có tiêu đề'}</h3><div className="preserve email-body">{report.email_body || 'Chưa có nội dung email.'}</div></>}
      </section><ReportEditor key={report.id} report={report} runId={id} refresh={refresh} onDirty={setDirty} />
      <details className="panel source-panel"><summary>Nguồn tham khảo <span className="muted">({evidence.length})</span></summary>{evidence.length ? <ol className="source-list">{evidence.map((e, i) => <li key={i}><a href={String(e.url)} target="_blank" rel="noopener noreferrer">{String(e.title || e.url)}</a></li>)}</ol> : <p className="muted">Chưa có nguồn tham khảo.</p>}</details></> : <section className="panel"><h2>Tiến độ nghiên cứu</h2><p className="muted">{run.status === 'failed' ? 'Chưa tạo được báo cáo. Xem lỗi và tiến độ từng bước bên cạnh.' : 'Báo cáo và email nháp sẽ xuất hiện sau khi nghiên cứu hoàn tất.'}</p></section>}
    </div><div className="detail-sidebar">
      {report && <section id="review" className="panel review-panel"><p className="eyebrow">KIỂM TRA & DUYỆT</p><div className="surface-heading"><h2>Phiên bản {report.version}</h2>{approval && <Status value={expired && approval.status === 'pending' ? 'expired' : approval.status} />}</div><p className="muted">Kiểm tra báo cáo, email, người nhận và các tùy chọn bên dưới trước khi duyệt.</p><dl className="review-summary"><div><dt>Báo cáo & email</dt><dd>v{report.version}</dd></div>{(['to', 'cc', 'bcc'] as const).map(key => <div key={key}><dt>{key.toUpperCase()}</dt><dd>{(report.recipients[key] ?? []).join(', ') || '—'}</dd></div>)}<div><dt>Gửi email</dt><dd>{report.send_email ? 'Có' : 'Không gửi'}</dd></div><div><dt>Lưu kho tri thức</dt><dd>{report.save_kb ? 'Có' : 'Không lưu'}</dd></div></dl>
        {Number(run.config.prompt_version ?? 0) < 5 && <p className="inline-notice notice">Email này được soạn theo hướng dẫn cũ; cần soạn lại trước khi gửi khách.</p>}<p className="review-consequence">{report.send_email ? 'Duyệt sẽ cho phép gửi email này tới người nhận đã chọn.' : 'Đang tắt gửi email. Duyệt phiên bản này sẽ không gửi email.'}</p>{approval && <><p className="muted meta">Hết hạn: {dateTime(approval.expires_at)}</p>{approval.status === 'pending' && !expired && <div className="actions review-actions"><button disabled={decision.isPending || dirty} onClick={() => decision.mutate({ approvalId: approval.id, approve: true })}>{decision.isPending ? 'Đang xử lý…' : `Duyệt v${report.version}`}</button><button className="secondary" disabled={decision.isPending || dirty} onClick={() => decision.mutate({ approvalId: approval.id, approve: false })}>Từ chối</button></div>}</>}{dirty && <p role="status" className="inline-notice notice">Lưu thay đổi trước khi duyệt phiên bản mới.</p>}{actions.length > 0 && <div className="action-results"><h3>Kết quả gửi / lưu</h3>{actions.map(action => <p key={action.id}>{action.kind}: <Status value={action.status} /></p>)}</div>}
      </section>}
      <section className="panel"><h2>Tiến độ từng bước</h2>{branches.length === 0 ? <p className="muted">Chưa có kết quả.</p> : branches.map((b, i) => <div className="row" key={i}><span>{branchLabels[String(b.branch)] ?? String(b.branch)}</span><Status value={String((b.result as Record<string, unknown>)?.status ?? 'pending')} /></div>)}</section>
      {report && <details className="panel quality-panel"><summary>Kiểm tra chất lượng</summary><p className="muted">Cần kiểm tra dữ kiện và nguồn trước khi sử dụng.</p><dl>{Object.entries(report.quality).map(([key, value]) => <div key={key}><dt>{qualityLabels[key] ?? key}</dt><dd>{qualityValue(value)}</dd></div>)}</dl></details>}
    </div></div></>;
}
