# app/services/base_product_service.py - NEW FILE

from typing import List, Optional

from sqlalchemy import asc, desc, text
from sqlalchemy.orm import defer, joinedload

from app.database import SessionLocal
from app.models import Product, ProductCategory


class BaseProductService:
    """Base service for common product operations"""

    def __init__(self):
        self.db = SessionLocal()

    def build_product_query(
        self,
        include_category: bool = True,
        include_inactive: bool = False,
        load_embeddings: bool = False,
    ):
        """Build optimized product query with common options"""
        query = self.db.query(Product)

        # Add eager loading options
        options = []
        if include_category:
            options.append(
                joinedload(Product.category).load_only(
                    ProductCategory.id, ProductCategory.name
                )
            )

        if not load_embeddings:
            options.append(defer(Product.embedding))

        if options:
            query = query.options(*options)

        # Filter active products by default
        if not include_inactive:
            query = query.filter(Product.is_active == True)

        return query

    def apply_product_filters(
        self,
        query,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        in_stock: Optional[bool] = None,
        search_term: Optional[str] = None,
    ):
        """Apply common product filters"""

        if category:
            # Get all descendant categories recursively
            def get_descendant_categories(cat_id):
                """Get all descendant category IDs recursively"""
                descendants = {cat_id}
                children = (
                    self.db.query(ProductCategory.id)
                    .filter(ProductCategory.parent_id == cat_id)
                    .all()
                )
                for (child_id,) in children:
                    descendants.update(get_descendant_categories(child_id))
                return descendants

            # Try to parse as UUID first, otherwise search by name
            try:
                from uuid import UUID

                category_uuid = (
                    UUID(category) if isinstance(category, str) else category
                )
                # Get all descendant categories
                all_category_ids = get_descendant_categories(category_uuid)
                query = query.join(ProductCategory).filter(
                    ProductCategory.id.in_(all_category_ids)
                )
            except (ValueError, AttributeError):
                # Not a valid UUID, search by name
                query = query.join(ProductCategory).filter(
                    ProductCategory.name.ilike(f"%{category}%")
                )

        if brand:
            query = query.filter(Product.brand.ilike(f"%{brand}%"))

        if min_price is not None:
            query = query.filter(Product.price >= min_price)

        if max_price is not None:
            query = query.filter(Product.price <= max_price)

        if in_stock is not None:
            query = query.filter(Product.in_stock == in_stock)

        if search_term:
            search_filter = (
                Product.name.ilike(f"%{search_term}%")
                | Product.description.ilike(f"%{search_term}%")
                | Product.brand.ilike(f"%{search_term}%")
                | Product.specification.ilike(f"%{search_term}%")
                | Product.technical_details.ilike(f"%{search_term}%")
                | Product.meta_description.ilike(f"%{search_term}%")
                | Product.meta_title.ilike(f"%{search_term}%")
            )
            query = query.filter(search_filter)

        return query

    def apply_sorting(
        self, query, sort_by: str = "created_at", sort_order: str = "desc"
    ):
        """Apply common sorting options"""

        sort_fields = {
            "name": Product.name,
            "price": Product.price,
            "created_at": Product.created_at,
            "brand": Product.brand,
            "stock": Product.stock_quantity,
        }

        sort_field = sort_fields.get(sort_by, Product.created_at)

        if sort_order == "desc":
            sort_field = desc(sort_field)
        else:
            sort_field = asc(sort_field)

        return query.order_by(sort_field)

    def get_popular_products(
        self, limit: int = 20, days: int = 30, category: Optional[str] = None
    ) -> List[Product]:
        """Get popular products with caching"""

        cache_key = f"popular_products:{limit}:{days}:{category or 'all'}"

        # Query popular products based on order data
        popular_query = text(
            """
            SELECT p.id, p.name, p.brand, p.price, p.category_id,
                   COUNT(oi.id) as order_count,
                   SUM(oi.quantity) as total_sold
            FROM products p
            JOIN order_items oi ON p.id = oi.product_id
            JOIN orders o ON oi.order_id = o.id
            WHERE p.is_active = true
            AND o.status IN ('delivered', 'shipped')
            AND o.created_at > NOW() - INTERVAL '%s days'
            GROUP BY p.id, p.name, p.brand, p.price, p.category_id
            ORDER BY total_sold DESC, order_count DESC
            LIMIT %s
        """
            % (days, limit)
        )

        result = self.db.execute(popular_query)
        products = []
        product_ids = []

        for row in result.fetchall():
            product = Product(
                id=row.id,
                name=row.name,
                brand=row.brand,
                price=row.price,
                category_id=row.category_id,
            )
            products.append(product)
            product_ids.append(str(row.id))

        return products
