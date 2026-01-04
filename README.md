# Soil Liquefaction Alert Detection System

A real-time soil liquefaction risk assessment platform that combines live earthquake data, weather conditions, and terrain analysis to evaluate liquefaction hazards for any location worldwide.

**Live Demo:** https://soil-liquefaction-alerts.onrender.com

## The Problem It Solves

### Why This Matters

Soil liquefaction is a devastating phenomenon where saturated soil loses its strength during earthquake shaking, causing the ground to behave like a liquid. This can lead to:

- **Building collapse and foundation failures** - structures sink or tilt as the ground loses bearing capacity
- **Infrastructure damage** - roads crack, pipelines rupture, bridges fail
- **Loss of life** - particularly in densely populated areas with poor soil conditions
- **Massive economic losses** - billions of dollars in damage from a single event

Historical disasters like the 1964 Niigata earthquake (Japan), 1999 Chi-Chi earthquake (Taiwan), and 2011 Christchurch earthquake (New Zealand) caused catastrophic liquefaction damage that could have been mitigated with proper risk assessment.

### How This System Helps

1. **Democratizes Access to Geotechnical Analysis**
   - Professional liquefaction assessments typically cost $10,000-$50,000+ and require specialized consultants
   - This tool provides instant preliminary risk screening for any location worldwide at no cost
   - Empowers engineers, urban planners, and property developers to make informed decisions

2. **Real-Time Risk Awareness**
   - Fetches live earthquake data from USGS to show recent seismic activity
   - Integrates current weather and groundwater conditions that affect liquefaction susceptibility
   - Provides actionable alerts when conditions indicate elevated risk

3. **Scientific Rigor with Accessibility**
   - Implements the industry-standard **Boulanger & Idriss (2014)** methodology used by professional geotechnical engineers
   - Supports both SPT (Standard Penetration Test) and CPT (Cone Penetration Test) based analysis
   - Calculates Liquefaction Potential Index (LPI) for comprehensive site assessment

4. **Multi-Source Data Integration**
   - **USGS Earthquake API** - Real-time seismic event monitoring
   - **OpenTopography** - High-resolution terrain and elevation data
   - **OpenWeatherMap** - Current weather conditions affecting soil saturation
   - **Google Earth Engine** - Land cover classification for soil type estimation

### Use Cases

- **Construction Planning**: Assess liquefaction risk before purchasing land or designing foundations
- **Urban Development**: Identify high-risk zones for zoning regulations and building codes
- **Emergency Preparedness**: Understand which areas are most vulnerable during earthquakes
- **Insurance Assessment**: Evaluate seismic risk for property underwriting
- **Educational Tool**: Learn about liquefaction mechanics and geotechnical engineering principles

---

## Challenges I Ran Into

### 1. Complex Geotechnical Calculations

**The Problem:**
Implementing the Boulanger & Idriss (2014) simplified procedure required understanding deeply nested geotechnical formulas with multiple correction factors (CN, CE, CB, CR, CS for SPT; stress-dependent normalization for CPT).

**How I Solved It:**
- Studied the original research papers and EERI monographs thoroughly
- Broke down the calculation into discrete, testable functions (`calculate_rd`, `calculate_csr`, `calculate_msf`, `calculate_k_sigma`)
- Created dataclasses (`StressState`, `LayerResult`) to track intermediate values through the calculation chain
- Implemented comprehensive docstrings referencing specific equations from the literature

```python
# Example: The CRR calculation follows Equation 4 from Boulanger & Idriss (2014)
crr = math.exp(
    n / 14.1
    + (n / 126) ** 2
    - (n / 23.6) ** 3
    + (n / 25.4) ** 4
    - 2.8
)
```

### 2. Integrating Multiple External APIs

**The Problem:**
The system needs to fetch data from 4+ external services (USGS, OpenTopography, OpenWeatherMap, Earth Engine), each with different authentication methods, rate limits, and response formats.

**How I Solved It:**
- Created dedicated service classes for each API with consistent interfaces
- Implemented async HTTP clients using `httpx` and `aiohttp` for non-blocking requests
- Added robust error handling with graceful fallbacks when services are unavailable
- Used Pydantic models to validate and normalize responses from different APIs

