"""
Bounding Box Detection Module
============================

This module provides OpenCV-based word-level bounding box detection for scanned
document images. It's designed to work alongside the alignment system to provide
spatial information about detected text regions.

Main Components:
- detector: Core OpenCV detection logic
- async_utils: Async wrappers for non-blocking integration

Usage:
    from backend.alignment.bounding_box import detect_word_bounding_boxes_async
    
    # Async detection (recommended for API endpoints)
    boxes = await detect_word_bounding_boxes_async("path/to/image.jpg")
    
    # Sync detection
    from backend.alignment.bounding_box.detector import detect_word_bounding_boxes
    boxes = detect_word_bounding_boxes("path/to/image.jpg")
"""

from .detector import (
    detect_word_bounding_boxes,
    get_detection_stats
)

from .async_utils import (
    detect_word_bounding_boxes_async,
    detect_with_stats_async,
    cleanup_thread_pool,
    BoundingBoxDetectionTask
)

__all__ = [
    # Core detection
    "detect_word_bounding_boxes",
    "get_detection_stats",
    
    # Async utilities
    "detect_word_bounding_boxes_async", 
    "detect_with_stats_async",
    "cleanup_thread_pool",
    "BoundingBoxDetectionTask"
] 