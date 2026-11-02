import { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { RetainedReportEditor } from '../../../src/features/report-editor';
import type { Report } from '../../../src/lib/api';

const original: Report = {
  id: 'report-1', run_id: 'run-1', version: 1, markdown: '# Original',
  email_subject: 'Original subject', email_body: 'Original body',
  recipients: { to: ['customer@example.org'], cc: [], bcc: [] },
  send_email: false, save_kb: false, quality: {}, artifacts: [],
};
const newer: Report = { ...original, id: 'report-2', version: 2, email_subject: 'Other tab subject' };

function mount(refresh = vi.fn()) {
  let updateReport: (report: Report | undefined) => void = () => {};
  function Editor() {
    const [report, setReport] = useState<Report | undefined>(original);
    updateReport = setReport;
    return <RetainedReportEditor readOnly={!report} report={report} runId="run-1" refresh={refresh} onDirty={() => {}} />;
  }
  const router = createMemoryRouter([
    { path: '/', element: <h1>Outside editor</h1> },
    { path: '/edit', element: <Editor /> },
  ], { initialEntries: ['/', '/edit'], initialIndex: 1 });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider>);
  return { router, updateReport: (report: Report | undefined) => act(() => updateReport(report)) };
}

async function editSubject() {
  const user = userEvent.setup();
  await user.click(screen.getByText('Chỉnh sửa nội dung & tùy chọn'));
  const input = screen.getByLabelText('Tiêu đề email');
  await user.clear(input);
  await user.type(input, 'My unsaved subject');
  return user;
}

describe('versioned report editing', () => {
  it('preserves a dirty draft when another tab publishes a new version, then explicitly reloads', async () => {
    const { updateReport } = mount();
    const user = await editSubject();
    updateReport(newer);
    expect(screen.getByLabelText('Tiêu đề email')).toHaveValue('My unsaved subject');
    expect(screen.getByRole('button', { name: 'Lưu phiên bản mới' })).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent('Phiên bản trên máy chủ đã thay đổi');
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    await user.click(screen.getByRole('button', { name: 'Tải phiên bản mới' }));
    expect(screen.getByLabelText('Tiêu đề email')).toHaveValue('My unsaved subject');
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    await user.click(screen.getByRole('button', { name: 'Tải phiên bản mới' }));
    expect(screen.getByLabelText('Tiêu đề email')).toHaveValue('Other tab subject');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('keeps unsaved content in memory when retention removes the server report and forbids saving', async () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    const { updateReport, router } = mount();
    const user = await editSubject();
    updateReport(undefined);
    expect(screen.getByLabelText('Tiêu đề email')).toHaveValue('My unsaved subject');
    expect(screen.getByLabelText('Tiêu đề email')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Lưu phiên bản mới' })).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent('đã hết hạn lưu');
    await user.click(screen.getByRole('button', { name: 'Lưu phiên bản mới' }));
    expect(fetch).not.toHaveBeenCalled();
    await act(() => router.navigate(-1));
    expect(screen.getByRole('alertdialog')).toBeVisible();
  });

  it('blocks history navigation until the operator explicitly discards the draft', async () => {
    const { router } = mount();
    const user = await editSubject();
    await act(() => router.navigate(-1));
    expect(screen.getByRole('alertdialog')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Tiếp tục chỉnh sửa' }));
    expect(screen.getByLabelText('Tiêu đề email')).toHaveValue('My unsaved subject');
    const unload = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);
    await act(() => router.navigate(-1));
    await user.click(screen.getByRole('button', { name: 'Bỏ thay đổi và rời trang' }));
    expect(await screen.findByRole('heading', { name: 'Outside editor' })).toBeVisible();
  });

  it('keeps the original base version and edits after a stale save conflict', async () => {
    const refresh = vi.fn();
    const fetch = vi.fn().mockResolvedValue(new Response('{"detail":"Report version changed"}', { status: 409 }));
    vi.stubGlobal('fetch', fetch);
    const { updateReport } = mount(refresh);
    const user = await editSubject();
    await user.click(screen.getByRole('button', { name: 'Lưu phiên bản mới' }));
    await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toMatchObject({ version: 1, email_subject: 'My unsaved subject' });
    expect(screen.getByLabelText('Tiêu đề email')).toHaveValue('My unsaved subject');
    expect(screen.getByRole('button', { name: 'Lưu phiên bản mới' })).toBeDisabled();
    updateReport(newer);
    expect(screen.getByLabelText('Tiêu đề email')).toHaveValue('My unsaved subject');
  });

  it('adopts the saved version after a successful save without treating it as an external conflict', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"id":"report-2"}')));
    const refresh = vi.fn();
    const { updateReport } = mount(refresh);
    const user = await editSubject();
    await user.click(screen.getByRole('button', { name: 'Lưu phiên bản mới' }));
    await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
    updateReport({ ...newer, email_subject: 'My unsaved subject' });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Lưu phiên bản mới' })).toBeDisabled();
    expect(screen.getByText('Chưa có thay đổi')).toBeVisible();
  });

  it('keeps business-rule conflicts editable rather than falsely requiring a newer version', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"Choose at least one recipient before enabling send"}', { status: 409 })));
    mount();
    const user = await editSubject();
    await user.click(screen.getByRole('button', { name: 'Lưu phiên bản mới' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Choose at least one recipient');
    expect(screen.getByRole('button', { name: 'Lưu phiên bản mới' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Tải phiên bản mới' })).not.toBeInTheDocument();
  });
});
