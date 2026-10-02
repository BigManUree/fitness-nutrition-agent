import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../auth/AuthProvider';
import { getProfile } from '../api/profile';
import type { Profile } from '../types/profile';
import Plan from './Plan';

vi.mock('../api/auth', () => ({
  me: vi.fn().mockResolvedValue({ username: 'x' }),
  logout: vi.fn(),
}));

vi.mock('../api/profile', () => ({
  getProfile: vi.fn(),
  saveProfile: vi.fn(),
}));

const STORED_PROFILE: Profile = {
  sex: 'male',
  age: 30,
  height_cm: 175,
  weight_kg: 72,
  goal: 'muscle_gain',
  days_per_week: 4,
  equipment: ['barbell'],
};

describe('Plan page cache', () => {
  it('shows the cached plan (with Chat substitutions) when navigating back', async () => {
    vi.mocked(getProfile).mockResolvedValue({
      username: 'x',
      profile: STORED_PROFILE,
    });
    const qc = new QueryClient();
    qc.setQueryData(['plan'], {
      weekly_plan: [
        { day: 1, focus: '腿', exercises: [{ name: 'Squat' }] },
      ],
      rationale: 'cached-rationale',
    });

    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <AuthProvider>
            <Plan />
          </AuthProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    );

    // 未点「生成」也应看到缓存（含 Chat 已应用的替换）
    expect(await screen.findByText('cached-rationale')).toBeInTheDocument();
  });
});
