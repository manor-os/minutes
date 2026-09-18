// Content script to sync auth token from page localStorage to chrome.storage
// This runs on localhost:3001 to sync the token for the extension

(function() {
  'use strict';
  
  // Check if this page is a Minutes instance by looking for the auth token in localStorage
  const hasMinutesToken = !!localStorage.getItem('auth_token');
  if (!hasMinutesToken) {
    return;
  }
  
  console.log('🔐 [AUTH SYNC] Content script loaded on meeting note taker page');
  
  // Function to sync token from localStorage to chrome.storage
  function syncAuthToken() {
    try {
      const token = localStorage.getItem('auth_token');
      const entityId = localStorage.getItem('entity_id');
      const userEmail = localStorage.getItem('user_email');
      const userName = localStorage.getItem('user_name');
      
      if (token && typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
        chrome.storage.local.set({
          auth_token: token,
          entity_id: entityId,
          user_email: userEmail,
          user_name: userName
        }).then(() => {
          console.log('✅ [AUTH SYNC] Token synced to chrome.storage');
        }).catch((err) => {
          console.warn('⚠️ [AUTH SYNC] Could not sync token:', err);
        });
      }
    } catch (error) {
      console.warn('⚠️ [AUTH SYNC] Error syncing token:', error);
    }
  }
  
  // Sync immediately
  syncAuthToken();
  
  // Listen for storage changes (when user logs in/out)
  window.addEventListener('storage', (e) => {
    if (e.key === 'auth_token') {
      console.log('🔐 [AUTH SYNC] Auth token changed in localStorage, syncing...');
      syncAuthToken();
    }
  });
  
  // Also sync periodically (in case storage event doesn't fire)
  setInterval(() => {
    syncAuthToken();
  }, 5000); // Check every 5 seconds
  
  // Override localStorage.setItem to sync when token is set
  const originalSetItem = localStorage.setItem;
  localStorage.setItem = function(key, value) {
    originalSetItem.apply(this, arguments);
    if (key === 'auth_token') {
      console.log('🔐 [AUTH SYNC] Auth token set, syncing...');
      setTimeout(syncAuthToken, 100); // Small delay to ensure value is set
    }
  };
})();

