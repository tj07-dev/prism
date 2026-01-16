import logging
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import Text, asc, cast, desc, or_
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models import Product, ProductCategory, ProductConfig, SearchAnalytics

settings = get_settings()
logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self, db: Session):
        self.db = db

    @lru_cache(maxsize=100)
    def get_category_by_name(self, category_name: str) -> Optional[ProductCategory]:
        """Get category by name with caching"""
        return (
            self.db.query(ProductCategory)
            .filter(ProductCategory.name.ilike(f"%{category_name}%"))
            .first()
        )

    def build_base_query(self, filters: Dict[str, Any]):
        """Build base product query with filters"""
        query = (
            self.db.query(Product)
            .options(selectinload(Product.category))
            .options(selectinload(Product.config))
            .filter(Product.is_active == True)
        )

        if filters.get("category"):
            category = self.get_category_by_name(filters["category"])
            if category:
                query = query.filter(Product.category_id == category.id)

        if filters.get("brand"):
            query = query.filter(Product.brand.ilike(f"%{filters['brand']}%"))

        if filters.get("min_price") is not None:
            query = query.filter(Product.price >= filters["min_price"])

        if filters.get("max_price") is not None:
            query = query.filter(Product.price <= filters["max_price"])

        if filters.get("in_stock") is not None:
            if filters["in_stock"]:
                query = query.filter(Product.in_stock == True)
            else:
                query = query.filter(Product.in_stock == False)

        return query

    def apply_traditional_search(self, query, search_term: str):
        """Apply traditional text search"""
        search_filter = or_(
            Product.name.ilike(f"%{search_term}%"),
            Product.description.ilike(f"%{search_term}%"),
            cast(Product.specification, Text).ilike(f"%{search_term}%"),
            cast(Product.technical_details, Text).ilike(f"%{search_term}%"),
            Product.brand.ilike(f"%{search_term}%"),
            Product.code.ilike(f"%{search_term}%"),
        )
        return query.filter(search_filter)

    def apply_sponsored_boost(self, products: List[Product]) -> List[Product]:
        """Apply sponsored product boosting"""
        sponsored_products = []
        regular_products = []

        for product in products:
            if product.config and product.config.is_sponsored:
                sponsored_products.append((product, product.config.sponsored_priority))
            else:
                regular_products.append(product)

        sponsored_products.sort(key=lambda x: -x[1])

        result = [p[0] for p in sponsored_products] + regular_products

        return result

    def apply_sorting(self, query, sort_by: str, sort_order: str):
        """Apply sorting to query"""
        order_func = desc if sort_order.lower() == "desc" else asc

        if sort_by == "price":
            return query.order_by(order_func(Product.price))
        elif sort_by == "name":
            return query.order_by(order_func(Product.name))
        elif sort_by == "created_at":
            return query.order_by(order_func(Product.created_at))
        elif sort_by == "popularity":
            return query.order_by(desc(Product.created_at))
        else:
            return query

    def traditional_search(
        self,
        search_term: str,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: str = "relevance",
        sort_order: str = "desc",
        page: int = 1,
        size: int = 20,
    ) -> Tuple[List[Product], int, int]:
        """Traditional text-based search"""
        start_time = time.time()

        query = self.build_base_query(filters or {})

        if search_term:
            search_filter = or_(
                Product.name.ilike(f"%{search_term}%"),
                Product.description.ilike(f"%{search_term}%"),
                Product.brand.ilike(f"%{search_term}%"),
            )
            query = query.filter(search_filter)

        if sort_by == "price":
            order_func = asc if sort_order == "asc" else desc
            query = query.order_by(order_func(Product.price))
        elif sort_by == "name":
            order_func = asc if sort_order == "asc" else desc
            query = query.order_by(order_func(Product.name))
        else:
            query = query.order_by(desc(Product.created_at))

        total = query.count()

        offset = (page - 1) * size
        products = query.offset(offset).limit(size).all()

        search_time_ms = int((time.time() - start_time) * 1000)

        return products, total, search_time_ms

    async def hybrid_search(
        self,
        search_term: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: str = "relevance",
        sort_order: str = "desc",
        page: int = 1,
        size: int = 20,
        use_vector: bool = True,
    ) -> Tuple[List[Product], int, int]:
        """Perform hybrid search (traditional text search with optional vector search)"""
        start_time = time.time()

        if filters is None:
            filters = {}

        query = self.build_base_query(filters)

        if search_term:
            query = self.apply_traditional_search(query, search_term)

        if sort_by != "relevance":
            query = self.apply_sorting(query, sort_by, sort_order)
        else:
            query = query.outerjoin(ProductConfig).order_by(
                desc(ProductConfig.is_sponsored),
                desc(ProductConfig.sponsored_priority),
                desc(Product.created_at),
            )

        total = query.count()
        logger.debug(f"Total products found: {total}")

        offset = (page - 1) * size
        products = query.offset(offset).limit(size).all()

        if sort_by == "relevance":
            products = self.apply_sponsored_boost(products)

        search_time_ms = int((time.time() - start_time) * 1000)

        return products, total, search_time_ms

    async def log_search(
        self,
        user_id: Optional[str],
        session_id: str,
        query: str,
        search_type: str,
        results_count: int,
        response_time_ms: int,
        filters: Dict[str, Any],
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ):
        """Log search analytics"""
        try:
            search_log = SearchAnalytics(
                user_id=user_id,
                session_id=session_id,
                query=query,
                search_type=search_type,
                results_count=results_count,
                response_time_ms=response_time_ms,
                filters_applied=filters,
                user_agent=user_agent,
                ip_address=ip_address,
            )

            self.db.add(search_log)
            self.db.commit()

        except Exception as e:
            logger.error(f"Error logging search: {str(e)}")
            self.db.rollback()

    def log_search_click(self, search_id: str, product_id: str, position: int):
        """Log when user clicks on search result"""
        try:
            search_log = (
                self.db.query(SearchAnalytics)
                .filter(SearchAnalytics.id == search_id)
                .first()
            )

            if search_log:
                search_log.clicked_product_id = product_id
                search_log.click_position = position
                self.db.commit()

        except Exception as e:
            logger.error(f"Error logging search click: {str(e)}")
            self.db.rollback()
