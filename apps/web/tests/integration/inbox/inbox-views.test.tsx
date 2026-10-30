import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../../../src/lib/i18n';
import { Inbox } from '../../../src/features/inbox';

const email = (id: string) => ({ id, kind: 'email', created_at: '2026-10-30T08:00:00Z', content: {
  subject: `Email ${id}`, status: 'succeeded', source_text: `Customer context ${id}`,
  headers: { From: 'Customer <customer@example.org>', Date: '2026-10-30T08:00:00Z' }, attachments: [],
} });
const meeting = (id: string, status = 'confirmed', available = true) => ({ id, kind: 'meeting', calendar_available: available, content: {
  summary: `Meeting ${id}`, status, location: 'Room A', description: 'Discuss the proposal',
  start: { dateTime: '2026-11-01T09:00:00+07:00' }, end: { dateTime: '2026-11-01T10:00:00+07:00' },
} });

function Location() {
  const location = useLocation();
  const navigate = useNavigate();
  return <><output data-testid="location">{location.search}</output><button onClick={() => navigate(-1)}>Back</button></>;
}

function setup(data: unknown[], path = '/inbox') {
  const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify(data))));
  vi.stubGlobal('fetch', fetch);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><I18nProvider><Inbox /><Location /></I18nProvider></MemoryRouter></QueryClientProvider>);
  return { user: userEvent.setup(), fetch };
}

