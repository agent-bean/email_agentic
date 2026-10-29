import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { api, post, type Run, type ResearchInput } from '../lib/api';
import { ErrorMessage, Status } from '../components/status';
import { businessDisplayText } from '../lib/business-display';

export function Overview() {
  const query = useQuery({ queryKey: ['runs'], queryFn: () => api<Run[]>('/runs'), refetchInterval: 5000 });
  const runs = query.data ?? [];
  return <><header><div><p className="eyebrow">KHÔNG GIAN LÀM VIỆC</p><h1>Tổng quan</h1><p className="muted">Nghiên cứu doanh nghiệp, chuẩn bị báo cáo và duyệt email trước khi gửi.</p></div><Link className="button" to="/research/new">Nghiên cứu mới</Link></header>
    <section className="stats"><article><span>Nghiên cứu</span><strong>{query.data ? runs.length : '—'}</strong></article><article><span>Chờ xác nhận</span><strong>{query.data ? runs.filter(r => r.status === 'awaiting_identity').length : '—'}</strong></article><article><span>Có báo cáo</span><strong>{query.data ? runs.filter(r => r.status === 'draft_ready').length : '—'}</strong></article></section>
    <section className="panel"><div className="section-heading"><h2>Nghiên cứu gần đây</h2><span className="muted">Mới nhất trước</span></div><ErrorMessage error={query.error} />
      {query.isPending ? <p role="status">Đang tải…</p> : query.isError ? <button className="secondary" onClick={() => void query.refetch()}>Thử lại</button> : runs.length === 0 ? <div className="empty"><h3>Chưa có nghiên cứu</h3><p>Tạo nghiên cứu đầu tiên để thu thập thông tin doanh nghiệp.</p></div> : <div className="run-list">{runs.map(run => <Link to={`/research/${run.id}`} key={run.id}><div className="run-company"><strong>{businessDisplayText(run.company_name)}</strong><small>{run.domain}</small></div><Status value={run.status} /><span className="run-date muted">{new Date(run.created_at).toLocaleString('vi-VN')}</span><span className="run-arrow" aria-hidden="true">→</span></Link>)}</div>}
    </section></>;
}

export function NewResearch() {
  const navigate = useNavigate();
  const submission = useRef({ body: '', key: '' });
  const [input, setInput] = useState<ResearchInput>({ company_name: '', domain: '', context: '' });
  const mutation = useMutation({ mutationFn: () => { const body = JSON.stringify(input); if (submission.current.body !== body) submission.current = { body, key: crypto.randomUUID() }; return post<{ id: string }>('/runs', input, submission.current.key); }, onSuccess: value => navigate(`/research/${value.id}`) });
  return <><header><div><p className="eyebrow">NGHIÊN CỨU DOANH NGHIỆP</p><h1>Nghiên cứu mới</h1><p className="muted">Xác nhận đúng doanh nghiệp, rồi thu thập thông tin có nguồn.</p></div></header>
    <form className="panel form" onSubmit={event => { event.preventDefault(); mutation.mutate(); }}>
      <label>Tên doanh nghiệp<input required minLength={2} maxLength={200} value={input.company_name} onChange={e => setInput({ ...input, company_name: e.target.value })} placeholder="Ví dụ: FPT Software" /></label>
      <label>Domain chính thức<input required value={input.domain} onChange={e => setInput({ ...input, domain: e.target.value })} placeholder="fptsoftware.com" /><small>Chỉ nhập domain, không có https:// hoặc đường dẫn.</small></label>
      <label>Mail gốc / bối cảnh trao đổi (không bắt buộc)<textarea rows={7} maxLength={12000} value={input.context ?? ''} onChange={e => setInput({ ...input, context: e.target.value })} placeholder="Dán nguyên văn mail khách gửi hoặc nhập chủ đề trao đổi, mục tiêu cuộc họp…" /><small>Để soạn email trả lời, dán cả tiêu đề và nội dung mail khách. Nội dung này được lưu để đối chiếu với email nháp.</small></label>
      <ErrorMessage error={mutation.error} /><button disabled={mutation.isPending}>{mutation.isPending ? 'Đang tạo…' : 'Tạo nghiên cứu'}</button>
    </form></>;
}
