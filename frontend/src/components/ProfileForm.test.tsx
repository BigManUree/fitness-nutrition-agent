import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ProfileForm from './ProfileForm';

describe('ProfileForm 校验', () => {
  it('缺装备时阻止提交并提示', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<ProfileForm onSave={onSave} onSaved={() => {}} saving={false} />);

    await userEvent.click(screen.getByRole('button', { name: '保存画像' }));
    await waitFor(() => expect(onSave).not.toHaveBeenCalled());
    expect(await screen.findByText('请至少选择一种器械')).toBeInTheDocument();
  });

  it('年龄越界提示', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<ProfileForm onSave={onSave} onSaved={() => {}} saving={false} />);
    await userEvent.type(screen.getByLabelText('年龄'), '200');
    await userEvent.click(screen.getByRole('button', { name: '保存画像' }));
    expect(
      await screen.findByText('年龄需在 14–80 之间', {}, { timeout: 3000 }),
    ).toBeInTheDocument();
  });
});
