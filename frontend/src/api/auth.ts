import { apiFetch } from './client';

export interface AuthResult {
  token: string;
  username: string;
}

export function register(username: string, password: string) {
  return apiFetch<AuthResult>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

export function login(username: string, password: string) {
  return apiFetch<AuthResult>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

export function logout() {
  return apiFetch<{ username: string; status: string }>('/api/auth/logout', {
    method: 'POST',
  });
}

export function me() {
  return apiFetch<{ username: string }>('/api/me');
}
