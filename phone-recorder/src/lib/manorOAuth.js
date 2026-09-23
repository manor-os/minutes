export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8002';

export async function startManorSignIn(next = '/') {
  const response = await fetch(`${API_BASE_URL}/api/auth/oauth/manor/start?${new URLSearchParams({ next })}`, { credentials: 'include' });
  const result = await response.json();
  if (!response.ok || !result.authorize_url || !result.state) {
    throw new Error(result.detail || 'Manor sign-in is unavailable.');
  }
  sessionStorage.setItem('manor_oauth_state', result.state);
  window.location.assign(result.authorize_url);
}
