// Content script for capturing audio from meeting pages

// === CONFIGURATION ===
// Change this URL to match your Minutes deployment
const FRONTEND_URL = 'http://localhost:9002';
// =====================

let mediaRecorder = null;
let audioChunks = [];
let stream = null;
let isRecording = false;

// Listen for messages from background script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log('📨 [CONTENT SCRIPT] Message received:', request);
  console.log('📨 [CONTENT SCRIPT] Sender:', sender);
  
  if (request.action === 'ping') {
    console.log('🏓 [CONTENT SCRIPT] Ping received, responding...');
    sendResponse({ success: true });
    return false;
  } else if (request.action === 'startRecording') {
    console.log('🎬 [CONTENT SCRIPT] startRecording action received, streamId:', request.streamId);
    if (request.streamId) {
      startRecording(request.streamId, sendResponse);
      return true; // Keep channel open for async response
    } else {
      console.error('❌ [CONTENT SCRIPT] No stream ID provided');
      sendResponse({ success: false, error: 'No stream ID provided' });
      return false;
    }
  } else if (request.action === 'stopRecording') {
    console.log('🛑 [CONTENT SCRIPT] stopRecording action received!');
    console.log('🛑 [CONTENT SCRIPT] Current state:', {
      hasMediaRecorder: !!mediaRecorder,
      isRecording: isRecording,
      audioChunksCount: audioChunks?.length || 0,
      streamExists: !!stream
    });
    
    // Also show an alert to confirm content script is running (for debugging)
    // Remove this after confirming it works
    if (window.location.href.includes('meet.google.com') || window.location.href.includes('zoom.us')) {
      console.log('✅ [CONTENT SCRIPT] Content script is active on meeting page!');
    }
    
    stopRecording(sendResponse);
    return true;
  }
  
  console.warn('⚠️ [CONTENT SCRIPT] Unknown action:', request.action);
  return false;
});

