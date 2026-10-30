import { lazy } from 'react';
import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RouteBoundary } from '../../../src/components/route-boundary';
import { I18nProvider } from '../../../src/lib/i18n';

afterEach(() => { localStorage.clear(); vi.restoreAllMocks(); });

describe('deferred route rendering', () => {
  it.each([
    ['vi', 'Đang tải trang…'],
    ['en', 'Loading page…'],
  ])('announces loading in %s until the route is ready', async (language, message) => {
    localStorage.setItem('email-assistant-language', language);
    let finish!: (module: { default: () => React.JSX.Element }) => void;
    const Page = lazy(() => new Promise<{ default: () => React.JSX.Element }>(resolve => { finish = resolve; }));
    render(<I18nProvider><RouteBoundary><Page /></RouteBoundary></I18nProvider>);
    expect(screen.getByRole('status')).toHaveTextContent(message);
    await act(async () => { finish({ default: () => <h1>Report content</h1> }); });
    expect(screen.getByRole('heading', { name: 'Report content' })).toBeVisible();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it.each([
    ['vi', 'Không tải được trang. Tải lại để thử lại.', 'Tải lại trang'],
    ['en', 'Could not load this page. Reload to try again.', 'Reload page'],
  ])('offers recovery in %s when a route download fails', async (language, message, button) => {
    localStorage.setItem('email-assistant-language', language);
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const Page = lazy(() => Promise.reject(new Error('Chunk download failed')));
    render(<I18nProvider><nav>Workspace navigation</nav><RouteBoundary><Page /></RouteBoundary></I18nProvider>);
    expect(await screen.findByRole('alert')).toHaveTextContent(message);
    expect(screen.getByRole('button', { name: button })).toBeVisible();
    expect(screen.getByRole('navigation')).toBeVisible();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
