"""
Google Earth Engine service.

Fetches land cover and soil data for liquefaction analysis.
Note: Requires Earth Engine authentication.
"""
from typing import Optional, Dict, Any
import httpx

from config import settings
from app.models.analysis import LandCoverData


class EarthEngineService:
    """
    Service for fetching geospatial data from Google Earth Engine.

    Note: Earth Engine requires authentication via:
    1. Service account (for server applications)
    2. OAuth (for interactive use)

    If Earth Engine is not configured, falls back to alternative data sources.
    """

    def __init__(self):
        """Initialize Earth Engine service."""
        self.ee_initialized = False
        self.client = httpx.AsyncClient(timeout=30.0)
        self._try_init_ee()

    def _try_init_ee(self):
        """Attempt to initialize Earth Engine."""
        try:
            import ee

            if settings.ee_service_account_key:
                # Initialize with service account
                credentials = ee.ServiceAccountCredentials(
                    None,
                    settings.ee_service_account_key,
                )
                ee.Initialize(credentials, project=settings.ee_project)
                self.ee_initialized = True
            else:
                # Try default authentication
                try:
                    ee.Initialize()
                    self.ee_initialized = True
                except Exception:
                    pass
        except ImportError:
            pass
        except Exception as e:
            print(f"Earth Engine initialization failed: {e}")

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    async def get_land_cover(
        self,
        latitude: float,
        longitude: float,
    ) -> LandCoverData:
        """
        Get land cover classification at a point.

        Uses ESA WorldCover or falls back to OpenStreetMap data.

        Args:
            latitude: Point latitude
            longitude: Point longitude

        Returns:
            LandCoverData with classification and susceptibility
        """
        if self.ee_initialized:
            return await self._get_land_cover_ee(latitude, longitude)
        else:
            return await self._get_land_cover_fallback(latitude, longitude)

    async def _get_land_cover_ee(
        self,
        latitude: float,
        longitude: float,
    ) -> LandCoverData:
        """Get land cover using Earth Engine."""
        try:
            import ee

            point = ee.Geometry.Point([longitude, latitude])

            # Use ESA WorldCover 10m
            worldcover = ee.ImageCollection("ESA/WorldCover/v200").first()
            value = worldcover.sample(point, 10).first().get("Map").getInfo()

            land_cover_map = {
                10: "Tree cover",
                20: "Shrubland",
                30: "Grassland",
                40: "Cropland",
                50: "Built-up",
                60: "Bare/sparse vegetation",
                70: "Snow and ice",
                80: "Permanent water",
                90: "Herbaceous wetland",
                95: "Mangroves",
                100: "Moss and lichen",
            }

            land_cover_type = land_cover_map.get(value, "Unknown")

            # Get forest cover from Hansen dataset
            hansen = ee.Image("UMD/hansen/global_forest_change_2022_v1_10")
            tree_cover = hansen.select("treecover2000").sample(point, 30)
            forest_pct = tree_cover.first().get("treecover2000").getInfo()

            # Calculate susceptibility factor
            susceptibility = self._calculate_susceptibility(value, forest_pct)

            return LandCoverData(
                land_cover_type=land_cover_type,
                forest_cover=forest_pct,
                soil_moisture=None,  # Would need SMAP data
                susceptibility_factor=susceptibility,
            )

        except Exception as e:
            print(f"Earth Engine query failed: {e}")
            return await self._get_land_cover_fallback(latitude, longitude)

    async def _get_land_cover_fallback(
        self,
        latitude: float,
        longitude: float,
    ) -> LandCoverData:
        """
        Fallback land cover estimation using Nominatim reverse geocoding.
        Faster and more reliable than Overpass API.
        """
        try:
            # Use Nominatim for reverse geocoding (faster than Overpass)
            response = await self.client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={
                    "lat": latitude,
                    "lon": longitude,
                    "format": "json",
                    "zoom": 14,
                },
                headers={"User-Agent": "LiquefactionAlertSystem/1.0"},
                timeout=10.0,
            )

            if response.status_code == 200:
                data = response.json()
                address = data.get("address", {})

                # Determine land cover from address type
                land_type = data.get("type", "")
                category = data.get("category", "")

                # Map to land cover type
                if category == "natural":
                    land_use = land_type.replace("_", " ").title()
                elif "water" in str(address).lower():
                    land_use = "Water Body"
                elif address.get("city") or address.get("town"):
                    land_use = "Urban/Built-up"
                elif address.get("village"):
                    land_use = "Rural/Settlement"
                elif "farm" in str(address).lower():
                    land_use = "Farmland"
                else:
                    land_use = land_type.replace("_", " ").title() if land_type else "Mixed Use"

                # Map to susceptibility
                susceptibility = self._osm_susceptibility(land_use.lower())

                return LandCoverData(
                    land_cover_type=land_use,
                    forest_cover=None,
                    soil_moisture=None,
                    susceptibility_factor=susceptibility,
                )

        except Exception as e:
            print(f"Nominatim land cover query failed: {e}")

        # Return default values
        return LandCoverData(
            land_cover_type="Unknown",
            forest_cover=None,
            soil_moisture=None,
            susceptibility_factor=1.0,
        )

    async def get_soil_moisture(
        self,
        latitude: float,
        longitude: float,
    ) -> Optional[float]:
        """
        Get soil moisture data from NASA SMAP.

        Returns soil moisture index if available.
        """
        if not self.ee_initialized:
            return None

        try:
            import ee

            point = ee.Geometry.Point([longitude, latitude])

            # NASA SMAP soil moisture
            smap = (
                ee.ImageCollection("NASA/SMAP/SPL4SMGP/007")
                .filterDate("2024-01-01", "2024-12-31")
                .mean()
            )

            moisture = smap.select("sm_surface").sample(point, 9000)
            value = moisture.first().get("sm_surface").getInfo()

            return value

        except Exception:
            return None

    def _calculate_susceptibility(
        self,
        land_cover_code: int,
        forest_cover: Optional[float],
    ) -> float:
        """
        Calculate liquefaction susceptibility factor from land cover.

        Higher values indicate higher susceptibility.
        """
        # Base susceptibility by land cover type
        base_susceptibility = {
            10: 0.7,   # Tree cover - lower susceptibility
            20: 0.8,   # Shrubland
            30: 0.9,   # Grassland
            40: 1.0,   # Cropland - often on alluvial soils
            50: 1.1,   # Built-up - may have fill material
            60: 1.2,   # Bare - potentially loose soils
            70: 0.5,   # Snow/ice - not applicable
            80: 1.3,   # Water - high water table
            90: 1.4,   # Wetland - very high water table
            95: 1.3,   # Mangroves - coastal, high susceptibility
            100: 0.8,  # Moss/lichen
        }

        factor = base_susceptibility.get(land_cover_code, 1.0)

        # Adjust for forest cover (roots provide some stability)
        if forest_cover and forest_cover > 50:
            factor *= 0.9
        elif forest_cover and forest_cover > 20:
            factor *= 0.95

        return round(factor, 2)

    def _osm_susceptibility(self, landuse: str) -> float:
        """Map OSM landuse to susceptibility factor."""
        landuse_lower = landuse.lower()

        susceptibility_map = {
            "residential": 1.1,
            "commercial": 1.1,
            "industrial": 1.2,
            "farmland": 1.0,
            "forest": 0.7,
            "grass": 0.9,
            "meadow": 0.9,
            "wetland": 1.4,
            "water": 1.3,
            "water body": 1.3,
            "beach": 1.3,
            "sand": 1.2,
            "mud": 1.4,
            "marsh": 1.4,
            "quarry": 0.8,
            "landfill": 1.3,
            "urban/built-up": 1.1,
            "rural/settlement": 1.0,
            "mixed use": 1.0,
        }

        # Check for partial matches
        for key, value in susceptibility_map.items():
            if key in landuse_lower:
                return value

        return susceptibility_map.get(landuse_lower, 1.0)

    async def get_comprehensive_data(
        self,
        latitude: float,
        longitude: float,
    ) -> Dict[str, Any]:
        """
        Get all available Earth Engine data for a location.

        Returns combined land cover, soil, and environmental data.
        """
        land_cover = await self.get_land_cover(latitude, longitude)
        soil_moisture = await self.get_soil_moisture(latitude, longitude)

        return {
            "land_cover": land_cover.model_dump(),
            "soil_moisture": soil_moisture,
            "ee_available": self.ee_initialized,
        }
