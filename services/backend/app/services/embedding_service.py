"""
Embedding Service using AWS Bedrock.

This service generates vector embeddings for products using Amazon Titan
embeddings via AWS Bedrock. Embeddings are used for similarity search
and content-based recommendations.
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings
from app.models import Product

settings = get_settings()
logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Service for generating product embeddings using AWS Bedrock.

    Uses Amazon Titan embedding model to create vector representations
    of products based on their text content (name, description, etc.).
    Includes caching to avoid redundant API calls.
    """

    def __init__(self):
        """
        Initialize the embedding service with AWS Bedrock client.

        Sets up boto3 client for Bedrock Runtime and initializes cache.
        """
        self._client = None
        self._cache: Dict[str, Tuple[List[float], datetime]] = {}
        self._cache_ttl = timedelta(seconds=settings.EMBEDDING_CACHE_TTL)
        self._initialize_client()

    def _initialize_client(self) -> None:
        """
        Initialize AWS Bedrock Runtime client.

        Uses credentials from settings (can be from environment variables,
        AWS credentials file, or IAM role).
        """
        try:
            # Initialize boto3 client for Bedrock Runtime
            session_kwargs = {
                "region_name": settings.AWS_REGION,
            }

            # Add credentials if provided in settings
            if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
                session_kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
                session_kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY

            session = boto3.Session(**session_kwargs)
            self._client = session.client("bedrock-runtime")

            logger.info(
                f"AWS Bedrock client initialized successfully in region {settings.AWS_REGION}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize AWS Bedrock client: {str(e)}")
            # Don't raise - allow service to start, will fail on first embedding call
            self._client = None

    async def generate_product_embedding(
        self, product: Product, language: str = "en"
    ) -> Optional[List[float]]:
        """
        Generate embedding vector for a single product.

        Args:
            product: Product model instance to generate embedding for
            language: Language code (currently unused, for future i18n support)

        Returns:
            List of floats representing the embedding vector (1536 dimensions for Titan)
            None if generation fails

        Example:
            >>> embedding_service = EmbeddingService()
            >>> embedding = await embedding_service.generate_product_embedding(product)
            >>> if embedding:
            >>>     # Use embedding for similarity search
        """
        try:
            # Create text representation of product
            text_content = self._create_product_text(product)

            # Check cache first
            cache_key = self._get_cache_key(text_content)
            cached_embedding = self._get_from_cache(cache_key)
            if cached_embedding is not None:
                logger.debug(f"Using cached embedding for product {product.id}")
                return cached_embedding

            # Generate new embedding via Bedrock
            embedding = await self._generate_embedding_bedrock(text_content)

            if embedding:
                # Cache the result
                self._add_to_cache(cache_key, embedding)
                logger.info(f"Generated embedding for product {product.id}")
                return embedding
            else:
                logger.warning(f"Failed to generate embedding for product {product.id}")
                return None

        except Exception as e:
            logger.error(
                f"Error generating embedding for product {product.id}: {str(e)}",
                exc_info=True,
            )
            return None

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding using Amazon Titan"""

        if not text or not text.strip():
            return None

        try:
            return asyncio.run(self._generate_embedding_bedrock(text))
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None

    async def generate_batch_embeddings(
        self, products: List[Product], language: str = "en"
    ) -> Dict[int, List[float]]:
        """
        Generate embeddings for multiple products efficiently.

        Processes products in batches to optimize API usage.

        Args:
            products: List of Product instances
            language: Language code for text processing

        Returns:
            Dictionary mapping product IDs to their embedding vectors

        Example:
            >>> embeddings = await embedding_service.generate_batch_embeddings(products)
            >>> for product_id, embedding in embeddings.items():
            >>>     # Store or use embeddings
        """
        results = {}

        try:
            # Process in batches to respect rate limits
            batch_size = settings.EMBEDDING_BATCH_SIZE

            for i in range(0, len(products), batch_size):
                batch = products[i : i + batch_size]

                # Generate embeddings concurrently for batch
                tasks = [
                    self.generate_product_embedding(product, language)
                    for product in batch
                ]
                embeddings = await asyncio.gather(*tasks, return_exceptions=True)

                # Collect results
                for product, embedding in zip(batch, embeddings):
                    if isinstance(embedding, list):  # Success
                        results[product.id] = embedding
                    elif isinstance(embedding, Exception):  # Error
                        logger.error(
                            f"Error in batch for product {product.id}: {str(embedding)}"
                        )
                    # None means generation failed, already logged

                logger.info(
                    f"Processed batch {i // batch_size + 1}: "
                    f"{len([e for e in embeddings if isinstance(e, list)])} successful, "
                    f"{len([e for e in embeddings if not isinstance(e, list)])} failed"
                )

        except Exception as e:
            logger.error(
                f"Error in batch embedding generation: {str(e)}", exc_info=True
            )

        return results

    async def _generate_embedding_bedrock(self, text: str) -> Optional[List[float]]:
        """
        Call AWS Bedrock to generate embedding for text.

        Args:
            text: Input text to generate embedding for

        Returns:
            Embedding vector as list of floats, or None if failed
        """
        if not self._client:
            logger.error("AWS Bedrock client not initialized")
            return None

        try:
            # Prepare request body for Titan embeddings
            body = json.dumps({"inputText": text})

            # Call Bedrock Runtime
            response = self._client.invoke_model(
                modelId=settings.BEDROCK_EMBEDDING_MODEL,
                contentType="application/json",
                accept="application/json",
                body=body,
            )

            # Parse response
            response_body = json.loads(response["body"].read())

            # Extract embedding vector
            embedding = response_body.get("embedding")

            if embedding and len(embedding) == settings.BEDROCK_EMBEDDING_DIMENSION:
                return embedding
            else:
                logger.error(
                    f"Invalid embedding response: expected {settings.BEDROCK_EMBEDDING_DIMENSION} dimensions, "
                    f"got {len(embedding) if embedding else 0}"
                )
                return None

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            logger.error(
                f"AWS Bedrock ClientError ({error_code}): {error_message}",
                exc_info=True,
            )
            return None

        except BotoCoreError as e:
            logger.error(f"AWS BotoCoreError: {str(e)}", exc_info=True)
            return None

        except Exception as e:
            logger.error(f"Unexpected error calling Bedrock: {str(e)}", exc_info=True)
            return None

    def _create_product_text(self, product: Product) -> str:
        """
        Create comprehensive text representation of product for embedding.

        Combines all relevant product fields into a single text string
        that captures the product's semantic meaning.

        Args:
            product: Product model instance

        Returns:
            Formatted text string representing the product
        """
        text_parts = []

        # Product name (most important)
        if product.name:
            text_parts.append(product.name)

        # Brand information
        if product.brand:
            text_parts.append(f"Brand: {product.brand}")

        # Category information
        if product.category and hasattr(product.category, "name"):
            text_parts.append(f"Category: {product.category.name}")

        # Description (rich semantic content)
        if product.description:
            text_parts.append(product.description)

        # Specification details
        if product.specification:
            text_parts.append(product.specification)

        # Technical details
        if product.technical_details:
            text_parts.append(product.technical_details)

        # Combine all parts with separators
        return " | ".join(text_parts)

    def _get_cache_key(self, text: str) -> str:
        """
        Generate cache key from text content.

        Uses SHA256 hash to create a fixed-length key from variable-length text.

        Args:
            text: Input text to hash

        Returns:
            Hexadecimal string representing the hash
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _get_from_cache(self, cache_key: str) -> Optional[List[float]]:
        """
        Retrieve embedding from cache if available and not expired.

        Args:
            cache_key: Cache key to look up

        Returns:
            Cached embedding vector or None if not found/expired
        """
        if cache_key in self._cache:
            embedding, timestamp = self._cache[cache_key]

            # Check if cache entry is still valid
            if datetime.now() - timestamp < self._cache_ttl:
                return embedding
            else:
                # Remove expired entry
                del self._cache[cache_key]

        return None

    def _add_to_cache(self, cache_key: str, embedding: List[float]) -> None:
        """
        Add embedding to cache with current timestamp.

        Args:
            cache_key: Cache key to store under
            embedding: Embedding vector to cache
        """
        self._cache[cache_key] = (embedding, datetime.now())

        # Simple cache size management: remove oldest if too large
        if len(self._cache) > 10000:  # Arbitrary limit
            # Remove oldest 10% of entries
            sorted_keys = sorted(self._cache.keys(), key=lambda k: self._cache[k][1])
            for key in sorted_keys[: len(sorted_keys) // 10]:
                del self._cache[key]

    def clear_cache(self) -> None:
        """
        Clear all cached embeddings.

        Useful for testing or when embedding model changes.
        """
        self._cache.clear()
        logger.info("Embedding cache cleared")

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get statistics about cache usage.

        Returns:
            Dictionary with cache statistics (size, valid entries)
        """
        now = datetime.now()
        valid_entries = sum(
            1
            for _, timestamp in self._cache.values()
            if now - timestamp < self._cache_ttl
        )

        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_entries,
            "expired_entries": len(self._cache) - valid_entries,
        }


# Singleton instance for reuse across the application
_embedding_service_instance = None


def get_embedding_service() -> EmbeddingService:
    """
    Get singleton instance of EmbeddingService.

    Returns:
        EmbeddingService instance

    Example:
        >>> service = get_embedding_service()
        >>> embedding = await service.generate_product_embedding(product)
    """
    global _embedding_service_instance
    if _embedding_service_instance is None:
        _embedding_service_instance = EmbeddingService()
    return _embedding_service_instance
