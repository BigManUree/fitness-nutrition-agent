export const UNAUTHORIZED_EVENT = 'app:unauthorized';

/** 全局广播「会话失效」：AuthProvider 监听后清会话，受保护路由随之跳转登录。 */
export function notifyUnauthorized(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    // FastAPI 错误体固定为 {"detail": ...}；字符串 detail 直接展示，
    // 校验错误数组等结构化 detail 退化为通用文案
    const message =
      typeof detail === 'object' &&
      detail !== null &&
      typeof (detail as { detail?: unknown }).detail === 'string'
        ? ((detail as { detail: string }).detail)
        : typeof detail === 'string'
          ? detail
          : `请求失败（${status}）`;
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const resp = await fetch(path, { ...init, headers, credentials: 'include' });
  if (!resp.ok) {
    // spec §8：401 一律清会话 → 跳登录（由 AuthProvider 监听该事件）
    if (resp.status === 401) notifyUnauthorized();
    let detail: unknown = null;
    try {
      detail = await resp.json();
    } catch {
      detail = await resp.text().catch(() => null);
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export function isUnauthorized(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}
