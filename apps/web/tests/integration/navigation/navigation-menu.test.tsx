import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../../../src/app/app';

function renderApp(path = '/research/new') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>);
}

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
});
