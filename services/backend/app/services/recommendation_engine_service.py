"""
Recommendation Engine Service - Compatibility Wrapper.
Provides unified interface to modular recommendation services.
"""

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.ml.ml_training_service import MLTrainingService
from app.services.recommendations import ModelConfigManager, PerformanceTracker

settings = get_settings()


class RecommendationEngineService:
    """Unified recommendation engine service using modular components."""

    def __init__(self, db: Session):
        self.db = db
        self.config_manager = ModelConfigManager(db)
        self.performance_tracker = PerformanceTracker(db)
        self.training_service = MLTrainingService(
            db, models_dir=settings.MODEL_STORAGE_PATH
        )

    # Model config management
    def get_model_configs(self, active_only=False):
        return self.config_manager.get_model_configs(active_only)

    def create_model_config(self, config_data, user_id):
        return self.config_manager.create_model_config(config_data, user_id)

    def update_model_config(self, config_id, config_data, user_id):
        return self.config_manager.update_model_config(config_id, config_data, user_id)

    def activate_model_config(self, config_id, user_id):
        return self.config_manager.activate_model_config(config_id, user_id)

    def deactivate_model_config(self, config_id, user_id):
        return self.config_manager.deactivate_model_config(config_id, user_id)

    def delete_model_config(self, config_id):
        return self.config_manager.delete_model_config(config_id)

    # Performance tracking
    def get_recommendation_performance(self, days=30):
        return self.performance_tracker.get_recommendation_performance(days)

    def get_conversion_analytics(self, days=30):
        return self.performance_tracker.get_conversion_analytics(days)

    def log_recommendation_display(self, user_id, recommendation_ids, context):
        return self.performance_tracker.log_recommendation_display(
            user_id, recommendation_ids, context
        )

    def log_recommendation_interaction(
        self, user_id, recommendation_id, interaction_type, product_id=None
    ):
        return self.performance_tracker.log_recommendation_interaction(
            user_id, recommendation_id, interaction_type, product_id
        )

    # Model training methods
    def trigger_model_training(self, model_type, custom_parameters=None):
        """
        Trigger training for a specific model type.

        Args:
            model_type: Type of model to train (als, content, kmeans, lightgbm, fbt)
            custom_parameters: Optional dictionary of hyperparameters to override defaults

        Returns:
            Dictionary with success status and training_id
        """
        import logging

        logger = logging.getLogger(__name__)

        try:
            # Use default parameters if none provided
            parameters = custom_parameters or {}

            # Set default parameters based on model type
            if model_type == "als" and not parameters:
                parameters = {
                    "factors": settings.CF_FACTORS,
                    "regularization": settings.CF_REGULARIZATION,
                    "iterations": settings.CF_ITERATIONS,
                }
            elif model_type == "kmeans" and not parameters:
                parameters = {
                    "n_clusters": settings.BEHAVIORAL_CLUSTERS,
                }
            elif model_type == "fbt" and not parameters:
                parameters = {
                    "min_support": settings.FBT_MIN_SUPPORT,
                    "min_confidence": settings.FBT_MIN_CONFIDENCE,
                }

            # Generate model name with timestamp
            from datetime import datetime

            model_name = (
                f"{model_type}_training_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            )

            # Start async training
            result = self.training_service.start_training_async(
                model_type=model_type, model_name=model_name, parameters=parameters
            )

            if result.get("success"):
                logger.info(
                    f"Training triggered for {model_type}, training_id: {result['training_id']}"
                )
                return {
                    "success": True,
                    "training_id": result["training_id"],
                    "model_type": model_type,
                    "model_name": model_name,
                    "parameters": parameters,
                    "message": f"Training started for {model_type}",
                }
            else:
                logger.error(
                    f"Failed to trigger training for {model_type}: {result.get('error')}"
                )
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                }

        except Exception as e:
            logger.error(f"Error triggering model training: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
            }

    def get_training_history(self, model_type=None, limit=50):
        """
        Get training history from database.

        Args:
            model_type: Optional filter by model type (als, content, kmeans, lightgbm, fbt)
            limit: Maximum number of records to return

        Returns:
            Dictionary with training history records
        """
        import logging

        from sqlalchemy import desc

        from app.models import MLModelConfig, ModelTrainingHistory

        logger = logging.getLogger(__name__)

        try:
            # Build query
            query = self.db.query(ModelTrainingHistory)

            # Filter by model type if provided
            if model_type:
                # Join with MLModelConfig to filter by model type
                query = query.join(MLModelConfig).filter(
                    MLModelConfig.model_type == model_type
                )

            # Order by most recent first and limit
            training_records = (
                query.order_by(desc(ModelTrainingHistory.started_at)).limit(limit).all()
            )

            # Serialize results
            history = []
            for record in training_records:
                history_item = {
                    "id": str(record.id),
                    "model_config_id": str(record.model_config_id)
                    if record.model_config_id
                    else None,
                    "training_status": record.training_status,
                    "training_metrics": record.training_metrics or {},
                    "training_parameters": record.training_parameters or {},
                    "error_message": record.error_message,
                    "training_data_stats": record.training_data_stats or {},
                    "model_performance": record.model_performance or {},
                    "training_duration_seconds": record.training_duration_seconds,
                    "started_at": record.started_at.isoformat()
                    if record.started_at
                    else None,
                    "completed_at": record.completed_at.isoformat()
                    if record.completed_at
                    else None,
                    "initiated_by": str(record.initiated_by)
                    if record.initiated_by
                    else None,
                }

                # Add model config details if available
                if record.model_config:
                    history_item["model_name"] = record.model_config.name
                    history_item["model_type"] = record.model_config.model_type

                history.append(history_item)

            return {
                "success": True,
                "total_records": len(history),
                "limit": limit,
                "filter": {"model_type": model_type} if model_type else None,
                "history": history,
            }

        except Exception as e:
            logger.error(f"Error getting training history: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
            }
