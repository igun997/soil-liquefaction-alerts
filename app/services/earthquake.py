"""
USGS Earthquake API service.

Fetches earthquake data and calculates PGA at target locations.
"""
import math
from typing import Optional, List
from datetime import datetime, timedelta
import httpx

from config import settings
from app.models.analysis import EarthquakeData


class EarthquakeService:
    """
    Service for fetching earthquake data from USGS.

    Uses the USGS Earthquake Hazards Program API.
    https://earthquake.usgs.gov/fdsnws/event/1/
    """

    BASE_URL = settings.usgs_earthquake_base_url

    def __init__(self):
        """Initialize earthquake service."""
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    async def get_recent_earthquakes(
        self,
        latitude: float,
        longitude: float,
        max_radius_km: float = 500,
        min_magnitude: float = 4.0,
        days_back: int = 30,
        limit: int = 10,
    ) -> List[EarthquakeData]:
        """
        Fetch recent earthquakes near a location.

        Args:
            latitude: Site latitude
            longitude: Site longitude
            max_radius_km: Maximum search radius in km
            min_magnitude: Minimum earthquake magnitude
            days_back: Number of days to look back
            limit: Maximum number of earthquakes to return

        Returns:
            List of EarthquakeData sorted by proximity
        """
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days_back)

        params = {
            "format": "geojson",
            "latitude": latitude,
            "longitude": longitude,
            "maxradiuskm": max_radius_km,
            "minmagnitude": min_magnitude,
            "starttime": start_time.strftime("%Y-%m-%d"),
            "endtime": end_time.strftime("%Y-%m-%d"),
            "orderby": "magnitude",
            "limit": limit,
        }

        try:
            response = await self.client.get(
                f"{self.BASE_URL}/query",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            earthquakes = []
            for feature in data.get("features", []):
                props = feature.get("properties", {})
                coords = feature.get("geometry", {}).get("coordinates", [0, 0, 0])

                eq_lon, eq_lat, eq_depth = coords[0], coords[1], coords[2]

                # Calculate distance from site
                distance = self._haversine_distance(
                    latitude, longitude, eq_lat, eq_lon
                )

                magnitude = props.get("mag", 0)

                # Calculate PGA using attenuation relationship
                pga = self._calculate_pga(magnitude, distance, eq_depth)

                event_time = None
                if props.get("time"):
                    event_time = datetime.fromtimestamp(props["time"] / 1000)

                earthquakes.append(
                    EarthquakeData(
                        magnitude=magnitude,
                        depth=eq_depth,
                        distance=distance,
                        pga=pga,
                        event_id=feature.get("id"),
                        event_time=event_time,
                        location=props.get("place", "Unknown"),
                    )
                )

            # Sort by PGA (highest first)
            earthquakes.sort(key=lambda x: x.pga, reverse=True)
            return earthquakes

        except Exception as e:
            print(f"Error fetching earthquakes: {e}")
            return []

    async def get_significant_earthquake(
        self,
        latitude: float,
        longitude: float,
        max_radius_km: float = 500,
    ) -> Optional[EarthquakeData]:
        """
        Get the most significant recent earthquake for analysis.

        Returns earthquake with highest PGA at site location.
        """
        earthquakes = await self.get_recent_earthquakes(
            latitude=latitude,
            longitude=longitude,
            max_radius_km=max_radius_km,
            min_magnitude=4.0,
            days_back=365,  # Look back 1 year
            limit=50,
        )

        if earthquakes:
            return earthquakes[0]  # Already sorted by PGA
        return None

    def _haversine_distance(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """
        Calculate distance between two points using Haversine formula.

        Returns distance in kilometers.
        """
        R = 6371  # Earth's radius in km

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1_rad)
            * math.cos(lat2_rad)
            * math.sin(delta_lon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def _calculate_pga(
        self,
        magnitude: float,
        distance_km: float,
        depth_km: float,
    ) -> float:
        """
        Estimate Peak Ground Acceleration using simplified attenuation.

        Uses simplified form of Boore-Atkinson (2008) GMPE.
        This is an approximation - for critical applications use
        full GMPE with site-specific parameters.

        Args:
            magnitude: Earthquake magnitude
            distance_km: Epicentral distance (km)
            depth_km: Focal depth (km)

        Returns:
            PGA in g (gravity units)
        """
        # Hypocentral distance
        r_hyp = math.sqrt(distance_km ** 2 + depth_km ** 2)

        # Simplified attenuation (approximation of Boore-Atkinson 2008)
        # ln(PGA) = c1 + c2*(M-6) + c3*(M-6)^2 + c4*ln(R) + c5*R

        # Coefficients (simplified/approximate)
        c1 = -0.5  # Baseline
        c2 = 0.9   # Magnitude scaling
        c3 = -0.1  # Magnitude saturation
        c4 = -1.3  # Geometric spreading
        c5 = -0.003  # Anelastic attenuation

        # Effective distance (with near-source saturation)
        r_eff = math.sqrt(r_hyp ** 2 + 10 ** 2)

        ln_pga = (
            c1
            + c2 * (magnitude - 6)
            + c3 * (magnitude - 6) ** 2
            + c4 * math.log(r_eff)
            + c5 * r_eff
        )

        pga = math.exp(ln_pga)

        # Convert from cm/s² to g (if needed) and cap at reasonable values
        # Note: This simplified model already gives approximate g values
        return min(max(pga, 0.01), 2.0)

    async def get_design_pga(
        self,
        latitude: float,
        longitude: float,
        return_period: int = 475,
    ) -> float:
        """
        Get design PGA for a location based on seismic hazard.

        This is a simplified estimation. For actual design, use
        official seismic hazard maps (e.g., USGS NSHM).

        Args:
            latitude: Site latitude
            longitude: Site longitude
            return_period: Return period in years (default 475 for 10% in 50 years)

        Returns:
            Design PGA in g
        """
        # Fetch historical significant earthquakes
        earthquakes = await self.get_recent_earthquakes(
            latitude=latitude,
            longitude=longitude,
            max_radius_km=500,
            min_magnitude=5.0,
            days_back=3650,  # 10 years
            limit=100,
        )

        if not earthquakes:
            return 0.1  # Default low seismicity value

        # Use maximum observed PGA as baseline
        max_pga = max(eq.pga for eq in earthquakes)

        # Apply simple scaling for return period
        # (This is a rough approximation)
        if return_period >= 2475:  # 2% in 50 years
            scale = 1.5
        elif return_period >= 475:  # 10% in 50 years
            scale = 1.0
        else:
            scale = 0.7

        return min(max_pga * scale, 1.5)
