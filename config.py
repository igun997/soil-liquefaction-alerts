"""
Configuration module for Liquefaction Alert Detection System.
Loads settings from environment variables with fallback defaults.
"""
import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "Liquefaction Alert Detection System"
    debug: bool = False

    # OpenTopography API
    opentopography_api_key: str = "546e26808229139f76a05ff49727578f"
    opentopography_base_url: str = "https://portal.opentopography.org/API"

    # OpenWeatherMap API
    openweathermap_api_key: str = "1adebca39f852f4db17734b41c4ed14d"
    openweathermap_base_url: str = "https://api.openweathermap.org/data/2.5"

    # USGS Earthquake API
    usgs_earthquake_base_url: str = "https://earthquake.usgs.gov/fdsnws/event/1"

    # Google Earth Engine
    # Note: Earth Engine requires OAuth authentication or service account
    # Set EE_SERVICE_ACCOUNT_KEY to path of service account JSON key file
    ee_service_account_key: str = ""
    ee_project: str = ""

    # Default location (for initial map view)
    default_latitude: float = 0.0
    default_longitude: float = 0.0
    default_zoom: int = 2

    # Analysis parameters
    default_magnitude: float = 7.5  # Reference earthquake magnitude
    gravity: float = 9.81  # m/s²
    water_density: float = 1000  # kg/m³

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Export settings for easy access
settings = get_settings()
