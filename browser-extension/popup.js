// Popup script for Meeting Note Taker extension

// === CONFIGURATION ===
// Change these URLs to match your Minutes deployment
const API_BASE_URL = 'http://localhost:8002';
const FRONTEND_URL = 'http://localhost:9002';
// =====================

let currentTabId = null;
let isRecording = false;
let recordingStartTime = null;
let recordingTimer = null;
let lastMeetingId = null;
let isAuthenticated = false;

// Initialize popup
document.addEventListener('DOMContentLoaded', async () => {
  // Set dynamic link for "Or login on the web app"
  const viewMeetingsLink = document.getElementById('viewMeetingsLink');
  if (viewMeetingsLink) viewMeetingsLink.href = FRONTEND_URL;

  // Check authentication first
  await checkAuthentication();
  
  if (!isAuthenticated) {
    showLoginSection();
    setupLoginForm();
    return; // Don't proceed with recording setup if not authenticated
  }
  
  showMainSection();
  
  // Get current tab
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  currentTabId = tab.id;
  
  // Check if on a meeting platform
  const meetingPlatforms = [
    'meet.google.com',
    'zoom.us',
    'teams.microsoft.com'
  ];
  
  const isMeetingPlatform = meetingPlatforms.some(platform => 
    tab.url.includes(platform)
  );
  
  if (isMeetingPlatform) {
    updateMeetingInfo(tab.title, tab.url);
  }
  
  // Check recording status
  checkRecordingStatus();
  
  // Check for latest meeting
  checkForLatestMeeting();
  
  // Set up periodic timer check to ensure it keeps running
  // This helps if the timer interval gets cleared somehow
  setInterval(() => {
    if (isRecording && recordingStartTime) {
      const recordingTimeEl = document.getElementById('recordingTime');
      if (recordingTimeEl && (!recordingTimer || recordingTimeEl.textContent === '00:00')) {
        // Timer might have stopped, restart it
        console.log('Timer check: Restarting timer if needed');
        if (!recordingTimer) {
          startRecordingTimer();
        } else {
          // Just update the display
          const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
          const minutes = Math.floor(elapsed / 60);
          const seconds = elapsed % 60;
          recordingTimeEl.textContent = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        }
      }
    }
  }, 2000); // Check every 2 seconds
  
  // Setup event listeners
  const btnRecord = document.getElementById('btnRecord');
  const btnStop = document.getElementById('btnStop');
  const btnView = document.getElementById('btnView');
  
  if (btnRecord) {
    btnRecord.addEventListener('click', (e) => {
      e.preventDefault();
      console.log('Start recording button clicked');
      startRecording();
    });
  } else {
    console.error('Start recording button not found!');
  }
  
  if (btnStop) {
    btnStop.addEventListener('click', (e) => {
      e.preventDefault();
      console.log('Stop recording button clicked');
      stopRecording();
    });
  }
  
  if (btnView) {
    btnView.addEventListener('click', (e) => {
      e.preventDefault();
      viewNotes();
    });
  }
  
  // Setup logout button
  const btnLogout = document.getElementById('btnLogout');
  if (btnLogout) {
    btnLogout.addEventListener('click', (e) => {
      e.preventDefault();
      handleLogout();
    });
  }
});

// Check authentication
async function checkAuthentication() {
  try {
    const storage = await chrome.storage.local.get(['auth_token']);
    const token = storage.auth_token;
    
    if (!token) {
      isAuthenticated = false;
      return;
    }
    
    // Verify token with backend
    const response = await fetch(`${API_BASE_URL}/api/auth/verify`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });
    
    if (response.ok) {
      const result = await response.json();
      if (result.success && result.valid) {
        isAuthenticated = true;
        return;
      }
    }
    
    // Token invalid, clear it
    await chrome.storage.local.remove(['auth_token', 'entity_id', 'user_email', 'user_name']);
    isAuthenticated = false;
  } catch (error) {
    console.error('Auth check error:', error);
    isAuthenticated = false;
  }
}

// Show login section
function showLoginSection() {
  const loginSection = document.getElementById('loginSection');
  const mainSection = document.getElementById('mainSection');
  
  if (loginSection) loginSection.classList.remove('hidden');
  if (mainSection) mainSection.classList.add('hidden');
}

