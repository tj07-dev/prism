"""
Comprehensive Recommendation Service integrating trained ML models.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Order, OrderItem, Product, RecommendationResult, User
from app.services.explainability_service import ExplainabilityService
from app.services.ml.als_model_service import ALSModelService
from app.services.ml.content_model_service import ContentModelService
from app.services.ml.hybrid_recommender_service import HybridRecommenderService
from app.services.ml.kmeans_model_service import KMeansModelService
from app.services.ml.lightgbm_model_service import LightGBMModelService
from app.services.ml.ml_model_manager import MLModelManager
from app.services.search_service import SearchService
from app.utils import product_to_json

logger = logging.getLogger(__name__)


class RecommendationService:
    """
    Comprehensive recommendation service that provides personalized product
    recommendations using multiple ML algorithms with explainability.

    Supports:
    - Collaborative Filtering (ALS)
    - Content-Based Filtering (TF-IDF + Embeddings)
    - Hybrid Recommendations
    - Frequently Bought Together (FP-Growth)
    - Vector Similarity
    - Popular/Trending Products
    """

    def __init__(self, db: Session):
        self.db = db
        self.search_service = SearchService(db)
        self.explainability_service = ExplainabilityService(db)
        self.settings = get_settings()

        self.model_manager = MLModelManager(self.settings.MODEL_STORAGE_PATH)
        models_dir = self.model_manager.models_dir

        self.als_service = ALSModelService(models_dir)
        self.content_service = ContentModelService(models_dir)
        self.kmeans_service = KMeansModelService(models_dir)
        self.lightgbm_service = LightGBMModelService(models_dir)
        self.hybrid_service = HybridRecommenderService(db, models_dir)

    async def get_user_recommendations(
        self,
        user_id: Optional[str],
        recommendation_type: str = "homepage",
        limit: int = 10,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get personalized recommendations for user using ML models.

        Args:
            user_id: User ID (None for anonymous users)
            recommendation_type: Type of recommendation (homepage, product_page, cart, etc.)
            limit: Number of recommendations to return
            context: Additional context information

        Returns:
            List of recommendation dictionaries with products and explanations
        """
        logger.info(
            f"Getting user recommendations for user_id={user_id}, type={recommendation_type}, limit={limit}"
        )

        recommendations = []

        # Try ML-based recommendations for authenticated users
        if user_id:
            ml_recommendations = await self._get_ml_recommendations(
                user_id, limit, context
            )
            if ml_recommendations:
                recommendations.extend(ml_recommendations)
                logger.info(f"Got {len(ml_recommendations)} ML-based recommendations")

        # If we need more recommendations, add fallback methods
        if len(recommendations) < limit:
            remaining_limit = limit - len(recommendations)
            fallback_recs = await self._get_fallback_recommendations(
                user_id, remaining_limit, context
            )
            recommendations.extend(fallback_recs)
            logger.info(f"Added {len(fallback_recs)} fallback recommendations")

        # Add recently viewed recommendations if we still need more
        if user_id and len(recommendations) < limit:
            remaining_limit = limit - len(recommendations)
            viewed_recs = await self._get_recently_viewed_recommendations(
                user_id, remaining_limit
            )
            recommendations.extend(viewed_recs)
            logger.info(f"Added {len(viewed_recs)} recently viewed recommendations")

        # Remove duplicates and limit results
        unique_recommendations = self._deduplicate_recommendations(recommendations)
        final_recommendations = unique_recommendations[:limit]

        # Enrich with full product data
        final_recommendations = await self._enrich_recommendations_with_products(
            final_recommendations
        )

        # Add explainability
        segment_name = self._get_user_segment_name(user_id) if user_id else None
        final_recommendations = (
            self.explainability_service.enhance_recommendations_with_explanations(
                user_id=user_id,
                recommendations=final_recommendations,
                segment_name=segment_name,
            )
        )

        # Track recommendations
        if user_id:
            self._track_recommendations(
                user_id, final_recommendations, recommendation_type
            )

        logger.info(
            f"Returning {len(final_recommendations)} final recommendations with explanations"
        )
        return final_recommendations

    async def get_product_recommendations(
        self, product_id: str, limit: int = 10, user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get products similar to given product using ML models.

        Args:
            product_id: Product ID to find similar products for
            limit: Number of recommendations
            user_id: Optional user ID for personalization

        Returns:
            List of similar products with explanations
        """
        logger.info(
            f"Getting product recommendations for product_id={product_id}, limit={limit}, user_id={user_id}"
        )

        recommendations = []

        # Try content-based ML model first (using embeddings + TF-IDF)
        ml_recommendations = await self._get_content_based_ml_recommendations(
            product_id=product_id, user_id=user_id, limit=limit
        )

        if ml_recommendations:
            recommendations.extend(ml_recommendations)
            logger.info(
                f"Got {len(ml_recommendations)} content-based ML recommendations"
            )

        # If ML model doesn't provide enough, use vector similarity fallback
        if len(recommendations) < limit:
            remaining_limit = limit - len(recommendations)
            similar_products = await self.get_similar_products(
                product_id, remaining_limit * 2
            )

            for product in similar_products:
                if len(recommendations) >= limit:
                    break

                recommendations.append(
                    {
                        "product_id": str(product.id),
                        "product": product,
                        "score": 0.7,  # Default similarity score
                        "algorithm": "vector_similarity",
                        "reason": "Similar product features",
                    }
                )

        # Remove duplicates and limit
        unique_recommendations = self._deduplicate_recommendations(recommendations)
        final_recommendations = unique_recommendations[:limit]

        # Enrich with product data
        final_recommendations = await self._enrich_recommendations_with_products(
            final_recommendations
        )

        # Add explainability
        final_recommendations = (
            self.explainability_service.enhance_recommendations_with_explanations(
                user_id=user_id,
                recommendations=final_recommendations,
                segment_name=None,
            )
        )

        # Track recommendations
        if user_id:
            self._track_recommendations(user_id, final_recommendations, "product_page")

        logger.info(
            f"Returning {len(final_recommendations)} product recommendations with explanations"
        )
        return final_recommendations

    async def get_fbt_recommendations(
        self, product_id: str, limit: int = 5, user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get Frequently Bought Together recommendations using FP-Growth algorithm.

        Args:
            product_id: Product ID
            limit: Number of recommendations
            user_id: Optional user ID for tracking

        Returns:
            List of FBT recommendations with confidence scores and explanations
        """
        logger.info(
            f"Getting FBT recommendations for product_id={product_id}, limit={limit}"
        )

        try:
            from app.services.fbt_recommender_service import FBTRecommenderService

            # Initialize FBT service
            fbt_service = FBTRecommenderService(db=self.db)

            # Get FBT recommendations
            fbt_results = fbt_service.get_recommendations(
                product_id=product_id, limit=limit
            )

            recommendations = []
            for fbt_rec in fbt_results:
                product = (
                    self.db.query(Product)
                    .filter(Product.id == fbt_rec["product_id"])
                    .first()
                )
                if product and product.is_active and product.in_stock:
                    recommendations.append(
                        {
                            "product_id": str(product.id),
                            "product": product,
                            "score": fbt_rec.get("confidence", 0.5),
                            "algorithm": "fbt",
                            "reason": f"Frequently bought together (confidence: {fbt_rec.get('confidence', 0.5):.2f})",
                            "reference_product_id": product_id,
                            "confidence": fbt_rec.get("confidence"),
                            "lift": fbt_rec.get("lift"),
                            "support": fbt_rec.get("support"),
                        }
                    )

            # Enrich with product data
            recommendations = await self._enrich_recommendations_with_products(
                recommendations
            )

            # Add explainability
            recommendations = (
                self.explainability_service.enhance_recommendations_with_explanations(
                    user_id=user_id, recommendations=recommendations, segment_name=None
                )
            )

            # Track recommendations
            if user_id:
                self._track_recommendations(user_id, recommendations, "fbt")

            logger.info(f"Returning {len(recommendations)} FBT recommendations")
            return recommendations

        except Exception as e:
            logger.error(f"Error getting FBT recommendations: {e}", exc_info=True)
            # Fallback to similar products
            return await self.get_product_recommendations(product_id, limit, user_id)

    async def get_trending_products(
        self, limit: int = 20, days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Get trending products based on recent views and cart additions.

        Trending = Most viewed/added to cart in last 7 days

        Args:
            limit: Number of products to return
            days: Number of days to look back (default: 7)

        Returns:
            List of trending products with explanations
        """
        logger.info(f"Getting trending products, limit={limit}, days={days}")

        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            # Query for products with most views and cart adds in recent days
            trending_query = text("""
                WITH product_activity AS (
                    SELECT
                        al.resource_id::uuid as product_id,
                        COUNT(CASE WHEN al.action = 'VIEW_PRODUCT' THEN 1 END) as view_count,
                        COUNT(CASE WHEN al.action = 'ADD_TO_CART' THEN 1 END) as cart_add_count
                    FROM audit_logs al
                    WHERE al.resource_type = 'Product'
                    AND al.resource_id IS NOT NULL
                    AND al.resource_id ~* '^[0-9a-f-]{36}$'
                    AND al.action IN ('VIEW_PRODUCT', 'ADD_TO_CART')
                    AND al.created_at >= :cutoff_date
                    GROUP BY al.resource_id
                )
                SELECT
                    p.id,
                    COALESCE(pa.view_count, 0) as view_count,
                    COALESCE(pa.cart_add_count, 0) as cart_add_count,
                    (COALESCE(pa.view_count, 0) + COALESCE(pa.cart_add_count, 0) * 3) as trending_score
                FROM products p
                LEFT JOIN product_activity pa ON p.id = pa.product_id
                WHERE p.is_active = true
                AND p.in_stock = true
                AND (pa.view_count > 0 OR pa.cart_add_count > 0)
                ORDER BY trending_score DESC
                LIMIT :limit
            """)

            results = self.db.execute(
                trending_query, {"cutoff_date": cutoff_date, "limit": limit}
            ).fetchall()

            recommendations = []
            for row in results:
                product = self.db.query(Product).filter(Product.id == row.id).first()
                if product:
                    score = min(1.0, row.trending_score / 100.0)  # Normalize score
                    recommendations.append(
                        {
                            "product_id": str(product.id),
                            "product": product,
                            "score": score,
                            "algorithm": "trending",
                            "reason": f"Trending (viewed {row.view_count} times, {row.cart_add_count} cart adds)",
                            "view_count": row.view_count,
                            "cart_add_count": row.cart_add_count,
                        }
                    )

            # Fallback if no trending data
            if not recommendations:
                logger.info("No trending data found, falling back to popular products")
                return await self.get_popular_products(limit, days=30)

            # Enrich with product data
            recommendations = await self._enrich_recommendations_with_products(
                recommendations
            )

            # Add explainability
            recommendations = (
                self.explainability_service.enhance_recommendations_with_explanations(
                    user_id=None, recommendations=recommendations, segment_name=None
                )
            )

            logger.info(f"Returning {len(recommendations)} trending products")
            return recommendations

        except Exception as e:
            logger.error(f"Error getting trending products: {e}", exc_info=True)
            self.db.rollback()
            # Fallback to popular products
            return await self.get_popular_products(limit, days=30)

    async def get_popular_products(
        self, limit: int = 20, days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get popular products based on recent purchases.

        Popular = Most purchased in last 30 days

        Args:
            limit: Number of products to return
            days: Number of days to look back (default: 30)

        Returns:
            List of popular products with explanations
        """
        logger.info(f"Getting popular products, limit={limit}, days={days}")

        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            # Query for most ordered products in specified time period
            popular_query = text("""
                SELECT
                    p.id,
                    COUNT(oi.id) as order_count,
                    SUM(oi.quantity) as total_quantity
                FROM products p
                JOIN order_items oi ON p.id = oi.product_id
                JOIN orders o ON oi.order_id = o.id
                WHERE p.is_active = true
                AND p.in_stock = true
                AND o.status NOT IN ('cancelled', 'refunded')
                AND o.created_at >= :cutoff_date
                GROUP BY p.id
                ORDER BY order_count DESC, total_quantity DESC
                LIMIT :limit
            """)

            results = self.db.execute(
                popular_query, {"cutoff_date": cutoff_date, "limit": limit}
            ).fetchall()

            recommendations = []
            for row in results:
                product = self.db.query(Product).filter(Product.id == row.id).first()
                if product:
                    score = min(1.0, row.order_count / 100.0)  # Normalize score
                    recommendations.append(
                        {
                            "product_id": str(product.id),
                            "product": product,
                            "score": score,
                            "algorithm": "popular",
                            "reason": f"Popular ({row.order_count} recent orders)",
                            "order_count": row.order_count,
                            "total_quantity": row.total_quantity,
                        }
                    )

            # Fallback if no popular data - return recent products
            if not recommendations:
                logger.info("No popular data found, falling back to new arrivals")
                return await self.get_new_arrivals(limit, days=90)

            # Enrich with product data
            recommendations = await self._enrich_recommendations_with_products(
                recommendations
            )

            # Add explainability
            recommendations = (
                self.explainability_service.enhance_recommendations_with_explanations(
                    user_id=None, recommendations=recommendations, segment_name=None
                )
            )

            logger.info(f"Returning {len(recommendations)} popular products")
            return recommendations

        except Exception as e:
            logger.error(f"Error getting popular products: {e}", exc_info=True)
            self.db.rollback()
            return await self.get_new_arrivals(limit, days=90)

    async def get_new_arrivals(
        self, limit: int = 20, days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get newly added products.

        Args:
            limit: Number of products to return
            days: Number of days to look back (default: 30)

        Returns:
            List of new arrival products with explanations
        """
        logger.info(f"Getting new arrivals, limit={limit}, days={days}")

        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            products = (
                self.db.query(Product)
                .filter(
                    Product.is_active == True,
                    Product.in_stock == True,
                    Product.created_at >= cutoff_date,
                )
                .order_by(Product.created_at.desc())
                .limit(limit)
                .all()
            )

            recommendations = []
            for product in products:
                recommendations.append(
                    {
                        "product_id": str(product.id),
                        "product": product,
                        "score": 0.75,
                        "algorithm": "new_arrivals",
                        "reason": "New arrival",
                    }
                )

            # Enrich with product data
            recommendations = await self._enrich_recommendations_with_products(
                recommendations
            )

            # Add explainability
            recommendations = (
                self.explainability_service.enhance_recommendations_with_explanations(
                    user_id=None, recommendations=recommendations, segment_name=None
                )
            )

            logger.info(f"Returning {len(recommendations)} new arrivals")
            return recommendations

        except Exception as e:
            logger.error(f"Error getting new arrivals: {e}", exc_info=True)
            self.db.rollback()
            return []

    async def get_similar_products(
        self, product_id: str, limit: int = 10
    ) -> List[Product]:
        """
        Get products similar to given product using vector similarity.

        Args:
            product_id: Product ID
            limit: Number of similar products

        Returns:
            List of similar Product objects
        """
        product = self.db.query(Product).filter(Product.id == product_id).first()

        if not product or product.embedding is None:
            logger.warning(f"Product {product_id} not found or has no embedding")
            # Fallback to category-based similarity
            if product:
                similar_products = (
                    self.db.query(Product)
                    .filter(Product.category_id == product.category_id)
                    .filter(Product.id != product_id)
                    .filter(Product.is_active == True)
                    .filter(Product.in_stock == True)
                    .limit(limit)
                    .all()
                )
                return similar_products
            return []

        # Use pgvector's cosine_distance method for vector similarity
        similar_products = (
            self.db.query(Product)
            .filter(Product.id != product_id)
            .filter(Product.is_active == True)
            .filter(Product.is_embedding_generated == True)
            .filter(Product.embedding.isnot(None))
            .order_by(Product.embedding.cosine_distance(product.embedding))
            .limit(limit)
            .all()
        )

        return similar_products

    # Private helper methods

    def _get_or_load_model(self, model_type: str) -> Optional[Dict[str, Any]]:
        """Retrieve an active model, reloading from disk if necessary."""

        model = self.model_manager.get_active_model(model_type)
        if model:
            return model

        model = self.model_manager.load_model(model_type)
        if model:
            self.model_manager.set_active_model(model_type, model)

        return model

    async def _get_ml_recommendations(
        self, user_id: str, limit: int, context: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Get recommendations using trained ML models."""

        recommendations: List[Dict[str, Any]] = []
        seen_product_ids: Set[str] = set()

        def append_unique(candidates: List[Dict[str, Any]]):
            for candidate in candidates:
                product_id = candidate.get("product_id")
                if not product_id or product_id in seen_product_ids:
                    continue
                seen_product_ids.add(product_id)
                recommendations.append(candidate)

        try:
            cf_model = self._get_or_load_model("als")
            content_model = self._get_or_load_model("content")
            user_key = self._normalize_uuid(user_id)
            seed_product_id = None
            if context:
                seed_product_id = context.get("product_id") or context.get(
                    "seed_product_id"
                )

            if cf_model or content_model:
                hybrid_recs = self.hybrid_service.get_recommendations(
                    user_id=user_key,
                    cf_model=cf_model,
                    content_model=content_model,
                    n_recommendations=limit,
                )
                append_unique(self._build_hybrid_recommendations(hybrid_recs))

            if len(recommendations) < limit and cf_model:
                remaining = limit - len(recommendations)
                collaborative_ids = self.als_service.get_recommendations(
                    model_data=cf_model,
                    user_id=user_key,
                    n_recommendations=remaining,
                )
                append_unique(
                    self._build_simple_recommendations(
                        collaborative_ids,
                        algorithm="collaborative_filtering",
                        reason="Customers with similar taste purchased this",
                        base_score=0.95,
                    )
                )

            if len(recommendations) < limit and content_model:
                recent_product = (
                    self._get_user_recent_product(user_id) or seed_product_id
                )
                if recent_product:
                    remaining = limit - len(recommendations)
                    content_ids = self.content_service.get_recommendations(
                        model_data=content_model,
                        product_id=self._normalize_uuid(recent_product),
                        n_recommendations=remaining,
                    )
                    append_unique(
                        self._build_simple_recommendations(
                            content_ids,
                            algorithm="content_based",
                            reason="Similar product attributes",
                            base_score=0.9,
                        )
                    )

        except Exception as exc:
            logger.error("Error getting ML recommendations: %s", exc, exc_info=True)

        return recommendations

    async def _get_collaborative_ml_recommendations(
        self, user_id: str, context: Optional[Dict[str, Any]], limit: int
    ):
        """Get collaborative filtering recommendations using the trained ALS model."""
        try:
            cf_model = self._get_or_load_model("als")
            if not cf_model:
                logger.info("Collaborative filtering model not available in cache")
                return []

            user_key = self._normalize_uuid(user_id)

            if cf_model:
                product_ids = self.als_service.get_recommendations(
                    model_data=cf_model,
                    user_id=user_key,
                    n_recommendations=limit,
                )
                return self._build_simple_recommendations(
                    product_ids,
                    algorithm="collaborative_filtering",
                    reason="Users with similar tastes bought this",
                    base_score=0.95,
                )
        except Exception as exc:
            logger.error(
                "Error getting collaborative ML recommendations: %s", exc, exc_info=True
            )

            return await self._get_simple_collaborative_recommendations(user_id, limit)

    async def _get_content_based_ml_recommendations(
        self, product_id: str, user_id: Optional[str], limit: int
    ) -> List[Dict[str, Any]]:
        """Get content-based recommendations using the trained content model."""

        try:
            content_model = self._get_or_load_model("content")
            if not content_model:
                logger.info(
                    "Content model not available, using vector similarity fallback"
                )
                similar_products = await self.get_similar_products(product_id, limit)
                return [
                    {
                        "product_id": str(product.id),
                        "product": product,
                        "score": 0.75,
                        "algorithm": "content_based",
                        "reason": "Similar product features",
                    }
                    for product in similar_products
                ]

            similar_ids = self.content_service.get_recommendations(
                model_data=content_model,
                product_id=self._normalize_uuid(product_id),
                n_recommendations=limit,
            )

            return self._build_simple_recommendations(
                similar_ids,
                algorithm="content_based",
                reason="Similar product attributes",
                base_score=0.9,
            )

        except Exception as exc:
            logger.error(
                "Error getting content-based ML recommendations: %s", exc, exc_info=True
            )
            return []

    async def _get_fallback_recommendations(
        self, user_id: Optional[str], limit: int, context: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Fallback recommendations when ML models are not available"""
        try:
            if user_id:
                # Try simple collaborative filtering based on order history
                return await self._get_simple_collaborative_recommendations(
                    user_id, limit
                )
            else:
                # Get popular products for anonymous users
                return await self.get_popular_products(limit, days=30)
        except Exception as e:
            logger.error(f"Error getting fallback recommendations: {e}", exc_info=True)
            return await self.get_popular_products(limit, days=30)

    async def _get_simple_collaborative_recommendations(
        self, user_id: str, limit: int
    ) -> List[Dict[str, Any]]:
        """Simple collaborative filtering using SQL"""
        try:
            # Find users who bought similar products
            similar_users_query = text("""
                WITH user_products AS (
                    SELECT DISTINCT oi.product_id
                    FROM orders o
                    JOIN order_items oi ON o.id = oi.order_id
                    WHERE o.user_id = :user_id
                    AND o.status NOT IN ('cancelled', 'refunded')
                ),
                similar_users AS (
                    SELECT o.user_id, COUNT(*) as common_products
                    FROM orders o
                    JOIN order_items oi ON o.id = oi.order_id
                    JOIN user_products up ON oi.product_id = up.product_id
                    WHERE o.user_id != :user_id
                    AND o.status NOT IN ('cancelled', 'refunded')
                    GROUP BY o.user_id
                    HAVING COUNT(*) >= 1
                    ORDER BY common_products DESC
                    LIMIT 10
                )
                SELECT DISTINCT
                    p.id as product_id,
                    COUNT(*) as purchase_count
                FROM similar_users su
                JOIN orders o ON su.user_id = o.user_id
                JOIN order_items oi ON o.id = oi.order_id
                JOIN products p ON oi.product_id = p.id
                WHERE p.is_active = true
                AND p.in_stock = true
                AND p.id NOT IN (
                    SELECT DISTINCT oi2.product_id
                    FROM orders o2
                    JOIN order_items oi2 ON o2.id = oi2.order_id
                    WHERE o2.user_id = :user_id
                )
                GROUP BY p.id
                ORDER BY purchase_count DESC
                LIMIT :limit
            """)

            results = self.db.execute(
                similar_users_query, {"user_id": user_id, "limit": limit}
            ).fetchall()

            recommendations = []
            for row in results:
                product = (
                    self.db.query(Product).filter(Product.id == row.product_id).first()
                )
                if product:
                    score = min(1.0, row.purchase_count / 10.0)  # Normalize score
                    recommendations.append(
                        {
                            "product_id": str(product.id),
                            "product": product,
                            "score": score,
                            "algorithm": "collaborative_filtering",
                            "reason": f"Customers with similar tastes bought this ({row.purchase_count} purchases)",
                        }
                    )

            return recommendations

        except Exception as e:
            logger.error(
                f"Error in simple collaborative recommendations: {e}", exc_info=True
            )
            return []

    async def _get_recently_viewed_recommendations(
        self, user_id: str, limit: int
    ) -> List[Dict[str, Any]]:
        """Get recommendations based on recently viewed products"""
        try:
            # Get user's recently viewed products
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user or not user.viewed_products:
                return []

            viewed_products = user.viewed_products[-10:]  # Last 10 viewed
            recommendations = []

            for product_id in viewed_products:
                if len(recommendations) >= limit:
                    break

                # Get similar products for each viewed product
                similar = await self.get_similar_products(product_id, 3)
                for product in similar:
                    if len(recommendations) >= limit:
                        break

                    recommendations.append(
                        {
                            "product_id": str(product.id),
                            "product": product,
                            "score": 0.6,
                            "algorithm": "recently_viewed",
                            "reason": "Based on recently viewed items",
                        }
                    )

            return recommendations

        except Exception as e:
            logger.error(
                f"Error getting recently viewed recommendations: {e}", exc_info=True
            )
            return []

    def _get_user_recent_product(self, user_id: str) -> Optional[str]:
        """Get user's most recently purchased product"""
        try:
            recent_order = (
                self.db.query(OrderItem)
                .join(Order)
                .filter(Order.user_id == user_id)
                .filter(Order.status.notin_(["cancelled", "refunded"]))
                .order_by(desc(Order.created_at))
                .first()
            )

            return str(recent_order.product_id) if recent_order else None

        except Exception as e:
            logger.error(f"Error getting user recent product: {e}", exc_info=True)
            return None

    def _build_simple_recommendations(
        self,
        product_ids: List[Any],
        algorithm: str,
        reason: str,
        base_score: float = 1.0,
    ) -> List[Dict[str, Any]]:
        """Create recommendation entries from an ordered list of product IDs."""

        recommendations: List[Dict[str, Any]] = []
        total = max(len(product_ids), 1)

        for rank, product_id in enumerate(product_ids):
            score_decay = (total - rank) / total
            recommendations.append(
                {
                    "product_id": str(product_id),
                    "score": max(0.1, base_score * score_decay),
                    "algorithm": algorithm,
                    "reason": reason,
                }
            )

        return recommendations

    def _build_hybrid_recommendations(
        self, hybrid_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Normalize hybrid recommendation payloads."""

        formatted: List[Dict[str, Any]] = []
        for rec in hybrid_results or []:
            product_id = rec.get("product_id")
            if product_id is None:
                continue
            formatted.append(
                {
                    "product_id": str(product_id),
                    "score": float(rec.get("score", 0.5)),
                    "algorithm": rec.get("algorithm", "hybrid"),
                    "reason": "Blend of collaborative and content signals",
                    "details": {
                        "cf_score": rec.get("cf_score"),
                        "content_score": rec.get("content_score"),
                        "trending_score": rec.get("trending_score"),
                    },
                }
            )
        return formatted

    def _get_user_segment_name(self, user_id: Optional[str]) -> Optional[str]:
        """Determine the user's segment using the trained clustering model."""

        if not user_id:
            return None

        model_data = self._get_or_load_model("kmeans")
        if not model_data:
            return None

        rfm_df = model_data.get("rfm_with_clusters")
        if rfm_df is None or getattr(rfm_df, "empty", True):
            return None

        try:
            user_key = self._normalize_uuid(user_id)
            user_row = rfm_df[rfm_df["user_id"] == user_key]
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.debug("Unable to resolve user segment: %s", exc)
            return None

        if user_row.empty:
            return None

        cluster_id = int(user_row.iloc[0]["cluster"])
        return f"cluster_{cluster_id}"

    @staticmethod
    def _normalize_uuid(value: Any) -> Any:
        try:
            return uuid.UUID(str(value))
        except (ValueError, TypeError, AttributeError):
            return value

    async def _enrich_recommendations_with_products(
        self, recommendations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Enrich recommendations with full product data"""
        enriched_recommendations = []

        for rec in recommendations:
            try:
                product_id = rec.get("product_id")
                if not product_id:
                    continue

                # If product is already included and is a Product object, convert to dict
                if "product" in rec and rec["product"]:
                    if not isinstance(rec["product"], dict):
                        rec["product"] = product_to_json(rec["product"])
                    enriched_recommendations.append(rec)
                    continue

                # Otherwise, fetch the product
                product = (
                    self.db.query(Product).filter(Product.id == product_id).first()
                )
                if product and product.is_active and product.in_stock:
                    rec["product"] = product_to_json(product)
                    enriched_recommendations.append(rec)

            except Exception as e:
                logger.error(f"Error enriching recommendation: {e}", exc_info=True)
                continue

        return enriched_recommendations

    def _deduplicate_recommendations(
        self, recommendations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Remove duplicate products from recommendations"""
        seen_products = set()
        unique_recs = []

        for rec in recommendations:
            product_id = rec["product_id"]
            if product_id not in seen_products:
                seen_products.add(product_id)
                unique_recs.append(rec)

        return unique_recs

    def _track_recommendations(
        self,
        user_id: str,
        recommendations: List[Dict[str, Any]],
        recommendation_type: str,
    ):
        """Track recommendations for analytics"""
        try:
            session_id = (
                f"rec_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{user_id[:8]}"
            )

            for i, rec in enumerate(recommendations):
                result = RecommendationResult(
                    user_id=user_id,
                    product_id=rec["product_id"],
                    session_id=session_id,
                    algorithm=rec["algorithm"],
                    score=rec["score"],
                    rank=i + 1,
                    recommendation_type=recommendation_type,
                    context_data={
                        "reason": rec.get("reason", ""),
                        "explanation": rec.get("explanation", ""),
                    },
                )
                self.db.add(result)

            self.db.commit()
            logger.info(
                f"Tracked {len(recommendations)} recommendations for session {session_id}"
            )

        except Exception as e:
            logger.error(f"Error tracking recommendations: {e}", exc_info=True)
            self.db.rollback()

    def track_recommendation_click(
        self, user_id: str, product_id: str, session_id: str, rank: int
    ):
        """Track when user clicks on a recommendation"""
        try:
            # Update the recommendation result with click
            result = (
                self.db.query(RecommendationResult)
                .filter(
                    RecommendationResult.user_id == user_id,
                    RecommendationResult.product_id == product_id,
                    RecommendationResult.session_id == session_id,
                    RecommendationResult.rank == rank,
                )
                .first()
            )

            if result:
                result.clicked = True
                result.clicked_at = datetime.utcnow()
                self.db.commit()
                logger.info(
                    f"Tracked click for recommendation: user={user_id}, product={product_id}, session={session_id}"
                )

        except Exception as e:
            logger.error(f"Error tracking recommendation click: {e}", exc_info=True)
            self.db.rollback()

    def track_recommendation_conversion(
        self, user_id: str, product_id: str, session_id: str, order_id: str
    ):
        """Track when user purchases a recommended product"""
        try:
            # Update all recommendation results for this product in this session
            results = (
                self.db.query(RecommendationResult)
                .filter(
                    RecommendationResult.user_id == user_id,
                    RecommendationResult.product_id == product_id,
                    RecommendationResult.session_id == session_id,
                )
                .all()
            )

            for result in results:
                result.converted = True
                result.converted_at = datetime.utcnow()
                result.order_id = order_id

            self.db.commit()
            logger.info(
                f"Tracked conversion for {len(results)} recommendations: user={user_id}, product={product_id}, order={order_id}"
            )

        except Exception as e:
            logger.error(
                f"Error tracking recommendation conversion: {e}", exc_info=True
            )
            self.db.rollback()
