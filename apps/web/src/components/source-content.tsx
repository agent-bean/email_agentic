import { useI18n, type Translate } from '../lib/i18n';
import type { SourceMessage, MeetingEvent } from '../lib/source-models';

export function MeetingSource({ event }: { event: MeetingEvent }) {
  const { t, locale } = useI18n();
  return (
    <div className="preserve">
      <strong>{event.summary || t('Cuộc họp', 'Meeting')}</strong>
      <p>
        {readableDate(event.start?.dateTime || event.start?.date, locale, t)} —{' '}
        {readableDate(meetingEndDate(event), locale, t)}
        {!event.start?.dateTime && event.start?.date && <> · {t('Cả ngày', 'All day')}</>}
      </p>
      {event.status === 'cancelled' && <p>{t('Cuộc họp đã bị hủy.', 'This meeting was cancelled.')}</p>}
      {event.location && <p>{event.location}</p>}
      {event.description && <p>{event.description}</p>}
      {event.attendees?.length ? (
        <p>
          {t('Người tham dự:', 'Attendees:')}{' '}
          {event.attendees.map((a) => a.displayName || a.email).join(', ')}
        </p>
      ) : null}
    </div>
  );
}
export function Attachments({ items }: { items: NonNullable<SourceMessage["attachments"]> }) {
  const { t } = useI18n();
  const labels: Record<string, string> = {
    succeeded: t('Đã đọc', 'Read'),
    no_text: t('Không có văn bản đọc được', 'No readable text'),
    partial: t('Đã đọc một phần', 'Partially read'),
    ocr_unavailable: t('Chưa cài công cụ OCR', 'OCR is unavailable'),
    ocr_timeout: t('OCR hết thời gian', 'OCR timed out'),
    ocr_failed: t('OCR thất bại', 'OCR failed'),
    ocr_limit_reached: t('Vượt giới hạn OCR', 'OCR limit reached'),
    encrypted: t('PDF có mật khẩu', 'Password-protected PDF'),
    too_large: t('Tệp quá lớn', 'File too large'),
    unsupported_type: t('Chưa hỗ trợ định dạng này', 'Unsupported file type'),
    limit_reached: t('Vượt giới hạn đọc tệp', 'Reading limit reached'),
    timeout: t('Hết thời gian đọc', 'Reading timed out'),
    invalid_pdf: t('Không đọc được PDF', 'Unreadable PDF'),
    extraction_failed: t('Đọc tệp thất bại', 'Reading failed'),
  };
  return items.length ? (
    <div>
      <h3>{t('File đính kèm', 'Attachments')}</h3>
      {items.map((item, index) => (
        <details key={index} className="record">
          <summary>
            {item.filename} · {Math.ceil(item.size / 1024)} KB ·{' '}
            {labels[item.extraction.status] ?? item.extraction.status}
          </summary>
          {item.extraction.pages != null && (
            <p className="muted">
              {t('Đã đọc', 'Read')} {item.extraction.pages_read}/{item.extraction.pages} {t('trang', 'pages')}
              {item.extraction.truncated ? t('; nội dung được giới hạn', '; content is limited') : ''}.
            </p>
          )}
          {item.extraction.page_results
            ? item.extraction.page_results.map((page) => (
                <div key={page.page}>
                  <p className="muted">
                    {t('Trang', 'Page')} {page.page} ·{' '}
                    {page.method === 'ocr'
                      ? t('OCR (cần kiểm tra lại nhận dạng)', 'OCR (check recognition accuracy)')
                      : t('Lớp văn bản', 'Text layer')}{' '}
                    · {labels[page.status] ?? page.status}
                  </p>
                  {page.text && <pre className="preserve">{page.text}</pre>}
                </div>
              ))
            : item.extraction.text && (
                <pre className="preserve">{item.extraction.text}</pre>
              )}
        </details>
      ))}
    </div>
  ) : null;
}

export function readableDate(value: string | null | undefined, locale: string, t: Translate) {
  if (!value) return t('Chưa có thời gian', 'Time not provided');
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium', ...(/^\d{4}-\d{2}-\d{2}$/.test(value) ? { timeZone: 'UTC' } : { timeStyle: 'short' as const }),
  }).format(date);
}

export function meetingEndDate(event: MeetingEvent) {
  if (event.end?.dateTime) return event.end.dateTime;
  const end = event.end?.date;
  if (!end || !/^\d{4}-\d{2}-\d{2}$/.test(end)) return end;
  const date = new Date(`${end}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return end;
  // Calendar all-day end dates are exclusive; show the last occupied day.
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}
