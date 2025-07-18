#!/usr/bin/env python3
"""
Test only the bounding box detection, bypassing other alignment imports.
"""

import sys
import os
from pathlib import Path

# Add backend to path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_path)

def test_bounding_box_only():
    """Test only the bounding box detection without other dependencies."""
    try:
        print("Testing imports...")
        
        # Test basic imports first
        import cv2
        print("✅ OpenCV imported")
        
        import numpy as np
        print("✅ NumPy imported")
        
        # Import bounding box detection directly
        from alignment.bounding_box.detector import detect_word_bounding_boxes
        print("✅ Bounding box detector imported")
        
        # Test image path
        test_image_path = "sample text image/legal_text_image.jpg"
        
        if not Path(test_image_path).exists():
            print(f"❌ Test image not found: {test_image_path}")
            return
        
        print(f"🧪 Testing bounding box detection with debug mode on: {test_image_path}")
        
        # Run with debug mode enabled
        boxes = detect_word_bounding_boxes(test_image_path, debug_mode=True)
        
        print(f"✅ Detection completed - Found {len(boxes)} boxes")
        
        if boxes:
            print(f"   First box: {boxes[0]}")
            print(f"   Last box: {boxes[-1]}")
        
        print("\n Debug images saved:")
        debug_files = [
            "debug_0_original_gray.png",
            "debug_1_thresh_otsu.png", 
            "debug_1_fg_otsu.png",
            "debug_2_thresh_adaptive.png",
            "debug_2_fg_adaptive.png", 
            "debug_3_gray_clahe.png",
            "debug_3_thresh_clahe.png",
            "debug_3_fg_clahe.png",
            "debug_4_selected_fg.png",
            "debug_5_cleaned.png",
            "debug_6_dilated_light.png",
            "debug_7_dilated_medium.png", 
            "debug_8_dilated_close.png",
            "debug_9_final_dilated.png",
            "debug_10_final_result.png"
        ]
        
        for debug_file in debug_files:
            if Path(debug_file).exists():
                print(f"   ✅ {debug_file}")
            else:
                print(f"   ❌ {debug_file} (not found)")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_bounding_box_only() 