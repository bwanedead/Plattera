"""
Async utilities for bounding box detection.

Provides async wrappers and task management for non-blocking bounding box detection
that can be integrated with FastAPI endpoints.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from .detector import detect_word_bounding_boxes, get_detection_stats

logger = logging.getLogger(__name__)

# Thread pool for CPU-intensive OpenCV operations
_thread_pool: Optional[ThreadPoolExecutor] = None


def get_thread_pool() -> ThreadPoolExecutor:
    """Get or create the shared thread pool for OpenCV operations."""
    global _thread_pool
    if _thread_pool is None:
        _thread_pool = ThreadPoolExecutor(
            max_workers=2,  # Limit concurrent OpenCV operations
            thread_name_prefix="bbox_detector"
        )
    return _thread_pool


async def detect_word_bounding_boxes_async(image_path: str) -> List[Dict[str, Any]]:
    """
    Async wrapper for detect_word_bounding_boxes.
    
    Runs the CPU-intensive OpenCV detection in a thread pool to avoid
    blocking the event loop.
    
    Args:
        image_path: Path to the input image file
        
    Returns:
        List of bounding box dictionaries with indices
        
    Raises:
        Same exceptions as detect_word_bounding_boxes
    """
    loop = asyncio.get_event_loop()
    
    try:
        logger.info(f"📦 BBOX ASYNC ► Starting thread pool execution for {image_path}")
        
        # Run the detection in a thread pool
        result = await loop.run_in_executor(
            get_thread_pool(),
            detect_word_bounding_boxes,
            image_path
        )
        
        logger.info(f"📦 BBOX ASYNC ► Detection completed successfully for {image_path} - Found {len(result)} boxes")
        return result
        
    except Exception as e:
        logger.error(f"📦 BBOX ASYNC ► Detection FAILED for {image_path}: {str(e)}")
        logger.exception("Full async detection traceback:")
        raise


async def detect_with_stats_async(image_path: str) -> Dict[str, Any]:
    """
    Detect bounding boxes and calculate statistics asynchronously.
    
    Args:
        image_path: Path to the input image file
        
    Returns:
        Dictionary containing both bounding boxes and statistics:
        {
            "bounding_boxes": [...],
            "stats": {...}
        }
    """
    loop = asyncio.get_event_loop()
    
    def detect_and_analyze():
        logger.info(f"📦 BBOX THREAD ► Starting detection in thread pool for {image_path}")
        try:
            # First check if we can import cv2
            try:
                import cv2
                logger.info(f"📦 BBOX THREAD ► OpenCV version: {cv2.__version__}")
            except ImportError as e:
                logger.error(f"📦 BBOX THREAD ► OpenCV import failed: {e}")
                raise
            
            bounding_boxes = detect_word_bounding_boxes(image_path)
            logger.info(f"📦 BBOX THREAD ► Detection successful, found {len(bounding_boxes)} boxes")
            
            stats = get_detection_stats(bounding_boxes)
            logger.info(f"📦 BBOX THREAD ► Stats calculation complete")
            
            result = {
                "bounding_boxes": bounding_boxes,
                "stats": stats
            }
            logger.info(f"📦 BBOX THREAD ► Returning result with {len(bounding_boxes)} boxes")
            return result
        except Exception as e:
            logger.error(f"📦 BBOX THREAD ► Error in thread execution: {str(e)}")
            logger.exception("Full thread execution traceback:")
            raise
    
    try:
        logger.info(f"📦 BBOX STATS ASYNC ► Starting detection with stats for {image_path}")
        
        result = await loop.run_in_executor(
            get_thread_pool(),
            detect_and_analyze
        )
        
        logger.info(f"📦 BBOX STATS ASYNC ► Detection with stats completed successfully for {image_path}")
        return result
        
    except Exception as e:
        logger.error(f"📦 BBOX STATS ASYNC ► Detection with stats FAILED for {image_path}: {str(e)}")
        logger.exception("Full async detection with stats traceback:")
        raise


async def cleanup_thread_pool():
    """
    Clean up the thread pool resources.
    
    Should be called when shutting down the application.
    """
    global _thread_pool
    if _thread_pool is not None:
        _thread_pool.shutdown(wait=True)
        _thread_pool = None
        logger.info("Bounding box detection thread pool cleaned up")


class BoundingBoxDetectionTask:
    """
    Manages a bounding box detection task with cancellation support.
    """
    
    def __init__(self, image_path: str):
        self.image_path = image_path
        self.task: Optional[asyncio.Task] = None
        self._result: Optional[List[Dict[str, Any]]] = None
        
    async def start(self) -> None:
        """Start the detection task."""
        if self.task is not None:
            raise RuntimeError("Task already started")
            
        self.task = asyncio.create_task(
            detect_word_bounding_boxes_async(self.image_path)
        )
        
    async def wait(self) -> List[Dict[str, Any]]:
        """Wait for the task to complete and return the result."""
        if self.task is None:
            raise RuntimeError("Task not started")
            
        if self._result is None:
            self._result = await self.task
            
        return self._result
    
    def cancel(self) -> bool:
        """Cancel the detection task."""
        if self.task is None:
            return False
            
        return self.task.cancel()
    
    @property
    def is_done(self) -> bool:
        """Check if the task is completed."""
        return self.task is not None and self.task.done()
    
    @property
    def is_cancelled(self) -> bool:
        """Check if the task was cancelled."""
        return self.task is not None and self.task.cancelled() 