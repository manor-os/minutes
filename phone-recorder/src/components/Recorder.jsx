import React, { useState, useRef, useEffect } from 'react';
import { format } from 'date-fns';
import { MicIcon, StopIcon, UploadIcon, CloseIcon, FileTextIcon, ClockIcon } from './Icons';
import './Recorder.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8002';
const WS_URL = API_BASE_URL.replace('http', 'ws');
const STT_MODE = import.meta.env.VITE_STT_MODE || 'cloud';
const LLM_MODE = import.meta.env.VITE_LLM_MODE || 'cloud';
const IS_LOCAL = STT_MODE === 'local' && LLM_MODE === 'local';

// Translate getUserMedia / MediaRecorder errors into instructions the user
// can actually act on. Returns { title, body, action } shape for the inline
// panel. Falls through to a generic message for unknown errors.
function describeMicError(err) {
  const name = err?.name || "";
  if (name === "NotAllowedError" || name === "PermissionDeniedError") {
    return {
      title: "Microphone permission denied",
      body:
        "Your browser blocked microphone access. Click the lock or camera icon next to the address bar and allow microphone for this site, then try again.",
    };
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return {
      title: "No microphone found",
      body:
        "We couldn't detect a microphone. Plug one in (or check your system's audio settings) and try again.",
    };
  }
  if (name === "NotReadableError" || name === "TrackStartError") {
    return {
      title: "Microphone is busy",
      body:
        "Another app (Zoom, Voice Memos, a browser tab, etc.) is using your microphone. Close it and try again.",
    };
  }
  if (name === "OverconstrainedError") {
    return {
      title: "Microphone doesn't support the required settings",
      body: "Try a different microphone or restart your browser.",
    };
  }
  if (name === "SecurityError") {
    return {
      title: "Recording blocked by the browser",
      body:
        "Recording requires a secure connection (https://) or localhost. Open this app over HTTPS and try again.",
    };
  }
  return {
    title: "Couldn't start recording",
    body:
      (err?.message && err.message.length < 200)
        ? err.message
        : "Something went wrong starting the microphone. Refresh the page and try again.",
  };
}


