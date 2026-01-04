"""
Analysis request and result models.
"""
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class RiskLevel(str, Enum):
    """Liquefaction risk levels based on Factor of Safety."""

    VERY_HIGH = "very_high"  # FS < 0.5
    HIGH = "high"  # 0.5 <= FS < 1.0
    MODERATE = "moderate"  # 1.0 <= FS < 1.5
    LOW = "low"  # FS >= 1.5


class LocationData(BaseModel):
    """Geographic location data."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    elevation: Optional[float] = Field(default=None, description="Elevation (m)")
    slope: Optional[float] = Field(default=None, description="Ground slope (degrees)")


class EarthquakeData(BaseModel):
    """Earthquake event data."""

    magnitude: float = Field(..., ge=0, le=10, description="Earthquake magnitude")
    depth: float = Field(default=10.0, ge=0, description="Focal depth (km)")
    distance: float = Field(
        default=50.0, ge=0, description="Distance from site (km)"
    )
    pga: float = Field(
        default=0.0, ge=0, description="Peak Ground Acceleration (g)"
    )
    event_id: Optional[str] = Field(default=None, description="USGS event ID")
    event_time: Optional[datetime] = Field(default=None, description="Event time")
    location: Optional[str] = Field(default=None, description="Event location")


class WeatherData(BaseModel):
    """Weather and precipitation data."""

    temperature: Optional[float] = Field(default=None, description="Temperature (°C)")
    humidity: Optional[float] = Field(default=None, description="Humidity (%)")
    precipitation_1h: Optional[float] = Field(
        default=None, description="Precipitation last hour (mm)"
    )
    precipitation_24h: Optional[float] = Field(
        default=None, description="Precipitation last 24h (mm)"
    )
    groundwater_factor: float = Field(
        default=1.0,
        ge=0.5,
        le=2.0,
        description="Groundwater adjustment factor based on precipitation",
    )


class LandCoverData(BaseModel):
    """Land cover classification data from Earth Engine."""

    land_cover_type: Optional[str] = Field(
        default=None, description="Land cover classification"
    )
    forest_cover: Optional[float] = Field(
        default=None, ge=0, le=100, description="Forest cover percentage"
    )
    soil_moisture: Optional[float] = Field(
        default=None, description="Soil moisture index"
    )
    susceptibility_factor: float = Field(
        default=1.0,
        ge=0.5,
        le=2.0,
        description="Land cover susceptibility factor",
    )


class LayerResult(BaseModel):
    """Liquefaction analysis result for a single layer/depth."""

    depth: float = Field(..., description="Analysis depth (m)")
    sigma_v: float = Field(..., description="Total vertical stress (kPa)")
    sigma_v_eff: float = Field(..., description="Effective vertical stress (kPa)")
    rd: float = Field(..., description="Stress reduction factor")
    csr: float = Field(..., description="Cyclic Stress Ratio")
    n1_60_cs: Optional[float] = Field(
        default=None, description="Corrected SPT N-value"
    )
    qc1n_cs: Optional[float] = Field(
        default=None, description="Corrected CPT tip resistance"
    )
    crr: float = Field(..., description="Cyclic Resistance Ratio")
    msf: float = Field(..., description="Magnitude Scaling Factor")
    k_sigma: float = Field(..., description="Overburden correction factor")
    factor_of_safety: float = Field(..., description="Factor of Safety")
    risk_level: RiskLevel = Field(..., description="Risk level")
    test_type: Literal["SPT", "CPT"] = Field(..., description="Test type used")


class LiquefactionRisk(BaseModel):
    """Overall liquefaction risk assessment."""

    overall_fs: float = Field(..., description="Minimum Factor of Safety")
    overall_risk: RiskLevel = Field(..., description="Overall risk level")
    lpi: Optional[float] = Field(
        default=None, description="Liquefaction Potential Index"
    )
    critical_depth: float = Field(
        ..., description="Depth with lowest Factor of Safety (m)"
    )
    liquefaction_likely: bool = Field(
        ..., description="Whether liquefaction is likely"
    )
    recommendation: str = Field(..., description="Risk assessment recommendation")


class AnalysisRequest(BaseModel):
    """Request model for liquefaction analysis."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    groundwater_depth: float = Field(default=2.0, ge=0, description="GWT depth (m)")

    # Soil test data - at least one required
    spt_data: Optional[List[dict]] = Field(
        default=None, description="SPT test data list"
    )
    cpt_data: Optional[List[dict]] = Field(
        default=None, description="CPT test data list"
    )
    layers: Optional[List[dict]] = Field(
        default=None, description="Soil layer definitions"
    )

    # Earthquake parameters - either use recent earthquake or manual input
    use_recent_earthquake: bool = Field(
        default=True, description="Use most recent nearby earthquake"
    )
    earthquake_magnitude: Optional[float] = Field(
        default=None, ge=0, le=10, description="Manual earthquake magnitude"
    )
    pga: Optional[float] = Field(
        default=None, ge=0, le=2.0, description="Manual PGA (g)"
    )

    # Optional parameters
    include_weather: bool = Field(default=True, description="Include weather data")
    include_landcover: bool = Field(
        default=True, description="Include land cover data"
    )


class AnalysisResult(BaseModel):
    """Complete liquefaction analysis result."""

    request_id: str = Field(..., description="Unique analysis ID")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Analysis timestamp"
    )
    location: LocationData = Field(..., description="Site location data")
    earthquake: Optional[EarthquakeData] = Field(
        default=None, description="Earthquake data used"
    )
    weather: Optional[WeatherData] = Field(default=None, description="Weather data")
    land_cover: Optional[LandCoverData] = Field(
        default=None, description="Land cover data"
    )
    layer_results: List[LayerResult] = Field(
        default_factory=list, description="Results per layer/depth"
    )
    risk_assessment: LiquefactionRisk = Field(
        ..., description="Overall risk assessment"
    )

    def get_risk_color(self) -> str:
        """Get color code for risk level."""
        colors = {
            RiskLevel.VERY_HIGH: "#dc3545",  # Red
            RiskLevel.HIGH: "#fd7e14",  # Orange
            RiskLevel.MODERATE: "#ffc107",  # Yellow
            RiskLevel.LOW: "#28a745",  # Green
        }
        return colors.get(self.risk_assessment.overall_risk, "#6c757d")
