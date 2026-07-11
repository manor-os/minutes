# Tab Capture Error Fix

## Error: "AbortError: Error starting tab capture"

This error occurs when the browser extension cannot capture audio from the tab. Here are the fixes:

### Common Causes and Solutions

1. **Tab not active**
   - Solution: Click on the meeting tab before starting recording
   - The tab must be the active/focused tab

2. **No audio playing**
   - Solution: Make sure there's audio in the meeting (someone speaking, music, etc.)
   - Tab capture requires active audio stream

3. **Permission issues**
   - Solution: 
     - Go to `chrome://extensions/`
     - Find "Meeting Note Taker"
     - Click "Details"
     - Ensure all permissions are granted
     - Reload the extension

4. **Unsupported platform**
   - Solution: Make sure you're on:
     - Google Meet (meet.google.com)
     - Zoom (zoom.us)
     - Microsoft Teams (teams.microsoft.com)

5. **Extension not reloaded**
   - Solution: Reload the extension after code changes

### Testing Steps

1. **Open a meeting tab**
   - Go to Google Meet, Zoom, or Teams
   - Join a meeting with audio

2. **Make tab active**
   - Click on the meeting tab
   - Ensure it's the focused window

3. **Start audio**
   - Make sure there's audio playing (speak, play music, etc.)

4. **Start recording**
   - Click extension icon
   - Click "Start Recording"
   - Should see recording indicator

### Alternative: Use Phone Recorder

If tab capture continues to fail, use the phone recorder app:
- Open http://localhost:3001
- Use the phone recorder to capture audio directly from your microphone
- This works for any meeting (online or offline)

### Debugging

1. **Check browser console**
   - Press F12 on the meeting page
   - Look for errors in Console tab

2. **Check extension console**
   - Go to `chrome://extensions/`
   - Find "Meeting Note Taker"
   - Click "Service worker" or "background page"
   - Check console for errors

3. **Test tab capture manually**
   ```javascript
   // In extension console:
   chrome.tabs.query({active: true}, (tabs) => {
     chrome.tabCapture.getMediaStreamId({targetTabId: tabs[0].id}, (streamId) => {
       console.log('Stream ID:', streamId);
     });
   });
   ```

### Known Limitations

- Tab capture only works when tab is active
- Requires audio to be playing in the tab
- Some browsers/contexts may have restrictions
- HTTPS required for getUserMedia

### Workaround

If tab capture doesn't work:
1. Use the phone recorder app instead
2. Or use screen recording software
3. Or use the meeting platform's built-in recording feature

