"""
Data fetching API routes.

Endpoints for fetching earthquake, weather, elevation, and land cover data.
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query

from app.services.earthquake import EarthquakeService
from app.services.weather import WeatherService
from app.services.opentopography import OpenTopographyService
from app.services.earth_engine import EarthEngineService
from app.models.analysis import EarthquakeData, WeatherData, LandCoverData

router = APIRouter(prefix="/api", tags=["data"])


@router.get("/earthquakes", response_model=List[EarthquakeData])
async def get_earthquakes(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
    radius_km: float = Query(500, ge=10, le=2000, description="Search radius (km)"),
    min_magnitude: float = Query(4.0, ge=0, le=10, description="Minimum magnitude"),
    days: int = Query(30, ge=1, le=365, description="Days to look back"),
    limit: int = Query(10, ge=1, le=100, description="Maximum results"),
):
    """
    Get recent earthquakes near a location.

    Returns earthquakes sorted by estimated PGA at the site.
    """
    service = EarthquakeService()
    try:
        earthquakes = await service.get_recent_earthquakes(
            latitude=lat,
            longitude=lon,
            max_radius_km=radius_km,
            min_magnitude=min_magnitude,
            days_back=days,
            limit=limit,
        )
        return earthquakes
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await service.close()


@router.get("/earthquakes/significant", response_model=Optional[EarthquakeData])
async def get_significant_earthquake(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
    radius_km: float = Query(500, ge=10, le=2000, description="Search radius (km)"),
):
    """
    Get the most significant recent earthquake for analysis.

    Returns the earthquake with highest estimated PGA at the site.
    """
    service = EarthquakeService()
    try:
        earthquake = await service.get_significant_earthquake(
            latitude=lat,
            longitude=lon,
            max_radius_km=radius_km,
        )
        return earthquake
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await service.close()


@router.get("/weather", response_model=Optional[WeatherData])
async def get_weather(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
):
    """
    Get current weather data for a location.

    Includes temperature, humidity, precipitation, and groundwater factor.
    """
    service = WeatherService()
    try:
        weather = await service.get_current_weather(
            latitude=lat,
            longitude=lon,
        )
        return weather
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await service.close()


@router.get("/elevation")
async def get_elevation(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
):
    """
    Get elevation at a point.

    Returns elevation in meters from OpenTopography or fallback source.
    """
    service = OpenTopographyService()
    try:
        elevation = await service.get_elevation(latitude=lat, longitude=lon)
        return {"latitude": lat, "longitude": lon, "elevation_m": elevation}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await service.close()


@router.get("/terrain")
async def get_terrain(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
    radius_m: float = Query(500, ge=100, le=5000, description="Analysis radius (m)"),
):
    """
    Get terrain characteristics for an area.

    Returns elevation, slope, terrain classification, and susceptibility.
    """
    service = OpenTopographyService()
    try:
        terrain = await service.get_terrain_data(
            latitude=lat,
            longitude=lon,
            radius_m=radius_m,
        )

        # Add susceptibility assessment
        susceptibility, factor = service.get_liquefaction_susceptibility(
            terrain["terrain_class"],
            terrain["elevation"],
        )
        terrain["susceptibility"] = susceptibility
        terrain["susceptibility_factor"] = factor

        return terrain
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await service.close()


@router.get("/landcover", response_model=LandCoverData)
async def get_landcover(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
):
    """
    Get land cover classification at a point.

    Uses Google Earth Engine if available, otherwise falls back to OSM.
    """
    service = EarthEngineService()
    try:
        land_cover = await service.get_land_cover(
            latitude=lat,
            longitude=lon,
        )
        return land_cover
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await service.close()


@router.get("/site-data")
async def get_site_data(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude"),
):
    """
    Get comprehensive site data for liquefaction analysis.

    Fetches all available data sources in parallel and returns combined results.
    """
    import asyncio

    eq_service = EarthquakeService()
    weather_service = WeatherService()
    topo_service = OpenTopographyService()
    ee_service = EarthEngineService()

    try:
        # Fetch all data in parallel
        earthquake_task = eq_service.get_significant_earthquake(lat, lon)
        weather_task = weather_service.get_current_weather(lat, lon)
        terrain_task = topo_service.get_terrain_data(lat, lon)
        landcover_task = ee_service.get_land_cover(lat, lon)

        earthquake, weather, terrain, landcover = await asyncio.gather(
            earthquake_task,
            weather_task,
            terrain_task,
            landcover_task,
        )

        # Calculate susceptibility
        susceptibility, factor = topo_service.get_liquefaction_susceptibility(
            terrain.get("terrain_class", "Unknown"),
            terrain.get("elevation"),
        )

        return {
            "location": {"latitude": lat, "longitude": lon},
            "earthquake": earthquake.model_dump() if earthquake else None,
            "weather": weather.model_dump() if weather else None,
            "terrain": {
                **terrain,
                "susceptibility": susceptibility,
                "susceptibility_factor": factor,
            },
            "landcover": landcover.model_dump() if landcover else None,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await asyncio.gather(
            eq_service.close(),
            weather_service.close(),
            topo_service.close(),
            ee_service.close(),
        )