// Start recording audio
async function startRecording(streamId, sendResponse) {
  try {
    if (!streamId) {
      sendResponse({ success: false, error: 'No stream ID provided' });
      return;
    }
    
    // Get the media stream using the stream ID from tabCapture
    // Note: getUserMedia with chromeMediaSource works in content scripts
    // but requires the constraints to be in the correct format
    // For newer Chrome versions, use the new format
    const constraints = {
      audio: {
        mandatory: {
          chromeMediaSource: 'tab',
          chromeMediaSourceId: streamId
        }
      },
      video: false
    };
    
    // Try the newer format if the old one doesn't work
    const constraintsNew = {
      audio: {
        chromeMediaSource: 'tab',
        chromeMediaSourceId: streamId
      },
      video: false
    };
    
    console.log('Attempting to get user media with constraints:', constraints);
    
    // getUserMedia with chromeMediaSource
    // This should work in content scripts with proper permissions
    try {
      // Request the stream - this may fail if:
      // 1. Tab is not active
      // 2. No audio is playing
      // 3. Permissions not granted
      try {
        stream = await navigator.mediaDevices.getUserMedia(constraints);
        console.log('✅ Successfully got media stream with mandatory constraints');
      } catch (oldFormatError) {
        console.log('Old format failed, trying new format...', oldFormatError);
        // Try the newer format without 'mandatory'
        stream = await navigator.mediaDevices.getUserMedia(constraintsNew);
        console.log('✅ Successfully got media stream with new format constraints');
      }
    } catch (error) {
      console.error('getUserMedia error details:', {
        name: error.name,
        message: error.message,
        constraint: error.constraint
      });
      
      // Provide more helpful error messages
      let errorMessage = 'Failed to capture audio. ';
      
      if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
        errorMessage += 'Permission denied. Please:\n1. Check extension permissions\n2. Allow microphone access\n3. Reload the extension';
      } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
        errorMessage += 'No audio source found. Make sure:\n1. The meeting has audio playing\n2. Someone is speaking or audio is active';
      } else if (error.name === 'AbortError') {
        errorMessage += 'Tab capture was aborted. Please:\n1. Make sure the meeting tab is ACTIVE (click on it)\n2. Ensure audio is playing\n3. Try again';
      } else if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
        errorMessage += 'Cannot read audio stream. Please:\n1. Make sure the meeting tab is active\n2. Check if another app is using the microphone\n3. Refresh the page and try again';
      } else if (error.name === 'OverconstrainedError') {
        errorMessage += 'Audio constraints not supported. The meeting platform may not support tab capture.';
      } else {
        errorMessage += `Error: ${error.message || error.name}. Please try:\n1. Making the tab active\n2. Ensuring audio is playing\n3. Refreshing the page`;
      }
      
      throw new Error(errorMessage);
    }

    // Create MediaRecorder
    mediaRecorder = new MediaRecorder(stream, {
      mimeType: 'audio/webm;codecs=opus'
    });

    console.log('✅ MediaRecorder created:', {
      state: mediaRecorder.state,
      mimeType: mediaRecorder.mimeType
    });

    audioChunks = [];
    
    // Generate unique recording ID for this session
    const recordingId = `recording_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    console.log('🎬 [CONTENT SCRIPT] Starting recording session:', recordingId);

        mediaRecorder.ondataavailable = async (event) => {
          if (event.data.size > 0) {
            audioChunks.push(event.data);
            const chunkIndex = audioChunks.length - 1;
            console.log('📦 [CONTENT SCRIPT] Data chunk received:', event.data.size, 'bytes, chunk index:', chunkIndex);
            
            // Send chunk to background script to store in extension's IndexedDB
            // Content script IndexedDB is separate from background script IndexedDB
            // We need to send chunks to background script for storage
            try {
              // Convert blob to ArrayBuffer, then to regular array for JSON serialization
              const arrayBuffer = await event.data.arrayBuffer();
              const uint8Array = new Uint8Array(arrayBuffer);
              
              // Check message size - chrome.runtime.sendMessage has ~64MB limit, but we'll be conservative
              // Each chunk is ~1 second of audio, typically < 100KB, so should be fine
              if (uint8Array.length > 50 * 1024 * 1024) { // 50MB limit
                console.error(`❌ [CONTENT SCRIPT] Chunk ${chunkIndex} too large (${uint8Array.length} bytes), skipping`);
                return;
              }
              
              // Send chunk to background script for storage
              chrome.runtime.sendMessage({
                action: 'storeAudioChunk',
                recordingId: recordingId,
                chunkIndex: chunkIndex,
                chunkData: Array.from(uint8Array), // Convert to regular array for JSON
                chunkSize: event.data.size
              }, (response) => {
                if (chrome.runtime.lastError) {
                  const errorMsg = chrome.runtime.lastError.message;
                  if (errorMsg.includes('Extension context invalidated') || errorMsg.includes('message port closed')) {
                    console.warn(`⚠️ [CONTENT SCRIPT] Extension context invalidated. Chunk ${chunkIndex} may not be stored.`);
                  } else {
                    console.error(`❌ [CONTENT SCRIPT] Error storing chunk ${chunkIndex}:`, errorMsg);
                  }
                } else if (response && response.success) {
                  console.log(`✅ [CONTENT SCRIPT] Chunk ${chunkIndex} stored in background IndexedDB`);
                } else {
                  console.warn(`⚠️ [CONTENT SCRIPT] Chunk ${chunkIndex} storage returned:`, response);
                }
              });
            } catch (error) {
              // Only log if it's NOT an extension context error
              if (error && error.message && !error.message.includes('Extension context invalidated')) {
                console.error('❌ [CONTENT SCRIPT] Error sending chunk to background:', error);
              }
            }
          } else {
            console.warn('⚠️ [CONTENT SCRIPT] Received empty data chunk');
          }
        };

    // Set up onstop handler BEFORE starting
    // Note: Upload is now handled in stopRecording function to avoid CORS
    // This handler just cleans up the stream
    mediaRecorder.onstop = async () => {
      console.log('📤 [CONTENT SCRIPT] mediaRecorder.onstop handler triggered!');
      console.log('📤 [CONTENT SCRIPT] Audio chunks collected:', audioChunks.length, 'chunks');
      console.log('📤 [CONTENT SCRIPT] Upload will be handled by stopRecording function');
      
      // Clean up stream
      if (stream) {
        stream.getTracks().forEach(track => track.stop());
        console.log('✅ [CONTENT SCRIPT] Stream tracks stopped in onstop handler');
      }
    };

    // Verify onstop handler is set
    if (!mediaRecorder.onstop) {
      console.error('❌ CRITICAL: onstop handler is not set!');
    } else {
      console.log('✅ onstop handler is set');
    }
    
    mediaRecorder.start(1000); // Collect data every second
    console.log('✅ MediaRecorder started, state:', mediaRecorder.state);
    
    isRecording = true;
    
    // Store start time for duration calculation
    mediaRecorder.startTime = Date.now();
    mediaRecorder.recordingId = recordingId; // Store recording ID for later use
    console.log('Recording start time:', mediaRecorder.startTime);
    
    // Initialize recording session in background script
    // Note: Content scripts can't use chrome.tabs.query, so we let background script get tabId from sender
    chrome.runtime.sendMessage({
      action: 'startRecordingSession',
      recordingId: recordingId
      // tabId will be set by background script from sender.tab.id
    }, (response) => {
      if (chrome.runtime.lastError) {
        console.warn('⚠️ [CONTENT SCRIPT] Error initializing recording session:', chrome.runtime.lastError.message);
      } else if (response && response.success) {
        console.log('✅ [CONTENT SCRIPT] Recording session initialized in background');
      }
    });
    
    // Update UI
    showRecordingIndicator();
    
    sendResponse({ success: true, recordingId: recordingId });
  } catch (error) {
    console.error('Error starting recording:', error);
    sendResponse({ success: false, error: error.message });
  }
}

// Stop recording
function stopRecording(sendResponse) {
  console.log('🛑 [CONTENT SCRIPT] stopRecording function called!');
  console.log('🛑 [CONTENT SCRIPT] State check:', {
    hasMediaRecorder: !!mediaRecorder,
    isRecording: isRecording,
    mediaRecorderState: mediaRecorder?.state,
    hasOnStopHandler: !!mediaRecorder?.onstop,
    audioChunksCount: audioChunks?.length || 0,
    streamExists: !!stream
  });
  
  if (mediaRecorder && isRecording) {
    console.log('Stopping MediaRecorder, current state:', mediaRecorder.state);
    
    // Verify onstop handler is set
    if (!mediaRecorder.onstop) {
      console.error('❌ CRITICAL: mediaRecorder.onstop handler is missing!');
      console.error('This means upload will NOT happen!');
      // Try to re-attach the handler (this shouldn't be necessary but let's try)
      console.warn('⚠️ Attempting to re-attach onstop handler...');
      // We can't re-attach it here because we don't have access to the original handler
      // But let's at least try to upload manually
    } else {
      console.log('✅ onstop handler is present, will fire when MediaRecorder stops');
    }
    
    try {
      // Check if MediaRecorder is in a valid state to stop
      if (mediaRecorder.state === 'inactive') {
        console.warn('⚠️ MediaRecorder is already inactive, but isRecording flag is true');
        // Try to trigger upload manually if we have chunks
        if (audioChunks && audioChunks.length > 0) {
          console.log('Attempting manual upload since MediaRecorder is already stopped...');
          // Manually trigger the upload logic
          triggerUpload();
        }
        isRecording = false;
        hideRecordingIndicator();
        sendResponse({ success: true });
        return;
      }
      
      // Immediately hide recording indicator and update state
      isRecording = false;
      hideRecordingIndicator();
      console.log('✅ Recording indicator hidden immediately');
      
      // Check if we have audio chunks before stopping
      console.log('📊 Before stop:', {
        chunksCount: audioChunks.length,
        chunksTotalSize: audioChunks.reduce((sum, chunk) => sum + chunk.size, 0),
        mediaRecorderState: mediaRecorder.state
      });
      
      // Store reference to audio chunks and stream before stopping
      const chunksToUpload = [...audioChunks];
      const streamToCleanup = stream;
      const startTime = mediaRecorder.startTime || Date.now();
      
      // Stop the MediaRecorder
      try {
        mediaRecorder.stop();
        console.log('✅ mediaRecorder.stop() called, new state:', mediaRecorder.state);
      } catch (stopError) {
        console.error('❌ Error calling mediaRecorder.stop():', stopError);
      }
      
      // ALWAYS trigger upload after a short delay (don't rely on onstop)
      console.log('⏳ [CONTENT SCRIPT] Scheduling upload in 500ms...');
      console.log('⏳ [CONTENT SCRIPT] Chunks stored:', chunksToUpload.length);
      
      // Also set up a visual indicator that upload is starting
      const uploadIndicator = document.createElement('div');
      uploadIndicator.id = 'meeting-note-upload-indicator';
      uploadIndicator.innerHTML = `
        <div style="
          position: fixed;
          top: 20px;
          right: 20px;
          background: #2196F3;
          color: white;
          padding: 12px 20px;
          border-radius: 8px;
          box-shadow: 0 4px 6px rgba(0,0,0,0.3);
          z-index: 10001;
          font-family: Arial, sans-serif;
          font-size: 14px;
          font-weight: 600;
        ">
          📤 Uploading recording...
        </div>
      `;
      document.body.appendChild(uploadIndicator);
      console.log('✅ [CONTENT SCRIPT] Upload indicator shown');
      
      // Set a timeout to remove indicator if upload takes too long (90 seconds - longer than upload timeout)
      // This is a safety mechanism in case the upload hangs
      let uploadCompleted = false;
      const uploadTimeout = setTimeout(() => {
        if (!uploadCompleted) {
          const indicator = document.getElementById('meeting-note-upload-indicator');
          if (indicator) {
            console.warn('⚠️ [CONTENT SCRIPT] Upload taking longer than expected - indicator will remain visible');
            // Don't remove, just update the message to show it's still processing
            indicator.innerHTML = `
              <div style="
                position: fixed;
                top: 20px;
                right: 20px;
                background: #FF9800;
                color: white;
                padding: 12px 20px;
                border-radius: 8px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.3);
                z-index: 10001;
                font-family: Arial, sans-serif;
                font-size: 14px;
                font-weight: 600;
              ">
                ⏳ Upload still processing... (this may take a while for large files)
              </div>
            `;
          }
        }
      }, 90000); // 90 seconds - longer than the 60 second upload timeout
      
      setTimeout(async () => {
        console.log('🔍 [CONTENT SCRIPT] Checking upload status after stop...', {
          mediaRecorderState: mediaRecorder.state,
          chunksCount: audioChunks.length,
          chunksToUploadCount: chunksToUpload.length,
          hasChunks: chunksToUpload.length > 0,
          chunksTotalSize: chunksToUpload.reduce((sum, chunk) => sum + chunk.size, 0)
        });
        
        // Use streaming finalize approach (chunks were already sent during recording)
        const recordingId = mediaRecorder?.recordingId;
        if (recordingId) {
          console.log('🔍 [CONTENT SCRIPT] Finalizing recording session with streaming chunks...', {
            recordingId: recordingId,
            chunksCount: chunksToUpload.length
          });
          
          // Get meeting metadata
          const metadata = {
            url: window.location.href,
            title: document.title || `Meeting ${new Date().toLocaleString()}`,
            platform: detectMeetingPlatform(),
            source: 'browser_extension',
            timestamp: new Date().toISOString(),
            duration: Math.floor((Date.now() - startTime) / 1000)
          };

          console.log('Meeting metadata:', metadata);

          // Finalize recording - background script will retrieve chunks from IndexedDB and upload
          try {
            const uploadStartTime = Date.now();
            
            const result = await new Promise((resolve, reject) => {
              const timeout = setTimeout(() => {
                reject(new Error('Finalize timeout - background script did not respond'));
              }, 120000); // 120 second timeout for large files
              
              chrome.runtime.sendMessage({
                action: 'finalizeRecording',
                recordingId: recordingId,
                metadata: metadata
              }, (response) => {
                clearTimeout(timeout);
                if (chrome.runtime.lastError) {
                  reject(new Error(chrome.runtime.lastError.message));
                } else if (response && response.success) {
                  resolve(response);
                } else {
                  reject(new Error(response?.error || 'Finalize failed'));
                }
              });
            });
            
            const uploadDuration = Date.now() - uploadStartTime;
            console.log(`📥 [CONTENT SCRIPT] Upload completed (took ${uploadDuration}ms):`, result);
            
            if (result.success) {
              console.log('✅ [CONTENT SCRIPT] Audio uploaded successfully!', {
                meetingId: result.meeting_id,
                meeting: result.meeting
              });
              
              // Mark upload as completed
              uploadCompleted = true;
              
              // Clear timeout since upload completed
              clearTimeout(uploadTimeout);
              
              // Remove upload indicator
              const indicator = document.getElementById('meeting-note-upload-indicator');
              if (indicator) {
                console.log('✅ [CONTENT SCRIPT] Removing upload indicator');
                indicator.remove();
              } else {
                console.warn('⚠️ [CONTENT SCRIPT] Upload indicator not found to remove');
              }
              
              const meetingId = result.meeting_id || result.meeting?.id;
              const meetingUrl = `${FRONTEND_URL}?meeting=${meetingId}`;
              showNotification(`✅ Recording uploaded! <a href="${meetingUrl}" target="_blank" style="color: white; text-decoration: underline; font-weight: bold;">View in My Meetings →</a>`);
            } else {
              throw new Error(result.error || 'Upload failed');
            }
          } catch (error) {
            console.error('❌ [CONTENT SCRIPT] Error uploading audio:', error);
            console.error('❌ [CONTENT SCRIPT] Error details:', {
              name: error.name,
              message: error.message,
              stack: error.stack
            });
            
            // Mark upload as completed (even though it failed)
            uploadCompleted = true;
            
            // Clear timeout
            clearTimeout(uploadTimeout);
            
            // Update upload indicator to show error
            const indicator = document.getElementById('meeting-note-upload-indicator');
            if (indicator) {
              indicator.innerHTML = `
                <div style="
                  position: fixed;
                  top: 20px;
                  right: 20px;
                  background: #f44336;
                  color: white;
                  padding: 12px 20px;
                  border-radius: 8px;
                  box-shadow: 0 4px 6px rgba(0,0,0,0.3);
                  z-index: 10001;
                  font-family: Arial, sans-serif;
                  font-size: 14px;
                  font-weight: 600;
                ">
                  ❌ Upload error: ${error.message}
                </div>
              `;
              setTimeout(() => {
                if (indicator && indicator.parentNode) {
                  indicator.remove();
                }
              }, 5000);
            }
            
            showNotification(`❌ Upload error: ${error.message}`);
          }
          
          // Clean up stream
          if (streamToCleanup) {
            streamToCleanup.getTracks().forEach(track => {
              track.stop();
              console.log('Stopped stream track');
            });
          }
        } else {
          console.error('❌ [CONTENT SCRIPT] No audio chunks to upload!', {
            chunksToUploadLength: chunksToUpload.length,
            audioChunksLength: audioChunks.length,
            mediaRecorderState: mediaRecorder.state
          });
          
          // Mark upload as completed (no upload needed)
          uploadCompleted = true;
          
          // Clear timeout
          clearTimeout(uploadTimeout);
          
          // Remove upload indicator
          const indicator = document.getElementById('meeting-note-upload-indicator');
          if (indicator) {
            console.log('✅ [CONTENT SCRIPT] Removing upload indicator (no chunks)');
            indicator.remove();
          }
          
          showNotification('⚠️ No audio data recorded. Please try recording again.');
        }
      }, 500); // Wait 500ms then upload
      
      console.log('✅ [CONTENT SCRIPT] Upload scheduled, will execute in 500ms');
      
      sendResponse({ success: true });
    } catch (error) {
      console.error('❌ Error stopping MediaRecorder:', error);
      sendResponse({ success: false, error: `Failed to stop recording: ${error.message}` });
    }
  } else {
    console.error('❌ Cannot stop recording:', {
      hasMediaRecorder: !!mediaRecorder,
      isRecording: isRecording
    });
    sendResponse({ success: false, error: 'No active recording' });
  }
}

// Manual upload trigger (fallback if onstop doesn't fire)
// Now uses background script to avoid CORS
async function triggerUpload() {
  console.log('🔄 [CONTENT SCRIPT] triggerUpload called manually');
  
  if (!audioChunks || audioChunks.length === 0) {
    console.error('❌ [CONTENT SCRIPT] No audio chunks to upload');
    return;
  }
  
  const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
  console.log('📦 [CONTENT SCRIPT] Created audio blob from chunks:', {
    size: audioBlob.size,
    chunks: audioChunks.length
  });
  
  // Get meeting metadata
  const metadata = {
    url: window.location.href,
    title: document.title || `Meeting ${new Date().toLocaleString()}`,
    platform: detectMeetingPlatform(),
    source: 'browser_extension',
    timestamp: new Date().toISOString(),
    duration: Math.floor((Date.now() - (mediaRecorder?.startTime || Date.now())) / 1000)
  };

  // Upload via background script to avoid CORS
  // Use chrome.storage.local for large files
  try {
    console.log('📤 [CONTENT SCRIPT] Storing audio blob for background upload...', {
      audioSize: audioBlob.size
    });
    
    // Convert blob to ArrayBuffer for chunking
    const arrayBuffer = await audioBlob.arrayBuffer();
    const uint8Array = new Uint8Array(arrayBuffer);
    
    // Chrome storage has a 5MB limit per item, so we need to chunk if larger
    const CHUNK_SIZE = 4 * 1024 * 1024; // 4MB chunks (safe margin)
    const totalChunks = Math.ceil(uint8Array.length / CHUNK_SIZE);
    
    console.log(`📦 [CONTENT SCRIPT] Audio size: ${audioBlob.size} bytes, splitting into ${totalChunks} chunks`);
    
    // Generate unique upload ID
    const uploadId = `upload_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
            // Use IndexedDB for large files (has much larger limits than chrome.storage)
            // Store the entire blob directly in IndexedDB
            const dbName = 'MeetingNoteTaker';
            const storeName = 'audioUploads';
            
            // Open IndexedDB
            const db = await new Promise((resolve, reject) => {
              const request = indexedDB.open(dbName, 1);
              request.onerror = () => reject(request.error);
              request.onsuccess = () => resolve(request.result);
              request.onupgradeneeded = (event) => {
                const db = event.target.result;
                if (!db.objectStoreNames.contains(storeName)) {
                  db.createObjectStore(storeName);
                }
              };
            });
            
            // Store the blob in IndexedDB
            const transaction = db.transaction([storeName], 'readwrite');
            const store = transaction.objectStore(storeName);
            await new Promise((resolve, reject) => {
              const request = store.put(audioBlob, uploadId);
              request.onsuccess = () => resolve();
              request.onerror = () => reject(request.error);
            });
            
            // Store metadata in chrome.storage (small, so it's OK)
            await chrome.storage.local.set({
              [`${uploadId}_metadata`]: {
                totalSize: audioBlob.size,
                totalChunks: 1, // Single blob in IndexedDB
                mimeType: audioBlob.type,
                metadata: metadata,
                storageType: 'indexeddb' // Flag to indicate IndexedDB storage
              }
            });
            
            console.log(`✅ [CONTENT SCRIPT] Stored audio blob (${audioBlob.size} bytes) in IndexedDB`);
    
    // Notify background script to upload
    const result = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('Upload timeout - background script did not respond'));
      }, 120000); // 120 second timeout for large files
      
      chrome.runtime.sendMessage({
        action: 'uploadAudioFromStorage',
        uploadId: uploadId,
        totalChunks: totalChunks,
        totalSize: audioBlob.size
      }, (response) => {
        clearTimeout(timeout);
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else if (response && response.success) {
          resolve(response);
        } else {
          reject(new Error(response?.error || 'Upload failed'));
        }
      });
    });
    
    if (result.success) {
      console.log('✅ [CONTENT SCRIPT] Audio uploaded successfully!', {
        meetingId: result.meeting_id
      });
      
      const meetingId = result.meeting_id || result.meeting?.id;
      const meetingUrl = `${FRONTEND_URL}?meeting=${meetingId}`;
      showNotification(`✅ Recording uploaded! <a href="${meetingUrl}" target="_blank" style="color: white; text-decoration: underline; font-weight: bold;">View in My Meetings →</a>`);
    } else {
      throw new Error(result.error || 'Upload failed');
    }
  } catch (error) {
    console.error('❌ [CONTENT SCRIPT] Error uploading audio:', error);
    showNotification(`❌ Upload error: ${error.message}`);
  }
  
  // Clean up
  if (stream) {
    stream.getTracks().forEach(track => track.stop());
  }
}

