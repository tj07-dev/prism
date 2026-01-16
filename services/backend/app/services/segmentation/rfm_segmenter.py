"""
RFM Segmenter Service.
Creates and manages RFM-based user segments.
"""

import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models.ml_models import UserSegment
from app.services.segmentation.base_segmentation_service import BaseSegmentationService
from app.services.segmentation.segment_manager import SegmentManager

logger = logging.getLogger(__name__)


class RFMSegmenter(BaseSegmentationService):
    """Service for RFM-based segmentation."""

    def __init__(self, db: Session):
        super().__init__(db)
        self.segment_manager = SegmentManager(db)

    def create_rfm_segments(self) -> List[Dict[str, Any]]:
        """Create standard RFM-based segments."""
        try:
            rfm_segments = [
                {
                    "name": "Champions",
                    "description": "Bought recently, buy often and spend the most",
                    "segment_type": "rfm",
                    "criteria": {
                        "conditions": [
                            {
                                "field": "rfm_recency_score",
                                "operator": ">=",
                                "value": 4,
                            },
                            {
                                "field": "rfm_frequency_score",
                                "operator": ">=",
                                "value": 4,
                            },
                            {
                                "field": "rfm_monetary_score",
                                "operator": ">=",
                                "value": 4,
                            },
                        ],
                        "logic": "AND",
                    },
                },
                {
                    "name": "Loyal Customers",
                    "description": "Spend good money often, responsive to promotions",
                    "segment_type": "rfm",
                    "criteria": {
                        "conditions": [
                            {
                                "field": "rfm_recency_score",
                                "operator": ">=",
                                "value": 2,
                            },
                            {
                                "field": "rfm_frequency_score",
                                "operator": ">=",
                                "value": 3,
                            },
                            {
                                "field": "rfm_monetary_score",
                                "operator": ">=",
                                "value": 3,
                            },
                        ],
                        "logic": "AND",
                    },
                },
                {
                    "name": "Potential Loyalists",
                    "description": "Recent customers with good spending",
                    "segment_type": "rfm",
                    "criteria": {
                        "conditions": [
                            {
                                "field": "rfm_recency_score",
                                "operator": ">=",
                                "value": 3,
                            },
                            {
                                "field": "rfm_frequency_score",
                                "operator": ">=",
                                "value": 2,
                            },
                            {
                                "field": "rfm_monetary_score",
                                "operator": ">=",
                                "value": 2,
                            },
                        ],
                        "logic": "AND",
                    },
                },
                {
                    "name": "New Customers",
                    "description": "Bought recently but not often",
                    "segment_type": "rfm",
                    "criteria": {
                        "conditions": [
                            {
                                "field": "rfm_recency_score",
                                "operator": ">=",
                                "value": 4,
                            },
                            {
                                "field": "rfm_frequency_score",
                                "operator": "<=",
                                "value": 2,
                            },
                        ],
                        "logic": "AND",
                    },
                },
                {
                    "name": "At Risk",
                    "description": "Spent big and purchased often, but long time ago",
                    "segment_type": "rfm",
                    "criteria": {
                        "conditions": [
                            {
                                "field": "rfm_recency_score",
                                "operator": "<=",
                                "value": 2,
                            },
                            {
                                "field": "rfm_frequency_score",
                                "operator": ">=",
                                "value": 3,
                            },
                            {
                                "field": "rfm_monetary_score",
                                "operator": ">=",
                                "value": 3,
                            },
                        ],
                        "logic": "AND",
                    },
                },
                {
                    "name": "Cannot Lose Them",
                    "description": "Made biggest purchases often, but long ago",
                    "segment_type": "rfm",
                    "criteria": {
                        "conditions": [
                            {
                                "field": "rfm_recency_score",
                                "operator": "<=",
                                "value": 2,
                            },
                            {
                                "field": "rfm_frequency_score",
                                "operator": ">=",
                                "value": 4,
                            },
                            {
                                "field": "rfm_monetary_score",
                                "operator": ">=",
                                "value": 4,
                            },
                        ],
                        "logic": "AND",
                    },
                },
                {
                    "name": "Hibernating",
                    "description": "Low spenders, low orders, inactive",
                    "segment_type": "rfm",
                    "criteria": {
                        "conditions": [
                            {
                                "field": "rfm_recency_score",
                                "operator": "<=",
                                "value": 2,
                            },
                            {
                                "field": "rfm_frequency_score",
                                "operator": "<=",
                                "value": 2,
                            },
                            {
                                "field": "rfm_monetary_score",
                                "operator": "<=",
                                "value": 2,
                            },
                        ],
                        "logic": "AND",
                    },
                },
                {
                    "name": "Lost",
                    "description": "Lowest recency, frequency and monetary scores",
                    "segment_type": "rfm",
                    "criteria": {
                        "conditions": [
                            {
                                "field": "rfm_recency_score",
                                "operator": "<=",
                                "value": 1,
                            },
                            {
                                "field": "rfm_frequency_score",
                                "operator": "<=",
                                "value": 1,
                            },
                        ],
                        "logic": "AND",
                    },
                },
            ]

            created_segments = []
            for segment_data in rfm_segments:
                try:
                    # Check if segment already exists
                    existing = (
                        self.db.query(UserSegment)
                        .filter(UserSegment.name == segment_data["name"])
                        .first()
                    )

                    if not existing:
                        segment = self.segment_manager.create_segment(
                            segment_data, "system"
                        )
                        created_segments.append(segment)
                        self.logger.info(f"Created RFM segment: {segment_data['name']}")
                    else:
                        self.logger.info(
                            f"RFM segment already exists: {segment_data['name']}"
                        )

                except Exception as e:
                    self.logger.error(
                        f"Error creating RFM segment {segment_data['name']}: {e}"
                    )
                    continue

            return created_segments

        except Exception as e:
            self.logger.error(f"Error creating RFM segments: {e}")
            return []
