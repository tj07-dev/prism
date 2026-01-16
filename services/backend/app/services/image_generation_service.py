"""
Image Generation Service using Google Gemini/Imagen.

This service generates marketing images like product posters and promotional
banners using Google's Gemini/Imagen API. Supports intelligent prompt generation
based on target segments, product information, and brand guidelines.
"""

import base64
import logging
import os
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

import aiohttp
import google.generativeai as genai

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class ImageType(Enum):
    """Types of images that can be generated."""

    PRODUCT_POSTER = "product_poster"
    PROMOTIONAL_BANNER = "promotional_banner"
    CATEGORY_BANNER = "category_banner"
    SEASONAL_BANNER = "seasonal_banner"


class UserSegment(Enum):
    """Target user segments for personalized images."""

    NEW_CUSTOMERS = "new_customers"
    YOUNG_ADULTS = "young_adults"
    HIGH_VALUE_CUSTOMERS = "high_value_customers"
    ELECTRONICS_ENTHUSIASTS = "electronics_enthusiasts"
    FASHION_LOVERS = "fashion_lovers"
    HOME_DECOR = "home_decor"


class DealType(Enum):
    """Types of promotional deals."""

    DISCOUNT = "discount"
    PRODUCT = "product"
    PROMOTION = "promotion"
    SEASONAL = "seasonal"


