import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../../src/app/app';

function renderApp(path = '/research/new') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>);
}

afterEach(() => localStorage.clear());

describe('navigation menu keyboard behavior', () => {
  it('closes on Escape from a navigation link and returns focus to its toggle', async () => {
    const user = userEvent.setup();
    renderApp();
    const toggle = screen.getByRole('button', { name: 'Menu' });
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const navigation = screen.getByRole('navigation', { name: 'Điều hướng chính' });
    expect(toggle).toHaveAttribute('aria-controls', navigation.id);
    within(navigation).getByRole('link', { name: 'Tổng quan' }).focus();
    await user.keyboard('{Escape}');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveFocus();
  });

  it('closes after choosing a route and updates the active navigation and document title', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => Response.json([])));
    const user = userEvent.setup();
    renderApp();
    await user.click(screen.getByRole('button', { name: 'Menu' }));
    const overview = within(screen.getByRole('navigation')).getByRole('link', { name: 'Tổng quan' });
    await user.click(overview);
    expect(await screen.findByRole('heading', { name: 'Sẵn sàng cho cuộc trao đổi tiếp theo.' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Menu' })).toHaveAttribute('aria-expanded', 'false');
    expect(overview).toHaveAttribute('aria-current', 'page');
    expect(document.title).toBe('Tổng quan · Email Assistant');
    expect(screen.getByRole('link', { name: 'Đến nội dung' })).toHaveAttribute('href', '#main-content');
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main-content');
    expect(screen.getByRole('main')).toHaveAttribute('tabindex', '-1');
  });

  it('offers a route back from an unknown URL', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => Response.json([])));
    const user = userEvent.setup();
    renderApp('/obsolete');
    expect(screen.getByRole('heading', { name: 'Không tìm thấy trang' })).toBeVisible();
    await user.click(screen.getByRole('link', { name: 'Về tổng quan' }));
    expect(await screen.findByRole('heading', { name: 'Sẵn sàng cho cuộc trao đổi tiếp theo.' })).toBeVisible();
  });

  it('opens the deferred knowledge route from the workspace navigation', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => Response.json([])));
    const user = userEvent.setup();
    renderApp();
    await user.click(within(screen.getByRole('navigation')).getByRole('link', { name: 'Kho tri thức' }));
    expect(await screen.findByRole('heading', { name: 'Chưa có báo cáo được lưu' })).toBeVisible();
    expect(document.title).toBe('Kho tri thức · Email Assistant');
    expect(within(screen.getByRole('navigation')).getByRole('link', { name: 'Kho tri thức' })).toHaveAttribute('aria-current', 'page');
  });
});

describe('interface language', () => {
  it('defaults to Vietnamese, switches the shell and form, and remembers English', async () => {
    const user = userEvent.setup();
    renderApp();
    expect(document.documentElement.lang).toBe('vi');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Ngôn ngữ' }), 'en');
    expect(document.documentElement.lang).toBe('en');
    expect(document.title).toBe('New research · Email Assistant');
    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Incoming email' })).toHaveAttribute('href', '/inputs?kind=email');
    expect(screen.getByRole('link', { name: 'Meetings' })).toHaveAttribute('href', '/inputs?kind=calendar');
    expect(localStorage.getItem('email-assistant-language')).toBe('en');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Language' }), 'vi');
    expect(document.title).toBe('Nghiên cứu mới · Email Assistant');
  });
  it('restores a saved English choice on mount', () => {
    localStorage.setItem('email-assistant-language', 'en');
    renderApp('/obsolete');
    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeVisible();
    expect(document.documentElement.lang).toBe('en');
  });
});
