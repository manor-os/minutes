"""
Database models for meetings using SQLAlchemy
"""
from sqlalchemy import Column, String, Integer, Text, DateTime, JSON, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime
import enum
import os

Base = declarative_base()

# Determine JSON type based on database URL
# Use JSONB for PostgreSQL, JSON for MySQL/SQLite
def get_json_column_type():
    """Return appropriate JSON column type for database"""
    database_url = os.getenv("DATABASE_URL", "")
    if "postgresql" in database_url.lower():
        return JSONB
    return JSON


class MeetingStatusEnum(str, enum.Enum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class MeetingModel(Base):
    """SQLAlchemy model for meetings"""
    __tablename__ = "meetings"
    
    id = Column(String(36), primary_key=True)
    title = Column(String(255), nullable=False)
    audio_file = Column(String(500), nullable=False)
    platform = Column(String(50), nullable=False)  # google_meet, zoom, teams, phone_recorder
    duration = Column(Integer, default=0)  # in seconds
    status = Column(String(20), default=MeetingStatusEnum.PROCESSING.value)  # Use String for PostgreSQL compatibility
    transcript = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    key_points = Column(get_json_column_type(), nullable=True)  # List of strings
    action_items = Column(get_json_column_type(), nullable=True)  # List of dicts
    meeting_metadata = Column(get_json_column_type(), nullable=True)  # Renamed from 'metadata' (reserved in SQLAlchemy)
    token_cost = Column(get_json_column_type(), nullable=True)  # Token usage and cost tracking
    entity_id = Column(Integer, nullable=False, index=True)  # Entity ID for multi-tenant isolation
    created_by_user_id = Column(String, nullable=True)  # User ID who recorded the meeting (UUID)
    share_token = Column(String(64), nullable=True, default=None, unique=True)
    tags = Column(String(500), nullable=True, default=None)  # Comma-separated tags
    is_favorite = Column(Boolean, default=False)  # Favorite flag
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)
    
    def to_dict(self, include_user_info=False):
        """Convert model to dictionary
        
        Args:
            include_user_info: If True, includes created_by_user_name and created_by_user_email
        """
        # Handle status - it's stored as string in database
        status_value = self.status
        if hasattr(status_value, 'value'):
            status_value = status_value.value
        elif not isinstance(status_value, str):
            status_value = str(status_value)
        
        result = {
            "id": self.id,
            "title": self.title,
            "audio_file": self.audio_file,
            "platform": self.platform,
            "duration": self.duration,
            "status": status_value,
            "transcript": self.transcript,
            "summary": self.summary,
            "key_points": self.key_points,
            "action_items": self.action_items,
            "metadata": self.meeting_metadata,  # Map to 'metadata' in API response
            "token_cost": self.token_cost,  # Token usage and cost information
            "entity_id": self.entity_id,
            "created_by_user_id": self.created_by_user_id,
            "share_token": self.share_token,
            "tags": [t.strip() for t in self.tags.split(",") if t.strip()] if self.tags else [],
            "is_favorite": bool(self.is_favorite) if self.is_favorite else False,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        
        return result

