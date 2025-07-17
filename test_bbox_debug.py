"""
Debug script to test bounding box detection functionality.
Run this to verify OpenCV installation and bounding box detection.
"""

import sys
import logging
from pathlib import Path

# Add backend to path
sys.path.append('backend')

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_opencv():
    """Test if OpenCV is properly installed."""
    try:
        import cv2
        print(f"✅ OpenCV successfully imported, version: {cv2.__version__}")
        return True
    except ImportError as e:
        print(f"❌ OpenCV import failed: {e}")
        return False

def test_image_loading():
    """Test if the sample image can be loaded."""
    try:
        import cv2
        image_path = r"C:\projects\Plattera\sample text image\legal_text_image.jpg"
        
        if not Path(image_path).exists():
            print(f"❌ Image file not found: {image_path}")
            return False
            
        image = cv2.imread(image_path)
        if image is None:
            print(f"❌ Could not load image: {image_path}")
            return False
            
        print(f"✅ Image loaded successfully: {image.shape}")
        return True
    except Exception as e:
        print(f"❌ Image loading failed: {e}")
        return False

def test_bounding_box_detection():
    """Test the bounding box detection function."""
    try:
        from alignment.bounding_box.detector import detect_word_bounding_boxes
        image_path = r"C:\projects\Plattera\sample text image\legal_text_image.jpg"
        
        print(f"🔍 Testing bounding box detection on: {image_path}")
        boxes = detect_word_bounding_boxes(image_path)
        print(f"✅ Bounding box detection successful: {len(boxes)} boxes found")
        
        if boxes:
            print(f"   Sample box: {boxes[0]}")
            
        return True
    except Exception as e:
        print(f"❌ Bounding box detection failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_async_detection():
    """Test the async bounding box detection."""
    try:
        import asyncio
        from alignment.bounding_box import detect_with_stats_async
        
        async def run_async_test():
            image_path = r"C:\projects\Plattera\sample text image\legal_text_image.jpg"
            print(f"🔍 Testing async bounding box detection on: {image_path}")
            result = await detect_with_stats_async(image_path)
            print(f"✅ Async bounding box detection successful:")
            print(f"   Boxes: {len(result['bounding_boxes'])}")
            print(f"   Stats: {result['stats']}")
            return True
        
        return asyncio.run(run_async_test())
    except Exception as e:
        print(f"❌ Async bounding box detection failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🔧 BOUNDING BOX DETECTION DEBUG TEST")
    print("=" * 50)
    
    # Test 1: OpenCV installation
    print("\n1. Testing OpenCV installation...")
    opencv_ok = test_opencv()
    
    if not opencv_ok:
        print("\n❌ OpenCV is not properly installed. Install with:")
        print("   pip install opencv-python==4.8.1.78")
        sys.exit(1)
    
    # Test 2: Image loading
    print("\n2. Testing image loading...")
    image_ok = test_image_loading()
    
    if not image_ok:
        print("\n❌ Cannot load the test image. Check the file path.")
        sys.exit(1)
    
    # Test 3: Sync detection
    print("\n3. Testing synchronous bounding box detection...")
    sync_ok = test_bounding_box_detection()
    
    # Test 4: Async detection
    print("\n4. Testing asynchronous bounding box detection...")
    async_ok = test_async_detection()
    
    print("\n" + "=" * 50)
    if sync_ok and async_ok:
        print("✅ ALL TESTS PASSED - Bounding box detection is working correctly!")
    else:
        print("❌ SOME TESTS FAILED - Check the errors above.") 