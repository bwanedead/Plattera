"""
Dossier API Endpoints Module
===========================

Independent API endpoints for dossier functionality.
Provides clean separation between different dossier concerns.
"""

from .management import router as management_router
from .association import router as association_router
from .navigation import router as navigation_router
from .views import router as views_router

__all__ = [
    "management_router",
    "association_router",
    "navigation_router",
    "views_router"
]
