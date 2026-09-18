# Meeting Note Taker - Project Summary

## Overview

A comprehensive AI-powered meeting note taker system that works for both online and offline meetings. The project consists of three main components:

1. **Browser Extension** - Records audio from online video meetings
2. **Phone Recorder** - PWA app for recording offline/in-person meetings  
3. **Backend API** - Processes audio, transcribes, and generates summaries

## Architecture

```
┌─────────────────┐         ┌─────────────────┐
│ Browser         │         │ Phone Recorder  │
│ Extension       │         │ (PWA)           │
└────────┬────────┘         └────────┬────────┘
         │                           │
         │  Upload Audio             │
         │  + Metadata               │
         └───────────┬───────────────┘
                     │
         ┌───────────▼───────────┐
         │   FastAPI Backend      │
         │   - Upload endpoint    │
         │   - Storage            │
         └───────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │   Celery Worker       │
         │   - Async processing   │
         └───────────┬───────────┘
                     │
    ┌────────────────┼────────────────┐
    │                │                │
┌───▼────┐    ┌──────▼──────┐  ┌─────▼─────┐
│ Whisper│    │ GPT-4        │  │ Database  │
│ API    │    │ Summarization│  │ (MySQL)   │
└────────┘    └─────────────┘  └───────────┘
```

## Components

### 1. Browser Extension (`browser-extension/`)

**Technology:** Vanilla JavaScript, Chrome Extension API

**Features:**
- Detects meeting platforms (Zoom, Google Meet, Teams)
- Captures tab audio using Chrome Tab Capture API
- Real-time recording indicator
- Automatic upload to backend
- Popup UI for controls

**Files:**
- `manifest.json` - Extension configuration
- `background.js` - Service worker for audio capture
- `content.js` - Content script for meeting pages
- `popup.html/js` - Extension popup UI

### 2. Phone Recorder (`phone-recorder/`)

**Technology:** React, Vite, PWA

**Features:**
- React-based UI
- PWA support (installable, offline)
- Audio recording from device microphone
- Meeting list view
- Mobile-optimized design

**Files:**
- `src/App.jsx` - Main application
- `src/components/Recorder.jsx` - Recording component
- `src/components/MeetingList.jsx` - Meetings list
- `vite.config.js` - Build configuration

### 3. Backend API (`backend/`)

**Technology:** FastAPI, SQLAlchemy, Celery, OpenAI

**Features:**
- RESTful API for audio upload
- Audio file storage and validation
- OpenAI Whisper transcription
- GPT-4 summarization
- Key points extraction
- Action items extraction
- Async processing with Celery
- Database models for meetings

**Key Files:**
- `api/main.py` - FastAPI application
- `api/routers/meetings.py` - API endpoints
- `api/services/transcription_service.py` - Whisper integration
- `api/services/summarization_service.py` - GPT-4 integration
- `celery_tasks.py` - Async task definitions
- `database/models.py` - SQLAlchemy models

## Data Flow

1. **Recording:**
   - User starts recording (extension or phone app)
   - Audio is captured and stored locally
   - User stops recording

2. **Upload:**
   - Audio file + metadata uploaded to backend
   - Backend saves file and creates meeting record
   - Celery task queued for processing

3. **Processing (Async):**
   - Audio transcribed using Whisper API
   - Transcript summarized using GPT-4
   - Key points extracted
   - Action items identified
   - Results saved to database

4. **Retrieval:**
   - User views meetings list
   - Can access transcript, summary, key points
   - Can download audio files

## API Endpoints

### POST `/api/meetings/upload`
Upload meeting audio file

### GET `/api/meetings/list`
List all meetings (with pagination and filtering)

### GET `/api/meetings/{meeting_id}`
Get meeting details

### GET `/api/meetings/{meeting_id}/transcript`
Get meeting transcript

### GET `/api/meetings/{meeting_id}/summary`
Get meeting summary

### DELETE `/api/meetings/{meeting_id}`
Delete a meeting

## Database Schema

**meetings table:**
- id (VARCHAR, PK)
- title (VARCHAR)
- audio_file (VARCHAR)
- platform (VARCHAR)
- duration (INT)
- status (ENUM: processing, completed, failed)
- transcript (TEXT)
- summary (TEXT)
- key_points (JSON)
- action_items (JSON)
- metadata (JSON)
- created_at (DATETIME)
- updated_at (DATETIME)

## Technology Stack

### Frontend
- **Browser Extension:** Vanilla JavaScript, Chrome Extension API
- **Phone Recorder:** React 18, Vite, PWA

### Backend
- **Framework:** FastAPI
- **Database:** SQLAlchemy (MySQL/PostgreSQL)
- **Task Queue:** Celery + Redis
- **AI Services:** OpenAI (Whisper, GPT-4)
- **Audio Processing:** ffmpeg

### Infrastructure
- **Storage:** Local file system (configurable to S3)
- **Cache:** Redis
- **Deployment:** Docker-ready

## Security Considerations

- API authentication (to be implemented)
- CORS configuration
- File upload validation
- Audio file size limits
- Environment variable management
- HTTPS in production

## Future Enhancements

1. **Authentication & Authorization**
   - User accounts
   - Meeting sharing
   - Access control

2. **Advanced Features**
   - Real-time transcription
   - Speaker identification
   - Meeting search
   - Export to PDF/DOCX
   - Calendar integration

3. **Platform Support**
   - More meeting platforms
   - Mobile apps (iOS/Android)
   - Desktop apps

4. **AI Improvements**
   - Custom prompts
   - Multi-language support
   - Sentiment analysis
   - Topic extraction

5. **Infrastructure**
   - Cloud storage (S3)
   - CDN for audio files
   - Monitoring & logging
   - Auto-scaling

## File Structure

```
meeting-note-taker/
├── browser-extension/      # Chrome/Edge extension
│   ├── manifest.json
│   ├── background.js
│   ├── content.js
│   ├── popup.html/js
│   └── icons/
├── phone-recorder/         # React PWA
│   ├── src/
│   │   ├── components/
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
├── backend/                # FastAPI backend
│   ├── api/
│   │   ├── routers/
│   │   ├── models/
│   │   ├── services/
│   │   └── main.py
│   ├── database/
│   │   ├── models.py
│   │   └── db.py
│   ├── celery_tasks.py
│   ├── requirements.txt
│   └── setup.py
├── README.md
├── QUICKSTART.md
└── INSTALLATION.md
```

## Getting Started

1. **Quick Start:** See `QUICKSTART.md`
2. **Full Installation:** See `INSTALLATION.md`
3. **Documentation:** See `README.md`

## Development Status

✅ Core functionality implemented
✅ Browser extension working
✅ Phone recorder working
✅ Backend API complete
✅ AI integration complete
⏳ Production deployment guide
⏳ Authentication system
⏳ Advanced features

## License

Part of the Manor AI Service ecosystem.

