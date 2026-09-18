# Testing Guide - Meeting Note Taker

## 🧪 Quick Test Checklist

### 1. Backend API Tests

```bash
# Health check
curl http://localhost:8001/health

# Root endpoint
curl http://localhost:8001/

# List meetings (should return empty array initially)
curl http://localhost:8001/api/meetings/list
```

Expected responses:
- Health: `{"status":"healthy","service":"meeting-note-taker"}`
- Root: `{"message":"Meeting Note Taker API","version":"1.0.0","status":"running"}`
- List: `{"success":true,"meetings":[],"total":0}`

### 2. Browser Extension Test

**Setup:**
1. Load extension in Chrome/Edge (see main README)
2. Open a meeting on Google Meet, Zoom, or Teams

**Test Steps:**
1. Click extension icon
2. Verify it shows "Ready to record"
3. Click "Start Recording"
4. Speak for 10-15 seconds
5. Click "Stop Recording"
6. Check backend logs: `docker-compose logs -f backend`

**Expected Behavior:**
- Recording indicator appears on page
- Extension popup shows "Recording..."
- After stopping, audio uploads to backend
- Backend processes the audio (check logs)

### 3. Phone Recorder Test

1. Open http://localhost:3001
2. Grant microphone permissions
3. Add optional meeting title
4. Click "Start Recording"
5. Speak for 10-15 seconds
6. Click "Stop Recording"
7. Check "My Meetings" tab

**Expected Behavior:**
- Recording starts and shows timer
- After stopping, uploads to backend
- Meeting appears in list (status: processing)
- After processing, shows summary and transcript

### 4. Database Verification

```bash
# Connect to database
docker-compose exec postgres psql -U meeting_user -d meeting_notes

# Check tables
\dt

# View meetings
SELECT id, title, platform, status, created_at FROM meetings;

# Exit
\q
```

### 5. Celery Worker Test

```bash
# Check Celery is processing tasks
docker-compose logs celery-worker | grep -i "task\|processing\|completed"

# Should see task processing messages when audio is uploaded
```

### 6. DeepSeek API Test

```bash
# Test DeepSeek connection (from backend container)
docker-compose exec backend python -c "
from api.services.summarization_service import SummarizationService
service = SummarizationService()
print('Model:', service.model)
print('Base URL:', service.client.base_url if hasattr(service.client, 'base_url') else 'OpenAI default')
"
```

Expected: Should show `deepseek-chat` and `https://api.deepseek.com`

### 7. End-to-End Test

**Complete workflow:**
1. Record a meeting (extension or phone recorder)
2. Upload audio
3. Wait for processing (check Celery logs)
4. Retrieve meeting details
5. Verify transcript and summary

```bash
# After recording, get meeting ID from logs or database
MEETING_ID="your-meeting-id-here"

# Get meeting details
curl http://localhost:8001/api/meetings/$MEETING_ID

# Get transcript
curl http://localhost:8001/api/meetings/$MEETING_ID/transcript

# Get summary
curl http://localhost:8001/api/meetings/$MEETING_ID/summary
```

## 🐛 Troubleshooting

### Backend not responding
```bash
docker-compose logs backend
docker-compose restart backend
```

### Celery not processing
```bash
docker-compose logs celery-worker
docker-compose restart celery-worker
```

### Database connection errors
```bash
# Check PostgreSQL is healthy
docker-compose ps postgres

# Check connection
docker-compose exec postgres pg_isready -U meeting_user
```

### Extension not recording
- Check browser console (F12)
- Verify microphone permissions
- Check API URL in extension files
- Verify backend is accessible from browser

### Audio not processing
- Check Celery worker logs
- Verify DeepSeek API key is correct
- Check backend logs for errors
- Verify audio file was uploaded

## 📊 Monitoring

### View all logs
```bash
docker-compose logs -f
```

### View specific service
```bash
docker-compose logs -f backend
docker-compose logs -f celery-worker
docker-compose logs -f postgres
```

### Check service status
```bash
docker-compose ps
```

### Resource usage
```bash
docker stats
```

## ✅ Success Criteria

- [ ] Backend API responds to health check
- [ ] Database connection works
- [ ] Celery worker is running
- [ ] Browser extension loads and shows UI
- [ ] Extension can start/stop recording
- [ ] Audio uploads successfully
- [ ] Celery processes the audio
- [ ] Transcript is generated
- [ ] Summary is generated using DeepSeek
- [ ] Meeting appears in list with all data

## 🎯 Performance Tests

### Test with different audio lengths
- Short: 10 seconds
- Medium: 2 minutes
- Long: 10 minutes

### Test with different platforms
- Google Meet
- Zoom
- Microsoft Teams
- Phone recorder

### Test concurrent recordings
- Multiple recordings at once
- Check Celery handles queue properly

## 📝 Test Results Template

```
Date: [Date]
Tester: [Name]

Backend API: ✅ / ❌
Database: ✅ / ❌
Celery Worker: ✅ / ❌
Browser Extension: ✅ / ❌
Phone Recorder: ✅ / ❌
DeepSeek Integration: ✅ / ❌
End-to-End Test: ✅ / ❌

Notes:
[Any issues or observations]
```