### 3. Handling Missing or Incomplete Data

**The Problem:**
Real-world analysis often lacks complete soil profile data. Users may only have partial SPT/CPT data, unknown groundwater depth, or estimated soil properties.

**How I Solved It:**
- Implemented sensible defaults based on typical soil conditions
- Created "quick analysis" mode that estimates soil parameters from terrain and land cover data
- Used the Soil Behavior Type Index (Ic) from CPT to estimate fines content when lab data is unavailable
- Added clear documentation about assumptions and limitations in the response

### 4. Stress Integration Through Depth

**The Problem:**
Calculating effective stress requires integrating unit weight through varying soil layers, accounting for the groundwater table position.

**How I Solved It:**
- Implemented numerical integration using small depth steps (0.1m)
- Created a flexible `SoilProfile` class that can interpolate properties between defined layers
- Properly handled the transition at the groundwater table where buoyant unit weight applies

```python
while z < depth:
    step = min(dz, depth - z)
    unit_weight = profile.get_unit_weight_at_depth(z)
    sigma_v += unit_weight * step

    if z >= gwt:
        sigma_v_eff += (unit_weight - self.WATER_UNIT_WEIGHT) * step
    else:
        sigma_v_eff += unit_weight * step
    z += step
```

### 5. Earth Engine Authentication in Serverless Environment

**The Problem:**
Google Earth Engine requires OAuth authentication, which is challenging in a serverless/containerized deployment where you can't run interactive browser authentication.

**How I Solved It:**
- Made Earth Engine integration optional - the system works without it
- Supported service account authentication via `EE_SERVICE_ACCOUNT_KEY` environment variable
- Provided fallback to simpler elevation/terrain APIs when Earth Engine is unavailable
- Documented the setup process for users who need full functionality

---

## Features

- **Real-time earthquake monitoring** from USGS
- **Interactive web dashboard** with map visualization
- **SPT and CPT analysis** following international standards
- **Liquefaction Potential Index (LPI)** calculation
- **Weather integration** for current conditions
- **Terrain analysis** including elevation and slope
- **Risk level classification** with actionable recommendations

## Tech Stack

- **Backend:** Python 3.12, FastAPI, Uvicorn
- **Frontend:** Jinja2 templates, Leaflet.js for maps
- **Data Processing:** NumPy, Pandas, SciPy
- **Geospatial:** Folium, Shapely, Rasterio
- **External APIs:** USGS, OpenTopography, OpenWeatherMap, Google Earth Engine

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web dashboard |
| `/health` | GET | Health check |
| `/api/analyze/quick` | POST | Quick liquefaction analysis |
| `/api/analyze/full` | POST | Comprehensive analysis with soil data |
| `/api/earthquakes` | GET | Recent earthquakes |
| `/api/weather` | GET | Current weather for location |
| `/api/elevation` | GET | Point elevation data |
| `/api/terrain` | GET | Terrain characteristics |

## Local Development

```bash
# Clone the repository
git clone https://github.com/igun997/soil-liquefaction-alerts.git
cd soil-liquefaction-alerts

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your API keys

# Run the application
python run.py
```

The application will be available at `http://localhost:8000`

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DEBUG` | Enable debug mode | No |
| `OPENTOPOGRAPHY_API_KEY` | OpenTopography API key | Yes |
| `OPENWEATHERMAP_API_KEY` | OpenWeatherMap API key | Yes |
| `EE_SERVICE_ACCOUNT_KEY` | Google Earth Engine service account JSON path | No |
| `EE_PROJECT` | Google Cloud Project ID for Earth Engine | No |

## References

- Boulanger, R.W. & Idriss, I.M. (2014). "CPT and SPT based liquefaction triggering procedures." Report No. UCD/CGM-14/01
- Idriss, I.M. & Boulanger, R.W. (2008). "Soil liquefaction during earthquakes." EERI Monograph MNO-12
- Iwasaki, T. et al. (1982). "A practical method for assessing soil liquefaction potential based on case studies at various sites in Japan."

## License

MIT License
