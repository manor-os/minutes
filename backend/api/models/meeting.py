"""
Meeting data models
"""
from enum import Enum
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, field_validator


class MeetingStatus(str, Enum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Meeting(BaseModel):
    """Meeting model"""
    id: Optional[str] = None
    title: str
    audio_file: str
    platform: str  # google_meet, zoom, teams, phone_recorder
    duration: int  # in seconds
    status: MeetingStatus
    transcript: Optional[str] = None
    summary: Optional[str] = None
    key_points: Optional[List[str]] = None
    action_items: Optional[List[Dict[str, Any]]] = None
    meeting_metadata: Optional[Dict[str, Any]] = None
    token_cost: Optional[Dict[str, Any]] = None
    entity_id: Optional[str] = None  # Entity ID for multi-tenant isolation
    created_by_user_id: Optional[str] = None  # User ID who recorded the meeting

    @field_validator("entity_id", mode="before")
    @classmethod
    def coerce_entity_id_to_str(cls, v):
        if v is None:
            return v
        return str(v)
    created_by_user_name: Optional[str] = None  # Name of user who recorded the meeting
    created_by_user_email: Optional[str] = None  # Email of user who recorded the meeting
    tags: Optional[List[str]] = None  # Tags for categorization
    is_favorite: Optional[bool] = False  # Favorite flag
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # For API compatibility, provide metadata property
    @property
    def metadata(self):
        return self.meeting_metadata
    
    @metadata.setter
    def metadata(self, value):
        self.meeting_metadata = value
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert meeting to dictionary"""
        # Handle status - it might be an enum or a string
        status_value = self.status
        if hasattr(status_value, 'value'):
            status_value = status_value.value
        elif hasattr(status_value, 'name'):
            status_value = status_value.name.lower()
        
        return {
            "id": self.id,
            "title": self.title,
            "platform": self.platform,
            "duration": self.duration,
            "status": status_value,
            "transcript": self.transcript,
            "summary": self.summary,
            "key_points": self.key_points,
            "action_items": self.action_items,
            "metadata": self.meeting_metadata,  # Return as 'metadata' in API
            "token_cost": self.token_cost,
            "entity_id": self.entity_id,
            "created_by_user_id": self.created_by_user_id,
            "created_by_user_name": self.created_by_user_name,
            "created_by_user_email": self.created_by_user_email,
            "tags": self.tags or [],
            "is_favorite": self.is_favorite or False,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class MeetingCreate(BaseModel):
    """Meeting creation request model"""
    title: str
    platform: str
    duration: int
    metadata: Optional[Dict[str, Any]] = None


class MeetingUpdate(BaseModel):
    """Meeting update request model"""
    title: Optional[str] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    key_points: Optional[List[str]] = None
    status: Optional[MeetingStatus] = None

