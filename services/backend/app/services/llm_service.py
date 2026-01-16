"""
LLM Service using AWS Bedrock.

This service provides text generation capabilities using Claude via AWS Bedrock.
Used for generating recommendation explanations, product descriptions, and other
natural language content.
"""

import json
import logging
from enum import Enum
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class PromptTemplate(Enum):
    """
    Predefined prompt templates for different use cases.
    """

    # Recommendation explanation templates
    COLLABORATIVE_EXPLANATION = """Based on users with similar preferences who also liked:
{similar_products}

We recommend: {recommended_product}

Explain why this recommendation makes sense in a friendly, concise way (2-3 sentences)."""

    CONTENT_BASED_EXPLANATION = """Product: {recommended_product}

This product is similar to items the user has viewed:
{viewed_products}

Similarities include: {similarity_factors}

Explain why this recommendation fits the user's interests in a friendly, concise way (2-3 sentences)."""

    TRENDING_EXPLANATION = """Product: {recommended_product}

This product is trending because:
- {trend_metrics}

Explain why this is a popular choice right now in a friendly, concise way (1-2 sentences)."""

    FBT_EXPLANATION = """Product: {recommended_product}

Customers who bought {anchor_product} frequently also purchase this item.

Explain why these products work well together in a friendly, concise way (1-2 sentences)."""

    # Product description generation
    PRODUCT_DESCRIPTION = """Generate a compelling product description for:

Name: {product_name}
Brand: {brand}
Category: {category}
Key Features: {features}

Create an engaging description (3-4 sentences) that highlights the benefits and appeals to customers."""

    # User segment description
    SEGMENT_DESCRIPTION = """User Segment Profile:
- Segment ID: {segment_id}
- RFM Score: {rfm_score}
- Purchase Behavior: {behavior_summary}
- Demographics: {demographics}

Generate a concise segment description (2-3 sentences) for marketing purposes."""

    # Personalized ad copy generation
    PERSONALIZED_AD_COPY = """Generate compelling promotional ad copy for:

Target Segment: Cluster {cluster_id}
Product Category: {product_category}
{additional_context}

Create engaging promotional text (3-4 sentences) that:
1. Appeals to the target segment
2. Highlights key benefits of the product category
3. Includes a clear call-to-action
4. Is persuasive and conversion-focused"""


