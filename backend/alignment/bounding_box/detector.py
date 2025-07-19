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
    Row-aligned word-level bounding box detection with strict boundary enforcement.
    Ensures boxes don't overlap rows and captures more words.
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
        
        # Stage 1: Find text rows using horizontal dilation
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        fg = 255 - binary  # Make text white
        
        if debug_mode:
            cv2.imwrite(str(debug_dir / 'debug_2_binary.png'), fg)
        
        # Small open to remove noise
        kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
        fg_clean = cv2.morphologyEx(fg, cv2.MORPH_OPEN, kernel_open, iterations=1)
        
        if debug_mode:
            cv2.imwrite(str(debug_dir / 'debug_3_cleaned.png'), fg_clean)
        
        # Moderate horizontal dilation to form text rows
        kernel_row = cv2.getStructuringElement(cv2.MORPH_RECT, (80, 2))
        fg_rows = cv2.dilate(fg_clean, kernel_row, iterations=1)
        
        if debug_mode:
            cv2.imwrite(str(debug_dir / 'debug_4_text_rows.png'), fg_rows)
        
        # Find text rows
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(fg_rows, connectivity=8)
        
        if debug_mode:
            print(f"Found {num_labels-1} potential text rows")
        
        # Filter text rows
        text_rows = []
        image_height, image_width = gray.shape
        
        for i in range(1, num_labels):
            x, y, w, h, area = stats[i]
            
            if debug_mode:
                print(f"Row {i}: x={x}, y={y}, w={w}, h={h}, area={area}")
            
            # Filter for valid text rows
            if (area > 1000 and
                h > 8 and
                w > image_width * 0.15 and
                x > image_width * 0.02 and
                x + w < image_width * 0.98):
                
                text_rows.append({
                    'x': x, 'y': y, 'w': w, 'h': h, 
                    'x2': x + w, 'y2': y + h,
                    'area': area
                })
        
        text_rows.sort(key=lambda row: row['y'])
        
        if debug_mode:
            print(f"Kept {len(text_rows)} text rows after filtering")
        
        if debug_mode:
            # Draw text rows
            debug_img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            for i, row in enumerate(text_rows):
                cv2.rectangle(debug_img, (row['x'], row['y']), 
                            (row['x2'], row['y2']), (0, 255, 0), 2)
                cv2.putText(debug_img, f"Row {i}", (row['x'], row['y']-5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            cv2.imwrite(str(debug_dir / 'debug_5_text_rows_detected.png'), debug_img)
        
        # Stage 2: Word detection within each row with strict boundaries
        all_words = []
        
        for row_idx, text_row in enumerate(text_rows):
            # Extract row region with NO padding to enforce strict boundaries
            y1 = text_row['y']
            y2 = text_row['y2']
            x1 = text_row['x']
            x2 = text_row['x2']
            
            # Extract row from clean image
            row_region = fg_clean[y1:y2, x1:x2]
            
            if debug_mode:
                cv2.imwrite(str(debug_dir / f'debug_6_row_{row_idx}_region.png'), row_region)
            
            # Try multiple dilation strategies to catch more words
            word_candidates = []
            
            # Strategy 1: Light dilation for connected words
            kernel_light = cv2.getStructuringElement(cv2.MORPH_RECT, (8, 1))
            row_light = cv2.dilate(row_region, kernel_light, iterations=1)
            
            # Strategy 2: Medium dilation for fragmented words
            kernel_medium = cv2.getStructuringElement(cv2.MORPH_RECT, (12, 2))
            row_medium = cv2.dilate(row_region, kernel_medium, iterations=1)
            
            # Strategy 3: Heavy dilation for very fragmented words
            kernel_heavy = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 2))
            row_heavy = cv2.dilate(row_region, kernel_heavy, iterations=2)
            
            if debug_mode:
                cv2.imwrite(str(debug_dir / f'debug_7_row_{row_idx}_light.png'), row_light)
                cv2.imwrite(str(debug_dir / f'debug_8_row_{row_idx}_medium.png'), row_medium)
                cv2.imwrite(str(debug_dir / f'debug_9_row_{row_idx}_heavy.png'), row_heavy)
            
            # Process each strategy
            for strategy_name, dilated_region in [("light", row_light), ("medium", row_medium), ("heavy", row_heavy)]:
                num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(dilated_region, connectivity=8)
                
                if debug_mode:
                    print(f"Row {row_idx} {strategy_name}: Found {num_labels-1} potential words")
                
                for i in range(1, num_labels):
                    x, y, w, h, area = stats[i]
                    
                    # STRICT row boundary enforcement
                    if y < 0 or y + h > text_row['h']:
                        continue  # Skip if extends beyond row boundaries
                    
                    # Word filtering criteria
                    if (area > 80 and  # Lower threshold to catch more words
                        h > 6 and w > 6 and  # Reasonable minimum size
                        h < text_row['h'] * 0.9 and  # Must fit within row height
                        w < text_row['w'] * 0.7 and  # Must fit within row width
                        w > h * 0.5):  # Words should be wider than tall
                        
                        # Convert to global coordinates
                        global_x = x1 + x
                        global_y = y1 + y
                        
                        # Ensure strict row boundary enforcement
                        global_y = max(global_y, text_row['y'])
                        global_y2 = min(global_y + h, text_row['y2'])
                        global_x = max(global_x, text_row['x'])
                        global_x2 = min(global_x + w, text_row['x2'])
                        
                        word_candidates.append({
                            'bbox': [global_x, global_y, global_x2, global_y2],
                            'area': area,
                            'width': global_x2 - global_x,
                            'height': global_y2 - global_y,
                            'strategy': strategy_name
                        })
            
            # Remove duplicate candidates (overlapping boxes)
            filtered_words = []
            for candidate in word_candidates:
                x1, y1, x2, y2 = candidate['bbox']
                is_duplicate = False
                
                for existing in filtered_words:
                    ex1, ey1, ex2, ey2 = existing['bbox']
                    # Check for significant overlap
                    overlap_x = max(0, min(x2, ex2) - max(x1, ex1))
                    overlap_y = max(0, min(y2, ey2) - max(y1, ey1))
                    overlap_area = overlap_x * overlap_y
                    candidate_area = (x2 - x1) * (y2 - y1)
                    
                    if overlap_area > candidate_area * 0.5:  # More than 50% overlap
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    filtered_words.append(candidate)
            
            # Sort words by x position within row
            filtered_words.sort(key=lambda word: word['bbox'][0])
            
            # Add indices
            for word_idx, word in enumerate(filtered_words):
                word['index'] = len(all_words) + word_idx
                word['row_index'] = row_idx
                word['word_index'] = word_idx
            
            all_words.extend(filtered_words)
            
            if debug_mode:
                print(f"Row {row_idx}: Kept {len(filtered_words)} words after deduplication")
        
        if debug_mode:
            print(f"Total words detected: {len(all_words)}")
        
        # Final result
        result = [{'bbox': word['bbox'], 'index': word['index']} for word in all_words]
        
        if debug_mode:
            # Draw final word boxes on original
            debug_img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            
            if all_words:
                for word in all_words:
                    x1, y1, x2, y2 = word['bbox']
                    cv2.rectangle(debug_img, (x1, y1), (x2, y2), (0, 0, 255), 1)
                    cv2.putText(debug_img, str(word['index']), (x1, y1-2), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 255), 1)
            else:
                cv2.putText(debug_img, "No words detected!", (50, 50), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            
            cv2.imwrite(str(debug_dir / 'debug_10_final_result.png'), debug_img)
            
            # Save stats
            with open(str(debug_dir / 'debug_stats.txt'), 'w') as f:
                f.write(f"Text rows detected: {len(text_rows)}\n")
                f.write(f"Total words detected: {len(all_words)}\n")
                if all_words:
                    widths = [w['width'] for w in all_words]
                    heights = [w['height'] for w in all_words]
                    f.write(f"Average word width: {sum(widths)/len(widths):.1f}px\n")
                    f.write(f"Average word height: {sum(heights)/len(heights):.1f}px\n")
                    f.write(f"Min width: {min(widths):.1f}px\n")
                    f.write(f"Max width: {max(widths):.1f}px\n")
                for i, row in enumerate(text_rows):
                    row_words = [w for w in all_words if w['row_index'] == i]
                    f.write(f"Row {i}: {len(row_words)} words\n")
        
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