import { createContext, useContext } from 'react';

export interface AuthContextValue {
  user: string | null;
  loading: boolean;
  logout: () => Promise<void>;
  setUser: (username: string | null) => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth 必须在 AuthProvider 内使用');
  return ctx;
}
