import { describe, it, expect, vi, afterEach } from 'vitest';
import { apiFetch, ApiError, isUnauthorized, UNAUTHORIZED_EVENT } from './client';

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

  it('unwraps the FastAPI {detail} envelope into the error message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: '画像保存失败：字段非法' }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    const err = await apiFetch('/api/profile', { method: 'PUT' }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).message).toBe('画像保存失败：字段非法');
  });

  it('falls back to a generic message for non-string detail bodies', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: [{ loc: ['age'], msg: 'invalid' }] }), {
          status: 422,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    const err = await apiFetch('/api/profile', { method: 'PUT' }).catch((e) => e);
    expect((err as ApiError).message).toBe('请求失败（422）');
  });

  it('dispatches the unauthorized event on 401', async () => {
    let signaled = false;
    window.addEventListener(
      UNAUTHORIZED_EVENT,
      () => {
        signaled = true;
      },
      { once: true },
    );
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: '未登录' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    await apiFetch('/api/me').catch(() => {});
    expect(signaled).toBe(true);
  });
});
