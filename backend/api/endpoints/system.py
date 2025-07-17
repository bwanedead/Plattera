"""
System utilities and file serving endpoints
"""

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/serve-image")
async def serve_image(image_path: str):
    """
    Serve an image file from the local filesystem.
    
    Args:
        image_path: Path to the image file
        
    Returns:
        FileResponse with the image
    """
    try:
        # Validate the path exists and is a file
        path = Path(image_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Image not found: {image_path}")
        
        if not path.is_file():
            raise HTTPException(status_code=400, detail=f"Path is not a file: {image_path}")
        
        # Check if it's an image file (basic check)
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
        if path.suffix.lower() not in allowed_extensions:
            raise HTTPException(status_code=400, detail=f"File is not a supported image format: {path.suffix}")
        
        logger.info(f"Serving image: {image_path}")
        
        # Return the file
        return FileResponse(
            path=str(path),
            media_type=f"image/{path.suffix[1:]}",  # Remove the dot from extension
            filename=path.name
        )
        
    except Exception as e:
        logger.error(f"Error serving image {image_path}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error serving image: {str(e)}") 