class ImageGenerationService:
    """
    Service for generating marketing images using Google Gemini/Imagen.

    Supports generating product posters, promotional banners, and other
    marketing visuals with intelligent prompt engineering based on context.
    """

    def __init__(self):
        """
        Initialize the image generation service with Gemini API client.

        Sets up the Google Generative AI client with API key from settings.
        """
        self._initialized = False
        self._initialize_client()

    def _initialize_client(self) -> None:
        """
        Initialize Google Generative AI client.

        Configures the client with API key from settings.
        """
        try:
            if settings.GOOGLE_API_KEY:
                genai.configure(api_key=settings.GOOGLE_API_KEY)
                self._initialized = True
                logger.info("Google Gemini/Imagen client initialized successfully")
            else:
                logger.warning(
                    "GOOGLE_API_KEY not configured - image generation will not work"
                )
                self._initialized = False

        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {str(e)}")
            self._initialized = False

    def generate_intelligent_prompt(
        self,
        image_type: ImageType,
        target_segment: Optional[UserSegment] = None,
        deal_type: Optional[DealType] = None,
        deal_data: Optional[Dict[str, Any]] = None,
        product_info: Optional[Dict[str, Any]] = None,
        brand_guidelines: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate intelligent prompt for image based on context.

        Creates a detailed prompt optimized for generating marketing images
        that resonate with the target audience and reflect brand identity.

        Args:
            image_type: Type of image to generate
            target_segment: Target user segment for personalization
            deal_type: Type of deal/promotion
            deal_data: Additional deal information
            product_info: Product details to include
            brand_guidelines: Brand colors, style preferences

        Returns:
            Detailed prompt string for image generation

        Example:
            >>> service = ImageGenerationService()
            >>> prompt = service.generate_intelligent_prompt(
            ...     image_type=ImageType.PRODUCT_POSTER,
            ...     product_info={"name": "Wireless Headphones", "category": "Electronics"}
            ... )
        """
        base_style = "Professional e-commerce image, high-quality, modern design, clean composition, photorealistic"

        # Segment-specific styling
        segment_styles = {
            UserSegment.NEW_CUSTOMERS: "welcoming and friendly, bright colors, approachable design, trust-building elements",
            UserSegment.YOUNG_ADULTS: "trendy and modern, vibrant colors, contemporary design, energetic aesthetic",
            UserSegment.HIGH_VALUE_CUSTOMERS: "luxury aesthetic, sophisticated palette, minimalist design, premium feel, elegant",
            UserSegment.ELECTRONICS_ENTHUSIASTS: "tech-focused, modern digital aesthetic, sleek themes, innovative style",
            UserSegment.FASHION_LOVERS: "stylish and fashionable, trendsetting design, aesthetic appeal, modern fashion",
            UserSegment.HOME_DECOR: "cozy and inviting, warm colors, homey atmosphere, comfortable aesthetic",
        }

        # Deal-specific elements
        deal_elements = {
            DealType.DISCOUNT: "prominent discount display, savings emphasis, price highlights, limited time urgency",
            DealType.PRODUCT: "product showcase, feature highlights, lifestyle context, quality demonstration",
            DealType.PROMOTION: "promotional theme, special event styling, exclusive offer indicators",
            DealType.SEASONAL: "seasonal theme, holiday aesthetics, timely relevance, festive elements",
        }

        # Image type specific requirements
        type_requirements = {
            ImageType.PRODUCT_POSTER: "product-focused layout, clear product visibility, hero product positioning",
            ImageType.PROMOTIONAL_BANNER: "9:6 aspect ratio, horizontal banner layout, text-friendly composition",
            ImageType.CATEGORY_BANNER: "category theme, multiple product suggestions, collection showcase",
            ImageType.SEASONAL_BANNER: "seasonal decorations, holiday theme, festive atmosphere",
        }

        prompt_parts = [base_style]

        # Add image type requirements
        if image_type:
            prompt_parts.append(type_requirements.get(image_type, ""))

        # Add segment styling
        if target_segment:
            prompt_parts.append(
                f"Target audience: {segment_styles.get(target_segment, '')}"
            )

        # Add deal elements
        if deal_type:
            prompt_parts.append(f"Campaign type: {deal_elements.get(deal_type, '')}")

        # Add product context
        if product_info:
            product_context = f"Product: {product_info.get('name', 'featured product')}"
            if product_info.get("category"):
                product_context += f", category: {product_info['category']}"
            if product_info.get("key_features"):
                features = product_info["key_features"]
                if isinstance(features, list):
                    product_context += f", features: {', '.join(features[:3])}"
                else:
                    product_context += f", features: {features}"
            prompt_parts.append(product_context)

        # Add deal data
        if deal_data:
            if deal_type == DealType.DISCOUNT and "discount" in deal_data:
                prompt_parts.append(
                    f"Featuring {deal_data['discount']}% discount prominently"
                )
            elif deal_type == DealType.PRODUCT and "product_name" in deal_data:
                prompt_parts.append(
                    f"Showcasing {deal_data['product_name']} as hero product"
                )
            elif "promotion_name" in deal_data:
                prompt_parts.append(f"Promoting {deal_data['promotion_name']} campaign")

        # Add brand guidelines
        if brand_guidelines:
            brand_elements = []
            if "primary_color" in brand_guidelines:
                brand_elements.append(
                    f"primary brand color: {brand_guidelines['primary_color']}"
                )
            if "secondary_color" in brand_guidelines:
                brand_elements.append(
                    f"secondary color: {brand_guidelines['secondary_color']}"
                )
            if "style" in brand_guidelines:
                brand_elements.append(f"brand style: {brand_guidelines['style']}")
            if brand_elements:
                prompt_parts.append(f"Brand elements: {', '.join(brand_elements)}")

        # Technical specifications
        technical_specs = [
            "high resolution",
            "professional photography style",
            "commercial advertising quality",
            "proper visual hierarchy",
            "clear focal point",
        ]
        prompt_parts.extend(technical_specs)

        final_prompt = ". ".join([p for p in prompt_parts if p]) + "."
        return final_prompt

    async def generate_image(
        self,
        prompt: str,
        output_path: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
        sample_count: int = 1,
        retries: int = 0,
    ) -> Dict[str, Any]:
        """
        Generate image using Google Imagen 4 API (:predict endpoint).

        Args:
            prompt: Text prompt describing the desired image
            output_path: Optional path to save the image (PNG/JPG)
            aspect_ratio: Optional aspect ratio (not directly supported in :predict, kept for compatibility)
            sample_count: Number of images to generate
            retries: Retry attempts on failure
        """
        if not self._initialized:
            return {
                "success": False,
                "error": "Google API not initialized. Configure GOOGLE_API_KEY.",
                "prompt_used": prompt,
            }

        model_name = getattr(settings, "GEMINI_IMAGE_MODEL", "imagen-4.0-generate-001")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:predict"

        print(url, "\n\n\n\n\n\n\n url", settings.GOOGLE_API_KEY)

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": settings.GOOGLE_API_KEY,
        }

        # Build payload similar to your working curl
        parameters = {"sampleCount": sample_count}
        if aspect_ratio:
            parameters["aspectRatio"] = aspect_ratio  # optional future-proof param

        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": parameters,
        }

        max_retries = retries or getattr(settings, "MAX_IMAGE_GENERATION_RETRIES", 3)

        for attempt in range(max_retries):
            try:
                logger.info(
                    f"Generating image via Imagen 4 API (attempt {attempt + 1}/{max_retries})"
                )

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=90),
                    ) as response:
                        if response.status == 200:
                            result = await response.json()

                            predictions = result.get("predictions", [])
                            if not predictions:
                                return {
                                    "success": False,
                                    "error": "No predictions returned from Imagen 4 API.",
                                    "prompt_used": prompt,
                                }

                            images_base64 = []
                            filenames = []

                            for i, pred in enumerate(predictions):
                                image_base64 = (
                                    pred.get("bytesBase64Encoded")
                                    or pred.get("imageBase64")
                                    or None
                                )
                                if not image_base64:
                                    logger.warning(
                                        f"Prediction {i} missing base64 data"
                                    )
                                    continue

                                images_base64.append(image_base64)

                                if output_path:
                                    os.makedirs(
                                        os.path.dirname(output_path), exist_ok=True
                                    )
                                    base, ext = os.path.splitext(output_path)
                                    file_path = f"{base}_{i + 1}{ext or '.png'}"
                                    with open(file_path, "wb") as f:
                                        f.write(base64.b64decode(image_base64))
                                    filenames.append(file_path)
                                    logger.info(f"Image saved to {file_path}")
                            # print(images_base64[0:10],"\n\n\n\n\n\n\n images_base64")
                            return {
                                "success": True,
                                "images_base64": images_base64,
                                "filenames": filenames,
                                "prompt_used": prompt,
                            }

                        else:
                            err_txt = await response.text()
                            logger.error(
                                f"Imagen 4 API error ({response.status}): {err_txt}"
                            )
                            if attempt < max_retries - 1:
                                continue
                            return {
                                "success": False,
                                "error": f"API returned {response.status}: {err_txt}",
                                "prompt_used": prompt,
                            }

            except aiohttp.ClientError as e:
                logger.error(f"Network error during image generation: {e}")
                if attempt == max_retries - 1:
                    return {"success": False, "error": str(e), "prompt_used": prompt}

            except Exception as e:
                logger.error(f"Unexpected error generating image: {e}", exc_info=True)
                if attempt == max_retries - 1:
                    return {"success": False, "error": str(e), "prompt_used": prompt}

        return {
            "success": False,
            "error": "Max retries exceeded",
            "prompt_used": prompt,
        }

    async def generate_product_poster(
        self,
        product_name: str,
        product_category: Optional[str] = None,
        product_features: Optional[list] = None,
        target_segment: Optional[UserSegment] = None,
        brand_guidelines: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a product poster image.

        Args:
            product_name: Name of the product
            product_category: Product category
            product_features: List of key features
            target_segment: Target user segment
            brand_guidelines: Brand styling guidelines

        Returns:
            Generation result dictionary

        Example:
            >>> result = await service.generate_product_poster(
            ...     product_name="Wireless Gaming Mouse",
            ...     product_category="Electronics",
            ...     product_features=["RGB lighting", "Ultra responsive", "Ergonomic"]
            ... )
        """
        product_info = {
            "name": product_name,
            "category": product_category,
            "key_features": product_features or [],
        }

        prompt = self.generate_intelligent_prompt(
            image_type=ImageType.PRODUCT_POSTER,
            target_segment=target_segment,
            product_info=product_info,
            brand_guidelines=brand_guidelines,
        )

        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() else "_" for c in product_name[:30])
        filename = f"poster_{safe_name}_{timestamp}.png"
        output_path = os.path.join(settings.IMAGE_STORAGE_PATH, filename)

        return await self.generate_image(
            prompt=prompt, output_path=output_path, aspect_ratio="1:1"
        )

    async def generate_promotional_banner(
        self,
        target_segment: UserSegment,
        deal_type: DealType,
        deal_data: Optional[Dict[str, Any]] = None,
        product_info: Optional[Dict[str, Any]] = None,
        brand_guidelines: Optional[Dict[str, Any]] = None,
        custom_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a promotional banner image.

        Args:
            target_segment: Target user segment
            deal_type: Type of promotion
            deal_data: Deal-specific information
            product_info: Product details
            brand_guidelines: Brand styling guidelines
            custom_prompt: Optional custom prompt override

        Returns:
            Generation result dictionary

        Example:
            >>> result = await service.generate_promotional_banner(
            ...     target_segment=UserSegment.YOUNG_ADULTS,
            ...     deal_type=DealType.DISCOUNT,
            ...     deal_data={"discount": 25, "product_name": "Summer Collection"}
            ... )
        """
        if custom_prompt:
            prompt = custom_prompt
        else:
            prompt = self.generate_intelligent_prompt(
                image_type=ImageType.PROMOTIONAL_BANNER,
                target_segment=target_segment,
                deal_type=deal_type,
                deal_data=deal_data,
                product_info=product_info,
                brand_guidelines=brand_guidelines,
            )

        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"banner_{target_segment.value}_{deal_type.value}_{timestamp}.png"
        output_path = os.path.join(settings.IMAGE_STORAGE_PATH, filename)

        return await self.generate_image(
            prompt=prompt, output_path=output_path, aspect_ratio="16:9"
        )

    def save_generated_image(
        self, image_data: str, filename: str, subdirectory: Optional[str] = None
    ) -> str:
        """
        Save base64 encoded image to local storage.

        Args:
            image_data: Base64 encoded image data
            filename: Filename to save as
            subdirectory: Optional subdirectory within IMAGE_STORAGE_PATH

        Returns:
            Relative URL path to the saved image

        Example:
            >>> url = service.save_generated_image(
            ...     image_data="data:image/png;base64,iVBORw0KG...",
            ...     filename="product_123.png",
            ...     subdirectory="products"
            ... )
        """
        try:
            # Create directory path
            if subdirectory:
                save_dir = os.path.join(settings.IMAGE_STORAGE_PATH, subdirectory)
            else:
                save_dir = settings.IMAGE_STORAGE_PATH

            os.makedirs(save_dir, exist_ok=True)

            # Full file path
            file_path = os.path.join(save_dir, filename)

            # Remove data URL prefix if present
            if "," in image_data:
                image_data = image_data.split(",")[1]

            # Decode and save
            with open(file_path, "wb") as f:
                f.write(base64.b64decode(image_data))

            # Return relative URL path
            if subdirectory:
                return f"/{settings.IMAGE_STORAGE_PATH}/{subdirectory}/{filename}"
            else:
                return f"/{settings.IMAGE_STORAGE_PATH}/{filename}"

        except Exception as e:
            logger.error(f"Error saving image: {str(e)}", exc_info=True)
            raise

    def get_segment_templates(self) -> Dict[UserSegment, str]:
        """
        Get pre-defined prompt templates for each user segment.

        Returns:
            Dictionary mapping segments to template prompts

        Example:
            >>> templates = service.get_segment_templates()
            >>> high_value_template = templates[UserSegment.HIGH_VALUE_CUSTOMERS]
        """
        return {
            UserSegment.HIGH_VALUE_CUSTOMERS: (
                "Luxury e-commerce banner with sophisticated black and gold design, "
                "premium product showcase, elegant typography, minimalist layout, "
                "high-end aesthetic, professional photography style"
            ),
            UserSegment.NEW_CUSTOMERS: (
                "Welcoming e-commerce banner with bright, friendly colors, "
                "approachable design, clear welcome messaging, inviting atmosphere, "
                "trust-building elements, modern clean layout"
            ),
            UserSegment.ELECTRONICS_ENTHUSIASTS: (
                "Tech-focused banner with modern digital aesthetic, sleek technology themes, "
                "innovative design, cutting-edge style, gadget-oriented imagery, "
                "futuristic elements"
            ),
            UserSegment.YOUNG_ADULTS: (
                "Trendy modern banner with vibrant colors, contemporary design, "
                "social media style, energetic and youthful aesthetic, "
                "bold typography, dynamic layout"
            ),
            UserSegment.FASHION_LOVERS: (
                "Fashion-forward banner with stylish aesthetic, trendsetting design, "
                "editorial photography style, sophisticated color palette, "
                "runway-inspired layout"
            ),
            UserSegment.HOME_DECOR: (
                "Cozy home-themed banner with warm inviting colors, comfortable aesthetic, "
                "lifestyle photography, homey atmosphere, interior design elements"
            ),
        }


# Singleton instance for reuse across the application
_image_service_instance = None


def get_image_generation_service() -> ImageGenerationService:
    """
    Get singleton instance of ImageGenerationService.

    Returns:
        ImageGenerationService instance

    Example:
        >>> service = get_image_generation_service()
        >>> result = await service.generate_product_poster("Product Name")
    """
    global _image_service_instance
    if _image_service_instance is None:
        _image_service_instance = ImageGenerationService()
    return _image_service_instance