// Show main section
function showMainSection() {
  const loginSection = document.getElementById('loginSection');
  const mainSection = document.getElementById('mainSection');
  
  if (loginSection) loginSection.classList.add('hidden');
  if (mainSection) mainSection.classList.remove('hidden');
}

// Setup login form
function setupLoginForm() {
  const loginForm = document.getElementById('loginForm');
  const btnLogin = document.getElementById('btnLogin');
  const errorDiv = document.getElementById('errorMessage');
  
  if (!loginForm) return;
  
  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const email = document.getElementById('loginEmail').value.trim();
    const password = document.getElementById('loginPassword').value;
    
    if (!email || !email.includes('@')) {
      showError('Please enter a valid email address');
      return;
    }
    
    if (!password) {
      showError('Please enter your password');
      return;
    }
    
    // Disable button
    if (btnLogin) {
      btnLogin.disabled = true;
      btnLogin.textContent = 'Logging in...';
    }
    
    // Clear error
    if (errorDiv) {
      errorDiv.classList.add('hidden');
      errorDiv.textContent = '';
    }
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password }),
      });
      
      const result = await response.json();
      
      if (result.success && result.token) {
        // Store token in chrome.storage
        await chrome.storage.local.set({
          auth_token: result.token,
          entity_id: result.entity_id,
          user_email: result.email || '',
          user_name: result.name || ''
        });
        
        isAuthenticated = true;
        showMainSection();
        
        // Reload popup to initialize recording features
        window.location.reload();
      } else {
        showError(result.message || 'Login failed. Please check your credentials.');
        if (btnLogin) {
          btnLogin.disabled = false;
          btnLogin.textContent = 'Login';
        }
      }
    } catch (error) {
      console.error('Login error:', error);
      showError('Login failed. Please check your connection and try again.');
      if (btnLogin) {
        btnLogin.disabled = false;
        btnLogin.textContent = 'Login';
      }
    }
  });
}

// Handle logout
async function handleLogout() {
  await chrome.storage.local.remove(['auth_token', 'entity_id', 'user_email', 'user_name']);
  isAuthenticated = false;
  showLoginSection();
  
  // Clear form
  const emailInput = document.getElementById('loginEmail');
  const passwordInput = document.getElementById('loginPassword');
  if (emailInput) emailInput.value = '';
  if (passwordInput) passwordInput.value = '';
}

// Show error message
function showError(message) {
  const errorDiv = document.getElementById('errorMessage');
  if (errorDiv) {
    errorDiv.textContent = message;
    errorDiv.classList.remove('hidden');
    errorDiv.style.display = 'block';
  }
}

// Check recording status
async function checkRecordingStatus() {
  try {
    if (!currentTabId) return;
    
    const response = await new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(
        { action: 'getMeetingStatus', tabId: currentTabId },
        (response) => {
          if (chrome.runtime.lastError) {
            // Ignore errors for status check
            resolve({ isRecording: false });
            return;
          }
          resolve(response);
        }
      );
    });
    
    if (response && response.isRecording) {
      // Restore recording state from storage
      const storage = await chrome.storage.local.get([`recording_${currentTabId}`]);
      const recordingData = storage[`recording_${currentTabId}`];
      
      if (recordingData && recordingData.startTime) {
        recordingStartTime = recordingData.startTime;
        console.log('Restored recording state, startTime:', recordingStartTime);
      }
      
      setRecordingState(true);
    } else {
      setRecordingState(false);
    }
  } catch (error) {
    // Silently fail for status check
    console.error('Error checking status:', error);
  }
}

