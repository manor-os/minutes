// Background service worker for Meeting Note Taker extension

console.log('🔧 Background service worker loaded/activated');

// === CONFIGURATION ===
// Change this URL to match your Minutes deployment
const API_BASE_URL = 'http://localhost:8002';
// =====================

// Store active recordings
const activeRecordings = new Map();

// Keep service worker alive by listening to events
chrome.runtime.onInstalled.addListener(() => {
  console.log('✅ Extension installed/updated');
});

chrome.runtime.onStartup.addListener(() => {
  console.log('✅ Extension startup');
});

// Listen for extension icon click to wake up service worker
chrome.action.onClicked.addListener((tab) => {
  console.log('🔔 Extension icon clicked, service worker active');
});

// Listen for messages from content script or popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log('📨 Message received in background script:', request.action, request);
  console.log('📨 Sender:', sender);
  
  // Helper to safely get tab ID
  const getTabId = () => {
    if (request.tabId) {
      console.log('Using tabId from request:', request.tabId);
      return request.tabId;
    }
    if (sender && sender.tab && sender.tab.id) {
      console.log('Using tabId from sender:', sender.tab.id);
      return sender.tab.id;
    }
    console.warn('No tab ID found in request or sender');
    return null;
  };
  
  // Handle ping to wake up service worker
  if (request.action === 'ping') {
    console.log('🏓 Ping received, service worker is active');
    sendResponse({ success: true, message: 'Service worker is active', timestamp: Date.now() });
    return false; // Synchronous response
  }
  
  // Handle upload complete notification (for logging)
  if (request.action === 'uploadComplete') {
    console.log('✅ Upload completed for meeting:', request.meetingId);
    sendResponse({ success: true });
    return false;
  }
  
  // Handle upload request from content script (to avoid CORS issues)
  if (request.action === 'uploadAudio') {
    console.log('📤 Upload request received from content script (legacy method)');
    uploadAudioFromContentScript(request, sender, sendResponse);
    return true; // Keep channel open for async response
  }
  
  // Handle upload from storage (for large files)
  if (request.action === 'uploadAudioFromStorage') {
    console.log('📤 Upload request from storage received from content script');
    uploadAudioFromStorage(request, sender, sendResponse);
    return true; // Keep channel open for async response
  }
  
  // Handle storing audio chunks from content script
  if (request.action === 'storeAudioChunk') {
    console.log(`📦 Store audio chunk ${request.chunkIndex} received for ${request.recordingId}`);
    storeAudioChunk(request, sender).then(response => {
      sendResponse(response || { success: true });
    }).catch(error => {
      console.error('❌ Error in storeAudioChunk:', error);
      sendResponse({ success: false, error: error.message });
    });
    return true; // Keep channel open for async response
  }
  
  // Handle streaming audio chunks (legacy - for backward compatibility)
  if (request.action === 'streamAudioChunk') {
    console.log(`📦 Stream audio chunk ${request.chunkIndex} received (legacy)`);
    handleStreamChunk(request, sender);
    sendResponse({ success: true });
    return false; // Synchronous response
  }
  
  // Handle recording session start
  if (request.action === 'startRecordingSession') {
    console.log('🎬 Starting recording session:', request.recordingId);
    startRecordingSession(request, sender);
    sendResponse({ success: true });
    return false; // Synchronous response
  }
  
  // Handle recording finalization
  if (request.action === 'finalizeRecording') {
    console.log('🏁 Finalizing recording:', request.recordingId);
    finalizeRecording(request, sender, sendResponse);
    return true; // Keep channel open for async response
  }
  
  // Handle async operations properly
  if (request.action === 'startRecording') {
    console.log('🎬 startRecording action received');
    const tabId = getTabId();
    console.log('Tab ID:', tabId);
    
    if (!tabId) {
      console.error('❌ No tab ID provided');
      const errorMsg = 'No tab ID provided. Please refresh the page and try again.';
      sendResponse({ success: false, error: errorMsg });
      return false;
    }
    
    console.log('✅ Starting recording for tab:', tabId);
    
    // Use async/await pattern to ensure response is sent
    (async () => {
      try {
        await startRecording(tabId, sendResponse);
      } catch (error) {
        console.error('❌ Error in startRecording:', error);
        try {
          sendResponse({ success: false, error: error.message || 'Failed to start recording' });
        } catch (e) {
          console.error('❌ Error sending error response:', e);
        }
      }
    })();
    
    return true; // Keep channel open for async response
  } else if (request.action === 'stopRecording') {
    const tabId = getTabId();
    if (!tabId) {
      sendResponse({ success: false, error: 'No tab ID provided' });
      return false;
    }
    stopRecording(tabId, sendResponse).catch(error => {
      console.error('Error in stopRecording:', error);
      sendResponse({ success: false, error: error.message || 'Failed to stop recording' });
    });
    return true;
  } else if (request.action === 'uploadAudio') {
    // Legacy support - upload now happens directly from page context
    uploadAudio(request.audioBlob, request.metadata, sendResponse).catch(error => {
      console.error('Error in uploadAudio:', error);
      sendResponse({ success: false, error: error.message || 'Failed to upload audio' });
    });
    return true;
  } else if (request.action === 'getMeetingStatus') {
    const tabId = getTabId();
    if (!tabId) {
      sendResponse({ isRecording: false });
      return false;
    }
    getMeetingStatus(tabId, sendResponse).catch(error => {
      console.error('Error in getMeetingStatus:', error);
      sendResponse({ isRecording: false });
    });
    return true;
  }
  
  // Unknown action
  console.warn('⚠️ Unknown action:', request.action);
  sendResponse({ success: false, error: 'Unknown action: ' + request.action });
  return false;
});

