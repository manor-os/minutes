---
sidebar_position: 1
title: Recording & Transcription
---

# Recording & Transcription

## Live Recording

Click **Start Recording** to capture audio from your microphone. A real-time transcript appears as you speak, with word-by-word streaming.

When you stop recording, the audio is uploaded and processed:
1. Transcription (Whisper or faster-whisper)
2. Speaker diarization (identifies different speakers)
3. AI summarization (summary, key points, action items)

## Upload Pre-Recorded Audio

Switch to the **Upload** tab to drag-and-drop or browse for an existing audio file.

Supported formats: MP3, WAV, M4A, WebM, OGG, FLAC, MP4 (up to 500MB).

## Speaker Diarization

Minutes identifies different speakers in the audio:

- **With pyannote-audio** (best quality) — requires `HF_TOKEN` and `pyannote-audio` package
- **Pause-based fallback** (built-in) — detects speaker changes from pauses in speech

## Languages

20+ languages supported for transcription. Set the language in **Settings** or let Whisper auto-detect.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `R` | Start recording |
| `S` | Stop recording |
| `1` | Switch to Recorder view |
| `2` | Switch to Meetings view |
