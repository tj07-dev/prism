"""
Recommendation Explainability Service.

This module provides personalized explanations for recommendations using
template-based approach (not LLM). Templates are more efficient, consistent,
and cost-effective than generating explanations via LLM for every recommendation.

The service analyzes user history, product details, and recommendation context
to select and populate appropriate explanation templates.
"""

import logging
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class ExplainabilityService:
    """
    Service for generating personalized explanations for recommendations.

    Uses template-based approach with context-aware personalization.
    Templates are populated with user-specific data (purchase history,
    viewing patterns, category preferences) for natural explanations.

    Example Usage:
        >>> explainability = ExplainabilityService(db_session)
        >>> explanation = explainability.generate_explanation(
        ...     user_id=123,
        ...     product_id=456,
        ...     algorithm="collaborative_filtering"
        ... )
        >>> # "Popular with customers who share your tastes"
    """

    def __init__(self, db: Session):
        """
        Initialize explainability service with database session.

        Args:
            db: SQLAlchemy database session for querying user/product data
        """
        self.db = db

        # Template definitions for different recommendation algorithms
        # Each algorithm has multiple templates for variety
        self.algorithm_explanations = {
            # Content-based recommendations
            "content_based": [
                "Based on your interest in {category_name}",
                "Similar to products you've viewed in {category_name}",
                "Because you browsed {category_name} products",
                "Matches your preferences in {category_name}",
                "Related to your {category_name} interests",
            ],
            # Collaborative filtering
            "collaborative_filtering": [
                "Popular with customers who share your tastes",
                "Customers with similar purchases also bought this",
                "Recommended based on similar shopping patterns",
                "Customers like you frequently buy this",
                "Others with your preferences loved this",
            ],
            # Frequently bought together
            "fbt": [
                "Frequently bought with {reference_product}",
                "Great companion to {reference_product}",
                "Customers often pair this with {reference_product}",
                "Complete your purchase of {reference_product}",
                "Perfect match for {reference_product}",
            ],
            # User purchase history based
            "purchase_history": [
                "Based on your previous purchases",
                "Complementary to items you already own",
                "You might need this based on what you've bought",
                "Pairs well with your recent purchase: {reference_product}",
                "Goes great with your {reference_product}",
            ],
            # New arrivals
            "new_arrivals": [
                "New arrival in {category_name}",
                "Just added to our {category_name} collection",
                "Fresh in our {category_name} catalog",
                "New product you might like based on your interests",
                "Latest addition to {category_name}",
            ],
            # Trending products
            "trending": [
                "Currently trending in {category_name}",
                "Popular right now in {category_name}",
                "Everyone's loving this in {category_name}",
                "Trending product similar to your interests",
                "Hot item in {category_name} this week",
            ],
            # Complementary products
            "complementary": [
                "Goes well with products you own",
                "Enhances your previous purchase: {reference_product}",
                "Add this to complete your {category_name} collection",
                "Recommended add-on for {reference_product}",
                "Complements your {category_name} items",
            ],
            # Seasonal recommendations
            "seasonal": [
                "Perfect for this season",
                "Trending this {season_name}",
                "This season's must-have in {category_name}",
                "Popular {season_name} item in {category_name}",
                "{season_name} essential in {category_name}",
            ],
            # Personalized for RFM segment
            "rfm_segment": [
                "Selected for our {segment_name} customers",
                "Specially curated for valued customers like you",
                "Exclusive recommendation for {segment_name} members",
                "Personalized for your shopping pattern",
                "Handpicked for {segment_name} shoppers",
            ],
            # Reorder prediction
            "reorder": [
                "Time to restock? You last bought this {days_ago} days ago",
                "Running low? You typically order this every {cycle_days} days",
                "Based on your purchase cycle, you might need this soon",
                "You might be running out of this item soon",
                "Reorder reminder: Last purchased {days_ago} days ago",
            ],
            # Hybrid recommendations (combining multiple signals)
            "hybrid": [
                "Recommended based on your preferences and similar customers",
                "Top pick combining your history and trending products",
                "Personalized using multiple recommendation factors",
                "Our best match for you",
            ],
            # Fallback generic explanations
            "default": [
                "Recommended for you",
                "Picked just for you",
                "You might be interested in this",
                "Selected based on your preferences",
                "We think you'll like this",
            ],
        }

    def get_user_purchase_history(self, user_id: int, days: int = 90) -> List[Dict]:
        """
        Get user's recent purchase history with product and category details.

        Args:
            user_id: User ID to query
            days: Number of days of history to retrieve (default: 90)

        Returns:
            List of purchase records with product info, categories, dates

        Example:
            >>> history = service.get_user_purchase_history(user_id=123, days=30)
            >>> # [{"product_id": 456, "product_name": "Laptop", ...}, ...]
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        try:
            query = text("""
                SELECT
                    p.id as product_id,
                    p.name as product_name,
                    p.category_id,
                    pc.name as category_name,
                    o.created_at as purchase_date,
                    oi.quantity,
                    COUNT(*) OVER (PARTITION BY p.id) as purchase_count
                FROM order_items oi
                JOIN orders o ON oi.order_id = o.id
                JOIN products p ON oi.product_id = p.id
                LEFT JOIN product_categories pc ON p.category_id = pc.id
                WHERE o.user_id = :user_id
                AND o.status != 'cancelled'
                AND o.created_at >= :cutoff_date
                ORDER BY o.created_at DESC
            """)

            results = self.db.execute(
                query, {"user_id": user_id, "cutoff_date": cutoff_date}
            ).fetchall()

            purchases = [
                {
                    "product_id": row.product_id,
                    "product_name": row.product_name,
                    "category_id": row.category_id,
                    "category_name": row.category_name,
                    "purchase_date": row.purchase_date,
                    "quantity": row.quantity,
                    "purchase_count": row.purchase_count,
                }
                for row in results
            ]

            logger.debug(f"Found {len(purchases)} purchases for user {user_id}")
            return purchases

        except Exception as e:
            logger.error(f"Error getting user purchase history: {e}", exc_info=True)
            return []

    def get_user_viewing_history(self, user_id: int, days: int = 30) -> List[Dict]:
        """
        Get user's recent product viewing history.

        Args:
            user_id: User ID to query
            days: Number of days of history (default: 30)

        Returns:
            List of viewed products with view counts and last viewed dates

        Example:
            >>> views = service.get_user_viewing_history(user_id=123)
            >>> # [{"product_id": 789, "view_count": 3, ...}, ...]
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        try:
            query = text("""
                SELECT
                    p.id as product_id,
                    p.name as product_name,
                    p.category_id,
                    pc.name as category_name,
                    MAX(ub.created_at) as last_viewed,
                    COUNT(*) as view_count
                FROM user_behavior ub
                JOIN products p ON ub.product_id = p.id
                LEFT JOIN product_categories pc ON p.category_id = pc.id
                WHERE ub.user_id = :user_id
                AND ub.event_type = 'product_view'
                AND ub.created_at >= :cutoff_date
                GROUP BY p.id, p.name, p.category_id, pc.name
                ORDER BY last_viewed DESC
            """)

            results = self.db.execute(
                query, {"user_id": user_id, "cutoff_date": cutoff_date}
            ).fetchall()

            viewed_products = [
                {
                    "product_id": row.product_id,
                    "product_name": row.product_name,
                    "category_id": row.category_id,
                    "category_name": row.category_name,
                    "last_viewed": row.last_viewed,
                    "view_count": row.view_count,
                }
                for row in results
            ]

            logger.debug(
                f"Found {len(viewed_products)} viewed products for user {user_id}"
            )
            return viewed_products

        except Exception as e:
            logger.error(f"Error getting user viewing history: {e}", exc_info=True)
            return []

    def get_user_preferred_categories(self, user_id: int) -> List[Tuple[int, str]]:
        """
        Get user's preferred categories based on combined purchase and view history.

        Categories are scored based on:
        - Purchase count (weighted 2x)
        - View count (weighted 1x)

        Args:
            user_id: User ID to query

        Returns:
            List of (category_id, category_name) tuples, ordered by preference

        Example:
            >>> categories = service.get_user_preferred_categories(user_id=123)
            >>> # [(5, "Electronics"), (12, "Books"), ...]
        """
        try:
            query = text("""
                WITH purchase_categories AS (
                    SELECT
                        p.category_id,
                        pc.name as category_name,
                        COUNT(*) as purchase_count
                    FROM order_items oi
                    JOIN orders o ON oi.order_id = o.id
                    JOIN products p ON oi.product_id = p.id
                    LEFT JOIN product_categories pc ON p.category_id = pc.id
                    WHERE o.user_id = :user_id
                    AND o.status != 'cancelled'
                    AND o.created_at >= NOW() - INTERVAL '90 days'
                    GROUP BY p.category_id, pc.name
                ),
                view_categories AS (
                    SELECT
                        p.category_id,
                        pc.name as category_name,
                        COUNT(*) as view_count
                    FROM user_behavior ub
                    JOIN products p ON ub.product_id = p.id
                    LEFT JOIN product_categories pc ON p.category_id = pc.id
                    WHERE ub.user_id = :user_id
                    AND ub.event_type = 'product_view'
                    AND ub.created_at >= NOW() - INTERVAL '90 days'
                    GROUP BY p.category_id, pc.name
                )
                SELECT
                    COALESCE(pc.category_id, vc.category_id) as category_id,
                    COALESCE(pc.category_name, vc.category_name) as category_name,
                    COALESCE(pc.purchase_count, 0) * 2 + COALESCE(vc.view_count, 0) as score
                FROM purchase_categories pc
                FULL OUTER JOIN view_categories vc
                    ON pc.category_id = vc.category_id
                ORDER BY score DESC
                LIMIT 5
            """)

            results = self.db.execute(query, {"user_id": user_id}).fetchall()

            preferred_categories = [
                (row.category_id, row.category_name)
                for row in results
                if row.category_id and row.category_name
            ]

            logger.debug(
                f"Found {len(preferred_categories)} preferred categories for user {user_id}"
            )
            return preferred_categories

        except Exception as e:
            logger.error(f"Error getting user preferred categories: {e}", exc_info=True)
            return []

    def get_product_details(self, product_id: int) -> Optional[Dict]:
        """
        Get product details including category information.

        Args:
            product_id: Product ID to query

        Returns:
            Dictionary with product details, or None if not found

        Example:
            >>> details = service.get_product_details(product_id=456)
            >>> # {"id": 456, "name": "Laptop", "category_name": "Electronics", ...}
        """
        try:
            query = text("""
                SELECT
                    p.id,
                    p.name,
                    p.category_id,
                    pc.name as category_name,
                    p.brand
                FROM products p
                LEFT JOIN product_categories pc ON p.category_id = pc.id
                WHERE p.id = :product_id
            """)

            result = self.db.execute(query, {"product_id": product_id}).fetchone()

            if result:
                return {
                    "id": result.id,
                    "name": result.name,
                    "category_id": result.category_id,
                    "category_name": result.category_name or "products",
                    "brand": result.brand,
                }

            return None

        except Exception as e:
            logger.error(f"Error getting product details: {e}", exc_info=True)
            return None

    def get_reorder_information(self, user_id: int, product_id: int) -> Optional[Dict]:
        """
        Get information about user's purchase cycle for a product.

        Calculates average days between purchases to predict reorder timing.

        Args:
            user_id: User ID
            product_id: Product ID

        Returns:
            Dictionary with last purchase date, days ago, and average cycle days

        Example:
            >>> info = service.get_reorder_information(user_id=123, product_id=456)
            >>> # {"days_ago": 28, "avg_cycle_days": 30, ...}
        """
        try:
            query = text("""
                WITH product_orders AS (
                    SELECT
                        o.created_at as purchase_date,
                        LAG(o.created_at) OVER (ORDER BY o.created_at) as prev_purchase
                    FROM order_items oi
                    JOIN orders o ON oi.order_id = o.id
                    WHERE o.user_id = :user_id
                    AND oi.product_id = :product_id
                    AND o.status != 'cancelled'
                    ORDER BY o.created_at
                )
                SELECT
                    MAX(purchase_date) as last_purchase,
                    AVG(EXTRACT(DAY FROM (purchase_date - prev_purchase))) as avg_days_between
                FROM product_orders
                WHERE prev_purchase IS NOT NULL
            """)

            result = self.db.execute(
                query, {"user_id": user_id, "product_id": product_id}
            ).fetchone()

            if result and result.last_purchase:
                days_ago = (datetime.utcnow() - result.last_purchase).days
                cycle_days = (
                    int(result.avg_days_between) if result.avg_days_between else None
                )

                return {
                    "last_purchase": result.last_purchase,
                    "days_ago": days_ago,
                    "avg_cycle_days": cycle_days,
                }

            return None

        except Exception as e:
            logger.error(f"Error getting reorder information: {e}", exc_info=True)
            return None

    def get_current_season(self) -> str:
        """
        Get current season name based on month.

        Returns:
            Season name: "Spring", "Summer", "Fall", or "Winter"
        """
        month = datetime.utcnow().month

        if 3 <= month <= 5:
            return "Spring"
        elif 6 <= month <= 8:
            return "Summer"
        elif 9 <= month <= 11:
            return "Fall"
        else:
            return "Winter"

    def generate_explanation(
        self,
        user_id: Optional[int],
        product_id: int,
        algorithm: str,
        reference_product_id: Optional[int] = None,
        segment_name: Optional[str] = None,
        score: Optional[float] = None,
    ) -> str:
        """
        Generate personalized explanation for a recommendation.

        Selects appropriate template based on algorithm and fills in
        context-specific variables from user history and product details.

        Args:
            user_id: User ID for personalization (None for anonymous)
            product_id: Recommended product ID
            algorithm: Recommendation algorithm used (e.g., "collaborative_filtering")
            reference_product_id: Optional reference product for context
            segment_name: Optional user segment name (e.g., "high_value")
            score: Optional recommendation score (0-1)

        Returns:
            Personalized explanation string

        Example:
            >>> explanation = service.generate_explanation(
            ...     user_id=123,
            ...     product_id=456,
            ...     algorithm="fbt",
            ...     reference_product_id=789
            ... )
            >>> # "Frequently bought with Wireless Mouse"
        """
        try:
            # Extract algorithm type from composite names like "collaborative_filtering_v2"
            algorithm_type = algorithm.split("_")[0] if "_" in algorithm else algorithm

            # Get templates for this algorithm (or default)
            explanation_templates = self.algorithm_explanations.get(
                algorithm_type, self.algorithm_explanations["default"]
            )

            # Get product details
            product_details = self.get_product_details(product_id)
            category_name = (
                product_details.get("category_name") if product_details else "products"
            )

            # Default replacement values
            replacements = {
                "category_name": category_name,
                "segment_name": segment_name or "valued customer",
                "season_name": self.get_current_season(),
                "reference_product": "your previous purchase",
                "days_ago": "recently",
                "cycle_days": "regularly",
            }

            # Personalize based on user history (if user_id provided)
            if user_id:
                # Get reference product name if provided
                if reference_product_id:
                    ref_product = self.get_product_details(reference_product_id)
                    if ref_product:
                        replacements["reference_product"] = ref_product["name"]

                # For reorder recommendations, get purchase cycle information
                if algorithm_type == "reorder":
                    reorder_info = self.get_reorder_information(user_id, product_id)
                    if reorder_info:
                        replacements["days_ago"] = str(reorder_info["days_ago"])
                        replacements["cycle_days"] = str(
                            reorder_info["avg_cycle_days"] or "30"
                        )

            # Select random template for variety
            explanation_template = random.choice(explanation_templates)

            # Fill in template variables
            explanation = explanation_template
            for key, value in replacements.items():
                explanation = explanation.replace(f"{{{key}}}", str(value))

            return explanation

        except Exception as e:
            logger.error(
                f"Error generating explanation for product {product_id}: {e}",
                exc_info=True,
            )
            return "Recommended for you"

    def enhance_recommendations_with_explanations(
        self,
        user_id: Optional[int],
        recommendations: List[Dict],
        segment_name: Optional[str] = None,
    ) -> List[Dict]:
        """
        Add personalized explanations to a list of recommendations.

        Modifies each recommendation dict to include an 'explanation' field.

        Args:
            user_id: User ID for personalization
            recommendations: List of recommendation dicts
            segment_name: Optional user segment name

        Returns:
            List of recommendations enhanced with explanations

        Example:
            >>> recs = [{"product_id": 123, "algorithm": "collaborative_filtering"}, ...]
            >>> enhanced = service.enhance_recommendations_with_explanations(
            ...     user_id=456,
            ...     recommendations=recs
            ... )
            >>> # Each rec now has 'explanation' field
        """
        logger.info(
            f"Enhancing {len(recommendations)} recommendations with explanations "
            f"for user {user_id}"
        )

        enhanced_recommendations = []

        for rec in recommendations:
            if not isinstance(rec, dict):
                logger.warning(f"Skipping non-dict recommendation: {type(rec)}")
                continue

            try:
                # Extract product ID (support different dict structures)
                product_id = rec.get("product_id") or (
                    rec.get("product", {}).get("id")
                    if isinstance(rec.get("product"), dict)
                    else None
                )

                if not product_id:
                    logger.warning(f"Recommendation missing product_id: {rec.keys()}")
                    continue

                # Extract algorithm and other metadata
                algorithm = rec.get("algorithm", "default")
                reference_product_id = rec.get("reference_product_id")
                score = rec.get("score")

                # Generate explanation
                explanation = self.generate_explanation(
                    user_id=user_id,
                    product_id=product_id,
                    algorithm=algorithm,
                    reference_product_id=reference_product_id,
                    segment_name=segment_name,
                    score=score,
                )

                # Add explanation to recommendation
                rec["explanation"] = explanation
                enhanced_recommendations.append(rec)

            except Exception as e:
                logger.error(f"Error enhancing recommendation: {e}", exc_info=True)
                # Still include the recommendation without explanation
                rec["explanation"] = "Recommended for you"
                enhanced_recommendations.append(rec)

        logger.info(
            f"Successfully enhanced {len(enhanced_recommendations)} recommendations"
        )
        return enhanced_recommendations


# Factory function for dependency injection
def get_explainability_service(db: Session) -> ExplainabilityService:
    """
    Get instance of ExplainabilityService.

    Args:
        db: SQLAlchemy database session

    Returns:
        ExplainabilityService instance

    Example:
        >>> from app.database import get_db
        >>> db = next(get_db())
        >>> service = get_explainability_service(db)
    """
    return ExplainabilityService(db)
