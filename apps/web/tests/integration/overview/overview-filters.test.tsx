import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { Overview } from '../../../src/features/research';

const runs = [
  { id: 'old', company_name: 'Alpha Research', domain: 'alpha.example', status: 'running', created_at: '2026-10-28T09:00:00Z' },
  { id: 'report', company_name: 'Beta Reports', domain: 'beta.example', status: 'draft_ready', created_at: '2026-10-30T09:00:00Z' },
  { id: 'new', company_name: 'Alpha Queued', domain: 'queue.example', status: 'queued', created_at: '2026-10-29T09:00:00Z' },
];

function renderOverview(path = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const router = createMemoryRouter([
    { path: '/', element: <Overview /> },
    { path: '/research/:id', element: <h1>Research detail</h1> },
  ], { initialEntries: [path] });
  render(<QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider>);
  return router;
}

describe('overview filters and recovery', () => {
  it('preserves a search containing all while retaining the selected status', async () => {
    const companies = [
      ...runs,
      { id: 'allianz', company_name: 'Allianz', domain: 'allianz.example', status: 'running', created_at: '2026-10-30T10:00:00Z' },
      { id: 'allianz-report', company_name: 'Allianz Report', domain: 'reports.allianz.example', status: 'draft_ready', created_at: '2026-10-30T11:00:00Z' },
    ];
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => Response.json(companies)));
    const user = userEvent.setup();
    const router = renderOverview('/?status=active');
    await screen.findByText('3 / 5 nghiên cứu');
    await user.type(screen.getByRole('searchbox'), 'allianz');
    expect(screen.getByRole('searchbox')).toHaveValue('allianz');
    expect(new URLSearchParams(router.state.location.search).get('q')).toBe('allianz');
    expect(new URLSearchParams(router.state.location.search).get('status')).toBe('active');
    expect(screen.getByText('1 / 5 nghiên cứu')).toBeVisible();
    expect(screen.getByRole('link', { name: /Allianz\s*allianz\.example/ })).toHaveAttribute('href', '/research/allianz');
    expect(screen.queryByText('Allianz Report')).not.toBeInTheDocument();
    expect(screen.queryByText('Alpha Research')).not.toBeInTheDocument();
  });

  it('combines URL search with active statuses, orders newest first, and restores filters after returning', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => Response.json(runs)));
    const user = userEvent.setup();
    const router = renderOverview('/?q=ALPHA&status=active');
    expect(await screen.findByText('2 / 3 nghiên cứu')).toBeVisible();
    expect(screen.getByRole('searchbox', { name: 'Tìm nghiên cứu' })).toHaveValue('ALPHA');
    expect(screen.getByRole('button', { name: 'Đang xử lý' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByText('Beta Reports')).not.toBeInTheDocument();
    const links = screen.getAllByRole('link').filter((link) => /Alpha/.test(link.textContent ?? ''));
    expect(links.map((link) => link.getAttribute('href'))).toEqual(['/research/new', '/research/old']);
    await user.click(within(links[0]).getByText('Alpha Queued'));
    expect(await screen.findByRole('heading', { name: 'Research detail' })).toBeVisible();
    await act(async () => { await router.navigate(-1); });
    expect(await screen.findByText('2 / 3 nghiên cứu')).toBeVisible();
    expect(screen.getByRole('searchbox')).toHaveValue('ALPHA');
    expect(screen.getByRole('button', { name: 'Đang xử lý' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('updates URL filters through interaction and clears a no-match result without showing first-use onboarding', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => Response.json(runs)));
    const user = userEvent.setup();
    const router = renderOverview();
    await screen.findByText('3 / 3 nghiên cứu');
    await user.click(screen.getByRole('button', { name: 'Có báo cáo' }));
    await user.type(screen.getByRole('searchbox'), 'missing.example');
    expect(new URLSearchParams(router.state.location.search).get('status')).toBe('draft_ready');
    expect(new URLSearchParams(router.state.location.search).get('q')).toBe('missing.example');
    expect(screen.getByRole('heading', { name: 'Không có nghiên cứu phù hợp' })).toBeVisible();
    expect(screen.queryByText('Bắt đầu từ một doanh nghiệp.')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Xóa bộ lọc' }));
    expect(screen.getByText('3 / 3 nghiên cứu')).toBeVisible();
    expect(router.state.location.search).toBe('');
    expect(screen.getByRole('searchbox')).toHaveValue('');
  });

  it('shows a retryable failure instead of an empty workspace, then recovers to the true empty state', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(Response.json({ detail: 'Research service unavailable' }, { status: 503 }))
      .mockResolvedValueOnce(Response.json([]));
    vi.stubGlobal('fetch', fetch);
    const user = userEvent.setup();
    renderOverview();
    expect(await screen.findByRole('alert')).toHaveTextContent('Research service unavailable');
    expect(screen.queryByText('Bắt đầu từ một doanh nghiệp.')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Thử lại' }));
    expect(await screen.findByRole('heading', { name: 'Bắt đầu từ một doanh nghiệp.' })).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('link', { name: /Chọn email hoặc cuộc họp/ })).toHaveAttribute('href', '/inputs');
  });
});
