import { describe, it, expect } from 'vitest';
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
});
