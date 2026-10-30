import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Knowledge } from '../../../src/features/knowledge';
import { I18nProvider } from '../../../src/lib/i18n';

afterEach(() => { localStorage.removeItem('email-assistant-language'); });

const reports = Array.from({ length: 30 }, (_, index) => ({
  id: `report-${index}`, run_id: `run-${index}`, status: index % 2 ? 'draft' : 'approved',
  content: `# Công ty ${index}\n\nNội dung riêng ${index}.\n\n## Chi tiết\n\n- **Bằng chứng**\n\n| Nguồn | Ghi chú |\n| --- | --- |\n| Trang web | Cần đối chiếu |`,
  created_at: '2026-10-30T09:00:00Z',
}));

function setup(path = '/knowledge', data = reports, fail = false) {
  const fetch = vi.fn().mockImplementation(async () => fail
    ? Response.json({ detail: 'Knowledge unavailable' }, { status: 503 }) : Response.json(data));
  vi.stubGlobal('fetch', fetch);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const router = createMemoryRouter([{ path: '/knowledge', element: <Knowledge /> }, { path: '/research/:id', element: <h1>Nghiên cứu gốc</h1> }], { initialEntries: [path] });
  render(<I18nProvider><QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider></I18nProvider>);
  return { router, fetch };
}

describe('saved knowledge library', () => {
  it('uses the saved English preference while retaining original report content', async () => {
    localStorage.setItem('email-assistant-language', 'en');
    setup();
    await screen.findByText('30 / 30 reports · Up to 100 most recent records');
    expect(screen.getByRole('heading', { name: 'Knowledge library' })).toBeVisible();
    expect(screen.getByRole('searchbox', { name: 'Search reports' })).toBeVisible();
    await userEvent.setup().click(screen.getByRole('link', { name: /Công ty 0 / }));
    expect(screen.getByRole('article', { name: 'Report content' })).toHaveTextContent('Nội dung riêng 0.');
    expect(screen.getByRole('link', { name: 'Open original research' })).toBeVisible();
    expect(screen.getByText(`Saved ${new Date(reports[0].created_at).toLocaleString('en-GB')}`)).toBeVisible();
    expect(screen.queryByText('Mở nghiên cứu gốc')).not.toBeInTheDocument();
  });
  it('bounds a long library and keeps pagination in the URL', async () => {
    const { router, fetch } = setup();
    const user = userEvent.setup();
    await screen.findByText('30 / 30 báo cáo · Tối đa 100 bản gần nhất');
    expect(screen.getAllByRole('listitem')).toHaveLength(12);
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
    expect(screen.queryByText('Nội dung riêng 0.')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Trang sau' }));
    expect(router.state.location.search).toBe('?page=2');
    await user.click(screen.getByRole('link', { name: /Công ty 12 / }));
    expect(screen.getByRole('article')).toBeVisible();
    await user.click(screen.getByRole('link', { name: /Danh sách báo cáo/ }));
    expect(screen.getByText('Trang 2 / 3')).toBeVisible();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('searches report contents, renders Markdown and restores search with browser back', async () => {
    const { router } = setup();
    const user = userEvent.setup();
    await screen.findByText('30 / 30 báo cáo · Tối đa 100 bản gần nhất');
    await user.type(screen.getByRole('searchbox'), 'Nội dung riêng 19.');
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
    await user.click(screen.getByRole('link', { name: /Công ty 19 / }));
    expect(screen.getByRole('heading', { name: 'Chi tiết' })).toBeVisible();
    expect(screen.getByRole('table')).toBeVisible();
    expect(screen.getByText('Bằng chứng').tagName).toBe('STRONG');
    expect(screen.getByText(/Bản nháp được lưu tự động/)).toBeVisible();
    expect(screen.getByRole('link', { name: 'Mở nghiên cứu gốc' })).toHaveAttribute('href', '/research/run-19');
    expect(screen.getByRole('heading', { level: 2, name: 'Công ty 19' })).toHaveFocus();
    await act(async () => { await router.navigate(-1); });
    expect(screen.getByRole('searchbox')).toHaveValue('Nội dung riêng 19.');
    expect(screen.getByRole('searchbox')).toHaveFocus();
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
  });

  it('restores approval filters and distinguishes no matches from first use', async () => {
    setup('/knowledge?status=approved&q=Nội+dung+riêng+19.');
    await screen.findByRole('heading', { name: 'Không có báo cáo phù hợp' });
    expect(screen.getByRole('combobox')).toHaveValue('approved');
    expect(screen.queryByText('Chưa có báo cáo được lưu')).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Xóa bộ lọc' }));
    expect(screen.getAllByRole('listitem')).toHaveLength(12);
  });

  it('handles missing selected reports without silently opening another', async () => {
    setup('/knowledge?report=missing');
    expect(await screen.findByRole('heading', { name: 'Không tìm thấy báo cáo' })).toBeVisible();
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
  });

  it('shows first use with no saved reports', async () => {
    setup('/knowledge', []);
    expect(await screen.findByRole('heading', { name: 'Chưa có báo cáo được lưu' })).toBeVisible();
  });

  it('shows a retryable failure instead of an empty library', async () => {
    const { fetch } = setup('/knowledge', reports, true);
    expect(await screen.findByRole('alert')).toHaveTextContent('Knowledge unavailable');
    expect(screen.queryByText('Chưa có báo cáo được lưu')).not.toBeInTheDocument();
    fetch.mockImplementation(async () => Response.json(reports));
    await userEvent.setup().click(screen.getByRole('button', { name: 'Làm mới' }));
    expect(await screen.findByText('30 / 30 báo cáo · Tối đa 100 bản gần nhất')).toBeVisible();
  });
});
