from typing import Any, Dict, List, Optional

from app.models.product import Product, ProductCategory, ProductConfig


def _category_to_json(category: ProductCategory) -> Dict[str, Any]:
    """Convert a category model to an API-friendly dictionary."""

    return {
        "id": str(category.id),
        "name": category.name,
        "description": category.description,
        "parent_id": str(category.parent_id) if category.parent_id else None,
        "sort_order": category.sort_order or 0,
        "is_active": category.is_active,
        "created_at": category.created_at.isoformat() if category.created_at else None,
        "children": [],
    }


def _config_to_json(config: ProductConfig) -> Dict[str, Any]:
    """Convert a product configuration model to response dictionary."""

    return {
        "id": str(config.id),
        "product_id": str(config.product_id),
        "show_in_search": config.show_in_search,
        "show_in_recommendations": config.show_in_recommendations,
        "reranking_priority": config.reranking_priority,
        "is_sponsored": config.is_sponsored,
        "sponsored_priority": config.sponsored_priority,
        "featured": config.featured,
        "promotion_text": config.promotion_text,
        "boost_factor": config.boost_factor,
        "created_at": config.created_at.isoformat() if config.created_at else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


def product_to_json(
    product: "Product",
    ignore_fields: Optional[List[str]] = None,
    include_related: bool = True,
) -> Dict[str, Any]:
    """
    Convert a Product SQLAlchemy model instance to a JSON-serializable dictionary.

    Args:
        product: The Product model instance to convert
        ignore_fields: List of field names to exclude from the output
        include_related: Whether to include related objects (category, etc.)

    Returns:
        Dictionary containing the product data
    """
    if ignore_fields is None:
        ignore_fields = []

    result: Dict[str, Any] = {
        "id": str(product.id),
        "name": product.name,
        "code": product.code,
        "brand": product.brand,
        "price": float(product.price) if product.price is not None else None,
        "compare_price": float(product.compare_price)
        if product.compare_price is not None
        else None,
        "description": product.description,
        "specification": product.specification,
        "technical_details": product.technical_details,
        "product_dimensions": product.product_dimensions,
        "images": list(product.images) if product.images else [],
        "product_url": product.product_url,
        "stock_quantity": product.stock_quantity,
        "in_stock": product.in_stock,
        "track_inventory": product.track_inventory,
        "is_active": product.is_active,
        "is_amazon_seller": product.is_amazon_seller,
        "is_embedding_generated": bool(product.is_embedding_generated),
        "custom_fields": product.custom_fields,
        "meta_title": product.meta_title,
        "meta_description": product.meta_description,
        "tags": product.tags,
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "updated_at": product.updated_at.isoformat() if product.updated_at else None,
    }

    optional_cost_fields = {
        "cost_price": float(product.cost_price)
        if product.cost_price is not None
        else None,
    }

    for field, value in optional_cost_fields.items():
        if field not in ignore_fields:
            result[field] = value

    if include_related:
        if "category" not in ignore_fields and product.category:
            result["category"] = _category_to_json(product.category)

        if "config" not in ignore_fields and product.config:
            result["config"] = _config_to_json(product.config)

    for field in ignore_fields:
        result.pop(field, None)

    return result