// Start recording audio from tab
async function startRecording(tabId, sendResponse, request = {}) {
  console.log('🎬 startRecording function called with tabId:', tabId, 'streamId provided:', !!request.streamId);
  
  // Ensure sendResponse is called even on error
  let responseSent = false;
  const safeSendResponse = (data) => {
    if (!responseSent) {
      responseSent = true;
      try {
        console.log('📤 Sending response:', data);
        sendResponse(data);
        console.log('✅ Response sent successfully');
      } catch (e) {
        console.error('❌ Error sending response:', e);
        console.error('Response data was:', data);
      }
    } else {
      console.warn('⚠️ Attempted to send response twice, ignoring second call');
    }
  };
  
  try {
    // Validate tab ID
    if (!tabId) {
      safeSendResponse({ success: false, error: 'Invalid tab ID' });
      return;
    }
    
    // Get tab info to verify it exists and is active
    let tab;
    try {
      tab = await chrome.tabs.get(tabId);
      if (!tab) {
        safeSendResponse({ success: false, error: 'Tab not found' });
        return;
      }
      
      // Check if tab is active - this is critical for tab capture
      if (!tab.active) {
        // Try to activate the tab and window
        try {
          // Get the window ID first
          const windowId = tab.windowId;
          if (windowId) {
            // Focus the window first
            await chrome.windows.update(windowId, { focused: true });
            await new Promise(resolve => setTimeout(resolve, 100));
          }
          
          // Then activate the tab
          await chrome.tabs.update(tabId, { active: true });
          // Wait a bit for tab to become active
          await new Promise(resolve => setTimeout(resolve, 300));
          // Re-check tab state
          tab = await chrome.tabs.get(tabId);
        } catch (e) {
          console.error('Failed to activate tab:', e);
        }
        
        if (!tab.active) {
          safeSendResponse({ 
            success: false, 
            error: '⚠️ Please click on the meeting tab to make it active before recording.\n\nThe tab must be the active/focused tab for audio capture to work.\n\nWe tried to activate it automatically, but it\'s still not active.' 
          });
          return;
        }
      }
      
      // Also ensure the window is focused
      try {
        if (tab.windowId) {
          const window = await chrome.windows.get(tab.windowId);
          if (!window.focused) {
            await chrome.windows.update(tab.windowId, { focused: true });
            await new Promise(resolve => setTimeout(resolve, 200));
          }
        }
      } catch (e) {
        console.warn('Could not focus window:', e);
      }
      
      console.log('Tab state:', { 
        id: tabId, 
        active: tab.active, 
        audible: tab.audible, 
        muted: tab.mutedInfo?.muted,
        url: tab.url,
        windowId: tab.windowId
      });
    } catch (e) {
      safeSendResponse({ success: false, error: 'Cannot access tab: ' + e.message });
      return;
    }
    
    // Use chrome.tabCapture.capture() directly - this is the most reliable method for Manifest V3
    // IMPORTANT: This only works for the currently ACTIVE tab
    try {
      console.log('Capturing tab audio using chrome.tabCapture.capture()...');
      console.log('Tab info:', { id: tabId, url: tab.url, active: tab.active, audible: tab.audible });
      
            // Check if streamId was provided from popup (avoids activeTab timing issues)
            let streamId = request.streamId;
            
            if (!streamId) {
              // If not provided, try to get it (may fail due to activeTab timing)
              console.log('⚠️ No streamId provided, attempting to get it...');
              
              // Ensure tab is active first
              try {
                await chrome.tabs.update(tabId, { active: true });
                await new Promise(resolve => setTimeout(resolve, 300));
                // Verify tab is now active
                const updatedTab = await chrome.tabs.get(tabId);
                if (!updatedTab.active) {
                  console.warn('⚠️ Tab is still not active after update attempt');
                }
              } catch (e) {
                console.warn('Could not activate tab:', e);
              }
              
              // Try to get media stream ID
              let streamIdError = null;
              try {
                streamId = await chrome.tabCapture.getMediaStreamId({
                  targetTabId: tabId
                });
                console.log('✅ Got stream ID in background:', streamId);
              } catch (error) {
                streamIdError = error;
                console.warn('⚠️ Could not get streamId in background:', error.message);
                
                // Try alternative: Inject into MAIN world
                try {
                  console.log('🔧 Trying MAIN world injection...');
                  await chrome.scripting.executeScript({
                    target: { tabId: tabId },
                    world: 'MAIN',
                    func: () => true
                  });
                  await new Promise(resolve => setTimeout(resolve, 200));
                  
                  streamId = await chrome.tabCapture.getMediaStreamId({
                    targetTabId: tabId
                  });
                  console.log('✅ Got stream ID on second attempt:', streamId);
                  streamIdError = null;
                } catch (secondError) {
                  console.error('❌ Second attempt also failed:', secondError);
                  streamIdError = secondError;
                }
              }
              
              // If still failed, provide helpful error message
              if (streamIdError) {
                console.error('getMediaStreamId failed after all attempts:', streamIdError);
                
                let errorMsg = `Permission error: ${streamIdError.message}\n\n`;
                
                if (streamIdError.message.includes('activeTab')) {
                  errorMsg += 'The activeTab permission requires the extension to be invoked.\n\n';
                  errorMsg += 'Please try this EXACT sequence:\n';
                  errorMsg += '1. Make sure the meeting tab is ACTIVE (click on it)\n';
                  errorMsg += '2. Click the extension icon in the toolbar\n';
                  errorMsg += '3. IMMEDIATELY click "Start Recording" (while popup is open)\n';
                  errorMsg += '4. Do NOT close the popup before clicking Start Recording\n\n';
                  errorMsg += 'If it still fails:\n';
                  errorMsg += '- Refresh the meeting page\n';
                  errorMsg += '- Try again with the popup open';
                } else if (streamIdError.message.includes('Chrome pages')) {
                  errorMsg += 'Chrome internal pages cannot be captured.\n\n';
                  errorMsg += 'Please use the extension on:\n';
                  errorMsg += '- Google Meet (meet.google.com)\n';
                  errorMsg += '- Zoom (zoom.us)\n';
                  errorMsg += '- Microsoft Teams (teams.microsoft.com)';
                } else {
                  errorMsg += 'Please:\n';
                  errorMsg += '1. Make sure the tab is ACTIVE\n';
                  errorMsg += '2. Grant tab capture permissions\n';
                  errorMsg += '3. Try reloading the extension';
                }
                
                safeSendResponse({
                  success: false,
                  error: errorMsg
                });
                return;
              }
            } else {
              console.log('✅ Using streamId provided from popup:', streamId);
            }
      
      // Wait a moment to ensure tab and window are fully active
      await new Promise(resolve => setTimeout(resolve, 300));
      
      // Double-check tab is still active
      const currentTab = await chrome.tabs.get(tabId);
      if (!currentTab.active) {
        safeSendResponse({ 
          success: false, 
          error: '⚠️ Tab is not active. Please:\n1. Click on the meeting tab\n2. Make sure it\'s the focused window\n3. Try recording again' 
        });
        return;
      }
      
      // streamId is already obtained above
      // In Manifest V3, chrome.tabCapture.capture() is not available in service workers
      // We need to use the content script to capture audio using getUserMedia with the streamId
      console.log('Using content script to capture audio with streamId:', streamId);
      
      // Ensure content script is loaded
      try {
        await chrome.tabs.sendMessage(tabId, { action: 'ping' });
        console.log('✅ Content script is loaded');
      } catch (e) {
        console.log('Content script not loaded, injecting...');
        try {
          await chrome.scripting.executeScript({
            target: { tabId: tabId },
            files: ['content.js']
          });
          // Wait a bit for script to initialize
          await new Promise(resolve => setTimeout(resolve, 200));
          console.log('✅ Content script injected');
        } catch (injectError) {
          console.error('Failed to inject content script:', injectError);
          safeSendResponse({ 
            success: false, 
            error: `Failed to load recording script: ${injectError.message}\n\nPlease:\n1. Refresh the meeting page\n2. Make sure you're on a supported platform (Google Meet, Zoom, Teams)\n3. Try again` 
          });
          return;
        }
      }
      
      // Send streamId to content script to start recording
      try {
        const captureResponse = await new Promise((resolve, reject) => {
          const timeout = setTimeout(() => {
            reject(new Error('Content script capture timed out after 10 seconds'));
          }, 10000);
          
          chrome.tabs.sendMessage(tabId, {
            action: 'startRecording',
            streamId: streamId
          }, (response) => {
            clearTimeout(timeout);
            if (chrome.runtime.lastError) {
              reject(new Error(chrome.runtime.lastError.message));
              return;
            }
            if (!response) {
              reject(new Error('No response from content script'));
              return;
            }
            resolve(response);
          });
        });
        
        if (!captureResponse || !captureResponse.success) {
          throw new Error(captureResponse?.error || 'Failed to start recording in content script');
        }
        
        // Content script will handle the recording and upload
        // Store the recording info for status tracking
        await chrome.storage.local.set({
          [`recording_${tabId}`]: {
            startTime: Date.now(),
            isRecording: true,
            streamId: streamId
          }
        });
        
        console.log('✅ Recording started in content script');
        safeSendResponse({ success: true });
        return;
        
      } catch (contentError) {
        console.error('Content script capture failed:', contentError);
        safeSendResponse({ 
          success: false, 
          error: `Failed to capture audio: ${contentError.message}\n\nPlease ensure:\n1. The meeting tab is ACTIVE (click on it)\n2. Audio is playing in the meeting\n3. You have granted tab capture permissions\n4. Try refreshing the meeting page` 
        });
        return;
      }
      
      if (!stream) {
        throw new Error('Failed to get audio stream');
      }
      
      console.log('✅ Got stream:', stream);
      
      // Create MediaRecorder in background script
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus'
      });
      
      const audioChunks = [];
      const recordingStartTime = Date.now();
      
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunks.push(event.data);
        }
      };
      
      mediaRecorder.onstop = async () => {
        console.log('Recording stopped, processing audio...');
        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
        
        // Get meeting metadata
        const metadata = {
          url: tab.url,
          title: tab.title || 'Browser Extension Recording',
          platform: detectPlatform(tab.url),
          source: 'browser_extension',
          timestamp: new Date().toISOString(),
          duration: Math.floor((Date.now() - recordingStartTime) / 1000)
        };
        
        // Upload to backend
        try {
          const formData = new FormData();
          formData.append('audio', audioBlob, 'meeting_audio.webm');
          formData.append('metadata', JSON.stringify(metadata));
          
          // Get auth token from chrome.storage
          const storage = await chrome.storage.local.get(['auth_token']);
          const authToken = storage.auth_token;
          
          const headers = {};
          if (authToken) {
            headers['Authorization'] = `Bearer ${authToken}`;
            console.log('✅ Using auth token for upload');
          } else {
            console.warn('⚠️ No auth token found. Upload may fail if backend requires auth.');
          }
          
          console.log('Uploading audio to backend...', {
            size: audioBlob.size,
            apiUrl: API_BASE_URL,
            metadata: metadata,
            hasAuthToken: !!authToken
          });
          
          const response = await fetch(`${API_BASE_URL}/api/meetings/upload`, {
            method: 'POST',
            headers: headers,
            body: formData
          });
          
          if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Upload failed: ${response.status} ${response.statusText} - ${errorText}`);
          }
          
          const result = await response.json();
          console.log('✅ Audio uploaded successfully:', result);
          
          // Notify content script if available
          try {
            chrome.tabs.sendMessage(tabId, {
              action: 'uploadComplete',
              meetingId: result.meeting_id
            });
          } catch (e) {
            // Ignore - content script might not be loaded
          }
        } catch (error) {
          console.error('❌ Error uploading audio:', error);
        }
        
        // Clean up
        stream.getTracks().forEach(track => track.stop());
        activeRecordings.delete(tabId);
      };
      
      mediaRecorder.start(1000); // Collect data every second
      
      // Store recording info
      activeRecordings.set(tabId, {
        mediaRecorder,
        stream,
        startTime: recordingStartTime
      });
      
      // Store recording state
      await chrome.storage.local.set({
        [`recording_${tabId}`]: {
          startTime: recordingStartTime,
          isRecording: true
        }
      });
      
      console.log('✅ Recording started successfully');
      safeSendResponse({ success: true });
      
    } catch (error) {
      console.error('TabCapture error:', error);
      
      let errorMessage = 'Failed to capture tab audio.\n\n';
      if (!tab.active) {
        errorMessage += '⚠️ The meeting tab must be ACTIVE (clicked on) for recording to work.\n\n';
      }
      errorMessage += 'Please ensure:\n';
      errorMessage += '1. The meeting tab is active (click on it)\n';
      errorMessage += '2. There is audio playing in the meeting\n';
      errorMessage += '3. You are on a supported platform (Google Meet, Zoom, Teams)\n';
      errorMessage += '4. You have granted tab capture permissions';
      
      safeSendResponse({ 
        success: false, 
        error: errorMessage
      });
      return;
    }

  } catch (error) {
    console.error('Error starting recording:', error);
    safeSendResponse({ success: false, error: error.message || 'Unknown error occurred' });
  }
}

// Note: We no longer use page context injection for recording
// Recording is now done directly in the background script using chrome.tabCapture.capture()

// Helper function to detect platform
function detectPlatform(url) {
  if (url.includes('meet.google.com')) return 'google_meet';
  if (url.includes('zoom.us')) return 'zoom';
  if (url.includes('teams.microsoft.com')) return 'teams';
  return 'unknown';
}

// Stop recording
async function stopRecording(tabId, sendResponse) {
  console.log('🛑 stopRecording called in background script, tabId:', tabId);
  
  let responseSent = false;
  const safeSendResponse = (data) => {
    if (!responseSent) {
      responseSent = true;
      try {
        sendResponse(data);
      } catch (e) {
        console.error('Error sending response:', e);
      }
    }
  };
  
  try {
    if (!tabId) {
      safeSendResponse({ success: false, error: 'No tab ID provided' });
      return;
    }
    
    // Check storage for recording state
    const storage = await chrome.storage.local.get([`recording_${tabId}`]);
    const storedRecording = storage[`recording_${tabId}`];
    console.log('Stored recording state:', storedRecording);
    
    if (!storedRecording || !storedRecording.isRecording) {
      console.warn('⚠️ No active recording found in storage');
      // Still try to stop in content script
    }

    // Stop the MediaRecorder from activeRecordings (if it exists - this is for old approach)
    const recording = activeRecordings.get(tabId);
    if (recording && recording.mediaRecorder && recording.mediaRecorder.state !== 'inactive') {
      console.log('Stopping MediaRecorder in background script (old approach)');
      recording.mediaRecorder.stop();
      console.log('✅ Stopped MediaRecorder in background');
    }

    // IMPORTANT: Send stop message to content script (this is the current approach)
    // The content script has the actual MediaRecorder and will handle the upload
    console.log('Sending stopRecording message to content script...');
    try {
      const contentResponse = await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          reject(new Error('Content script stop timeout'));
        }, 5000);
        
        chrome.tabs.sendMessage(tabId, {
          action: 'stopRecording'
        }, (response) => {
          clearTimeout(timeout);
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
            return;
          }
          resolve(response);
        });
      });
      
      console.log('Content script stopRecording response:', contentResponse);
      
      if (!contentResponse || !contentResponse.success) {
        console.warn('⚠️ Content script stopRecording failed:', contentResponse?.error);
      }
    } catch (contentError) {
      console.error('❌ Error sending stopRecording to content script:', contentError);
      // Continue anyway - the upload might still happen
    }

    // Clear recording state after a delay to allow upload to complete
    setTimeout(async () => {
      await chrome.storage.local.remove([`recording_${tabId}`]);
      console.log('Cleared recording state from storage');
    }, 2000);

    safeSendResponse({ success: true });
  } catch (error) {
    console.error('Error stopping recording:', error);
    safeSendResponse({ success: false, error: error.message });
  }
}

// Get meeting status
async function getMeetingStatus(tabId, sendResponse) {
  let responseSent = false;
  const safeSendResponse = (data) => {
    if (!responseSent) {
      responseSent = true;
      try {
        sendResponse(data);
      } catch (e) {
        console.error('Error sending response:', e);
      }
    }
  };
  
  try {
    if (!tabId) {
      safeSendResponse({ isRecording: false });
      return;
    }
    
    const storage = await chrome.storage.local.get([`recording_${tabId}`]);
    const recording = storage[`recording_${tabId}`];
    
    safeSendResponse({
      isRecording: recording?.isRecording || false,
      startTime: recording?.startTime || null
    });
  } catch (error) {
    console.error('Error getting meeting status:', error);
    safeSendResponse({ isRecording: false });
  }
}

// Upload audio from content script (proxies through background to avoid CORS)
async function uploadAudioFromContentScript(request, sender, sendResponse) {
  let responseSent = false;
  const safeSendResponse = (data) => {
    if (!responseSent) {
      responseSent = true;
      try {
        sendResponse(data);
      } catch (e) {
        console.error('Error sending response:', e);
      }
    }
  };
  
  try {
    // Get tabId from sender if not provided
    const tabId = request.tabId || (sender && sender.tab && sender.tab.id) || null;
    
    console.log('📤 Processing upload request:', {
      hasAudioData: !!request.audioData,
      audioSize: request.audioSize,
      metadata: request.metadata,
      tabId: tabId
    });
    
    // Convert ArrayBuffer back to Blob
    const audioBlob = new Blob([new Uint8Array(request.audioData)], { type: 'audio/webm' });
    console.log('✅ Converted ArrayBuffer to Blob:', {
      size: audioBlob.size,
      type: audioBlob.type
    });
    
    // Create FormData
    const formData = new FormData();
    formData.append('audio', audioBlob, 'meeting_audio.webm');
    formData.append('metadata', JSON.stringify(request.metadata));
    
    // Get auth token from chrome.storage (set by frontend when user logs in)
    const storage = await chrome.storage.local.get(['auth_token']);
    const authToken = storage.auth_token;
    
    const headers = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
      console.log('✅ Using auth token for upload');
    } else {
      console.warn('⚠️ No auth token found in chrome.storage. Upload may fail if backend requires auth.');
    }
    
    console.log('📤 Uploading to backend from background script...', {
      url: `${API_BASE_URL}/api/meetings/upload`,
      audioSize: audioBlob.size,
      hasAuthToken: !!authToken
    });
    
    const response = await fetch(`${API_BASE_URL}/api/meetings/upload`, {
      method: 'POST',
      headers: headers,
      body: formData
    });
    
    console.log('📥 Upload response:', {
      status: response.status,
      statusText: response.statusText,
      ok: response.ok
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Upload failed: ${response.status} ${response.statusText} - ${errorText}`);
    }
    
    const result = await response.json();
    console.log('✅ Upload successful:', result);
    
    safeSendResponse({
      success: true,
      meeting_id: result.meeting_id,
      meeting: result.meeting
    });
    
    // Notify content script of success
    if (tabId) {
      try {
        chrome.tabs.sendMessage(tabId, {
          action: 'uploadSuccess',
          meetingId: result.meeting_id,
          meeting: result.meeting
        });
      } catch (e) {
        console.warn('Could not notify content script:', e);
      }
    }
  } catch (error) {
    console.error('❌ Error uploading audio from background:', error);
    safeSendResponse({
      success: false,
      error: error.message
    });
    
    // Notify content script of failure
    const tabId = request.tabId || (sender && sender.tab && sender.tab.id) || null;
    if (tabId) {
      try {
        chrome.tabs.sendMessage(tabId, {
          action: 'uploadError',
          error: error.message
        });
      } catch (e) {
        console.warn('Could not notify content script:', e);
      }
    }
  }
}

