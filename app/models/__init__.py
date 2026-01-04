"""Data Models Package."""
from .soil import SoilProfile, SPTData, CPTData, SoilLayer
from .analysis import (
    AnalysisRequest,
    AnalysisResult,
    LiquefactionRisk,
    LocationData,
)

__all__ = [
    "SoilProfile",
    "SPTData",
    "CPTData",
    "SoilLayer",
    "AnalysisRequest",
    "AnalysisResult",
    "LiquefactionRisk",
    "LocationData",
]
