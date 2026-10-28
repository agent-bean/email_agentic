import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Markdown from 'react-markdown';
import { api, post, type Detail, type Report, type ReportEdit } from '../lib/api';
import { ErrorMessage, Status } from '../components/status';

const qualityLabels: Record<string, string> = { cited_sources: 'Nguồn được trích dẫn', source_target_met: 'Đủ nguồn tham khảo', elapsed_seconds: 'Thời gian tạo nháp (giây)', target_seconds: 'Mục tiêu thời gian (giây)', time_target_met: 'Đạt mục tiêu thời gian', factual_accuracy: 'Độ chính xác', completeness: 'Độ đầy đủ', readiness: 'Sẵn sàng sử dụng', branch_failures: 'Nhánh gặp lỗi', human_edited: 'Đã chỉnh sửa', content_review: 'Duyệt nội dung' };
const qualityValue = (value: unknown) => value === true ? 'Đạt' : value === false ? 'Chưa đạt' : ['requires_review', 'required'].includes(String(value)) ? 'Cần kiểm tra' : value === 'not_evaluated' ? 'Chưa đánh giá' : Array.isArray(value) ? value.join(', ') || 'Không có' : typeof value === 'number' ? value.toFixed(1) : String(value);

function ReportEditor({ report, runId, refresh }: { report: Report; runId: string; refresh: () => void }) {
  const [edit, setEdit] = useState<ReportEdit>({ version: report.version, markdown: report.markdown,
    email_subject: report.email_subject, email_body: report.email_body,
    recipients: { to: report.recipients.to ?? [], cc: report.recipients.cc ?? [], bcc: report.recipients.bcc ?? [] },
    send_email: report.send_email, save_kb: report.save_kb });
  const save = useMutation({ mutationFn: () => api(`/runs/${runId}/report`, { method: 'PUT', body: JSON.stringify(edit) }), onSuccess: refresh });
  return <details className="editor"><summary>Sửa nội dung và lựa chọn phát hành</summary><form className="form" onSubmit={e => { e.preventDefault(); save.mutate(); }}>
    <label>Báo cáo Markdown<textarea rows={16} value={edit.markdown} onChange={e => setEdit({ ...edit, markdown: e.target.value })} /></label>
    <label>Tiêu đề email<input value={edit.email_subject} onChange={e => setEdit({ ...edit, email_subject: e.target.value })} /></label>
    <label>Nội dung email<textarea rows={7} value={edit.email_body} onChange={e => setEdit({ ...edit, email_body: e.target.value })} /></label>
    {(['to', 'cc', 'bcc'] as const).map(key => <label key={key}>{key.toUpperCase()}<input value={(edit.recipients?.[key] ?? []).join(', ')} onChange={e => setEdit({ ...edit, recipients: { ...edit.recipients, [key]: e.target.value.split(',').map(v => v.trim()).filter(Boolean) } })} /></label>)}
    <label className="check"><input type="checkbox" checked={edit.send_email} onChange={e => setEdit({ ...edit, send_email: e.target.checked })} />Gửi email sau duyệt</label>
    <label className="check"><input type="checkbox" checked={edit.save_kb} onChange={e => setEdit({ ...edit, save_kb: e.target.checked })} />Lưu KB sau duyệt</label>
    <p className="muted">Lưu thay đổi sẽ tạo phiên bản mới và yêu cầu duyệt lại.</p><ErrorMessage error={save.error} /><button disabled={save.isPending}>Lưu phiên bản mới</button>
  </form></details>;
}

