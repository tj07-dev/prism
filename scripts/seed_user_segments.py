#!/usr/bin/env python3
"""
User Segment Seeding Script
This script seeds user segment data by mapping existing users to appropriate segments
based on predefined rules. This script works independently without app imports.
"""

import logging
import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import psycopg2
from psycopg2.extras import execute_values

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UserSegmentSeeder:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.conn = psycopg2.connect(database_url)
        self.conn.autocommit = False

    def seed_user_segments(self):
        """Seed user segment data by mapping users to segments."""
        logger.info("Starting user segment seeding...")
        try:
            # Get all active segments
            segments = self._get_active_segments()
            logger.info(f"Found {len(segments)} active segments")
            if not segments:
                logger.warning(
                    "No active segments found. Please ensure segments are created."
                )
                return

            # Get all users (just for logging purposes)
            users = self._get_all_users()
            logger.info(f"Found {len(users)} users to process")
            if not users:
                logger.warning(
                    "No users found in database. Please run seed-data first."
                )
                return

            total_memberships = 0
            mapped_users = 0

            # Process each segment
            for segment in segments:
                logger.info(
                    f"Processing segment: {segment['name']} ({segment['segment_type']})"
                )

                # Evaluate segment rules and get matching user IDs
                matching_user_ids = self._evaluate_segment_rules(segment)

                if matching_user_ids:
                    memberships_created = self._create_segment_memberships(
                        segment["id"], matching_user_ids
                    )
                    total_memberships += memberships_created
                    mapped_users += len(matching_user_ids)
                    logger.info(
                        f"  Created {memberships_created} memberships for {len(matching_user_ids)} users"
                    )

                    # Update segment member count
                    self._update_segment_member_count(segment["id"])

            self.conn.commit()
            logger.info("✅ User segment seeding completed successfully!")
            logger.info(f"📊 Summary: {mapped_users} users mapped to segments")
            logger.info(f"📊 Total memberships created: {total_memberships}")

        except Exception as e:
            logger.error(f"Error during user segment seeding: {str(e)}")
            self.conn.rollback()
            raise

        finally:
            self.conn.close()

    def _get_active_segments(self):
        """Get all active segments with their rules."""
        query = """
            SELECT id, name, segment_type, criteria
            FROM user_segments
            WHERE is_active = true
            ORDER BY name
        """
        with self.conn.cursor() as cursor:
            cursor.execute(query)
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _get_all_users(self):
        """Get all users with their basic info (for logging)."""
        query = """
            SELECT id, email, created_at, last_login
            FROM users
            ORDER BY created_at
        """
        with self.conn.cursor() as cursor:
            cursor.execute(query)
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _evaluate_segment_rules(self, segment):
        """Evaluate segment rules and return matching user IDs."""
        segment_type = (segment.get("segment_type") or "custom").lower()
        criteria = segment.get("criteria") or {}

        if segment_type == "rfm":
            return self._evaluate_rfm_rules(criteria)
        else:
            return self._evaluate_custom_rules(criteria)

    def _evaluate_rfm_rules(self, criteria):
        """Evaluate RFM (Recency, Frequency, Monetary) rules."""
        conditions = criteria.get("conditions", [])
        logic = criteria.get("logic", "and").lower()

        query = """
            WITH user_rfm AS (
                SELECT
                    u.id,
                    u.email,
                    u.created_at,
                    u.last_login,
                    CASE
                        WHEN MAX(o.created_at) IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (NOW() - MAX(o.created_at))) / 86400
                        ELSE EXTRACT(EPOCH FROM (NOW() - u.created_at)) / 86400
                    END as recency_days,
                    COUNT(o.id) as frequency,
                    COALESCE(SUM(o.total_amount), 0) as monetary
                FROM users u
                LEFT JOIN orders o ON u.id = o.user_id AND o.status = 'completed'
                GROUP BY u.id, u.email, u.created_at, u.last_login
            )
            SELECT id FROM user_rfm WHERE
        """
        where_conditions = []
        params = []

        for condition in conditions:
            field = condition.get("field", "")
            operator = condition.get("operator", "")
            value = condition.get("value")

            if field.startswith("rfm."):
                rfm_field = field.split(".")[1]
                field_map = {
                    "recency": "recency_days",
                    "frequency": "frequency",
                    "monetary": "monetary",
                }
                if rfm_field in field_map:
                    db_field = field_map[rfm_field]
                    sql_condition, sql_params = self._build_condition_sql(
                        db_field, operator, value
                    )
                    where_conditions.append(sql_condition)
                    params.extend(sql_params)

        if not where_conditions:
            return []

        query += (
            " OR ".join(where_conditions)
            if logic == "or"
            else " AND ".join(where_conditions)
        )

        with self.conn.cursor() as cursor:
            cursor.execute(query, params)
            return [row[0] for row in cursor.fetchall()]

    def _evaluate_custom_rules(self, criteria):
        """Evaluate custom/behavioral segment rules."""
        conditions = criteria.get("conditions", [])
        logic = criteria.get("logic", "and").lower()

        query = """
            SELECT DISTINCT u.id
            FROM users u
            LEFT JOIN (
                SELECT
                    user_id,
                    COUNT(*) as order_count,
                    SUM(total_amount) as total_spent,
                    AVG(total_amount) as avg_order_value,
                    MAX(created_at) as last_order_date
                FROM orders
                WHERE status = 'completed'
                GROUP BY user_id
            ) order_stats ON u.id = order_stats.user_id
            WHERE
        """
        where_conditions = []
        params = []

        for condition in conditions:
            field = condition.get("field", "")
            operator = condition.get("operator", "")
            value = condition.get("value")

            if field == "total_spent":
                sql, p = self._build_condition_sql(
                    "COALESCE(order_stats.total_spent, 0)", operator, value
                )
                where_conditions.append(sql)
                params.extend(p)
            elif field == "order_count":
                sql, p = self._build_condition_sql(
                    "COALESCE(order_stats.order_count, 0)", operator, value
                )
                where_conditions.append(sql)
                params.extend(p)
            elif field == "days_since_last_order":
                days = int(value)
                cutoff = datetime.now() - timedelta(days=days)
                if operator in (">=", ">"):
                    where_conditions.append(
                        "(order_stats.last_order_date IS NULL OR order_stats.last_order_date <= %s)"
                    )
                    params.append(cutoff)
                elif operator in ("<=", "<"):
                    where_conditions.append(
                        "(order_stats.last_order_date IS NOT NULL AND order_stats.last_order_date >= %s)"
                    )
                    params.append(cutoff)
            elif field == "days_since_registration":
                days = int(value)
                cutoff = datetime.now() - timedelta(days=days)
                if operator in (">=", ">"):
                    where_conditions.append("u.created_at <= %s")
                    params.append(cutoff)
                elif operator in ("<=", "<"):
                    where_conditions.append("u.created_at >= %s")
                    params.append(cutoff)

        if not where_conditions:
            query = "SELECT id FROM users"
            with self.conn.cursor() as cursor:
                cursor.execute(query)
                return [row[0] for row in cursor.fetchall()]

        query += (
            " OR ".join(where_conditions)
            if logic == "or"
            else " AND ".join(where_conditions)
        )

        with self.conn.cursor() as cursor:
            cursor.execute(query, params)
            return [row[0] for row in cursor.fetchall()]

    def _build_condition_sql(self, field, operator, value):
        """Build SQL condition for a field comparison."""
        operators = {
            ">=": f"{field} >= %s",
            "<=": f"{field} <= %s",
            ">": f"{field} > %s",
            "<": f"{field} < %s",
            "==": f"{field} = %s",
            "=": f"{field} = %s",
        }
        sql = operators.get(operator, f"{field} = %s")
        return sql, [value]

    def _create_segment_memberships(self, segment_id, user_ids):
        """Create or update segment memberships - safe version without requiring unique constraint"""
        if not user_ids:
            return 0

        membership_data = [
            (
                str(uuid.uuid4()),  # id
                user_id,  # user_id
                segment_id,  # segment_id
                Decimal("1.0"),  # membership_score
                datetime.now(),  # assigned_at
                datetime.now(),  # last_evaluated
                True,  # is_active
                "auto_assigned",  # assignment_reason
            )
            for user_id in user_ids
        ]

        with self.conn.cursor() as cursor:
            # Step 1: Deactivate any existing memberships for these users in this segment
            cursor.execute(
                """
                UPDATE user_segment_memberships
                SET is_active = false
                WHERE segment_id = %s
                  AND user_id = ANY(%s::uuid[])
            """,
                (segment_id, user_ids),
            )

            # Step 2: Insert fresh records
            execute_values(
                cursor,
                """
                INSERT INTO user_segment_memberships
                (id, user_id, segment_id, membership_score, assigned_at, last_evaluated, is_active, assignment_reason)
                VALUES %s
            """,
                membership_data,
            )

        return len(membership_data)

    def _update_segment_member_count(self, segment_id):
        """Update the member count for a segment."""
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE user_segments
                SET member_count = (
                    SELECT COUNT(*)
                    FROM user_segment_memberships
                    WHERE segment_id = %s
                      AND is_active = true
                ),
                last_updated = NOW()
                WHERE id = %s
            """,
                (segment_id, segment_id),
            )


# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if os.getenv("RUNNING_IN_DOCKER") or os.path.exists("/.dockerenv"):
        DATABASE_URL = (
            "postgresql://ecommerce_user:ecommerce_pass@postgres:5432/ecommerce"
        )
    else:
        DATABASE_URL = (
            "postgresql://ecommerce_user:ecommerce_pass@localhost:5435/ecommerce"
        )

    seeder = UserSegmentSeeder(DATABASE_URL)
    seeder.seed_user_segments()

    print("\n" + "=" * 60)
    print("🎉 USER SEGMENT SEEDING COMPLETED!")
    print("=" * 60)
    print("\n📊 User segments have been populated with member data")
    print("📈 Analytics and recommendations will now use segment information")
    print("🎯 Users are now mapped to appropriate segments based on their behavior")
