"""
Segment Rule Engine.
Applies segmentation rules and queries to find matching users.
"""

import logging
import math
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import (
    and_,
    exists,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.orm import aliased

from app.models import Order, User
from app.models.ml_models import UserSegment, UserSegmentMembership
from app.models.order import OrderItem
from app.models.product import Product, ProductCategory
from app.services.segmentation.base_segmentation_service import BaseSegmentationService

logger = logging.getLogger(__name__)


class SegmentRuleEngine(BaseSegmentationService):
    """Service for validating and applying segment rules."""

    SUPPORTED_OPERATORS = {
        "equals",
        "not_equals",
        "greater_than",
        "greater_or_equal",
        "less_than",
        "less_or_equal",
        "in",
        "not_in",
        "contains",
    }

    FIELD_DEFINITIONS: Dict[str, Dict[str, Any]] = {
        "user.created_at": {
            "type": "datetime",
            "resolver": lambda engine, refs: User.created_at,
        },
        "user.last_login": {
            "type": "datetime",
            "resolver": lambda engine, refs: User.last_login,
        },
        "user.gender": {
            "type": "string",
            "case_insensitive": True,
            "resolver": lambda engine, refs: func.lower(
                func.coalesce(User.gender, literal(""))
            ),
        },
        "user.country": {
            "type": "string",
            "case_insensitive": True,
            "resolver": lambda engine, refs: func.lower(
                func.coalesce(User.address["country"].astext, literal(""))
            ),
        },
        "demographic.age": {
            "type": "numeric",
            "resolver": lambda engine, refs: func.coalesce(
                func.date_part("year", func.age(func.now(), User.date_of_birth)),
                literal(0),
            ),
        },
        "order.total": {
            "type": "numeric",
            "resolver": lambda engine, refs: func.coalesce(
                refs["order_stats"].c.total_spent,
                literal(0),
            ),
        },
        "order.count": {
            "type": "numeric",
            "resolver": lambda engine, refs: func.coalesce(
                refs["order_stats"].c.order_count,
                literal(0),
            ),
        },
        "order.average_value": {
            "type": "numeric",
            "resolver": lambda engine, refs: func.coalesce(
                refs["order_stats"].c.average_order_value,
                literal(0),
            ),
        },
        "order.last_purchase": {
            "type": "datetime",
            "resolver": lambda engine, refs: refs["order_stats"].c.last_purchase_at,
        },
        "order.category": {
            "type": "string",
            "case_insensitive": True,
            "handler": "_build_category_condition",
        },
    }

    RFM_FIELD_MAP: Dict[str, Tuple[str, str]] = {
        "rfm.recency_score": ("rfm_recency_score", "numeric"),
        "rfm.frequency_score": ("rfm_frequency_score", "numeric"),
        "rfm.monetary_score": ("rfm_monetary_score", "numeric"),
        "rfm.total_spent": ("total_spent", "numeric"),
        "rfm.order_count": ("order_count", "numeric"),
        "rfm.recency_days": ("recency_days", "numeric"),
    }

    def validate_segment_rules(self, rules: Dict[str, Any]):
        """Validate segment rules structure and ensure fields/operators are supported."""
        if not rules:
            return

        logic = str(rules.get("logic", "and")).lower()
        if logic not in {"and", "or"}:
            raise ValueError("Segment logic must be 'and' or 'or'.")

        conditions = rules.get("conditions")
        if not isinstance(conditions, list) or not conditions:
            raise ValueError("Segment rules must include at least one condition.")

        for condition in conditions:
            field = condition.get("field")
            operator = condition.get("operator")
            if not field or not operator:
                raise ValueError("Each rule must specify both 'field' and 'operator'.")

            operator = operator.lower()
            if operator not in self.SUPPORTED_OPERATORS:
                raise ValueError(f"Unsupported operator: {operator}")

            if field not in self.FIELD_DEFINITIONS and field not in self.RFM_FIELD_MAP:
                raise ValueError(f"Unsupported field in segment rules: {field}")

    def apply_segment_rules(self, segment: UserSegment) -> None:
        segment_type = (segment.segment_type or "custom").lower()
        rules = segment.criteria or {}

        try:
            if not rules or not rules.get("conditions"):
                user_ids = self._load_all_user_ids()
            elif segment_type == "rfm":
                user_ids = self._evaluate_rfm_segment(rules)
            else:
                user_ids = self._evaluate_attribute_segment(rules)

            self._persist_segment_memberships(segment, user_ids)

        except Exception as exc:  # pragma: no cover - logged for observability
            logger.exception("Failed to apply segment rules", exc_info=exc)
            self.db.rollback()
            raise

    # ------------------------------------------------------------------
    # Core evaluators
    # ------------------------------------------------------------------
    def _evaluate_attribute_segment(self, rules: Dict[str, Any]) -> List[uuid.UUID]:
        order_stats = self._build_order_stats_subquery()

        query = self.db.query(User.id.label("user_id")).outerjoin(
            order_stats, order_stats.c.user_id == User.id
        )

        refs = {"order_stats": order_stats}
        expressions = []
        for condition in rules.get("conditions", []):
            expr = self._build_condition(condition, refs)
            if expr is not None:
                expressions.append(expr)

        logic = str(rules.get("logic", "and")).lower()
        if expressions:
            if logic == "or":
                query = query.filter(or_(*expressions))
            else:
                query = query.filter(and_(*expressions))

        return [row.user_id for row in query.distinct()]

    def _evaluate_rfm_segment(self, rules: Dict[str, Any]) -> List[uuid.UUID]:
        metrics = self._compute_rfm_metrics()
        if not metrics:
            return []

        logic = str(rules.get("logic", "and")).lower()
        conditions = rules.get("conditions", [])

        if logic == "or":
            matching_users: Optional[set[uuid.UUID]] = set()
        else:
            matching_users = set(metrics.keys())

        for condition in conditions:
            field = condition.get("field")
            operator = str(condition.get("operator", "equals")).lower()
            mapping = self.RFM_FIELD_MAP.get(field)
            if not mapping:
                continue

            metric_key, value_type = mapping
            target = self._normalize_simple_value(condition.get("value"), value_type)
            if target is None:
                continue

            current_matches = {
                user_id
                for user_id, data in metrics.items()
                if self._evaluate_scalar(data.get(metric_key), operator, target)
            }

            if logic == "or":
                matching_users |= current_matches
            else:
                matching_users &= current_matches

        return list(matching_users)

    # ------------------------------------------------------------------
    # Helpers (query construction, persistence, normalisation)
    # ------------------------------------------------------------------
    def _build_condition(self, condition: Dict[str, Any], refs: Dict[str, Any]):
        field = condition.get("field")
        operator = str(condition.get("operator", "equals")).lower()
        definition = self.FIELD_DEFINITIONS.get(field)
        if not definition:
            return None

        handler_name = definition.get("handler")
        if handler_name:
            handler = getattr(self, handler_name, None)
            if handler is None:
                return None
            return handler(operator, condition.get("value"))

        resolver = definition.get("resolver")
        if not callable(resolver):
            return None

        column_expr = resolver(self, refs)
        normalized_value = self._normalize_for_operator(
            operator, condition.get("value"), definition
        )
        if normalized_value is None:
            return None

        return self._build_operator_expression(
            column_expr, operator, normalized_value, definition
        )

    def _build_operator_expression(
        self, column, operator: str, value, definition: Dict[str, Any]
    ):
        if operator == "equals":
            return column == value
        if operator == "not_equals":
            return column != value
        if operator == "greater_than":
            return column > value
        if operator == "greater_or_equal":
            return column >= value
        if operator == "less_than":
            return column < value
        if operator == "less_or_equal":
            return column <= value
        if operator == "in":
            return column.in_(value) if value else literal(False)
        if operator == "not_in":
            return column.notin_(value) if value else literal(True)
        if operator == "contains":
            return column.ilike(f"%{value}%")
        return None

    def _build_category_condition(self, operator: str, raw_value: Any):
        values = self._coerce_to_list(raw_value, coerce_lower=True)
        if not values:
            return None

        order_alias = aliased(Order)
        order_item_alias = aliased(OrderItem)
        product_alias = aliased(Product)
        category_alias = aliased(ProductCategory)

        exists_query = (
            select(1)
            .select_from(order_alias)
            .join(order_item_alias, order_item_alias.order_id == order_alias.id)
            .join(product_alias, product_alias.id == order_item_alias.product_id)
            .outerjoin(category_alias, category_alias.id == product_alias.category_id)
            .where(order_alias.user_id == User.id)
            .where(order_alias.status.notin_(["cancelled", "refunded"]))
        )

        category_ids: List[uuid.UUID] = []
        category_names: List[str] = []
        for val in values:
            try:
                category_ids.append(uuid.UUID(val))
            except (TypeError, ValueError):
                category_names.append(val)

        filters = []
        if category_ids:
            filters.append(product_alias.category_id.in_(category_ids))
        if category_names:
            filters.append(func.lower(category_alias.name).in_(category_names))

        if filters:
            exists_query = exists_query.where(or_(*filters))

        if operator in {"equals", "in", "contains"}:
            return exists(exists_query)
        if operator in {"not_equals", "not_in"}:
            return ~exists(exists_query)
        return None

    def _build_order_stats_subquery(self):
        return (
            self.db.query(
                Order.user_id.label("user_id"),
                func.coalesce(func.sum(Order.total_amount), 0).label("total_spent"),
                func.count(Order.id).label("order_count"),
                func.coalesce(func.avg(Order.total_amount), 0).label(
                    "average_order_value"
                ),
                func.max(Order.created_at).label("last_purchase_at"),
                func.min(Order.created_at).label("first_purchase_at"),
            )
            .filter(Order.status.notin_(["cancelled", "refunded"]))
            .group_by(Order.user_id)
            .subquery()
        )

    def _compute_rfm_metrics(self) -> Dict[uuid.UUID, Dict[str, Any]]:
        rows = (
            self.db.query(
                Order.user_id,
                func.max(Order.created_at),
                func.count(Order.id),
                func.coalesce(func.sum(Order.total_amount), 0),
            )
            .filter(Order.status.notin_(["cancelled", "refunded"]))
            .group_by(Order.user_id)
            .all()
        )

        metrics: Dict[uuid.UUID, Dict[str, Any]] = {}
        if not rows:
            return metrics

        now = datetime.utcnow()
        recency_map: Dict[uuid.UUID, float] = {}
        frequency_map: Dict[uuid.UUID, float] = {}
        monetary_map: Dict[uuid.UUID, float] = {}

        for user_id, last_purchase, order_count, total_spent in rows:
            recency_days = (
                (now - last_purchase).days
                if isinstance(last_purchase, datetime)
                else math.inf
            )
            total_value = float(total_spent or 0)
            order_value = float(order_count or 0)

            recency_map[user_id] = recency_days
            frequency_map[user_id] = order_value
            monetary_map[user_id] = total_value

            metrics[user_id] = {
                "recency_days": recency_days,
                "order_count": order_value,
                "total_spent": total_value,
            }

        recency_scores = self._score_metric(recency_map, reverse=True)
        frequency_scores = self._score_metric(frequency_map, reverse=False)
        monetary_scores = self._score_metric(monetary_map, reverse=False)

        for user_id, data in metrics.items():
            data["rfm_recency_score"] = recency_scores.get(user_id, 1)
            data["rfm_frequency_score"] = frequency_scores.get(user_id, 1)
            data["rfm_monetary_score"] = monetary_scores.get(user_id, 1)

        return metrics

    def _score_metric(
        self, values: Dict[uuid.UUID, float], reverse: bool
    ) -> Dict[uuid.UUID, int]:
        if not values:
            return {}

        sorted_items = sorted(
            values.items(), key=lambda item: item[1], reverse=not reverse
        )
        total = len(sorted_items)
        bucket_size = max(1, total // 5)

        scores: Dict[uuid.UUID, int] = {}
        for index, (user_id, _value) in enumerate(sorted_items):
            bucket_index = min(4, index // bucket_size)
            score = 5 - bucket_index if not reverse else 5 - bucket_index
            scores[user_id] = max(1, min(5, score))
        return scores

    def _persist_segment_memberships(
        self, segment: UserSegment, user_ids: Sequence[uuid.UUID]
    ) -> None:
        normalized_ids = [
            self._normalize_user_id(user_id) for user_id in user_ids if user_id
        ]

        self.db.query(UserSegmentMembership).filter(
            UserSegmentMembership.segment_id == segment.id
        ).delete(synchronize_session=False)

        for user_id in normalized_ids:
            membership = UserSegmentMembership(
                id=uuid.uuid4(),
                user_id=user_id,
                segment_id=segment.id,
                is_active=True,
            )
            self.db.add(membership)

        segment.actual_size = len(normalized_ids)
        segment.last_updated = datetime.utcnow()
        self.db.commit()

    def _normalize_user_id(self, user_id: Any) -> uuid.UUID:
        if isinstance(user_id, uuid.UUID):
            return user_id
        return uuid.UUID(str(user_id))

    def _normalize_for_operator(
        self,
        operator: str,
        raw_value: Any,
        definition: Dict[str, Any],
    ):
        if operator in {"in", "not_in"}:
            values = self._coerce_to_list(
                raw_value,
                coerce_lower=definition.get("case_insensitive"),
            )
            normalized_values = [
                self._normalize_simple_value(value, definition.get("type", "string"))
                for value in values
            ]
            return [value for value in normalized_values if value is not None]
        return self._normalize_simple_value(
            raw_value, definition.get("type", "string"), definition
        )

    def _normalize_simple_value(
        self,
        raw_value: Any,
        value_type: str,
        definition: Optional[Dict[str, Any]] = None,
    ):
        if raw_value is None:
            return None

        if value_type in {"numeric", "number"}:
            try:
                return Decimal(str(raw_value))
            except (ArithmeticError, ValueError, TypeError):
                return None
        if value_type in {"integer", "int"}:
            try:
                return int(raw_value)
            except (ValueError, TypeError):
                return None
        if value_type == "boolean":
            if isinstance(raw_value, bool):
                return raw_value
            text = str(raw_value).strip().lower()
            if text in {"true", "1", "yes"}:
                return True
            if text in {"false", "0", "no"}:
                return False
            return None
        if value_type == "datetime":
            return self._parse_datetime(raw_value)

        text_value = str(raw_value).strip()
        if definition and definition.get("case_insensitive"):
            return text_value.lower()
        return text_value

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        for fmt in (None, "%Y-%m-%d"):
            try:
                return (
                    datetime.fromisoformat(text)
                    if fmt is None
                    else datetime.strptime(text, fmt)
                )
            except ValueError:
                continue
        return None

    def _evaluate_scalar(self, left: Any, operator: str, right: Any) -> bool:
        if left is None:
            return False
        if operator == "equals":
            return left == right
        if operator == "not_equals":
            return left != right
        if operator == "greater_than":
            return left > right
        if operator == "greater_or_equal":
            return left >= right
        if operator == "less_than":
            return left < right
        if operator == "less_or_equal":
            return left <= right
        if operator == "contains":
            return str(right).lower() in str(left).lower()
        if operator == "in":
            return left in (right or [])
        if operator == "not_in":
            return left not in (right or [])
        return False

    def _coerce_to_list(self, raw_value: Any, coerce_lower: bool = False) -> List[str]:
        if raw_value is None:
            return []
        if isinstance(raw_value, (list, tuple, set)):
            iterable = raw_value
        else:
            iterable = [part.strip() for part in str(raw_value).split(",")]
        result = [str(value).strip() for value in iterable if str(value).strip()]
        if coerce_lower:
            return [value.lower() for value in result]
        return result

    def _load_all_user_ids(self) -> List[uuid.UUID]:
        return [row.id for row in self.db.query(User.id).all()]
