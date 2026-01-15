import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.api import api_router
from app.core.config import get_settings
from app.database import SessionLocal, engine
from app.middleware import (
    ErrorTrackingMiddleware,
    PerformanceMonitoringMiddleware,
    RedirectCORSMiddleware,
    # SecurityHeadersMiddleware,
    setup_cors,
)
from app.models import Base
from app.services.ml_engine_service import MLEngineService
from app.services.system_health_service import SystemMonitor
from app.utils.logging_config import setup_logging

settings = get_settings()

os.makedirs("generated_banners", exist_ok=True)

setup_logging()
logger = logging.getLogger(__name__)
system_monitor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global system_monitor

    logger.info("Launch:  Starting up ecommerce backend ...")

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # init_db(db)  # Commented out - database is restored from dump
        await _init_default_admin_settings(db)
        await _init_default_segments(db)
        await _init_sponsored_products(db)
        await _map_users_to_segments(db)

        # Only train models if they don't already exist
        await _init_ml_models(db)
    finally:
        db.close()

    os.makedirs(settings.UPLOAD_FOLDER, exist_ok=True)

    try:
        system_monitor = SystemMonitor(SessionLocal)

        import asyncio

        asyncio.create_task(system_monitor.start_monitoring())
        logger.info("Success:  System monitoring started")
    except Exception as e:
        logger.error(f"Error:  Failed to start system monitoring: {e}")

    logger.info("Success:   startup complete")

    yield

    logger.info("Processing  Shutting down...")
    if system_monitor:
        await system_monitor.stop_monitoring()
    logger.info("Success:  Shutdown complete")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION + " - Admin Panel",
    lifespan=lifespan,
)


# ============================================================================
# Middleware Configuration
# ============================================================================
# Order matters! Middleware is executed top-to-bottom for requests
# and bottom-to-top for responses

# 1. Redirect CORS - Add CORS headers to redirects (must be before CORS middleware)
app.add_middleware(RedirectCORSMiddleware)

# 2. CORS - Must be early to handle preflight requests
setup_cors(app)

# 3. Security Headers - Add security headers to all responses
# app.add_middleware(SecurityHeadersMiddleware)

# 4. Error Tracking - Track and log errors
app.add_middleware(ErrorTrackingMiddleware)

# 5. Performance Monitoring - Track response times and metrics
app.add_middleware(PerformanceMonitoringMiddleware)

# Optional middleware (uncomment to enable):
# from app.middleware import RateLimitingMiddleware, AdminActivityTrackingMiddleware
# app.add_middleware(RateLimitingMiddleware, requests_per_minute=60)
# app.add_middleware(AdminActivityTrackingMiddleware)


# ============================================================================
# Static Files
# ============================================================================
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount(
    "/generated_banners",
    StaticFiles(directory="generated_banners"),
    name="generated-banners",
)


@app.exception_handler(HTTPException)
async def enhanced_http_exception_handler(request: Request, exc: HTTPException):
    logger.warning(
        f"Warning:  HTTP Exception {exc.status_code} on {request.method} {request.url.path}: {exc.detail}"
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error_code": getattr(exc, "error_code", None),
            "timestamp": time.time(),
            "path": request.url.path,
        },
    )


@app.get("/health")
async def health_check():
    """health check with system status"""
    try:
        db = SessionLocal()
        try:
            from app.services.system_health_service import SystemHealthService

            health_service = SystemHealthService(db)

            db_health = await health_service.check_database_connectivity()

            health_status = {
                "status": "healthy",
                "version": settings.VERSION,
                "timestamp": time.time(),
                "database": db_health,
                "system_monitor": "active"
                if system_monitor and system_monitor.is_running
                else "inactive",
                "features": {
                    "admin_panel": True,
                    "performance_monitoring": True,
                    "real_time_dashboard": True,
                },
            }

            if db_health.get("status") != "healthy":
                health_status["status"] = "degraded"

            return health_status

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "version": settings.VERSION,
            "timestamp": time.time(),
            "error": str(e),
        }


@app.get("/admin-info")
async def get_admin_panel_info():
    """Get information about admin panel capabilities"""
    return {
        "admin_panel": {
            "version": "2.0.0",
            "features": [
                "Dashboard",
                "Real-time Metrics",
                "System Health Monitoring",
                "Performance Analytics",
                "Admin Activity Tracking",
                "Feature Flags",
                "System Configuration",
            ],
            "endpoints": {
                "dashboard": "/api/v1/admin/dashboard",
                "health": "/api/v1/admin/dashboard/system-health",
                "real_time": "/api/v1/admin/dashboard/real-time-stats",
                "performance": "/api/v1/admin/dashboard/performance-metrics",
            },
        },
        "monitoring": {
            "performance_tracking": True,
            "error_tracking": True,
            "security_headers": True,
            "rate_limiting": not settings.DEBUG,
            "admin_activity_tracking": True,
        },
    }


