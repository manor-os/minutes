# Publishing Meeting Note Taker Browser Extension to Chrome Web Store

## Prerequisites

1. **Chrome Web Store Developer Account**
   - Go to [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole)
   - Sign in with your Google account
   - Pay the one-time $5 registration fee (if not already done)

2. **Prepare Extension Package**
   - Ensure all production URLs are configured
   - Test the extension thoroughly
   - Update version number in `manifest.json`

## Step-by-Step Publishing Process

### 1. Prepare the Extension

1. **Update Version Number**
   ```json
   // In manifest.json
   "version": "1.0.0"  // Increment for each release (e.g., 1.0.1, 1.1.0)
   ```

2. **Verify Production URLs**
   - API URL: `https://minutes.manorai.xyz:8002`
   - Frontend URL: `https://minutes.manorai.xyz`
   - All localhost references should be replaced

3. **Create Extension Package**
   ```bash
   cd browser-extension
   # Create a zip file with all extension files
   zip -r meeting-note-taker-extension.zip . \
     -x "*.git*" \
     -x "*.md" \
     -x "create_icons.py" \
     -x "*.DS_Store"
   ```

### 2. Create Chrome Web Store Listing

1. **Go to Developer Dashboard**
   - Visit: https://chrome.google.com/webstore/devconsole
   - Click "New Item"

2. **Upload Extension Package**
   - Upload the `.zip` file you created
   - Wait for Chrome to process and validate

3. **Fill Out Store Listing**

   **Required Fields:**
   
   - **Name**: `Meeting Note Taker`
   - **Summary** (132 characters max):
     ```
     AI-powered meeting notes for Zoom, Google Meet, and Teams. Automatically transcribe and summarize your meetings.
     ```
   
   - **Description** (up to 16,000 characters):
     ```
     Meeting Note Taker is an AI-powered browser extension that automatically records, transcribes, and summarizes your online meetings.
     
     Features:
     • Record audio from Zoom, Google Meet, Microsoft Teams, and more
     • Automatic transcription using advanced AI
     • Smart meeting summaries with key points and action items
     • View all your meetings in one place
     • Works seamlessly with Manor AI platform
     
     How it works:
     1. Install the extension
     2. Join any meeting (Zoom, Google Meet, Teams)
     3. Click "Start Recording" in the extension popup
     4. The extension captures audio from the meeting
     5. After the meeting, get automatic transcription and AI-generated summary
     
     Privacy & Security:
     • All recordings are processed securely
     • Audio is uploaded to your Manor AI account
     • You have full control over your meeting data
     
     Requirements:
     • Manor AI account (sign up at manorai.xyz)
     • Microphone permissions (for meeting audio)
     
     Supported Platforms:
     • Google Meet
     • Zoom
     • Microsoft Teams
     • And more...
     ```
   
   - **Category**: Productivity
   - **Language**: English (and others if you have translations)

4. **Upload Graphics**

   **Required Images:**
   - **Small tile** (128x128): `icons/icon128.png`
   - **Large tile** (440x280): Create a promotional image
   - **Screenshots** (1280x800 or 640x400):
     - Screenshot 1: Extension popup showing login
     - Screenshot 2: Recording in progress
     - Screenshot 3: Meeting notes view
     - Screenshot 4: Meeting summary example
   
   **Optional:**
   - Promotional images
   - YouTube video link (if available)

5. **Privacy & Permissions**

   **Privacy Policy URL** (Required):
   - Create a privacy policy page
   - Example: `https://minutes.manorai.xyz/privacy-policy`
   - Must explain:
     - What data is collected
     - How data is used
     - Data storage and security
     - User rights

   **Permissions Explanation:**
   - `storage`: Store authentication tokens and user preferences
   - `tabs`: Access current tab to detect meeting platforms
   - `activeTab`: Capture audio from the active meeting tab
   - `scripting`: Inject content scripts for meeting platforms
   - `tabCapture`: Record audio from browser tabs

6. **Pricing & Distribution**

   - **Pricing**: Free
   - **Visibility**: 
     - Public (recommended)
     - Unlisted (for testing)
   - **Regions**: All regions (or select specific ones)

### 3. Submit for Review

1. **Review Checklist**
   - ✅ All URLs point to production
   - ✅ Privacy policy is accessible
   - ✅ Extension works without errors
   - ✅ All required fields filled
   - ✅ Graphics uploaded
   - ✅ Permissions are justified

2. **Submit**
   - Click "Submit for Review"
   - Review typically takes 1-3 business days
   - You'll receive email notifications about status

### 4. Post-Publication

1. **Monitor Reviews**
   - Respond to user feedback
   - Address issues quickly

2. **Update Extension**
   - For updates, upload new zip file
   - Increment version number
   - Update "What's New" section
   - Submit for review (usually faster for updates)

## Important Notes

### Privacy Policy Requirements

You must create a privacy policy that covers:
- Data collection (audio recordings, user info)
- Data usage (transcription, summarization)
- Data storage (where recordings are stored)
- Data sharing (if any)
- User rights (access, deletion)

Example privacy policy structure:
```
https://minutes.manorai.xyz/privacy-policy
```

### Version Management

- Use semantic versioning: `MAJOR.MINOR.PATCH`
- Example: `1.0.0` → `1.0.1` (bug fix) → `1.1.0` (new feature)

### Testing Before Publishing

1. **Load Unpacked Extension**
   - Go to `chrome://extensions/`
   - Enable "Developer mode"
   - Click "Load unpacked"
   - Select the `browser-extension` folder
   - Test all features

2. **Test Production URLs**
   - Verify API calls work
   - Test login flow
   - Test recording functionality
   - Test meeting list view

## Quick Reference

**Chrome Web Store Developer Dashboard:**
https://chrome.google.com/webstore/devconsole

**Extension ID** (after first upload):
- Found in the developer dashboard
- Use for support and updates

**Update Process:**
1. Update code
2. Increment version in manifest.json
3. Create new zip file
4. Upload to Chrome Web Store
5. Submit for review

## Support

For issues or questions:
- Check Chrome Web Store review guidelines
- Review Chrome Extension documentation
- Test thoroughly before submission
