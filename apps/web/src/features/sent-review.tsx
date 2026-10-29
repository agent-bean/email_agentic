import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import type { components } from '../lib/api-schema';
import { ErrorMessage } from '../components/status';

type Row = components['schemas']['SentReviewRow'];
type Verification = components['schemas']['SentVerification'];

const verificationLabels: Record<string, string> = {
  content_expired:
    'Nội dung đã hết thời hạn lưu; không đủ dữ liệu để đối chiếu.',
  matched: 'Gmail Sent khớp email đã duyệt.',
  mismatch: 'Email trên Gmail không khớp đầy đủ với phiên bản đã duyệt.',
  not_found:
    'Chưa tìm thấy trong Sent. Điều này chưa chứng minh email chưa gửi.',
  multiple_matches: 'Có nhiều kết quả tương quan; cần kiểm tra thủ công.',
  too_large: 'Email quá lớn để kiểm tra đầy đủ.',
};

function Receipt({ row }: { row: Row }) {
  const [checked, setChecked] = useState(false);
  const query = useQuery({
    queryKey: ['sent-verification', row.id],
    queryFn: () => api<Verification>(`/sent-review/${row.id}`),
    enabled: checked,
    retry: false,
    staleTime: 0,
  });
  const recipients = Object.entries(row.recipients)
    .map(([kind, values]) => `${kind.toUpperCase()}: ${values.join(', ')}`)
    .join(' · ');

  function verify() {
    if (checked) {
      void query.refetch();
    } else {
      setChecked(true);
    }
  }

  return (
    <article className="record">
      <h2>{row.email_subject}</h2>
      <p>
        Phiên bản {row.version} · Trạng thái ứng dụng: {row.status}
      </p>
      <p>{recipients}</p>
      {row.provider_id && (
        <p className="muted">Mã Gmail đã lưu: {row.provider_id}</p>
      )}
      {row.error_code && <p className="muted">{row.error_code}</p>}
      <details>
        <summary>Xem email đã duyệt · phiên bản {row.version}</summary>
        <h3>{row.email_subject}</h3>
        <pre className="preserve">
          {row.email_body || 'Nội dung không còn được lưu.'}
        </pre>
      </details>
      <div className="actions">
        <button disabled={query.isFetching} onClick={verify}>
          {query.isFetching ? 'Đang đối chiếu…' : 'Đối chiếu Gmail Sent'}
        </button>
        <Link to={`/research/${row.run_id}?view=email`}>
          Mở nghiên cứu (bản mới nhất)
        </Link>
      </div>
      <ErrorMessage error={query.error} />
      {query.data && (
        <div role="status">
          <p>
            {verificationLabels[query.data.verification] ||
              query.data.verification}
          </p>
          {query.data.provider_id && (
            <p>Mã Gmail thực tế: {query.data.provider_id}</p>
          )}
          <p className="muted">
            Đã kiểm tra lúc{' '}
            {new Date(query.dataUpdatedAt).toLocaleString('vi-VN')}. Kết quả chỉ
            để review, không cập nhật biên nhận hoặc gửi lại email.
          </p>
        </div>
      )}
    </article>
  );
}

export function SentReview() {
  const query = useQuery({
    queryKey: ['sent-review'],
    queryFn: () => api<Row[]>('/sent-review'),
  });

  return (
    <>
      <header>
        <div>
          <p className="eyebrow">GMAIL SENT</p>
          <h1>Đối chiếu email đã gửi</h1>
          <p className="muted">
            Kiểm tra email đã duyệt với dữ liệu trực tiếp từ Gmail Sent. Không
            tìm thấy ngay chưa chứng minh chưa gửi; không gửi lại khi kết quả
            chưa rõ.
          </p>
        </div>
        <button
          className="secondary"
          onClick={() => void query.refetch()}
          disabled={query.isFetching}
        >
          Tải lại danh sách
        </button>
      </header>
      <ErrorMessage error={query.error} />
      <section className="panel">
        {query.isPending ? (
          <p role="status">Đang tải…</p>
        ) : query.data?.length ? (
          query.data.map((row) => <Receipt key={row.id} row={row} />)
        ) : (
          !query.isError && (
            <p>
              Chưa có yêu cầu gửi email. Danh sách hiển thị tối đa 100 yêu cầu
              gần nhất.
            </p>
          )
        )}
      </section>
    </>
  );
}
