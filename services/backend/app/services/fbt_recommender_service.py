"""
FP-Growth Based Frequently Bought Together (FBT) Recommender Service.

This module implements association rule mining using the FP-Growth algorithm
to generate "Frequently Bought Together" product recommendations. FP-Growth
discovers patterns in transaction data to identify products commonly purchased
together.

The algorithm:
1. Mines frequent itemsets from transaction history
2. Generates association rules (if X is purchased, then Y is likely purchased)
3. Ranks recommendations by confidence, lift, and support metrics

This is particularly effective for:
- Product bundles
- Cross-sell recommendations
- Shopping cart suggestions
"""

import json
import logging
import os
from typing import Dict, List, Optional

import pandas as pd
from mlxtend.frequent_patterns import association_rules, fpgrowth
from mlxtend.preprocessing import TransactionEncoder
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class FBTRecommenderService:
    """
    Service for Frequently Bought Together recommendations using FP-Growth.

    FP-Growth (Frequent Pattern Growth) is an efficient algorithm for mining
    frequent itemsets and association rules from transaction data. It builds
    a compressed representation of the database (FP-tree) and extracts patterns
    without generating candidate itemsets.

    Key Metrics:
    - **Support**: Frequency of itemset in all transactions
    - **Confidence**: Probability that consequent is purchased given antecedent
    - **Lift**: How much more likely consequent is purchased with antecedent
      (lift > 1 indicates positive correlation)

    Example Usage:
        >>> fbt_service = FBTRecommenderService(db_session)
        >>> fbt_service.train()  # Train on transaction data
        >>> recs = fbt_service.get_recommendations(product_id=123, limit=5)
        >>> # [{"product_id": 456, "confidence": 0.75, "lift": 2.3, ...}, ...]
    """

    def __init__(
        self,
        db: Session,
        min_support: Optional[float] = None,
        min_confidence: Optional[float] = None,
        min_lift: Optional[float] = None,
        max_itemset_size: Optional[int] = None,
        cache_file: Optional[str] = None,
    ):
        """
        Initialize FBT recommender with configurable parameters.

        Args:
            db: SQLAlchemy database session
            min_support: Minimum support for frequent itemsets (default from settings)
            min_confidence: Minimum confidence for association rules (default from settings)
            min_lift: Minimum lift threshold for rules (default from settings)
            max_itemset_size: Maximum itemset size to consider (default from settings)
            cache_file: Path to cache file for saving/loading trained model

        Example:
            >>> fbt_service = FBTRecommenderService(
            ...     db=db_session,
            ...     min_support=0.01,  # 1% of transactions
            ...     min_confidence=0.3,  # 30% confidence
            ...     min_lift=1.0  # Positive correlation
            ... )
        """
        self.db = db

        # Use settings defaults if not provided
        self.min_support = min_support or settings.FBT_MIN_SUPPORT
        self.min_confidence = min_confidence or settings.FBT_MIN_CONFIDENCE
        self.min_lift = min_lift or settings.FBT_MIN_LIFT
        self.max_itemset_size = max_itemset_size or settings.FBT_MAX_ITEMSET_SIZE

        # Cache file for saving trained model
        self.cache_file = cache_file or os.path.join(
            settings.MODEL_STORAGE_PATH, "fbt_recommendations.json"
        )

        # Recommendation map: {product_id: [recommended_products]}
        self.fbt_map: Dict[str, List[Dict]] = {}

        # Training status
        self.is_trained = False

        logger.info(
            f"Initialized FBT Recommender: support={self.min_support}, "
            f"confidence={self.min_confidence}, lift={self.min_lift}"
        )

    def load_transactions(self) -> List[List[str]]:
        """
        Load transaction data from database and format for FP-Growth.

        Extracts all completed orders and their items, grouping by order_id
        to create transaction baskets. Only multi-item transactions are kept
        since single-item orders don't provide association patterns.

        Returns:
            List of transactions, where each transaction is a list of product IDs

        Example:
            >>> transactions = service.load_transactions()
            >>> # [['101', '102', '103'], ['101', '105'], ...]

        Raises:
            Exception: If database query fails
        """
        try:
            query = text("""
                SELECT o.id as order_id, oi.product_id
                FROM orders o
                JOIN order_items oi ON o.id = oi.order_id
                WHERE o.status != 'cancelled'
                AND o.status != 'pending'
                ORDER BY o.id
            """)

            # Execute query and load into DataFrame
            df = pd.read_sql(query, self.db.bind)

            if df.empty:
                logger.warning("No transaction data found in database")
                return []

            logger.info(f"Loaded {len(df)} order items from database")

            # Group by order to create transaction baskets
            grouped = df.groupby("order_id")["product_id"].apply(
                lambda x: list(set(str(i) for i in x))
            )

            # Only keep transactions with 2+ products (association needs pairs)
            transactions = [t for t in grouped.tolist() if len(t) > 1]

            logger.info(
                f"Created {len(transactions)} multi-item transactions "
                f"from {len(grouped)} total orders "
                f"({len(transactions) / len(grouped) * 100:.1f}% multi-item)"
            )

            return transactions

        except Exception as e:
            logger.error(f"Failed to load transactions: {e}", exc_info=True)
            raise

    def mine_association_rules(self, transactions: List[List[str]]) -> None:
        """
        Apply FP-Growth algorithm and generate association rules.

        Process:
        1. Encode transactions into binary matrix (TransactionEncoder)
        2. Mine frequent itemsets using FP-Growth
        3. Generate association rules from frequent itemsets
        4. Build recommendation map from rules

        Args:
            transactions: List of transaction baskets (each basket is list of product IDs)

        Raises:
            ValueError: If insufficient transactions or no patterns found
            Exception: If FP-Growth algorithm fails
        """
        if len(transactions) < 10:
            raise ValueError(
                f"Insufficient transactions ({len(transactions)}). Need at least 10."
            )

        try:
            logger.info(f"Mining patterns from {len(transactions)} transactions...")

            # Step 1: Encode transactions into binary matrix
            # Each column represents a product, each row a transaction
            # Cell is 1 if product in transaction, 0 otherwise
            te = TransactionEncoder()
            te_array = te.fit(transactions).transform(transactions)
            df_encoded = pd.DataFrame(te_array, columns=te.columns_)

            logger.info(
                f"Encoded transactions: {df_encoded.shape[0]} transactions x "
                f"{df_encoded.shape[1]} unique products"
            )

            # Step 2: Find frequent itemsets using FP-Growth
            # These are product combinations that appear frequently
            frequent_itemsets = fpgrowth(
                df_encoded,
                min_support=self.min_support,
                use_colnames=True,
                max_len=self.max_itemset_size,
            )

            if frequent_itemsets.empty:
                logger.warning(
                    f"No frequent itemsets found with min_support={self.min_support}. "
                    f"Try lowering the threshold."
                )
                return

            logger.info(
                f"Found {len(frequent_itemsets)} frequent itemsets "
                f"(support >= {self.min_support})"
            )

            # Step 3: Generate association rules
            # Format: IF antecedent THEN consequent
            # Example: IF {product_A} THEN {product_B}
            rules = association_rules(
                frequent_itemsets,
                metric="confidence",
                min_threshold=self.min_confidence,
            )

            if rules.empty:
                logger.warning(
                    f"No association rules generated with min_confidence={self.min_confidence}. "
                    f"Try lowering the threshold."
                )
                return

            # Filter by lift threshold
            rules = rules[rules["lift"] >= self.min_lift]

            if rules.empty:
                logger.warning(f"No rules passed min_lift={self.min_lift} threshold")
                return

            logger.info(
                f"Generated {len(rules)} association rules "
                f"(confidence >= {self.min_confidence}, lift >= {self.min_lift})"
            )

            # Step 4: Build recommendation map from rules
            self._build_recommendation_map(rules)

        except Exception as e:
            logger.error(f"Failed to mine association rules: {e}", exc_info=True)
            raise

    def _build_recommendation_map(self, rules: pd.DataFrame) -> None:
        """
        Convert association rules DataFrame into recommendation map.

        Extracts single-item -> single-item rules (most useful for recommendations)
        and organizes them by product ID for fast lookup.

        Args:
            rules: DataFrame of association rules from mlxtend

        Note:
            Rules are sorted by confidence (primary), then lift (secondary),
            then support (tertiary) to prioritize most reliable recommendations.
        """
        self.fbt_map = {}
        processed_rules = 0

        # Process each rule
        for _, row in rules.iterrows():
            antecedents = list(row["antecedents"])
            consequents = list(row["consequents"])

            # We want single-item rules: "if you buy X, you'll also buy Y"
            # Multi-item rules are harder to use in practice
            if len(antecedents) == 1 and len(consequents) == 1:
                product_id = antecedents[0]  # Product we're making recommendations for
                recommended_id = consequents[0]  # Product being recommended

                # Create recommendation entry
                recommendation = {
                    "product_id": recommended_id,
                    "confidence": round(float(row["confidence"]), 4),
                    "lift": round(float(row["lift"]), 4),
                    "support": round(float(row["support"]), 4),
                }

                # Add to map
                if product_id not in self.fbt_map:
                    self.fbt_map[product_id] = []

                self.fbt_map[product_id].append(recommendation)
                processed_rules += 1

        # Sort recommendations for each product by quality metrics
        for product_id in self.fbt_map:
            self.fbt_map[product_id] = sorted(
                self.fbt_map[product_id],
                key=lambda x: (-x["confidence"], -x["lift"], -x["support"]),
            )

        logger.info(
            f"Built recommendation map for {len(self.fbt_map)} products "
            f"from {processed_rules} single-item rules"
        )

    def save_to_cache(self) -> None:
        """
        Save trained recommendation map to JSON cache file.

        Enables fast loading without retraining. Cache includes metadata
        about training parameters for validation.

        Example:
            >>> service.train()
            >>> service.save_to_cache()  # Save for future use
        """
        if not self.cache_file:
            logger.info("No cache file specified, skipping save")
            return

        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)

            # Include metadata for validation
            cache_data = {
                "fbt_map": self.fbt_map,
                "metadata": {
                    "min_support": self.min_support,
                    "min_confidence": self.min_confidence,
                    "min_lift": self.min_lift,
                    "max_itemset_size": self.max_itemset_size,
                    "n_products": len(self.fbt_map),
                    "trained_at": pd.Timestamp.now().isoformat(),
                },
            }

            with open(self.cache_file, "w") as f:
                json.dump(cache_data, f, indent=2)

            logger.info(
                f"Saved recommendation map to {self.cache_file} "
                f"({len(self.fbt_map)} products)"
            )

        except Exception as e:
            logger.error(f"Failed to save recommendation map: {e}", exc_info=True)

    def load_from_cache(self) -> bool:
        """
        Load trained recommendation map from JSON cache file.

        Returns:
            True if successfully loaded from cache, False otherwise

        Example:
            >>> service = FBTRecommenderService(db)
            >>> if service.load_from_cache():
            >>>     # Use cached model
            >>>     recs = service.get_recommendations(product_id=123)
            >>> else:
            >>>     # Train new model
            >>>     service.train()
        """
        if not self.cache_file:
            return False

        try:
            with open(self.cache_file, "r") as f:
                cache_data = json.load(f)

            # Load recommendation map
            self.fbt_map = cache_data.get("fbt_map", {})

            # Log metadata if available
            metadata = cache_data.get("metadata", {})
            if metadata:
                logger.info(
                    f"Loaded recommendation map from {self.cache_file}: "
                    f"{metadata.get('n_products', 0)} products, "
                    f"trained at {metadata.get('trained_at', 'unknown')}"
                )
            else:
                logger.info(
                    f"Loaded recommendation map from {self.cache_file} "
                    f"({len(self.fbt_map)} products)"
                )

            self.is_trained = True
            return True

        except FileNotFoundError:
            logger.info(f"Cache file {self.cache_file} not found")
            return False

        except Exception as e:
            logger.error(f"Failed to load recommendation map: {e}", exc_info=True)
            return False

    def train(self, force_retrain: bool = False) -> None:
        """
        Train the FP-Growth model and generate recommendations.

        Loads from cache if available (unless force_retrain=True),
        otherwise trains on current transaction data and saves to cache.

        Args:
            force_retrain: If True, ignore cache and retrain from scratch

        Example:
            >>> service.train()  # Use cache if available
            >>> service.train(force_retrain=True)  # Always retrain

        Raises:
            Exception: If training fails (insufficient data, database error, etc.)
        """
        # Try to load from cache first (unless forcing retrain)
        if not force_retrain and self.load_from_cache():
            return

        logger.info("Training FP-Growth model on transaction data...")

        try:
            # Load transaction data from database
            transactions = self.load_transactions()

            if len(transactions) < 10:
                raise ValueError(
                    f"Insufficient transactions for training ({len(transactions)}). "
                    f"Need at least 10 multi-item orders."
                )

            # Mine association rules using FP-Growth
            self.mine_association_rules(transactions)

            # Save results to cache for future use
            self.save_to_cache()

            self.is_trained = True
            logger.info("FP-Growth training completed successfully")

        except Exception as e:
            logger.error(f"Failed to train FP-Growth model: {e}", exc_info=True)
            raise

    def get_recommendations(self, product_id: int, limit: int = 5) -> List[Dict]:
        """
        Get 'Frequently Bought Together' recommendations for a product.

        Returns products commonly purchased together with the given product,
        ranked by confidence, lift, and support metrics.

        Args:
            product_id: Product ID to get recommendations for
            limit: Maximum number of recommendations to return

        Returns:
            List of recommendation dicts with product_id, confidence, lift, support

        Example:
            >>> recs = service.get_recommendations(product_id=123, limit=5)
            >>> # [
            >>> #   {"product_id": "456", "confidence": 0.75, "lift": 2.3, "support": 0.05},
            >>> #   {"product_id": "789", "confidence": 0.68, "lift": 1.9, "support": 0.04},
            >>> #   ...
            >>> # ]

        Note:
            Returns empty list if:
            - Model not trained
            - No recommendations available for this product
        """
        # Ensure model is trained
        if not self.is_trained:
            logger.info("Model not trained, training now...")
            self.train()

        # Convert product_id to string (stored as strings in map)
        product_id_str = str(product_id)

        # Return recommendations if available
        if product_id_str in self.fbt_map:
            recommendations = self.fbt_map[product_id_str][:limit]
            logger.debug(
                f"Found {len(recommendations)} FBT recommendations for product {product_id}"
            )
            return recommendations

        # No recommendations found for this product
        logger.debug(f"No FBT recommendations available for product {product_id}")
        return []

    def get_batch_recommendations(
        self, product_ids: List[int], limit: int = 5
    ) -> Dict[int, List[Dict]]:
        """
        Get recommendations for multiple products efficiently.

        Args:
            product_ids: List of product IDs
            limit: Maximum recommendations per product

        Returns:
            Dictionary mapping product IDs to their recommendations

        Example:
            >>> recs = service.get_batch_recommendations([123, 456, 789])
            >>> # {
            >>> #   123: [{...}, {...}],
            >>> #   456: [{...}, {...}],
            >>> #   789: []
            >>> # }
        """
        results = {}

        for product_id in product_ids:
            results[product_id] = self.get_recommendations(product_id, limit)

        return results

    def get_model_statistics(self) -> Dict:
        """
        Get statistics about the trained FBT model.

        Returns:
            Dictionary with model statistics

        Example:
            >>> stats = service.get_model_statistics()
            >>> # {
            >>> #   "is_trained": True,
            >>> #   "n_products_with_recs": 150,
            >>> #   "total_recommendations": 487,
            >>> #   "avg_recs_per_product": 3.25,
            >>> #   ...
            >>> # }
        """
        if not self.is_trained:
            return {"is_trained": False}

        total_recs = sum(len(recs) for recs in self.fbt_map.values())
        n_products = len(self.fbt_map)

        return {
            "is_trained": True,
            "n_products_with_recommendations": n_products,
            "total_recommendations": total_recs,
            "avg_recommendations_per_product": round(total_recs / n_products, 2)
            if n_products > 0
            else 0,
            "min_support": self.min_support,
            "min_confidence": self.min_confidence,
            "min_lift": self.min_lift,
            "max_itemset_size": self.max_itemset_size,
        }


# Factory function for dependency injection
def get_fbt_recommender_service(db: Session) -> FBTRecommenderService:
    """
    Get instance of FBTRecommenderService.

    Args:
        db: SQLAlchemy database session

    Returns:
        FBTRecommenderService instance

    Example:
        >>> from app.database import get_db
        >>> db = next(get_db())
        >>> service = get_fbt_recommender_service(db)
        >>> service.train()
        >>> recs = service.get_recommendations(product_id=123)
    """
    return FBTRecommenderService(db)
