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
