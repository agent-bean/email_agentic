import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { api, post, type Run, type ResearchInput } from '../lib/api';
import { ErrorMessage, Status } from '../components/status';

export function Overview() {
  const query = useQuery({ queryKey: ['runs'], queryFn: () => api<Run[]>('/runs'), refetchInterval: 5000 });
  const runs = query.data ?? [];
  return <><header><div><p className="eyebrow">CHUẨN BỊ CHO CUỘC HỌP TIẾP THEO</p><h1>Tổng quan</h1><p className="muted">Từ thông tin rời rạc đến bản briefing có nguồn.</p></div><Link className="button" to="/research/new">+ Nghiên cứu mới</Link></header>
    <section className="stats"><article><span>Tổng tác vụ</span><strong>{runs.length}</strong></article><article><span>Cần xác nhận</span><strong>{runs.filter(r => r.status === 'awaiting_identity').length}</strong></article><article><span>Có bản nháp</span><strong>{runs.filter(r => r.status === 'draft_ready').length}</strong></article></section>
    <section className="panel"><h2>Nghiên cứu gần đây</h2><ErrorMessage error={query.error} />
      {query.isPending ? <p>Đang tải…</p> : runs.length === 0 ? <div className="empty"><h3>Chưa có nghiên cứu</h3><p>Tạo tác vụ đầu tiên để bắt đầu thu thập thông tin doanh nghiệp.</p></div> : <div className="run-list">{runs.map(run => <Link to={`/research/${run.id}`} key={run.id}><div><strong>{run.company_name}</strong><small>{run.domain}</small></div><Status value={run.status} /><span className="muted">{new Date(run.created_at).toLocaleString('vi-VN')}</span></Link>)}</div>}
    </section></>;
}

export function NewResearch() {
  const navigate = useNavigate();
  const submission = useRef({ body: '', key: '' });
  const [input, setInput] = useState<ResearchInput>({ company_name: '', domain: '', context: '' });
  const mutation = useMutation({ mutationFn: () => { const body = JSON.stringify(input); if (submission.current.body !== body) submission.current = { body, key: crypto.randomUUID() }; return post<{ id: string }>('/runs', input, submission.current.key); }, onSuccess: value => navigate(`/research/${value.id}`) });
  return <><header><div><p className="eyebrow">NGHIÊN CỨU DOANH NGHIỆP</p><h1>Chuẩn bị một briefing mới</h1><p className="muted">Xác nhận đúng doanh nghiệp, rồi thu thập thông tin có nguồn.</p></div></header>
    <form className="panel form" onSubmit={event => { event.preventDefault(); mutation.mutate(); }}>
      <label>Tên doanh nghiệp<input required minLength={2} maxLength={200} value={input.company_name} onChange={e => setInput({ ...input, company_name: e.target.value })} placeholder="Ví dụ: FPT Software" /></label>
      <label>Domain chính thức<input required value={input.domain} onChange={e => setInput({ ...input, domain: e.target.value })} placeholder="fptsoftware.com" /><small>Chỉ nhập domain, không có https:// hoặc đường dẫn.</small></label>
      <label>Ngữ cảnh và nhu cầu<textarea rows={5} maxLength={12000} value={input.context ?? ''} onChange={e => setInput({ ...input, context: e.target.value })} placeholder="Cuộc họp này cần chuẩn bị những gì?" /></label>
      <ErrorMessage error={mutation.error} /><button disabled={mutation.isPending}>{mutation.isPending ? 'Đang tạo…' : 'Tạo nghiên cứu'}</button>
    </form></>;
}
