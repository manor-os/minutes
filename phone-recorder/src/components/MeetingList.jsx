import React, { useState, useEffect, useRef } from 'react';
import { format } from 'date-fns';
import MeetingDetail from './MeetingDetail';
import { StarIcon, RefreshIcon, LoaderIcon, UploadIcon, CloseIcon, MicIcon, SearchIcon, DownloadIcon, EditIcon, AlertCircleIcon, SettingsIcon } from './Icons';
import './MeetingList.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8002';
const authHeaders = () => {
  const token = localStorage.getItem('auth_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

// Preview the content, without importing the document's heading hierarchy into the list.
const summaryPreview = (summary) => String(summary || '')
  .replace(/```[\s\S]*?```/g, '')
  .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
  .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
  .split('\n')
  .map(line => line.replace(/^\s*(?:#{1,6}\s*|[-*>]\s*|\d+\.\s*)/, '').replace(/[*_`]/g, '').trim())
  .filter(line => line && !/^(meeting summary|summary|participants|main topics discussed|key points|action items):?$/i.test(line))
  .join(' ').replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();

const formatDuration = (seconds) => {
  if (!seconds) return '0s';
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  return hours ? `${hours}h ${mins}m` : mins ? `${mins}m${secs ? ` ${secs}s` : ''}` : `${secs}s`;
};

function MeetingList({ recordings, onRefresh, onNotification, searchQuery = '', sortBy, statusFilter, onSearchChange, onSortChange, onStatusChange, page, totalPages, onPageChange, onNewRecording }) {
  const [selectedMeeting, setSelectedMeeting] = useState(null);
  const [recordingsList, setRecordingsList] = useState(recordings);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [retryingMeetings, setRetryingMeetings] = useState(new Set());
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const [isRenaming, setIsRenaming] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [openMenuId, setOpenMenuId] = useState(null);
  const [searchResults, setSearchResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);
  const menuTrigger = useRef(null);
  const viewOptions = useRef(null);
  const refreshRef = useRef(onRefresh);
  refreshRef.current = onRefresh;
  const processingCount = recordingsList.filter(r => ['processing', 'uploading'].includes(r.status)).length;

  useEffect(() => {
    setRecordingsList(recordings);
    setSelectedIds(prev => new Set([...prev].filter(id => recordings.some(r => r.id === id))));
    setRetryingMeetings(prev => new Set([...prev].filter(id => !recordings.some(r => r.id === id && ['uploading', 'processing', 'completed'].includes(r.status)))));
  }, [recordings]);

  useEffect(() => {
    if (!processingCount) return;
    const interval = setInterval(() => {
      Promise.resolve(refreshRef.current()).catch(() => {});
    }, 3000);
    return () => clearInterval(interval);
  }, [processingCount]);

  useEffect(() => {
    const dismissOptions = e => {
      const panel = viewOptions.current;
      if (!panel?.open) return;
      if (e.type === 'keydown' && e.key === 'Escape') { panel.open = false; panel.querySelector('summary')?.focus(); }
      else if (e.type === 'pointerdown' && !panel.contains(e.target)) panel.open = false;
    };
    document.addEventListener('pointerdown', dismissOptions);
    document.addEventListener('keydown', dismissOptions);
    return () => { document.removeEventListener('pointerdown', dismissOptions); document.removeEventListener('keydown', dismissOptions); };
  }, []);

  useEffect(() => {
    if (openMenuId === null) return;
    const closeOutside = e => { if (!e.target.closest('.meeting-menu')) setOpenMenuId(null); };
    const closeOnEscape = e => {
      if (e.key === 'Escape') { setOpenMenuId(null); menuTrigger.current?.focus(); }
    };
    document.addEventListener('pointerdown', closeOutside);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOutside);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [openMenuId]);

  useEffect(() => {
    setSearchResults([]);
    setIsSearching(false);
    if (searchQuery.trim().length < 3) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setIsSearching(true);
      try {
        const response = await fetch(`${API_BASE_URL}/api/meetings/search?q=${encodeURIComponent(searchQuery)}&limit=5`, { headers: authHeaders(), signal: controller.signal });
        const data = await response.json();
        if (!controller.signal.aborted && response.ok && data.success) setSearchResults(data.results);
      } catch { /* The regular title search still works when full-text search is unavailable. */ }
      finally { if (!controller.signal.aborted) setIsSearching(false); }
    }, 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [searchQuery]);

  const notifyError = message => onNotification?.({ message, type: 'error' });
  const handleRefresh = async () => {
    setIsRefreshing(true);
    try { await onRefresh(); }
    catch { notifyError('Could not refresh meetings. Please try again.'); }
    finally { setIsRefreshing(false); }
  };

  const handleRetryProcessing = async id => {
    setRetryingMeetings(prev => new Set(prev).add(id));
    setOpenMenuId(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/meetings/${id}/retry`, { method: 'POST', headers: authHeaders() });
      const result = await response.json();
      if (!response.ok || !result.success) throw new Error(result.detail || result.message || 'Please try again.');
      await onRefresh();
    } catch (error) { notifyError(`Could not retry this recording: ${error.message}`); }
    finally { setRetryingMeetings(prev => { const next = new Set(prev); next.delete(id); return next; }); }
  };

  const handleToggleFavorite = async id => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/meetings/${id}/favorite`, { method: 'PATCH', headers: authHeaders() });
      if (!response.ok) throw new Error();
      const result = await response.json();
      setRecordingsList(prev => prev.filter(r => !(statusFilter === 'favorites' && r.id === id && !result.is_favorite)).map(r => r.id === id ? { ...r, is_favorite: result.is_favorite } : r));
    } catch { notifyError('Could not update your favorites. Please try again.'); }
  };

  const handleBulkDelete = async () => {
    if (!selectedIds.size || isDeleting || !window.confirm(`Delete ${selectedIds.size} meeting(s)? This cannot be undone.`)) return;
    setIsDeleting(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/meetings/bulk-delete`, {
        method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ meeting_ids: [...selectedIds] }),
      });
      if (!response.ok) throw new Error();
      const result = await response.json();
      setRecordingsList(prev => prev.filter(r => !selectedIds.has(r.id)));
      setSelectedIds(new Set()); setSelectMode(false);
      onNotification?.({ message: `Deleted ${result.deleted_count} meeting(s)`, type: 'success' });
      await onRefresh();
    } catch { notifyError('Could not delete the selected meetings. Please try again.'); }
    finally { setIsDeleting(false); }
  };

  const handleRename = async id => {
    const title = renameValue.trim();
    if (!title || isRenaming) return;
    setIsRenaming(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/meetings/${id}`, {
        method: 'PATCH', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ title }),
      });
      if (!response.ok) throw new Error();
      setRecordingsList(prev => prev.map(r => r.id === id ? { ...r, title } : r));
      setRenamingId(null);
    } catch { notifyError('Could not rename this meeting. Please try again.'); }
    finally { setIsRenaming(false); }
  };

  const handleDownload = async recording => {
    setOpenMenuId(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/meetings/audio/${recording.audio_file}`, { headers: authHeaders() });
      if (!response.ok) throw new Error();
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `${recording.title || 'recording'}${(recording.audio_file.match(/\.[a-z0-9]+$/i) || ['.webm'])[0]}`;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { notifyError('Could not download the audio. Please try again.'); }
  };

  const openSearchResult = async result => {
    setSearchFocused(false);
    const existing = recordingsList.find(r => r.id === result.id);
    if (existing) { setSelectedMeeting(existing); return; }
    try {
      const response = await fetch(`${API_BASE_URL}/api/meetings/${result.id}`, { headers: authHeaders() });
      const data = await response.json();
      if (!response.ok || !data.meeting) throw new Error();
      setSelectedMeeting(data.meeting);
    } catch { notifyError('Could not open this meeting. Please try again.'); }
  };

  const hasFilters = Boolean(searchQuery || statusFilter);
  return (
    <>
      <section className="meeting-list" aria-labelledby="meetings-heading">
        <div className="meetings-heading-row">
          <div>
            <h2 id="meetings-heading">My meetings</h2>
          </div>
          {onNewRecording && <button className="meetings-new-button" onClick={onNewRecording}><MicIcon size={17} /> New recording</button>}
        </div>

        <div className="meetings-toolbar">
          <div className="meetings-views" aria-label="Meeting views">
            <button className={statusFilter !== 'favorites' ? 'is-active' : ''} aria-pressed={statusFilter !== 'favorites'} onClick={() => onStatusChange('')} aria-label="All meetings">{statusFilter && statusFilter !== 'favorites' ? statusFilter.charAt(0).toUpperCase() + statusFilter.slice(1) : 'All'}</button>
            <button className={statusFilter === 'favorites' ? 'is-active' : ''} aria-pressed={statusFilter === 'favorites'} onClick={() => onStatusChange('favorites')}><StarIcon size={14} /> Favorites</button>
          </div>
          <div className="meetings-tools">
            <div className="meetings-search" onFocus={() => setSearchFocused(true)} onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget)) setSearchFocused(false); }}>
              <SearchIcon size={16} />
              <input type="search" className="search-input" aria-label="Search meetings" placeholder="Search meetings" value={searchQuery} onChange={e => onSearchChange(e.target.value)} onKeyDown={e => { if (e.key === 'Escape') setSearchFocused(false); }} />
              {isSearching ? <LoaderIcon size={14} className="meetings-spin" /> : searchQuery ? <button className="meetings-icon-button" aria-label="Clear search" onClick={() => onSearchChange('')}><CloseIcon size={14} /></button> : null}
              {searchFocused && searchResults.length > 0 && <div className="meetings-search-results" aria-label="Search results">
                <p>In your conversations</p>
                {searchResults.map(result => <button key={result.id} onClick={() => openSearchResult(result)}>
                  <span>{result.title || 'Untitled meeting'}</span>
                  {result.snippet && <small>{result.snippet}</small>}
                </button>)}
              </div>}
            </div>
            <details className="meetings-view-options" ref={viewOptions}>
              <summary aria-label="View options"><SettingsIcon size={15} /><span>View</span></summary>
              <div className="meetings-filter-row">
          <div className="meetings-filter-controls">
            {statusFilter !== 'favorites' && <><select aria-label="Filter by status" value={statusFilter} onChange={e => onStatusChange(e.target.value)}>
              <option value="">All statuses</option><option value="completed">Completed</option><option value="uploading">Uploading</option><option value="processing">Processing</option><option value="failed">Failed</option>
            </select>
            <span className="meetings-control-divider" aria-hidden="true" /></>}
            <select aria-label="Sort meetings" value={sortBy} onChange={e => onSortChange(e.target.value)}>
              <option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="longest">Longest first</option><option value="shortest">Shortest first</option>
            </select>
          </div>
          <div className="meetings-list-actions">
            <button className={`meetings-text-button ${selectMode ? 'is-active' : ''}`} aria-pressed={selectMode} onClick={e => { e.currentTarget.closest('details').open = false; setSelectMode(!selectMode); setSelectedIds(new Set()); setRenamingId(null); setOpenMenuId(null); }}>{selectMode ? 'Cancel selection' : 'Select'}</button>
            <button className="meetings-text-button" onClick={e => { e.currentTarget.closest('details').open = false; handleRefresh(); }} disabled={isRefreshing}><RefreshIcon size={14} /> {isRefreshing ? 'Refreshing…' : 'Refresh'}</button>
          </div>
        </div>
            </details>
          </div>
        </div>



        {selectMode && <div className="meetings-selection-bar">
          <label><input type="checkbox" aria-label="Select all meetings on this page" checked={recordingsList.length > 0 && selectedIds.size === recordingsList.length} onChange={e => setSelectedIds(e.target.checked ? new Set(recordingsList.map(r => r.id)) : new Set())} /> {selectedIds.size} selected</label>
          <button className="meetings-text-button" onClick={() => { setSelectMode(false); setSelectedIds(new Set()); }}>Cancel selection</button>
          <button className="meetings-delete-button" onClick={handleBulkDelete} disabled={!selectedIds.size || isDeleting}>{isDeleting ? 'Deleting…' : 'Delete selected'}</button>
        </div>}

        {recordingsList.length === 0 ? <div className="meetings-empty">
          <div className="meetings-empty-icon">{hasFilters ? <SearchIcon size={24} /> : <MicIcon size={24} />}</div>
          <h3>{hasFilters ? 'No meetings found' : 'Room for your next conversation'}</h3>
          <p>{hasFilters ? 'Try another search or change your filters.' : 'Record a meeting. We’ll take care of the notes.'}</p>
          {hasFilters ? <button className="meetings-text-button" onClick={() => { onSearchChange(''); onStatusChange(''); }}>Clear filters</button> : onNewRecording && <button className="meetings-new-button" onClick={onNewRecording}><MicIcon size={16} /> New recording</button>}
        </div> : <div className="meetings-rows meetings-cards">
          {recordingsList.map(recording => {
            const title = recording.title || 'Untitled meeting';
            const busy = ['processing', 'uploading'].includes(recording.status);
            const failed = recording.status === 'failed';
            const preview = recording.status === 'completed' ? summaryPreview(recording.summary) : '';
            return <article className={`meeting-row meeting-card ${busy ? 'is-processing' : ''} ${failed ? 'is-failed' : ''} ${selectedIds.has(recording.id) ? 'is-selected' : ''}`} key={recording.id} data-meeting-id={recording.id} onClick={e => {
              if (e.target.closest('button, input, select, textarea, a, details, form, label')) return;
              if (selectMode) setSelectedIds(prev => { const next = new Set(prev); next.has(recording.id) ? next.delete(recording.id) : next.add(recording.id); return next; });
              else setSelectedMeeting(recording);
            }}>
              {selectMode ? <input className="meeting-checkbox" type="checkbox" aria-label={`Select ${title}`} checked={selectedIds.has(recording.id)} onChange={() => setSelectedIds(prev => { const next = new Set(prev); next.has(recording.id) ? next.delete(recording.id) : next.add(recording.id); return next; })} />
                : <div className="meeting-row-icon" aria-hidden="true">{failed ? <AlertCircleIcon size={20} /> : busy ? recording.status === 'uploading' ? <UploadIcon size={20} /> : <LoaderIcon size={20} className="meetings-spin" /> : <MicIcon size={20} />}</div>}
              <div className="meeting-row-content">
                {renamingId === recording.id ? <form className="meeting-rename" onSubmit={e => { e.preventDefault(); handleRename(recording.id); }} onKeyDown={e => { if (e.key === 'Escape') setRenamingId(null); }}>
                  <input aria-label="Meeting title" value={renameValue} onChange={e => setRenameValue(e.target.value)} autoFocus disabled={isRenaming} />
                  <button type="submit" disabled={!renameValue.trim() || isRenaming}>{isRenaming ? 'Saving…' : 'Save'}</button>
                  <button type="button" aria-label="Cancel rename" onClick={() => setRenamingId(null)} disabled={isRenaming}><CloseIcon size={15} /></button>
                </form> : <h3><button className="meeting-open" onClick={() => selectMode ? setSelectedIds(prev => { const next = new Set(prev); next.has(recording.id) ? next.delete(recording.id) : next.add(recording.id); return next; }) : setSelectedMeeting(recording)}>{title}</button></h3>}
                {preview && <p className="meeting-preview">{preview}</p>}
                {(busy || failed || !['completed', 'processing', 'uploading', 'failed'].includes(recording.status)) && <div className="meeting-state-line"><span className="meeting-status"><span />{recording.status === 'uploading' ? 'Uploading' : busy ? 'Processing' : failed ? 'Needs attention' : recording.status}</span>
                  {failed && <button className="meeting-retry" onClick={() => handleRetryProcessing(recording.id)} disabled={retryingMeetings.has(recording.id)}>{retryingMeetings.has(recording.id) ? 'Retrying…' : 'Try again'}</button>}
                </div>}
                {failed && recording.metadata?.processing_error && <details className="meeting-error-details"><summary>Error details</summary><p>{recording.metadata.processing_error}</p></details>}
              </div>
              <div className="meeting-row-date"><time dateTime={recording.created_at} title={format(new Date(recording.created_at), 'PPpp')}>{format(new Date(recording.created_at), 'MMM d, yyyy')}</time>{recording.duration > 0 && <span>{formatDuration(recording.duration)}</span>}</div>
              {!selectMode && <div className="meeting-row-actions">
                <button className={`meetings-icon-button meeting-favorite ${recording.is_favorite ? 'is-favorite' : ''}`} aria-label={`${recording.is_favorite ? 'Remove from' : 'Add to'} favorites: ${title}`} aria-pressed={Boolean(recording.is_favorite)} title={recording.is_favorite ? 'Remove from favorites' : 'Add to favorites'} onClick={() => handleToggleFavorite(recording.id)}><StarIcon size={16} /></button>
                <div className="meeting-menu">
                  <button className="meetings-icon-button" aria-label={`More options for ${title}`} aria-expanded={openMenuId === recording.id} aria-controls={`meeting-actions-${recording.id}`} onClick={e => { menuTrigger.current = e.currentTarget; setOpenMenuId(openMenuId === recording.id ? null : recording.id); }}><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="19" cy="12" r="1.6" /></svg></button>
                  {openMenuId === recording.id && <div className="meeting-menu-panel" id={`meeting-actions-${recording.id}`} role="group" aria-label={`Actions for ${title}`}>
                    <button onClick={() => { setRenamingId(recording.id); setRenameValue(title); setOpenMenuId(null); }}><EditIcon size={14} /> Rename</button>
                    {recording.audio_file && <button onClick={() => handleDownload(recording)}><DownloadIcon size={14} /> Download audio</button>}
                    {(failed || busy) && <button onClick={() => handleRetryProcessing(recording.id)} disabled={retryingMeetings.has(recording.id)}><RefreshIcon size={14} /> {retryingMeetings.has(recording.id) ? 'Retrying…' : 'Retry processing'}</button>}
                  </div>}
                </div>
              </div>}
            </article>;
          })}
        </div>}

        {totalPages > 1 && <nav className="meetings-pagination" aria-label="Meeting pages"><button disabled={page <= 1} onClick={() => onPageChange(page - 1)}>Previous</button><span>Page {page} of {totalPages}</span><button disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>Next</button></nav>}
      </section>
      {selectedMeeting && <MeetingDetail meeting={selectedMeeting} onClose={() => setSelectedMeeting(null)} onUpdate={updated => { setRecordingsList(prev => prev.map(r => r.id === updated.id ? updated : r)); setSelectedMeeting(updated); onRefresh(); }} onDelete={id => { setRecordingsList(prev => prev.filter(r => r.id !== id)); setSelectedMeeting(null); onRefresh(); }} onNotification={onNotification} />}
    </>
  );
}

export default MeetingList;
