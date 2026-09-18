# Meeting Note Taker - Phone Recorder

Progressive Web App (PWA) for recording offline/in-person meetings and generating AI-powered notes.

## Features

- Record audio from phone or device microphone
- Add meeting title and notes
- View all recorded meetings
- Automatic transcription and summarization
- Works offline (PWA)

## Installation

### Development

```bash
npm install
npm run dev
```

### Production

```bash
npm run build
npm run preview
```

## Usage

1. Open the app in your browser
2. Grant microphone permissions
3. Optionally add meeting title and notes
4. Click "Start Recording"
5. Hold device near meeting participants
6. Click "Stop Recording" when done
7. View meetings in "My Meetings" tab

## Configuration

Update the API URL in `src/App.jsx`:
```javascript
const API_BASE_URL = 'http://localhost:8002';
```

## PWA Features

- Installable on mobile devices
- Works offline
- Service worker for caching
- Mobile-optimized UI

## Browser Support

- Chrome/Edge (recommended)
- Firefox
- Safari (iOS 11.3+)

## Development

1. Make changes to source files
2. Hot reload is enabled in development
3. Test on mobile devices for best experience

## Building

```bash
npm run build
```

Output will be in the `dist/` directory.

