"""
User, Role, and Permission models for authentication and authorization.
"""

import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base

# Association tables
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True),
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True),
)


class User(Base):
    """User model for customer and admin accounts."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String)
    first_name = Column(String(100))
    last_name = Column(String(100))
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    is_superuser = Column(Boolean, default=False)
    date_of_birth = Column(DateTime(timezone=False))
    gender = Column(String(10))
    interests = Column(JSON)
    preferences = Column(JSON)
    address = Column(JSON)
    last_login = Column(DateTime(timezone=False))
    login_count = Column(Integer, default=0)
    created_by = Column(UUID(as_uuid=True))
    updated_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=False), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now()
    )
    viewed_products = Column(JSON, default=[])

    # Relationships
    roles = relationship("Role", secondary=user_roles, back_populates="users")
    cart = relationship("Cart", back_populates="user", uselist=False)
    orders = relationship("Order", back_populates="user")
    wishlist = relationship(
        "Product", secondary="wishlist_items", back_populates="wishlisted_by"
    )
    search_analytics = relationship("SearchAnalytics", back_populates="user")


class Role(Base):
    """Role model for role-based access control."""

    __tablename__ = "roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    permissions = Column(JSON)
    is_active = Column(Boolean, default=True)
    created_by = Column(UUID(as_uuid=True))
    updated_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    users = relationship("User", secondary=user_roles, back_populates="roles")
