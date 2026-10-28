import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, post } from '../lib/api';
import { ErrorMessage, Status } from '../components/status';

export function Collection({ kind, title }: { kind: string; title: string }) {
  const client = useQueryClient();
  const query = useQuery({ queryKey: [kind], queryFn: () => api<Record<string, unknown>[]>(`/${kind}`) });
  const sync = useMutation({ mutationFn: (provider: string) => post(`/sync/${provider}`), onSuccess: () => { void client.invalidateQueries({ queryKey: [kind] }); } });
  return <><header><div><p className="eyebrow">DỮ LIỆU CỦA BẠN</p><h1>{title}</h1></div>{kind === 'inputs' && <div className="actions"><button disabled={sync.isPending} onClick={() => sync.mutate('email')}>Đồng bộ email</button><button className="secondary" disabled={sync.isPending} onClick={() => sync.mutate('calendar')}>Đồng bộ lịch</button></div>}</header>
    <ErrorMessage error={query.error || sync.error} />{sync.isSuccess && <p role="status">Đã đưa yêu cầu đồng bộ vào hàng đợi. Tải lại danh sách sau khi worker hoàn tất.</p>}
    <section className="panel">{query.isPending ? <p>Đang tải…</p> : !query.data?.length ? <div className="empty">Chưa có dữ liệu.</div> : query.data.map((item, i) => <article className="record" key={String(item.id ?? i)}><h3>{String(item.legal_name ?? item.kind ?? 'Tri thức')}</h3>{item.status ? <Status value={String(item.status)} /> : null}<p className="preserve">{item.content && typeof item.content === 'string' ? item.content : String(item.domain ?? item.source_id ?? '')}</p>{typeof item.content === 'object' && <details><summary>Xem nội dung nguồn</summary><pre>{JSON.stringify(item.content, null, 2)}</pre></details>}</article>)}</section>
  </>;
}

type SystemData = { mode: string; model: string; target_seconds: number; scheduler_enabled: boolean; connections: Record<string, string>; jobs: {kind: string; status: string; total: number}[] };
export function System() {
  const query = useQuery({ queryKey: ['system'], queryFn: () => api<SystemData>('/system'), refetchInterval: 10000 });
  return <><header><div><p className="eyebrow">TÌNH TRẠNG HỆ THỐNG</p><h1>Kết nối & vận hành</h1></div></header><ErrorMessage error={query.error} />{query.data && <><section className="panel"><h2>Cấu hình hoạt động</h2><p>Model: {query.data.model || 'Chưa cấu hình'}</p><p>Mục tiêu tạo báo cáo: {query.data.target_seconds} giây</p><p>Lịch tự động: {query.data.scheduler_enabled ? 'Đang bật' : 'Đang tắt'}</p><p className="muted">Trạng thái cấu hình không thay thế kiểm tra kết nối thực tế.</p>{Object.entries(query.data.connections).map(([key, value]) => <p key={key}>{key}: {value === 'configured' ? 'Đã cấu hình' : 'Thiếu cấu hình'}</p>)}</section><section className="panel"><h2>Hàng đợi</h2>{query.data.jobs.length ? query.data.jobs.map((job, i) => <p key={i}>{job.kind} · {job.status}: {job.total}</p>) : <p>Chưa có tác vụ.</p>}</section></>}</>;
}
