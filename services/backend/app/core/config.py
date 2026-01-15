"""
Application configuration settings.
Loads from environment variables with fallback defaults.
"""

import os
from functools import lru_cache
from typing import Any, List, Optional

from pydantic import BaseSettings, validator


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All sensitive credentials should be set via environment variables.
    Create a .env file in the backend root directory with the required values.
    """

    # API Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Ecommerce Backend"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "Advanced Ecommerce Backend with ML-powered Recommendations"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Security - MUST be set via environment variables
    SECRET_KEY: str = "ABCD1234EFGH5678IJKL9012MNOP3456QRST7890UVWX"
    JWT_ISSUER: str = "ecommerce-backend"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1230
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS - Comma-separated list of allowed origins
    BACKEND_CORS_ORIGINS: Any = None

    @validator("BACKEND_CORS_ORIGINS", pre=True, always=True)
    def assemble_cors_origins(cls, v) -> List[str]:
        """
        Parse CORS origins from environment variable.
        Accepts comma-separated string or list.
        Defaults to common development origins if not specified.
        """
        if v is None or v == "":
            # Default to common development origins if not specified
            return [
                "http://localhost:3000",
                "http://localhost:5173",
                "http://localhost:5174",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
                "http://127.0.0.1:5174",
                "http://localhost:8000",
                "http://127.0.0.1:8000",
            ]
        if isinstance(v, str):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, list):
            return v
        return []

    # Database Configuration - Use environment variables
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "ecommerce_user"
    POSTGRES_PASSWORD: str = "ecommerce_pass"
    POSTGRES_DB: str = "ecommerce"
    POSTGRES_PORT: str = "5435"

    DATABASE_URL: Optional[str] = None

    @validator("DATABASE_URL", pre=True)
    def assemble_db_connection(cls, v, values):
        """
        Construct DATABASE_URL from individual components if not provided.
        Priority: explicit DATABASE_URL > constructed from components
        """
        if isinstance(v, str) and v:
            return v
        return f"postgresql://{values.get('POSTGRES_USER')}:{values.get('POSTGRES_PASSWORD')}@{values.get('POSTGRES_SERVER')}:{values.get('POSTGRES_PORT')}/{values.get('POSTGRES_DB')}"

    # File Upload Settings
    UPLOAD_FOLDER: str = "static/uploads"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_IMAGE_EXTENSIONS: set = {"png", "jpg", "jpeg", "gif", "webp"}

    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "app.log"

    # AWS Bedrock Configuration
    # Used for embeddings and LLM operations (explanations, descriptions)
    AWS_ACCESS_KEY_ID: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID", None)
    AWS_SECRET_ACCESS_KEY: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY", None)
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")

    # AWS Bedrock Model Configuration
    BEDROCK_EMBEDDING_MODEL: str = "amazon.titan-embed-text-v1"  # Titan embeddings
    BEDROCK_LLM_MODEL: str = (
        "anthropic.claude-3-sonnet-20240229-v1:0"  # Claude for text generation
    )
    BEDROCK_EMBEDDING_DIMENSION: int = 1536  # Titan embedding dimension

    # Embedding service settings
    EMBEDDING_BATCH_SIZE: int = 25  # Process embeddings in batches
    EMBEDDING_CACHE_TTL: int = 86400  # Cache embeddings for 24 hours

    # LLM service settings
    LLM_MAX_TOKENS: int = 1000  # Max tokens for LLM responses
    LLM_TEMPERATURE: float = 0.7  # Temperature for text generation
    LLM_TOP_P: float = 0.9  # Top-p sampling parameter

    # Google Gemini Configuration
    # Used for image generation (product posters, banners)
    GOOGLE_API_KEY: Optional[str] = os.getenv("GOOGLE_API_KEY", None)
    GEMINI_MODEL: str = "models/gemini-2.0-flash"  # Gemini model for image generation
    GEMINI_IMAGE_MODEL: str = "imagen-4.0-generate-001"  # Imagen for image generation

    # Image generation settings
    IMAGE_GENERATION_SIZE: str = "1024x1024"  # Default image size
    IMAGE_STORAGE_PATH: str = (
        "static/generated_images"  # Where to store generated images
    )
    MAX_IMAGE_GENERATION_RETRIES: int = 3  # Retry failed generations

    # ML Model Configuration
    MODEL_STORAGE_PATH: str = "ml_models"  # Directory to store trained models
    MODEL_VERSION_LIMIT: int = 5  # Keep last N versions of each model

    # Recommendation settings
    SIMILARITY_THRESHOLD: float = 0.7  # Minimum similarity for recommendations
    MIN_RECOMMENDATIONS: int = 5  # Minimum number of recommendations to return
    MAX_RECOMMENDATIONS: int = 20  # Maximum number of recommendations to return
    DEFAULT_RECOMMENDATION_COUNT: int = 10  # Default recommendation count

    # Collaborative filtering settings
    CF_FACTORS: int = 50  # Number of latent factors for matrix factorization
    CF_REGULARIZATION: float = 0.01  # Regularization parameter
    CF_ITERATIONS: int = 15  # Training iterations
    CF_MIN_INTERACTIONS: int = 3  # Minimum interactions for user/item inclusion

    # FBT (Frequently Bought Together) settings
    FBT_MIN_SUPPORT: float = 0.0002  # Minimum support for association rules
    FBT_MIN_CONFIDENCE: float = 0.05  # Minimum confidence for recommendations
    FBT_MIN_LIFT: float = 1.0  # Minimum lift threshold
    FBT_MAX_ITEMSET_SIZE: int = 3  # Maximum items in a frequent itemset

    # User segmentation settings
    RFM_SEGMENTS: int = 5  # Number of RFM segments
    BEHAVIORAL_CLUSTERS: int = 8  # Number of behavioral clusters
    CLUSTERING_MIN_SAMPLES: int = 10  # Minimum samples for clustering

    # Model training schedule
    TRAINING_SCHEDULE_CRON: str = "0 2 * * *"  # Train at 2 AM daily (cron format)
    INCREMENTAL_TRAINING_DAYS: int = 7  # Days of data for incremental training
    FULL_TRAINING_DAYS: int = 90  # Days of data for full retraining

    # Initial Admin User (for development only)
    FIRST_SUPERUSER_USERNAME: str = "admin"
    FIRST_SUPERUSER_EMAIL: str = "admin@example.com"
    FIRST_SUPERUSER_PASSWORD: str = "admin123"

    class Config(BaseSettings.Config):
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings():
    return Settings()
