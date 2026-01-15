-- Initialize PostgreSQL database with required extensions and tables
-- This script runs automatically when the postgres container is first created

-- Initialize PostgreSQL with required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- for text search similarity

-- ===========================================
-- TABLE CREATION STATEMENTS
-- ===========================================

-- Roles table (no dependencies)
CREATE TABLE IF NOT EXISTS roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    permissions JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    created_by UUID,
    updated_by UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Product categories table (no dependencies)
CREATE TABLE IF NOT EXISTS product_categories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) UNIQUE,
    description TEXT,
    parent_id UUID REFERENCES product_categories(id),
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    meta_title VARCHAR(200),
    meta_description TEXT,
    created_by UUID,
    updated_by UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Users table (depends on roles via association table)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(20),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    is_superuser BOOLEAN DEFAULT FALSE,
    date_of_birth TIMESTAMP WITHOUT TIME ZONE,
    gender VARCHAR(10),
    interests JSONB,
    preferences JSONB,
    address JSONB,
    last_login TIMESTAMP WITHOUT TIME ZONE,
    login_count INTEGER DEFAULT 0,
    created_by UUID,
    updated_by UUID,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    viewed_products JSONB DEFAULT '[]'::jsonb
);

-- User roles association table
CREATE TABLE IF NOT EXISTS user_roles (
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

-- Products table (depends on product_categories)
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(200) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    brand VARCHAR(100),
    category_id UUID REFERENCES product_categories(id),
    price DECIMAL(10,2) NOT NULL,
    compare_price DECIMAL(10,2),
    cost_price DECIMAL(10,2),
    description TEXT,
    specification JSONB,
    technical_details JSONB,
    product_dimensions JSONB,
    images TEXT[],
    product_url VARCHAR(500),
    stock_quantity INTEGER DEFAULT 0,
    in_stock BOOLEAN DEFAULT TRUE,
    track_inventory BOOLEAN DEFAULT TRUE,
    is_active BOOLEAN DEFAULT TRUE,
    is_amazon_seller BOOLEAN DEFAULT FALSE,
    is_embedding_generated BOOLEAN DEFAULT FALSE,
    embedding vector(1536),
    custom_fields JSONB DEFAULT '{}'::jsonb,
    meta_title VARCHAR(200),
    meta_description TEXT,
    tags JSONB DEFAULT '[]'::jsonb,
    created_by UUID,
    updated_by UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Product config table (depends on products)
CREATE TABLE IF NOT EXISTS product_config (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID UNIQUE REFERENCES products(id) ON DELETE CASCADE,
    show_in_search BOOLEAN DEFAULT TRUE,
    show_in_recommendations BOOLEAN DEFAULT TRUE,
    reranking_priority INTEGER DEFAULT 0,
    is_sponsored BOOLEAN DEFAULT FALSE,
    sponsored_priority INTEGER DEFAULT 0,
    featured BOOLEAN DEFAULT FALSE,
    promotion_text VARCHAR(255),
    boost_factor REAL DEFAULT 1.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Wishlist items association table
CREATE TABLE IF NOT EXISTS wishlist_items (
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    product_id UUID REFERENCES products(id) ON DELETE CASCADE,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (user_id, product_id)
);

-- Carts table (depends on users)
CREATE TABLE IF NOT EXISTS carts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Cart items table (depends on carts and products)
CREATE TABLE IF NOT EXISTS cart_item (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cart_id UUID NOT NULL REFERENCES carts(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    quantity INTEGER DEFAULT 1 NOT NULL,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(cart_id, product_id)
);

-- Legacy cart items association table (for backward compatibility)
CREATE TABLE IF NOT EXISTS cart_items (
    cart_id UUID REFERENCES carts(id) ON DELETE CASCADE,
    product_id UUID REFERENCES products(id) ON DELETE CASCADE,
    quantity INTEGER DEFAULT 1,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (cart_id, product_id)
);

-- Orders table (depends on users)
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id),
    order_number VARCHAR(50) UNIQUE NOT NULL,
    subtotal DECIMAL(10,2) NOT NULL,
    tax_amount DECIMAL(10,2) DEFAULT 0,
    shipping_amount DECIMAL(10,2) DEFAULT 0,
    discount_amount DECIMAL(10,2) DEFAULT 0,
    total_amount DECIMAL(10,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    payment_status VARCHAR(20) DEFAULT 'pending',
    billing_address JSONB,
    shipping_address JSONB,
    payment_method VARCHAR(50) DEFAULT 'cash_on_delivery',
    payment_reference VARCHAR(100),
    recommendation_source VARCHAR(50),
    recommendation_session_id VARCHAR(100),
    order_notes TEXT,
    admin_notes TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- Order items table (depends on orders and products)
CREATE TABLE IF NOT EXISTS order_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID REFERENCES orders(id) ON DELETE CASCADE,
    product_id UUID REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    total_price DECIMAL(10,2) NOT NULL
);

-- Search analytics table (depends on users and products)
CREATE TABLE IF NOT EXISTS search_analytics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    session_id VARCHAR(255),
    query TEXT NOT NULL,
    search_type VARCHAR(255),
    results_count INTEGER,
    clicked_product_id UUID REFERENCES products(id),
    click_position INTEGER,
    response_time_ms INTEGER,
    filters_applied JSONB,
    sort_option VARCHAR(50),
    user_agent VARCHAR(500),
    ip_address VARCHAR(45),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- User behavior table (depends on users, products, product_categories)
CREATE TABLE IF NOT EXISTS user_behavior (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    user_id UUID REFERENCES users(id),
    session_id VARCHAR(100),
    event_type VARCHAR(50) NOT NULL,
    product_id UUID REFERENCES products(id),
    category_id UUID REFERENCES product_categories(id),
    page_url VARCHAR(500),
    referrer VARCHAR(500),
    device_type VARCHAR(20),
    event_data JSONB
);

-- Audit logs table (depends on users)
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(100),
    old_values JSONB,
    new_values JSONB,
    details JSONB,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    endpoint VARCHAR(200),
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- Recommendation results table (depends on users and products)
CREATE TABLE IF NOT EXISTS recommendation_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    user_id UUID REFERENCES users(id),
    product_id UUID REFERENCES products(id),
    session_id VARCHAR(100),
    algorithm VARCHAR(50) NOT NULL,
    score NUMERIC(5,4) NOT NULL,
    rank INTEGER NOT NULL,
    recommendation_type VARCHAR(50),
    context_data JSONB,
    was_clicked BOOLEAN DEFAULT FALSE,
    was_purchased BOOLEAN DEFAULT FALSE,
    click_timestamp TIMESTAMP WITHOUT TIME ZONE
);

-- ML model configs table (depends on users)
CREATE TABLE IF NOT EXISTS ml_model_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE,
    model_type VARCHAR(100) NOT NULL,
    description TEXT,
    parameters JSONB NOT NULL,
    is_active BOOLEAN DEFAULT FALSE,
    is_default BOOLEAN DEFAULT FALSE,
    accuracy_score DECIMAL(5,4),
    precision_score DECIMAL(5,4),
    recall_score DECIMAL(5,4),
    last_trained TIMESTAMP WITHOUT TIME ZONE,
    training_data_version VARCHAR(500),
    model_version VARCHAR(500),
    created_by UUID REFERENCES users(id),
    updated_by UUID REFERENCES users(id),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- Model training history table (depends on ml_model_configs)
CREATE TABLE IF NOT EXISTS model_training_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_config_id UUID REFERENCES ml_model_configs(id),
    training_started TIMESTAMP WITHOUT TIME ZONE,
    training_completed TIMESTAMP WITHOUT TIME ZONE,
    status VARCHAR(50),
    parameters JSONB,
    metrics JSONB,
    training_data_info JSONB,
    error_message TEXT,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- Ad banners table (depends on users and products)
CREATE TABLE IF NOT EXISTS ad_banners (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    target_segment VARCHAR(100) NOT NULL,
    product_id UUID REFERENCES products(id),
    deal_type VARCHAR(50),
    deal_data TEXT,
    image_url VARCHAR(500),
    banner_text TEXT,
    call_to_action VARCHAR(100),
    start_time TIMESTAMP WITHOUT TIME ZONE,
    end_time TIMESTAMP WITHOUT TIME ZONE,
    status VARCHAR(20),
    click_count INTEGER DEFAULT 0,
    impression_count INTEGER DEFAULT 0,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- Promotional banners table (depends on users)
CREATE TABLE IF NOT EXISTS promotional_banners (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    target_segment VARCHAR(100) NOT NULL,
    product_id UUID,
    deal_type VARCHAR(50),
    deal_data TEXT,
    image_url VARCHAR(500),
    banner_text TEXT,
    call_to_action VARCHAR(100),
    start_time TIMESTAMP WITHOUT TIME ZONE,
    end_time TIMESTAMP WITHOUT TIME ZONE,
    status VARCHAR(20),
    click_count INTEGER DEFAULT 0,
    impression_count INTEGER DEFAULT 0,
    ai_generated BOOLEAN DEFAULT FALSE,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- Notifications table (depends on users)
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    type VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    data JSONB,
    is_read BOOLEAN DEFAULT FALSE,
    is_sent BOOLEAN DEFAULT FALSE,
    scheduled_for TIMESTAMP WITH TIME ZONE,
    sent_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Currencies table (no dependencies)
CREATE TABLE IF NOT EXISTS currencies (
    id INTEGER PRIMARY KEY,
    code VARCHAR(3) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    exchange_rate DECIMAL(10,6) DEFAULT 1.0,
    is_base BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ===========================================
-- INDEXES
-- ===========================================

-- Users indexes
CREATE INDEX IF NOT EXISTS ix_users_username ON users(username);
CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);

-- Products indexes
CREATE INDEX IF NOT EXISTS ix_products_name ON products(name);
CREATE INDEX IF NOT EXISTS ix_products_code ON products(code);
CREATE INDEX IF NOT EXISTS ix_products_brand ON products(brand);
CREATE INDEX IF NOT EXISTS ix_products_category_id ON products(category_id);
CREATE INDEX IF NOT EXISTS ix_products_price ON products(price);
CREATE INDEX IF NOT EXISTS ix_products_is_active ON products(is_active);
CREATE INDEX IF NOT EXISTS ix_products_brand_category ON products(brand, category_id);
CREATE INDEX IF NOT EXISTS ix_products_price_active ON products(price, is_active);

-- Vector index for embeddings (IVFFlat with cosine distance)
CREATE INDEX IF NOT EXISTS ix_products_embedding_cosine ON products USING ivfflat (embedding vector_cosine_ops);

-- Product categories indexes
CREATE INDEX IF NOT EXISTS ix_product_categories_name ON product_categories(name);
CREATE INDEX IF NOT EXISTS ix_product_categories_slug ON product_categories(slug);
CREATE INDEX IF NOT EXISTS ix_product_categories_parent_id ON product_categories(parent_id);

-- Orders indexes
CREATE INDEX IF NOT EXISTS ix_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS ix_orders_order_number ON orders(order_number);
CREATE INDEX IF NOT EXISTS ix_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS ix_orders_created_at ON orders(created_at);

-- Cart items indexes
CREATE INDEX IF NOT EXISTS ix_cart_item_cart_id ON cart_item(cart_id);
CREATE INDEX IF NOT EXISTS ix_cart_item_product_id ON cart_item(product_id);

-- Search analytics indexes
CREATE INDEX IF NOT EXISTS ix_search_analytics_user_id ON search_analytics(user_id);
CREATE INDEX IF NOT EXISTS ix_search_analytics_session_id ON search_analytics(session_id);
CREATE INDEX IF NOT EXISTS ix_search_analytics_created_at ON search_analytics(created_at);

-- User behavior indexes
CREATE INDEX IF NOT EXISTS ix_user_behavior_user_id ON user_behavior(user_id);
CREATE INDEX IF NOT EXISTS ix_user_behavior_session_id ON user_behavior(session_id);
CREATE INDEX IF NOT EXISTS ix_user_behavior_event_type ON user_behavior(event_type);
CREATE INDEX IF NOT EXISTS ix_user_behavior_created_at ON user_behavior(created_at);

-- Recommendation results indexes
CREATE INDEX IF NOT EXISTS ix_recommendation_results_user_id ON recommendation_results(user_id);
CREATE INDEX IF NOT EXISTS ix_recommendation_results_product_id ON recommendation_results(product_id);
CREATE INDEX IF NOT EXISTS ix_recommendation_results_session_id ON recommendation_results(session_id);
CREATE INDEX IF NOT EXISTS ix_recommendation_results_algorithm ON recommendation_results(algorithm);
CREATE INDEX IF NOT EXISTS ix_recommendation_results_created_at ON recommendation_results(created_at);

-- ML model configs indexes
CREATE INDEX IF NOT EXISTS ix_ml_model_configs_name ON ml_model_configs(name);
CREATE INDEX IF NOT EXISTS ix_ml_model_configs_model_type ON ml_model_configs(model_type);
CREATE INDEX IF NOT EXISTS ix_ml_model_configs_is_active ON ml_model_configs(is_active);

-- Audit logs indexes
CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS ix_audit_logs_resource_type ON audit_logs(resource_type);
CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs(created_at);

-- ===========================================
-- DEFAULT DATA
-- ===========================================

-- -- Insert default currency (USD)
-- INSERT INTO currencies (id, code, name, symbol, is_base, is_active)
-- VALUES (1, 'USD', 'US Dollar', '$', TRUE, TRUE)
-- ON CONFLICT (id) DO NOTHING;

-- Insert default admin role
-- INSERT INTO roles (id, name, description, permissions, is_active)
-- VALUES (
--     '00000000-0000-0000-0000-000000000001',
--     'admin',
--     'Administrator with full access',
--     '[
--         "users.view", "users.create", "users.update", "users.delete",
--         "products.view", "products.create", "products.update", "products.delete",
--         "products.manage_inventory", "products.manage_categories",
--         "orders.view", "orders.view_all", "orders.update", "orders.delete",
--         "orders.manage_status", "orders.view_reports",
--         "analytics.view", "analytics.view_detailed", "analytics.export",
--         "system.admin", "system.settings", "system.logs",
--         "system.recommendations", "system.ml_models"
--     ]'::jsonb,
--     TRUE
-- )
-- ON CONFLICT (name) DO NOTHING;

-- -- Insert default customer role
-- INSERT INTO roles (id, name, description, permissions, is_active)
-- VALUES (
--     '00000000-0000-0000-0000-000000000002',
--     'customer',
--     'Regular customer',
--     '["products.view", "cart.view", "cart.manage", "orders.view"]'::jsonb,
--     TRUE
-- )
-- ON CONFLICT (name) DO NOTHING;

-- -- Insert default manager role
-- INSERT INTO roles (id, name, description, permissions, is_active)
-- VALUES (
--     '00000000-0000-0000-0000-000000000003',
--     'manager',
--     'Store manager',
--     '[
--         "products.view", "products.update", "products.manage_inventory",
--         "orders.view", "orders.view_all", "orders.update",
--         "analytics.view", "users.view"
--     ]'::jsonb,
--     TRUE
-- )
-- ON CONFLICT (name) DO NOTHING;

-- -- Insert default admin user
-- -- INSERT INTO users (
-- --     id, username, email, hashed_password, first_name, last_name,
-- --     is_active, is_verified, is_superuser
-- -- )
-- -- VALUES (
-- --     '00000000-0000-0000-0000-000000000001',
-- --     'admin',
-- --     'admin@ecommerce.com',
-- --     '$2b$12$Iy5njesJ9WYwWctcsHbXtOhYys4OH8ybcHNFi3abWQqQCoQZMW1hS',
-- --     'Admin',
-- --     'User',
-- --     TRUE,
-- --     TRUE,
-- --     TRUE
-- -- )
-- -- ON CONFLICT (email) DO NOTHING;

-- -- Assign admin role to admin user
-- -- INSERT INTO user_roles (user_id, role_id)
-- -- SELECT '00000000-0000-0000-0000-000000000001', id
-- -- FROM roles WHERE name = 'admin'
-- -- ON CONFLICT DO NOTHING;

-- -- Insert sample product categories
-- -- INSERT INTO product_categories (id, name, slug, description, is_active, sort_order)
-- -- VALUES
-- --     ('11111111-1111-1111-1111-111111111111', 'Electronics', 'electronics', 'Electronic devices and gadgets', TRUE, 1),
-- --     ('22222222-2222-2222-2222-222222222222', 'Toys & Games', 'toys-games', 'Educational toys and games', TRUE, 2),
-- --     ('33333333-3333-3333-3333-333333333333', 'Educational', 'educational', 'Educational materials and kits', TRUE, 3),
-- --     ('44444444-4444-4444-4444-444444444444', 'Tools', 'tools', 'Tools and hardware', TRUE, 4),
-- --     ('55555555-5555-5555-5555-555555555555', 'Home & Garden', 'home-garden', 'Home and garden products', TRUE, 5)
-- -- ON CONFLICT (slug) DO NOTHING;