// Upload audio from storage (chunked storage for large files)
async function uploadAudioFromStorage(request, sender, sendResponse) {
  let responseSent = false;
  const safeSendResponse = (data) => {
    if (!responseSent) {
      responseSent = true;
      try {
        sendResponse(data);
      } catch (e) {
        console.error('Error sending response:', e);
      }
    }
  };
  
  try {
    const uploadId = request.uploadId;
    const totalChunks = request.totalChunks;
    const totalSize = request.totalSize;
    const tabId = request.tabId || (sender && sender.tab && sender.tab.id) || null;
    
    console.log('📤 Processing upload from storage:', {
      uploadId: uploadId,
      totalChunks: totalChunks,
      totalSize: totalSize,
      tabId: tabId
    });
    
    // Retrieve metadata
    const storage = await chrome.storage.local.get([`${uploadId}_metadata`]);
    const metadataInfo = storage[`${uploadId}_metadata`];
    
    if (!metadataInfo) {
      throw new Error('Upload metadata not found in storage');
    }
    
    let audioBlob;
    
    // Check if stored in IndexedDB (for large files)
    if (metadataInfo.storageType === 'indexeddb') {
      console.log('📦 Retrieving audio blob from IndexedDB...');
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
      
      // Retrieve the blob
      const transaction = db.transaction([storeName], 'readonly');
      const store = transaction.objectStore(storeName);
      audioBlob = await new Promise((resolve, reject) => {
        const request = store.get(uploadId);
        request.onsuccess = () => {
          if (request.result) {
            resolve(request.result);
          } else {
            reject(new Error('Audio blob not found in IndexedDB'));
          }
        };
        request.onerror = () => reject(request.error);
      });
      
      // Clean up IndexedDB entry (async)
      const deleteTransaction = db.transaction([storeName], 'readwrite');
      const deleteStore = deleteTransaction.objectStore(storeName);
      deleteStore.delete(uploadId).then(() => {
        console.log('🧹 Cleaned up IndexedDB entry');
      }).catch(err => {
        console.warn('⚠️ Failed to clean up IndexedDB entry:', err);
      });
      
      console.log('✅ Retrieved audio blob from IndexedDB:', {
        size: audioBlob.size,
        type: audioBlob.type
      });
    } else {
      // Legacy: Retrieve chunks from chrome.storage
      console.log(`📦 Retrieving ${totalChunks} chunks from chrome.storage...`);
      const chunkKeys = [];
      for (let i = 0; i < totalChunks; i++) {
        chunkKeys.push(`${uploadId}_chunk_${i}`);
      }
      
      const chunksStorage = await chrome.storage.local.get(chunkKeys);
      
      // Reassemble chunks into ArrayBuffer
      const chunks = [];
      for (let i = 0; i < totalChunks; i++) {
        const chunkData = chunksStorage[`${uploadId}_chunk_${i}`];
        if (!chunkData) {
          throw new Error(`Chunk ${i} not found in storage`);
        }
        chunks.push(new Uint8Array(chunkData));
      }
      
      // Combine chunks into single ArrayBuffer
      const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
      const combinedArray = new Uint8Array(totalLength);
      let offset = 0;
      for (const chunk of chunks) {
        combinedArray.set(chunk, offset);
        offset += chunk.length;
      }
      
      // Create Blob from reassembled data
      audioBlob = new Blob([combinedArray], { type: metadataInfo.mimeType || 'audio/webm' });
      console.log('✅ Reassembled audio blob:', {
        size: audioBlob.size,
        type: audioBlob.type,
        expectedSize: totalSize
      });
      
      // Clean up storage chunks (async, don't wait)
      const keysToRemove = [`${uploadId}_metadata`, ...chunkKeys];
      chrome.storage.local.remove(keysToRemove).then(() => {
        console.log('🧹 Cleaned up storage chunks');
      }).catch(err => {
        console.warn('⚠️ Failed to clean up storage chunks:', err);
      });
    }
    
    // Create FormData
    const formData = new FormData();
    formData.append('audio', audioBlob, 'meeting_audio.webm');
    formData.append('metadata', JSON.stringify(metadataInfo.metadata));
    
    // Get auth token from chrome.storage
    const authStorage = await chrome.storage.local.get(['auth_token']);
    const authToken = authStorage.auth_token;
    
    const headers = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
      console.log('✅ Using auth token for upload');
    } else {
      console.warn('⚠️ No auth token found in chrome.storage. Upload may fail if backend requires auth.');
    }
    
    console.log('📤 Uploading to backend from background script...', {
      url: `${API_BASE_URL}/api/meetings/upload`,
      audioSize: audioBlob.size,
      hasAuthToken: !!authToken
    });
    
    const response = await fetch(`${API_BASE_URL}/api/meetings/upload`, {
      method: 'POST',
      headers: headers,
      body: formData
    });
    
    console.log('📥 Upload response:', {
      status: response.status,
      statusText: response.statusText,
      ok: response.ok
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Upload failed: ${response.status} ${response.statusText} - ${errorText}`);
    }
    
    const result = await response.json();
    console.log('✅ Upload successful:', result);
    
    safeSendResponse({
      success: true,
      meeting_id: result.meeting_id,
      meeting: result.meeting
    });
    
    // Notify content script of success
    if (tabId) {
      try {
        chrome.tabs.sendMessage(tabId, {
          action: 'uploadSuccess',
          meetingId: result.meeting_id
        });
      } catch (e) {
        console.warn('Could not notify content script:', e);
      }
    }
  } catch (error) {
    console.error('❌ Error uploading from storage:', error);
    safeSendResponse({
      success: false,
      error: error.message || 'Upload failed'
    });
  }
}

// Upload audio to backend (deprecated - now done directly from page context)
// Keeping for backward compatibility
async function uploadAudio(audioBlob, metadata, sendResponse) {
  let responseSent = false;
  const safeSendResponse = (data) => {
    if (!responseSent) {
      responseSent = true;
      try {
        sendResponse(data);
      } catch (e) {
        console.error('Error sending response:', e);
      }
    }
  };
  
  try {
    if (!audioBlob) {
      safeSendResponse({ success: false, error: 'No audio data provided' });
      return;
    }
    
    // Convert Blob to File-like object for FormData
    const formData = new FormData();
    
    // Create a File from the Blob
    const audioFile = new File([audioBlob], 'meeting_audio.webm', { type: 'audio/webm' });
    formData.append('audio', audioFile);
    formData.append('metadata', JSON.stringify(metadata || {}));

    // Get auth token from chrome.storage
    const storage = await chrome.storage.local.get(['auth_token']);
    const authToken = storage.auth_token;
    
    const headers = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }

    const response = await fetch(`${API_BASE_URL}/api/meetings/upload`, {
      method: 'POST',
      headers: headers,
      body: formData
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Upload failed: ${response.status} ${response.statusText} - ${errorText}`);
    }

    const result = await response.json();
    safeSendResponse({ success: true, data: result });
  } catch (error) {
    console.error('Error uploading audio:', error);
    safeSendResponse({ success: false, error: error.message || 'Upload failed' });
  }
}

