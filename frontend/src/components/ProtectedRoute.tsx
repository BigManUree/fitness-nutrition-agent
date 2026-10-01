import { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { Spin } from 'antd';
import { useAuth } from '../auth/useAuth';

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) {
    return <Spin style={{ display: 'block', margin: '80px auto' }} />;
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
