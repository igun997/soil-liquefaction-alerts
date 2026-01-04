"""
OpenWeatherMap API service.

Fetches weather and precipitation data for groundwater estimation.
"""
from typing import Optional
import httpx

from config import settings
from app.models.analysis import WeatherData


class WeatherService:
    """
    Service for fetching weather data from OpenWeatherMap.

    Uses current weather and precipitation data to estimate
    groundwater conditions.
    """

    BASE_URL = settings.openweathermap_base_url
    API_KEY = settings.openweathermap_api_key

    def __init__(self):
        """Initialize weather service."""
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    async def get_current_weather(
        self,
        latitude: float,
        longitude: float,
    ) -> Optional[WeatherData]:
        """
        Fetch current weather data for a location.

        Args:
            latitude: Site latitude
            longitude: Site longitude

        Returns:
            WeatherData with current conditions
        """
        params = {
            "lat": latitude,
            "lon": longitude,
            "appid": self.API_KEY,
            "units": "metric",
        }

        try:
            response = await self.client.get(
                f"{self.BASE_URL}/weather",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            # Extract weather data
            main = data.get("main", {})
            rain = data.get("rain", {})

            precipitation_1h = rain.get("1h", 0)
            precipitation_3h = rain.get("3h", 0)

            # Estimate 24h precipitation (rough approximation from 3h data)
            precipitation_24h = precipitation_3h * 8 if precipitation_3h else 0

            # Calculate groundwater adjustment factor
            # Higher precipitation = higher groundwater = lower effective stress
            groundwater_factor = self._calculate_groundwater_factor(
                precipitation_24h,
                main.get("humidity", 50),
            )

            return WeatherData(
                temperature=main.get("temp"),
                humidity=main.get("humidity"),
                precipitation_1h=precipitation_1h,
                precipitation_24h=precipitation_24h,
                groundwater_factor=groundwater_factor,
            )

        except Exception as e:
            print(f"Error fetching weather: {e}")
            return None

    async def get_precipitation_history(
        self,
        latitude: float,
        longitude: float,
        days: int = 7,
    ) -> float:
        """
        Get cumulative precipitation over recent days.

        Note: Requires OpenWeatherMap One Call API (paid tier for history).
        This is a simplified version using current data.

        Returns:
            Estimated cumulative precipitation (mm)
        """
        weather = await self.get_current_weather(latitude, longitude)
        if weather and weather.precipitation_24h:
            # Rough estimation based on current rate
            return weather.precipitation_24h * (days / 1)
        return 0

    def _calculate_groundwater_factor(
        self,
        precipitation_24h: float,
        humidity: float,
    ) -> float:
        """
        Calculate groundwater adjustment factor based on weather.

        This factor adjusts the assumed groundwater depth based on
        recent precipitation and humidity.

        Factor > 1.0: Groundwater likely higher (wetter conditions)
        Factor < 1.0: Groundwater likely lower (drier conditions)

        Args:
            precipitation_24h: 24-hour precipitation (mm)
            humidity: Relative humidity (%)

        Returns:
            Groundwater adjustment factor (0.5 - 2.0)
        """
        # Base factor from precipitation
        if precipitation_24h > 50:
            precip_factor = 1.5
        elif precipitation_24h > 20:
            precip_factor = 1.3
        elif precipitation_24h > 5:
            precip_factor = 1.1
        elif precipitation_24h > 0:
            precip_factor = 1.0
        else:
            precip_factor = 0.9

        # Humidity adjustment
        if humidity > 80:
            humid_factor = 1.1
        elif humidity > 60:
            humid_factor = 1.0
        elif humidity > 40:
            humid_factor = 0.95
        else:
            humid_factor = 0.9

        # Combined factor
        factor = precip_factor * humid_factor

        # Clamp to reasonable range
        return max(0.5, min(factor, 2.0))

    def estimate_gwt_adjustment(
        self,
        base_gwt: float,
        groundwater_factor: float,
    ) -> float:
        """
        Estimate adjusted groundwater table depth.

        Args:
            base_gwt: Base groundwater depth (m)
            groundwater_factor: Factor from weather analysis

        Returns:
            Adjusted groundwater depth (m)
        """
        # Higher factor = higher water table = lower depth
        adjusted_gwt = base_gwt / groundwater_factor

        # Don't let it go below surface or too deep
        return max(0.5, min(adjusted_gwt, base_gwt * 2))