// Store active recording sessions (recordingId -> chunks)
const activeRecordingSessions = new Map();

// Start a new recording session
function startRecordingSession(request, sender) {
  const recordingId = request.recordingId;
  const tabId = request.tabId || (sender && sender.tab && sender.tab.id);
  
  activeRecordingSessions.set(recordingId, {
    chunks: [],
    tabId: tabId,
    startTime: Date.now(),
    totalSize: 0
  });
  
  console.log('✅ Recording session started:', recordingId, 'for tab:', tabId);
}

// Handle storing audio chunk from content script
async function storeAudioChunk(request, sender) {
  const recordingId = request.recordingId;
  const chunkIndex = request.chunkIndex;
  const chunkData = request.chunkData; // Array of numbers (Uint8Array converted to array)
  const chunkSize = request.chunkSize;
  
  const session = activeRecordingSessions.get(recordingId);
  if (!session) {
    console.warn('⚠️ Received chunk for unknown recording session:', recordingId);
    return { success: false, error: 'Recording session not found' };
  }
  
  try {
    // Convert array back to Uint8Array, then to Blob
    const uint8Array = new Uint8Array(chunkData);
    const chunkBlob = new Blob([uint8Array], { type: 'audio/webm' });
    
    // Store chunk in extension's IndexedDB
    const dbName = 'MeetingNoteTaker';
    const storeName = 'recordingChunks';
    
    const db = await new Promise((resolve, reject) => {
      const request = indexedDB.open(dbName, 3);
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);
      request.onupgradeneeded = (event) => {
        const db = event.target.result;
        if (!db.objectStoreNames.contains('recordingChunks')) {
          db.createObjectStore('recordingChunks');
        }
        if (!db.objectStoreNames.contains('audioUploads')) {
          db.createObjectStore('audioUploads');
        }
      };
    });
    
    const transaction = db.transaction([storeName], 'readwrite');
    const store = transaction.objectStore(storeName);
    const chunkKey = `${recordingId}_chunk_${chunkIndex}`;
    
    await new Promise((resolve, reject) => {
      const request = store.put(chunkBlob, chunkKey);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
    
    // Update session info
    if (!session.chunks.includes(chunkIndex)) {
      session.chunks.push(chunkIndex);
    }
    session.totalSize += chunkSize;
    
    console.log(`✅ Chunk ${chunkIndex} stored in extension IndexedDB for recording ${recordingId} (${session.chunks.length} chunks, ${session.totalSize} bytes)`);
    
    return { success: true };
  } catch (error) {
    console.error(`❌ Error storing chunk ${chunkIndex}:`, error);
    return { success: false, error: error.message };
  }
}

// Handle streaming audio chunk notification (legacy - for backward compatibility)
async function handleStreamChunk(request, sender) {
  // This is now handled by storeAudioChunk, but keep for compatibility
  console.warn('⚠️ handleStreamChunk called (legacy), redirecting to storeAudioChunk');
  return await storeAudioChunk(request, sender);
}

// Finalize recording and upload
async function finalizeRecording(request, sender, sendResponse) {
  let responseSent = false;
  const safeSendResponse = (data) => {
    if (!responseSent) {
      responseSent = true;
      try {
        sendResponse(data);
      } catch (e) {
        console.error('Error sending response:', e);
      }
    }
  };
  
  try {
    const recordingId = request.recordingId;
    const metadata = request.metadata;
    
    const session = activeRecordingSessions.get(recordingId);
    if (!session) {
      throw new Error('Recording session not found');
    }
    
    console.log(`📦 Finalizing recording ${recordingId}`);
    console.log(`📦 Session info: ${session.chunks.length} chunks tracked, ${session.totalSize} bytes total`);
    
    // Retrieve all chunks from IndexedDB
    const dbName = 'MeetingNoteTaker';
    const storeName = 'recordingChunks';
    
    const db = await new Promise((resolve, reject) => {
      const request = indexedDB.open(dbName, 3);
      request.onerror = () => {
        console.error('❌ IndexedDB open error:', request.error);
        reject(request.error);
      };
      request.onsuccess = () => {
        console.log('✅ IndexedDB opened successfully');
        resolve(request.result);
      };
      request.onupgradeneeded = (event) => {
        const db = event.target.result;
        const oldVersion = event.oldVersion;
        console.log(`📦 IndexedDB upgrade needed: ${oldVersion} -> 3`);
        
        // Create recordingChunks store if it doesn't exist
        if (!db.objectStoreNames.contains('recordingChunks')) {
          db.createObjectStore('recordingChunks');
          console.log('✅ Created recordingChunks object store');
        }
        
        // Create audioUploads store if it doesn't exist (for backward compatibility)
        if (!db.objectStoreNames.contains('audioUploads')) {
          db.createObjectStore('audioUploads');
          console.log('✅ Created audioUploads object store');
        }
      };
    });
    
    // Verify the store exists - if not, try to upgrade the database
    if (!db.objectStoreNames.contains(storeName)) {
      console.warn(`⚠️ Store '${storeName}' not found. Available stores: ${Array.from(db.objectStoreNames).join(', ')}`);
      console.log('🔄 Attempting to upgrade database...');
      
      // Close current connection
      db.close();
      
      // If database exists at version 2 but stores don't exist, we need to increment version
      // to force onupgradeneeded to fire
      const upgradedDb = await new Promise((resolve, reject) => {
        // Try version 3 to force upgrade
        const request = indexedDB.open(dbName, 3);
        request.onerror = () => {
          console.error('❌ IndexedDB upgrade error:', request.error);
          reject(request.error);
        };
        request.onsuccess = () => {
          console.log('✅ IndexedDB upgraded successfully');
          resolve(request.result);
        };
        request.onupgradeneeded = (event) => {
          const db = event.target.result;
          const oldVersion = event.oldVersion;
          console.log(`📦 IndexedDB upgrade triggered: ${oldVersion} -> 3`);
          
          // Create recordingChunks store if it doesn't exist
          if (!db.objectStoreNames.contains('recordingChunks')) {
            db.createObjectStore('recordingChunks');
            console.log('✅ Created recordingChunks object store during upgrade');
          }
          
          // Create audioUploads store if it doesn't exist
          if (!db.objectStoreNames.contains('audioUploads')) {
            db.createObjectStore('audioUploads');
            console.log('✅ Created audioUploads object store during upgrade');
          }
        };
      });
      
      // Verify stores were created
      if (!upgradedDb.objectStoreNames.contains(storeName)) {
        console.error('❌ Stores still missing after upgrade. Available:', Array.from(upgradedDb.objectStoreNames));
        throw new Error(`Object store '${storeName}' does not exist after upgrade. Available stores: ${Array.from(upgradedDb.objectStoreNames).join(', ')}`);
      }
      
      console.log('✅ Store verified after upgrade:', storeName);
      
      // Use the upgraded database to retrieve chunks
      const transaction = upgradedDb.transaction([storeName], 'readonly');
      const store = transaction.objectStore(storeName);
      
      // Retrieve chunks - scan IndexedDB for all chunks with this recordingId
      // Don't rely on session.chunks as notifications might have been missed
      const chunks = [];
      const chunkIndices = new Set();
      
      // First, try to get chunks from session.chunks if available
      if (session.chunks && session.chunks.length > 0) {
        console.log(`📦 Retrieving ${session.chunks.length} chunks from session tracking...`);
        for (const chunkIndex of session.chunks.sort((a, b) => a - b)) {
          const chunkKey = `${recordingId}_chunk_${chunkIndex}`;
          const chunkBlob = await new Promise((resolve, reject) => {
            const request = store.get(chunkKey);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });
          
          if (chunkBlob && chunkBlob.size > 0) {
            chunks.push({ index: chunkIndex, blob: chunkBlob });
            chunkIndices.add(chunkIndex);
          }
        }
      }
      
      // Also scan IndexedDB for any chunks we might have missed
      // This handles cases where notifications were missed due to extension reload
      console.log(`📦 Scanning IndexedDB for additional chunks with prefix: ${recordingId}_chunk_`);
      const allKeys = await new Promise((resolve, reject) => {
        const request = store.getAllKeys();
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      
      // Filter keys for this recording and find missing chunks
      const recordingKeys = allKeys.filter(key => 
        typeof key === 'string' && key.startsWith(`${recordingId}_chunk_`)
      );
      
      console.log(`📦 Found ${recordingKeys.length} total chunk keys in IndexedDB for this recording`);
      
      // Retrieve any chunks we haven't already loaded
      for (const key of recordingKeys) {
        const chunkIndex = parseInt(key.replace(`${recordingId}_chunk_`, ''));
        if (!chunkIndices.has(chunkIndex)) {
          console.log(`📦 Retrieving missed chunk ${chunkIndex}...`);
          const chunkBlob = await new Promise((resolve, reject) => {
            const request = store.get(key);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
          });
          
          if (chunkBlob && chunkBlob.size > 0) {
            chunks.push({ index: chunkIndex, blob: chunkBlob });
            chunkIndices.add(chunkIndex);
          }
        }
      }
      
      // Sort chunks by index to ensure correct order
      chunks.sort((a, b) => a.index - b.index);
      const sortedBlobs = chunks.map(c => c.blob);
      
      console.log(`📦 Retrieved ${sortedBlobs.length} chunks total (indices: ${Array.from(chunkIndices).sort((a, b) => a - b).join(', ')})`);
      
      // Combine chunks into single blob
      if (sortedBlobs.length === 0) {
        throw new Error('No audio chunks found in IndexedDB. Recording may have failed or chunks were not stored.');
      }
      
      const audioBlob = new Blob(sortedBlobs, { type: 'audio/webm' });
      console.log('✅ Reassembled audio blob:', {
        size: audioBlob.size,
        chunks: sortedBlobs.length,
        totalChunks: chunkIndices.size
      });
      
      if (audioBlob.size === 0) {
        throw new Error('Reassembled audio blob is empty. Chunks may be corrupted.');
      }
      
      // Clean up IndexedDB chunks (async) - delete all chunks for this recording
      const deleteTransaction = upgradedDb.transaction([storeName], 'readwrite');
      const deleteStore = deleteTransaction.objectStore(storeName);
      for (const chunkIndex of chunkIndices) {
        const chunkKey = `${recordingId}_chunk_${chunkIndex}`;
        deleteStore.delete(chunkKey);
      }
      console.log(`🧹 Cleaned up ${chunkIndices.size} chunks from IndexedDB`);
      
      // Remove session
      activeRecordingSessions.delete(recordingId);
      
      // Upload to backend
      const formData = new FormData();
      formData.append('audio', audioBlob, 'meeting_audio.webm');
      formData.append('metadata', JSON.stringify(metadata));
      
      // Get auth token
      const authStorage = await chrome.storage.local.get(['auth_token']);
      const authToken = authStorage.auth_token;
      
      const headers = {};
      if (authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
      }
      
      console.log('📤 Uploading finalized recording to backend...', {
        url: `${API_BASE_URL}/api/meetings/upload`,
        audioSize: audioBlob.size
      });
      
      const response = await fetch(`${API_BASE_URL}/api/meetings/upload`, {
        method: 'POST',
        headers: headers,
        body: formData
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Upload failed: ${response.status} ${response.statusText} - ${errorText}`);
      }
      
      const result = await response.json();
      console.log('✅ Upload successful:', result);
      
      safeSendResponse({
        success: true,
        meeting_id: result.meeting_id,
        meeting: result.meeting
      });
      
      // Notify content script
      if (session.tabId) {
        try {
          chrome.tabs.sendMessage(session.tabId, {
            action: 'uploadSuccess',
            meetingId: result.meeting_id
          });
        } catch (e) {
          console.warn('Could not notify content script:', e);
        }
      }
      
      return; // Exit early - we've handled everything with the upgraded database
    }
    
    // Normal path - store exists, use original database
    const transaction = db.transaction([storeName], 'readonly');
    const store = transaction.objectStore(storeName);
    
    // Retrieve chunks - scan IndexedDB for all chunks with this recordingId
    const chunks = [];
    const chunkIndices = new Set();
      
    // First, try to get chunks from session.chunks if available
    if (session.chunks && session.chunks.length > 0) {
      console.log(`📦 Retrieving ${session.chunks.length} chunks from session tracking...`);
      for (const chunkIndex of session.chunks.sort((a, b) => a - b)) {
        const chunkKey = `${recordingId}_chunk_${chunkIndex}`;
        const chunkBlob = await new Promise((resolve, reject) => {
          const request = store.get(chunkKey);
          request.onsuccess = () => resolve(request.result);
          request.onerror = () => reject(request.error);
        });
        
        if (chunkBlob && chunkBlob.size > 0) {
          chunks.push({ index: chunkIndex, blob: chunkBlob });
          chunkIndices.add(chunkIndex);
        }
      }
    }
    
    // Also scan IndexedDB for any chunks we might have missed
    const allKeys = await new Promise((resolve, reject) => {
      const request = store.getAllKeys();
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    
    const recordingKeys = allKeys.filter(key => 
      typeof key === 'string' && key.startsWith(`${recordingId}_chunk_`)
    );
    
    console.log(`📦 Found ${recordingKeys.length} total chunk keys in IndexedDB for this recording`);
    
    // Retrieve any chunks we haven't already loaded
    for (const key of recordingKeys) {
      const chunkIndex = parseInt(key.replace(`${recordingId}_chunk_`, ''));
      if (!chunkIndices.has(chunkIndex)) {
        console.log(`📦 Retrieving missed chunk ${chunkIndex}...`);
        const chunkBlob = await new Promise((resolve, reject) => {
          const request = store.get(key);
          request.onsuccess = () => resolve(request.result);
          request.onerror = () => reject(request.error);
        });
        
        if (chunkBlob && chunkBlob.size > 0) {
          chunks.push({ index: chunkIndex, blob: chunkBlob });
          chunkIndices.add(chunkIndex);
        }
      }
    }
    
    // Sort chunks by index to ensure correct order
    chunks.sort((a, b) => a.index - b.index);
    const sortedBlobs = chunks.map(c => c.blob);
    
    console.log(`📦 Retrieved ${sortedBlobs.length} chunks total (indices: ${Array.from(chunkIndices).sort((a, b) => a - b).join(', ')})`);
    
    // Combine chunks into single blob
    if (sortedBlobs.length === 0) {
      throw new Error('No audio chunks found in IndexedDB. Recording may have failed or chunks were not stored.');
    }
    
    const audioBlob = new Blob(sortedBlobs, { type: 'audio/webm' });
    console.log('✅ Reassembled audio blob:', {
      size: audioBlob.size,
      chunks: sortedBlobs.length,
      totalChunks: chunkIndices.size
    });
    
    if (audioBlob.size === 0) {
      throw new Error('Reassembled audio blob is empty. Chunks may be corrupted.');
    }
    
    // Clean up IndexedDB chunks (async) - delete all chunks for this recording
    const deleteTransaction = db.transaction([storeName], 'readwrite');
    const deleteStore = deleteTransaction.objectStore(storeName);
    for (const chunkIndex of chunkIndices) {
      const chunkKey = `${recordingId}_chunk_${chunkIndex}`;
      deleteStore.delete(chunkKey);
    }
    console.log(`🧹 Cleaned up ${chunkIndices.size} chunks from IndexedDB`);
    
    // Remove session
    activeRecordingSessions.delete(recordingId);
    
    // Upload to backend
    const formData = new FormData();
    formData.append('audio', audioBlob, 'meeting_audio.webm');
    formData.append('metadata', JSON.stringify(metadata));
    
    // Get auth token
    const authStorage = await chrome.storage.local.get(['auth_token']);
    const authToken = authStorage.auth_token;
    
    const headers = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    
    console.log('📤 Uploading finalized recording to backend...', {
      url: `${API_BASE_URL}/api/meetings/upload`,
      audioSize: audioBlob.size
    });
    
    const response = await fetch(`${API_BASE_URL}/api/meetings/upload`, {
      method: 'POST',
      headers: headers,
      body: formData
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Upload failed: ${response.status} ${response.statusText} - ${errorText}`);
    }
    
    const result = await response.json();
    console.log('✅ Upload successful:', result);
    
    safeSendResponse({
      success: true,
      meeting_id: result.meeting_id,
      meeting: result.meeting
    });
    
    // Notify content script
    if (session.tabId) {
      try {
        chrome.tabs.sendMessage(session.tabId, {
          action: 'uploadSuccess',
          meetingId: result.meeting_id
        });
      } catch (e) {
        console.warn('Could not notify content script:', e);
      }
    }
  } catch (error) {
    console.error('❌ Error finalizing recording:', error);
    safeSendResponse({
      success: false,
      error: error.message || 'Finalization failed'
    });
  }
}

// Listen for tab updates to detect meeting platforms
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url) {
    const meetingPlatforms = [
      'meet.google.com',
      'zoom.us',
      'teams.microsoft.com'
    ];
    
    const isMeetingPlatform = meetingPlatforms.some(platform => 
      tab.url.includes(platform)
    );
    
    if (isMeetingPlatform) {
      chrome.action.setBadgeText({ text: '●', tabId: tabId });
      chrome.action.setBadgeBackgroundColor({ color: '#4CAF50' });
    }
  }
});
