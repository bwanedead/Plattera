"""
Line detection and ruler overlay system for LLM-based word segmentation.
Creates a visual overlay with line boundaries and horizontal position markers.
"""

import cv2
import numpy as np
from typing import List, Dict, Any, Tuple
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def detect_text_lines_with_ruler(image_path: str, debug_mode: bool = False) -> Dict[str, Any]:
    """
    Detect text lines and create a ruler overlay for LLM analysis.
    
    Returns:
        Dictionary containing:
        - lines: List of line boundaries [y1, y2]
        - ruler_positions: List of horizontal marker positions
        - overlay_image: Image with line boundaries and ruler markers
    """
    if not Path(image_path).exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    
    # Set up debug directory - CORRECT PATH
    debug_dir = Path(__file__).parent / "test_line_detector"
    if debug_mode:
        debug_dir.mkdir(exist_ok=True)
    
    try:
        # Load image
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not load image: {image_path}")
        
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        if debug_mode:
            cv2.imwrite(str(debug_dir / "debug_1_gray.png"), gray)
        
        # 1. PREPROCESSING - Clean and prepare for line detection
        # Apply CLAHE for better contrast
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        gray_eq = clahe.apply(gray)
        
        # Binary threshold (non-inverted)
        _, binary = cv2.threshold(gray_eq, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Invert so text is white on black
        fg = 255 - binary
        
        if debug_mode:
            cv2.imwrite(str(debug_dir / "debug_2_binary.png"), fg)
        
        # 2. IMPROVED MARGIN CROPPING - More aggressive margin removal
        # Find the main text region using horizontal projection
        # Sum white pixels (text) in each column
        col_sums = np.sum(fg, axis=0)
        
        # Find the main text region (where there's significant text)
        threshold = np.max(col_sums) * 0.1  # 10% of max column density
        
        # Find left and right boundaries
        left_bound = 0
        for i in range(len(col_sums)):
            if col_sums[i] > threshold:
                left_bound = max(0, i - 10)  # Add small padding
                break
        
        right_bound = len(col_sums) - 1
        for i in range(len(col_sums) - 1, -1, -1):
            if col_sums[i] > threshold:
                right_bound = min(len(col_sums) - 1, i + 10)  # Add small padding
                break
        
        # Find top and bottom boundaries using row projection
        row_sums = np.sum(fg, axis=1)
        threshold_row = np.max(row_sums) * 0.1
        
        top_bound = 0
        for i in range(len(row_sums)):
            if row_sums[i] > threshold_row:
                top_bound = max(0, i - 10)
                break
        
        bottom_bound = len(row_sums) - 1
        for i in range(len(row_sums) - 1, -1, -1):
            if row_sums[i] > threshold_row:
                bottom_bound = min(len(row_sums) - 1, i + 10)
                break
        
        # Crop the image to main text region
        cropped_fg = fg[top_bound:bottom_bound, left_bound:right_bound]
        cropped_original = image[top_bound:bottom_bound, left_bound:right_bound]
        
        if debug_mode:
            cv2.imwrite(str(debug_dir / "debug_3_cropped.png"), cropped_fg)
            
            # Save projection data for debugging
            with open(debug_dir / "debug_projections.txt", "w") as f:
                f.write(f"Image shape: {image.shape}\n")
                f.write(f"Cropped shape: {cropped_fg.shape}\n")
                f.write(f"Left bound: {left_bound}, Right bound: {right_bound}\n")
                f.write(f"Top bound: {top_bound}, Bottom bound: {bottom_bound}\n")
                f.write(f"Column threshold: {threshold}\n")
                f.write(f"Row threshold: {threshold_row}\n")
        
        # 3. LINE DETECTION - Use horizontal projection for line finding
        # Sum white pixels in each row of the cropped image
        row_sums_cropped = np.sum(cropped_fg, axis=1)
        
        # Find lines using peak detection
        lines = []
        in_line = False
        line_start = 0
        min_line_height = 20  # Minimum height for a line
        min_line_density = np.max(row_sums_cropped) * 0.3  # Minimum text density for a line
        
        for i, density in enumerate(row_sums_cropped):
            if density > min_line_density and not in_line:
                # Start of a line
                line_start = i
                in_line = True
            elif density <= min_line_density and in_line:
                # End of a line
                line_end = i
                if line_end - line_start >= min_line_height:
                    lines.append((line_start, line_end))
                in_line = False
        
        # Handle case where line extends to bottom
        if in_line and len(row_sums_cropped) - line_start >= min_line_height:
            lines.append((line_start, len(row_sums_cropped)))
        
        # Sort lines by y-position
        lines.sort(key=lambda line: line[0])
        
        if debug_mode:
            # Create debug image showing detected lines
            debug_lines = cv2.cvtColor(cropped_fg, cv2.COLOR_GRAY2BGR)
            
            # Draw bright red lines through the center of each detected line
            for i, (y1, y2) in enumerate(lines):
                center_y = (y1 + y2) // 2
                # Draw a bright red horizontal line through the center
                cv2.line(debug_lines, (0, center_y), (cropped_fg.shape[1], center_y), (0, 0, 255), 3)
                # Add line number
                cv2.putText(debug_lines, f"Line {i+1}", (10, center_y-10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            
            cv2.imwrite(str(debug_dir / "debug_4_detected_lines.png"), debug_lines)
            
            # Also create a version with boxes around each line
            debug_boxes = cv2.cvtColor(cropped_fg, cv2.COLOR_GRAY2BGR)
            for i, (y1, y2) in enumerate(lines):
                # Draw bright red box around each line
                cv2.rectangle(debug_boxes, (0, y1), (cropped_fg.shape[1], y2), (0, 0, 255), 2)
                # Add line number
                cv2.putText(debug_boxes, f"Line {i+1}", (10, y1+20), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
            
            cv2.imwrite(str(debug_dir / "debug_5_line_boxes.png"), debug_boxes)
            
            # Save line detection stats
            with open(debug_dir / "debug_stats.txt", "w") as f:
                f.write(f"Original image dimensions: {image.shape}\n")
                f.write(f"Cropped image dimensions: {cropped_fg.shape}\n")
                f.write(f"Number of lines detected: {len(lines)}\n")
                f.write(f"Min line height: {min_line_height}\n")
                f.write(f"Min line density: {min_line_density}\n")
                f.write(f"Max row density: {np.max(row_sums_cropped)}\n")
                f.write("\nLine details:\n")
                for i, (y1, y2) in enumerate(lines):
                    f.write(f"Line {i+1}: y1={y1}, y2={y2}, height={y2-y1}, center={y1+(y2-y1)//2}\n")
        
        # 4. CREATE RULER OVERLAY
        # Add horizontal position markers every 50 pixels
        ruler_spacing = 50
        ruler_positions = list(range(0, cropped_fg.shape[1], ruler_spacing))
        
        # Create overlay image
        overlay = cropped_original.copy()
        
        # Draw bright red lines through the center of each detected line
        for i, (y1, y2) in enumerate(lines):
            center_y = (y1 + y2) // 2
            # Draw a bright red horizontal line through the center
            cv2.line(overlay, (0, center_y), (cropped_fg.shape[1], center_y), (0, 0, 255), 3)
            # Add line number
            cv2.putText(overlay, f"Line {i+1}", (10, center_y-10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        
        # Draw ruler markers (vertical lines)
        for pos in ruler_positions:
            cv2.line(overlay, (pos, 0), (pos, cropped_fg.shape[0]), (255, 0, 0), 1)
            cv2.putText(overlay, str(pos), (pos+2, 20), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 0, 0), 1)
        
        if debug_mode:
            cv2.imwrite(str(debug_dir / "debug_6_final_overlay.png"), overlay)
        
        return {
            "lines": lines,
            "ruler_positions": ruler_positions,
            "overlay_image": overlay,
            "cropped_region": (left_bound, top_bound, right_bound, bottom_bound)
        }
        
    except Exception as e:
        logger.error(f"Error in line detection: {e}")
        raise


def create_test_script():
    """Create a test script for the line detector."""
    test_script = '''#!/usr/bin/env python3
"""
Test script for line detection and ruler overlay.
"""

import sys
import os
from pathlib import Path

# Add backend to path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_path)

def cleanup_previous_results():
    """Remove all previous debug images from the test directory."""
    test_dir = Path(__file__).parent / "test_line_detector"
    test_dir.mkdir(exist_ok=True)
    
    # Remove ALL files in the test directory
    for file in test_dir.glob("*"):
        if file.is_file():
            file.unlink()
            print(f"Deleted: {file}")

def main():
    """Test the line detection system."""
    try:
        from alignment.bounding_box.line_detector import detect_text_lines_with_ruler
        
        # Clean up previous results
        cleanup_previous_results()
        
        # Test image path
        image_path = "sample text image/legal_text_image.jpg"
        
        if not Path(image_path).exists():
            print(f"Test image not found: {image_path}")
            return
        
        print("Testing line detection with ruler overlay...")
        
        # Run detection
        result = detect_text_lines_with_ruler(image_path, debug_mode=True)
        
        print(f"\\nResults:")
        print(f"Number of lines detected: {len(result['lines'])}")
        print(f"Ruler positions: {len(result['ruler_positions'])} markers")
        print(f"Cropped region: {result['cropped_region']}")
        
        print("\\nLine details:")
        for i, (y1, y2) in enumerate(result['lines']):
            print(f"Line {i+1}: y1={y1}, y2={y2}, height={y2-y1}")
        
        print("\\nDebug images saved to: test_line_detector/")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
'''
    
    with open("test_line_detection.py", "w") as f:
        f.write(test_script)
    
    print("Created test_line_detection.py")


if __name__ == "__main__":
    create_test_script() 