function Recorder({ onRecordingComplete, isRecording, setIsRecording, onNotification, hidden, onOpenSettings }) {
  const [recordingTime, setRecordingTime] = useState(0);
  const [meetingTitle, setMeetingTitle] = useState('');
  const [meetingNotes, setMeetingNotes] = useState('');
  const [liveSegments, setLiveSegments] = useState([]);
  const [liveStatus, setLiveStatus] = useState('');
  const [liveOffline, setLiveOffline] = useState(false);
  const [mode, setMode] = useState('record'); // 'record' | 'upload'
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState('general');
  const [apiKeyWarning, setApiKeyWarning] = useState(null); // null | 'stt' | 'both'
  const [micError, setMicError] = useState(null); // { title, body } | null

  // Upload state
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const streamRef = useRef(null);
  const timerRef = useRef(null);
  const wsRef = useRef(null);
  const liveRecorderRef = useRef(null);
  const scrollRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/meetings/templates`)
      .then(r => r.json())
      .then(data => {
        if (data.success) setTemplates(data.templates);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (isRecording) {
      timerRef.current = setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [isRecording]);

  // Cleanup on unmount — stop all media if component is destroyed
  useEffect(() => {
    return () => {
      if (liveRecorderRef.current && liveRecorderRef.current.state === 'recording') {
        try { liveRecorderRef.current.stop(); } catch (_) {}
      }
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        try { wsRef.current.close(); } catch (_) {}
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
        try { mediaRecorderRef.current.stop(); } catch (_) {}
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => { try { t.stop(); } catch (_) {} });
      }
    };
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [liveSegments]);

  const handleStartRecording = () => {
    if (!IS_LOCAL) {
      const hasStt = localStorage.getItem('has_stt_key') === 'true';
      const hasLlm = localStorage.getItem('has_llm_key') === 'true';
      if (!hasStt && !hasLlm) {
        setApiKeyWarning('both');
        return;
      }
      if (!hasStt) {
        setApiKeyWarning('stt');
        return;
      }
    }
    setApiKeyWarning(null);
    startRecording();
  };

  const startRecording = async () => {
    setMicError(null);
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setMicError({
        title: "Recording isn't supported in this browser",
        body:
          "Use a recent version of Chrome, Safari, Firefox, or Edge — and make sure the page is served over HTTPS.",
      });
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, sampleRate: 44100 }
      });
      streamRef.current = stream;

      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
      audioChunksRef.current = [];
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };
      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        const metadata = {
          title: meetingTitle || `Meeting ${format(new Date(), 'yyyy-MM-dd HH:mm')}`,
          notes: meetingNotes,
          duration: recordingTime,
          timestamp: new Date().toISOString(),
          template: selectedTemplate,
        };
        onRecordingComplete(audioBlob, metadata);
        setRecordingTime(0);
        setMeetingTitle('');
        setMeetingNotes('');
        setLiveOffline(false);
      };
      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.start();
      setIsRecording(true);
      setLiveSegments([]);
      setLiveStatus('Connecting…');
      setLiveOffline(false);
      startLiveTranscription(stream);
    } catch (error) {
      console.error('Error starting recording:', error);
      const described = describeMicError(error);
      // Show an inline, persistent panel — toasts disappear and leave the
      // user staring at a recorder that looks ready but isn't.
      setMicError(described);
      if (onNotification) {
        onNotification({ message: described.title, type: "error" });
      }
    }
  };

  const startLiveTranscription = (stream) => {
    try {
      const ws = new WebSocket(`${WS_URL}/ws/transcribe`);
      wsRef.current = ws;

      ws.onopen = () => {
        setLiveStatus('Live transcription active');
        const language = localStorage.getItem('transcript_language') || '';
        const sttKey = localStorage.getItem('stt_api_key') || '';
        ws.send(JSON.stringify({ type: 'config', language: language || undefined, stt_api_key: sttKey || undefined }));

        const startCycle = () => {
          if (!streamRef.current?.active || ws.readyState !== WebSocket.OPEN) return;
          const rec = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
          liveRecorderRef.current = rec;
          const chunks = [];
          rec.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
          rec.onstop = () => {
            if (chunks.length > 0 && ws.readyState === WebSocket.OPEN) {
              const blob = new Blob(chunks, { type: 'audio/webm' });
              blob.arrayBuffer().then(buf => ws.send(buf));
            }
            if (ws.readyState === WebSocket.OPEN && streamRef.current?.active) {
              startCycle();
            }
          };
          rec.start();
          setTimeout(() => { if (rec.state === 'recording') rec.stop(); }, 3000);
        };
        startCycle();
      };

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.type === 'transcript' && msg.text) {
            const words = msg.text.split(' ');
            const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            const segIndex = Date.now();
            setLiveSegments(prev => [...prev, { id: segIndex, text: '', time, complete: false }]);
            words.forEach((word, i) => {
              setTimeout(() => {
                setLiveSegments(prev => prev.map(seg =>
                  seg.id === segIndex
                    ? { ...seg, text: words.slice(0, i + 1).join(' '), complete: i === words.length - 1 }
                    : seg
                ));
              }, i * 60);
            });
          } else if (msg.type === 'error') {
            setLiveStatus(`Error: ${msg.message}`);
          }
        } catch (_) {}
      };

      ws.onclose = () => setLiveStatus('');
      ws.onerror = () => {
        // The audio is still being captured locally — only the live preview
        // is offline. Make that distinction explicit so the user doesn't
        // think the whole recording failed.
        setLiveStatus('Live preview unavailable');
        setLiveOffline(true);
      };
    } catch (err) {
      setLiveStatus('Live transcription unavailable');
    }
  };

  const stopRecording = () => {
    if (liveRecorderRef.current && liveRecorderRef.current.state === 'recording') {
      liveRecorderRef.current.stop();
    }
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'stop' }));
      wsRef.current.close();
    }
    setLiveStatus('');

    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop());
      }
      setIsRecording(false);
      setLiveSegments([]);
    }
  };

  const handleFileUpload = async () => {
    if (!uploadFile) return;
    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append('audio', uploadFile);
      formData.append('metadata', JSON.stringify({
        title: uploadTitle || uploadFile.name.replace(/\.[^/.]+$/, ''),
        platform: 'file_upload',
        source: 'file_upload',
        duration: 0,
        original_filename: uploadFile.name,
        file_size: uploadFile.size,
        language: localStorage.getItem('transcript_language') || undefined,
        template: selectedTemplate,
      }));

      const token = localStorage.getItem('auth_token');
      const response = await fetch(`${API_BASE_URL}/api/meetings/upload`, {
        method: 'POST',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        body: formData,
      });

      if (!response.ok) {
        const err = await response.text();
        throw new Error(err);
      }

      const result = await response.json();
      if (result.success) {
        setUploadFile(null);
        setUploadTitle('');
        if (onRecordingComplete) onRecordingComplete(result.meeting);
        if (onNotification) onNotification({ message: 'Audio uploaded! Processing started.', type: 'success' });
      }
    } catch (error) {
      if (onNotification) onNotification({ message: `Upload failed: ${error.message}`, type: 'error' });
    } finally {
      setIsUploading(false);
    }
  };

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="recorder" style={hidden ? { display: 'none' } : undefined}>
      <div className="recorder-card">
        {/* Mode tabs — only show when not recording */}
        {!isRecording && (
          <div className="recorder-tabs">
            <button
              className={`recorder-tab ${mode === 'record' ? 'active' : ''}`}
              onClick={() => setMode('record')}
            >
              <MicIcon size={16} />
              <span>Record</span>
            </button>
            <button
              className={`recorder-tab ${mode === 'upload' ? 'active' : ''}`}
              onClick={() => setMode('upload')}
            >
              <UploadIcon size={16} />
              <span>Upload</span>
            </button>
          </div>
        )}

        {/* ===== RECORD MODE ===== */}
        {(mode === 'record' || isRecording) && (
          <div className="recorder-body">
            {!isRecording ? (
              <>
                <div className="recorder-hero">
                  <div className="hero-icon">
                    <MicIcon size={28} />
                  </div>
                  <h2>Record Meeting</h2>
                  <p className="recorder-subtitle">Get AI-powered transcript, summary, and action items</p>
                </div>

                <div className="recorder-form">
                  <input
                    type="text"
                    className="recorder-input"
                    value={meetingTitle}
                    onChange={(e) => setMeetingTitle(e.target.value)}
                    placeholder="Meeting title (optional)"
                  />
                  {templates.length > 0 && (
                    <select
                      className="recorder-select"
                      value={selectedTemplate}
                      onChange={(e) => setSelectedTemplate(e.target.value)}
                    >
                      {templates.map(t => (
                        <option key={t.id} value={t.id}>{t.name}</option>
                      ))}
                    </select>
                  )}
                  <textarea
                    className="recorder-textarea"
                    value={meetingNotes}
                    onChange={(e) => setMeetingNotes(e.target.value)}
                    placeholder="Quick notes or context..."
                    rows="2"
                  />
                </div>

                {apiKeyWarning && (
                  <div className="api-key-warning">
                    <div className="api-key-warning-text">
                      {apiKeyWarning === 'both'
                        ? 'STT and LLM API keys are not configured. Recording requires at least an STT key for transcription.'
                        : 'STT API key is not configured. Live transcription will not work without it.'}
                    </div>
                    <div className="api-key-warning-actions">
                      {onOpenSettings && (
                        <button
                          className="api-key-warning-btn-settings"
                          onClick={() => { setApiKeyWarning(null); onOpenSettings(); }}
                        >
                          Go to Settings
                        </button>
                      )}
                      <button
                        className="api-key-warning-btn-dismiss"
                        onClick={() => { setApiKeyWarning(null); startRecording(); }}
                      >
                        Record anyway
                      </button>
                    </div>
                  </div>
                )}

                {micError && (
                  <div className="mic-error" role="alert">
                    <div className="mic-error-title">{micError.title}</div>
                    <div className="mic-error-body">{micError.body}</div>
                    <div className="mic-error-actions">
                      <button
                        type="button"
                        className="mic-error-retry"
                        onClick={() => { setMicError(null); startRecording(); }}
                      >
                        Try again
                      </button>
                      <button
                        type="button"
                        className="mic-error-dismiss"
                        onClick={() => setMicError(null)}
                      >
                        Dismiss
                      </button>
                    </div>
                  </div>
                )}

                <button className="btn-record btn-start" onClick={handleStartRecording}>
                  <MicIcon size={20} />
                  Start Recording
                </button>

                <div className="recorder-features">
                  <div className="feature-item">
                    <FileTextIcon size={14} />
                    <span>Live transcript</span>
                  </div>
                  <div className="feature-item">
                    <ClockIcon size={14} />
                    <span>Auto-summarize</span>
                  </div>
                </div>
              </>
            ) : (
              /* Recording active state */
              <div className="recording-active">
                <div className="recording-visualizer">
                  <div className="visualizer-ring ring-1"></div>
                  <div className="visualizer-ring ring-2"></div>
                  <div className="visualizer-ring ring-3"></div>
                  <div className="visualizer-core">
                    <MicIcon size={24} />
                  </div>
                </div>

                <div className="recording-time">{formatTime(recordingTime)}</div>

                <div className="recording-label">
                  <span className="pulse-dot"></span>
                  <span>Recording in progress</span>
                </div>

                <button className="btn-record btn-stop" onClick={stopRecording}>
                  <StopIcon size={20} />
                  Stop & Generate Summary
                </button>
              </div>
            )}
          </div>
        )}

        {/* ===== UPLOAD MODE ===== */}
        {mode === 'upload' && !isRecording && (
          <div className="recorder-body">
            <div className="recorder-hero">
              <div className="hero-icon hero-icon-upload">
                <UploadIcon size={28} />
              </div>
              <h2>Upload Recording</h2>
              <p className="recorder-subtitle">Transcribe a pre-recorded meeting from Zoom, Voice Memos, etc.</p>
            </div>

            <div
              className={`upload-dropzone ${dragOver ? 'drag-over' : ''} ${uploadFile ? 'has-file' : ''}`}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                const file = e.dataTransfer.files[0];
                if (file) setUploadFile(file);
              }}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".webm,.mp3,.wav,.m4a,.ogg,.flac,.mp4"
                style={{ display: 'none' }}
                onChange={(e) => { setUploadFile(e.target.files[0]); e.target.value = ''; }}
              />
              {uploadFile ? (
                <div className="upload-file-info">
                  <div className="file-icon-box">
                    <FileTextIcon size={20} />
                  </div>
                  <div className="file-details">
                    <span className="file-name">{uploadFile.name}</span>
                    <span className="file-size">{(uploadFile.size / 1024 / 1024).toFixed(1)} MB</span>
                  </div>
                  <button className="file-remove" onClick={(e) => { e.stopPropagation(); setUploadFile(null); }}>
                    <CloseIcon size={16} />
                  </button>
                </div>
              ) : (
                <div className="upload-placeholder">
                  <div className="upload-icon-circle">
                    <UploadIcon size={24} />
                  </div>
                  <span className="upload-cta">Drop audio file here or click to browse</span>
                  <span className="upload-formats">MP3, WAV, M4A, WebM, OGG, FLAC, MP4 — up to 500 MB</span>
                </div>
              )}
            </div>

            {uploadFile && (
              <div className="upload-form">
                <input
                  type="text"
                  className="recorder-input"
                  placeholder="Meeting title (optional)"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                />
                <button
                  className="btn-record btn-start"
                  onClick={handleFileUpload}
                  disabled={isUploading}
                  style={{ width: '100%' }}
                >
                  {isUploading ? (
                    <>Processing...</>
                  ) : (
                    <><UploadIcon size={20} /> Upload & Process</>
                  )}
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Live transcript panel */}
      {isRecording && (
        <div className="live-panel">
          <div className="live-panel-header">
            <span className="live-dot"></span>
            <h3>Live Transcript</h3>
            {liveStatus && <span className="live-panel-status">{liveStatus}</span>}
          </div>
          <div className="live-panel-body" ref={scrollRef}>
            {liveSegments.length === 0 ? (
              <p className="live-panel-empty">
                {liveOffline
                  ? "Live preview is offline, but your audio is still being recorded — the full transcript will be ready when you stop."
                  : "Listening… your words will show up here in about 3 seconds. The recording continues even if the preview lags."}
              </p>
            ) : (
              liveSegments.map((seg, i) => (
                <div key={seg.id || i} className="live-panel-segment">
                  <span className="live-panel-time">{seg.time}</span>
                  <span className={`live-panel-text ${!seg.complete ? 'typing' : ''}`}>{seg.text}</span>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default Recorder;
