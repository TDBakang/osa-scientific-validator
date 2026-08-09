"""Application settings and environment configuration."""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration settings for rocsa_generator."""

    model_config = SettingsConfigDict(
        env_prefix="ROCSA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="development", description="Execution environment")
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging verbosity level")
    
    # Output directory configuration
    output_dir: Path = Field(
        default=Path("./output"),
        description="Target path where generated assets are written",
    )
    
    # Optional API key or remote service config if applicable
    api_key: Optional[str] = Field(default=None, description="Optional API credentials")


# Single instance for simple import across the library
settings = Settings()