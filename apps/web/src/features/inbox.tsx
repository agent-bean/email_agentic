import { Link } from 'react-router-dom';
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, post } from '../lib/api';
import { ErrorMessage } from '../components/status';

export type Attachment = { filename: string; size: number; extraction: { status: string; text?: string; pages?: number; pages_read?: number; truncated?: boolean } };
export type SourceMessage = { id: string; thread_id: string; mailbox?: string; subject: string; source_text: string; body_format: string; headers: Record<string, string>; attachments: Attachment[] };
export type SourceInput = { id: string; kind: string; source_id: string; content: SourceMessage & { summary?: string; status?: string }; created_at: string; intake_status?: string | null; research_run_id?: string | null };

export function Attachments({ items }: { items: Attachment[] }) {
  const labels: Record<string, string> = { succeeded: 'Đã đọc', no_text: 'Không có lớp văn bản; cần OCR', encrypted: 'PDF có mật khẩu', too_large: 'Tệp quá lớn', unsupported_type: 'Chưa hỗ trợ định dạng này', limit_reached: 'Vượt giới hạn đọc tệp', timeout: 'Hết thời gian đọc', invalid_pdf: 'Không đọc được PDF', extraction_failed: 'Đọc tệp thất bại' };
  return items.length ? <div><h3>File đính kèm</h3>{items.map((item, index) => <details key={index} className="record"><summary>{item.filename} · {Math.ceil(item.size / 1024)} KB · {labels[item.extraction.status] ?? item.extraction.status}</summary>{item.extraction.pages != null && <p className="muted">Đã đọc {item.extraction.pages_read}/{item.extraction.pages} trang{item.extraction.truncated ? '; nội dung được giới hạn' : ''}.</p>}{item.extraction.text && <pre className="preserve">{item.extraction.text}</pre>}</details>)}</div> : null;
}

export function Inbox() {
  const [showOwn, setShowOwn] = useState(false);
  const client = useQueryClient();
  const query = useQuery({ queryKey: ['inputs'], queryFn: () => api<SourceInput[]>('/inputs'), refetchInterval: 5000 });
  const sync = useMutation({ mutationFn: (provider: string) => post(`/sync/${provider}`), onSuccess: () => { void client.invalidateQueries({ queryKey: ['inputs'] }); } });
  const items = query.data?.filter(item => item.kind !== 'email' || !item.content.headers || showOwn ||
    !item.content.headers.From?.toLowerCase().includes(item.content.mailbox?.toLowerCase() || '\0')).sort((a, b) => (Date.parse(b.content.headers?.Date ?? b.created_at) || 0) - (Date.parse(a.content.headers?.Date ?? a.created_at) || 0));
  return <><header><div><p className="eyebrow">DỮ LIỆU CỦA BẠN</p><h1>Email & cuộc họp</h1><p className="muted">Chọn email để nghiên cứu và chuẩn bị reply trong đúng thread Gmail.</p></div><div className="actions"><button disabled={sync.isPending} onClick={() => sync.mutate('email')}>Đồng bộ Gmail</button><button className="secondary" disabled={sync.isPending} onClick={() => sync.mutate('calendar')}>Đồng bộ lịch</button></div></header>
    <ErrorMessage error={query.error || sync.error} />{sync.isSuccess && <p role="status">Đã nhận yêu cầu đồng bộ. Danh sách tự cập nhật khi xử lý xong.</p>}
    <label className="check"><input type="checkbox" checked={showOwn} onChange={event => setShowOwn(event.target.checked)} />Hiển thị cả email từ chính hộp thư này</label>
    <section className="panel">{query.isPending ? <p role="status">Đang tải…</p> : query.isError ? <button onClick={() => void query.refetch()}>Thử lại</button> : !items?.length ? <p>Chưa có dữ liệu. Chọn Đồng bộ Gmail để đọc hộp thư.</p> : items.map(item => <article className="record" key={item.id}>
      <h2>{item.content.subject || item.content.summary || (item.kind === 'email' ? 'Email' : 'Cuộc họp')}</h2>
      {item.kind === 'email' && item.content.status === 'succeeded' && item.content.source_text ? <><p className="muted">{item.content.headers.From} · {item.content.headers.Date}</p><details><summary>Xem email gốc</summary><pre className="preserve">{item.content.source_text}</pre>{item.content.body_format === 'html' && <p className="muted">Email HTML được hiển thị dưới dạng văn bản an toàn.</p>}<Attachments items={item.content.attachments} /></details>{item.research_run_id ? <Link className="button" to={`/research/${item.research_run_id}?view=email`}>Mở nghiên cứu</Link> : <><p className="muted">{item.intake_status === 'queued' ? 'Đang phân loại email và đề xuất doanh nghiệp…' : item.intake_status === 'skipped' ? 'Không tự tạo nghiên cứu cho email này. Bạn vẫn có thể tạo thủ công.' : item.intake_status === 'needs_review' ? 'Chưa xác định rõ doanh nghiệp. Hãy nhập tên và domain để nghiên cứu.' : item.intake_status === 'failed' ? 'Chưa phân loại được email. Bạn có thể tạo nghiên cứu thủ công.' : ''}</p><Link className="button" to={`/research/new?input=${item.id}`}>Nghiên cứu từ email này</Link></>}</> : item.kind === 'email' ? <p className="muted">Chưa đọc được nội dung email này. Đồng bộ lại để thử tiếp.</p> : <details><summary>Xem dữ liệu nguồn</summary><pre>{JSON.stringify(item.content, null, 2)}</pre></details>}
    </article>)}</section></>;
}
