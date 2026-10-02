import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Profile from './Profile';
import { getProfile, saveProfile } from '../api/profile';

// 把 ProfileForm 替换成最小驱动件：透传保存回调与告警 props
vi.mock('../components/ProfileForm', () => ({
  default: ({ onSave, saveWarning }: any) => (
    <div>
      <span data-testid="warning">{saveWarning ?? ''}</span>
      <button onClick={() => onSave({})}>保存</button>
    </div>
  ),
}));

vi.mock('../api/profile', () => ({
  getProfile: vi.fn(),
  saveProfile: vi.fn(),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <Profile />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('Profile page indexing warning', () => {
  beforeEach(() => {
    vi.mocked(getProfile).mockResolvedValue({ username: 'x', profile: {} as never });
    vi.mocked(saveProfile).mockReset();
  });

  it('clears a previous warning when starting a new save', async () => {
    vi.mocked(saveProfile)
      .mockResolvedValueOnce({
        username: 'x',
        status: 'saved',
        indexing_warning: '向量入库失败（超时）',
      })
      .mockImplementationOnce(
        () => new Promise(() => undefined), // 第二次保存挂起：应立即清掉旧告警
      );

    renderPage();
    const btn = await screen.findByText('保存');
    fireEvent.click(btn);
    expect(await screen.findByTestId('warning')).toHaveTextContent('向量入库失败（超时）');

    fireEvent.click(btn);
    expect(screen.getByTestId('warning')).toBeEmptyDOMElement();
  });
});
