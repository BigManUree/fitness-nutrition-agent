import type { Profile } from '../types/profile';
import type { Plan } from '../types/plan';
import { apiFetch } from './client';

export interface GenerateResponse {
  username: string;
  plan: Plan;
  validation: { valid: boolean; violations?: string[] } | null;
  errors: string[];
}

export function generatePlan(profile: Profile | null) {
  return apiFetch<GenerateResponse>('/api/plans/generate', {
    method: 'POST',
    body: JSON.stringify({ profile, persist: true }),
  });
}

export interface LatestPlanResponse {
  plan: Plan;
  created_at: string;
}

export function getLatestPlan() {
  return apiFetch<LatestPlanResponse>('/api/plans/latest');
}

export function persistPlan(plan: Plan) {
  return apiFetch<LatestPlanResponse>('/api/plans/latest', {
    method: 'PUT',
    body: JSON.stringify({ plan }),
  });
}