describe('inbox source workspace', () => {
  it('shows all-day dates without timezone shifts and excludes the calendar end boundary', async () => {
    const originalFormatter = Intl.DateTimeFormat;
    const formatter = vi.spyOn(Intl, 'DateTimeFormat').mockImplementation(function (locale, options) {
      return new originalFormatter(locale, { timeZone: 'America/Los_Angeles', ...options });
    });
    localStorage.setItem('email-assistant-language', 'en');
    try {
      const event = meeting('all-day');
      const { user } = setup([{ ...event, content: { ...event.content,
        start: { date: '2026-11-01' }, end: { date: '2026-11-03' },
      } }], '/inbox?kind=calendar');
      await screen.findByRole('heading', { name: 'Meeting all-day' });
      expect(screen.getByText('1 Nov 2026 · All day')).toBeVisible();
      expect(screen.getByText('2 Nov 2026')).toBeVisible();
      await user.click(screen.getByRole('button', { name: 'View meeting details' }));
      expect(screen.getByText('1 Nov 2026 — 2 Nov 2026 · All day')).toBeVisible();
      expect(screen.queryByText(/3 Nov 2026/)).not.toBeInTheDocument();
      expect(screen.queryByText(/31 Oct 2026/)).not.toBeInTheDocument();
    } finally {
      formatter.mockRestore();
      localStorage.removeItem('email-assistant-language');
    }
  });

  it('hides only the exact mailbox address, not overlapping addresses or display names', async () => {
    const senders = [
      ['own', 'Operator <ANN@example.org>'],
      ['own-bare', 'ann@example.org'],
      ['similar', 'Joann <joann@example.org>'],
      ['display', '"ann@example.org" <customer@example.org>'],
      ['other-domain', 'ann@example.org.other'],
    ];
    setup(senders.map(([id, from]) => {
      const item = email(id);
      return { ...item, content: { ...item.content, mailbox: 'ann@example.org', headers: { ...item.content.headers, From: from } } };
    }));
    expect(await screen.findByRole('heading', { name: 'Email similar' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Email display' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Email other-domain' })).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'Email own' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Email own-bare' })).not.toBeInTheDocument();
  });

  it('renders English chrome and dates without translating source content', async () => {
    localStorage.setItem('email-assistant-language', 'en');
    try {
      const { user } = setup([meeting('Khách hàng')], '/inbox?kind=calendar');
      expect(await screen.findByRole('heading', { name: 'Meeting Khách hàng' })).toBeVisible();
      expect(screen.getByRole('button', { name: 'Sync calendar' })).toBeVisible();
      expect(screen.getByText('Starts')).toBeVisible();
      expect(screen.getAllByText(/1 Nov 2026/)[0]).toBeVisible();
      await user.click(screen.getByRole('button', { name: 'View meeting details' }));
      expect(screen.getByText('Discuss the proposal')).toBeVisible();
      expect(screen.getByRole('button', { name: 'Collapse content' })).toBeVisible();
    } finally {
      localStorage.removeItem('email-assistant-language');
    }
  });

  it('filters own-mailbox email and restores the selected filter from the URL', async () => {
    const own = email('own');
    const { user } = setup([{ ...own, content: { ...own.content, mailbox: 'customer@example.org' } }, email('incoming')], '/inbox?kind=email&own=1');
    expect(await screen.findByRole('heading', { name: 'Email own' })).toBeVisible();
    const checkbox = screen.getByRole('checkbox');
    expect(checkbox).toBeChecked();
    await user.click(checkbox);
    expect(screen.queryByRole('heading', { name: 'Email own' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Email incoming' })).toBeVisible();
    expect(screen.getByTestId('location')).not.toHaveTextContent('own=1');
  });

  it('separates email and meeting views and syncs only on explicit action', async () => {
    const { user, fetch } = setup([email('a'), meeting('b')]);
    expect(await screen.findByRole('heading', { name: 'Email a' })).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'Meeting b' })).not.toBeInTheDocument();
    expect(screen.getByText('Customer <customer@example.org>')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Xem email gốc' })).toHaveAttribute('aria-expanded', 'false');
    await user.click(screen.getByRole('link', { name: 'Cuộc họp' }));
    expect(await screen.findByRole('heading', { name: 'Meeting b' })).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'Email a' })).not.toBeInTheDocument();
    expect(screen.getByText('Room A')).toBeVisible();
    expect(screen.getByTestId('location')).toHaveTextContent('kind=calendar');
    expect(fetch.mock.calls.every((call) => !String(call[0]).includes('/sync/'))).toBe(true);
    await user.click(screen.getByRole('button', { name: 'Đồng bộ lịch' }));
    expect(fetch.mock.calls.some((call) => String(call[0]).endsWith('/sync/calendar') && call[1]?.method === 'POST')).toBe(true);
  });

  it('keeps search, pagination and reading selection in the URL and supports back', async () => {
    const { user } = setup(Array.from({ length: 13 }, (_, i) => email(String(i))));
    await screen.findByRole('heading', { name: 'Email 0' });
    expect(screen.queryByRole('heading', { name: 'Email 12' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Trang sau' }));
    expect(screen.getByRole('heading', { name: 'Email 12' })).toBeVisible();
    expect(screen.getByTestId('location')).toHaveTextContent('page=2');
    await user.click(screen.getByRole('button', { name: 'Xem email gốc' }));
    expect(screen.getByTestId('location')).toHaveTextContent('source=12');
    expect(screen.getByRole('button', { name: 'Thu gọn nội dung' })).toHaveAttribute('aria-expanded', 'true');
    await user.click(screen.getByRole('button', { name: 'Back' }));
    expect(screen.getByRole('button', { name: 'Xem email gốc' })).toHaveAttribute('aria-expanded', 'false');
    await user.type(screen.getByRole('searchbox'), 'no match');
    expect(screen.getByText(/Không tìm thấy kết quả cho/)).toBeVisible();
    expect(screen.getByTestId('location')).toHaveTextContent('q=no+match');
    await user.click(screen.getByRole('button', { name: 'Xóa bộ lọc' }));
    expect(screen.getByRole('heading', { name: 'Email 0' })).toBeVisible();
  });

  it('restores a shared search and open source while blocking cancelled and unavailable preparation', async () => {
    setup([meeting('cancelled', 'cancelled'), meeting('unavailable', 'confirmed', false), meeting('ready')], '/inbox?kind=calendar&q=Meeting&source=ready');
    await screen.findByRole('heading', { name: 'Meeting cancelled' });
    for (const name of ['cancelled', 'unavailable']) {
      const article = screen.getByRole('heading', { name: `Meeting ${name}` }).closest('article')!;
      expect(within(article).queryByRole('link', { name: 'Chuẩn bị trước họp' })).not.toBeInTheDocument();
    }
    expect(screen.getByRole('link', { name: 'Chuẩn bị trước họp' })).toHaveAttribute('href', '/research/new?input=ready');
    expect(screen.getByRole('searchbox')).toHaveValue('Meeting');
    expect(screen.getByRole('button', { name: 'Thu gọn nội dung' })).toHaveAttribute('aria-expanded', 'true');
  });
});
