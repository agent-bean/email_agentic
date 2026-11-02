import { Link, useSearchParams } from 'react-router-dom';
import { Icon } from '../components/icon';
import './inbox.css';
import { useI18n } from '../lib/i18n';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { endpoints } from '../lib/api';
import { ErrorMessage } from '../components/status';
import { Attachments, MeetingSource, readableDate, meetingEndDate } from '../components/source-content';
import type { SourceInput } from '../lib/source-models';

function sourceHeader(item: SourceInput, name: string) {
  return Object.entries(item.kind === 'email' ? item.content.headers ?? {} : {}).find(
    ([key]) => key.toLowerCase() === name.toLowerCase(),
  )?.[1] ?? '';
}

function senderAddress(from: string) {
  const address = (from.match(/<([^<>]+)>\s*(?:\([^)]*\))?\s*$/)?.[1]
    ?? from.replace(/\([^)]*\)/g, '').trim()).trim();
  return /^(?:"(?:[^"\\]|\\.)+"|[^\s<>(),;"@]+)@[^\s<>(),;"@]+$/.test(address)
    ? address.toLowerCase() : '';
}

function SourceIcon({ meeting }: { meeting: boolean }) {
  return meeting ? (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <path d="M4 5h16v16H4z M4 10h16 M8 2v6 M16 2v6 M8 14h3 M8 17h6" />
    </svg>
  ) : <Icon name="inbox" />;
}

