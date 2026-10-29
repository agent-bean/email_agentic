import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { NewResearch } from '../../../src/features/research';

function renderForm(path = '/research/new') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}>
    <Routes><Route path="/research/new" element={<NewResearch />} />
      <Route path="/research/:id" element={<h1>Research detail reached</h1>} /></Routes>
  </MemoryRouter></QueryClientProvider>);
}

describe('research creation UI and transport', () => {
  it('keeps customer email separate from internal research instructions', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{"id":"created"}', { status: 202 }));
    vi.stubGlobal('fetch', fetch);
    const user = userEvent.setup();
    renderForm();
    await user.type(screen.getByLabelText('Tên doanh nghiệp'), 'Example Company');
    await user.type(screen.getByLabelText(/Domain chính thức/), 'example.org');
    await user.type(screen.getByLabelText(/Email gốc/), 'Customer asks about OCR');
    await user.type(screen.getByLabelText(/Yêu cầu nghiên cứu/), 'Check evidence and scope');
    await user.click(screen.getByRole('button', { name: 'Tạo nghiên cứu' }));
    expect(await screen.findByRole('heading', { name: 'Research detail reached' })).toBeVisible();
    const payload = JSON.parse(fetch.mock.calls[0][1].body);
    expect(payload).toMatchObject({ source_email: 'Customer asks about OCR', context: 'Check evidence and scope' });
    expect(payload).not.toHaveProperty('approve');
    expect(payload).not.toHaveProperty('send_email');
  });

  it('preserves input and the idempotency key after a failed submission', async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response(
      '{"detail":"Temporary failure"}', { status: 503 },
    )));
    vi.stubGlobal('fetch', fetch);
    const user = userEvent.setup();
    renderForm();
    await user.type(screen.getByLabelText('Tên doanh nghiệp'), 'Example Company');
    await user.type(screen.getByLabelText(/Domain chính thức/), 'example.org');
    await user.click(screen.getByRole('button', { name: 'Tạo nghiên cứu' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Temporary failure');
    expect(screen.getByLabelText('Tên doanh nghiệp')).toHaveValue('Example Company');
    await user.click(screen.getByRole('button', { name: 'Tạo nghiên cứu' }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(fetch.mock.calls[0][1].headers['Idempotency-Key']).toBe(fetch.mock.calls[1][1].headers['Idempotency-Key']);
  });

  it('blocks submission when the selected source cannot be loaded', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"Not found"}', { status: 404 })));
    renderForm('/research/new?input=missing');
    expect(await screen.findByRole('alert')).toHaveTextContent('Not found');
    expect(screen.getByRole('button', { name: 'Tạo nghiên cứu' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Tải lại nguồn' })).toBeEnabled();
  });
});
