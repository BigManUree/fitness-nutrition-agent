import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Spin } from 'antd';
import { AuthProvider } from './auth/AuthProvider';
import ProtectedRoute from './components/ProtectedRoute';

// 路由级代码分割：每个页面独立 chunk，首屏只加载登录所需代码
const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));
const Plan = lazy(() => import('./pages/Plan'));
const Profile = lazy(() => import('./pages/Profile'));
const Chat = lazy(() => import('./pages/Chat'));

const fallback = <Spin style={{ display: 'block', margin: '120px auto' }} />;

export default function App() {
  return (
    <AuthProvider>
      <Suspense fallback={fallback}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
          <Route path="/plan" element={<ProtectedRoute><Plan /></ProtectedRoute>} />
          <Route path="/chat" element={<ProtectedRoute><Chat /></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/plan" replace />} />
        </Routes>
      </Suspense>
    </AuthProvider>
  );
}
