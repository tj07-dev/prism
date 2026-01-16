"""Unified interface over ML services for training and inference."""

import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.ml import (
    ALSModelService,
    ContentModelService,
    KMeansModelService,
    LightGBMModelService,
    MLModelManager,
    MLTrainingService,
)
from app.services.ml.hybrid_recommender_service import HybridRecommenderService


class MLEngineService:
    """Coordinated access to ML training and inference utilities."""

    def __init__(self, db: Session, models_dir: Optional[str] = None):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.db = db
        self.training_service = MLTrainingService(db, models_dir)

        # Reuse sub-services from the training service to keep model cache consistent
        self.model_manager: MLModelManager = self.training_service.model_manager
        self.als_service: ALSModelService = self.training_service.als_service
        self.lightgbm_service: LightGBMModelService = (
            self.training_service.lightgbm_service
        )
        self.kmeans_service: KMeansModelService = self.training_service.kmeans_service
        self.content_service: ContentModelService = (
            self.training_service.content_service
        )
        self.hybrid_service = HybridRecommenderService(db, models_dir)

    # ------------------------------------------------------------------
    # Model cache helpers
    # ------------------------------------------------------------------
    @property
    def active_models(self) -> Dict[str, Any]:
        return self.model_manager.active_models

    def refresh_models(self) -> Dict[str, Any]:
        return self.training_service.refresh_model_cache()

    def get_active_model(self, model_type: str) -> Optional[Dict[str, Any]]:
        return self.model_manager.get_active_model(model_type)

    # ------------------------------------------------------------------
    # Training orchestration
    # ------------------------------------------------------------------
    def start_training_async(
        self,
        model_type: str,
        model_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        callback: Optional[Any] = None,
        training_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.training_service.start_training_async(
            model_type=model_type,
            model_name=model_name,
            parameters=parameters or {},
            callback=callback,
            training_id=training_id,
        )

    def train_model(
        self,
        model_type: str,
        model_name: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        return self.training_service.train_model(
            model_type=model_type,
            model_name=model_name,
            parameters=parameters,
            callback=callback,
        )

    def train_all_models(
        self,
        parameters_by_model: Optional[Dict[str, Dict[str, Any]]] = None,
        callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        return self.training_service.train_all_models(parameters_by_model, callback)

    def get_training_status(self, training_id: str) -> Optional[Dict[str, Any]]:
        return self.training_service.get_training_status(training_id)

    def cancel_training(self, training_id: str) -> Dict[str, Any]:
        return self.training_service.cancel_training(training_id)

    def get_training_logs(self, training_id: str, lines: int = 100) -> List[str]:
        return self.training_service.get_training_logs(training_id, lines)

    def list_training_jobs(self) -> List[Dict[str, Any]]:
        return self.training_service.list_training_jobs()

    # ------------------------------------------------------------------
    # Recommendation helpers
    # ------------------------------------------------------------------
    def get_recommendations(
        self,
        user_id: str,
        model_type: Optional[str] = None,
        limit: int = 10,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate recommendations leveraging the trained models."""

        model_type = (model_type or "hybrid").lower()
        context = context or {}
        user_key = self._normalize_uuid(user_id)

        cf_model = self.get_active_model("als")
        content_model = self.get_active_model("content")

        if model_type in {"hybrid", "auto"}:
            hybrid_recs = self.hybrid_service.get_recommendations(
                user_id=user_key,
                cf_model=cf_model,
                content_model=content_model,
                n_recommendations=limit,
            )
            if hybrid_recs:
                return self._format_hybrid_recommendations(hybrid_recs, limit)

        if model_type in {"als", "collaborative"}:
            if not cf_model:
                self.logger.warning("ALS model not available in cache")
                return []

            product_ids = self.als_service.get_recommendations(
                model_data=cf_model,
                user_id=user_key,
                n_recommendations=limit,
            )
            return self._format_product_id_list(
                product_ids,
                algorithm="collaborative_filtering",
                reason="Similar customers also bought this",
                limit=limit,
            )

        if model_type in {"content", "content_based"}:
            if not content_model:
                self.logger.warning("Content-based model not available in cache")
                return []

            product_id = context.get("product_id")
            if not product_id:
                self.logger.warning(
                    "Content recommendations require a reference product_id"
                )
                return []

            similar_ids = self.content_service.get_recommendations(
                model_data=content_model,
                product_id=self._normalize_uuid(product_id),
                n_recommendations=limit,
            )
            return self._format_product_id_list(
                similar_ids,
                algorithm="content_based",
                reason="Similarity in product attributes",
                limit=limit,
            )

        # Fallback to hybrid attempt if available
        if cf_model or content_model:
            hybrid_recs = self.hybrid_service.get_recommendations(
                user_id=user_key,
                cf_model=cf_model,
                content_model=content_model,
                n_recommendations=limit,
            )
            return self._format_hybrid_recommendations(hybrid_recs, limit)

        self.logger.warning("No trained models available for recommendations")
        return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _format_hybrid_recommendations(
        self, recommendations: List[Dict[str, Any]], limit: int
    ) -> List[Dict[str, Any]]:
        formatted = []
        for rec in recommendations[:limit]:
            product_id = rec.get("product_id")
            if product_id is None:
                continue
            formatted.append(
                {
                    "product_id": str(product_id),
                    "score": float(rec.get("score", 0.5)),
                    "algorithm": rec.get("algorithm", "hybrid"),
                    "reason": "Personalized blend of collaborative and content signals",
                    "details": {
                        "cf_score": rec.get("cf_score"),
                        "content_score": rec.get("content_score"),
                        "trending_score": rec.get("trending_score"),
                    },
                }
            )
        return formatted

    def _format_product_id_list(
        self,
        product_ids: List[Any],
        algorithm: str,
        reason: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        formatted: List[Dict[str, Any]] = []
        for idx, product_id in enumerate(product_ids[:limit]):
            formatted.append(
                {
                    "product_id": str(product_id),
                    "score": 1.0 - (idx / max(1, limit)),
                    "algorithm": algorithm,
                    "reason": reason,
                }
            )
        return formatted

    @staticmethod
    def _normalize_uuid(value: Any) -> Any:
        try:
            return uuid.UUID(str(value))
        except (ValueError, TypeError, AttributeError):
            return value
