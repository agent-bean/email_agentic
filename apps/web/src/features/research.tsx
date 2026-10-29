import { useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { api, post, type Run, type ResearchInput } from '../lib/api';
import { ErrorMessage, Status } from '../components/status';
import { Attachments, MeetingSource, type SourceInput } from './inbox';

export function Overview() {
  const query = useQuery({ queryKey: ['runs'], queryFn: () => api<Run[]>('/runs'), refetchInterval: 5000 });
  const runs = query.data ?? [];
  return <><header><div><p className="eyebrow">KHÔNG GIAN LÀM VIỆC</p><h1>Tổng quan</h1><p className="muted">Nghiên cứu doanh nghiệp, chuẩn bị báo cáo và duyệt email trước khi gửi.</p></div><Link className="button" to="/research/new">Nghiên cứu mới</Link></header>
    <section className="stats"><article><span>Nghiên cứu</span><strong>{query.data ? runs.length : '—'}</strong></article><article><span>Chờ xác nhận</span><strong>{query.data ? runs.filter(r => r.status === 'awaiting_identity').length : '—'}</strong></article><article><span>Có báo cáo</span><strong>{query.data ? runs.filter(r => r.status === 'draft_ready').length : '—'}</strong></article></section>
    <section className="panel"><div className="section-heading"><h2>Nghiên cứu gần đây</h2><span className="muted">Mới nhất trước</span></div><ErrorMessage error={query.error} />
      {query.isPending ? <p role="status">Đang tải…</p> : query.isError ? <button className="secondary" onClick={() => void query.refetch()}>Thử lại</button> : runs.length === 0 ? <div className="empty"><h3>Chưa có nghiên cứu</h3><p>Tạo nghiên cứu đầu tiên để thu thập thông tin doanh nghiệp.</p></div> : <div className="run-list">{runs.map(run => <Link to={`/research/${run.id}`} key={run.id}><div className="run-company"><strong>{run.company_name}</strong><small>{run.domain}</small></div><Status value={run.status} /><span className="run-date muted">{new Date(run.created_at).toLocaleString('vi-VN')}</span><span className="run-arrow" aria-hidden="true">→</span></Link>)}</div>}
    </section></>;
}

export function NewResearch() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const sourceId = params.get('input');
  const source = useQuery({ queryKey: ['input', sourceId], queryFn: () => api<SourceInput>(`/inputs/${sourceId}`), enabled: Boolean(sourceId) });
  const submission = useRef({ body: '', key: '' });
  const [input, setInput] = useState<ResearchInput>({ company_name: '', domain: '', context: '' });
  const mutation = useMutation({ mutationFn: () => { const payload = sourceId ? { ...input, ...(source.data?.kind === 'meeting' ? {source_meeting_id: sourceId} : {source_input_id: sourceId}) } : input; const body = JSON.stringify(payload); if (submission.current.body !== body) submission.current = { body, key: crypto.randomUUID() }; return post<{ id: string }>('/runs', payload, submission.current.key); }, onSuccess: value => navigate(`/research/${value.id}`) });
  return <><header><div><p className="eyebrow">NGHIÊN CỨU DOANH NGHIỆP</p><h1>Nghiên cứu mới</h1><p className="muted">Xác nhận đúng doanh nghiệp, rồi thu thập thông tin có nguồn.</p></div></header>
    <form className="panel form" onSubmit={event => { event.preventDefault(); mutation.mutate(); }}>
      <label>Tên doanh nghiệp<input required minLength={2} maxLength={200} value={input.company_name} onChange={e => setInput({ ...input, company_name: e.target.value })} placeholder="Ví dụ: FPT Software" /></label>
      <label>Domain chính thức<input required value={input.domain} onChange={e => setInput({ ...input, domain: e.target.value })} placeholder="fptsoftware.com" /><small>Chỉ nhập domain, không có https:// hoặc đường dẫn.</small></label>
      {sourceId ? <section><h2>{source.data?.kind === 'meeting' ? 'Cuộc họp từ Google Calendar' : 'Email từ Gmail'}</h2><ErrorMessage error={source.error} />{source.isPending ? <p role="status">Đang tải nguồn…</p> : source.data && <>{source.data.kind === 'meeting' ? <MeetingSource event={source.data.content} /> : <pre className="preserve">{source.data.content.source_text}</pre>}<Attachments items={source.data.content.attachments ?? []} /><p className="muted">Ứng dụng giữ nguyên nguồn đã chọn. Nhập đúng doanh nghiệp cần nghiên cứu ở phía trên.</p></>}</section> : <label>Email gốc (không bắt buộc)<textarea rows={8} maxLength={30000} value={input.source_email ?? ''} onChange={e => setInput({ ...input, source_email: e.target.value === '' ? null : e.target.value })} placeholder="Dán nguyên văn email khách gửi, gồm tiêu đề và nội dung…" /><small>Để chọn email trực tiếp từ Gmail, mở trang Email & cuộc họp.</small></label>}
      <label>Yêu cầu nghiên cứu (không bắt buộc)<textarea rows={5} maxLength={12000} value={input.context ?? ''} onChange={e => setInput({ ...input, context: e.target.value })} placeholder="Cần tìm hiểu gì về doanh nghiệp? Mục tiêu cuộc trao đổi là gì?" /><small>Hướng dẫn riêng cho trợ lý; không phải lời khách gửi trong email.</small></label>
      <ErrorMessage error={mutation.error} /><button disabled={mutation.isPending || Boolean(sourceId && (!source.data || !['email', 'meeting'].includes(source.data.kind)))}>{mutation.isPending ? 'Đang tạo…' : 'Tạo nghiên cứu'}</button>
    </form></>;
}
