import { ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
import { me, logout as apiLogout } from '../api/auth';
import { UNAUTHORIZED_EVENT } from '../api/client';
import { AuthContext, AuthContextValue, useAuth } from './useAuth';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    me()
      .then((r) => setUser(r.username))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  // 任意请求收到 401（含其他标签页登出/服务端吊销）→ 清会话，
  // 已挂载的 ProtectedRoute 随即跳转 /login。
  useEffect(() => {
    const onUnauthorized = () => setUser(null);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } catch {
      /* 服务端失败也清本地会话 */
    }
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, logout, setUser }),
    [user, loading, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export { useAuth };
