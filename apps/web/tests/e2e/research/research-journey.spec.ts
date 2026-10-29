import { expect, test } from '@playwright/test';

test('creates a research request, persists it, and keeps publication gated', async ({ page }, testInfo) => {
  const company = `Browser journey ${testInfo.project.name} ${Date.now()}`;
  await page.goto('/research/new');
  await page.getByLabel('Tên doanh nghiệp').fill(company);
  await page.getByLabel(/Domain chính thức/).fill('example.org');
  await page.getByLabel(/Email gốc/).fill('Customer asks about document processing.');
  await page.getByLabel(/Yêu cầu nghiên cứu/).fill('Investigate relevant evidence.');
  await page.getByRole('button', { name: 'Tạo nghiên cứu' }).click();
  await expect(page).toHaveURL(/\/research\/[a-f0-9-]+$/);
  await expect(page.getByRole('heading', { name: company, exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: company, exact: true })).toBeVisible();
  const id = page.url().split('/').at(-1);
  const response = await page.request.get(`/api/v1/runs/${id}`);
  expect(response.ok()).toBeTruthy();
  const detail = await response.json();
  expect(detail.run.source_email).toBe('Customer asks about document processing.');
  expect(detail.run.context).toBe('Investigate relevant evidence.');
  expect(detail.actions).toEqual([]);
  expect(detail.approvals).toEqual([]);
  await expect(page.getByRole('button', { name: /^Duyệt/ })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

test('shows backend validation without losing entered values', async ({ page }) => {
  await page.goto('/research/new');
  await page.getByLabel('Tên doanh nghiệp').fill('Invalid domain case');
  await page.getByLabel(/Domain chính thức/).fill('https://example.org/path');
  await page.getByRole('button', { name: 'Tạo nghiên cứu' }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByLabel('Tên doanh nghiệp')).toHaveValue('Invalid domain case');
  await expect(page.getByRole('button', { name: 'Tạo nghiên cứu' })).toBeEnabled();
});
