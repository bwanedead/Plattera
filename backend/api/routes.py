from fastapi import APIRouter
from .endpoints import process, export

router = APIRouter()

# Include endpoint routers
router.include_router(process.router, prefix="/process", tags=["processing"])
router.include_router(export.router, prefix="/export", tags=["export"]) 