class LLMService:
    """
    Service for text generation using AWS Bedrock LLM (Claude).

    Provides methods for generating recommendation explanations,
    product descriptions, and other natural language content.
    """

    def __init__(self):
        """
        Initialize the LLM service with AWS Bedrock client.

        Sets up boto3 client for Bedrock Runtime.
        """
        self._client = None
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
                f"AWS Bedrock LLM client initialized successfully in region {settings.AWS_REGION}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize AWS Bedrock LLM client: {str(e)}")
            self._client = None

    async def generate_text(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> Optional[str]:
        """
        Generate text using Claude via AWS Bedrock.

        Args:
            prompt: The input prompt for text generation
            max_tokens: Maximum tokens to generate (defaults to settings value)
            temperature: Sampling temperature 0.0-1.0 (defaults to settings value)
            top_p: Top-p sampling parameter (defaults to settings value)

        Returns:
            Generated text string, or None if generation fails

        Example:
            >>> llm_service = LLMService()
            >>> text = await llm_service.generate_text("Explain why...")
        """
        response = await self.invoke_model(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": prompt,
                        }
                    ],
                }
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
        )

        return self.extract_text(response)

    async def invoke_model(
        self,
        *,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Invoke the configured Bedrock model with raw messages payload."""
        if not self._client:
            logger.error("AWS Bedrock LLM client not initialized")
            return None

        # Use defaults from settings if not provided
        max_tokens = max_tokens or settings.LLM_MAX_TOKENS
        temperature = (
            temperature if temperature is not None else settings.LLM_TEMPERATURE
        )
        top_p = top_p if top_p is not None else settings.LLM_TOP_P

        try:
            # Prepare request body for Claude
            body = json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "top_p": top_p,
                    "messages": messages,
                    **kwargs,
                }
            )

            # Call Bedrock Runtime
            response = self._client.invoke_model(
                modelId=settings.BEDROCK_LLM_MODEL,
                contentType="application/json",
                accept="application/json",
                body=body,
            )

            # Parse response
            response_body = json.loads(response["body"].read())
            return response_body

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
            logger.error(
                f"Unexpected error calling Bedrock LLM: {str(e)}", exc_info=True
            )
            return None

    @staticmethod
    def extract_text(response: Optional[Dict[str, Any]]) -> Optional[str]:
        """Extract concatenated text segments from a Bedrock response."""
        if not response:
            return None

        content = response.get("content", [])
        if not isinstance(content, list):
            logger.error("Unexpected LLM response content format")
            return None

        text_segments: List[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_value = part.get("text")
                if isinstance(text_value, str):
                    text_segments.append(text_value.strip())

        if not text_segments:
            return None

        return "\n".join(segment for segment in text_segments if segment)

    async def generate_recommendation_explanation(
        self,
        recommendation_type: str,
        recommended_product: str,
        context: Dict[str, any],
    ) -> Optional[str]:
        """
        Generate natural language explanation for a recommendation.

        Args:
            recommendation_type: Type of recommendation (collaborative, content-based, trending, fbt)
            recommended_product: Name/description of the recommended product
            context: Dictionary containing context information for the explanation

        Returns:
            Generated explanation string, or None if generation fails

        Example:
            >>> explanation = await llm_service.generate_recommendation_explanation(
            ...     recommendation_type="collaborative",
            ...     recommended_product="Wireless Mouse",
            ...     context={
            ...         "similar_products": ["Keyboard", "Monitor"],
            ...     }
            ... )
        """
        try:
            # Select appropriate template
            template_map = {
                "collaborative": PromptTemplate.COLLABORATIVE_EXPLANATION,
                "content_based": PromptTemplate.CONTENT_BASED_EXPLANATION,
                "trending": PromptTemplate.TRENDING_EXPLANATION,
                "fbt": PromptTemplate.FBT_EXPLANATION,
            }

            template = template_map.get(recommendation_type.lower())
            if not template:
                logger.warning(f"Unknown recommendation type: {recommendation_type}")
                return None

            # Format prompt with context
            prompt = template.value.format(
                recommended_product=recommended_product, **context
            )

            # Generate explanation
            explanation = await self.generate_text(
                prompt=prompt,
                max_tokens=200,  # Shorter for explanations
                temperature=0.7,  # Moderate creativity
            )

            return explanation

        except KeyError as e:
            logger.error(
                f"Missing required context key for explanation: {str(e)}",
                exc_info=True,
            )
            return None
        except Exception as e:
            logger.error(
                f"Error generating recommendation explanation: {str(e)}",
                exc_info=True,
            )
            return None

    async def generate_product_description(
        self,
        product_name: str,
        brand: Optional[str] = None,
        category: Optional[str] = None,
        features: Optional[str] = None,
    ) -> Optional[str]:
        """
        Generate a compelling product description.

        Args:
            product_name: Name of the product
            brand: Brand name (optional)
            category: Product category (optional)
            features: Key features (optional)

        Returns:
            Generated product description, or None if generation fails

        Example:
            >>> description = await llm_service.generate_product_description(
            ...     product_name="Wireless Bluetooth Headphones",
            ...     brand="TechAudio",
            ...     category="Electronics",
            ...     features="Noise cancellation, 30-hour battery, comfortable fit"
            ... )
        """
        try:
            # Format prompt
            prompt = PromptTemplate.PRODUCT_DESCRIPTION.value.format(
                product_name=product_name,
                brand=brand or "N/A",
                category=category or "N/A",
                features=features or "N/A",
            )

            # Generate description
            description = await self.generate_text(
                prompt=prompt,
                max_tokens=300,
                temperature=0.8,  # More creative for marketing copy
            )

            return description

        except Exception as e:
            logger.error(
                f"Error generating product description: {str(e)}", exc_info=True
            )
            return None

    async def generate_segment_description(
        self,
        segment_id: str,
        rfm_score: str,
        behavior_summary: str,
        demographics: Optional[str] = None,
    ) -> Optional[str]:
        """
        Generate description for a user segment.

        Args:
            segment_id: Segment identifier
            rfm_score: RFM score string (e.g., "555" for best customers)
            behavior_summary: Summary of purchase behavior
            demographics: Optional demographic information

        Returns:
            Generated segment description, or None if generation fails

        Example:
            >>> description = await llm_service.generate_segment_description(
            ...     segment_id="high_value",
            ...     rfm_score="555",
            ...     behavior_summary="Frequent buyers of premium electronics",
            ...     demographics="Tech-savvy, 25-40 years old"
            ... )
        """
        try:
            # Format prompt
            prompt = PromptTemplate.SEGMENT_DESCRIPTION.value.format(
                segment_id=segment_id,
                rfm_score=rfm_score,
                behavior_summary=behavior_summary,
                demographics=demographics or "N/A",
            )

            # Generate description
            description = await self.generate_text(
                prompt=prompt,
                max_tokens=250,
                temperature=0.7,
            )

            return description

        except Exception as e:
            logger.error(
                f"Error generating segment description: {str(e)}", exc_info=True
            )
            return None

    async def generate_personalized_ad_copy(
        self,
        cluster_id: int,
        target_product_category: str,
        additional_context: Optional[str] = None,
    ) -> Optional[str]:
        """
        Generate personalized promotional ad copy for a user segment.

        Args:
            cluster_id: User cluster/segment ID
            target_product_category: Target product category for the promotion
            additional_context: Optional additional context for the ad

        Returns:
            Generated ad copy string, or None if generation fails

        Example:
            >>> ad_copy = await llm_service.generate_personalized_ad_copy(
            ...     cluster_id=5,
            ...     target_product_category="Electronics",
            ...     additional_context="Holiday sale, 20% off"
            ... )
        """
        try:
            # Format additional context
            context_str = ""
            if additional_context:
                context_str = f"Additional Context: {additional_context}"

            # Format prompt
            prompt = PromptTemplate.PERSONALIZED_AD_COPY.value.format(
                cluster_id=cluster_id,
                product_category=target_product_category,
                additional_context=context_str,
            )

            # Generate ad copy
            ad_copy = await self.generate_text(
                prompt=prompt,
                max_tokens=300,
                temperature=0.8,  # More creative for marketing copy
            )

            return ad_copy

        except Exception as e:
            logger.error(
                f"Error generating personalized ad copy: {str(e)}", exc_info=True
            )
            return None

    async def generate_batch_explanations(
        self,
        explanations_data: List[Dict[str, any]],
    ) -> Dict[int, Optional[str]]:
        """
        Generate multiple explanations efficiently.

        Args:
            explanations_data: List of dicts with keys:
                - index: Unique identifier for the explanation
                - recommendation_type: Type of recommendation
                - recommended_product: Product name
                - context: Context dict

        Returns:
            Dictionary mapping indices to generated explanations

        Example:
            >>> explanations = await llm_service.generate_batch_explanations([
            ...     {
            ...         "index": 0,
            ...         "recommendation_type": "collaborative",
            ...         "recommended_product": "Product A",
            ...         "context": {...}
            ...     },
            ...     ...
            ... ])
        """
        results = {}

        try:
            # Generate all explanations concurrently
            tasks = []
            for data in explanations_data:
                task = self.generate_recommendation_explanation(
                    recommendation_type=data["recommendation_type"],
                    recommended_product=data["recommended_product"],
                    context=data["context"],
                )
                tasks.append((data["index"], task))

            # Await all tasks
            for index, task in tasks:
                try:
                    explanation = await task
                    results[index] = explanation
                except Exception as e:
                    logger.error(f"Error generating explanation {index}: {str(e)}")
                    results[index] = None

        except Exception as e:
            logger.error(
                f"Error in batch explanation generation: {str(e)}", exc_info=True
            )

        return results

    def create_fallback_explanation(
        self,
        recommendation_type: str,
        product_name: str,
    ) -> str:
        """
        Create a simple fallback explanation when LLM generation fails.

        Args:
            recommendation_type: Type of recommendation
            product_name: Name of recommended product

        Returns:
            Simple explanation string

        Example:
            >>> explanation = llm_service.create_fallback_explanation("collaborative", "Product A")
        """
        fallback_templates = {
            "collaborative": f"Customers with similar interests also liked {product_name}.",
            "content_based": f"Based on your browsing history, you might like {product_name}.",
            "trending": f"{product_name} is trending and popular with our customers.",
            "fbt": f"Customers often buy {product_name} together with their purchase.",
            "default": f"We think you'll like {product_name}.",
        }

        return fallback_templates.get(
            recommendation_type.lower(), fallback_templates["default"]
        )


# Singleton instance for reuse across the application
_llm_service_instance = None


def get_llm_service() -> LLMService:
    """
    Get singleton instance of LLMService.

    Returns:
        LLMService instance

    Example:
        >>> service = get_llm_service()
        >>> text = await service.generate_text("Your prompt here")
    """
    global _llm_service_instance
    if _llm_service_instance is None:
        _llm_service_instance = LLMService()
    return _llm_service_instance
