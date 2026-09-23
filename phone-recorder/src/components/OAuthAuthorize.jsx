import React, { useEffect, useRef, useState } from 'react';
import { API_BASE_URL, startManorSignIn } from '../lib/manorOAuth';
import './Login.css';

export default function OAuthAuthorize() {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState('');
  const [needsLogin, setNeedsLogin] = useState(false);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const query = window.location.search;

  useEffect(() => {
    const controller = new AbortController();
    const token = localStorage.getItem('auth_token');
    fetch(`${API_BASE_URL}/api/oauth/authorize${query}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}, signal: controller.signal,
    }).then(async response => {
      const data = await response.json();
      if (response.status === 401) { setNeedsLogin(true); return; }
      if (!response.ok) throw new Error(data.detail || 'This connection request is invalid.');
      setInfo(data);
    }).catch(err => { if (err.name !== 'AbortError') setError(err.message); });
    return () => controller.abort();
  }, [query]);

  async function signIn() {
    setBusy(true); setError('');
    try { await startManorSignIn(`/oauth/authorize${query}`); }
    catch (err) { setError(err.message); setBusy(false); }
  }

  async function decide(decision) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/oauth/authorize`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('auth_token') || ''}` },
        body: JSON.stringify({ ...Object.fromEntries(new URLSearchParams(query)), decision }),
      });
      const data = await response.json();
      if (!response.ok || !data.redirect_to) throw new Error(data.detail || 'Connection could not be authorized.');
      window.location.assign(data.redirect_to);
    } catch (err) { setError(err.message); setBusy(false); inFlight.current = false; }
  }

  return <main className="login-container"><section className="login-card" aria-labelledby="consent-title" style={{ display: 'flex', flexDirection: 'column', gap: 24, minWidth: 0, overflowWrap: 'anywhere', lineHeight: 1.55 }}>
    <div className="login-header" style={{ marginBottom: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}><img src="/minutes-product-mark.svg" alt="Minutes" className="login-logo" style={{ marginBottom: 0 }} />
      <h1 id="consent-title">Connect Minutes to {info?.client_name || 'Manor AI'}</h1>
      <p className="login-subtitle">Review access to your organization’s meeting notes.</p>
    </div>
    {error && <p className="error-message" role="alert">{error}</p>}
    {needsLogin && <><p>Sign in with Manor to choose the account for this connection.</p>
      <button type="button" className="btn-login" onClick={signIn} disabled={busy}>Continue with Manor</button></>}
    {!needsLogin && !info && !error && <p role="status">Loading connection request…</p>}
    {info && <div style={{ display: 'grid', gap: 16, minWidth: 0 }}>
      <p><strong>{info.user.name}</strong> · {info.user.email}</p>
      <p>Organization: {info.user.manor_entity_id}</p>
      <ul style={{ display: 'grid', gap: 8, textAlign: 'left', paddingLeft: 20, lineHeight: 1.7 }}>
        {info.scope.split(' ').includes('minutes:read') && <li>Search and read meetings, transcripts, summaries, action items, and statistics.</li>}
        {info.scope.split(' ').includes('minutes:write') && <li>Ask AI questions about meetings using your organization’s configured credits.</li>}
      </ul>
      <p>You can disconnect this access from Manor Integrations.</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <button type="button" className="btn-login" style={{ marginTop: 0, minHeight: 48, width: '100%', whiteSpace: 'normal' }} disabled={busy} onClick={() => decide('approve')}>Authorize connection</button>
        <button type="button" className="btn-login" style={{ marginTop: 0, minHeight: 48, width: '100%', whiteSpace: 'normal', background: '#475569' }} disabled={busy} onClick={() => decide('deny')}>Cancel</button>
      </div>
    </div>}
  </section></main>;
}
