"""
Integration endpoints for programmatic access via API key
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from typing import Optional, List
from loguru import logger

from api.services.api_key_service import verify_api_key
from api.routers.meetings import list_meetings, get_meeting
from api.models.meeting import MeetingStatus

router = APIRouter(prefix="/api/integration", tags=["integration"])


@router.get("/health")
async def health_check(api_key_info: dict = Depends(verify_api_key)):
    """Health check endpoint. Requires API key authentication."""
    return JSONResponse({
        "status": "healthy",
        "service": "meeting-note-taker",
        "authenticated": True,
        "auth_method": "api_key"
    })


@router.get("/meetings")
async def list_meetings_integration(
    limit: int = 20,
    offset: int = 0,
    status: Optional[str] = None,
    entity_id: Optional[int] = None,
    api_key_info: dict = Depends(verify_api_key)
):
    """
    List meetings. Requires API key authentication and entity_id for data isolation.
    """
    if not entity_id:
        raise HTTPException(
            status_code=400,
            detail="entity_id query parameter is required for data isolation"
        )

    try:
        from database.models import MeetingModel, MeetingStatusEnum
        from database.db import get_db
        from sqlalchemy.orm import Session

        db: Session = next(get_db())

        query = db.query(MeetingModel).filter(MeetingModel.entity_id == str(entity_id))

        # Filter by status if provided
        if status:
            try:
                status_enum = MeetingStatusEnum[status.upper()]
                query = query.filter(MeetingModel.status == status_enum)
            except KeyError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        # Apply pagination
        total = query.count()
        meetings = query.order_by(MeetingModel.created_at.desc()).offset(offset).limit(limit).all()

        # Convert to dict format
        meetings_list = [meeting.to_dict() for meeting in meetings]

        result = {
            "success": True,
            "meetings": meetings_list,
            "total": total,
            "limit": limit,
            "offset": offset
        }
        db.close()
        return JSONResponse(result)

    except HTTPException:
        raise
    except Exception as e:
        if 'db' in locals():
            db.close()
        logger.error(f"Error listing meetings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list meetings: {str(e)}")


@router.get("/meetings/{meeting_id}")
async def get_meeting_integration(
    meeting_id: str,
    entity_id: int = None,
    api_key_info: dict = Depends(verify_api_key)
):
    """Get a specific meeting. Requires API key authentication and entity_id for data isolation."""
    if not entity_id:
        raise HTTPException(
            status_code=400,
            detail="entity_id query parameter is required for data isolation"
        )

    try:
        from database.models import MeetingModel
        from database.db import SessionLocal

        db = SessionLocal()

        meeting = db.query(MeetingModel).filter(
            MeetingModel.id == meeting_id,
            MeetingModel.entity_id == str(entity_id)
        ).first()

        if not meeting:
            db.close()
            raise HTTPException(status_code=404, detail="Meeting not found")

        result = {
            "success": True,
            "meeting": meeting.to_dict()
        }
        db.close()
        return JSONResponse(result)

    except HTTPException:
        if 'db' in locals():
            db.close()
        raise
    except Exception as e:
        if 'db' in locals():
            db.close()
        logger.error(f"Error getting meeting: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get meeting: {str(e)}")


@router.get("/stats")
async def get_stats(
    entity_id: int = None,
    api_key_info: dict = Depends(verify_api_key)
):
    """Get meeting statistics. Requires API key authentication and entity_id for data isolation."""
    if not entity_id:
        raise HTTPException(
            status_code=400,
            detail="entity_id query parameter is required for data isolation"
        )

    try:
        from database.models import MeetingModel, MeetingStatusEnum
        from database.db import SessionLocal

        db = SessionLocal()

        entity_filter = MeetingModel.entity_id == str(entity_id)

        total_meetings = db.query(MeetingModel).filter(entity_filter).count()
        completed_meetings = db.query(MeetingModel).filter(
            entity_filter,
            MeetingModel.status == MeetingStatusEnum.COMPLETED
        ).count()
        processing_meetings = db.query(MeetingModel).filter(
            entity_filter,
            MeetingModel.status == MeetingStatusEnum.PROCESSING
        ).count()
        failed_meetings = db.query(MeetingModel).filter(
            entity_filter,
            MeetingModel.status == MeetingStatusEnum.FAILED
        ).count()

        result = {
            "success": True,
            "stats": {
                "total_meetings": total_meetings,
                "completed": completed_meetings,
                "processing": processing_meetings,
                "failed": failed_meetings
            }
        }
        db.close()
        return JSONResponse(result)

    except HTTPException:
        raise
    except Exception as e:
        if 'db' in locals():
            db.close()
        logger.error(f"Error getting stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

