import { expect, test } from '@playwright/test';

test('persists language across reload and keeps workspace pages usable', async ({ page }, testInfo) => {
  await page.goto('/research/new');
  await expect(page.locator('html')).toHaveAttribute('lang', 'vi');
  await page.getByRole('combobox', { name: 'Ngôn ngữ' }).selectOption('en');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page).toHaveTitle('New research · Email Assistant');
  for (const path of ['/inputs?kind=email', '/inputs?kind=calendar', '/sent-review', '/knowledge']) {
    await page.goto(path);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({ path: testInfo.outputPath(path.replace(/[^a-z]/g, '-') + '.png'), fullPage: true });
  }
  await page.getByRole('combobox', { name: 'Language' }).selectOption('vi');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('lang', 'vi');
});
