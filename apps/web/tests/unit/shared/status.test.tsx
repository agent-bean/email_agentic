import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { ErrorMessage, Status } from '../../../src/components/status';
import { api, ApiError } from '../../../src/lib/api';
import { I18nProvider, useI18n } from '../../../src/lib/i18n';

afterEach(() => { localStorage.removeItem('email-assistant-language'); });

function ErrorWithLanguageSwitch({ error }: { error: unknown }) {
  const { setLanguage } = useI18n();
  return <><ErrorMessage error={error} /><button onClick={() => setLanguage('en')}>English</button></>;
}

describe('shared feedback', () => {
  it('distinguishes ambiguous sends from successful sends', () => {
    render(<><Status value="unknown" /><Status value="sent" /></>);
    expect(screen.getByText('Cần đối chiếu')).toBeVisible();
    expect(screen.getByText('Đã gửi')).toBeVisible();
  });
  it('exposes errors to assistive technology and renders text safely', () => {
    render(<ErrorMessage error={new Error('<script>unsafe</script>')} />);
    expect(screen.getByRole('alert')).toHaveTextContent('<script>unsafe</script>');
    expect(document.querySelector('script')).toBeNull();
  });
  it('does not announce a nonexistent error', () => {
    render(<ErrorMessage error={null} />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it.each([
    ['gateway HTML', '<html>gateway</html>', 502],
    ['validation details', JSON.stringify({ detail: [{ msg: 'Invalid input' }] }), 422],
  ])('translates the existing %s fallback when language changes', async (_name, body, status) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status })));
    const error = await api('/runs').catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status, detail: null });
    render(<I18nProvider><ErrorWithLanguageSwitch error={error} /></I18nProvider>);
    expect(screen.getByRole('alert')).toHaveTextContent(`Yêu cầu không thành công (${status}).`);
    await userEvent.setup().click(screen.getByRole('button', { name: 'English' }));
    expect(screen.getByRole('alert')).toHaveTextContent(`Request failed (${status}).`);
    expect(screen.queryByText('gateway')).not.toBeInTheDocument();
  });

  it('retains server-provided details in English', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ detail: 'Phiên bản đã thay đổi' }, { status: 409 })));
    const error = await api('/runs').catch((caught: unknown) => caught);
    expect(error).toMatchObject({ status: 409, detail: 'Phiên bản đã thay đổi' });
    localStorage.setItem('email-assistant-language', 'en');
    render(<I18nProvider><ErrorMessage error={error} /></I18nProvider>);
    expect(screen.getByRole('alert')).toHaveTextContent('Phiên bản đã thay đổi');
  });
});
