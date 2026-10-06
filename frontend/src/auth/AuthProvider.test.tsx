import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from './AuthProvider';
import { UNAUTHORIZED_EVENT } from '../api/client';

vi.mock('../api/auth', () => ({
  me: vi.fn(),
  logout: vi.fn().mockResolvedValue({ username: 'x', status: 'logged_out' }),
}));

import { me } from '../api/auth';

function Probe() {
  const { user, loading } = useAuth();
  if (loading) return <div>loading</div>;
  return <div>user: {user ?? 'none'}</div>;
}

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.mocked(me).mockReset();
  });

  it('sets user when /api/me succeeds', async () => {
    vi.mocked(me).mockResolvedValue({ username: 'alice' });
    renderWithQueryClient(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    expect(screen.getByText('loading')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('user: alice')).toBeInTheDocument());
  });

  it('leaves user null when /api/me rejects', async () => {
    vi.mocked(me).mockRejectedValue(new Error('401'));
    renderWithQueryClient(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText('user: none')).toBeInTheDocument());
  });

  it('clears user when the unauthorized event fires', async () => {
    vi.mocked(me).mockResolvedValue({ username: 'alice' });
    renderWithQueryClient(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText('user: alice')).toBeInTheDocument());
    act(() => {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    });
    await waitFor(() => expect(screen.getByText('user: none')).toBeInTheDocument());
  });

  it('clears React Query cache on logout to prevent data leakage between users', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    // 模拟用户 A 登录后缓存了一些数据
    queryClient.setQueryData(['plan'], { id: 'user-a-plan' });
    queryClient.setQueryData(['latestPlan'], { plan: { id: 'user-a-plan' } });
    queryClient.setQueryData(['profile'], { username: 'alice' });

    vi.mocked(me).mockResolvedValue({ username: 'alice' });

    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByText('user: alice')).toBeInTheDocument());

    // 验证缓存存在
    expect(queryClient.getQueryData(['plan'])).toBeDefined();
    expect(queryClient.getQueryData(['latestPlan'])).toBeDefined();

    // 触发登出（通过 401 事件）
    act(() => {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    });

    await waitFor(() => expect(screen.getByText('user: none')).toBeInTheDocument());

    // 验证所有缓存被清理，防止新用户看到旧数据
    expect(queryClient.getQueryData(['plan'])).toBeUndefined();
    expect(queryClient.getQueryData(['latestPlan'])).toBeUndefined();
    expect(queryClient.getQueryData(['profile'])).toBeUndefined();
  });
});
