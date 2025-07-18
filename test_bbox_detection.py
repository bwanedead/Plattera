#!/usr/bin/env python3
"""
Standalone test script for bounding box detection.
Runs the detection in isolation and saves debug images to test_bounding_box/ directory.
"""

import sys
import os
from pathlib import Path
import time

# Add backend to path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_path)

def cleanup_previous_results():
    """Remove all previous debug images from the test directory."""
    test_dir = Path(__file__).parent / "test_bounding_box"
    test_dir.mkdir(exist_ok=True)
    
    # Remove ALL files in the test directory
    for file in test_dir.iterdir():
        if file.is_file():
            file.unlink()
            print(f"Deleted: {file.name}")
    
    print(f"Cleaned up all files in {test_dir}")

def test_bounding_box_detection():
    """Test the bounding box detection with debug mode."""
    try:
        from alignment.bounding_box.detector import detect_word_bounding_boxes
        
        # Test image path
        image_path = "sample text image/legal_text_image.jpg"
        
        if not Path(image_path).exists():
            print(f"Test image not found: {image_path}")
            return
        
        print(f"Testing bounding box detection on: {image_path}")
        print("=" * 50)
        
        # Clean up previous results FIRST
        cleanup_previous_results()
        
        # Run detection with debug mode
        start_time = time.time()
        boxes = detect_word_bounding_boxes(image_path, debug_mode=True)
        end_time = time.time()
        
        print(f"Detection completed in {end_time - start_time:.2f} seconds")
        print(f"Found {len(boxes)} bounding boxes")
        
        if boxes:
            # Calculate statistics
            widths = [box['bbox'][2] - box['bbox'][0] for box in boxes]
            heights = [box['bbox'][3] - box['bbox'][1] for box in boxes]
            
            print(f"Average width: {sum(widths)/len(widths):.1f}px")
            print(f"Average height: {sum(heights)/len(heights):.1f}px")
            print(f"Min width: {min(widths):.1f}px")
            print(f"Max width: {max(widths):.1f}px")
        
        print("\nDebug images saved to test_bounding_box/ directory")
        print("Check debug_10_final_result.png for the final result")
        
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_bounding_box_detection() 