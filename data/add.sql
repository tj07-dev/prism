-- Additional database tables for ML and advanced features
-- This script should be run after init.sql

-- ===========================================
-- ML AND ADVANCED FEATURE TABLES
-- ===========================================

-- Recommendation results table (depends on users and products)
CREATE TABLE IF NOT EXISTS recommendation_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    user_id UUID REFERENCES users(id),
    product_id UUID REFERENCES products(id),
    session_id VARCHAR(100),
    algorithm VARCHAR(50) NOT NULL,
    score DECIMAL(5,4) NOT NULL,
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

-- Model training history table (depends on ml_model_configs and users)
CREATE TABLE IF NOT EXISTS model_training_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_config_id UUID REFERENCES ml_model_configs(id),
    training_status VARCHAR(50) DEFAULT 'queued',
    training_metrics JSONB,
    training_parameters JSONB,
    error_message TEXT,
    training_data_stats JSONB,
    model_performance JSONB,
    training_duration_seconds INTEGER,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    initiated_by UUID REFERENCES users(id)
);

-- Model versions table (depends on ml_model_configs, model_training_history, users)
CREATE TABLE IF NOT EXISTS model_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_config_id UUID REFERENCES ml_model_configs(id),
    training_history_id UUID REFERENCES model_training_history(id),
    version_number VARCHAR(50) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_size_bytes INTEGER,
    is_active BOOLEAN DEFAULT FALSE,
    model_metadata JSONB,
    performance_metrics JSONB,
    config_snapshot JSONB,
    training_data_hash VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID REFERENCES users(id)
);

-- Recommendation metrics table (depends on users)
CREATE TABLE IF NOT EXISTS recommendation_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    session_id VARCHAR(100),
    recommendation_type VARCHAR(50),
    recommended_products JSONB,
    viewed_products JSONB,
    clicked_products JSONB,
    added_to_cart JSONB,
    purchased_products JSONB,
    conversion_rate DECIMAL(5,4),
    click_through_rate DECIMAL(5,4),
    revenue_generated DECIMAL(10,2) DEFAULT 0.0,
    recommendation_context JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User segments table (no dependencies)
CREATE TABLE IF NOT EXISTS user_segments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    segment_type VARCHAR(50),
    criteria JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    auto_update BOOLEAN DEFAULT TRUE,
    update_frequency VARCHAR(20),
    member_count INTEGER DEFAULT 0,
    last_updated TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- User segment memberships table (depends on users and user_segments)
CREATE TABLE IF NOT EXISTS user_segment_memberships (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    segment_id UUID REFERENCES user_segments(id),
    membership_score DECIMAL(5,4),
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_evaluated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    assignment_reason VARCHAR(200)
);

-- Add unique constraint for user-segment combinations
ALTER TABLE user_segment_memberships ADD CONSTRAINT IF NOT EXISTS user_segment_memberships_unique
    UNIQUE (user_id, segment_id);

