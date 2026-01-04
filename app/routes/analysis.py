"""
Liquefaction analysis API routes.

Main analysis endpoints for computing liquefaction risk.
"""
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.liquefaction import LiquefactionCalculator
from app.services.earthquake import EarthquakeService
from app.services.weather import WeatherService
from app.services.opentopography import OpenTopographyService
from app.services.earth_engine import EarthEngineService
from app.models.soil import SoilProfile, SPTData, CPTData, SoilLayer
from app.models.analysis import (
    AnalysisRequest,
    AnalysisResult,
    LocationData,
    EarthquakeData,
)

router = APIRouter(prefix="/api", tags=["analysis"])


class QuickAnalysisRequest(BaseModel):
    """Simplified request for quick analysis with minimal input."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    groundwater_depth: float = Field(default=2.0, ge=0, description="GWT depth (m)")

    # Simplified soil data
    avg_spt_n: Optional[int] = Field(
        default=None, ge=0, le=100, description="Average SPT N-value"
    )
    avg_cpt_qc: Optional[float] = Field(
        default=None, ge=0, description="Average CPT qc (MPa)"
    )
    fines_content: float = Field(default=15.0, ge=0, le=100, description="Fines (%)")
    analysis_depth: float = Field(default=15.0, ge=1, le=30, description="Depth (m)")

    # Optional earthquake parameters
    earthquake_magnitude: Optional[float] = Field(default=None, ge=0, le=10)
    pga: Optional[float] = Field(default=None, ge=0, le=2.0, description="PGA (g)")


class FullAnalysisRequest(BaseModel):
    """Full analysis request with detailed soil profile."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    groundwater_depth: float = Field(default=2.0, ge=0)

    # Detailed soil data
    layers: list[dict] = Field(default_factory=list)
    spt_data: list[dict] = Field(default_factory=list)
    cpt_data: list[dict] = Field(default_factory=list)

    # Earthquake parameters
    use_recent_earthquake: bool = Field(default=True)
    earthquake_magnitude: Optional[float] = Field(default=None)
    pga: Optional[float] = Field(default=None)

    # Options
    include_weather: bool = Field(default=True)
    include_landcover: bool = Field(default=True)


