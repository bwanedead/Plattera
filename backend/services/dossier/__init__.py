"""
Dossier Services Module
======================

Modular services for dossier management functionality.
Provides clean separation between different dossier-related concerns.
"""

from .management_service import DossierManagementService
from .association_service import TranscriptionAssociationService
from .navigation_service import DossierNavigationService
from .view_service import DossierViewService

__all__ = [
    "DossierManagementService",
    "TranscriptionAssociationService",
    "DossierNavigationService",
    "DossierViewService"
]
