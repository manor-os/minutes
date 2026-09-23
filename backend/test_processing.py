#!/usr/bin/env python3
"""
Test script to manually process a meeting and check if summary is generated
"""
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from database.db import get_db_session
from database.models import MeetingModel, MeetingStatusEnum
from api.services.transcription_service import TranscriptionService
from api.services.summarization_service import SummarizationService

def test_processing():
    """Test the processing pipeline"""
    db = get_db_session()
    
    try:
        # Get the most recent meeting
        meeting = db.query(MeetingModel).order_by(MeetingModel.created_at.desc()).first()
        
        if not meeting:
            print("❌ No meetings found in database")
            return
        
        print(f"📋 Testing meeting: {meeting.id}")
        print(f"   Title: {meeting.title}")
        print(f"   Status: {meeting.status}")
        print(f"   Audio file: {meeting.audio_file}")
        print(f"   Has transcript: {bool(meeting.transcript)}")
        print(f"   Has summary: {bool(meeting.summary)}")
        print()
        
        # Check if audio file exists
        if not os.path.exists(meeting.audio_file):
            print(f"❌ Audio file not found: {meeting.audio_file}")
            return
        
        # Test transcription
        print("🎤 Testing transcription...")
        transcription_service = TranscriptionService()
        transcript = transcription_service.transcribe(meeting.audio_file)
        print(f"✅ Transcription completed: {len(transcript)} characters")
        print(f"   Preview: {transcript[:100]}...")
        print()
        
        # Test summarization
        print("📝 Testing summarization with DeepSeek...")
        summarization_service = SummarizationService()
        print(f"   Model: {summarization_service.model}")
        print(f"   Base URL: {summarization_service.client.base_url if hasattr(summarization_service.client, 'base_url') else 'default'}")
        
        notes = summarization_service.generate_meeting_notes(transcript)
        print(f"✅ Summarization completed")
        print(f"   Summary: {notes.get('summary', 'N/A')[:200]}...")
        print(f"   Key points: {len(notes.get('key_points', []))}")
        print(f"   Action items: {len(notes.get('action_items', []))}")
        print()
        
        # Update meeting
        print("💾 Updating meeting in database...")
        meeting.transcript = transcript
        meeting.summary = notes.get("summary", "")
        meeting.key_points = notes.get("key_points", [])
        meeting.action_items = notes.get("action_items", [])
        meeting.status = MeetingStatusEnum.COMPLETED
        db.commit()
        print("✅ Meeting updated successfully!")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    test_processing()

