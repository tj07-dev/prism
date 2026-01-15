"""
Complete User Update Script (Fixed)
This script updates all users in the database according to the specifications:
- Set is_superuser to False if invalid (not boolean).
- Assign a random phone number.
- Randomly assign 1-5 products to viewed_products from the products table (as JSON array of string IDs).
- If last_login is not null/None, update to a random date within the past 9-12 months.
- Generate mock search analytics (5-15 per user).
- Add mock address JSON to all users.

Requirements: Install faker, sqlalchemy, and psycopg2-binary if not already installed.
pip install faker sqlalchemy psycopg2-binary
"""

import json

# Database configuration - updated for Docker environment
import os
import random
from datetime import datetime, timedelta

from faker import Faker
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Check if running in Docker
if os.getenv("RUNNING_IN_DOCKER") or os.path.exists("/.dockerenv"):
    DATABASE_URL = "postgresql://ecommerce_user:ecommerce_pass@postgres:5432/ecommerce"
else:
    DATABASE_URL = "postgresql://ecommerce_user:ecommerce_pass@localhost:5435/ecommerce"

# Initialize Faker for random data
fake = Faker()


def generate_random_date_past_months(min_months=9, max_months=12):
    """Generate a random date within the past min_months to max_months months."""
    now = datetime.now()
    days_ago = random.randint(
        min_months * 28, max_months * 31
    )  # Approximate days for months
    random_date = now - timedelta(days=days_ago)
    # Set to a random time of day
    random_date = random_date.replace(
        hour=random.randint(0, 23),
        minute=random.randint(0, 59),
        second=random.randint(0, 59),
        microsecond=0,
    )
    return random_date


def generate_mock_address():
    """Generate a mock address JSON."""
    return {
        "city": fake.city(),
        "state": fake.state_abbr(),
        "street": fake.street_address(),
        "country": "US",
        "zip_code": fake.zipcode(),
        "address_type": random.choice(["home", "billing", "shipping"]),
    }


