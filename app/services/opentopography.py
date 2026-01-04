"""
OpenTopography API service.

Fetches elevation and terrain data for site analysis.
"""
from typing import Optional, Tuple
import httpx
import math

from config import settings


class OpenTopographyService:
    """
    Service for fetching topography data from OpenTopography.

    Uses the OpenTopography REST API to fetch DEM data.
    """

    BASE_URL = settings.opentopography_base_url
    API_KEY = settings.opentopography_api_key

    # Available DEM datasets
    DATASETS = {
        "SRTMGL1": "SRTM GL1 (30m)",
        "SRTMGL3": "SRTM GL3 (90m)",
        "AW3D30": "ALOS World 3D (30m)",
        "NASADEM": "NASADEM (30m)",
        "COP30": "Copernicus DEM (30m)",
        "COP90": "Copernicus DEM (90m)",
    }

    def __init__(self):
        """Initialize OpenTopography service."""
        self.client = httpx.AsyncClient(timeout=60.0)

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    async def get_elevation(
        self,
        latitude: float,
        longitude: float,
        dataset: str = "SRTMGL1",
    ) -> Optional[float]:
        """
        Get elevation at a specific point.

        Args:
            latitude: Point latitude
            longitude: Point longitude
            dataset: DEM dataset to use

        Returns:
            Elevation in meters, or None if failed
        """
        # Create small bounding box around point
        delta = 0.001  # ~100m
        bbox = self._create_bbox(latitude, longitude, delta)

        params = {
            "demtype": dataset,
            "south": bbox["south"],
            "north": bbox["north"],
            "west": bbox["west"],
            "east": bbox["east"],
            "outputFormat": "GTiff",
            "API_Key": self.API_KEY,
        }

        try:
            # Note: Full implementation would download and parse GeoTIFF
            # For simplicity, we use a point query approach
            response = await self.client.get(
                f"{self.BASE_URL}/globaldem",
                params=params,
            )

            if response.status_code == 200:
                # In production, parse GeoTIFF and extract center value
                # For now, return estimated elevation from alternative source
                return await self._get_elevation_fallback(latitude, longitude)

            return None

        except Exception as e:
            print(f"Error fetching elevation: {e}")
            return await self._get_elevation_fallback(latitude, longitude)

    async def _get_elevation_fallback(
        self,
        latitude: float,
        longitude: float,
    ) -> Optional[float]:
        """
        Fallback elevation lookup using multiple APIs.
        """
        # Try Open-Meteo API first (fast and reliable)
        try:
            response = await self.client.get(
                "https://api.open-meteo.com/v1/elevation",
                params={"latitude": latitude, "longitude": longitude},
                timeout=10.0,
            )
            if response.status_code == 200:
                data = response.json()
                elevation = data.get("elevation")
                if elevation is not None:
                    # Returns array, get first value
                    if isinstance(elevation, list):
                        return elevation[0] if elevation else None
                    return elevation
        except Exception as e:
            print(f"Open-Meteo elevation failed: {e}")

        # Try Open-Elevation API as backup
        try:
            response = await self.client.get(
                "https://api.open-elevation.com/api/v1/lookup",
                params={"locations": f"{latitude},{longitude}"},
                timeout=10.0,
            )
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                if results:
                    return results[0].get("elevation")
        except Exception as e:
            print(f"Open-Elevation failed: {e}")

        return None

    async def get_terrain_data(
        self,
        latitude: float,
        longitude: float,
        radius_m: float = 500,
    ) -> dict:
        """
        Get terrain characteristics for an area.

        Returns elevation, slope, and terrain classification.

        Args:
            latitude: Center latitude
            longitude: Center longitude
            radius_m: Analysis radius in meters

        Returns:
            Dictionary with terrain data
        """
        # Get center elevation only (to avoid slow multiple API calls)
        center_elevation = await self._get_elevation_fallback(latitude, longitude)

        # Estimate slope as None (would need multiple points)
        slope_deg = None

        # Classify terrain based on elevation
        terrain_class = self._classify_terrain(center_elevation, slope_deg)

        return {
            "elevation": center_elevation,
            "slope_degrees": slope_deg,
            "terrain_class": terrain_class,
            "analysis_radius_m": radius_m,
        }

    def _create_bbox(
        self,
        latitude: float,
        longitude: float,
        delta: float,
    ) -> dict:
        """Create bounding box around a point."""
        return {
            "south": latitude - delta,
            "north": latitude + delta,
            "west": longitude - delta,
            "east": longitude + delta,
        }

    def _classify_terrain(
        self,
        elevation: Optional[float],
        slope: Optional[float],
    ) -> str:
        """
        Classify terrain based on elevation and slope.

        Returns terrain classification relevant to liquefaction:
        - Coastal lowland
        - River valley
        - Flat terrain
        - Gentle slope
        - Steep slope
        - Highland
        """
        if elevation is None:
            return "Unknown"

        if elevation < 10:
            return "Coastal lowland"
        elif elevation < 50 and (slope is None or slope < 2):
            return "River valley/Alluvial"
        elif slope is not None:
            if slope < 2:
                return "Flat terrain"
            elif slope < 5:
                return "Gentle slope"
            elif slope < 15:
                return "Moderate slope"
            else:
                return "Steep slope"
        elif elevation > 500:
            return "Highland"
        else:
            return "Flat terrain"

    def get_liquefaction_susceptibility(
        self,
        terrain_class: str,
        elevation: Optional[float],
    ) -> Tuple[str, float]:
        """
        Estimate liquefaction susceptibility from terrain.

        Returns susceptibility level and factor.

        Terrain-based susceptibility:
        - Coastal/alluvial areas: High susceptibility
        - River valleys: High to moderate
        - Flat lowlands: Moderate
        - Slopes: Low to moderate
        - Highlands: Low
        """
        susceptibility_map = {
            "Coastal lowland": ("High", 1.3),
            "River valley/Alluvial": ("High", 1.2),
            "Flat terrain": ("Moderate", 1.0),
            "Gentle slope": ("Low-Moderate", 0.9),
            "Moderate slope": ("Low", 0.8),
            "Steep slope": ("Very Low", 0.7),
            "Highland": ("Very Low", 0.7),
            "Unknown": ("Unknown", 1.0),
        }

        return susceptibility_map.get(terrain_class, ("Unknown", 1.0))
