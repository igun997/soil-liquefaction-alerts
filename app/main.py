"""
Liquefaction Alert Detection System - Main Application.

A FastAPI web application for soil liquefaction risk assessment using:
- Boulanger & Idriss (2014) simplified procedure
- USGS Earthquake data
- OpenWeatherMap weather data
- OpenTopography elevation data
- Google Earth Engine land cover data
"""
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from config import settings
from app.routes import analysis_router, data_router

# Application info
APP_TITLE = "Liquefaction Alert Detection System"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = """
## Soil Liquefaction Risk Assessment Tool

This application evaluates the potential for earthquake-induced soil liquefaction
using the **Boulanger & Idriss (2014)** simplified procedure.

### Features
- **SPT and CPT Analysis**: Supports both Standard Penetration Test and
  Cone Penetration Test data
- **Real-time Earthquake Data**: Fetches recent earthquakes from USGS
- **Weather Integration**: Considers precipitation for groundwater estimation
- **Terrain Analysis**: Uses elevation and land cover data for susceptibility

### Methodology
The analysis calculates the **Factor of Safety (FS)** against liquefaction:
- FS < 1.0: Liquefaction likely
- FS >= 1.0: Liquefaction unlikely

### References
- Boulanger, R.W. & Idriss, I.M. (2014). CPT and SPT based liquefaction
  triggering procedures. Report No. UCD/CGM-14/01
"""

# Create FastAPI app
app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files and templates
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Include routers
app.include_router(analysis_router)
app.include_router(data_router)


@app.get("/", include_in_schema=False)
async def home(request: Request):
    """Serve the main dashboard page."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": APP_TITLE,
            "version": APP_VERSION,
        },
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": APP_TITLE,
        "version": APP_VERSION,
    }


@app.get("/api/info")
async def api_info():
    """Get API information and available endpoints."""
    return {
        "app": APP_TITLE,
        "version": APP_VERSION,
        "methodology": "Boulanger & Idriss (2014)",
        "endpoints": {
            "analysis": {
                "quick": "/api/analyze/quick - Quick screening analysis",
                "full": "/api/analyze/full - Comprehensive analysis",
            },
            "data": {
                "earthquakes": "/api/earthquakes - Recent earthquakes",
                "weather": "/api/weather - Current weather",
                "elevation": "/api/elevation - Point elevation",
                "terrain": "/api/terrain - Terrain characteristics",
                "landcover": "/api/landcover - Land cover classification",
                "site_data": "/api/site-data - All site data combined",
            },
        },
        "references": [
            "Boulanger & Idriss (2014) - CPT and SPT based liquefaction procedures",
            "Seed & Idriss (1971) - Simplified procedure for evaluating liquefaction",
            "Youd et al. (2001) - NCEER Workshop summary",
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
