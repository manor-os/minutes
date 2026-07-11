# Troubleshooting Browser Extension

## Common Issues and Solutions

### "Failed to start recording: Unknown error"

**Possible causes:**

1. **Content script not loaded**
   - Solution: Refresh the meeting page and try again
   - The extension will try to inject the script automatically

2. **Tab not active or accessible**
   - Solution: Make sure the meeting tab is the active tab
   - Try clicking on the meeting tab before starting recording

3. **TabCapture permission issue**
   - Solution: 
     - Go to `chrome://extensions/`
     - Find "Meeting Note Taker"
     - Click "Details"
     - Ensure "tabCapture" permission is granted
     - Reload the extension

4. **Not on a supported platform**
   - Supported: Google Meet, Zoom, Microsoft Teams
   - Solution: Make sure you're on one of these platforms

5. **Browser compatibility**
   - Works on: Chrome 88+, Edge 88+
   - Solution: Update your browser

### Debugging Steps

1. **Check browser console:**
   - Right-click extension icon → "Inspect popup"
   - Or press F12 on the meeting page
   - Look for error messages

2. **Check extension logs:**
   - Go to `chrome://extensions/`
   - Find "Meeting Note Taker"
   - Click "Service worker" or "background page"
   - Check console for errors

3. **Verify permissions:**
   ```javascript
   // In extension console, check:
   chrome.permissions.getAll((permissions) => {
     console.log('Permissions:', permissions);
   });
   ```

4. **Test tabCapture:**
   ```javascript
   // In extension console:
   chrome.tabs.query({active: true}, (tabs) => {
     chrome.tabCapture.getMediaStreamId({targetTabId: tabs[0].id}, (streamId) => {
       console.log('Stream ID:', streamId);
     });
   });
   ```

### Manual Testing

1. **Test on Google Meet:**
   - Go to https://meet.google.com
   - Start or join a meeting
   - Click extension icon
   - Click "Start Recording"

2. **Test on Zoom:**
   - Go to https://zoom.us
   - Join a meeting
   - Click extension icon
   - Click "Start Recording"

3. **Test on Teams:**
   - Go to https://teams.microsoft.com
   - Join a meeting
   - Click extension icon
   - Click "Start Recording"

### Still Not Working?

1. **Reload the extension:**
   - Go to `chrome://extensions/`
   - Click reload icon on "Meeting Note Taker"

2. **Check backend is running:**
   ```bash
   curl http://localhost:8001/health
   ```

3. **Verify API URL:**
   - Check `background.js` has correct API URL
   - Should be: `http://localhost:8001`

4. **Clear extension storage:**
   - In extension console:
   ```javascript
   chrome.storage.local.clear(() => {
     console.log('Storage cleared');
   });
   ```

### Error Messages

- **"Tab not found"**: Refresh the page and try again
- **"Cannot access tab"**: Make sure the tab is active
- **"Failed to capture tab audio"**: Check tabCapture permission
- **"Could not load recording script"**: Refresh the meeting page
- **"No stream ID provided"**: Extension bug, reload extension

### Getting Help

If issues persist:
1. Check browser console for detailed errors
2. Check extension service worker console
3. Verify all permissions are granted
4. Make sure backend is running
5. Try on a different meeting platform