-- User analytics daily table (depends on users)
CREATE TABLE IF NOT EXISTS user_analytics_daily (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    date DATE NOT NULL,
    page_views INTEGER DEFAULT 0,
    search_queries INTEGER DEFAULT 0,
    products_viewed INTEGER DEFAULT 0,
    unique_products_viewed INTEGER DEFAULT 0,
    cart_additions INTEGER DEFAULT 0,
    cart_removals INTEGER DEFAULT 0,
    wishlist_additions INTEGER DEFAULT 0,
    session_duration_seconds INTEGER DEFAULT 0,
    bounce_rate DECIMAL(5,4),
    conversion_events INTEGER DEFAULT 0,
    revenue_generated DECIMAL(10,2) DEFAULT 0.0,
    device_type VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User journey events table (depends on users)
CREATE TABLE IF NOT EXISTS user_journey_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    session_id VARCHAR(100),
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    page_url VARCHAR(500),
    referrer VARCHAR(500),
    user_agent VARCHAR(1000),
    ip_address VARCHAR(45),
    device_info JSONB,
    geolocation JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Recommendation conversions table (depends on users)
CREATE TABLE IF NOT EXISTS recommendation_conversions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    session_id VARCHAR(100),
    recommendation_request_id VARCHAR(100),
    recommended_products JSONB,
    interactions JSONB,
    final_conversion JSONB,
    conversion_value DECIMAL(10,2) DEFAULT 0.0,
    time_to_conversion_minutes INTEGER,
    conversion_funnel JSONB,
    a_b_test_variant VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- System alerts table (depends on users)
CREATE TABLE IF NOT EXISTS system_alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) DEFAULT 'medium',
    title VARCHAR(200) NOT NULL,
    description TEXT,
    alert_data JSONB,
    source_component VARCHAR(100),
    is_acknowledged BOOLEAN DEFAULT FALSE,
    is_resolved BOOLEAN DEFAULT FALSE,
    acknowledged_by UUID REFERENCES users(id),
    resolved_by UUID REFERENCES users(id),
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Inventory forecasts table (depends on products)
CREATE TABLE IF NOT EXISTS inventory_forecasts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID REFERENCES products(id),
    forecast_period_days INTEGER DEFAULT 30,
    predicted_demand INTEGER,
    confidence_interval_lower INTEGER,
    confidence_interval_upper INTEGER,
    current_stock INTEGER,
    recommended_order_quantity INTEGER,
    stockout_probability DECIMAL(5,4),
    seasonal_factor DECIMAL(5,4),
    trend_factor DECIMAL(5,4),
    forecast_accuracy DECIMAL(5,4),
    model_used VARCHAR(50),
    forecast_date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ===========================================
-- INDEXES FOR NEW TABLES
-- ===========================================

-- Recommendation results indexes
CREATE INDEX IF NOT EXISTS ix_recommendation_results_user_id ON recommendation_results(user_id);
CREATE INDEX IF NOT EXISTS ix_recommendation_results_product_id ON recommendation_results(product_id);
CREATE INDEX IF NOT EXISTS ix_recommendation_results_session_id ON recommendation_results(session_id);
CREATE INDEX IF NOT EXISTS ix_recommendation_results_algorithm ON recommendation_results(algorithm);

-- ML model configs indexes
CREATE INDEX IF NOT EXISTS ix_ml_model_configs_name ON ml_model_configs(name);
CREATE INDEX IF NOT EXISTS ix_ml_model_configs_model_type ON ml_model_configs(model_type);
CREATE INDEX IF NOT EXISTS ix_ml_model_configs_is_active ON ml_model_configs(is_active);
CREATE INDEX IF NOT EXISTS ix_ml_model_configs_is_default ON ml_model_configs(is_default);

-- Model training history indexes
CREATE INDEX IF NOT EXISTS ix_model_training_history_model_config_id ON model_training_history(model_config_id);
CREATE INDEX IF NOT EXISTS ix_model_training_history_training_status ON model_training_history(training_status);
CREATE INDEX IF NOT EXISTS ix_model_training_history_started_at ON model_training_history(started_at);

-- Model versions indexes
CREATE INDEX IF NOT EXISTS ix_model_versions_model_config_id ON model_versions(model_config_id);
CREATE INDEX IF NOT EXISTS ix_model_versions_training_history_id ON model_versions(training_history_id);
CREATE INDEX IF NOT EXISTS ix_model_versions_is_active ON model_versions(is_active);

-- Recommendation metrics indexes
CREATE INDEX IF NOT EXISTS ix_recommendation_metrics_user_id ON recommendation_metrics(user_id);
CREATE INDEX IF NOT EXISTS ix_recommendation_metrics_session_id ON recommendation_metrics(session_id);
CREATE INDEX IF NOT EXISTS ix_recommendation_metrics_recommendation_type ON recommendation_metrics(recommendation_type);

-- User segments indexes
CREATE INDEX IF NOT EXISTS ix_user_segments_name ON user_segments(name);
CREATE INDEX IF NOT EXISTS ix_user_segments_is_active ON user_segments(is_active);

-- User segment memberships indexes
CREATE INDEX IF NOT EXISTS ix_user_segment_memberships_user_id ON user_segment_memberships(user_id);
CREATE INDEX IF NOT EXISTS ix_user_segment_memberships_segment_id ON user_segment_memberships(segment_id);
CREATE INDEX IF NOT EXISTS ix_user_segment_memberships_is_active ON user_segment_memberships(is_active);

