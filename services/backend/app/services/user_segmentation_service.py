"""
User Segmentation Service - Compatibility Wrapper.
Provides unified interface to modular segmentation services.
"""

from sqlalchemy.orm import Session

from app.services.segmentation import RFMSegmenter, SegmentManager, SegmentRuleEngine


class UserSegmentationService:
    """Unified segmentation service using modular components."""

    def __init__(self, db: Session):
        self.db = db
        self.segment_manager = SegmentManager(db)
        self.rule_engine = SegmentRuleEngine(db)
        self.rfm_segmenter = RFMSegmenter(db)

    # Segment management
    def get_segments(self, active_only=False, include_memberships=False):
        return self.segment_manager.get_segments(active_only, include_memberships)

    def create_segment(self, segment_data, user_id):
        return self.segment_manager.create_segment(segment_data, user_id)

    def update_segment(self, segment_id, segment_data, user_id):
        return self.segment_manager.update_segment(segment_id, segment_data, user_id)

    def delete_segment(self, segment_id):
        return self.segment_manager.delete_segment(segment_id)

    def refresh_segment(self, segment_id):
        return self.segment_manager.refresh_segment(segment_id)

    # Rule engine
    def validate_segment_rules(self, rules):
        return self.rule_engine.validate_segment_rules(rules)

    def apply_segment_rules(self, segment_id):
        return self.rule_engine.apply_segment_rules(segment_id)

    # RFM segmentation
    def create_rfm_segments(self):
        return self.rfm_segmenter.create_rfm_segments()

    # User membership management
    def get_segment_users(self, segment_id, limit=100, offset=0):
        """Get users in a segment with pagination."""
        return self.segment_manager.get_segment_users(segment_id, limit, offset)

    def add_user_to_segment(self, segment_id, user_id, score=None, reason=None):
        """Manually add a user to a segment."""
        return self.segment_manager.add_user_to_segment(
            segment_id, user_id, score, reason
        )

    def remove_user_from_segment(self, segment_id, user_id):
        """Remove a user from a segment."""
        return self.segment_manager.remove_user_from_segment(segment_id, user_id)