app.include_router(api_router, prefix=settings.API_V1_STR)


async def _init_ml_models(db):
    """Initialize and train ML models only if they don't already exist"""
    try:
        from app.models.ml_models import MLModelConfig

        # Check if any active models exist
        existing_models = (
            db.query(MLModelConfig).filter(MLModelConfig.is_active).count()
        )

        if existing_models > 0:
            logger.info(f"Found {existing_models} active ML models, skipping training")
            return

        logger.info("No active ML models found, starting initial training...")
        ml_engine = MLEngineService(db)
        ml_engine.train_all_models()
        logger.info("Success:  ML models trained successfully")

    except Exception as e:
        logger.error(f"Error:  Failed to initialize ML models: {e}")
        # Don't rollback here as we're not making direct DB changes


async def _init_default_segments(db):
    """Initialize default user segments if they don't exist"""
    try:
        from app.models.ml_models import UserSegment

        # Quick check if segments already exist
        existing_count = db.query(UserSegment).count()
        if existing_count > 0:
            logger.info(
                f"Found {existing_count} existing segments, skipping default segment initialization"
            )
            return

        default_segments = [
            {
                "name": "High-Value Customers",
                "description": "Customers with high lifetime value and frequent purchases",
                "segment_type": "rfm",
                "criteria": {
                    "rules": [
                        {"field": "total_spent", "operator": ">=", "value": 1000},
                        {"field": "order_count", "operator": ">=", "value": 5},
                    ]
                },
                "is_active": True,
                "auto_update": True,
                "update_frequency": "daily",
            },
            {
                "name": "Frequent Buyers",
                "description": "Customers who purchase regularly",
                "segment_type": "behavioral",
                "criteria": {
                    "rules": [
                        {"field": "order_count", "operator": ">=", "value": 3},
                        {
                            "field": "days_since_last_order",
                            "operator": "<=",
                            "value": 30,
                        },
                    ]
                },
                "is_active": True,
                "auto_update": True,
                "update_frequency": "daily",
            },
            {
                "name": "New Customers",
                "description": "Recently registered users with few or no orders",
                "segment_type": "behavioral",
                "criteria": {
                    "rules": [
                        {
                            "field": "days_since_registration",
                            "operator": "<=",
                            "value": 30,
                        },
                        {"field": "order_count", "operator": "<=", "value": 1},
                    ]
                },
                "is_active": True,
                "auto_update": True,
                "update_frequency": "daily",
            },
            {
                "name": "At-Risk Customers",
                "description": "Previously active customers who haven't ordered recently",
                "segment_type": "rfm",
                "criteria": {
                    "rules": [
                        {
                            "field": "days_since_last_order",
                            "operator": ">=",
                            "value": 90,
                        },
                        {"field": "order_count", "operator": ">=", "value": 2},
                    ]
                },
                "is_active": True,
                "auto_update": True,
                "update_frequency": "weekly",
            },
            {
                "name": "VIP Shoppers",
                "description": "Top spending customers in premium categories",
                "segment_type": "custom",
                "criteria": {
                    "rules": [
                        {"field": "total_spent", "operator": ">=", "value": 5000},
                        {
                            "field": "average_order_value",
                            "operator": ">=",
                            "value": 500,
                        },
                    ]
                },
                "is_active": True,
                "auto_update": True,
                "update_frequency": "weekly",
            },
            {
                "name": "Budget Conscious",
                "description": "Customers who prefer lower-priced items",
                "segment_type": "behavioral",
                "criteria": {
                    "rules": [
                        {"field": "average_order_value", "operator": "<", "value": 100},
                        {"field": "order_count", "operator": ">=", "value": 2},
                    ]
                },
                "is_active": True,
                "auto_update": True,
                "update_frequency": "weekly",
            },
        ]

        # Bulk create all segments since we already checked none exist
        for segment_data in default_segments:
            segment = UserSegment(**segment_data)
            db.add(segment)

        db.commit()
        logger.info(
            f"Success:  {len(default_segments)} default user segments initialized"
        )

    except Exception as e:
        logger.error(f"Error:  Failed to initialize default segments: {e}")
        db.rollback()