-- User analytics daily indexes
CREATE INDEX IF NOT EXISTS ix_user_analytics_daily_user_id ON user_analytics_daily(user_id);
CREATE INDEX IF NOT EXISTS ix_user_analytics_daily_date ON user_analytics_daily(date);

-- User journey events indexes
CREATE INDEX IF NOT EXISTS ix_user_journey_events_user_id ON user_journey_events(user_id);
CREATE INDEX IF NOT EXISTS ix_user_journey_events_session_id ON user_journey_events(session_id);
CREATE INDEX IF NOT EXISTS ix_user_journey_events_event_type ON user_journey_events(event_type);
CREATE INDEX IF NOT EXISTS ix_user_journey_events_timestamp ON user_journey_events(timestamp);

-- Recommendation conversions indexes
CREATE INDEX IF NOT EXISTS ix_recommendation_conversions_user_id ON recommendation_conversions(user_id);
CREATE INDEX IF NOT EXISTS ix_recommendation_conversions_session_id ON recommendation_conversions(session_id);
CREATE INDEX IF NOT EXISTS ix_recommendation_conversions_request_id ON recommendation_conversions(recommendation_request_id);

-- System alerts indexes
CREATE INDEX IF NOT EXISTS ix_system_alerts_alert_type ON system_alerts(alert_type);
CREATE INDEX IF NOT EXISTS ix_system_alerts_severity ON system_alerts(severity);
CREATE INDEX IF NOT EXISTS ix_system_alerts_is_acknowledged ON system_alerts(is_acknowledged);
CREATE INDEX IF NOT EXISTS ix_system_alerts_is_resolved ON system_alerts(is_resolved);

-- Inventory forecasts indexes
CREATE INDEX IF NOT EXISTS ix_inventory_forecasts_product_id ON inventory_forecasts(product_id);
CREATE INDEX IF NOT EXISTS ix_inventory_forecasts_forecast_date ON inventory_forecasts(forecast_date);

-- ===========================================
-- DEFAULT USER SEGMENTS
-- ===========================================

-- Insert default user segments
INSERT INTO user_segments (id, name, description, segment_type, criteria, is_active, auto_update, update_frequency)
VALUES
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1', 'High-Value Customers', 'Customers with high lifetime value and frequent purchases', 'rfm',
     '{"rules": [{"field": "total_spent", "operator": ">=", "value": 1000}, {"field": "order_count", "operator": ">=", "value": 5}]}',
     TRUE, TRUE, 'daily'),
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2', 'Frequent Buyers', 'Customers who purchase regularly', 'behavioral',
     '{"rules": [{"field": "order_count", "operator": ">=", "value": 3}, {"field": "days_since_last_order", "operator": "<=", "value": 30}]}',
     TRUE, TRUE, 'daily'),
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa3', 'New Customers', 'Recently registered users with few or no orders', 'behavioral',
     '{"rules": [{"field": "days_since_registration", "operator": "<=", "value": 30}, {"field": "order_count", "operator": "<=", "value": 1}]}',
     TRUE, TRUE, 'daily'),
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa4', 'At-Risk Customers', 'Previously active customers who haven''t ordered recently', 'rfm',
     '{"rules": [{"field": "days_since_last_order", "operator": ">=", "value": 90}, {"field": "order_count", "operator": ">=", "value": 2}]}',
     TRUE, TRUE, 'weekly'),
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa5', 'VIP Shoppers', 'Top spending customers in premium categories', 'custom',
     '{"rules": [{"field": "total_spent", "operator": ">=", "value": 5000}, {"field": "average_order_value", "operator": ">=", "value": 500}]}',
     TRUE, TRUE, 'weekly'),
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa6', 'Budget Conscious', 'Customers who prefer lower-priced items', 'behavioral',
     '{"rules": [{"field": "average_order_value", "operator": "<", "value": 100}, {"field": "order_count", "operator": ">=", "value": 2}]}',
     TRUE, TRUE, 'weekly')
ON CONFLICT (name) DO NOTHING;