import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { BarChartIcon, ClockIcon, DollarIcon, CalendarIcon, CloseIcon } from './Icons';
import './UsageStats.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8002';

function formatTokens(n) {
  if (!n) return '0';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return n.toString();
}

function UsageStats({ onClose }) {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const token = localStorage.getItem('auth_token');
    fetch(`${API_BASE_URL}/api/meetings/usage-stats`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(r => {
        if (!r.ok) throw new Error('Failed to load');
        return r.json();
      })
      .then(data => { setStats(data); setLoading(false); })
      .catch(() => { setError('Failed to load usage statistics'); setLoading(false); });
  }, []);

  const maxMeetings = stats?.daily
    ? Math.max(...stats.daily.map(d => d.meetings), 1)
    : 1;

  const modalContent = (
    <div className="usage-modal" onClick={onClose}>
      <div className="usage-content" onClick={(e) => e.stopPropagation()}>
        <div className="usage-header">
          <h2>Usage Statistics</h2>
          <button className="usage-close-btn" onClick={onClose} aria-label="Close">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path
                d="M15 5L5 15M5 5L15 15"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        </div>

        <div className="usage-body">
          {loading && (
            <div className="usage-loading">Loading statistics...</div>
          )}

          {error && !loading && (
            <div className="usage-error">{error}</div>
          )}

          {stats && !loading && (
            <>
              <div className="usage-grid">
                <div className="usage-card">
                  <span className="usage-card-icon"><BarChartIcon size={20} /></span>
                  <span className="usage-card-value">{stats.total_meetings}</span>
                  <span className="usage-card-label">Total Meetings</span>
                  <span className="usage-card-sub">{stats.meetings_this_month} this month</span>
                </div>
                <div className="usage-card">
                  <span className="usage-card-icon"><ClockIcon size={20} /></span>
                  <span className="usage-card-value">{stats.total_minutes}</span>
                  <span className="usage-card-label">Minutes Transcribed</span>
                </div>
                <div className="usage-card">
                  <span className="usage-card-icon"><DollarIcon size={20} /></span>
                  <span className="usage-card-value">{formatTokens(stats.total_tokens)}</span>
                  <span className="usage-card-label">Tokens Used</span>
                </div>
                <div className="usage-card">
                  <span className="usage-card-icon"><DollarIcon size={20} /></span>
                  <span className="usage-card-value">${stats.total_cost.toFixed(4)}</span>
                  <span className="usage-card-label">Estimated Cost</span>
                </div>
              </div>

              <div className="usage-section">
                <h3 className="usage-section-title"><CalendarIcon size={16} /> Daily Activity (Last 7 Days)</h3>
                <div className="usage-daily">
                  {stats.daily.map((day) => (
                    <div className="usage-day-row" key={day.date}>
                      <span className="usage-day-label">
                        {new Date(day.date + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}
                      </span>
                      <div className="usage-bar-container">
                        <div
                          className="usage-bar"
                          style={{ width: `${(day.meetings / maxMeetings) * 100}%` }}
                        />
                      </div>
                      <span className="usage-day-count">{day.meetings}</span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
}

export default UsageStats;
