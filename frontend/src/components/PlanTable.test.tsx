import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import PlanTable from './PlanTable';
import type { Plan } from '../types/plan';

const plan: Plan = {
  weekly_plan: [
    {
      day: 1,
      focus: '胸+三头',
      exercises: [
        { name: 'Barbell Bench Press', name_zh: '杠铃卧推', sets: 4, reps: '8-10', rest: '90秒' },
      ],
    },
  ],
};

describe('PlanTable', () => {
  it('renders day and Chinese name with English original', () => {
    render(<PlanTable plan={plan} />);
    expect(screen.getByText(/第 1 天/)).toBeInTheDocument();
    expect(screen.getByText(/杠铃卧推（Barbell Bench Press）/)).toBeInTheDocument();
  });

  it('does not emit duplicate-key warnings for unnamed or repeated exercises', () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const repeated: Plan = {
      weekly_plan: [
        {
          day: 1,
          focus: '胸',
          exercises: [
            { sets: 3, reps: '10' },
            { name: 'Push Up', sets: 3, reps: '10' },
            { name: 'Push Up', sets: 4, reps: '12' },
          ],
        },
      ],
    };

    render(<PlanTable plan={repeated} />);
    expect(screen.getAllByText('Push Up')).toHaveLength(2);
    const hasDupKey = errorSpy.mock.calls.some(
      (call) => typeof call[0] === 'string' && call[0].includes('Encountered two children with the same key'),
    );
    expect(hasDupKey).toBe(false);
    errorSpy.mockRestore();
  });
});