// Detect meeting platform
function detectMeetingPlatform() {
  const url = window.location.href;
  if (url.includes('meet.google.com')) return 'google_meet';
  if (url.includes('zoom.us')) return 'zoom';
  if (url.includes('teams.microsoft.com')) return 'teams';
  return 'unknown';
}

// Show recording indicator
function showRecordingIndicator() {
  // Remove any existing indicator first
  hideRecordingIndicator();
  
  console.log('Showing recording indicator...');
  const indicator = document.createElement('div');
  indicator.id = 'meeting-note-recorder-indicator';
  indicator.innerHTML = `
    <div style="
      position: fixed;
      top: 20px;
      right: 20px;
      background: #f44336;
      color: white;
      padding: 12px 20px;
      border-radius: 8px;
      box-shadow: 0 4px 6px rgba(0,0,0,0.3);
      z-index: 10000;
      font-family: Arial, sans-serif;
      font-size: 14px;
      display: flex;
      align-items: center;
      gap: 8px;
      font-weight: 600;
    ">
      <span style="
        width: 12px;
        height: 12px;
        background: white;
        border-radius: 50%;
        animation: pulse 1.5s infinite;
      "></span>
      Recording...
    </div>
    <style>
      @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
      }
    </style>
  `;
  document.body.appendChild(indicator);
  console.log('✅ Recording indicator added to DOM');
}

// Hide recording indicator
function hideRecordingIndicator() {
  console.log('Hiding recording indicator...');
  const indicator = document.getElementById('meeting-note-recorder-indicator');
  if (indicator) {
    indicator.remove();
    console.log('✅ Recording indicator removed from DOM');
  } else {
    console.log('No recording indicator found to hide');
  }
  
  // Also try to remove by class name as fallback
  const indicators = document.querySelectorAll('[id="meeting-note-recorder-indicator"]');
  indicators.forEach(ind => {
    ind.remove();
    console.log('Removed indicator by querySelector');
  });
}

// Show notification
function showNotification(message) {
  const notification = document.createElement('div');
  notification.innerHTML = `
    <div style="
      position: fixed;
      top: 20px;
      right: 20px;
      background: #4CAF50;
      color: white;
      padding: 12px 20px;
      border-radius: 8px;
      box-shadow: 0 4px 6px rgba(0,0,0,0.3);
      z-index: 10001;
      font-family: Arial, sans-serif;
      font-size: 14px;
      max-width: 400px;
    ">
      ${message}
    </div>
  `;
  document.body.appendChild(notification);
  
  setTimeout(() => {
    notification.remove();
  }, 8000); // Show for 8 seconds to give user time to click link
}

