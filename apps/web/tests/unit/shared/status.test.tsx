import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ErrorMessage, Status } from '../../../src/components/status';

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
});
