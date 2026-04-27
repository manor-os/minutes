import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { CalendarIcon, ClockIcon, CheckCircleIcon, StarIcon } from './Icons';
import './SharedMeeting.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8002';

function SharedMeeting({ shareToken }) {
  const [meeting, setMeeting] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchMeeting = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/meetings/shared/${shareToken}`);
        if (!response.ok) {
          if (response.status === 404) {
            setError('This shared meeting was not found or the link has been revoked.');
          } else {
            setError('Failed to load shared meeting.');
          }
          return;
        }
        const data = await response.json();
        if (data.success) {
          setMeeting(data.meeting);
        } else {
          setError('Failed to load shared meeting.');
        }
      } catch (err) {
        console.error('Error fetching shared meeting:', err);
        setError('Failed to load shared meeting. Please check your connection.');
      } finally {
        setLoading(false);
      }
    };

    fetchMeeting();
  }, [shareToken]);

  const formatDuration = (seconds) => {
    if (!seconds) return null;
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return null;
    try {
      return new Date(dateStr).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  if (loading) {
    return (
      <div className="shared-meeting-page">
        <div className="shared-loading">
          <div className="shared-spinner"></div>
          <p>Loading shared meeting...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="shared-meeting-page">
        <div className="shared-error">
          <h2>Meeting Not Found</h2>
          <p>{error}</p>
          <a href="/" className="shared-home-link">Go to Minutes</a>
        </div>
      </div>
    );
  }

  if (!meeting) return null;

  return (
    <div className="shared-meeting-page">
      <div className="shared-meeting-container">
        <header className="shared-header">
          <h1>{meeting.title || 'Untitled Meeting'}</h1>
          <div className="shared-meta">
            {meeting.created_at && (
              <span className="shared-meta-item">
                <CalendarIcon size={14} />
                {formatDate(meeting.created_at)}
              </span>
            )}
            {meeting.duration > 0 && (
              <span className="shared-meta-item">
                <ClockIcon size={14} />
                {formatDuration(meeting.duration)}
              </span>
            )}
          </div>
        </header>

        {meeting.summary && (
          <section className="shared-section">
            <h2>Summary</h2>
            <div className="shared-summary">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {meeting.summary}
              </ReactMarkdown>
            </div>
          </section>
        )}

        {meeting.key_points && meeting.key_points.length > 0 && (
          <section className="shared-section">
            <h2><StarIcon size={16} /> Key Points</h2>
            <ul className="shared-key-points">
              {meeting.key_points.map((point, index) => (
                <li key={index}>
                  {typeof point === 'string' ? point : (point.text || point.description || JSON.stringify(point))}
                </li>
              ))}
            </ul>
          </section>
        )}

        {meeting.action_items && meeting.action_items.length > 0 && (
          <section className="shared-section">
            <h2><CheckCircleIcon size={16} /> Action Items</h2>
            <ul className="shared-action-items">
              {meeting.action_items.map((item, index) => {
                const raw = typeof item === 'string' ? { task: item } : item;
                const task = raw.task || raw.description || raw.text || (typeof raw === 'string' ? raw : JSON.stringify(raw));
                const assignee = typeof raw.assignee === 'object' ? JSON.stringify(raw.assignee) : (raw.assignee || null);
                const dueDate = typeof raw.due_date === 'object' ? JSON.stringify(raw.due_date) : (raw.due_date || raw.deadline || null);
                return (
                  <li key={index} className="shared-action-item">
                    <div className="shared-action-task">{task}</div>
                    {(assignee || dueDate) && (
                      <div className="shared-action-meta">
                        {assignee && <span>Assignee: {assignee}</span>}
                        {dueDate && <span>Due: {dueDate}</span>}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {meeting.transcript && (
          <section className="shared-section">
            <h2>Transcript</h2>
            <div className="shared-transcript">
              {meeting.transcript}
            </div>
          </section>
        )}

        <footer className="shared-footer">
          <p>
            Powered by <a href="/" className="shared-brand-link">Minutes</a>
          </p>
        </footer>
      </div>
    </div>
  );
}

export default SharedMeeting;
