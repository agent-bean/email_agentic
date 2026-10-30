import { describe, expect, it, vi } from 'vitest';
import { api, post } from '../../../src/lib/api';

describe('API transport', () => {
  it('preserves server conflict details for the review UI', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'Report version changed' }), { status: 409 },
    )));
    await expect(api('/runs/example')).rejects.toThrow('Report version changed');
  });

  it('handles non-JSON gateway errors without leaking HTML', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>gateway</html>', { status: 502 })));
    await expect(api('/runs')).rejects.toThrow('Yêu cầu không thành công (502).');
  });

  it('retains an explicit idempotency key and request body on retries', async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response('{"id":"run-id"}')));
    vi.stubGlobal('fetch', fetch);
    const body = { company_name: 'Example', domain: 'example.org' };
    await post('/runs', body, 'same-request-key');
    await post('/runs', body, 'same-request-key');
    for (const call of fetch.mock.calls) {
      expect(call[0]).toBe('/api/v1/runs');
      expect(call[1]).toMatchObject({
        method: 'POST', body: JSON.stringify(body),
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': 'same-request-key' },
      });
    }
  });
});

describe('generated endpoint contracts', () => {
  it('encodes path values and preserves cancellation signals', async () => {
    const { endpoints } = await import('../../../src/lib/api');
    const fetch = vi.fn().mockResolvedValue(new Response('{}'));
    vi.stubGlobal('fetch', fetch);
    const controller = new AbortController();
    await endpoints.input('source/with space', controller.signal);
    expect(fetch).toHaveBeenCalledWith('/api/v1/inputs/source%2Fwith%20space', expect.objectContaining({ signal: controller.signal, method: 'GET' }));
  });

  it('binds research submission to its typed body and stable idempotency key', async () => {
    const { endpoints } = await import('../../../src/lib/api');
    const fetch = vi.fn().mockResolvedValue(new Response('{"id":"run-id"}'));
    vi.stubGlobal('fetch', fetch);
    await endpoints.createRun({ company_name: 'Example', domain: 'example.org', context: '' }, 'stable-key');
    expect(fetch).toHaveBeenCalledWith('/api/v1/runs', expect.objectContaining({
      method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': 'stable-key' },
    }));
    if (false) {
      // @ts-expect-error The generated request requires a domain.
      void endpoints.createRun({ company_name: 'Example' }, 'stable-key');
      // @ts-expect-error Approval is boolean, not an arbitrary payload.
      void endpoints.decide('approval-id', 'yes');
      // @ts-expect-error Report editing requires a versioned payload.
      void endpoints.editReport('run-id', { email_subject: 'Unversioned' });
    }
  });
});
