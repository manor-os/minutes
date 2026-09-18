import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { CalendarIcon, ClockIcon } from './Icons';
import { cleanKeyPoints, cleanSummaryForDisplay } from '../utils/keyPoints';
import './SharedMeeting.css';
import './QuietDetail.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8002';

function SharedMeeting({ shareToken }) {
  const [activeTab, setActiveTab] = useState('summary');
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
      <div className="shared-meeting-page quiet-shared-meeting">
        <div className="shared-loading">
          <div className="shared-spinner"></div>
          <p>Loading shared meeting...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="shared-meeting-page quiet-shared-meeting">
        <div className="shared-error">
          <h2>Meeting Not Found</h2>
          <p>{error}</p>
          <a href="/" className="shared-home-link">Go to Minutes</a>
        </div>
      </div>
    );
  }

  if (!meeting) return null;

  const displaySummary = cleanSummaryForDisplay(meeting.summary);

  const tabs = [
    { id: 'summary', label: 'Summary' },
    ...(meeting.transcript ? [{ id: 'transcript', label: 'Transcript' }] : []),
    ...(meeting.action_items?.length ? [{ id: 'actions', label: 'Actions' }] : []),
  ];
  const selectedTab = tabs.some(tab => tab.id === activeTab) ? activeTab : 'summary';
  const handleTabKeyDown = (event, index) => {
    let nextIndex;
    if (event.key === 'ArrowRight') nextIndex = (index + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') nextIndex = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = tabs.length - 1;
    else return;
    event.preventDefault();
    setActiveTab(tabs[nextIndex].id);
    event.currentTarget.parentElement.children[nextIndex].focus();
  };

  return (
    <div className="shared-meeting-page quiet-shared-meeting">
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

        <div className="quiet-detail-tabs" role="tablist" aria-label="Shared meeting content">
          {tabs.map((tab, index) => (
            <button
              key={tab.id}
              id={`shared-tab-${tab.id}`}
              role="tab"
              aria-selected={selectedTab === tab.id}
              aria-controls={`shared-panel-${tab.id}`}
              tabIndex={selectedTab === tab.id ? 0 : -1}
              onClick={() => setActiveTab(tab.id)}
              onKeyDown={(event) => handleTabKeyDown(event, index)}
            >{tab.label}</button>
          ))}
        </div>

        <div id="shared-panel-summary" role="tabpanel" aria-labelledby="shared-tab-summary" hidden={selectedTab !== 'summary'} tabIndex={0}>
        {!meeting.summary && <p className="quiet-detail-empty">No summary is available yet.</p>}
        {meeting.summary && (
          <section className="shared-section">
            <div className="shared-summary">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {displaySummary}
              </ReactMarkdown>
            </div>
          </section>
        )}

        {cleanKeyPoints(meeting.key_points).length > 0 && (
          <details className="shared-section quiet-key-points">
            <summary>Key points <span>{cleanKeyPoints(meeting.key_points).length}</span></summary>
            <ul className="shared-key-points">
              {cleanKeyPoints(meeting.key_points).map((point, index) => (
                <li key={index}>{point}</li>
              ))}
            </ul>
          </details>
        )}
        </div>

        <div id="shared-panel-actions" role="tabpanel" aria-labelledby="shared-tab-actions" hidden={selectedTab !== 'actions'} tabIndex={0}>
        {meeting.action_items && meeting.action_items.length > 0 && (
          <section className="shared-section">
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

        </div>
        <div id="shared-panel-transcript" role="tabpanel" aria-labelledby="shared-tab-transcript" hidden={selectedTab !== 'transcript'} tabIndex={0}>
        {meeting.transcript && (
          <section className="shared-section">
            <div className="shared-transcript">
              {meeting.transcript}
            </div>
          </section>
        )}

        </div>

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
