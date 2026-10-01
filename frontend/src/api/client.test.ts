import { describe, it, expect, vi, afterEach } from 'vitest';
import { apiFetch, ApiError, isUnauthorized } from './client';

describe('apiFetch', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('sends credentials include and parses JSON', async () => {
    const spy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ username: 'alice' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', spy);

    const data = await apiFetch<{ username: string }>('/api/me');
    expect(data.username).toBe('alice');
    const [, init] = spy.mock.calls[0];
    expect(init.credentials).toBe('include');
  });

  it('throws ApiError with status on non-2xx', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: '未登录' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    const err = await apiFetch('/api/me').catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(isUnauthorized(err)).toBe(true);
  });
});
