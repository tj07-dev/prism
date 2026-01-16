"""
User Analytics Service - Compatibility Wrapper.
Provides unified interface to modular analytics services.
"""

from sqlalchemy.orm import Session

from app.services.analytics import (
    BehaviorAnalyzer,
    ChurnPredictor,
    CohortAnalyzer,
    UserEventTracker,
)


class UserAnalyticsService:
    """Unified analytics service using modular components."""

    def __init__(self, db: Session):
        self.db = db
        self.event_tracker = UserEventTracker(db)
        self.behavior_analyzer = BehaviorAnalyzer(db)
        self.cohort_analyzer = CohortAnalyzer(db)
        self.churn_predictor = ChurnPredictor(db)

    # Event tracking
    def track_user_event(
        self, user_id, session_id, event_type, event_data, request_info=None
    ):
        return self.event_tracker.track_user_event(
            user_id, session_id, event_type, event_data, request_info
        )

    # Cohort analysis
    def get_user_cohort_analysis(self, cohort_period, months_back):
        return self.cohort_analyzer.get_user_cohort_analysis(cohort_period, months_back)

    # Behavior analysis
    def get_user_behavior_summary(self, user_id, days=30):
        return self.behavior_analyzer.get_user_behavior_summary(user_id, days)

    # Churn prediction
    def calculate_churn_risk(self, user_id):
        return self.churn_predictor.calculate_churn_risk(user_id)

    def get_funnel_analysis(self, funnel_steps, days):
        """
        Analyze conversion funnel through specified steps.

        Args:
            funnel_steps: List of event types representing funnel steps
            days: Number of days to analyze

        Returns:
            Dictionary with funnel analysis including conversion rates between steps
        """
        import logging
        from datetime import datetime, timedelta

        from sqlalchemy import distinct, func

        from app.models import UserBehaviorEvent

        logger = logging.getLogger(__name__)

        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            funnel_data = []
            previous_user_count = None

            for i, step in enumerate(funnel_steps):
                # Count unique users who reached this step
                user_count = (
                    self.db.query(func.count(distinct(UserBehaviorEvent.user_id)))
                    .filter(
                        UserBehaviorEvent.event_type == step,
                        UserBehaviorEvent.created_at >= cutoff_date,
                    )
                    .scalar()
                    or 0
                )

                # Calculate conversion rate from previous step
                conversion_rate = 0.0
                drop_off_rate = 0.0

                if i == 0:
                    conversion_rate = 100.0  # First step is always 100%
                elif previous_user_count and previous_user_count > 0:
                    conversion_rate = round((user_count / previous_user_count) * 100, 2)
                    drop_off_rate = round(100.0 - conversion_rate, 2)

                funnel_data.append(
                    {
                        "step": i + 1,
                        "step_name": step,
                        "user_count": user_count,
                        "conversion_rate": conversion_rate,
                        "drop_off_rate": drop_off_rate,
                    }
                )

                previous_user_count = user_count

            # Calculate overall funnel conversion
            overall_conversion = 0.0
            if funnel_data and funnel_data[0]["user_count"] > 0:
                overall_conversion = round(
                    (funnel_data[-1]["user_count"] / funnel_data[0]["user_count"])
                    * 100,
                    2,
                )

            return {
                "funnel_steps": funnel_data,
                "overall_conversion_rate": overall_conversion,
                "total_started": funnel_data[0]["user_count"] if funnel_data else 0,
                "total_completed": funnel_data[-1]["user_count"] if funnel_data else 0,
                "days_analyzed": days,
                "date_range": {
                    "start": cutoff_date.isoformat(),
                    "end": datetime.utcnow().isoformat(),
                },
            }

        except Exception as e:
            logger.error(f"Error in funnel analysis: {e}", exc_info=True)
            raise

    def get_user_segmentation_insights(self, days):
        """
        Get insights about user segment performance and distribution.

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary with segment insights including growth, activity, and performance metrics
        """
        import logging
        from datetime import datetime, timedelta
        from decimal import Decimal

        from sqlalchemy import func

        from app.models import Order, UserSegment, UserSegmentMembership

        logger = logging.getLogger(__name__)

        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            # Get all active segments
            segments = (
                self.db.query(UserSegment).filter(UserSegment.is_active == True).all()
            )

            insights = []

            for segment in segments:
                # Get current member count
                current_members = (
                    self.db.query(func.count(UserSegmentMembership.id))
                    .filter(
                        UserSegmentMembership.segment_id == segment.id,
                        UserSegmentMembership.is_active == True,
                    )
                    .scalar()
                    or 0
                )

                # Get new members in period
                new_members = (
                    self.db.query(func.count(UserSegmentMembership.id))
                    .filter(
                        UserSegmentMembership.segment_id == segment.id,
                        UserSegmentMembership.is_active == True,
                        UserSegmentMembership.assigned_at >= cutoff_date,
                    )
                    .scalar()
                    or 0
                )

                # Calculate growth rate
                growth_rate = 0.0
                if current_members > 0:
                    previous_members = current_members - new_members
                    if previous_members > 0:
                        growth_rate = round(
                            ((current_members - previous_members) / previous_members)
                            * 100,
                            2,
                        )

                # Get segment user IDs for activity calculations
                segment_user_ids = (
                    self.db.query(UserSegmentMembership.user_id)
                    .filter(
                        UserSegmentMembership.segment_id == segment.id,
                        UserSegmentMembership.is_active == True,
                    )
                    .all()
                )
                segment_user_ids = [str(uid[0]) for uid in segment_user_ids]

                # Calculate active users (users with orders in period)
                active_users = 0
                total_revenue = 0.0

                if segment_user_ids:
                    active_users = (
                        self.db.query(func.count(distinct(Order.user_id)))
                        .filter(
                            Order.user_id.in_(segment_user_ids),
                            Order.created_at >= cutoff_date,
                            Order.status.notin_(["cancelled", "refunded"]),
                        )
                        .scalar()
                        or 0
                    )

                    revenue_sum = (
                        self.db.query(func.sum(Order.total_amount))
                        .filter(
                            Order.user_id.in_(segment_user_ids),
                            Order.created_at >= cutoff_date,
                            Order.status.notin_(["cancelled", "refunded"]),
                        )
                        .scalar()
                    )

                    if revenue_sum:
                        if isinstance(revenue_sum, Decimal):
                            total_revenue = float(revenue_sum)
                        else:
                            total_revenue = revenue_sum

                # Calculate activity rate
                activity_rate = 0.0
                if current_members > 0:
                    activity_rate = round((active_users / current_members) * 100, 2)

                insights.append(
                    {
                        "segment_id": str(segment.id),
                        "segment_name": segment.name,
                        "segment_type": segment.segment_type,
                        "total_members": current_members,
                        "new_members": new_members,
                        "growth_rate": growth_rate,
                        "active_users": active_users,
                        "activity_rate": activity_rate,
                        "total_revenue": round(total_revenue, 2),
                        "revenue_per_member": round(total_revenue / current_members, 2)
                        if current_members > 0
                        else 0.0,
                    }
                )

            # Calculate total stats
            total_users = sum(s["total_members"] for s in insights)
            total_revenue = sum(s["total_revenue"] for s in insights)

            return {
                "segment_insights": insights,
                "summary": {
                    "total_segments": len(segments),
                    "total_users_in_segments": total_users,
                    "total_revenue": round(total_revenue, 2),
                    "days_analyzed": days,
                },
                "date_range": {
                    "start": cutoff_date.isoformat(),
                    "end": datetime.utcnow().isoformat(),
                },
            }

        except Exception as e:
            logger.error(f"Error getting segmentation insights: {e}", exc_info=True)
            raise

    def get_real_time_metrics(self):
        """
        Get real-time system metrics for monitoring dashboard.

        Returns:
            Dictionary with current system metrics including active users, recent events, and performance stats
        """
        import logging
        from datetime import datetime, timedelta

        from sqlalchemy import distinct, func

        from app.models import (
            Order,
            Product,
            RecommendationResult,
            SearchAnalytics,
            User,
            UserBehaviorEvent,
        )

        logger = logging.getLogger(__name__)

        try:
            now = datetime.utcnow()
            last_hour = now - timedelta(hours=1)
            last_24h = now - timedelta(hours=24)

            # Active users (users with events in last hour)
            active_users_1h = (
                self.db.query(func.count(distinct(UserBehaviorEvent.user_id)))
                .filter(UserBehaviorEvent.created_at >= last_hour)
                .scalar()
                or 0
            )

            active_users_24h = (
                self.db.query(func.count(distinct(UserBehaviorEvent.user_id)))
                .filter(UserBehaviorEvent.created_at >= last_24h)
                .scalar()
                or 0
            )

            # Recent orders
            orders_1h = (
                self.db.query(func.count(Order.id))
                .filter(
                    Order.created_at >= last_hour,
                    Order.status.notin_(["cancelled", "refunded"]),
                )
                .scalar()
                or 0
            )

            orders_24h = (
                self.db.query(func.count(Order.id))
                .filter(
                    Order.created_at >= last_24h,
                    Order.status.notin_(["cancelled", "refunded"]),
                )
                .scalar()
                or 0
            )

            # Revenue
            revenue_1h_raw = (
                self.db.query(func.sum(Order.total_amount))
                .filter(
                    Order.created_at >= last_hour,
                    Order.status.notin_(["cancelled", "refunded"]),
                )
                .scalar()
            )
            revenue_1h = float(revenue_1h_raw) if revenue_1h_raw else 0.0

            revenue_24h_raw = (
                self.db.query(func.sum(Order.total_amount))
                .filter(
                    Order.created_at >= last_24h,
                    Order.status.notin_(["cancelled", "refunded"]),
                )
                .scalar()
            )
            revenue_24h = float(revenue_24h_raw) if revenue_24h_raw else 0.0

            # Event counts
            events_1h = (
                self.db.query(func.count(UserBehaviorEvent.id))
                .filter(UserBehaviorEvent.created_at >= last_hour)
                .scalar()
                or 0
            )

            events_24h = (
                self.db.query(func.count(UserBehaviorEvent.id))
                .filter(UserBehaviorEvent.created_at >= last_24h)
                .scalar()
                or 0
            )

            # Search queries
            searches_1h = (
                self.db.query(func.count(SearchAnalytics.id))
                .filter(SearchAnalytics.created_at >= last_hour)
                .scalar()
                or 0
            )

            searches_24h = (
                self.db.query(func.count(SearchAnalytics.id))
                .filter(SearchAnalytics.created_at >= last_24h)
                .scalar()
                or 0
            )

            # Recommendations served
            recommendations_1h = (
                self.db.query(func.count(RecommendationResult.id))
                .filter(RecommendationResult.created_at >= last_hour)
                .scalar()
                or 0
            )

            recommendations_24h = (
                self.db.query(func.count(RecommendationResult.id))
                .filter(RecommendationResult.created_at >= last_24h)
                .scalar()
                or 0
            )

            # System stats
            total_users = self.db.query(func.count(User.id)).scalar() or 0
            total_products = (
                self.db.query(func.count(Product.id))
                .filter(Product.is_active == True)
                .scalar()
                or 0
            )
            total_orders = self.db.query(func.count(Order.id)).scalar() or 0

            return {
                "timestamp": now.isoformat(),
                "active_users": {
                    "last_hour": active_users_1h,
                    "last_24_hours": active_users_24h,
                },
                "orders": {
                    "last_hour": orders_1h,
                    "last_24_hours": orders_24h,
                },
                "revenue": {
                    "last_hour": round(revenue_1h, 2),
                    "last_24_hours": round(revenue_24h, 2),
                },
                "events": {
                    "last_hour": events_1h,
                    "last_24_hours": events_24h,
                },
                "searches": {
                    "last_hour": searches_1h,
                    "last_24_hours": searches_24h,
                },
                "recommendations": {
                    "last_hour": recommendations_1h,
                    "last_24_hours": recommendations_24h,
                },
                "system": {
                    "total_users": total_users,
                    "total_products": total_products,
                    "total_orders": total_orders,
                },
            }

        except Exception as e:
            logger.error(f"Error getting real-time metrics: {e}", exc_info=True)
            raise
