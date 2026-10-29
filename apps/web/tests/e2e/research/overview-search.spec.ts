import { expect, test } from '@playwright/test';

test('preserves sequential search input and the active filter across reload', async ({ page }, testInfo) => {
  const company = `Allianz browser fixture ${testInfo.project.name}`;
  const created = await page.request.post('/api/v1/runs', {
    headers: { Origin: 'http://127.0.0.1:5173', 'Idempotency-Key': crypto.randomUUID() },
    data: { company_name: company, domain: 'example.org' },
  });
  expect(created.status()).toBe(202);
  await page.goto('/?status=active');
  const search = page.getByRole('searchbox', { name: 'Tìm nghiên cứu' });
  await search.pressSequentially('allianz', { delay: 20 });
  await expect(search).toHaveValue('allianz');
  await expect(page).toHaveURL(/q=allianz/);
  expect(new URL(page.url()).searchParams.get('status')).toBe('active');
  await expect(page.getByRole('link', { name: new RegExp(company) })).toBeVisible();
  await page.reload();
  await expect(search).toHaveValue('allianz');
  await expect(page.getByRole('button', { name: 'Đang xử lý', exact: true })).toHaveAttribute('aria-pressed', 'true');
});
