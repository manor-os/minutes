# Meeting Note Taker - Browser Extension

Chrome/Edge browser extension for recording online meetings and generating AI-powered notes.

## Features

- Record audio from online meetings (Zoom, Google Meet, Teams)
- Automatic platform detection
- Real-time recording indicator
- Automatic upload and processing
- View meeting notes

## Installation

1. Open Chrome/Edge and navigate to `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select this directory

## Usage

1. Join a meeting on a supported platform
2. Click the extension icon
3. Click "Start Recording"
4. Click "Stop Recording" when done
5. View notes in the web app

## Supported Platforms

- Google Meet
- Zoom
- Microsoft Teams

## Configuration

Update the API URL in `background.js` and `popup.js`:
```javascript
const API_BASE_URL = 'http://localhost:8000';
```

## Permissions

The extension requires:
- `tabs`: To detect meeting platforms
- `tabCapture`: To capture audio from tabs
- `storage`: To save recording state
- `scripting`: To inject content scripts

## Development

1. Make changes to the extension files
2. Reload the extension in `chrome://extensions/`
3. Test on a meeting platform

## Building for Production

1. Create icon files (16x16, 48x48, 128x128 PNG)
2. Update `manifest.json` version
3. Package the extension
4. Submit to Chrome Web Store or Edge Add-ons

