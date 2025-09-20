"""
Dossier API Endpoints Module
===========================

Independent API endpoints for dossier functionality.
Provides clean separation between different dossier concerns.
"""

from .dossier_management import router as management_router
from .dossier_association import router as association_router
from .dossier_navigation import router as navigation_router
from .dossier_views import router as views_router
from .dossier_image_processing import router as dossier_image_processing_router
from .dossier_run_initialization import router as runs_router

__all__ = [
    "management_router",
    "association_router",
    "navigation_router",
    "views_router",
    "dossier_image_processing_router",
    "runs_router"
]
