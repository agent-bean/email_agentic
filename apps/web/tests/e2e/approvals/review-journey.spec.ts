import { expect, test } from '@playwright/test';

test('approves only the saved version and never sends by default', async ({ page }, testInfo) => {
  const listing = await page.request.get('/api/v1/runs');
  const run = (await listing.json()).find((item: { company_name: string }) => item.company_name === `Browser review fixture ${testInfo.project.name}`);
  expect(run).toBeTruthy();
  await page.goto(`/research/${run.id}`);
  const editor = page.locator('details').filter({ has: page.getByText('Chỉnh sửa nội dung & tùy chọn', { exact: true }) });
  await editor.locator('summary').click();
  const subject = editor.getByLabel('Tiêu đề email');
  await subject.fill(`Review ${Date.now()}`);
  await expect(page.getByRole('button', { name: /^Duyệt nội dung/ })).toBeDisabled();
  await editor.getByRole('button', { name: 'Lưu phiên bản mới' }).click();
  await expect(page.getByRole('button', { name: /^Duyệt nội dung/ })).toBeEnabled();
  await page.getByRole('button', { name: /^Duyệt nội dung/ }).click();
  await expect(page.getByText('Đã duyệt nội dung; không yêu cầu gửi email từ ứng dụng.')).toBeVisible();
  const detail = await (await page.request.get(`/api/v1/runs/${run.id}`)).json();
  expect(detail.reports[0].send_email).toBe(false);
  expect(detail.actions).toEqual([]);
  expect(detail.approvals.find((item: { report_id: string }) => item.report_id === detail.reports[0].id).status).toBe('approved');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

test('browser Back preserves unsaved report edits until explicitly discarded', async ({ page }, testInfo) => {
  const listing = await page.request.get('/api/v1/runs');
  const run = (await listing.json()).find((item: { company_name: string }) => item.company_name === `Browser review fixture ${testInfo.project.name}`);
  await page.goto('/');
  await page.locator(`a[href="/research/${run.id}"]`).click();
  const editor = page.locator('#report-editor');
  await editor.locator('summary').click();
  await editor.getByLabel('Tiêu đề email').fill('Unsaved browser draft');
  await page.evaluate(() => history.back());
  await expect(page.getByRole('alertdialog')).toBeVisible();
  await page.getByRole('button', { name: 'Tiếp tục chỉnh sửa' }).click();
  await expect(editor.getByLabel('Tiêu đề email')).toHaveValue('Unsaved browser draft');
  await page.evaluate(() => history.back());
  await page.getByRole('button', { name: 'Bỏ thay đổi và rời trang' }).click();
  await expect(page).toHaveURL(/\/$/);
});

test('a competing saved version preserves the browser draft and requires explicit reload', async ({ page }, testInfo) => {
  const listing = await page.request.get('/api/v1/runs');
  const run = (await listing.json()).find((item: { company_name: string }) => item.company_name === `Browser review fixture ${testInfo.project.name}`);
  await page.goto(`/research/${run.id}`);
  const editor = page.locator('#report-editor');
  await editor.locator('summary').click();
  await editor.getByLabel('Tiêu đề email').fill('Local unsaved subject');
  const detail = await (await page.request.get(`/api/v1/runs/${run.id}`)).json();
  const report = detail.reports[0];
  const saved = await page.request.put(`/api/v1/runs/${run.id}/report`, { headers: { Origin: 'http://127.0.0.1:5173' }, data: {
    version: report.version, markdown: report.markdown, email_subject: 'Competing saved subject',
    email_body: report.email_body, recipients: report.recipients, send_email: false, save_kb: false,
    attachment_formats: [],
  } });
  expect(saved.ok(), `Save returned ${saved.status()}: ${await saved.text()}`).toBe(true);
  // A stale save sees the real version conflict and refreshes the current server snapshot.
  await editor.getByRole('button', { name: 'Lưu phiên bản mới' }).click();
  await expect(editor.getByLabel('Tiêu đề email')).toHaveValue('Local unsaved subject');
  await expect(editor.getByRole('button', { name: 'Tải phiên bản mới' })).toBeEnabled();
  await expect(editor.getByRole('button', { name: 'Lưu phiên bản mới' })).toBeDisabled();
  await expect(page.getByRole('button', { name: /^Duyệt nội dung/ })).toBeDisabled();
  page.once('dialog', (dialog) => dialog.accept());
  await editor.getByRole('button', { name: 'Tải phiên bản mới' }).click();
  await expect(editor.getByLabel('Tiêu đề email')).toHaveValue('Competing saved subject');
  const persisted = await (await page.request.get(`/api/v1/runs/${run.id}`)).json();
  expect(persisted.reports[0].email_subject).toBe('Competing saved subject');
  expect(persisted.actions).toEqual([]);
});