function SourceCard({ item, opened, onOpen }: {
  item: SourceInput; opened: boolean; onOpen: () => void;
}) {
  const { t, locale } = useI18n();
  const emailIntakeLabels: Record<string, string> = {
    queued: t('Đang phân loại email và đề xuất doanh nghiệp…', 'Classifying email and suggesting a company…'),
    skipped:
      t('Không tự tạo nghiên cứu cho email này. Bạn vẫn có thể tạo thủ công.', 'No research is created automatically for this email. You can create it manually.'),
    needs_review:
      t('Chưa xác định rõ doanh nghiệp. Hãy nhập tên và domain để nghiên cứu.', 'The company is unclear. Enter its name and domain to research it.'),
    failed: t('Chưa phân loại được email. Bạn có thể tạo nghiên cứu thủ công.', 'Email classification failed. You can create research manually.'),
  };
  const meetingIntakeLabels: Record<string, string> = {
    queued: t('Đang đề xuất doanh nghiệp cho cuộc họp…', 'Suggesting a company for this meeting…'),
    skipped: t('Không tự tạo nghiên cứu cho cuộc họp này.', 'No research is created automatically for this meeting.'),
    needs_review: t('Cần nhập doanh nghiệp để chuẩn bị cuộc họp.', 'Enter a company to prepare for this meeting.'),
    failed: t('Cần nhập doanh nghiệp để chuẩn bị cuộc họp.', 'Enter a company to prepare for this meeting.'),
  };

  const meeting = item.kind === 'meeting';
  const readable = item.kind === 'email' && item.content.status === 'succeeded' && Boolean(item.content.source_text);
  const cancelled = item.content.status === 'cancelled';
  const unavailable = item.calendar_available === false;
  const title = item.kind === 'meeting' ? item.content.summary || t('Cuộc họp', 'Meeting') : item.content.subject || t('Email không có tiêu đề', 'Untitled email');
  return (
    <article className={`record inbox-record ${meeting ? 'inbox-meeting' : 'inbox-email'}`}>
      <div className="inbox-record-heading">
        <span className="inbox-source-icon"><SourceIcon meeting={meeting} /></span>
        <div>
          <p className="eyebrow">{meeting ? t('CUỘC HỌP', 'MEETING') : 'EMAIL'}</p>
          <h2>{title}</h2>
        </div>
        {meeting && <span className="badge">{cancelled ? t('Đã hủy', 'Cancelled') : unavailable ? t('Không còn trong lịch', 'No longer in calendar') : item.content.status === 'tentative' ? t('Chưa xác nhận', 'Tentative') : t('Trong lịch', 'In calendar')}</span>}
      </div>
      {item.kind === 'meeting' ? (
        <dl className="inbox-meeting-facts">
          <div><dt>{t('Bắt đầu', 'Starts')}</dt><dd>{readableDate(item.content.start?.dateTime || item.content.start?.date, locale, t)}{!item.content.start?.dateTime && item.content.start?.date && <> · {t('Cả ngày', 'All day')}</>}</dd></div>
          <div><dt>{t('Kết thúc', 'Ends')}</dt><dd>{readableDate(meetingEndDate(item.content), locale, t)}</dd></div>
          <div><dt>{t('Địa điểm', 'Location')}</dt><dd>{item.content.location || t('Chưa có địa điểm', 'Location not provided')}</dd></div>
        </dl>
      ) : (
        <>
          <p className="inbox-email-meta"><strong>{sourceHeader(item, 'From') || t('Chưa rõ người gửi', 'Unknown sender')}</strong><span>{readableDate(sourceHeader(item, 'Date') || item.created_at, locale, t)}</span></p>
          {readable && <p className="inbox-snippet">{item.content.source_text?.replace(/\s+/g, ' ').slice(0, 220)}</p>}
        </>
      )}
      {(meeting || readable) && (
        <>
          <button className="secondary inbox-read-button" aria-expanded={opened} aria-controls={`source-${item.id}`} onClick={onOpen}>
            {opened ? t('Thu gọn nội dung', 'Collapse content') : meeting ? t('Xem chi tiết cuộc họp', 'View meeting details') : t('Xem email gốc', 'Read original email')}
          </button>
          {opened && <div id={`source-${item.id}`} className="inbox-reader">
            {item.kind === 'meeting' ? <MeetingSource event={item.content} /> : <>
              <pre className="preserve">{item.content.source_text}</pre>
              {item.content.body_format === 'html' && <p className="muted">{t('Email HTML được hiển thị dưới dạng văn bản an toàn.', 'HTML email is displayed as safe plain text.')}</p>}
              <Attachments items={item.content.attachments ?? []} />
            </>}
          </div>}
        </>
      )}
      {!meeting && !readable ? <p className="muted">{t('Chưa đọc được nội dung email này. Đồng bộ Gmail để thử lại.', 'This email could not be read. Sync Gmail to try again.')}</p> : (
        <div className="inbox-next-step">
          {item.research_run_id ? <Link className="button secondary" to={`/research/${item.research_run_id}${meeting ? '' : '?view=email'}`}>
            {meeting ? t('Mở nghiên cứu trước họp', 'Open meeting research') : t('Mở nghiên cứu', 'Open research')}
          </Link> : meeting && (cancelled || unavailable) ? <p className="muted">{cancelled ? t('Cuộc họp đã bị hủy. Không tạo nghiên cứu chuẩn bị.', 'This meeting was cancelled. Preparation research is unavailable.') : t('Cuộc họp không còn trong lịch sắp tới. Không tạo nghiên cứu từ bản lịch cũ.', 'This meeting is no longer upcoming. Research cannot be created from an outdated calendar entry.')}</p> : <>
            <p className="muted">{(meeting ? meetingIntakeLabels : emailIntakeLabels)[item.intake_status ?? ''] ?? (meeting ? t('Chọn cuộc họp để nghiên cứu doanh nghiệp và chuẩn bị trao đổi.', 'Choose a meeting to research the company and prepare for the conversation.') : t('Nghiên cứu doanh nghiệp và chuẩn bị trả lời email này.', 'Research the company and prepare a reply to this email.'))}</p>
            <Link className="button secondary" to={`/research/new?input=${item.id}`}>{meeting ? t('Chuẩn bị trước họp', 'Prepare for meeting') : t('Nghiên cứu từ email này', 'Research from this email')}</Link>
          </>}
        </div>
      )}
    </article>
  );
}

const PAGE_SIZE = 12;