// Start recording
async function startRecording() {
  console.log('startRecording() called');
  
  // Check authentication first
  if (!isAuthenticated) {
    await checkAuthentication();
    if (!isAuthenticated) {
      const errorDiv = document.getElementById('errorMessage');
      if (errorDiv) {
        errorDiv.textContent = 'Please login first to record meetings.';
        errorDiv.classList.remove('hidden');
        errorDiv.style.display = 'block';
      }
      showLoginSection();
      return;
    }
  }
  
  // Get button reference first
  const btnRecord = document.getElementById('btnRecord');
  const errorDiv = document.getElementById('errorMessage');
  
  // Clear any previous errors
  if (errorDiv) {
    errorDiv.classList.add('hidden');
    errorDiv.style.display = 'none';
    errorDiv.textContent = '';
  }
  
  try {
    // Disable button to prevent double-clicks
    if (btnRecord) {
      btnRecord.disabled = true;
      btnRecord.textContent = 'Starting...';
      // Force button to stay visible during starting
      btnRecord.classList.remove('hidden');
    }
    
    // Get the current active tab
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    
    if (!tab || !tab.id) {
      const errorMsg = 'Error: Could not get current tab. Please refresh the page and try again.';
      console.error(errorMsg);
      if (errorDiv) {
        errorDiv.textContent = errorMsg;
        errorDiv.classList.remove('hidden');
        errorDiv.style.display = 'block';
      }
      if (btnRecord) {
        btnRecord.disabled = false;
        btnRecord.textContent = 'Start Recording';
      }
      return;
    }
    
    console.log('Current tab:', tab.id, tab.url);
    
    // Check if content script is loaded
    try {
      await chrome.tabs.sendMessage(tab.id, { action: 'ping' });
    } catch (e) {
      // Content script not loaded, try to inject it
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ['content.js']
        });
        // Wait a bit for script to initialize
        await new Promise(resolve => setTimeout(resolve, 100));
      } catch (injectError) {
        console.error('Error: Could not load recording script. Please make sure you are on a supported meeting platform (Google Meet, Zoom, or Teams).');
        console.error('Injection error:', injectError);
        return;
      }
    }
    
    // Send start recording message to background using Promise
    // The background script will handle focusing the tab/window
    console.log('Sending startRecording message to background script...');
    console.log('Tab ID:', tab.id);
    
    // First, try to wake up the service worker by clicking the action (this wakes it up)
    console.log('Attempting to wake up service worker...');
    try {
      // Try to get the extension's service worker status
      const serviceWorker = await chrome.runtime.getBackgroundPage();
      console.log('Service worker page:', serviceWorker);
    } catch (e) {
      console.log('getBackgroundPage not available (Manifest V3), using message ping instead');
    }
    
    // Send a ping to wake up the service worker
    console.log('Pinging service worker...');
    try {
      const pingResponse = await new Promise((resolve, reject) => {
        const pingTimeout = setTimeout(() => {
          reject(new Error('Ping timeout - service worker may be inactive'));
        }, 2000); // Shorter timeout
        
        chrome.runtime.sendMessage({ action: 'ping' }, (response) => {
          clearTimeout(pingTimeout);
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
            return;
          }
          resolve(response);
        });
      });
      console.log('✅ Service worker is active:', pingResponse);
    } catch (pingError) {
      console.error('❌ Service worker ping failed:', pingError);
      console.error('❌ The service worker is not responding. This usually means:');
      console.error('   1. The extension needs to be reloaded');
      console.error('   2. There is a syntax error in background.js');
      console.error('   3. The service worker crashed');
      console.error('');
      console.error('Please:');
      console.error('   1. Go to chrome://extensions/');
      console.error('   2. Find "Meeting Note Taker"');
      console.error('   3. Click "Reload" button');
      console.error('   4. Check for any errors shown in red');
      console.error('   5. Click "service worker" link to see console errors');
      
      // Show error to user
      if (errorDiv) {
        errorDiv.textContent = 'Service worker is not responding. Please reload the extension:\n\n1. Go to chrome://extensions/\n2. Find "Meeting Note Taker"\n3. Click "Reload"\n4. Try again';
        errorDiv.classList.remove('hidden');
        errorDiv.style.display = 'block';
      }
      
      // Re-enable button
      if (btnRecord) {
        btnRecord.disabled = false;
        btnRecord.textContent = 'Start Recording';
      }
      
      return; // Don't continue if service worker is not responding
    }
    
    // CRITICAL: Try to get streamId IMMEDIATELY in popup context (while user gesture is active)
    // This invokes activeTab permission while the gesture is still valid
    let streamId = null;
    try {
      console.log('🔧 [POPUP] Attempting to get streamId immediately (while user gesture active)...');
      streamId = await chrome.tabCapture.getMediaStreamId({
        targetTabId: tab.id
      });
      console.log('✅ [POPUP] Got streamId in popup:', streamId);
    } catch (streamIdError) {
      console.warn('⚠️ [POPUP] Could not get streamId in popup:', streamIdError.message);
      // Continue - background script will try to get it
      streamId = null;
    }
    
    // Now send the startRecording message
    console.log('Sending startRecording message with tabId:', tab.id, 'streamId:', streamId ? 'provided' : 'not provided');
    try {
      const response = await new Promise((resolve, reject) => {
        // Set a timeout for the response
        const timeout = setTimeout(() => {
          console.error('❌ Timeout: No response from background script after 15 seconds');
          console.error('❌ The service worker might be inactive or crashed.');
          console.error('❌ Please check:');
          console.error('   1. Go to chrome://extensions/');
          console.error('   2. Find "Meeting Note Taker"');
          console.error('   3. Click "service worker" link to open console');
          console.error('   4. Check for errors');
          reject(new Error('No response from background script. The service worker might be inactive. Try:\n1. Reloading the extension\n2. Closing and reopening the popup\n3. Checking the service worker console for errors'));
        }, 15000); // 15 second timeout
        
        console.log('📤 Sending chrome.runtime.sendMessage with:', { action: 'startRecording', tabId: tab.id, streamId: streamId ? 'provided' : 'not provided' });
        
              chrome.runtime.sendMessage(
                { action: 'startRecording', tabId: tab.id, streamId: streamId },
                (response) => {
            clearTimeout(timeout);
            
            if (chrome.runtime.lastError) {
              console.error('❌ chrome.runtime.lastError:', chrome.runtime.lastError);
              reject(new Error(chrome.runtime.lastError.message));
              return;
            }
            
            console.log('✅ Response from background:', response);
            if (!response) {
              console.warn('⚠️ Response is null/undefined, this might indicate the service worker is inactive');
              reject(new Error('No response received from background script'));
              return;
            }
            resolve(response);
          }
        );
        
        // Log that message was sent
        console.log('📨 Message sent, waiting for response...');
      });
      
      // Get error div reference
      const errorDiv = document.getElementById('errorMessage');
      
      if (response && response.success) {
        console.log('✅ Recording started successfully, updating UI...');
        
        // Clear any previous errors
        if (errorDiv) {
          errorDiv.classList.add('hidden');
          errorDiv.textContent = '';
          errorDiv.style.display = 'none';
        }
        
        // Set recording start time FIRST
        recordingStartTime = Date.now();
        console.log('Recording start time set:', recordingStartTime, new Date(recordingStartTime).toISOString());
        
        // Store start time in chrome.storage for persistence
        if (currentTabId) {
          await chrome.storage.local.set({
            [`recording_${currentTabId}`]: {
              startTime: recordingStartTime,
              isRecording: true
            }
          });
          console.log('Stored recording start time in chrome.storage for tab:', currentTabId);
        }
        
        // Update UI state IMMEDIATELY - this will hide start button and show stop button
        console.log('🔄 Calling setRecordingState(true) to update UI...');
        setRecordingState(true);
        
        // Force UI update by checking elements
        const statusRecording = document.getElementById('statusRecording');
        const btnRecord = document.getElementById('btnRecord');
        const btnStop = document.getElementById('btnStop');
        const recordingTime = document.getElementById('recordingTime');
        
        console.log('UI elements after setRecordingState:', {
          statusRecording: statusRecording ? (statusRecording.classList.contains('hidden') ? 'HIDDEN' : 'VISIBLE') : 'NOT FOUND',
          btnRecord: btnRecord ? (btnRecord.classList.contains('hidden') ? 'HIDDEN' : 'VISIBLE') : 'NOT FOUND',
          btnStop: btnStop ? (btnStop.classList.contains('hidden') ? 'HIDDEN' : 'VISIBLE') : 'NOT FOUND',
          recordingTime: recordingTime ? recordingTime.textContent : 'NOT FOUND'
        });
        
        // Start timer immediately
        if (recordingStartTime) {
          startRecordingTimer();
          console.log('Timer started immediately');
        }
        
        console.log('✅ UI updated, recording active');
      } else {
        // Show error message
        const errorMsg = response?.error || 'Unknown error occurred';
        console.error('Recording failed:', errorMsg);
        
        // Show error in popup - make absolutely sure it's visible
        if (errorDiv) {
          errorDiv.textContent = errorMsg;
          errorDiv.classList.remove('hidden');
          errorDiv.style.display = 'block'; // Force display
          // Scroll error into view
          setTimeout(() => {
            errorDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          }, 100);
          console.log('Error displayed:', errorMsg);
        } else {
          // Fallback to alert if error div not found
          console.error('Error div not found, using alert');
          alert('Failed to start recording:\n\n' + errorMsg);
        }
        
        // Re-enable button
        const btnRecord = document.getElementById('btnRecord');
        if (btnRecord) {
          btnRecord.disabled = false;
          btnRecord.textContent = 'Start Recording';
        }
        
        // Make sure error is visible
        console.log('Error should be visible in popup');
      }
    } catch (error) {
      console.error('Error sending message:', error);
      
      // Show error in popup
      const errorDiv = document.getElementById('errorMessage');
      const errorMsg = 'Error: ' + error.message;
      
      if (errorDiv) {
        errorDiv.textContent = errorMsg;
        errorDiv.classList.remove('hidden');
        errorDiv.style.display = 'block'; // Force display
      } else {
        alert(errorMsg);
      }
      
      // Re-enable button
      const btnRecord = document.getElementById('btnRecord');
      if (btnRecord) {
        btnRecord.disabled = false;
        btnRecord.textContent = 'Start Recording';
      }
    }
  } catch (error) {
    console.error('Error starting recording:', error);
    
    // Show error in popup
    const errorDiv = document.getElementById('errorMessage');
    const errorMsg = 'Error: ' + error.message;
    
    if (errorDiv) {
      errorDiv.textContent = errorMsg;
      errorDiv.classList.remove('hidden');
    } else {
      alert(errorMsg);
    }
    
    // Re-enable button
    const btnRecord = document.getElementById('btnRecord');
    if (btnRecord) {
      btnRecord.disabled = false;
      btnRecord.textContent = 'Start Recording';
    }
  }
}

