#!/usr/bin/env python3
"""
Test script for bounding box detection functionality.

This script demonstrates how to use the bounding box detection module
both synchronously and asynchronously.

Note: This script is for testing purposes and should not be run automatically.
Run manually after installing opencv-python.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

async def test_bounding_box_detection():
    """Test the bounding box detection functionality."""
    
    try:
        from backend.alignment.bounding_box import (
            detect_word_bounding_boxes,
            detect_word_bounding_boxes_async,
            detect_with_stats_async,
            get_detection_stats
        )
        
        # Test image path (you'll need to provide an actual image)
        test_image_path = "sample text image/legal_text_image.jpg"
        
        if not Path(test_image_path).exists():
            print(f"❌ Test image not found: {test_image_path}")
            print("Please provide a valid image path for testing.")
            return
        
        print(f"🧪 Testing bounding box detection with: {test_image_path}")
        
        # Test 1: Synchronous detection
        print("\n1️⃣ Testing synchronous detection...")
        try:
            boxes_sync = detect_word_bounding_boxes(test_image_path)
            stats_sync = get_detection_stats(boxes_sync)
            print(f"✅ Sync detection completed - Found {len(boxes_sync)} boxes")
            print(f"📊 Stats: {stats_sync}")
        except Exception as e:
            print(f"❌ Sync detection failed: {e}")
        
        # Test 2: Asynchronous detection
        print("\n2️⃣ Testing asynchronous detection...")
        try:
            boxes_async = await detect_word_bounding_boxes_async(test_image_path)
            print(f"✅ Async detection completed - Found {len(boxes_async)} boxes")
        except Exception as e:
            print(f"❌ Async detection failed: {e}")
        
        # Test 3: Async detection with stats
        print("\n3️⃣ Testing async detection with stats...")
        try:
            result = await detect_with_stats_async(test_image_path)
            boxes = result['bounding_boxes']
            stats = result['stats']
            print(f"✅ Async detection with stats completed - Found {len(boxes)} boxes")
            print(f"📊 Stats: {stats}")
            
            # Display first few bounding boxes
            print("\n📦 First 5 bounding boxes:")
            for i, box in enumerate(boxes[:5]):
                bbox = box['bbox']
                print(f"  Box {box['index']}: [{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}]")
                
        except Exception as e:
            print(f"❌ Async detection with stats failed: {e}")
        
        print("\n✅ All tests completed!")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure opencv-python is installed: pip install opencv-python")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


async def test_api_integration():
    """Test how the bounding box detection integrates with the API models."""
    
    try:
        from backend.api.endpoints.alignment import BoundingBoxRequest, BoundingBoxResponse
        
        print("\n🔌 Testing API model integration...")
        
        # Create a test request
        request = BoundingBoxRequest(image_path="sample text image/legal_text_image.jpg")
        print(f"📝 Created request: {request}")
        
        # Test response model (with dummy data)
        response = BoundingBoxResponse(
            success=True,
            processing_time=1.23,
            bounding_boxes=[
                {"bbox": [10, 20, 100, 40], "index": 0},
                {"bbox": [110, 20, 200, 40], "index": 1}
            ],
            stats={
                "total_boxes": 2,
                "avg_width": 90.0,
                "avg_height": 20.0,
                "avg_area": 1800.0
            }
        )
        print(f"📦 Created response: {response}")
        print("✅ API model integration test completed!")
        
    except ImportError as e:
        print(f"❌ API model import error: {e}")
    except Exception as e:
        print(f"❌ API integration test error: {e}")


if __name__ == "__main__":
    print("🧪 Bounding Box Detection Test Suite")
    print("=" * 50)
    
    # Run tests
    asyncio.run(test_bounding_box_detection())
    asyncio.run(test_api_integration())
    
    print("\n🎯 Test suite completed!")
    print("\nNext steps:")
    print("1. Install opencv-python: pip install opencv-python")
    print("2. Provide a test image and update the test_image_path")
    print("3. Run this script to verify everything works")
    print("4. Test the API endpoints with your frontend") 