export function Inbox() {
  const { t, locale } = useI18n();
  const [params, setParams] = useSearchParams();
  const kind = params.get('kind') === 'calendar' ? 'calendar' : 'email';
  const meeting = kind === 'calendar';
  const search = params.get('q') ?? '';
  const showOwn = params.get('own') === '1';
  const requestedPage = Math.max(1, Number.parseInt(params.get('page') ?? '1', 10) || 1);
  function update(values: Record<string, string | null>, replace = false) {
    setParams((current) => {
      const next = new URLSearchParams(current);
      for (const [key, value] of Object.entries(values)) {
        if (value) next.set(key, value); else next.delete(key);
      }
      return next;
    }, { replace });
  }
  const client = useQueryClient();
  const query = useQuery({ queryKey: ['inputs'], queryFn: ({ signal }) => endpoints.inputs(signal), refetchInterval: 5000 });
  const sync = useMutation({
    mutationFn: (provider: 'email' | 'calendar') => endpoints.sync(provider),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ['inputs'] }); },
  });
  const sources = (query.data ?? []).filter((item) => item.kind === (meeting ? 'meeting' : 'email'));
  const items = sources.filter((item) => {
    if (item.kind === 'email' && !showOwn && item.content.mailbox && senderAddress(sourceHeader(item, 'From')) === item.content.mailbox.trim().toLowerCase()) return false;
    const searchable = item.kind === 'email'
      ? [item.content.subject, item.content.source_text, sourceHeader(item, 'From')]
      : [item.content.summary, item.content.location, item.content.description, ...(item.content.attendees ?? []).flatMap((a) => [a.email, a.displayName])];
    return searchable
      .filter(Boolean).join(' ').toLocaleLowerCase(locale).includes(search.trim().toLocaleLowerCase(locale));
  }).sort((a, b) => a.kind === 'meeting' && b.kind === 'meeting'
    ? (Date.parse(a.content.start?.dateTime || a.content.start?.date || a.created_at) || 0) - (Date.parse(b.content.start?.dateTime || b.content.start?.date || b.created_at) || 0)
    : (Date.parse(sourceHeader(b, 'Date') || b.created_at) || 0) - (Date.parse(sourceHeader(a, 'Date') || a.created_at) || 0));
  const pages = Math.max(1, Math.ceil(items.length / PAGE_SIZE));
  const page = Math.min(requestedPage, pages);
  const visible = items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  return <>
    <header>
      <div><p className="eyebrow">{t('DỮ LIỆU CỦA BẠN', 'YOUR SOURCES')}</p><h1>{meeting ? t('Cuộc họp', 'Meeting') : t('Email đến', 'Incoming email')}</h1>
        <p className="muted">{meeting ? t('Xem lịch hẹn, người tham dự và chuẩn bị trước cuộc họp.', 'Review appointments and attendees, and prepare for meetings.') : t('Đọc email khách hàng, nghiên cứu doanh nghiệp và chuẩn bị trả lời.', 'Read customer emails, research companies and prepare replies.')}</p>
      </div>
      <button disabled={sync.isPending} onClick={() => sync.mutate(kind)}>{sync.isPending ? t('Đang yêu cầu…', 'Requesting…') : meeting ? t('Đồng bộ lịch', 'Sync calendar') : t('Đồng bộ Gmail', 'Sync Gmail')}</button>
    </header>
    <nav className="workspace-tabs inbox-tabs" aria-label={t('Loại dữ liệu nguồn', 'Source type')}>
      {(['email', 'calendar'] as const).map((value) => <Link key={value} to={`?kind=${value}`} aria-current={kind === value ? 'page' : undefined}>
        <SourceIcon meeting={value === 'calendar'} />{value === 'email' ? t('Email đến', 'Incoming email') : t('Cuộc họp', 'Meeting')}
      </Link>)}
    </nav>
    <ErrorMessage error={query.error || sync.error} />
    {sync.isSuccess && <p role="status">{t('Đã nhận yêu cầu đồng bộ', 'Sync requested for')} {sync.variables === 'calendar' ? t('lịch', 'calendar') : 'Gmail'}. {t('Danh sách tự cập nhật khi xử lý xong.', 'The list updates when processing finishes.')}</p>}
    <section className="workspace-toolbar inbox-toolbar" aria-label={t('Bộ lọc nguồn', 'Source filters')}>
      <label>{t('Tìm', 'Search')} {meeting ? t('cuộc họp', 'meetings') : 'email'}<input type="search" value={search} placeholder={meeting ? t('Tên cuộc họp, địa điểm, người tham dự', 'Meeting name, location, attendees') : t('Tiêu đề, người gửi, nội dung', 'Subject, sender, content')} onChange={(event) => update({ q: event.target.value, page: null, source: null }, true)} /></label>
      {!meeting && <label className="check"><input type="checkbox" checked={showOwn} onChange={(event) => update({ own: event.target.checked ? '1' : null, page: null, source: null })} />{t('Hiển thị cả email từ chính hộp thư này', 'Include emails from this mailbox')}</label>}
      {(search || showOwn) && <button className="secondary" onClick={() => update({ q: null, own: null, page: null, source: null })}>{t('Xóa bộ lọc', 'Clear filters')}</button>}
    </section>
    <section className="panel workspace-list inbox-list" aria-label={meeting ? t('Danh sách cuộc họp', 'Meeting list') : t('Danh sách email', 'Email list')} aria-busy={query.isPending}>
      {query.isPending ? <p role="status">{t('Đang tải', 'Loading')} {meeting ? t('cuộc họp', 'meetings') : 'email'}…</p> : query.isError ? <div className="empty"><h2>{t('Chưa tải được danh sách', 'Unable to load sources')}</h2><button onClick={() => void query.refetch()}>{t('Thử lại', 'Retry')}</button></div> : !items.length ? <div className="empty">
        <h2>{sources.length ? t(`Không có ${meeting ? 'cuộc họp' : 'email'} phù hợp bộ lọc`, `No ${meeting ? 'meetings' : 'emails'} match your filters`) : meeting ? t('Chưa có cuộc họp', 'No meetings yet') : t('Chưa có email', 'No emails yet')}</h2>
        <p>{search ? t(`Không tìm thấy kết quả cho “${search}”. Hãy thử từ khóa khác hoặc xóa bộ lọc.`, `No results for “${search}”. Try another search or clear filters.`) : sources.length ? t('Bật hiển thị email từ chính hộp thư để xem thêm.', 'Include emails from this mailbox to see more.') : t(`Chọn ${meeting ? 'Đồng bộ lịch' : 'Đồng bộ Gmail'} để lấy dữ liệu nguồn.`, `Choose ${meeting ? 'Sync calendar' : 'Sync Gmail'} to load your sources.`)}</p>
        {sources.length > 0 && !search && !meeting && <button className="secondary" onClick={() => update({ own: '1' })}>{t('Hiển thị tất cả email', 'Show all emails')}</button>}
      </div> : <>
        <p className="muted">{items.length} {meeting ? t('cuộc họp · theo thời gian bắt đầu', 'meetings · ordered by start time') : t('email · mới nhất trước', 'emails · newest first')}</p>
        {visible.map((item) => <SourceCard key={item.id} item={item} opened={params.get('source') === item.id} onOpen={() => update({ source: params.get('source') === item.id ? null : item.id })} />)}
        <nav className="workspace-pagination inbox-pagination" aria-label={t('Phân trang nguồn', 'Source pagination')}>
          <button className="secondary" disabled={page <= 1} onClick={() => update({ page: String(page - 1), source: null })}>{t('Trang trước', 'Previous page')}</button>
          <span>{t('Trang', 'Page')} {page} / {pages} · {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, items.length)} / {items.length}</span>
          <button className="secondary" disabled={page >= pages} onClick={() => update({ page: String(page + 1), source: null })}>{t('Trang sau', 'Next page')}</button>
        </nav>
      </>}
    </section>
  </>;
}
