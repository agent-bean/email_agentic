import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { ResearchProgress } from '../../../src/components/research-progress';

describe('research progress safety guidance', () => {
  it('prioritizes uncertain sending over approval and directs the user to reconciliation', () => {
    render(<MemoryRouter><ResearchProgress status="draft_ready" hasReport approvalStatus="approved" expired={false} hasUnknownAction /></MemoryRouter>);
    expect(screen.getByText('Cần kiểm tra email đã gửi')).toBeVisible();
    expect(screen.getByText(/Kiểm tra lịch sử gửi trước khi quyết định gửi lại/)).toBeVisible();
    expect(screen.getByRole('link', { name: 'Kiểm tra lịch sử gửi' })).toHaveAttribute('href', '/sent-review');
    expect(screen.queryByRole('link', { name: /Xem gói duyệt/ })).not.toBeInTheDocument();
  });

  it('distinguishes approval from successful sending', () => {
    render(<MemoryRouter><ResearchProgress status="draft_ready" hasReport approvalStatus="approved" expired={false} hasUnknownAction={false} /></MemoryRouter>);
    expect(screen.getByText('Đã duyệt. Kiểm tra kết quả gửi / lưu.')).toBeVisible();
    expect(screen.getByText(/Phê duyệt và gửi thành công là hai trạng thái khác nhau/)).toBeVisible();
    expect(screen.getByRole('link', { name: /Xem gói duyệt/ })).toHaveAttribute('href', '#review');
  });

  it.each(['rejected', 'superseded'])('requires a new version for a %s approval even when expired', (approvalStatus) => {
    render(<MemoryRouter><ResearchProgress status="draft_ready" hasReport approvalStatus={approvalStatus} expired hasUnknownAction={false} /></MemoryRouter>);
    expect(screen.getByText('Cần lưu phiên bản mới trước khi duyệt')).toBeVisible();
    expect(screen.queryByText('Quyền duyệt đã hết hạn')).not.toBeInTheDocument();
  });

  it('explains that identity confirmation starts research without suggesting approval', () => {
    render(<MemoryRouter><ResearchProgress status="awaiting_identity" hasReport={false} expired={false} hasUnknownAction={false} /></MemoryRouter>);
    expect(screen.getByText(/Xác nhận này chỉ bắt đầu nghiên cứu/)).toBeVisible();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});