// Stop recording
async function stopRecording() {
  console.log('stopRecording() called');
  
  const btnStop = document.getElementById('btnStop');
  if (btnStop) {
    btnStop.disabled = true;
    btnStop.textContent = 'Stopping...';
  }
  
  try {
    // Get current tab
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const tabId = tab?.id || currentTabId;
    
    console.log('Stopping recording for tab:', tabId);
    
    if (!tabId) {
      const errorMsg = 'Error: Could not get current tab.';
      console.error(errorMsg);
      alert(errorMsg);
      if (btnStop) {
        btnStop.disabled = false;
        btnStop.textContent = 'Stop Recording';
      }
      return;
    }
    
    // Send stop recording message using Promise
    try {
      const response = await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          reject(new Error('No response from background script when stopping recording'));
        }, 10000);
        
        chrome.runtime.sendMessage(
          { action: 'stopRecording', tabId: tabId },
          (response) => {
            clearTimeout(timeout);
            
            if (chrome.runtime.lastError) {
              console.error('chrome.runtime.lastError:', chrome.runtime.lastError);
              reject(new Error(chrome.runtime.lastError.message));
              return;
            }
            
            console.log('Stop recording response:', response);
            resolve(response);
          }
        );
      });
      
      if (response && response.success) {
        console.log('✅ Recording stopped successfully');
        stopRecordingTimer();
        setRecordingState(false);
        
        // Wait a moment for upload to complete, then get meeting ID
        setTimeout(async () => {
          await checkForNewMeeting();
        }, 2000);
        
        alert('Recording stopped. Processing will begin shortly. Check "View Notes" to see your meeting.');
      } else {
        const errorMsg = 'Failed to stop recording: ' + (response?.error || 'Unknown error');
        console.error('❌', errorMsg);
        alert(errorMsg);
        // Still update UI even if there was an error
        setRecordingState(false);
      }
    } catch (error) {
      console.error('❌ Error sending stop message:', error);
      alert('Error stopping recording: ' + error.message);
      // Still update UI even if there was an error
      setRecordingState(false);
    }
  } catch (error) {
    console.error('❌ Error stopping recording:', error);
    alert('Error: ' + error.message);
    // Still update UI even if there was an error
    setRecordingState(false);
  } finally {
    // Always re-enable button
    if (btnStop) {
      btnStop.disabled = false;
      btnStop.textContent = 'Stop Recording';
    }
  }
}

