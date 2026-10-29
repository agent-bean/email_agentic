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