@router.post("/analyze/quick", response_model=AnalysisResult)
async def quick_analysis(request: QuickAnalysisRequest):
    """
    Perform quick liquefaction analysis with simplified input.

    Suitable for preliminary screening assessments.
    """
    import asyncio

    if request.avg_spt_n is None and request.avg_cpt_qc is None:
        raise HTTPException(
            status_code=400,
            detail="Either avg_spt_n or avg_cpt_qc must be provided",
        )

    # Initialize services
    eq_service = EarthquakeService()
    weather_service = WeatherService()
    topo_service = OpenTopographyService()
    ee_service = EarthEngineService()
    calculator = LiquefactionCalculator()

    try:
        # Fetch all data in parallel
        if request.pga and request.earthquake_magnitude:
            eq_task = asyncio.sleep(0)  # Skip if manual values provided
        else:
            eq_task = eq_service.get_significant_earthquake(
                request.latitude,
                request.longitude,
            )

        weather_task = weather_service.get_current_weather(
            request.latitude,
            request.longitude,
        )
        terrain_task = topo_service.get_terrain_data(
            request.latitude,
            request.longitude,
        )
        landcover_task = ee_service.get_land_cover(
            request.latitude,
            request.longitude,
        )

        results = await asyncio.gather(
            eq_task,
            weather_task,
            terrain_task,
            landcover_task,
            return_exceptions=True,
        )

        # Process earthquake data
        if request.pga and request.earthquake_magnitude:
            earthquake = EarthquakeData(
                magnitude=request.earthquake_magnitude,
                pga=request.pga,
                distance=0,
                depth=10,
            )
        elif isinstance(results[0], EarthquakeData):
            earthquake = results[0]
        else:
            # Use default design earthquake if none found
            earthquake = EarthquakeData(
                magnitude=7.0,
                pga=0.2,
                distance=100,
                depth=15,
                location="Default design earthquake",
            )

        # Process weather data
        weather = results[1] if not isinstance(results[1], Exception) else None

        # Process terrain data
        terrain = results[2] if not isinstance(results[2], Exception) else {}
        elevation = terrain.get("elevation") if isinstance(terrain, dict) else None
        slope = terrain.get("slope_degrees") if isinstance(terrain, dict) else None

        # Process land cover data
        land_cover = results[3] if not isinstance(results[3], Exception) else None

        # Create synthetic soil profile
        profile = _create_synthetic_profile(
            latitude=request.latitude,
            longitude=request.longitude,
            gwt=request.groundwater_depth,
            avg_spt_n=request.avg_spt_n,
            avg_cpt_qc=request.avg_cpt_qc,
            fines_content=request.fines_content,
            max_depth=request.analysis_depth,
        )

        # Run analysis
        layer_results, risk_assessment = calculator.analyze_profile(
            profile=profile,
            amax=earthquake.pga,
            magnitude=earthquake.magnitude,
        )

        return AnalysisResult(
            request_id=str(uuid.uuid4()),
            location=LocationData(
                latitude=request.latitude,
                longitude=request.longitude,
                elevation=elevation,
                slope=slope,
            ),
            earthquake=earthquake,
            weather=weather,
            land_cover=land_cover,
            layer_results=layer_results,
            risk_assessment=risk_assessment,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await asyncio.gather(
            eq_service.close(),
            weather_service.close(),
            topo_service.close(),
            ee_service.close(),
        )


@router.post("/analyze/full", response_model=AnalysisResult)
async def full_analysis(request: FullAnalysisRequest):
    """
    Perform comprehensive liquefaction analysis.

    Uses detailed soil profile and integrates all data sources.
    """
    import asyncio

    # Validate input
    if not request.spt_data and not request.cpt_data:
        raise HTTPException(
            status_code=400,
            detail="Either SPT or CPT test data must be provided",
        )

    # Initialize services
    eq_service = EarthquakeService()
    weather_service = WeatherService()
    topo_service = OpenTopographyService()
    ee_service = EarthEngineService()
    calculator = LiquefactionCalculator()

    try:
        # Fetch external data in parallel
        tasks = []

        if request.use_recent_earthquake and not (
            request.pga and request.earthquake_magnitude
        ):
            tasks.append(
                eq_service.get_significant_earthquake(
                    request.latitude, request.longitude
                )
            )
        else:
            tasks.append(asyncio.sleep(0))  # Placeholder

        if request.include_weather:
            tasks.append(
                weather_service.get_current_weather(
                    request.latitude, request.longitude
                )
            )
        else:
            tasks.append(asyncio.sleep(0))

        tasks.append(
            topo_service.get_terrain_data(request.latitude, request.longitude)
        )

        if request.include_landcover:
            tasks.append(
                ee_service.get_land_cover(request.latitude, request.longitude)
            )
        else:
            tasks.append(asyncio.sleep(0))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        earthquake = None
        if request.pga and request.earthquake_magnitude:
            earthquake = EarthquakeData(
                magnitude=request.earthquake_magnitude,
                pga=request.pga,
                distance=0,
                depth=10,
            )
        elif isinstance(results[0], EarthquakeData):
            earthquake = results[0]

        if not earthquake:
            earthquake = EarthquakeData(
                magnitude=7.0,
                pga=0.2,
                distance=100,
                depth=15,
                location="Default design earthquake",
            )

        weather = results[1] if request.include_weather and not isinstance(
            results[1], Exception
        ) else None

        terrain = results[2] if not isinstance(results[2], Exception) else {}

        land_cover = results[3] if request.include_landcover and not isinstance(
            results[3], Exception
        ) else None

        # Create soil profile from request data
        profile = SoilProfile(
            latitude=request.latitude,
            longitude=request.longitude,
            groundwater_depth=request.groundwater_depth,
            layers=[SoilLayer(**layer) for layer in request.layers],
            spt_data=[SPTData(**spt) for spt in request.spt_data],
            cpt_data=[CPTData(**cpt) for cpt in request.cpt_data],
        )

        # Adjust groundwater for weather if available
        if weather and hasattr(weather, "groundwater_factor"):
            adjusted_gwt = weather_service.estimate_gwt_adjustment(
                profile.groundwater_depth,
                weather.groundwater_factor,
            )
            profile.groundwater_depth = adjusted_gwt

        # Run analysis
        layer_results, risk_assessment = calculator.analyze_profile(
            profile=profile,
            amax=earthquake.pga,
            magnitude=earthquake.magnitude,
        )

        # Get elevation
        elevation = terrain.get("elevation") if terrain else None

        return AnalysisResult(
            request_id=str(uuid.uuid4()),
            location=LocationData(
                latitude=request.latitude,
                longitude=request.longitude,
                elevation=elevation,
                slope=terrain.get("slope_degrees") if terrain else None,
            ),
            earthquake=earthquake,
            weather=weather,
            land_cover=land_cover,
            layer_results=layer_results,
            risk_assessment=risk_assessment,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await asyncio.gather(
            eq_service.close(),
            weather_service.close(),
            topo_service.close(),
            ee_service.close(),
        )


def _create_synthetic_profile(
    latitude: float,
    longitude: float,
    gwt: float,
    avg_spt_n: Optional[int],
    avg_cpt_qc: Optional[float],
    fines_content: float,
    max_depth: float,
) -> SoilProfile:
    """
    Create a synthetic soil profile from simplified parameters.

    Used for quick screening analyses.
    """
    # Create layers
    layers = [
        SoilLayer(
            depth_top=0,
            depth_bottom=max_depth,
            unit_weight=18.0,
            fines_content=fines_content,
        )
    ]

    # Create test data at regular intervals
    depths = [d for d in range(1, int(max_depth) + 1, 2)]

    spt_data = []
    cpt_data = []

    if avg_spt_n is not None:
        for depth in depths:
            # Add some depth variation to N-value
            n_value = max(1, int(avg_spt_n * (0.8 + 0.03 * depth)))
            spt_data.append(
                SPTData(
                    depth=float(depth),
                    n_value=n_value,
                    fines_content=fines_content,
                )
            )

    if avg_cpt_qc is not None:
        for depth in depths:
            # Add some depth variation to qc
            qc = avg_cpt_qc * (0.8 + 0.03 * depth)
            cpt_data.append(
                CPTData(
                    depth=float(depth),
                    qc=qc,
                    fs=qc * 10,  # Approximate sleeve friction
                    fines_content=fines_content,
                )
            )

    return SoilProfile(
        name="Quick Analysis Profile",
        latitude=latitude,
        longitude=longitude,
        groundwater_depth=gwt,
        layers=layers,
        spt_data=spt_data,
        cpt_data=cpt_data,
    )