// Set recording state UI
function setRecordingState(recording) {
  isRecording = recording;
  console.log('🔄 setRecordingState called:', recording, 'recordingStartTime:', recordingStartTime);
  
  const statusIdle = document.getElementById('statusIdle');
  const statusRecording = document.getElementById('statusRecording');
  const status = document.getElementById('status');
  const btnRecord = document.getElementById('btnRecord');
  const btnStop = document.getElementById('btnStop');
  const recordingTime = document.getElementById('recordingTime');
  
  console.log('UI elements found:', {
    statusIdle: !!statusIdle,
    statusRecording: !!statusRecording,
    status: !!status,
    btnRecord: !!btnRecord,
    btnStop: !!btnStop,
    recordingTime: !!recordingTime
  });
  
    if (recording) {
      console.log('✅ Showing recording UI');
      
      // Hide idle status, show recording status
      if (statusIdle) {
        statusIdle.classList.add('hidden');
        statusIdle.style.display = 'none';
        console.log('Hidden statusIdle');
      }
      if (statusRecording) {
        statusRecording.classList.remove('hidden');
        statusRecording.style.display = 'flex'; // Force display
        console.log('Shown statusRecording');
      }
      if (status) {
        status.classList.add('recording');
        console.log('Added recording class to status');
      }
      
      // Hide start button, show stop button
      if (btnRecord) {
        btnRecord.classList.add('hidden');
        btnRecord.style.display = 'none'; // Force hide
        btnRecord.disabled = false; // Make sure it's enabled for next time
        btnRecord.textContent = 'Start Recording'; // Reset text
        console.log('Hidden btnRecord');
      }
      if (btnStop) {
        btnStop.classList.remove('hidden');
        btnStop.style.display = 'block'; // Force show
        btnStop.disabled = false; // Make sure stop button is enabled
        console.log('Shown btnStop, display:', btnStop.style.display);
      }
      
      // Initialize recording time display
      if (recordingTime) {
        recordingTime.style.display = 'block'; // Force show
        // If we have a start time, calculate and show elapsed time immediately
        if (recordingStartTime) {
          const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
          const minutes = Math.floor(elapsed / 60);
          const seconds = elapsed % 60;
          const timeString = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
          recordingTime.textContent = timeString;
          console.log('Initialized recordingTime with elapsed time:', timeString);
        } else {
          recordingTime.textContent = '00:00';
          console.log('Initialized recordingTime to 00:00 (no start time yet)');
        }
      } else {
        console.error('❌ recordingTime element not found!');
      }
      
      // Start timer if we have a start time and timer isn't already running
      if (recordingStartTime && !recordingTimer) {
        console.log('Starting timer from setRecordingState');
        setTimeout(() => {
          startRecordingTimer();
        }, 50);
      }
  } else {
    console.log('Showing idle UI');
    // Show idle status, hide recording status
    if (statusIdle) statusIdle.classList.remove('hidden');
    if (statusRecording) statusRecording.classList.add('hidden');
    if (status) status.classList.remove('recording');
    
    // Show start button, hide stop button
    if (btnRecord) {
      btnRecord.classList.remove('hidden');
      btnRecord.disabled = false;
      btnRecord.textContent = 'Start Recording';
    }
    if (btnStop) {
      btnStop.classList.add('hidden');
      btnStop.disabled = false;
    }
    
    // Stop timer when recording stops
    stopRecordingTimer();
  }
}

