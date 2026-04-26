import React, { useState, useEffect } from 'react';
import { format } from 'date-fns';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import MeetingDetail from './MeetingDetail';
import { CalendarIcon, ClockIcon, UserIcon, MonitorIcon, DollarIcon, StarIcon, CheckCircleIcon, FileTextIcon, AlertCircleIcon, RefreshIcon, LoaderIcon, UploadIcon, CloseIcon, MicIcon, SettingsIcon, SearchIcon } from './Icons';
import './MeetingList.css';

function MeetingList({ recordings, onRefresh, onNotification, currentUser, searchQuery, sortBy, statusFilter, onSearchChange, onSortChange, onStatusChange, page, totalPages, onPageChange }) {
  const [selectedMeeting, setSelectedMeeting] = useState(null);
  const [recordingsList, setRecordingsList] = useState(recordings);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastRefreshTime, setLastRefreshTime] = useState(null);
  const [processingMeetings, setProcessingMeetings] = useState([]);
  const [retryingMeetings, setRetryingMeetings] = useState(new Set()); // Track meetings being retried
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);

  // Update local state when recordings prop changes
  useEffect(() => {
    setRecordingsList(recordings);
    // Track which meetings are processing
    const processing = recordings.filter(r => r.status === 'processing' || r.status === 'uploading').map(r => r.id);
    setProcessingMeetings(processing);
    
    // Remove from retrying set if meeting is now processing or completed
    setRetryingMeetings(prev => {
      const updated = new Set(prev);
      recordings.forEach(r => {
        if (r.status === 'uploading' || r.status === 'processing' || r.status === 'completed') {
          updated.delete(r.id);
        }
      });
      return updated;
    });
  }, [recordings]);

  // Auto-refresh processing meetings more frequently
  useEffect(() => {
    if (processingMeetings.length === 0) return;
    
    const interval = setInterval(() => {
      handleRefresh(true); // Silent refresh
    }, 3000); // Check every 3 seconds for processing meetings
    
    return () => clearInterval(interval);
  }, [processingMeetings.length]);

  // Debounced cross-meeting search
  useEffect(() => {
    if (!searchQuery || searchQuery.length < 3) {
      setSearchResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      setIsSearching(true);
      try {
        const token = localStorage.getItem('auth_token');
        const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8002';
        const response = await fetch(`${API_BASE_URL}/api/meetings/search?q=${encodeURIComponent(searchQuery)}&limit=5`, {
          headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        });
        const data = await response.json();
        if (data.success) setSearchResults(data.results);
      } catch { }
      setIsSearching(false);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const handleRefresh = async (silent = false) => {
    if (!silent) {
      setIsRefreshing(true);
    }
    try {
      await onRefresh();
      setLastRefreshTime(new Date());
    } catch (error) {
      console.error('Error refreshing:', error);
    } finally {
      if (!silent) {
        setIsRefreshing(false);
      }
    }
  };

  const handleRetryProcessing = async (meetingId) => {
    // Add to retrying set to show loading state
    setRetryingMeetings(prev => new Set(prev).add(meetingId));
    
    try {
      const token = localStorage.getItem('auth_token');
      const headers = {
        'Content-Type': 'application/json',
      };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      
      const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8002';
      const response = await fetch(`${API_BASE_URL}/api/meetings/${meetingId}/retry`, {
        method: 'POST',
        headers: headers,
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        let errorMessage = `Retry failed: ${response.status} ${response.statusText}`;
        try {
          const errorJson = JSON.parse(errorText);
          errorMessage = errorJson.detail || errorMessage;
        } catch {
          errorMessage = `${errorMessage} - ${errorText}`;
        }
        throw new Error(errorMessage);
      }
      
      const result = await response.json();
      if (result.success) {
        // Refresh to get updated status
        await handleRefresh(true);
        // Keep retrying state until status changes to processing
        // (will be cleared by useEffect when status updates)
      } else {
        throw new Error(result.message || 'Retry failed');
      }
    } catch (error) {
      console.error('Error retrying processing:', error);
      // Remove from retrying set on error
      setRetryingMeetings(prev => {
        const updated = new Set(prev);
        updated.delete(meetingId);
        return updated;
      });
      if (onNotification) {
        onNotification({ message: `Failed to retry: ${error.message}`, type: 'error' });
      }
    }
  };

  const formatDuration = (seconds) => {
    if (!seconds || seconds === 0) return '0s';
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hours > 0) {
      return `${hours}h ${mins}m`;
    } else if (mins > 0) {
      return `${mins}m ${secs > 0 ? `${secs}s` : ''}`.trim();
    } else {
      return `${secs}s`;
    }
  };

  const getStatusBadge = (status) => {
    const statusMap = {
      uploading: {
        text: 'Uploading',
        class: 'status-uploading',
        icon: <UploadIcon size={14} />,
        description: 'Uploading recording to server...'
      },
      processing: { 
        text: 'Processing', 
        class: 'status-processing',
        icon: <LoaderIcon size={14} />,
        description: 'Transcribing and generating summary...'
      },
      completed: { 
        text: 'Completed', 
        class: 'status-completed',
        icon: <CheckCircleIcon size={12} />,
        description: 'Ready to view'
      },
      failed: { 
        text: 'Failed', 
        class: 'status-failed',
        icon: <CloseIcon size={14} />,
        description: 'Processing failed'
      }
    };
    const statusInfo = statusMap[status] || { 
      text: status, 
      class: 'status-default',
      icon: '•',
      description: status
    };
    return (
      <div className={`status-badge-container ${statusInfo.class}`}>
        <span className={`status-badge ${statusInfo.class}`}>
          <span className="status-icon">{statusInfo.icon}</span>
          <span className="status-text">{statusInfo.text}</span>
        </span>
        <span className="status-description">{statusInfo.description}</span>
      </div>
    );
  };
  
  const formatPlatform = (platform) => {
    const platformMap = {
      'google_meet': 'Google Meet',
      'zoom': 'Zoom',
      'teams': 'Microsoft Teams',
      'browser_extension': 'Browser Extension',
      'phone_recorder': 'Minutes Recorder'
    };
    return platformMap[platform] || platform || 'Unknown';
  };

  const handleToggleFavorite = async (meetingId) => {
    try {
      const token = localStorage.getItem('auth_token');
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8002';
      const response = await fetch(`${API_BASE_URL}/api/meetings/${meetingId}/favorite`, {
        method: 'PATCH',
        headers,
      });
      if (!response.ok) throw new Error('Failed to toggle favorite');
      const result = await response.json();
      setRecordingsList(prev => prev.map(r =>
        r.id === meetingId ? { ...r, is_favorite: result.is_favorite } : r
      ));
    } catch (error) {
      console.error('Error toggling favorite:', error);
      if (onNotification) onNotification({ message: `Failed to toggle favorite: ${error.message}`, type: 'error' });
    }
  };

  const handleBulkDelete = async () => {
    if (selectedIds.size === 0) return;
    if (!window.confirm(`Delete ${selectedIds.size} meeting(s)? This cannot be undone.`)) return;
    try {
      const token = localStorage.getItem('auth_token');
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8002';
      const response = await fetch(`${API_BASE_URL}/api/meetings/bulk-delete`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ meeting_ids: Array.from(selectedIds) }),
      });
      if (!response.ok) throw new Error('Failed to bulk delete');
      const result = await response.json();
      setRecordingsList(prev => prev.filter(r => !selectedIds.has(r.id)));
      setSelectedIds(new Set());
      setSelectMode(false);
      if (onNotification) onNotification({ message: `Deleted ${result.deleted_count} meeting(s)`, type: 'success' });
      onRefresh();
    } catch (error) {
      console.error('Error bulk deleting:', error);
      if (onNotification) onNotification({ message: `Failed to delete: ${error.message}`, type: 'error' });
    }
  };

  const toggleSelectId = (id) => {
    setSelectedIds(prev => {
      const updated = new Set(prev);
      if (updated.has(id)) updated.delete(id);
      else updated.add(id);
      return updated;
    });
  };

  const handleRename = async (meetingId) => {
    if (!renameValue.trim()) {
      setRenamingId(null);
      return;
    }
    try {
      const token = localStorage.getItem('auth_token');
      const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8002';
      const response = await fetch(`${API_BASE_URL}/api/meetings/${meetingId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ title: renameValue.trim() }),
      });
      if (response.ok) {
        setRecordingsList(prev => prev.map(m => m.id === meetingId ? { ...m, title: renameValue.trim() } : m));
      }
    } catch (e) {
      console.error('Rename failed:', e);
    }
    setRenamingId(null);
  };

  return (
    <>
      <div className="meeting-list">
        <div className="list-header">
          <div className="list-header-row">
            <div className="header-left">
              <h2>My Meetings</h2>
              {processingMeetings.length > 0 && (
                <span className="processing-indicator">
                  <LoaderIcon size={14} /> {processingMeetings.length} meeting{processingMeetings.length > 1 ? 's' : ''} processing...
                </span>
              )}
              {lastRefreshTime && (
                <span className="last-refresh-time">
                  Last checked: {format(lastRefreshTime, 'HH:mm:ss')}
                </span>
              )}
            </div>
            <div className="header-actions">
              {selectMode && selectedIds.size > 0 && (
                <button className="btn-bulk-delete" onClick={handleBulkDelete}>
                  Delete Selected ({selectedIds.size})
                </button>
              )}
              <button
                className={`btn-select-mode ${selectMode ? 'active' : ''}`}
                onClick={() => { setSelectMode(!selectMode); setSelectedIds(new Set()); }}
              >
                {selectMode ? 'Cancel' : 'Select'}
              </button>
              <button
                className={`btn-refresh ${isRefreshing ? 'refreshing' : ''}`}
                onClick={() => handleRefresh(false)}
                disabled={isRefreshing}
              >
                {isRefreshing ? <><RefreshIcon size={14} /> Checking...</> : <><RefreshIcon size={14} /> Check Status</>}
              </button>
              {processingMeetings.length > 0 && (
                <button
                  className="btn-auto-refresh"
                  onClick={() => {
                    // Auto-refresh indicator
                  }}
                  title="Auto-refreshing every 3 seconds for processing meetings"
                >
                  ⚡ Auto
                </button>
              )}
            </div>
          </div>
          {/* Search and filters */}
          <div className="list-filters">
            <div className="search-box">
              <SearchIcon size={16} />
              <input
                type="text"
                placeholder="Search meetings..."
                value={searchQuery}
                onChange={(e) => onSearchChange(e.target.value)}
                className="search-input"
              />
              {searchQuery && (
                <button className="search-clear" onClick={() => onSearchChange('')}>
                  <CloseIcon size={14} />
                </button>
              )}
            </div>
            {searchResults.length > 0 && (
              <div className="search-results-dropdown">
                {searchResults.map(result => (
                  <div
                    key={result.id}
                    className="search-result-item"
                    onClick={() => {
                      const meeting = recordingsList.find(m => m.id === result.id);
                      if (meeting) setSelectedMeeting(meeting);
                      setSearchResults([]);
                    }}
                  >
                    <div className="search-result-title">{result.title || 'Untitled'}</div>
                    <div className="search-result-meta">
                      {result.match_in.map(m => (
                        <span key={m} className="search-result-badge">{m}</span>
                      ))}
                    </div>
                    {result.snippet && (
                      <div className="search-result-snippet">{result.snippet}</div>
                    )}
                  </div>
                ))}
              </div>
            )}
            <select
              className="filter-select"
              value={sortBy}
              onChange={(e) => onSortChange(e.target.value)}
            >
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="longest">Longest</option>
              <option value="shortest">Shortest</option>
            </select>
            <select
              className="filter-select"
              value={statusFilter}
              onChange={(e) => onStatusChange(e.target.value)}
            >
              <option value="">All status</option>
              <option value="completed">Completed</option>
              <option value="processing">Processing</option>
              <option value="failed">Failed</option>
              <option value="favorites">Favorites</option>
            </select>
          </div>
        </div>

      {recordingsList.length === 0 ? (
        <div className="empty-state">
          <p>No recordings yet</p>
          <p className="empty-subtitle">Start recording to see your meetings here</p>
        </div>
      ) : (
        <div className="recordings-grid">
          {recordingsList.map((recording) => (
            <div
              key={recording.id}
              className={`recording-card recording-card-${recording.status}`}
              data-meeting-id={recording.id}
              onClick={() => !selectMode && recording.status === 'completed' && setSelectedMeeting(recording)}
            >
              {/* Title + Status */}
              <div className="card-header">
                {selectMode && (
                  <label className="card-select-checkbox" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selectedIds.has(recording.id)}
                      onChange={() => toggleSelectId(recording.id)}
                    />
                  </label>
                )}
                {renamingId === recording.id ? (
                  <input
                    className="card-title-edit"
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onBlur={() => handleRename(recording.id)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleRename(recording.id); if (e.key === 'Escape') setRenamingId(null); }}
                    autoFocus
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <h3
                    className="card-title"
                    onDoubleClick={(e) => {
                      if (recording.status !== 'completed') return;
                      e.stopPropagation();
                      setRenamingId(recording.id);
                      setRenameValue(recording.title || 'Untitled Meeting');
                    }}
                    title={recording.status === 'completed' ? 'Double-click to rename' : undefined}
                  >
                    {recording.title || 'Untitled Meeting'}
                  </h3>
                )}
                <div className="card-status-badge" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  {recording.status === 'completed' && (
                    <button
                      className={`btn-favorite ${recording.is_favorite ? 'active' : ''}`}
                      onClick={(e) => { e.stopPropagation(); handleToggleFavorite(recording.id); }}
                    >
                      <StarIcon size={16} />
                    </button>
                  )}
                  {getStatusBadge(recording.status)}
                </div>
              </div>

              {/* Property grid */}
              <div className="card-props">
                <div className="card-prop">
                  <CalendarIcon size={14} />
                  <span>{format(new Date(recording.created_at), 'MMM dd, yyyy · HH:mm')}</span>
                </div>
                {recording.duration > 0 && (
                  <div className="card-prop">
                    <ClockIcon size={14} />
                    <span>{formatDuration(recording.duration)}</span>
                  </div>
                )}
                {recording.platform && (
                  <div className="card-prop">
                    <MonitorIcon size={14} />
                    <span>{formatPlatform(recording.platform)}</span>
                  </div>
                )}
                {(recording.created_by_user_name || currentUser) && (
                  <div className="card-prop">
                    <UserIcon size={14} />
                    <span>{recording.created_by_user_name || currentUser?.name || currentUser?.email?.split('@')[0] || 'User'}</span>
                  </div>
                )}
                {recording.token_cost && recording.token_cost.total_cost > 0 && (
                  <div className="card-prop card-prop-cost">
                    <DollarIcon size={14} />
                    <span>${recording.token_cost.total_cost.toFixed(4)}</span>
                  </div>
                )}
              </div>
              
              {/* Status Check Indicator for Processing/Uploading */}
              {(recording.status === 'processing' || recording.status === 'uploading') && (
                <div className="status-check-indicator">
                  <span className="check-dot"></span>
                  <span className="check-text">
                    {recording.status === 'uploading' ? 'Uploading...' : 'Checking status...'}
                  </span>
                </div>
              )}

              {/* Processing Status - Enhanced UI */}
              {recording.status === 'processing' && (
                <div className="card-processing">
                  <div className="processing-steps">
                    <div className="processing-step active">
                      <span className="step-icon"><MicIcon size={14} /></span>
                      <span className="step-text">Transcribing audio...</span>
                    </div>
                    <div className="processing-step">
                      <span className="step-icon"><SettingsIcon size={14} /></span>
                      <span className="step-text">Generating summary...</span>
                    </div>
                    <div className="processing-step">
                      <span className="step-icon"><StarIcon size={14} /></span>
                      <span className="step-text">Extracting key points...</span>
                    </div>
                  </div>
                  <div className="processing-progress">
                    <div className="progress-bar">
                      <div className="progress-fill"></div>
                    </div>
                    <p className="progress-text">This usually takes 30-60 seconds</p>
                  </div>
                  <button
                    className="btn-retry btn-retry-sm"
                    onClick={() => handleRetryProcessing(recording.id)}
                    disabled={retryingMeetings.has(recording.id)}
                    title="Restart processing if stuck"
                  >
                    {retryingMeetings.has(recording.id) ? <><LoaderIcon size={14} /> Retrying...</> : <><RefreshIcon size={14} /> Retry</>}
                  </button>
                </div>
              )}

              {/* Failed Status - Enhanced UI */}
              {recording.status === 'failed' && (
                <div className="card-error">
                  <div className="error-header">
                    <span className="error-icon"><AlertCircleIcon size={16} /></span>
                    <strong>Processing Failed</strong>
                  </div>
                  {recording.metadata?.processing_error ? (
                    <div className="error-detail">
                      <p className="error-message" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                        {recording.metadata.processing_error}
                      </p>
                      {recording.metadata.processing_error.toLowerCase().includes('empty result') && (
                        <p className="error-hint">The audio may not contain recognizable speech. Try recording with your microphone closer, or check that your mic is not muted.</p>
                      )}
                      {recording.metadata.processing_error.toLowerCase().includes('api') && (
                        <p className="error-hint">Check your API key in Settings. Make sure it's valid and has credits.</p>
                      )}
                      {recording.metadata.processing_error.toLowerCase().includes('timeout') && (
                        <p className="error-hint">Processing took too long. Try a shorter recording or check your internet connection.</p>
                      )}
                    </div>
                  ) : (
                    <>
                      <p className="error-message">This may be due to:</p>
                      <ul className="error-list">
                        <li>Audio has no recognizable speech</li>
                        <li>Invalid or missing API key</li>
                        <li>Audio file too short or corrupted</li>
                        <li>Network connectivity issues</li>
                      </ul>
                    </>
                  )}
                  <button 
                    className="btn-retry"
                    onClick={() => handleRetryProcessing(recording.id)}
                    disabled={retryingMeetings.has(recording.id)}
                  >
                    {retryingMeetings.has(recording.id) ? (
                      <>
                        <span className="retry-spinner"><LoaderIcon size={14} /></span> Retrying...
                      </>
                    ) : (
                      <>
                        <RefreshIcon size={14} /> Retry Processing
                      </>
                    )}
                  </button>
                </div>
              )}

              {/* Completed Status - Show Summary and Transcript */}
              {recording.status === 'completed' && (
                <div className="card-completed-content">
                  {/* Summary preview */}
                  {recording.summary && (
                    <div className="card-summary-preview">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {recording.summary.length > 150
                          ? `${recording.summary.substring(0, 150)}...`
                          : recording.summary}
                      </ReactMarkdown>
                    </div>
                  )}

                  {/* Quick stats row */}
                  <div className="card-stats-row">
                    {recording.key_points && recording.key_points.length > 0 && (
                      <span className="card-stat card-stat-teal">
                        <StarIcon size={12} />
                        <span>{recording.key_points.length} key points</span>
                      </span>
                    )}
                    {recording.action_items && recording.action_items.length > 0 && (
                      <span className="card-stat card-stat-blue">
                        <CheckCircleIcon size={12} />
                        <span>{recording.action_items.length} actions</span>
                      </span>
                    )}
                    {recording.transcript && (
                      <span className="card-stat">
                        <FileTextIcon size={12} />
                        <span>{Math.round(recording.transcript.split(/\s+/).length)} words</span>
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Placeholder for non-completed meetings */}
              {recording.status !== 'completed' && recording.status !== 'processing' && recording.status !== 'failed' && (
                <div className="card-placeholder">
                  <p className="placeholder-text">Processing will start shortly...</p>
                </div>
              )}

              <div className="card-actions">
                <button 
                  className="btn-view"
                  onClick={() => setSelectedMeeting(recording)}
                >
                  View Details
                </button>
                {recording.audio_file && (
                  <button className="btn-download" onClick={(e) => {
                    e.stopPropagation();
                    const token = localStorage.getItem('auth_token');
                    const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8002';
                    fetch(`${API_BASE_URL}/api/meetings/audio/${recording.audio_file}`, {
                      headers: token ? { 'Authorization': `Bearer ${token}` } : {},
                    }).then(r => r.blob()).then(blob => {
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `${recording.title || 'recording'}.webm`;
                      a.click();
                      URL.revokeObjectURL(url);
                    }).catch(() => {
                      if (onNotification) onNotification({ message: 'Failed to download audio', type: 'error' });
                    });
                  }}>Download Audio</button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {totalPages > 1 && (
        <div className="pagination">
          <button
            className="pagination-btn"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
          >
            Previous
          </button>
          <span className="pagination-info">Page {page} of {totalPages}</span>
          <button
            className="pagination-btn"
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
          >
            Next
          </button>
        </div>
      )}
      </div>

      {selectedMeeting && (
        <MeetingDetail
          meeting={selectedMeeting}
          onClose={() => setSelectedMeeting(null)}
          onUpdate={(updatedMeeting) => {
            // Update the meeting in the list
            setRecordingsList(recordingsList.map(m => 
              m.id === updatedMeeting.id ? updatedMeeting : m
            ));
            setSelectedMeeting(updatedMeeting);
            onRefresh();
          }}
          onDelete={(deletedId) => {
            // Remove the meeting from the list
            setRecordingsList(recordingsList.filter(m => m.id !== deletedId));
            setSelectedMeeting(null);
            onRefresh();
          }}
          onNotification={onNotification}
        />
      )}
    </>
  );
}

export default MeetingList;