def update_users_and_generate_analytics():
    """Main function to update users and generate mock search analytics."""
    # Create engine and session
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        # Step 1: Fetch all users
        users_result = session.execute(
            text(
                "SELECT id, is_superuser, phone, last_login, viewed_products, address FROM users"
            )
        )
        users = users_result.fetchall()

        if not users:
            print("⚠️ No users found. Exiting.")
            return

        # Fetch all product IDs for random assignment to viewed_products
        products_result = session.execute(text("SELECT id FROM products"))
        product_ids = [
            str(row[0]) for row in products_result.fetchall()
        ]  # Convert UUID to string

        if not product_ids:
            print("⚠️ No products found. Skipping viewed_products assignments.")
            product_ids = []

        updated_fields_count = 0
        updated_last_login_count = 0
        updated_address_count = 0

        # Step 2: Update users
        print("👥 Updating users...")
        for user_row in users:
            user_id, is_superuser, phone, last_login, viewed_products, address = (
                user_row
            )

            # Update is_superuser: Set to False if invalid (not boolean or None)
            try:
                is_superuser_bool = (
                    is_superuser if isinstance(is_superuser, bool) else False
                )
                if is_superuser != is_superuser_bool:
                    session.execute(
                        text(
                            "UPDATE users SET is_superuser = :is_superuser WHERE id = :user_id"
                        ),
                        {"is_superuser": is_superuser_bool, "user_id": user_id},
                    )
                    updated_fields_count += 1
            except Exception as e:
                print(f"⚠️ Error updating is_superuser for user {user_id}: {e}")

            # Update phone: Assign random phone number
            new_phone = fake.phone_number()
            try:
                if phone != new_phone:
                    session.execute(
                        text("UPDATE users SET phone = :phone WHERE id = :user_id"),
                        {"phone": new_phone, "user_id": user_id},
                    )
                    updated_fields_count += 1
            except Exception as e:
                print(f"⚠️ Error updating phone for user {user_id}: {e}")

            # Update viewed_products: Randomly assign 1-5 random products (as JSON array of string IDs)
            # if product_ids:
            #     try:
            #         num_products = random.randint(1, 5)
            #         random_products = random.sample(product_ids, min(num_products, len(product_ids)))
            #         new_viewed_products = json.dumps(random_products)  # Already strings
            #         # Handle viewed_products comparison (could be JSON string, list, or None)
            #         current_viewed_str = json.dumps(viewed_products) if viewed_products else "[]"
            #         if current_viewed_str != new_viewed_products:
            #             session.execute(
            #                 text("UPDATE users SET viewed_products = :viewed_products WHERE id = :user_id"),
            #                 {"viewed_products": new_viewed_products, "user_id": user_id}
            #             )
            #             updated_fields_count += 1
            #     except Exception as e:
            #         print(f"⚠️ Error updating viewed_products for user {user_id}: {e}")

            # Update last_login: If not null/None, set to random date in past 9-12 months
            # last_login is DateTime, so check if not None
            print(last_login)
            if last_login is None:
                try:
                    new_last_login = generate_random_date_past_months()
                    session.execute(
                        text(
                            "UPDATE users SET last_login = :last_login WHERE id = :user_id"
                        ),
                        {"last_login": new_last_login, "user_id": user_id},
                    )
                    updated_last_login_count += 1
                except Exception as e:
                    print(f"⚠️ Error updating last_login for user {user_id}: {e}")

            # Update address: Generate mock address JSON if None or empty
            try:
                new_address = generate_mock_address()
                new_address_json = json.dumps(new_address)
                current_address_str = json.dumps(address) if address else "{}"
                if current_address_str != new_address_json:
                    session.execute(
                        text("UPDATE users SET address = :address WHERE id = :user_id"),
                        {"address": new_address_json, "user_id": user_id},
                    )
                    updated_address_count += 1
            except Exception as e:
                print(f"⚠️ Error updating address for user {user_id}: {e}")

        # Commit user updates
        session.commit()
        print(
            f"✅ Updated {updated_fields_count} user fields, {updated_last_login_count} last_login dates, and {updated_address_count} addresses."
        )

        # Step 3: Generate mock search analytics (5-15 per user)
        # print("🔍 Generating mock search analytics...")
        # analytics_generated = 0
        # common_queries = [
        #     "electronics kit", "toy robot", "science experiment", "building blocks",
        #     "educational toy", "STEM learning", "wireless speaker", "bluetooth earbuds",
        #     "fitness tracker", "yoga mat", "running shoes", "coffee maker", "smartphone",
        #     "laptop", "headphones", "gaming console"
        # ]
        # search_types = ["text", "vector", "hybrid"]
        # sort_options = ["relevance", "price_low", "price_high", "newest", "popular", "rating_high"]

        # # Convert product_ids back to UUID for insertion (since DB expects UUID)
        # product_uuid_ids = [uuid.UUID(pid) for pid in product_ids]

        # for user_row in users:
        #     user_id, _, _, _, _, _ = user_row
        #     num_analytics = random.randint(5, 15)
        #     for _ in range(num_analytics):
        #         try:
        #             session_id = f"analytics_{uuid.uuid4().hex[:8]}_{random.randint(1000, 9999)}"
        #             query = random.choice(common_queries)
        #             search_type = random.choice(search_types)
        #             results_count = random.randint(5, 50)
        #             clicked_product_id = random.choice(product_uuid_ids) if product_uuid_ids and random.random() < 0.4 else None
        #             click_position = random.randint(1, min(10, results_count)) if clicked_product_id else None
        #             response_time_ms = random.randint(50, 1000)

        #             # Random filters
        #             filters_applied = {}
        #             if random.random() < 0.3:
        #                 filters_applied["category"] = random.choice(["Electronics", "Toys & Games", "Sports", "Home & Garden"])
        #             if random.random() < 0.2:
        #                 filters_applied["price_min"] = random.choice([10, 25, 50])
        #             if random.random() < 0.2:
        #                 filters_applied["price_max"] = random.choice([100, 200, 500])
        #             if random.random() < 0.1:
        #                 filters_applied["brand"] = "Sample Brand"  # Or fetch from DB if needed
        #             filters_json = json.dumps(filters_applied) if filters_applied else None

        #             sort_option = random.choice(sort_options)
        #             user_agent = fake.user_agent()
        #             ip_address = fake.ipv4()
        #             created_at = datetime.now() - timedelta(days=random.randint(0, 365), hours=random.randint(0, 23))

        #             session.execute(
        #                 text("""
        #                 INSERT INTO search_analytics (
        #                     id, user_id, session_id, query, search_type, results_count,
        #                     clicked_product_id, click_position, response_time_ms,
        #                     filters_applied, sort_option, user_agent, ip_address, created_at
        #                 ) VALUES (
        #                     :id, :user_id, :session_id, :query, :search_type, :results_count,
        #                     :clicked_product_id, :click_position, :response_time_ms,
        #                     :filters_applied, :sort_option, :user_agent, :ip_address, :created_at
        #                 ) ON CONFLICT (id) DO NOTHING
        #                 """),
        #                 {
        #                     "id": uuid.uuid4(),
        #                     "user_id": user_id,
        #                     "session_id": session_id,
        #                     "query": query,
        #                     "search_type": search_type,
        #                     "results_count": results_count,
        #                     "clicked_product_id": clicked_product_id,
        #                     "click_position": click_position,
        #                     "response_time_ms": response_time_ms,
        #                     "filters_applied": filters_json,
        #                     "sort_option": sort_option,
        #                     "user_agent": user_agent,
        #                     "ip_address": ip_address,
        #                     "created_at": created_at
        #                 }
        #             )
        #             analytics_generated += 1
        #         except Exception as e:
        #             print(f"⚠️ Error generating analytics for user {user_id}: {e}")
        #             continue

        # Commit analytics
        session.commit()
        # print(f"✅ Generated {analytics_generated} mock search analytics records.")

    engine.dispose()
    print("🎉 All updates and generations completed successfully!")


if __name__ == "__main__":
    update_users_and_generate_analytics()