// Start recording timer
function startRecordingTimer() {
  console.log('⏱️ startRecordingTimer called, recordingStartTime:', recordingStartTime);
  
  // Clear any existing timer
  if (recordingTimer) {
    clearInterval(recordingTimer);
    recordingTimer = null;
    console.log('Cleared existing timer');
  }
  
  // Validate we have a start time
  if (!recordingStartTime) {
    console.error('❌ No recordingStartTime set, cannot start timer');
    return;
  }
  
  // Get the recording time element
  const recordingTimeEl = document.getElementById('recordingTime');
  if (!recordingTimeEl) {
    console.error('❌ recordingTime element not found!');
    // Try to find it again after a short delay
    setTimeout(() => {
      const retryEl = document.getElementById('recordingTime');
      if (retryEl && recordingStartTime) {
        console.log('Found recordingTime element on retry');
        startRecordingTimer();
      } else {
        console.error('Still cannot find recordingTime element or no start time');
      }
    }, 200);
    return;
  }
  
  console.log('Found recordingTime element:', recordingTimeEl);
  
  // Update function
  const updateTimer = () => {
    if (!recordingStartTime) {
      console.warn('No recordingStartTime in updateTimer, stopping');
      stopRecordingTimer();
      return;
    }
    
    const now = Date.now();
    const elapsed = Math.floor((now - recordingStartTime) / 1000);
    
    if (elapsed < 0) {
      console.warn('Negative elapsed time, resetting');
      recordingTimeEl.textContent = '00:00';
      return;
    }
    
    const minutes = Math.floor(elapsed / 60);
    const seconds = elapsed % 60;
    const timeString = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    
    if (recordingTimeEl) {
      recordingTimeEl.textContent = timeString;
      // Only log every 10 seconds to reduce console spam
      if (elapsed % 10 === 0) {
        console.log('Timer updated:', timeString, `(${elapsed}s elapsed)`);
      }
    }
  };
  
  // Update immediately
  updateTimer();
  
  // Set up interval to update every second
  recordingTimer = setInterval(updateTimer, 1000);
  
  console.log('✅ Timer started, interval ID:', recordingTimer, 'will update every second');
}

