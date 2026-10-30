import { focusManager, onlineManager, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SentReview } from '../../../src/features/sent-review';
import { I18nProvider } from '../../../src/lib/i18n';

afterEach(() => { localStorage.removeItem('email-assistant-language'); });

const row = { id: 'receipt-1', run_id: 'run-1', version: 2, email_subject: 'Hợp tác Alpha', email_body: 'Nội dung được duyệt\nTrân trọng.', recipients: { to: ['alpha@example.test'] }, status: 'succeeded', provider_id: 'gmail-1', error_code: null, created_at: '2026-10-30T09:00:00Z' };
function renderHistory(path = '/sent-review') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const router = createMemoryRouter([{ path: '/sent-review', element: <SentReview /> }, { path: '/research/:id', element: <h1>Nghiên cứu</h1> }], { initialEntries: [path] });
  render(<I18nProvider><QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider></I18nProvider>);
  return router;
}
function mockApi(rows = [row], verification = 'matched') {
  const fetch = vi.fn().mockImplementation(async (input: string) => Response.json(input.endsWith('/sent-review') ? rows : { verification, provider_id: 'gmail-1' }));
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
function verificationCalls(fetch: ReturnType<typeof vi.fn>) { return fetch.mock.calls.filter(([url]) => String(url).endsWith('/sent-review/receipt-1')); }

describe('sent history', () => {
  it('uses English for controls and verification while preserving approved content', async () => {
    localStorage.setItem('email-assistant-language', 'en');
    const fetch = mockApi([row], 'not_found');
    renderHistory();
    const user = userEvent.setup();
    expect(await screen.findByRole('heading', { name: 'Email send history' })).toBeVisible();
    await screen.findByRole('heading', { name: row.email_subject });
    await user.type(screen.getByRole('searchbox', { name: 'Find email' }), 'alpha');
    await user.click(screen.getByText('Read approved email'));
    expect(screen.getByText(/Nội dung được duyệt/)).toBeVisible();
    expect(verificationCalls(fetch)).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Check in Gmail' }));
    expect(await screen.findByText(/This does not prove it was not sent/)).toBeVisible();
    expect(screen.getByText(/The application status has not changed/)).toBeVisible();
    expect(verificationCalls(fetch)).toHaveLength(1);
  });
  it('verifies only by click, including after focus, reconnect and remount', async () => {
    const fetch = mockApi();
    const router = renderHistory();
    const user = userEvent.setup();
    await screen.findByRole('heading', { name: row.email_subject });
    expect(verificationCalls(fetch)).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Kiểm tra trên Gmail' }));
    expect(await screen.findByText('Email trong thư mục Đã gửi trên Gmail khớp phiên bản đã duyệt.')).toBeVisible();
    expect(verificationCalls(fetch)).toHaveLength(1);
    await act(async () => { focusManager.setFocused(false); focusManager.setFocused(true); onlineManager.setOnline(false); onlineManager.setOnline(true); });
    expect(verificationCalls(fetch)).toHaveLength(1);
    await user.click(screen.getByRole('link', { name: 'Mở nghiên cứu (bản mới nhất)' }));
    await act(async () => { await router.navigate(-1); });
    await screen.findByRole('heading', { name: row.email_subject });
    expect(verificationCalls(fetch)).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: 'Kiểm tra trên Gmail' }));
    await screen.findByText('Email trong thư mục Đã gửi trên Gmail khớp phiên bản đã duyệt.');
    expect(verificationCalls(fetch)).toHaveLength(2);
    focusManager.setFocused(undefined);
  });

  it.each([
    ['not_found', /Điều này chưa chứng minh email chưa gửi/],
    ['mismatch', /không khớp đầy đủ/],
    ['content_expired', /hết thời hạn lưu/],
    ['multiple_matches', /Có nhiều email tương ứng/],
    ['too_large', /Email quá lớn/],
  ])('explains %s without changing application status', async (verification, message) => {
    mockApi([row], verification);
    renderHistory();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Kiểm tra trên Gmail' }));
    expect(await screen.findByText(message)).toBeVisible();
    expect(within(screen.getByRole('article')).getByText('Đã ghi nhận gửi')).toBeVisible();
    expect(screen.getByText(/Không gửi lại email hoặc thay đổi biên nhận/)).toBeVisible();
  });

  it('restores URL filters and searches recipient or subject, then clears no results', async () => {
    const fetch = mockApi([row, { ...row, id: 'receipt-2', status: 'unknown', email_subject: 'Beta', recipients: { to: ['beta@example.test'] } }]);
    const router = renderHistory('/sent-review?q=beta&status=attention');
    const user = userEvent.setup();
    expect(await screen.findByText('1 / 2 yêu cầu · Trong tối đa 100 yêu cầu gần nhất')).toBeVisible();
    expect(screen.getByRole('searchbox')).toHaveValue('beta');
    expect(screen.queryByRole('heading', { name: row.email_subject })).not.toBeInTheDocument();
    await user.clear(screen.getByRole('searchbox'));
    await user.type(screen.getByRole('searchbox'), 'missing');
    expect(new URLSearchParams(router.state.location.search).get('status')).toBe('attention');
    expect(screen.getByRole('heading', { name: 'Không có email phù hợp' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Xóa bộ lọc' }));
    expect(router.state.location.search).toBe('');
    await user.type(screen.getByRole('searchbox'), 'alpha@example.test');
    expect(screen.getByRole('heading', { name: row.email_subject })).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'Beta' })).not.toBeInTheDocument();
    expect(verificationCalls(fetch)).toHaveLength(0);
  });

  it('bounds results to ten and preserves page in the URL', async () => {
    mockApi(Array.from({ length: 12 }, (_, index) => ({ ...row, id: `receipt-${index}`, email_subject: `Email ${index}` })));
    const router = renderHistory();
    const user = userEvent.setup();
    await screen.findByText('Trang 1 / 2');
    expect(screen.getAllByRole('article')).toHaveLength(10);
    await user.click(screen.getByRole('button', { name: 'Trang sau' }));
    expect(screen.getAllByRole('article')).toHaveLength(2);
    expect(new URLSearchParams(router.state.location.search).get('page')).toBe('2');
    await act(async () => { await router.navigate(-1); });
    expect(screen.getAllByRole('article')).toHaveLength(10);
  });

  it('discloses approved content and keeps technical identifiers secondary', async () => {
    mockApi(); renderHistory();
    const user = userEvent.setup();
    await screen.findByRole('heading', { name: row.email_subject });
    expect(screen.getByText('Mã Gmail đã lưu: gmail-1')).not.toBeVisible();
    expect(screen.getByText(/Nội dung được duyệt/)).not.toBeVisible();
    await user.click(screen.getByText('Đọc email đã duyệt'));
    expect(screen.getByText(/Nội dung được duyệt/)).toBeVisible();
    expect(screen.getByText(/UTC\+7/)).toHaveTextContent('16:00:00');
  });

  it('recovers a failed list into a genuine empty state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json({ detail: 'Unavailable' }, { status: 503 })).mockResolvedValueOnce(Response.json([])));
    renderHistory();
    const user = userEvent.setup();
    await screen.findByRole('alert');
    expect(screen.queryByText('Chưa có yêu cầu gửi email')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Thử lại' }));
    expect(await screen.findByRole('heading', { name: 'Chưa có yêu cầu gửi email' })).toBeVisible();
  });

  it('keeps a verification failure retryable only by another click', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(Response.json([row]))
      .mockResolvedValueOnce(Response.json({ detail: 'Gmail unavailable' }, { status: 503 }))
      .mockResolvedValueOnce(Response.json({ verification: 'matched', provider_id: 'gmail-1' }));
    vi.stubGlobal('fetch', fetch);
    renderHistory();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Kiểm tra trên Gmail' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Gmail unavailable');
    expect(verificationCalls(fetch)).toHaveLength(1);
    expect(screen.getByText('Chưa kiểm tra được Gmail. Bạn có thể bấm kiểm tra để thử lại.')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Kiểm tra trên Gmail' }));
    expect(await screen.findByText('Email trong thư mục Đã gửi trên Gmail khớp phiên bản đã duyệt.')).toBeVisible();
    expect(verificationCalls(fetch)).toHaveLength(2);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