export function ResearchDetail() {
  const id = useParams().id!;
  const client = useQueryClient();
  const refresh = () => { void client.invalidateQueries({ queryKey: ['run', id] }); void client.invalidateQueries({ queryKey: ['runs'] }); };
  const query = useQuery({ queryKey: ['run', id], queryFn: () => api<Detail>(`/runs/${id}`), refetchInterval: 3000 });
  const confirm = useMutation({ mutationFn: () => post(`/runs/${id}/identity`, { version: query.data?.run.version }), onSuccess: refresh });
  const decision = useMutation({ mutationFn: ({ approvalId, approve }: { approvalId: string; approve: boolean }) => post(`/approvals/${approvalId}/decision`, { approve }), onSuccess: refresh });
  if (query.isPending) return <p>Đang tải nghiên cứu…</p>;
  if (!query.data) return <ErrorMessage error={query.error} />;
  const { run, reports, approvals, evidence, actions, branches } = query.data;
  const report = reports[0];
  const approval = approvals.find(item => item.report_id === report?.id);
  return <><header><div><p className="eyebrow">NGHIÊN CỨU DOANH NGHIỆP</p><h1>{run.company_name}</h1><p className="muted">{run.domain}</p></div><Status value={run.status} /></header>
    <ErrorMessage error={query.error || confirm.error || decision.error} />
    {run.status === 'awaiting_identity' && <section className="panel notice"><h2>Xác nhận đúng doanh nghiệp</h2><p>Domain <strong>{run.domain}</strong> có đúng pháp nhân bạn muốn nghiên cứu?</p><button disabled={confirm.isPending} onClick={() => confirm.mutate()}>Xác nhận doanh nghiệp này</button></section>}
    {run.error_code && <p className="error">Tác vụ gặp lỗi: {run.error_code}. Kết quả đã lưu vẫn được giữ.</p>}
    <div className="detail-grid"><section className="panel"><h2>{report ? `Bản nháp · phiên bản ${report.version}` : 'Tiến độ thu thập'}</h2>
      {report ? <><div className="markdown"><Markdown skipHtml disallowedElements={['img']}>{report.markdown}</Markdown></div><ReportEditor key={report.id} report={report} runId={id} refresh={refresh} /></> : <p className="muted">Kết quả sẽ xuất hiện khi worker hoàn tất bước nghiên cứu.</p>}
    </section><div>
      <section className="panel"><h2>Các nhánh xử lý</h2>{branches.length === 0 ? <p className="muted">Chưa có kết quả nhánh.</p> : branches.map((b, i) => <div className="row" key={i}><span>{String(b.branch)}</span><Status value={String((b.result as Record<string, unknown>)?.status)} /></div>)}</section>
      {report && <section className="panel"><h2>Gói phát hành</h2><h3>{report.email_subject}</h3><p className="preserve">{report.email_body}</p><p><strong>TO:</strong> {(report.recipients.to ?? []).join(', ') || 'Chưa chọn'}</p><p><strong>CC:</strong> {(report.recipients.cc ?? []).join(', ') || '—'}</p><p><strong>BCC:</strong> {(report.recipients.bcc ?? []).join(', ') || '—'}</p><p>Gửi email: {report.send_email ? 'Có' : 'Không'} · Lưu KB: {report.save_kb ? 'Có' : 'Không'}</p>
        {approval && <><Status value={approval.status} /><p className="muted">Hết hạn: {new Date(approval.expires_at).toLocaleString('vi-VN')}</p>{approval.status === 'pending' && <div className="actions"><button disabled={decision.isPending} onClick={() => decision.mutate({ approvalId: approval.id, approve: true })}>Duyệt phiên bản này</button><button className="secondary" disabled={decision.isPending} onClick={() => decision.mutate({ approvalId: approval.id, approve: false })}>Từ chối</button></div>}</>}
        {actions.map(action => <p key={action.id}>{action.kind}: <Status value={action.status} /></p>)}
      </section>}
      <section className="panel"><h2>Nguồn tham khảo <small>({evidence.length})</small></h2>{evidence.map((e, i) => <p key={i}><a href={String(e.url)} target="_blank" rel="noopener noreferrer">{String(e.title || e.url)}</a></p>)}</section>
      {report && <section className="panel"><h2>Kiểm tra chất lượng</h2><dl>{Object.entries(report.quality).map(([key, value]) => <div key={key}><dt>{qualityLabels[key] ?? key}</dt><dd>{qualityValue(value)}</dd></div>)}</dl><p className="muted">Có nháp không đồng nghĩa đã đạt nghiệm thu. Dữ kiện và mức sẵn sàng cần review.</p></section>}
    </div></div></>;
}
