# Complete Data Migration Script for Training Data
# migrate_complete_ecom_data.py

import json
import logging
import random
import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import psycopg2
from faker import Faker
from psycopg2 import sql
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CompleteEcomDataMigrator:
    def __init__(self, database_url: str, csv_file_path: str):
        self.database_url = database_url
        self.csv_file_path = csv_file_path
        self.engine = create_engine(database_url)
        self.Session = sessionmaker(bind=self.engine)
        self.fake = Faker()

        # Generated data storage
        self.users = []
        self.categories = {}
        self.brands = {}
        self.products = []
        self.orders = []
        self.recommendations = []

    def migrate_all_data(
        self,
        users_count: int = 2000,
        orders_count: int = 8000,
        search_interactions: int = 25000,
    ):
        """Complete data migration pipeline"""

        logger.info("🚀 Starting complete data migration...")

        try:
            # 1. Create default roles and admin user (separate transaction)
            logger.info("Step 1: Creating default roles and admin user...")
            with self.Session() as session:
                self._create_default_roles(session)
                session.commit()

            # 2. Extract and create categories/brands from CSV (separate transaction)
            logger.info("Step 2: Creating categories and brands...")
            with self.Session() as session:
                self._extract_categories_and_brands_from_csv(session)
                session.commit()

            # 3. Import products from CSV (handled individually)
            logger.info("Step 3: Importing products from CSV...")
            self._import_products_from_csv(None)  # Uses its own transactions

            # 4. Generate users (separate transaction)
            logger.info("Step 4: Generating users...")
            with self.Session() as session:
                self._generate_users(session, users_count)
                session.commit()

            # 5. Generate orders with realistic patterns (separate transaction)
            logger.info("Step 5: Generating orders...")
            with self.Session() as session:
                self._generate_orders(session, orders_count)
                session.commit()

            # 6. Generate search analytics (separate transaction)
            logger.info("Step 6: Generating search analytics...")
            with self.Session() as session:
                self._generate_search_analytics(session, search_interactions)
                session.commit()

            # 7. Generate user behavior data (separate transaction)
            logger.info("Step 7: Generating user behavior data...")
            with self.Session() as session:
                self._generate_user_behavior(session)
                session.commit()

            # 8. Generate recommendation data (separate transaction)
            logger.info("Step 8: Generating recommendation data...")
            with self.Session() as session:
                self._generate_recommendation_data(session)
                session.commit()

            # 9. Create ML model configs (separate transaction)
            logger.info("Step 9: Creating ML model configs...")
            with self.Session() as session:
                self._create_ml_model_configs(session)
                session.commit()

            # 10. Create user segments (separate transaction)
            # logger.info("Step 10: Creating user segments...")
            # with self.Session() as session:
            #     self._create_user_segments(session)
            #     session.commit()

            logger.info("✅ Data migration completed successfully!")

            # Return summary
            with self.Session() as session:
                return self._generate_summary(session)

        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            raise

    def _create_default_roles(self, session):
        """Create default roles and admin user"""
        logger.info("Creating default roles and admin user...")

        # Default roles
        roles_data = [
            {
                "name": "admin",
                "description": "Administrator with full access",
                "permissions": [
                    "users.view",
                    "users.create",
                    "users.update",
                    "users.delete",
                    "products.view",
                    "products.create",
                    "products.update",
                    "products.delete",
                    "products.manage_inventory",
                    "products.manage_categories",
                    "orders.view",
                    "orders.view_all",
                    "orders.update",
                    "orders.delete",
                    "orders.manage_status",
                    "orders.view_reports",
                    "analytics.view",
                    "analytics.view_detailed",
                    "analytics.export",
                    "system.admin",
                    "system.settings",
                    "system.logs",
                    "system.recommendations",
                    "system.ml_models",
                ],
            },
            {
                "name": "customer",
                "description": "Regular customer",
                "permissions": [
                    "products.view",
                    "cart.view",
                    "cart.manage",
                    "orders.view",
                ],
            },
            {
                "name": "manager",
                "description": "Store manager",
                "permissions": [
                    "products.view",
                    "products.update",
                    "products.manage_inventory",
                    "orders.view",
                    "orders.view_all",
                    "orders.update",
                    "analytics.view",
                    "users.view",
                ],
            },
        ]

        role_ids = {}
        for role_data in roles_data:
            # Check if role exists
            existing = session.execute(
                text("SELECT id FROM roles WHERE name = :name"),
                {"name": role_data["name"]},
            ).fetchone()
            if existing:
                role_id = existing.id
                logger.info(
                    f"Using existing role '{role_data['name']}' with id {role_id}"
                )
            else:
                role_id = str(uuid.uuid4())
                session.execute(
                    text("""
                    INSERT INTO roles (id, name, description, permissions, is_active)
                    VALUES (:id, :name, :description, :permissions, :is_active)
                """),
                    {
                        "id": role_id,
                        "name": role_data["name"],
                        "description": role_data["description"],
                        "permissions": json.dumps(role_data["permissions"]),
                        "is_active": True,
                    },
                )
                logger.info(f"Created new role '{role_data['name']}' with id {role_id}")

            role_ids[role_data["name"]] = role_id

        # Create admin user if not exists
        admin_email = "admin@ecommerce.com"
        existing_admin = session.execute(
            text("SELECT id FROM users WHERE email = :email"), {"email": admin_email}
        ).fetchone()
        if existing_admin:
            admin_id = existing_admin.id
            logger.info(f"Using existing admin user with id {admin_id}")
        else:
            admin_id = str(uuid.uuid4())
            admin_username = "admin"
            admin_first_name = "Admin"
            admin_last_name = "User"
            session.execute(
                text("""
                INSERT INTO users (
                    id, username, email, hashed_password, first_name, last_name,
                    is_active, is_verified, is_superuser
                ) VALUES (
                    :id, :username, :email, :hashed_password, :first_name, :last_name,
                    :is_active, :is_verified, :is_superuser
                )
                """),
                {
                    "id": admin_id,
                    "username": admin_username,
                    "email": admin_email,
                    "hashed_password": "$2b$12$Iy5njesJ9WYwWctcsHbXtOhYys4OH8ybcHNFi3abWQqQCoQZMW1hS",  # password123
                    "first_name": admin_first_name,
                    "last_name": admin_last_name,
                    "is_active": True,
                    "is_verified": True,
                    "is_superuser": True,
                },
            )
            logger.info(f"Created new admin user with id {admin_id}")

        # Assign admin role to admin user if not already assigned
        existing_assignment = session.execute(
            text("""
            SELECT 1 FROM user_roles ur
            JOIN roles r ON ur.role_id = r.id
            WHERE ur.user_id = :user_id AND r.name = 'admin'
            """),
            {"user_id": admin_id},
        ).fetchone()
        if not existing_assignment:
            session.execute(
                text("""
                INSERT INTO user_roles (user_id, role_id)
                VALUES (:user_id, :role_id)
                """),
                {
                    "user_id": admin_id,
                    "role_id": role_ids["admin"],
                },
            )
            logger.info("Assigned admin role to admin user")

        logger.info(
            "✅ Created/verified roles and admin user (admin@ecommerce.com / password123)"
        )

    def _extract_categories_and_brands_from_csv(self, session):
        """Extract unique categories and brands from product CSV"""
        logger.info("Extracting categories and brands from CSV...")

        try:
            # Read CSV to extract unique values
            df = pd.read_csv(self.csv_file_path)

            # Extract unique brands from CSV
            unique_brands = df["brand"].dropna().unique()

            for brand in unique_brands:
                if pd.notna(brand) and brand.strip():
                    self.brands[brand] = str(uuid.uuid4())
        except Exception as e:
            logger.warning(f"Could not read CSV for brands: {e}. Using no brands.")

        # Extract unique categories (assuming category names in your data)
        # Since your CSV has category_id, we'll create some sample categories
        category_names = [
            "Electronics",
            "Toys & Games",
            "Educational",
            "Science Kits",
            "Books",
            "Home & Garden",
            "Sports",
            "Beauty",
            "Automotive",
            "Clothing",
            "Health",
            "Kitchen",
            "Tools",
            "Music",
            "Art & Crafts",
        ]

        for i, name in enumerate(category_names):
            # Check if category exists
            existing = session.execute(
                text("SELECT id FROM product_categories WHERE name = :name"),
                {"name": name},
            ).fetchone()
            if existing:
                category_id = existing.id
                logger.info(f"Using existing category '{name}' with id {category_id}")
            else:
                category_id = str(uuid.uuid4())
                slug = name.lower().replace(" ", "-").replace("&", "and")
                session.execute(
                    text("""
                    INSERT INTO product_categories (id, name, slug, description, is_active, sort_order)
                    VALUES (:id, :name, :slug, :description, :is_active, :sort_order)
                """),
                    {
                        "id": category_id,
                        "name": name,
                        "slug": slug,
                        "description": f"{name} products and accessories",
                        "is_active": True,
                        "sort_order": i,
                    },
                )
                logger.info(f"Created new category '{name}' with id {category_id}")

            self.categories[name] = category_id

        logger.info(
            f"✅ Created/verified {len(self.categories)} categories and identified {len(self.brands)} brands"
        )

    def _import_products_from_csv(self, session):
        """Import products from CSV file"""
        logger.info("Importing products from CSV...")

        try:
            df = pd.read_csv(self.csv_file_path)

            if df.empty:
                logger.warning("CSV is empty. Generating sample products.")
                self._generate_sample_products()
                return

            # Get a random category for products without clear category mapping
            category_list = list(self.categories.values())

            products_imported = 0
            products_failed = 0

            for index, row in df.iterrows():
                # Use individual transactions for each product to prevent cascade failures
                try:
                    with self.engine.begin() as conn:
                        # Parse the data from your CSV format
                        product_id = (
                            row["id"] if pd.notna(row["id"]) else str(uuid.uuid4())
                        )

                        # Clean and validate data before insertion
                        name = (
                            str(row["name"])[:200]
                            if pd.notna(row["name"])
                            else f"Product_{index}"
                        )
                        code = (
                            str(row["code"])[:50]
                            if pd.notna(row["code"])
                            else f"CODE_{index}"
                        )

                        # Ensure code is unique
                        existing_code_check = conn.execute(
                            text("SELECT id FROM products WHERE code = :code"),
                            {"code": code},
                        ).fetchone()
                        if existing_code_check:
                            code = f"{code}_{index}"

                        # Choose appropriate category
                        name_lower = name.lower()
                        if "electronic" in name_lower or "circuit" in name_lower:
                            category_id = self.categories.get(
                                "Electronics", random.choice(category_list)
                            )
                        elif "toy" in name_lower or "kit" in name_lower:
                            category_id = self.categories.get(
                                "Toys & Games", random.choice(category_list)
                            )
                        elif "ladder" in name_lower or "tool" in name_lower:
                            category_id = self.categories.get(
                                "Tools", random.choice(category_list)
                            )
                        elif "education" in str(row.get("description", "")).lower():
                            category_id = self.categories.get(
                                "Educational", random.choice(category_list)
                            )
                        else:
                            category_id = random.choice(category_list)

                        # Parse and clean data
                        brand = (
                            str(row["brand"])[:100]
                            if pd.notna(row["brand"]) and str(row["brand"]).strip()
                            else None
                        )

                        # Validate price
                        try:
                            price = (
                                float(row["price"]) if pd.notna(row["price"]) else 0.0
                            )
                            if price < 0:
                                price = 0.0
                        except (ValueError, TypeError):
                            price = 0.0

                        # Clean description
                        description = None
                        if pd.notna(row["description"]):
                            desc_str = str(row["description"])
                            # Truncate very long descriptions
                            if len(desc_str) > 5000:
                                desc_str = desc_str[:5000] + "..."
                            description = desc_str

                        # Parse images - handle different formats
                        images = []
                        if pd.notna(row["images"]):
                            try:
                                image_str = str(row["images"])
                                # Handle different image formats
                                if image_str.startswith("{") and image_str.endswith(
                                    "}"
                                ):
                                    # Remove braces and split
                                    image_str = image_str.strip("{}")
                                    images = [
                                        img.strip()
                                        for img in image_str.split(",")
                                        if img.strip()
                                    ]
                                elif image_str.startswith("[") and image_str.endswith(
                                    "]"
                                ):
                                    # JSON array format
                                    images = json.loads(image_str)
                                else:
                                    # Comma separated
                                    images = [
                                        img.strip()
                                        for img in image_str.split(",")
                                        if img.strip()
                                    ]

                                # Validate URLs
                                valid_images = []
                                for img in images:
                                    if img.startswith("http") and len(img) < 500:
                                        valid_images.append(img)
                                images = valid_images[:10]  # Limit to 10 images

                            except Exception:
                                images = []

                        # Parse tags
                        tags = []
                        if pd.notna(row["tags"]):
                            try:
                                tag_str = str(row["tags"])
                                if tag_str.startswith("{") and tag_str.endswith("}"):
                                    tag_str = tag_str.strip("{}")
                                    tags = [
                                        tag.strip().strip('"')
                                        for tag in tag_str.split(",")
                                        if tag.strip()
                                    ]
                                elif tag_str.startswith("[") and tag_str.endswith("]"):
                                    tags = json.loads(tag_str)
                                else:
                                    tags = [
                                        tag.strip()
                                        for tag in tag_str.split(",")
                                        if tag.strip()
                                    ]

                                # Clean and limit tags
                                tags = [
                                    tag[:50] for tag in tags if tag and len(tag) > 1
                                ][:20]
                            except Exception:
                                tags = []

                        # Parse specification and technical details safely
                        specification = None
                        if pd.notna(row["specification"]):
                            try:
                                spec_str = str(row["specification"])
                                if len(spec_str) > 2000:
                                    spec_str = spec_str[:2000] + "..."
                                specification = json.dumps({"details": spec_str})
                            except Exception:
                                specification = None

                        technical_details = None
                        if pd.notna(row["technical_details"]):
                            try:
                                tech_str = str(row["technical_details"])
                                if len(tech_str) > 2000:
                                    tech_str = tech_str[:2000] + "..."
                                technical_details = json.dumps({"details": tech_str})
                            except Exception:
                                technical_details = None

                        # Product dimensions
                        product_dimensions = None
                        if pd.notna(row["product_dimensions"]):
                            try:
                                dim_str = str(row["product_dimensions"])
                                product_dimensions = json.dumps({"dimensions": dim_str})
                            except Exception:
                                product_dimensions = None

                        # Validate stock quantity
                        try:
                            stock_quantity = (
                                int(row["stock_quantity"])
                                if pd.notna(row["stock_quantity"])
                                else random.randint(10, 100)
                            )
                            if stock_quantity < 0:
                                stock_quantity = 0
                        except (ValueError, TypeError):
                            stock_quantity = random.randint(10, 100)

                        # Clean URL
                        product_url = None
                        if pd.notna(row["product_url"]):
                            url_str = str(row["product_url"])
                            if url_str.startswith("http") and len(url_str) < 500:
                                product_url = url_str

                        # Meta title and description
                        meta_title = name[:200]
                        meta_description = None
                        if pd.notna(row["meta_description"]):
                            meta_desc = str(row["meta_description"])
                            if len(meta_desc) > 500:
                                meta_desc = meta_desc[:500] + "..."
                            meta_description = meta_desc

                        # Insert product with error handling
                        conn.execute(
                            text("""
                            INSERT INTO products (
                                id, name, code, brand, category_id, price, description,
                                specification, technical_details, product_dimensions,
                                images, product_url, is_amazon_seller, is_active,
                                stock_quantity, in_stock, is_embedding_generated,
                                custom_fields, meta_title, meta_description, tags
                            ) VALUES (
                                :id, :name, :code, :brand, :category_id, :price, :description,
                                :specification, :technical_details, :product_dimensions,
                                :images, :product_url, :is_amazon_seller, :is_active,
                                :stock_quantity, :in_stock, :is_embedding_generated,
                                :custom_fields, :meta_title, :meta_description, :tags
                            ) ON CONFLICT (code) DO UPDATE SET
                                name = EXCLUDED.name,
                                price = EXCLUDED.price,
                                description = EXCLUDED.description,
                                updated_at = NOW()
                        """),
                            {
                                "id": product_id,
                                "name": name,
                                "code": code,
                                "brand": brand,
                                "category_id": category_id,
                                "price": price,
                                "description": description,
                                "specification": specification,
                                "technical_details": technical_details,
                                "product_dimensions": product_dimensions,
                                "images": images,
                                "product_url": product_url,
                                "is_amazon_seller": bool(
                                    row.get("is_amazon_seller", False)
                                ),
                                "is_active": bool(row.get("is_active", True)),
                                "stock_quantity": stock_quantity,
                                "in_stock": bool(row.get("in_stock", True)),
                                "is_embedding_generated": bool(
                                    row.get("is_embedding_generated", False)
                                ),
                                "custom_fields": json.dumps({}),
                                "meta_title": meta_title,
                                "meta_description": meta_description,
                                "tags": json.dumps(tags),
                            },
                        )

                        self.products.append(
                            {
                                "id": product_id,
                                "name": name,
                                "category_id": category_id,
                                "price": price,
                                "brand": brand,
                            }
                        )

                        products_imported += 1

                        if products_imported % 100 == 0:
                            logger.info(f"Imported {products_imported} products...")

                except Exception as e:
                    products_failed += 1
                    logger.warning(
                        f"Failed to import product {row.get('name', 'Unknown')} (row {index}): {e}"
                    )
                    continue

            logger.info(
                f"✅ Imported {products_imported} products from CSV ({products_failed} failed)"
            )
        except Exception as e:
            logger.warning(
                f"Could not import from CSV: {e}. Generating sample products."
            )
            self._generate_sample_products()

    def _generate_sample_products(self):
        """Generate sample products if CSV import fails"""
        logger.info("Generating 100 sample products...")
        category_list = list(self.categories.values())
        sample_names = [
            "Wireless Bluetooth Speaker",
            "Smart LED Light Bulb",
            "Portable Power Bank",
            "Educational Science Kit",
            "Building Block Set",
            "Remote Control Car",
            "Fitness Tracker",
            "Yoga Mat",
            "Running Shoes",
            "Wireless Earbuds",
            "Coffee Maker",
            "Blender",
            "Toaster Oven",
            "Garden Tool Set",
            "Art Supply Kit",
        ]
        sample_brands = (
            list(self.brands.keys()) if self.brands else ["Generic", "Sample"]
        )
        for i in range(100):
            product_id = str(uuid.uuid4())
            name = f"{random.choice(sample_names)} {i + 1}"
            code = f"SAMPLE_{i:04d}"
            category_id = random.choice(category_list)
            brand = random.choice(sample_brands)
            price = round(random.uniform(10, 200), 2)
            description = f"A sample {name.lower()} for testing purposes."
            stock_quantity = random.randint(10, 100)
            with self.engine.begin() as conn:
                conn.execute(
                    text("""
                    INSERT INTO products (
                        id, name, code, brand, category_id, price, description,
                        stock_quantity, in_stock, is_active, custom_fields, tags
                    ) VALUES (
                        :id, :name, :code, :brand, :category_id, :price, :description,
                        :stock_quantity, :in_stock, :is_active, :custom_fields, :tags
                    ) ON CONFLICT (code) DO NOTHING
                    """),
                    {
                        "id": product_id,
                        "name": name,
                        "code": code,
                        "brand": brand,
                        "category_id": category_id,
                        "price": price,
                        "description": description,
                        "stock_quantity": stock_quantity,
                        "in_stock": True,
                        "is_active": True,
                        "custom_fields": json.dumps({}),
                        "tags": json.dumps(["sample", "test"]),
                    },
                )
            self.products.append(
                {
                    "id": product_id,
                    "name": name,
                    "category_id": category_id,
                    "price": price,
                    "brand": brand,
                }
            )
        logger.info("✅ Generated 100 sample products")

    def _generate_users(self, session, count: int):
        """Generate realistic users"""
        logger.info(f"Generating {count} users...")

        # Get customer role ID
        customer_role_result = session.execute(
            text("SELECT id FROM roles WHERE name = 'customer'")
        ).fetchone()
        customer_role_id = customer_role_result.id if customer_role_result else None

        for i in range(count):
            user_id = str(uuid.uuid4())

            # Generate user data
            first_name = self.fake.first_name()
            last_name = self.fake.last_name()
            username = f"{first_name.lower()}.{last_name.lower()}.{i}"
            email = f"{first_name.lower()}.{last_name.lower()}.{i}@example.com"

            # Create user preferences based on realistic patterns
            interests = random.sample(
                [
                    "electronics",
                    "toys",
                    "books",
                    "sports",
                    "beauty",
                    "home",
                    "automotive",
                    "health",
                    "fashion",
                    "music",
                ],
                random.randint(2, 5),
            )

            preferences = {
                "price_range": random.choice(["budget", "mid-range", "premium"]),
                "brand_preference": random.choice(
                    ["no_preference", "brand_loyal", "value_focused"]
                ),
                "interests": interests,
            }

            dob_date = self.fake.date_of_birth(minimum_age=18, maximum_age=70)
            date_of_birth = datetime.combine(dob_date, time(0, 0))

            session.execute(
                text("""
                INSERT INTO users (
                    id, username, email, hashed_password, first_name, last_name,
                    is_active, is_verified, date_of_birth, gender,
                    preferences, interests, login_count
                ) VALUES (
                    :id, :username, :email, :hashed_password, :first_name, :last_name,
                    :is_active, :is_verified, :date_of_birth, :gender,
                    :preferences, :interests, :login_count
                )
            """),
                {
                    "id": user_id,
                    "username": username,
                    "email": email,
                    "hashed_password": "$2b$12$3CqmhFLIzV0zoR94ZYk4K.DY8mno6P2FVsJ5twcdrLT5u3q0Obq9y",  # password123
                    "first_name": first_name,
                    "last_name": last_name,
                    "is_active": True,
                    "is_verified": random.choice([True, False]),
                    "date_of_birth": date_of_birth,
                    "gender": random.choice(["male", "female", "other"]),
                    "preferences": json.dumps(preferences),
                    "interests": json.dumps(interests),
                    "login_count": random.randint(1, 50),
                },
            )

            # Assign customer role
            if customer_role_id:
                session.execute(
                    text("""
                    INSERT INTO user_roles (user_id, role_id)
                    VALUES (:user_id, :role_id)
                """),
                    {
                        "user_id": user_id,
                        "role_id": customer_role_id,
                    },
                )

            self.users.append(
                {
                    "id": user_id,
                    "username": username,
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "preferences": preferences,
                    "interests": interests,
                }
            )

        logger.info(f"✅ Generated {count} users")

    def _generate_orders(self, session, count: int):
        """Generate realistic orders with seasonal patterns"""
        logger.info(f"Generating {count} orders...")

        if not self.users or not self.products:
            logger.error("Need users and products before generating orders")
            return

        # Order status distribution
        order_statuses = [
            "pending",
            "confirmed",
            "processing",
            "shipped",
            "delivered",
            "cancelled",
        ]
        status_weights = [0.05, 0.10, 0.15, 0.15, 0.50, 0.05]

        payment_methods = [
            "credit_card",
            "paypal",
            "bank_transfer",
            "apple_pay",
            "google_pay",
        ]
        recommendation_sources = [
            "collaborative",
            "content_based",
            "hybrid",
            "popular",
            "search",
            None,
        ]
        rec_weights = [
            0.20,
            0.15,
            0.25,
            0.10,
            0.15,
            0.15,
        ]  # 15% direct (no recommendation)

        generated_orders = 0
        for i in range(count):
            # Select random user
            user = random.choice(self.users)

            # Order timing with realistic patterns (more recent orders)
            days_ago = int(np.random.exponential(15))  # Most orders in last 15 days
            days_ago = min(days_ago, 180)  # Max 6 months ago
            order_date = datetime.now() - timedelta(days=days_ago)

            # Add seasonality
            month = order_date.month
            seasonal_multiplier = 1.0
            if month in [11, 12]:  # Holiday season
                seasonal_multiplier = 1.5
            elif month in [6, 7]:  # Summer
                seasonal_multiplier = 1.2
            elif month in [1, 2]:  # Post-holiday
                seasonal_multiplier = 0.7

            # Skip some orders based on seasonality
            if random.random() > seasonal_multiplier * 0.6:
                continue

            # Number of items (realistic distribution)
            num_items = np.random.choice(
                [1, 2, 3, 4, 5], p=[0.45, 0.30, 0.15, 0.07, 0.03]
            )

            # User preference-based product selection
            user_interests = user.get("interests", [])
            user_preferences = user.get("preferences", {})

            # Filter products based on user interests and price preference
            suitable_products = []
            for product in self.products:
                # Interest matching
                interest_match = False
                for interest in user_interests:
                    if interest.lower() in product["name"].lower():
                        interest_match = True
                        break

                # Price range matching
                price_match = True
                if (
                    user_preferences.get("price_range") == "budget"
                    and product["price"] > 50
                ):
                    price_match = False
                elif (
                    user_preferences.get("price_range") == "premium"
                    and product["price"] < 100
                ):
                    price_match = False

                if interest_match or random.random() < 0.3:  # 30% random selection
                    if (
                        price_match or random.random() < 0.5
                    ):  # 50% ignore price for variety
                        suitable_products.append(product)

            if not suitable_products:
                suitable_products = self.products

            # Select products for this order
            selected_products = random.sample(
                suitable_products, min(num_items, len(suitable_products))
            )

            # Calculate order totals
            subtotal = 0
            order_items = []

            for product in selected_products:
                quantity = random.randint(1, 3)
                unit_price = Decimal(str(product["price"]))
                total_price = unit_price * quantity
                subtotal += total_price

                order_items.append(
                    {
                        "product_id": product["id"],
                        # "product_name": product["name"],
                        "quantity": quantity,
                        "unit_price": unit_price,
                        "total_price": total_price,
                    }
                )

            # Calculate additional costs
            tax_rate = Decimal("0.08")  # 8% tax
            shipping_amount = (
                Decimal("10.00") if subtotal < 50 else Decimal("0.00")
            )  # Free shipping over $50
            tax_amount = subtotal * tax_rate
            total_amount = subtotal + tax_amount + shipping_amount

            # Order details
            order_id = str(uuid.uuid4())
            order_number = f"ORD-{order_date.strftime('%Y%m%d')}-{generated_orders:06d}"
            status = np.random.choice(order_statuses, p=status_weights)
            payment_method = random.choice(payment_methods)
            recommendation_source = np.random.choice(
                recommendation_sources, p=rec_weights
            )

            # Create realistic addresses
            billing_address = {
                "name": f"{user['first_name']} {user['last_name']}",
                "street": self.fake.street_address(),
                "city": self.fake.city(),
                "state": self.fake.state(),
                "zip_code": self.fake.zipcode(),
                "country": "US",
            }

            shipping_address = billing_address.copy()
            if random.random() < 0.2:  # 20% different shipping address
                shipping_address = {
                    "name": self.fake.name(),
                    "street": self.fake.street_address(),
                    "city": self.fake.city(),
                    "state": self.fake.state(),
                    "zip_code": self.fake.zipcode(),
                    "country": "US",
                }

            # Insert order
            session.execute(
                text("""
                INSERT INTO orders (
                    id, user_id, order_number, subtotal, tax_amount, shipping_amount,
                    total_amount, status, payment_status, billing_address, shipping_address,
                    payment_method, recommendation_source, recommendation_session_id,
                    created_at, updated_at
                ) VALUES (
                    :id, :user_id, :order_number, :subtotal, :tax_amount, :shipping_amount,
                    :total_amount, :status, :payment_status, :billing_address, :shipping_address,
                    :payment_method, :recommendation_source, :recommendation_session_id,
                    :created_at, :updated_at
                )
            """),
                {
                    "id": order_id,
                    "user_id": user["id"],
                    "order_number": order_number,
                    "subtotal": float(subtotal),
                    "tax_amount": float(tax_amount),
                    "shipping_amount": float(shipping_amount),
                    "total_amount": float(total_amount),
                    "status": status,
                    "payment_status": "paid" if status != "cancelled" else "failed",
                    "billing_address": json.dumps(billing_address),
                    "shipping_address": json.dumps(shipping_address),
                    "payment_method": payment_method,
                    "recommendation_source": recommendation_source,
                    "recommendation_session_id": f"rec_{order_date.strftime('%Y%m%d')}_{generated_orders}"
                    if recommendation_source
                    else None,
                    "created_at": order_date,
                    "updated_at": order_date,
                },
            )

            # Insert order items
            for item in order_items:
                session.execute(
                    text("""
                    INSERT INTO order_items (
                        id, order_id, product_id, quantity, unit_price, total_price
                    ) VALUES (
                        :id, :order_id, :product_id, :quantity, :unit_price, :total_price
                    )
                """),
                    {
                        "id": str(uuid.uuid4()),
                        "order_id": order_id,
                        "product_id": item["product_id"],
                        "quantity": item["quantity"],
                        "unit_price": float(item["unit_price"]),
                        "total_price": float(item["total_price"]),
                    },
                )

            self.orders.append(
                {
                    "id": order_id,
                    "user_id": user["id"],
                    "total_amount": float(total_amount),
                    "status": status,
                    "recommendation_source": recommendation_source,
                    "created_at": order_date,
                    "items": order_items,
                }
            )
            generated_orders += 1

        logger.info(f"✅ Generated {len(self.orders)} orders")

    def _generate_search_analytics(self, session, count: int):
        """Generate realistic search analytics"""
        logger.info(f"Generating {count} search analytics records...")

        if not self.categories:
            logger.warning(
                "No categories available. Skipping filters in search analytics."
            )
            category_keys = []
        else:
            category_keys = list(self.categories.keys())

        if not self.brands:
            logger.warning(
                "No brands available. Skipping brand filters in search analytics."
            )
            brand_keys = []
        else:
            brand_keys = list(self.brands.keys())

        # Common search terms based on your product data
        search_terms = [
            "electronic",
            "kit",
            "toy",
            "circuit",
            "radio",
            "detector",
            "music",
            "sound",
            "educational",
            "science",
            "learning",
            "kids",
            "children",
            "snap",
            "building",
            "STEM",
            "robot",
            "sensor",
            "LED",
            "battery",
            "wireless",
            "bluetooth",
            "solar",
            "motor",
            "switch",
            "speaker",
            "microphone",
            "alarm",
            "timer",
        ]

        # Extend with product names and brands
        for product in self.products[:50]:  # Use subset for search terms
            words = product["name"].split()[:3]  # First 3 words
            search_terms.extend([word.lower() for word in words if len(word) > 3])

        search_terms = list(set(search_terms))  # Remove duplicates

        for i in range(count):
            # User and session
            user = (
                random.choice(self.users) if random.random() < 0.7 else None
            )  # 30% anonymous
            session_id = f"search_{datetime.now().strftime('%Y%m%d')}_{i}"

            # Search query (realistic combinations)
            if random.random() < 0.6:  # Single term
                query = random.choice(search_terms)
            else:  # Multiple terms
                query = " ".join(random.sample(search_terms, random.randint(2, 3)))

            # Search timing
            search_time = datetime.now() - timedelta(
                days=random.randint(0, 30),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )

            # Results and interaction
            results_count = random.randint(0, 50)
            response_time = random.randint(50, 500)  # milliseconds

            # Click interaction (30% of searches result in clicks)
            clicked_product_id = None
            click_position = None
            if random.random() < 0.3 and self.products:
                clicked_product_id = random.choice(self.products)["id"]
                click_position = (
                    random.randint(1, min(10, results_count))
                    if results_count > 0
                    else 1
                )

            # Filters applied (20% of searches use filters)
            filters_applied = None
            if random.random() < 0.2:
                filters_applied = {}
                if random.random() < 0.5 and category_keys:
                    filters_applied["category"] = random.choice(category_keys)
                if random.random() < 0.3:
                    filters_applied["price_min"] = random.choice([10, 25, 50])
                if random.random() < 0.3:
                    filters_applied["price_max"] = random.choice([100, 200, 500])
                if random.random() < 0.2 and brand_keys:
                    filters_applied["brand"] = random.choice(brand_keys)
                if not filters_applied:
                    filters_applied = None

            session.execute(
                text("""
                INSERT INTO search_analytics (
                    id, user_id, session_id, query, search_type, results_count,
                    clicked_product_id, click_position, response_time_ms,
                    filters_applied, sort_option, user_agent, ip_address, created_at
                ) VALUES (
                    :id, :user_id, :session_id, :query, :search_type, :results_count,
                    :clicked_product_id, :click_position, :response_time_ms,
                    :filters_applied, :sort_option, :user_agent, :ip_address, :created_at
                )
            """),
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user["id"] if user else None,
                    "session_id": session_id,
                    "query": query,
                    "search_type": "text_vector_hybrid",
                    "results_count": results_count,
                    "clicked_product_id": clicked_product_id,
                    "click_position": click_position,
                    "response_time_ms": response_time,
                    "filters_applied": json.dumps(filters_applied)
                    if filters_applied
                    else None,
                    "sort_option": random.choice(
                        ["relevance", "price_low", "price_high", "newest"]
                    ),
                    "user_agent": self.fake.user_agent(),
                    "ip_address": self.fake.ipv4(),
                    "created_at": search_time,
                },
            )

        logger.info(f"✅ Generated {count} search analytics records")

    def _generate_user_behavior(self, session):
        """Generate user behavior tracking data"""
        logger.info("Generating user behavior data...")

        if not self.users or not self.products:
            logger.warning("No users or products for behavior data. Skipping.")
            return

        behavior_events = [
            "product_view",
            "category_view",
            "add_to_cart",
            "remove_from_cart",
            "add_to_wishlist",
            "remove_from_wishlist",
            "product_share",
            "review_click",
        ]

        behavior_count = 0

        for user in self.users:
            # Generate 5-20 behavior events per user
            num_events = random.randint(5, 20)

            for _ in range(num_events):
                event_type = random.choice(behavior_events)
                product = random.choice(self.products)

                # Event timing
                event_time = datetime.now() - timedelta(
                    days=random.randint(0, 60),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59),
                )

                # Event data
                event_data = {
                    "duration_seconds": random.randint(10, 300),
                    "scroll_depth": random.uniform(0.2, 1.0),
                    "referrer_type": random.choice(
                        ["search", "recommendation", "direct", "social"]
                    ),
                }

                session.execute(
                    text("""
                    INSERT INTO user_behavior (
                        id, user_id, session_id, event_type, product_id, category_id,
                        page_url, referrer, device_type, event_data, created_at
                    ) VALUES (
                        :id, :user_id, :session_id, :event_type, :product_id, :category_id,
                        :page_url, :referrer, :device_type, :event_data, :created_at
                    )
                """),
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": user["id"],
                        "session_id": f"session_{event_time.strftime('%Y%m%d')}_{user['id'][:8]}",
                        "event_type": event_type,
                        "product_id": product["id"],
                        "category_id": product["category_id"],
                        "page_url": f"/products/{product['id']}",
                        "referrer": random.choice(
                            [
                                None,
                                "https://google.com",
                                "https://facebook.com",
                                "direct",
                            ]
                        ),
                        "device_type": random.choice(["desktop", "mobile", "tablet"]),
                        "event_data": json.dumps(event_data),
                        "created_at": event_time,
                    },
                )

                behavior_count += 1

        logger.info(f"✅ Generated {behavior_count} user behavior events")

    def _generate_recommendation_data(self, session):
        """Generate recommendation tracking data"""
        logger.info("Generating recommendation tracking data...")

        if not self.orders and not self.users:
            logger.warning("No orders or users for recommendations. Skipping.")
            return

        algorithms = [
            "collaborative",
            "content_based",
            "hybrid",
            "popular",
            "recently_viewed",
        ]
        recommendation_types = [
            "homepage",
            "product_page",
            "cart",
            "checkout",
            "search_results",
        ]

        recommendation_count = 0

        # Generate recommendations for orders that used recommendation sources
        for order in self.orders:
            if (
                order["recommendation_source"]
                and order["recommendation_source"] != "search"
            ):
                for item in order["items"]:
                    # Create recommendation result
                    session.execute(
                        text("""
                        INSERT INTO recommendation_results (
                            id, user_id, product_id, session_id, algorithm, score, rank,
                            recommendation_type, context_data, was_clicked, was_purchased,
                            click_timestamp, created_at
                        ) VALUES (
                            :id, :user_id, :product_id, :session_id, :algorithm, :score, :rank,
                            :recommendation_type, :context_data, :was_clicked, :was_purchased,
                            :click_timestamp, :created_at
                        )
                    """),
                        {
                            "id": str(uuid.uuid4()),
                            "user_id": order["user_id"],
                            "product_id": item["product_id"],
                            "session_id": f"rec_{order['created_at'].strftime('%Y%m%d')}_{order['user_id'][:8]}",
                            "algorithm": order["recommendation_source"],
                            "score": random.uniform(0.6, 0.95),
                            "rank": random.randint(1, 10),
                            "recommendation_type": random.choice(recommendation_types),
                            "context_data": json.dumps(
                                {"reason": "purchased", "confidence": "high"}
                            ),
                            "was_clicked": True,
                            "was_purchased": True,
                            "click_timestamp": order["created_at"],
                            "created_at": order["created_at"]
                            - timedelta(minutes=random.randint(1, 60)),
                        },
                    )

                    recommendation_count += 1

        # Generate additional recommendations that weren't purchased
        for user in random.sample(self.users, min(500, len(self.users))):
            num_recs = random.randint(10, 50)

            for _ in range(num_recs):
                product = random.choice(self.products)
                algorithm = random.choice(algorithms)

                rec_time = datetime.now() - timedelta(
                    days=random.randint(0, 30), hours=random.randint(0, 23)
                )

                was_clicked = random.random() < 0.15  # 15% click rate

                session.execute(
                    text("""
                    INSERT INTO recommendation_results (
                        id, user_id, product_id, session_id, algorithm, score, rank,
                        recommendation_type, context_data, was_clicked, was_purchased,
                        click_timestamp, created_at
                    ) VALUES (
                        :id, :user_id, :product_id, :session_id, :algorithm, :score, :rank,
                        :recommendation_type, :context_data, :was_clicked, :was_purchased,
                        :click_timestamp, :created_at
                    )
                """),
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": user["id"],
                        "product_id": product["id"],
                        "session_id": f"rec_{rec_time.strftime('%Y%m%d')}_{user['id'][:8]}",
                        "algorithm": algorithm,
                        "score": random.uniform(0.3, 0.9),
                        "rank": random.randint(1, 20),
                        "recommendation_type": random.choice(recommendation_types),
                        "context_data": json.dumps({"reason": "algorithm_suggestion"}),
                        "was_clicked": was_clicked,
                        "was_purchased": False,
                        "click_timestamp": rec_time if was_clicked else None,
                        "created_at": rec_time,
                    },
                )

                recommendation_count += 1

        logger.info(
            f"✅ Generated {recommendation_count} recommendation tracking records"
        )

    def _create_ml_model_configs(self, session):
        """Create ML model configurations"""
        logger.info("Creating ML model configurations...")

        # Check if required columns exist first
        try:
            # Test query to check if all columns exist
            session.execute(
                text("""
                SELECT id, name, model_type, parameters, description, is_active,
                       accuracy_score, precision_score, recall_score, created_at
                FROM ml_model_configs LIMIT 0
            """)
            )
        except Exception as e:
            logger.error(f"Missing columns in ml_model_configs table: {e}")
            logger.error("Please run: psql -d your_database -f fix_schema.sql")
            return

        model_configs = [
            {
                "name": "Collaborative_Filtering_v1",
                "model_type": "collaborative",
                "parameters": {
                    "n_factors": 50,
                    "n_epochs": 20,
                    "lr_all": 0.005,
                    "reg_all": 0.02,
                    "random_state": 42,
                },
                "description": "User-based collaborative filtering with matrix factorization",
                "is_active": True,
            },
            {
                "name": "Content_Based_v1",
                "model_type": "content_based",
                "parameters": {
                    "similarity_threshold": 0.5,
                    "max_features": 5000,
                    "ngram_range": [1, 2],
                    "min_df": 2,
                },
                "description": "Content-based filtering using product features",
                "is_active": True,
            },
            {
                "name": "Hybrid_Model_v1",
                "model_type": "hybrid",
                "parameters": {
                    "collaborative_weight": 0.6,
                    "content_weight": 0.4,
                    "min_interactions": 5,
                },
                "description": "Hybrid model combining collaborative and content-based approaches",
                "is_active": True,
            },
            {
                "name": "LightGBM_Ranker_v1",
                "model_type": "lightgbm",
                "parameters": {
                    "num_leaves": 31,
                    "learning_rate": 0.05,
                    "feature_fraction": 0.9,
                    "bagging_fraction": 0.8,
                    "bagging_freq": 5,
                    "verbose": 0,
                },
                "description": "LightGBM model for ranking recommendations",
                "is_active": False,
            },
        ]

        for config in model_configs:
            # Check if exists
            existing = session.execute(
                text("SELECT id FROM ml_model_configs WHERE name = :name"),
                {"name": config["name"]},
            ).fetchone()
            if existing:
                logger.info(f"ML config '{config['name']}' already exists")
                continue

            try:
                session.execute(
                    text("""
                    INSERT INTO ml_model_configs (
                        id, name, model_type, parameters, description, is_active,
                        accuracy_score, precision_score, recall_score, created_at
                    ) VALUES (
                        :id, :name, :model_type, :parameters, :description, :is_active,
                        :accuracy_score, :precision_score, :recall_score, :created_at
                    )
                """),
                    {
                        "id": str(uuid.uuid4()),
                        "name": config["name"],
                        "model_type": config["model_type"],
                        "parameters": json.dumps(config["parameters"]),
                        "description": config["description"],
                        "is_active": config["is_active"],
                        "accuracy_score": random.uniform(0.75, 0.92)
                        if config["is_active"]
                        else None,
                        "precision_score": random.uniform(0.70, 0.88)
                        if config["is_active"]
                        else None,
                        "recall_score": random.uniform(0.65, 0.85)
                        if config["is_active"]
                        else None,
                        "created_at": datetime.now(),
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to create ML config {config['name']}: {e}")
                continue

        logger.info("✅ Created/verified ML model configurations")

    # def _create_user_segments(self, session):
    #     """Create user segments"""
    #     logger.info("Creating user segments...")

    #     segments = [
    #         {
    #             "name": "High Value Customers",
    #             "description": "Customers with high lifetime value",
    #             "segment_type": "rfm",
    #             "criteria": {
    #                 "monetary_amount": {"min": 500, "max": None},
    #                 "frequency_orders": {"min": 3, "max": None},
    #                 "recency_days": {"min": 0, "max": 90},
    #             },
    #         },
    #         {
    #             "name": "Electronics Enthusiasts",
    #             "description": "Users who frequently buy electronics",
    #             "segment_type": "behavioral",
    #             "criteria": {
    #                 "categories": ["Electronics"],
    #                 "min_purchases": 2,
    #                 "days_back": 180,
    #             },
    #         },
    #         {
    #             "name": "Bargain Hunters",
    #             "description": "Price-sensitive customers",
    #             "segment_type": "purchase_based",
    #             "criteria": {
    #                 "avg_order_value": {"max": 50},
    #                 "discount_usage": {"min": 0.7},
    #             },
    #         },
    #         {
    #             "name": "Young Adults",
    #             "description": "Users aged 18-35",
    #             "segment_type": "demographic",
    #             "criteria": {"age_range": {"min": 18, "max": 35}},
    #         },
    #         {
    #             "name": "At Risk Customers",
    #             "description": "Customers who might churn",
    #             "segment_type": "rfm",
    #             "criteria": {
    #                 "recency_days": {"min": 120, "max": None},
    #                 "frequency_orders": {"min": 1, "max": None},
    #             },
    #         },
    #     ]

    #     for segment in segments:
    #         # Check if exists
    #         existing = session.execute(
    #             text("SELECT id FROM user_segments WHERE name = :name"),
    #             {"name": segment["name"]}
    #         ).fetchone()
    #         if existing:
    #             logger.info(f"User segment '{segment['name']}' already exists")
    #             continue

    #         segment_id = str(uuid.uuid4())

    #         session.execute(
    #             text("""
    #             INSERT INTO user_segments (
    #                 id, name, description, segment_type, criteria,
    #                 is_active, auto_update, member_count, created_at
    #             ) VALUES (
    #                 :id, :name, :description, :segment_type, :criteria,
    #                 :is_active, :auto_update, :member_count, :created_at
    #             )
    #         """),
    #             {
    #                 "id": segment_id,
    #                 "name": segment["name"],
    #                 "description": segment["description"],
    #                 "segment_type": segment["segment_type"],
    #                 "criteria": json.dumps(segment["criteria"]),
    #                 "is_active": True,
    #                 "auto_update": True,
    #                 "member_count": 0,  # Will be calculated later
    #                 "created_at": datetime.now(),
    #             },
    #         )

    #     logger.info(f"✅ Created/verified {len(segments)} user segments")

    def _generate_summary(self, session):
        """Generate migration summary"""

        # Count records
        counts = {}
        tables = [
            "users",
            "products",
            "product_categories",
            "orders",
            "order_items",
            "search_analytics",
            "user_behavior",
            "recommendation_results",
            "ml_model_configs",
            "user_segments",
        ]

        for table in tables:
            try:
                result = session.execute(
                    text(f"SELECT COUNT(*) FROM {table}")
                ).fetchone()
                counts[table] = result[0] if result else 0
            except:
                counts[table] = 0

        # Calculate some metrics
        try:
            total_revenue = session.execute(
                text("""
                SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE status != 'cancelled'
            """)
            ).fetchone()[0]
        except:
            total_revenue = 0

        try:
            avg_order_value = session.execute(
                text("""
                SELECT COALESCE(AVG(total_amount), 0) FROM orders WHERE status != 'cancelled'
            """)
            ).fetchone()[0]
        except:
            avg_order_value = 0

        return {
            "status": "completed",
            "timestamp": datetime.now().isoformat(),
            "record_counts": counts,
            "metrics": {
                "total_revenue": float(total_revenue),
                "average_order_value": float(avg_order_value),
                "products_with_orders": len(
                    [o for o in self.orders if len(o["items"]) > 0]
                ),
            },
            "notes": [
                "✅ Database populated with realistic e-commerce data",
                "✅ ML model configurations created and ready for training",
                "✅ User segments created for targeted marketing",
                "✅ Recommendation tracking data available for analytics",
                "✅ Search analytics ready for performance optimization",
            ],
        }

    def truncate_all_tables(self):
        """
        Connects to the PostgreSQL database defined in DATABASE_URL and
        truncates all user tables (resets identity and cascades foreign keys).
        """
        try:
            # Connect using DATABASE_URL
            conn = psycopg2.connect(DATABASE_URL)
            conn.autocommit = True
            cur = conn.cursor()

            print("🔗 Connected to database recom_sys")

            # Disable foreign key constraints & triggers
            cur.execute("SET session_replication_role = replica;")

            # Get all user tables (skip system schemas)
            cur.execute("""
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                AND table_schema NOT IN ('pg_catalog', 'information_schema');
            """)
            tables = cur.fetchall()

            if not tables:
                print("⚠️ No user tables found to truncate.")
                return

            # Truncate all tables
            for schema, table in tables:
                query = sql.SQL(
                    "TRUNCATE TABLE {}.{} RESTART IDENTITY CASCADE;"
                ).format(sql.Identifier(schema), sql.Identifier(table))
                cur.execute(query)
                print(f"✅ Truncated table: {schema}.{table}")

            # Re-enable triggers
            cur.execute("SET session_replication_role = DEFAULT;")

            cur.close()
            conn.close()
            print("🎉 All tables truncated successfully!")

        except Exception as e:
            print("❌ Error truncating tables:", e)


# Usage example
if __name__ == "__main__":
    # Database connection - updated for Docker environment
    # When running inside Docker container, use 'postgres' as host
    # When running locally, use 'localhost'
    import os

    # Check if running in Docker (backend container has this env var from docker-compose)
    if os.getenv("RUNNING_IN_DOCKER") or os.path.exists("/.dockerenv"):
        DATABASE_URL = (
            "postgresql://ecommerce_user:ecommerce_pass@postgres:5432/ecommerce"
        )
    else:
        DATABASE_URL = (
            "postgresql://ecommerce_user:ecommerce_pass@localhost:5435/ecommerce"
        )

    # CSV file path - will be in /app/ when running in Docker
    import os

    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    CSV_FILE_PATH = os.path.join(SCRIPT_DIR, "products-data.csv")

    # Initialize migrator
    migrator = CompleteEcomDataMigrator(DATABASE_URL, CSV_FILE_PATH)
    migrator.truncate_all_tables()
    # Run complete migration
    summary = migrator.migrate_all_data(
        users_count=2000,  # Number of users to generate
        orders_count=8000,  # Number of orders to generate
        search_interactions=25000,  # Number of search analytics records
    )

    print("\n" + "=" * 60)
    print("🎉 DATA MIGRATION COMPLETED!")
    print("=" * 60)

    print("\n📊 Records Created:")
    for table, count in summary["record_counts"].items():
        print(f"   {table}: {count:,}")

    print("\n💰 Business Metrics:")
    print(f"   Total Revenue: ${summary['metrics']['total_revenue']:,.2f}")
    print(f"   Average Order Value: ${summary['metrics']['average_order_value']:.2f}")

    print("\n📝 Migration Notes:")
    for note in summary["notes"]:
        print(f"   {note}")

    print("\n🚀 Next Steps:")
    print("   1. ✅ Your database is now populated with realistic training data")
    print("   2. 🤖 ML models can be trained with sufficient data")
    print("   3. 📈 Analytics dashboard will show meaningful metrics")
    print("   4. 🎯 Recommendation engine has user behavior data")
    print("   5. 🔍 Search analytics provide insights for optimization")

    print("\n🔐 Default Access:")
    print("   Admin: admin@ecommerce.com / password123")
    print("   Users: firstname.lastname.N@example.com / password123")
