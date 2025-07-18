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
    Two-stage bounding box detection:
    1. Dilation stage identifies meta-lines (text regions)
    2. Clean stage finds individual words within those regions
    """
    if not Path(image_path).exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    
    # Set up debug directory
    debug_dir = Path(__file__).parent / "test_bounding_box"
    if debug_mode:
        debug_dir.mkdir(exist_ok=True)
    
    try:
        # Load and preprocess
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not load image: {image_path}")
        
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        if debug_mode:
            cv2.imwrite(str(debug_dir / 'debug_1_gray.png'), gray)
        
        # Stage 1: Meta-line detection using dilation
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        fg = 255 - binary  # Make text white
        
        if debug_mode:
            cv2.imwrite(str(debug_dir / 'debug_2_binary.png'), fg)
        
        # Small open to remove noise
        kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
        fg_clean = cv2.morphologyEx(fg, cv2.MORPH_OPEN, kernel_open, iterations=1)
        
        if debug_mode:
            cv2.imwrite(str(debug_dir / 'debug_3_cleaned.png'), fg_clean)
        
        # Meta-line detection
        kernel_dilate = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 2))
        fg_dilated = cv2.dilate(fg_clean, kernel_dilate, iterations=2)
        
        if debug_mode:
            cv2.imwrite(str(debug_dir / 'debug_4_meta_lines.png'), fg_dilated)
        
        # Find meta-line regions
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(fg_dilated, connectivity=8)
        
        # IMPROVED: Filter meta-lines more aggressively to exclude margins
        meta_lines = []
        image_height, image_width = gray.shape
        
        for i in range(1, num_labels):
            x, y, w, h, area = stats[i]
            
            # More aggressive filtering to exclude margins
            if (area > 2000 and  # Increased minimum area
                h > 15 and  # Increased minimum height
                w > 50 and  # Minimum width to exclude narrow margin elements
                x > image_width * 0.05 and  # Not too close to left edge
                x + w < image_width * 0.95 and  # Not too close to right edge
                y > image_height * 0.05 and  # Not too close to top edge
                y + h < image_height * 0.95):  # Not too close to bottom edge
                
                meta_lines.append({
                    'x': x, 'y': y, 'w': w, 'h': h, 
                    'x2': x + w, 'y2': y + h,
                    'area': area
                })
        
        meta_lines.sort(key=lambda line: line['y'])
        
        if debug_mode:
            # Draw filtered meta-lines
            debug_img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            for i, line in enumerate(meta_lines):
                cv2.rectangle(debug_img, (line['x'], line['y']), 
                            (line['x2'], line['y2']), (0, 255, 0), 2)
                cv2.putText(debug_img, f"Line {i}", (line['x'], line['y']-5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            cv2.imwrite(str(debug_dir / 'debug_5_filtered_meta_lines.png'), debug_img)
        
        # Find the main text region by combining all meta-lines
        if meta_lines:
            # Find the bounding box that encompasses all meta-lines
            min_x = min(line['x'] for line in meta_lines)
            max_x = max(line['x2'] for line in meta_lines)
            min_y = min(line['y'] for line in meta_lines)
            max_y = max(line['y2'] for line in meta_lines)
            
            # Add some padding to ensure we capture the full text
            pad = 10
            text_region = {
                'x': max(0, min_x - pad),
                'y': max(0, min_y - pad),
                'x2': min(gray.shape[1], max_x + pad),
                'y2': min(gray.shape[0], max_y + pad),
                'w': min(gray.shape[1], max_x + pad) - max(0, min_x - pad),
                'h': min(gray.shape[0], max_y + pad) - max(0, min_y - pad)
            }
        else:
            # Fallback: use the center 80% of the image
            text_region = {
                'x': int(image_width * 0.1),
                'y': int(image_height * 0.1),
                'x2': int(image_width * 0.9),
                'y2': int(image_height * 0.9),
                'w': int(image_width * 0.8),
                'h': int(image_height * 0.8)
            }
        
        if debug_mode:
            # Draw the main text region
            debug_img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            cv2.rectangle(debug_img, (text_region['x'], text_region['y']), 
                        (text_region['x2'], text_region['y2']), (0, 255, 0), 2)
            cv2.putText(debug_img, "Main Text Region", (text_region['x'], text_region['y']-5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            cv2.imwrite(str(debug_dir / 'debug_6_main_text_region.png'), debug_img)
        
        # Crop to main text region
        cropped_gray = gray[text_region['y']:text_region['y2'], text_region['x']:text_region['x2']]
        cropped_fg_clean = fg_clean[text_region['y']:text_region['y2'], text_region['x']:text_region['x2']]
        
        if debug_mode:
            cv2.imwrite(str(debug_dir / 'debug_7_cropped_text.png'), cropped_gray)
            cv2.imwrite(str(debug_dir / 'debug_8_cropped_cleaned.png'), cropped_fg_clean)
        
        # Stage 2: Word detection on the cropped text region
        # Word-level dilation to connect characters within words
        kernel_word = cv2.getStructuringElement(cv2.MORPH_RECT, (8, 1))
        word_dilated = cv2.dilate(cropped_fg_clean, kernel_word, iterations=1)
        
        if debug_mode:
            cv2.imwrite(str(debug_dir / 'debug_9_word_detection_image.png'), word_dilated)
        
        # Find connected components in the cropped region
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(word_dilated, connectivity=8)
        
        # Filter components to find words
        all_words = []
        for i in range(1, num_labels):
            x, y, w, h, area = stats[i]
            
            # Word filtering criteria
            if (area > 100 and
                h > 8 and w > 8 and
                h < text_region['h'] * 0.3 and  # Not too tall relative to text region
                w < text_region['w'] * 0.8 and  # Not too wide relative to text region
                w > h * 0.5):  # Aspect ratio check
                
                # Convert to global coordinates (add back the crop offset)
                global_x = text_region['x'] + x
                global_y = text_region['y'] + y
                
                all_words.append({
                    'bbox': [global_x, global_y, global_x + w, global_y + h],
                    'area': area,
                    'width': w,
                    'height': h,
                    'index': len(all_words)
                })
        
        # Sort words by reading order (top to bottom, left to right)
        all_words.sort(key=lambda word: (word['bbox'][1], word['bbox'][0]))
        
        # Update indices after sorting
        for i, word in enumerate(all_words):
            word['index'] = i
        
        # Final result
        result = [{'bbox': word['bbox'], 'index': word['index']} for word in all_words]
        
        if debug_mode:
            # Draw final word boxes on original
            debug_img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            for word in all_words:
                x1, y1, x2, y2 = word['bbox']
                cv2.rectangle(debug_img, (x1, y1), (x2, y2), (0, 0, 255), 1)
                cv2.putText(debug_img, str(word['index']), (x1, y1-2), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 255), 1)
            cv2.imwrite(str(debug_dir / 'debug_10_final_result.png'), debug_img)
            
            # Save stats
            with open(str(debug_dir / 'debug_stats.txt'), 'w') as f:
                f.write(f"Meta-lines detected: {len(meta_lines)}\n")
                f.write(f"Main text region: {text_region['x']},{text_region['y']} to {text_region['x2']},{text_region['y2']}\n")
                f.write(f"Total words detected: {len(all_words)}\n")
                if all_words:
                    widths = [w['width'] for w in all_words]
                    heights = [w['height'] for w in all_words]
                    f.write(f"Average word width: {sum(widths)/len(widths):.1f}px\n")
                    f.write(f"Average word height: {sum(heights)/len(heights):.1f}px\n")
                    f.write(f"Min width: {min(widths):.1f}px\n")
                    f.write(f"Max width: {max(widths):.1f}px\n")
        
        return result
        
    except Exception as e:
        logger.error(f"Error in bounding box detection: {e}")
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