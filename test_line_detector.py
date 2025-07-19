#!/usr/bin/env python3
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
            print("Please make sure you have a test image at that location.")
            return
        
        print("Testing line detection with ruler overlay...")
        
        # Run detection
        result = detect_text_lines_with_ruler(image_path, debug_mode=True)
        
        print(f"\nResults:")
        print(f"Number of lines detected: {len(result['lines'])}")
        print(f"Ruler positions: {len(result['ruler_positions'])} markers")
        print(f"Cropped region: {result['cropped_region']}")
        
        print("\nLine details:")
        for i, (y1, y2) in enumerate(result['lines']):
            print(f"Line {i+1}: y1={y1}, y2={y2}, height={y2-y1}")
        
        print("\nDebug images saved to: test_line_detector/")
        print("Check the debug images to see the line detection results!")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
