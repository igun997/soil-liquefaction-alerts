"""API Routes Package."""
from .analysis import router as analysis_router
from .data import router as data_router

__all__ = ["analysis_router", "data_router"]