// Stop recording timer
function stopRecordingTimer() {
  if (recordingTimer) {
    clearInterval(recordingTimer);
    recordingTimer = null;
  }
  recordingStartTime = null;
  document.getElementById('recordingTime').textContent = '00:00';
}

// Check for new meeting after recording
async function checkForNewMeeting() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/meetings/list?limit=1`);
    if (!response.ok) return;
    
    const data = await response.json();
    if (data.success && data.meetings && data.meetings.length > 0) {
      const latestMeeting = data.meetings[0];
      lastMeetingId = latestMeeting.id;
      showMeetingLink(latestMeeting.id);
    }
  } catch (error) {
    console.error('Error checking for meeting:', error);
  }
}

// Show meeting link
function showMeetingLink(meetingId) {
  const linkDiv = document.getElementById('meetingLink');
  const link = document.getElementById('viewMeetingLink');
  
  link.href = `${FRONTEND_URL}?meeting=${meetingId}`;
  linkDiv.classList.remove('hidden');
  
  // Update meeting info
  document.getElementById('meetingInfo').textContent = 'Recording uploaded! Click link to view.';
}

// Check for meeting on load
async function checkForLatestMeeting() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/meetings/list?limit=1`);
    if (!response.ok) return;
    
    const data = await response.json();
    if (data.success && data.meetings && data.meetings.length > 0) {
      const latestMeeting = data.meetings[0];
      lastMeetingId = latestMeeting.id;
      
      // Show link if meeting exists
      if (latestMeeting.status === 'completed' || latestMeeting.status === 'processing') {
        showMeetingLink(latestMeeting.id);
      }
    }
  } catch (error) {
    console.error('Error checking for meeting:', error);
  }
}

// Update meeting info
function updateMeetingInfo(title, url) {
  const info = document.getElementById('meetingInfo');
  const platform = detectPlatform(url);
  info.textContent = `${platform}: ${title}`;
}

// Detect platform
function detectPlatform(url) {
  if (url.includes('meet.google.com')) return 'Google Meet';
  if (url.includes('zoom.us')) return 'Zoom';
  if (url.includes('teams.microsoft.com')) return 'Microsoft Teams';
  return 'Unknown';
}

// View notes
function viewNotes() {
  const url = lastMeetingId 
    ? `${FRONTEND_URL}?meeting=${lastMeetingId}`
    : FRONTEND_URL;
  
  chrome.tabs.create({
    url: url
  });
}