async def _init_sponsored_products(db):
    """Initialize sponsored products with priority if not already configured"""
    try:
        from app.models.product import Product, ProductConfig

        # Check if any sponsored products already exist
        existing_sponsored = (
            db.query(ProductConfig).filter(ProductConfig.is_sponsored).count()
        )
        if existing_sponsored > 0:
            logger.info(
                f"Found {existing_sponsored} sponsored products, skipping initialization"
            )
            return

        # Get top 10 products by some criteria (e.g., most popular categories)
        products = (
            db.query(Product)
            .filter(Product.is_active)
            .filter(Product.in_stock)
            .limit(10)
            .all()
        )

        if not products:
            logger.info("No products available for sponsored product initialization")
            return

        sponsored_count = 0
        for idx, product in enumerate(products):
            # Check if product already has a config
            config = (
                db.query(ProductConfig)
                .filter(ProductConfig.product_id == product.id)
                .first()
            )

            if config:
                # Update existing config to be sponsored
                config.is_sponsored = True
                config.sponsored_priority = (
                    10 - idx
                )  # Higher priority for earlier products
                config.boost_factor = 1.5
                sponsored_count += 1
            else:
                # Create new config with sponsored settings
                config = ProductConfig(
                    product_id=product.id,
                    show_in_search=True,
                    show_in_recommendations=True,
                    reranking_priority=5,
                    is_sponsored=True,
                    sponsored_priority=10 - idx,
                    featured=True,
                    boost_factor=1.5,
                )
                db.add(config)
                sponsored_count += 1

        db.commit()
        logger.info(f"Success:  {sponsored_count} products configured as sponsored")

    except Exception as e:
        logger.error(f"Error:  Failed to initialize sponsored products: {e}")
        db.rollback()


async def _map_users_to_segments(db):
    """Map all users to appropriate segments based on segment rules"""
    try:
        from app.models.ml_models import UserSegment
        from app.services.segmentation.segment_rule_engine import SegmentRuleEngine

        # Get all active segments
        segments = db.query(UserSegment).filter(UserSegment.is_active).all()

        if not segments:
            logger.info("No active segments found, skipping user mapping")
            return

        rule_engine = SegmentRuleEngine(db)
        total_mappings = 0

        for segment in segments:
            try:
                logger.info(f"Applying rules for segment: {segment.name}")
                rule_engine.apply_segment_rules(segment)
                total_mappings += segment.actual_size or 0
            except Exception as e:
                logger.error(f"Failed to apply rules for segment {segment.name}: {e}")
                continue

        db.commit()
        logger.info(
            f"Success: Mapped users to {len(segments)} segments (total mappings: {total_mappings})"
        )

    except Exception as e:
        logger.error(f"Error: Failed to map users to segments: {e}")
        db.rollback()


async def _init_default_admin_settings(db):
    """Initialize default admin settings and feature flags"""
    try:
        from app.models.admin import FeatureFlag, SystemSetting

        # Check if settings already exist
        existing_settings = db.query(SystemSetting).count()
        existing_flags = db.query(FeatureFlag).count()

        if existing_settings > 0 and existing_flags > 0:
            logger.info(
                "Admin settings and feature flags already exist, skipping initialization"
            )
            return

        default_settings = [
            {
                "category": "general",
                "key": "site_name",
                "value": "Ecommerce Platform",
                "description": "Site display name",
            },
            {
                "category": "general",
                "key": "maintenance_mode",
                "value": "false",
                "data_type": "boolean",
                "description": "Enable maintenance mode",
            },
            {
                "category": "performance",
                "key": "cache_ttl_minutes",
                "value": "60",
                "data_type": "integer",
                "description": "Default cache TTL in minutes",
            },
            {
                "category": "admin",
                "key": "max_dashboard_widgets",
                "value": "12",
                "data_type": "integer",
                "description": "Maximum dashboard widgets per user",
            },
        ]

        for setting_data in default_settings:
            existing = (
                db.query(SystemSetting)
                .filter(
                    SystemSetting.category == setting_data["category"],
                    SystemSetting.key == setting_data["key"],
                )
                .first()
            )

            if not existing:
                setting = SystemSetting(**setting_data)
                db.add(setting)

        default_flags = [
            {
                "name": "enhanced_dashboard",
                "description": "Enable admin dashboard",
                "is_enabled": True,
                "rollout_percentage": 100,
            },
            {
                "name": "real_time_monitoring",
                "description": "Enable real-time system monitoring",
                "is_enabled": True,
                "rollout_percentage": 100,
            },
            {
                "name": "advanced_analytics",
                "description": "Enable advanced analytics features",
                "is_enabled": False,
                "rollout_percentage": 0,
            },
        ]

        for flag_data in default_flags:
            existing = (
                db.query(FeatureFlag)
                .filter(FeatureFlag.name == flag_data["name"])
                .first()
            )

            if not existing:
                flag = FeatureFlag(**flag_data)
                db.add(flag)

        db.commit()
        logger.info("Success:  Default admin settings and feature flags initialized")

    except Exception as e:
        logger.error(f"Error:  Failed to initialize default admin settings: {e}")
        db.rollback()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )
