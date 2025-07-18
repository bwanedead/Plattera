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


def detect_word_bounding_boxes(image_path: str, debug_mode: bool = False) -> List[Dict[str, Any]]:
    """
    Detect bounding boxes using character detection + intelligent grouping.
    Works from the clean preprocessed stage without destructive dilation.
    """
    if not Path(image_path).exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    
    try:
        # Load and preprocess (same as before through Stage 5)
        image = cv2.imread(image_path)
        if image is None:
            raise cv2.error(f"Could not load image: {image_path}")
            
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Multiple thresholding approaches
        _, thresh_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        fg_otsu = 255 - thresh_otsu
        
        thresh_adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                               cv2.THRESH_BINARY, 21, 5)
        fg_adaptive = 255 - thresh_adaptive
        
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray_eq = clahe.apply(gray)
        _, thresh_clahe = cv2.threshold(gray_eq, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        fg_clahe = 255 - thresh_clahe
        
        # Choose best method
        otsu_density = np.sum(fg_otsu > 0) / fg_otsu.size
        adaptive_density = np.sum(fg_adaptive > 0) / fg_adaptive.size
        clahe_density = np.sum(fg_clahe > 0) / fg_clahe.size
        
        logger.info(f"Thresholding densities - Otsu: {otsu_density:.3f}, Adaptive: {adaptive_density:.3f}, CLAHE: {clahe_density:.3f}")
        
        if 0.05 <= otsu_density <= 0.25:
            fg = fg_otsu
            method = "Otsu"
        elif 0.05 <= adaptive_density <= 0.25:
            fg = fg_adaptive
            method = "Adaptive"
        elif 0.05 <= clahe_density <= 0.25:
            fg = fg_clahe
            method = "CLAHE+Otsu"
        else:
            target = 0.15
            distances = [abs(otsu_density - target), abs(adaptive_density - target), abs(clahe_density - target)]
            best_idx = distances.index(min(distances))
            if best_idx == 0:
                fg = fg_otsu
                method = "Otsu (fallback)"
            elif best_idx == 1:
                fg = fg_adaptive
                method = "Adaptive (fallback)"
            else:
                fg = fg_clahe
                method = "CLAHE+Otsu (fallback)"
        
        logger.info(f"Selected thresholding method: {method}")
        
        # Light cleanup to get to Stage 5 quality
        kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
        fg_clean = cv2.morphologyEx(fg, cv2.MORPH_OPEN, kernel_small, iterations=1)
        
        if debug_mode:
            cv2.imwrite("debug_0_original_gray.png", gray)
            cv2.imwrite("debug_1_selected_fg.png", fg)
            cv2.imwrite("debug_2_cleaned_stage5.png", fg_clean)
        
        # STOP HERE - Use Stage 5 for bounding box detection
        
        # Find individual character/stroke components
        n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(fg_clean, connectivity=8)
        
        if n_labels <= 1:
            logger.info("No text components found")
            return []
        
        logger.info(f"Found {n_labels-1} character/stroke components at Stage 5")
        
        # Extract character bounding boxes
        char_boxes = []
        for i in range(1, n_labels):
            x, y, w, h, area = stats[i]
            
            # Filter for reasonable character/stroke size
            if (h >= 5 and w >= 2 and  # Minimum readable size
                h <= 80 and w <= 200 and  # Maximum reasonable size
                area >= 10):  # Minimum area
                char_boxes.append({
                    'x': x, 'y': y, 'w': w, 'h': h,
                    'x2': x + w, 'y2': y + h,
                    'area': area,
                    'center_x': x + w/2,
                    'center_y': y + h/2
                })
        
        logger.info(f"Found {len(char_boxes)} valid character components")
        
        if not char_boxes:
            return []
        
        # Estimate character dimensions for grouping
        heights = [box['h'] for box in char_boxes]
        median_char_height = np.median(heights)
        
        # Group characters into lines
        line_tolerance = median_char_height * 0.6  # Characters on same line
        lines = {}
        
        for box in char_boxes:
            line_id = int(box['center_y'] / line_tolerance)
            if line_id not in lines:
                lines[line_id] = []
            lines[line_id].append(box)
        
        logger.info(f"Grouped characters into {len(lines)} lines")
        
        # Group characters into words within each line
        word_boxes = []
        
        for line_id in sorted(lines.keys()):
            line_chars = sorted(lines[line_id], key=lambda b: b['x'])
            
            if not line_chars:
                continue
            
            # Estimate word spacing for this line
            if len(line_chars) > 1:
                gaps = []
                for i in range(len(line_chars) - 1):
                    gap = line_chars[i+1]['x'] - line_chars[i]['x2']
                    if gap > 0:
                        gaps.append(gap)
                
                if gaps:
                    # Use larger gaps as word boundaries
                    median_gap = np.median(gaps)
                    word_gap_threshold = max(median_gap * 1.5, median_char_height * 0.8)
                else:
                    word_gap_threshold = median_char_height * 0.8
            else:
                word_gap_threshold = median_char_height * 0.8
            
            # Group characters into words
            current_word = [line_chars[0]]
            
            for i in range(1, len(line_chars)):
                gap = line_chars[i]['x'] - line_chars[i-1]['x2']
                
                if gap <= word_gap_threshold:
                    # Same word
                    current_word.append(line_chars[i])
                else:
                    # New word - save current and start new
                    if len(current_word) > 0:
                        # Create word bounding box
                        min_x = min(c['x'] for c in current_word)
                        min_y = min(c['y'] for c in current_word)
                        max_x = max(c['x2'] for c in current_word)
                        max_y = max(c['y2'] for c in current_word)
                        
                        # Only keep word-like shapes
                        word_w = max_x - min_x
                        word_h = max_y - min_y
                        
                        if (word_w >= median_char_height * 0.5 and  # Minimum word width
                            word_h >= 5 and  # Minimum height
                            word_w > word_h * 0.8):  # Word-like aspect ratio
                            word_boxes.append([min_x, min_y, max_x, max_y])
                    
                    current_word = [line_chars[i]]
            
            # Don't forget the last word
            if len(current_word) > 0:
                min_x = min(c['x'] for c in current_word)
                min_y = min(c['y'] for c in current_word)
                max_x = max(c['x2'] for c in current_word)
                max_y = max(c['y2'] for c in current_word)
                
                word_w = max_x - min_x
                word_h = max_y - min_y
                
                if (word_w >= median_char_height * 0.5 and
                    word_h >= 5 and
                    word_w > word_h * 0.8):
                    word_boxes.append([min_x, min_y, max_x, max_y])
        
        logger.info(f"Formed {len(word_boxes)} word groups from character analysis")
        
        # Sort in reading order
        line_tolerance_final = int(median_char_height * 1.5) or 30
        word_boxes.sort(key=lambda box: (box[1] // line_tolerance_final, box[0]))
        
        result = []
        for i, bbox in enumerate(word_boxes):
            result.append({
                "bbox": [int(coord) for coord in bbox],
                "index": i
            })
        
        # Debug visualization
        if debug_mode:
            # Show character components
            char_debug = image.copy()
            for box in char_boxes:
                cv2.rectangle(char_debug, (box['x'], box['y']), (box['x2'], box['y2']), (0, 255, 0), 1)
            cv2.imwrite("debug_3_character_components.png", char_debug)
            
            # Show final word boxes
            word_debug = image.copy()
            for box_data in result:
                x1, y1, x2, y2 = box_data["bbox"]
                cv2.rectangle(word_debug, (x1, y1), (x2, y2), (0, 0, 255), 2)
                cv2.putText(word_debug, str(box_data["index"]), (x1, y1-5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
            cv2.imwrite("debug_4_final_word_boxes.png", word_debug)
        
        logger.info(f"Final result: {len(result)} word-level bounding boxes from Stage 5 analysis")
        return result
        
    except Exception as e:
        logger.error(f"Error processing image {image_path}: {str(e)}")
        raise


# Simplified helper functions (kept for compatibility)
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


def _estimate_char_height(contours: List[np.ndarray]) -> float:
    """
    Estimate typical character height from contours for dynamic filtering.
    
    Args:
        contours: List of detected contours
        
    Returns:
        Estimated character height in pixels
    """
    if not contours:
        return 10.0  # Fallback
    
    heights = []
    for contour in contours:
        _, _, _, h = cv2.boundingRect(contour)
        if 3 <= h <= 200:  # Reasonable character height range
            heights.append(h)
    
    if not heights:
        return 10.0
    
    return float(np.median(heights))


def _filter_and_extract_bboxes(
    contours: List[np.ndarray], 
    image_shape: Tuple[int, int, int]
) -> List[Dict[str, Any]]:
    """
    Filter noise contours and extract bounding boxes.
    Uses dynamic sizing based on estimated character height.
    
    Args:
        contours: List of detected contours
        image_shape: Shape of the original image (height, width, channels)
        
    Returns:
        List of valid bounding boxes as dictionaries
    """
    height, width = image_shape[:2]
    valid_boxes = []
    
    # Estimate character height for dynamic filtering
    estimated_char_height = _estimate_char_height(contours)
    
    # Dynamic size filters based on character height
    min_height = max(3, 0.5 * estimated_char_height)
    min_width = max(2, 0.5 * estimated_char_height)
    max_height = 3.0 * estimated_char_height
    min_area = min_width * min_height
    
    # Relaxed aspect ratio for short words and single characters
    min_aspect_ratio = 0.4  # Allow nearly square characters
    max_aspect_ratio = 15.0  # Still avoid very long artifacts
    
    filtered_count = 0
    
    for contour in contours:
        # Get bounding rectangle
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        aspect_ratio = w / float(h) if h > 0 else 0
        
        # Apply all filters
        size_ok = (w >= min_width and h >= min_height and 
                  h <= max_height and area >= min_area)
        aspect_ok = min_aspect_ratio <= aspect_ratio <= max_aspect_ratio
        
        if size_ok and aspect_ok:
            # Convert to [x1, y1, x2, y2] format
            bbox = [x, y, x + w, y + h]
            valid_boxes.append({"bbox": bbox})
        else:
            filtered_count += 1
    
    logger.info(f"Character height: {estimated_char_height:.1f}px, "
                f"kept {len(valid_boxes)} boxes, filtered {filtered_count}")
    return valid_boxes


def _sort_reading_order(bounding_boxes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sort bounding boxes in reading order (top-to-bottom, left-to-right).
    
    Args:
        bounding_boxes: List of bounding box dictionaries
        
    Returns:
        Sorted list with added index field
    """
    def sort_key(box):
        x1, y1, x2, y2 = box["bbox"]
        # Group boxes on the same line with tolerance
        line_tolerance = max(1, abs(y2 - y1) * 0.5)  # Half the height as tolerance, minimum 1
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
            "avg_area": 0,
            "min_width": 0,
            "max_width": 0,
            "min_height": 0,
            "max_height": 0
        }
    
    widths = [box["bbox"][2] - box["bbox"][0] for box in bounding_boxes]
    heights = [box["bbox"][3] - box["bbox"][1] for box in bounding_boxes]
    areas = [w * h for w, h in zip(widths, heights)]
    
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