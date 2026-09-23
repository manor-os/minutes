from sqlalchemy import String

from database.models import MeetingModel


def test_meeting_entity_id_accepts_manor_string_ids():
    assert isinstance(MeetingModel.__table__.c.entity_id.type, String)
