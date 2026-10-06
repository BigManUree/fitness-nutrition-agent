import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../auth/AuthProvider';
import { ApiError } from '../api/client';
import Login from './Login';

vi.mock('../api/auth', () => ({
  me: vi.fn().mockRejectedValue(new Error('401')),
  logout: vi.fn(),
  login: vi.fn(),
}));

import { login } from '../api/auth';

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{ui}</AuthProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('Login', () => {
  beforeEach(() => {
    vi.mocked(login).mockReset();
  });

  it('submits and shows error on wrong password', async () => {
    vi.mocked(login).mockRejectedValue(
      new ApiError(401, { detail: '用户名或密码错误' }),
    );
    renderWithProviders(<Login />);
    await userEvent.type(screen.getByLabelText('用户名'), 'alice');
    await userEvent.type(screen.getByLabelText('密码'), 'wrongpass');
    await userEvent.click(screen.getByRole('button', { name: /登\s*录/ }));
    await waitFor(() => expect(login).toHaveBeenCalledWith('alice', 'wrongpass'));
    expect(await screen.findByText('用户名或密码错误')).toBeInTheDocument();
  });
});
