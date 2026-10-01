import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from './AuthProvider';

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

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.mocked(me).mockReset();
  });

  it('sets user when /api/me succeeds', async () => {
    vi.mocked(me).mockResolvedValue({ username: 'alice' });
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    expect(screen.getByText('loading')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('user: alice')).toBeInTheDocument());
  });

  it('leaves user null when /api/me rejects', async () => {
    vi.mocked(me).mockRejectedValue(new Error('401'));
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText('user: none')).toBeInTheDocument());
  });
});
