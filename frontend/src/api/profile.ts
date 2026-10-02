import type { Profile } from '../types/profile';
import { apiFetch } from './client';

export interface ProfileResponse {
  username: string;
  profile: Profile;
}

export interface ProfileSaveResponse {
  username: string;
  status: string;
  indexing_warning?: string | null;
}

export function getProfile() {
  return apiFetch<ProfileResponse>('/api/profile');
}

export function saveProfile(profile: Profile) {
  return apiFetch<ProfileSaveResponse>('/api/profile', {
    method: 'PUT',
    body: JSON.stringify(profile),
  });
}
