from fastapi import APIRouter
from .endpoints import process, export, image

router = APIRouter()

# Include endpoint routers
router.include_router(process.router, prefix="/process", tags=["processing"])
router.include_router(export.router, prefix="/export", tags=["export"])
router.include_router(image.router, tags=["image"]) 