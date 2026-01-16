"""
Segment Manager Service.
Handles CRUD operations for user segments.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import and_, desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.ml_models import UserSegment, UserSegmentMembership
from app.services.segmentation.base_segmentation_service import BaseSegmentationService
from app.services.segmentation.segment_rule_engine import SegmentRuleEngine

logger = logging.getLogger(__name__)


class SegmentManager(BaseSegmentationService):
    """Service for managing user segments."""

    def __init__(self, db: Session):
        super().__init__(db)
        self.rule_engine = SegmentRuleEngine(db)

    def create_segment(
        self, segment_data: Dict[str, Any], user_id: str
    ) -> Dict[str, Any]:
        """Create a new user segment."""
        try:
            raw_name = (segment_data.get("name") or "").strip()
            if not raw_name:
                raise ValueError("Segment name cannot be empty.")

            existing = (
                self.db.query(UserSegment.id)
                .filter(func.lower(UserSegment.name) == raw_name.lower())
                .first()
            )
            if existing:
                raise ValueError(
                    f"A segment named '{raw_name}' already exists. Please choose a different name."
                )

            criteria = segment_data.get("criteria") or {}
            self.rule_engine.validate_segment_rules(criteria)

            segment_type = (segment_data.get("segment_type") or "custom").lower()
            description = (segment_data.get("description") or "").strip()

            segment = UserSegment(
                id=uuid.uuid4(),
                name=raw_name,
                description=description,
                criteria=criteria,
                segment_type=segment_type,
                is_active=segment_data.get("is_active", True),
                auto_update=segment_data.get("auto_update", True),
                update_frequency=segment_data.get("update_frequency"),
            )

            self.db.add(segment)
            self.db.commit()
            self.db.refresh(segment)

            # Apply segment rules to find initial members
            if segment.auto_update:
                self.rule_engine.apply_segment_rules(segment)

            self.logger.info(f"Created user segment: {segment.name}")
            return self._serialize_segment(segment)

        except IntegrityError as exc:
            self.db.rollback()
            if "ix_user_segments_name" in str(exc.orig).lower():
                raise ValueError(
                    f"A segment named '{segment_data.get('name')}' already exists. Please choose a different name."
                )
            self.logger.error(f"Database error creating segment: {exc}")
            raise
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Error creating segment: {e}")
            raise

    def update_segment(
        self, segment_id: str, segment_data: Dict[str, Any], user_id: str
    ) -> Dict[str, Any]:
        """Update an existing segment."""
        try:
            segment = (
                self.db.query(UserSegment)
                .filter(UserSegment.id == uuid.UUID(segment_id))
                .first()
            )
            if not segment:
                raise ValueError(f"Segment not found: {segment_id}")

            # Update fields
            updateable_fields = [
                "name",
                "description",
                "criteria",
                "is_active",
                "auto_update",
                "update_frequency",
            ]

            rules_changed = False
            for field in updateable_fields:
                if field not in segment_data:
                    continue

                value = segment_data[field]

                if field == "name":
                    new_name = (value or "").strip()
                    if not new_name:
                        raise ValueError("Segment name cannot be empty.")

                    duplicate = (
                        self.db.query(UserSegment.id)
                        .filter(func.lower(UserSegment.name) == new_name.lower())
                        .filter(UserSegment.id != segment.id)
                        .first()
                    )
                    if duplicate:
                        raise ValueError(
                            f"A segment named '{new_name}' already exists. Please choose a different name."
                        )
                    segment.name = new_name
                    continue

                if field == "description":
                    segment.description = (value or "").strip()
                    continue

                if field == "criteria":
                    new_criteria = value or {}
                    if new_criteria != segment.criteria:
                        self.rule_engine.validate_segment_rules(new_criteria)
                        rules_changed = True
                    segment.criteria = new_criteria
                    continue

                setattr(segment, field, value)

            segment.updated_at = datetime.utcnow()
            segment.last_updated = datetime.utcnow()

            self.db.commit()

            # Re-apply rules if they changed
            if rules_changed and segment.auto_update:
                self.rule_engine.apply_segment_rules(segment)

            self.logger.info(f"Updated segment {segment_id}")
            return self._serialize_segment(segment)

        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Error updating segment: {e}")
            raise

    def delete_segment(self, segment_id: str) -> bool:
        """Delete a segment and its memberships."""
        try:
            segment = (
                self.db.query(UserSegment)
                .filter(UserSegment.id == uuid.UUID(segment_id))
                .first()
            )

            if not segment:
                return False

            # Delete memberships first
            self.db.query(UserSegmentMembership).filter(
                UserSegmentMembership.segment_id == uuid.UUID(segment_id)
            ).delete()

            # Delete segment
            self.db.delete(segment)
            self.db.commit()

            self.logger.info(f"Deleted segment {segment_id}")
            return True

        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Error deleting segment: {e}")
            raise

    def get_segments(
        self, filters: Dict[str, Any] = None, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get list of segments with optional filters."""
        try:
            query = self.db.query(UserSegment)

            if filters:
                if "is_active" in filters:
                    query = query.filter(UserSegment.is_active == filters["is_active"])
                if "segment_type" in filters:
                    query = query.filter(
                        UserSegment.segment_type == filters["segment_type"]
                    )

            segments = (
                query.order_by(desc(UserSegment.created_at))
                .limit(limit)
                .offset(offset)
                .all()
            )

            return [self._serialize_segment(seg) for seg in segments]

        except Exception as e:
            self.logger.error(f"Error getting segments: {e}")
            return []

    def get_segment_by_id(self, segment_id: str) -> Dict[str, Any]:
        """Get segment by ID."""
        try:
            segment = (
                self.db.query(UserSegment)
                .filter(UserSegment.id == uuid.UUID(segment_id))
                .first()
            )

            if not segment:
                raise ValueError(f"Segment not found: {segment_id}")

            return self._serialize_segment(segment)

        except Exception as e:
            self.logger.error(f"Error getting segment: {e}")
            raise

    def refresh_segment(self, segment_id: str) -> Dict[str, Any]:
        """Refresh segment by re-applying rules."""
        try:
            segment = (
                self.db.query(UserSegment)
                .filter(UserSegment.id == uuid.UUID(segment_id))
                .first()
            )

            if not segment:
                raise ValueError(f"Segment not found: {segment_id}")

            # Re-apply rules
            self.rule_engine.apply_segment_rules(segment)

            return {
                "success": True,
                "segment_id": segment_id,
                "new_size": segment.actual_size,
                "updated_at": segment.last_updated.isoformat()
                if segment.last_updated
                else None,
            }

        except Exception as e:
            self.logger.error(f"Error refreshing segment: {e}")
            raise

    def get_segment_users(
        self, segment_id: str, limit: int = 100, offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get users in a segment with pagination.

        Args:
            segment_id: Segment ID
            limit: Maximum number of users to return
            offset: Number of users to skip

        Returns:
            Dictionary with users list and pagination info
        """
        try:
            segment = (
                self.db.query(UserSegment)
                .filter(UserSegment.id == uuid.UUID(segment_id))
                .first()
            )

            if not segment:
                raise ValueError(f"Segment not found: {segment_id}")

            # Get total count
            total_count = (
                self.db.query(UserSegmentMembership)
                .filter(
                    and_(
                        UserSegmentMembership.segment_id == uuid.UUID(segment_id),
                        UserSegmentMembership.is_active == True,
                    )
                )
                .count()
            )

            # Get paginated memberships with user data
            memberships = (
                self.db.query(UserSegmentMembership)
                .filter(
                    and_(
                        UserSegmentMembership.segment_id == uuid.UUID(segment_id),
                        UserSegmentMembership.is_active == True,
                    )
                )
                .order_by(desc(UserSegmentMembership.assigned_at))
                .limit(limit)
                .offset(offset)
                .all()
            )

            # Serialize user data
            users = []
            for membership in memberships:
                user_data = {
                    "user_id": str(membership.user_id),
                    "membership_score": float(membership.membership_score)
                    if membership.membership_score
                    else None,
                    "assigned_at": membership.assigned_at.isoformat()
                    if membership.assigned_at
                    else None,
                    "last_evaluated": membership.last_evaluated.isoformat()
                    if membership.last_evaluated
                    else None,
                    "assignment_reason": membership.assignment_reason,
                }

                # Add user details if relationship is loaded
                if membership.user:
                    user_data["email"] = membership.user.email
                    user_data["username"] = membership.user.username
                    user_data["first_name"] = membership.user.first_name
                    user_data["last_name"] = membership.user.last_name

                users.append(user_data)

            return {
                "segment_id": segment_id,
                "segment_name": segment.name,
                "users": users,
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total_count,
            }

        except Exception as e:
            self.logger.error(f"Error getting segment users: {e}")
            raise

    def add_user_to_segment(
        self, segment_id: str, user_id: str, score: float = None, reason: str = None
    ) -> Dict[str, Any]:
        """
        Manually add a user to a segment.

        Args:
            segment_id: Segment ID
            user_id: User ID to add
            score: Optional membership score (0-1)
            reason: Optional reason for adding user

        Returns:
            Dictionary with success status and membership info
        """
        try:
            # Validate segment exists
            segment = (
                self.db.query(UserSegment)
                .filter(UserSegment.id == uuid.UUID(segment_id))
                .first()
            )

            if not segment:
                raise ValueError(f"Segment not found: {segment_id}")

            # Check if membership already exists
            existing = (
                self.db.query(UserSegmentMembership)
                .filter(
                    and_(
                        UserSegmentMembership.segment_id == uuid.UUID(segment_id),
                        UserSegmentMembership.user_id == uuid.UUID(user_id),
                    )
                )
                .first()
            )

            if existing:
                # Reactivate if inactive
                if not existing.is_active:
                    existing.is_active = True
                    existing.last_evaluated = datetime.utcnow()
                    existing.membership_score = (
                        score if score is not None else existing.membership_score
                    )
                    existing.assignment_reason = reason or "Manually reactivated"
                    self.db.commit()

                    self.logger.info(
                        f"Reactivated user {user_id} in segment {segment_id}"
                    )
                    return {
                        "success": True,
                        "action": "reactivated",
                        "membership_id": str(existing.id),
                        "user_id": user_id,
                        "segment_id": segment_id,
                    }
                else:
                    return {
                        "success": False,
                        "error": "User already in segment",
                        "membership_id": str(existing.id),
                    }

            # Create new membership
            membership = UserSegmentMembership(
                id=uuid.uuid4(),
                user_id=uuid.UUID(user_id),
                segment_id=uuid.UUID(segment_id),
                membership_score=score if score is not None else 1.0,
                assigned_at=datetime.utcnow(),
                last_evaluated=datetime.utcnow(),
                is_active=True,
                assignment_reason=reason or "Manually added",
            )

            self.db.add(membership)

            # Update segment size
            segment.actual_size = (segment.actual_size or 0) + 1
            segment.last_updated = datetime.utcnow()

            self.db.commit()

            self.logger.info(f"Added user {user_id} to segment {segment_id}")
            return {
                "success": True,
                "action": "created",
                "membership_id": str(membership.id),
                "user_id": user_id,
                "segment_id": segment_id,
            }

        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Error adding user to segment: {e}")
            raise

    def remove_user_from_segment(self, segment_id: str, user_id: str) -> Dict[str, Any]:
        """
        Remove a user from a segment.

        Args:
            segment_id: Segment ID
            user_id: User ID to remove

        Returns:
            Dictionary with success status
        """
        try:
            # Find membership
            membership = (
                self.db.query(UserSegmentMembership)
                .filter(
                    and_(
                        UserSegmentMembership.segment_id == uuid.UUID(segment_id),
                        UserSegmentMembership.user_id == uuid.UUID(user_id),
                        UserSegmentMembership.is_active == True,
                    )
                )
                .first()
            )

            if not membership:
                return {
                    "success": False,
                    "error": "User not found in segment or already removed",
                }

            # Soft delete - mark as inactive
            membership.is_active = False
            membership.last_evaluated = datetime.utcnow()

            # Update segment size
            segment = (
                self.db.query(UserSegment)
                .filter(UserSegment.id == uuid.UUID(segment_id))
                .first()
            )
            if segment and segment.actual_size:
                segment.actual_size = max(0, segment.actual_size - 1)
                segment.last_updated = datetime.utcnow()

            self.db.commit()

            self.logger.info(f"Removed user {user_id} from segment {segment_id}")
            return {
                "success": True,
                "user_id": user_id,
                "segment_id": segment_id,
                "removed_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Error removing user from segment: {e}")
            raise
