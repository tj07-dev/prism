"""
Base Segmentation Service with common functionality.
"""

import logging
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.models.ml_models import UserSegment

logger = logging.getLogger(__name__)


class BaseSegmentationService:
    """Base class for segmentation services."""

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(self.__class__.__name__)

    def _serialize_segment(self, segment: UserSegment) -> Dict[str, Any]:
        """Serialize segment to dictionary."""
        return {
            "id": str(segment.id),
            "name": segment.name,
            "description": segment.description,
            "segment_type": segment.segment_type,
            "criteria": segment.criteria,
            "is_active": segment.is_active,
            "auto_update": segment.auto_update,
            "update_frequency": segment.update_frequency,
            "member_count": segment.member_count,
            "created_at": segment.created_at.isoformat()
            if segment.created_at
            else None,
            "updated_at": segment.updated_at.isoformat()
            if segment.updated_at
            else None,
            "last_updated": segment.last_updated.isoformat()
            if segment.last_updated
            else None,
            # "created_by": str(segment.created_by) if segment.created_by else None,
        }
