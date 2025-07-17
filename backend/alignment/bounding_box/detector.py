"""
Word-level bounding box detection using OpenCV.

This module provides functionality to detect word-like regions in scanned document images
and return their bounding boxes in reading order.
"""

import cv2
import numpy as np
from typing import List, Dict, Any, Tuple
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def detect_word_bounding_boxes(image_path: str) -> List[Dict[str, Any]]:
    """
    Detect bounding boxes around word-like regions in a scanned document image.
    
    Args:
        image_path: Path to the input image file
        
    Returns:
        List of dictionaries with format:
        [
            {"bbox": [x1, y1, x2, y2], "index": 0},
            {"bbox": [x1, y1, x2, y2], "index": 1},
            ...
        ]
        Sorted in reading order (top-to-bottom, left-to-right)
        
    Raises:
        FileNotFoundError: If image file doesn't exist
        cv2.error: If image cannot be processed
    """
    if not Path(image_path).exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    
    try:
        # Load and preprocess the image
        image = cv2.imread(image_path)
        if image is None:
            raise cv2.error(f"Could not load image: {image_path}")
            
        preprocessed = _preprocess_image(image)
        
        # Detect contours
        contours = _detect_contours(preprocessed)
        
        # Filter and convert to bounding boxes
        bounding_boxes = _filter_and_extract_bboxes(contours, image.shape)
        
        # Sort in reading order and add indices
        sorted_boxes = _sort_reading_order(bounding_boxes)
        
        logger.info(f"Detected {len(sorted_boxes)} word-level bounding boxes in {image_path}")
        return sorted_boxes
        
    except Exception as e:
        logger.error(f"Error processing image {image_path}: {str(e)}")
        raise


def _preprocess_image(image: np.ndarray) -> np.ndarray:
    """
    Preprocess the image for optimal contour detection.
    
    Args:
        image: Input BGR image
        
    Returns:
        Binary image ready for contour detection
    """
    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Apply adaptive thresholding for better handling of varying lighting
    binary = cv2.adaptiveThreshold(
        gray, 
        255, 
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY_INV, 
        11, 
        2
    )
    
    # Optional: Dilate to merge close characters into word blobs
    # This helps group individual characters into word-level regions
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 1))
    dilated = cv2.dilate(binary, kernel, iterations=2)
    
    return dilated


def _detect_contours(binary_image: np.ndarray) -> List[np.ndarray]:
    """
    Detect contours in the preprocessed binary image.
    
    Args:
        binary_image: Binary image with text regions in white
        
    Returns:
        List of contours representing potential word regions
    """
    contours, _ = cv2.findContours(
        binary_image, 
        cv2.RETR_EXTERNAL, 
        cv2.CHAIN_APPROX_SIMPLE
    )
    
    return contours


def _filter_and_extract_bboxes(
    contours: List[np.ndarray], 
    image_shape: Tuple[int, int, int]
) -> List[Dict[str, Any]]:
    """
    Filter noise contours and extract bounding boxes.
    
    Args:
        contours: List of detected contours
        image_shape: Shape of the original image (height, width, channels)
        
    Returns:
        List of valid bounding boxes as dictionaries
    """
    height, width = image_shape[:2]
    valid_boxes = []
    
    # Minimum size thresholds to filter out noise
    min_width = max(10, width * 0.01)  # At least 1% of image width or 10px
    min_height = max(8, height * 0.005)  # At least 0.5% of image height or 8px
    min_area = min_width * min_height
    
    for contour in contours:
        # Get bounding rectangle
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        
        # Filter out noise based on size
        if w >= min_width and h >= min_height and area >= min_area:
            # Convert to [x1, y1, x2, y2] format
            bbox = [x, y, x + w, y + h]
            valid_boxes.append({"bbox": bbox})
    
    return valid_boxes


def _sort_reading_order(bounding_boxes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sort bounding boxes in reading order (top-to-bottom, left-to-right).
    
    Args:
        bounding_boxes: List of bounding box dictionaries
        
    Returns:
        Sorted list with added index field
    """
    # Sort by top-left corner: first by y-coordinate (top), then by x-coordinate (left)
    # Use a small tolerance for y-coordinate to group boxes on the same line
    def sort_key(box):
        x1, y1, x2, y2 = box["bbox"]
        # Group boxes on the same line with tolerance
        line_tolerance = abs(y2 - y1) * 0.5  # Half the height as tolerance
        line_group = int(y1 / line_tolerance)
        return (line_group, x1)
    
    sorted_boxes = sorted(bounding_boxes, key=sort_key)
    
    # Add index field
    for i, box in enumerate(sorted_boxes):
        box["index"] = i
    
    return sorted_boxes


def get_detection_stats(bounding_boxes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate statistics about the detected bounding boxes.
    
    Args:
        bounding_boxes: List of detected bounding boxes
        
    Returns:
        Dictionary with detection statistics
    """
    if not bounding_boxes:
        return {
            "total_boxes": 0,
            "avg_width": 0,
            "avg_height": 0,
            "avg_area": 0
        }
    
    widths = []
    heights = []
    areas = []
    
    for box in bounding_boxes:
        x1, y1, x2, y2 = box["bbox"]
        width = x2 - x1
        height = y2 - y1
        area = width * height
        
        widths.append(width)
        heights.append(height)
        areas.append(area)
    
    return {
        "total_boxes": len(bounding_boxes),
        "avg_width": np.mean(widths),
        "avg_height": np.mean(heights),
        "avg_area": np.mean(areas),
        "min_width": min(widths),
        "max_width": max(widths),
        "min_height": min(heights),
        "max_height": max(heights)
    } 