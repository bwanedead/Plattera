#!/usr/bin/env python3
"""
Comprehensive Bounding Box API Test Script
==========================================

Tests the complete bounding box detection pipeline:
1. Line detection with OpenCV
2. Word segmentation with LLM
3. Visualization of results

This script tests the API endpoints directly and creates visual output.
"""

import sys
import os
import json
import base64
import time
import requests
from pathlib import Path
import cv2
import numpy as np
from typing import Dict, Any, List

# Add backend to path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_path)

# Test configuration
TEST_IMAGE_PATH = "sample text image/legal_text_image.jpg"
API_BASE_URL = "http://localhost:8000"
DEBUG_OUTPUT_DIR = Path("test_bounding_box_api_output")


def setup_test_environment():
    """Set up test environment and directories."""
    print("🔧 Setting up test environment...")
    
    # Create output directory
    DEBUG_OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Clean up previous results
    for file in DEBUG_OUTPUT_DIR.glob("*"):
        if file.is_file():
            file.unlink()
            print(f"🗑️  Deleted: {file}")
    
    print(f"📁 Output directory: {DEBUG_OUTPUT_DIR}")
    print()


def save_original_image():
    """Save the original test image to the output directory."""
    print("💾 Saving original test image...")
    
    try:
        import shutil
        original_path = Path(TEST_IMAGE_PATH)
        output_path = DEBUG_OUTPUT_DIR / "original_test_image.jpg"
        shutil.copy2(original_path, output_path)
        print(f"✅ Original image saved: {output_path}")
        return str(output_path)
    except Exception as e:
        print(f"❌ Error saving original image: {e}")
        return None


def check_api_status():
    """Check if the API server is running."""
    print("🔍 Checking API status...")
    
    try:
        response = requests.get(f"{API_BASE_URL}/api/bounding-boxes/status", timeout=5)
        if response.status_code == 200:
            status_data = response.json()
            print("✅ API server is running")
            print(f"📊 Services: {status_data.get('services', {})}")
            return True
        else:
            print(f"❌ API server returned status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to API server: {e}")
        print("💡 Make sure the backend server is running on http://localhost:8000")
        return False


def test_line_detection():
    """Test line detection endpoint."""
    print("📏 Testing line detection...")
    
    if not Path(TEST_IMAGE_PATH).exists():
        print(f"❌ Test image not found: {TEST_IMAGE_PATH}")
        return None
    
    try:
        with open(TEST_IMAGE_PATH, 'rb') as f:
            files = {'image': ('test_image.jpg', f, 'image/jpeg')}
            response = requests.post(f"{API_BASE_URL}/api/bounding-boxes/detect-lines", files=files)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print(f"✅ Line detection successful")
                print(f"📊 Lines detected: {result.get('total_lines', 0)}")
                print(f"⏱️  Processing time: {result.get('processing_time', 0):.2f}ms")
                return result
            else:
                print(f"❌ Line detection failed: {result.get('error', 'Unknown error')}")
                return None
        else:
            print(f"❌ Line detection request failed: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Line detection error: {e}")
        return None


def test_word_detection(line_result: Dict[str, Any]):
    """Test word detection endpoint."""
    print("🔤 Testing LLM word detection...")
    
    if not Path(TEST_IMAGE_PATH).exists():
        print(f"❌ Test image not found: {TEST_IMAGE_PATH}")
        return None
    
    try:
        with open(TEST_IMAGE_PATH, 'rb') as f:
            files = {'image': ('test_image.jpg', f, 'image/jpeg')}
            data = {
                'lines': json.dumps(line_result.get('lines', [])),
                'model': 'gpt-o4-mini',  # Changed to o4-mini model
                'complexity': 'standard'
            }
            
            print(f"🤖 Using model: {data['model']}")
            print(f"🎯 Complexity level: {data['complexity']}")
            print(f"📏 Lines data: {len(line_result.get('lines', []))} lines")
            
            response = requests.post(f"{API_BASE_URL}/api/bounding-boxes/detect-words", 
                                   files=files, data=data)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print(f"✅ LLM word detection successful")
                print(f"📊 Words detected: {result.get('total_words', 0)}")
                print(f"⏱️  Processing time: {result.get('processing_time', 0):.2f}ms")
                print(f"🤖 Model used: {result.get('model_used', 'Unknown')}")
                print(f"🔢 Tokens used: {result.get('tokens_used', 0)}")
                return result
            else:
                print(f"❌ LLM word detection failed: {result.get('error', 'Unknown error')}")
                # Show more details about the error
                print(f"🔍 Full error response: {result}")
                return None
        else:
            print(f"❌ LLM word detection request failed: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ LLM word detection error: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_full_pipeline():
    """Test the complete bounding box pipeline."""
    print("🚀 Testing full bounding box pipeline...")
    
    if not Path(TEST_IMAGE_PATH).exists():
        print(f"❌ Test image not found: {TEST_IMAGE_PATH}")
        return None
    
    try:
        with open(TEST_IMAGE_PATH, 'rb') as f:
            files = {'image': ('test_image.jpg', f, 'image/jpeg')}
            data = {
                'model': 'gpt-o4-mini',  # Changed to o4-mini model
                'complexity': 'standard'
            }
            response = requests.post(f"{API_BASE_URL}/api/bounding-boxes/pipeline", 
                                   files=files, data=data)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print(f"✅ Full pipeline successful")
                print(f"📊 Lines detected: {len(result.get('lines', []))}")
                print(f"📊 Words detected: {result.get('total_words', 0)}")
                print(f"⏱️  Total processing time: {result.get('total_processing_time', 0):.2f}ms")
                print(f"🤖 Model used: {result.get('model_used', 'Unknown')}")
                return result
            else:
                print(f"❌ Full pipeline failed: {result.get('error', 'Unknown error')}")
                return None
        else:
            print(f"❌ Full pipeline request failed: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Full pipeline error: {e}")
        return None


def create_visualization(result: Dict[str, Any]):
    """Create visual output showing bounding boxes on the image."""
    print("🎨 Creating visualization...")
    
    if not result or not result.get('success'):
        print("❌ No valid result to visualize")
        return
    
    try:
        # Use the overlay image if available, otherwise use original
        overlay_path = result.get('overlay_image_path')
        if overlay_path and Path(overlay_path).exists():
            image = cv2.imread(overlay_path)
            print(f"📁 Using overlay image for visualization: {overlay_path}")
        else:
            image = cv2.imread(TEST_IMAGE_PATH)
            print(f"📁 Using original image for visualization: {TEST_IMAGE_PATH}")
        
        if image is None:
            print(f"❌ Could not load image")
            return
        
        # FIRST: Save the exact image that was sent to the LLM
        if overlay_path and Path(overlay_path).exists():
            llm_input_path = DEBUG_OUTPUT_DIR / "llm_used_image.jpg"
            import shutil
            shutil.copy2(overlay_path, llm_input_path)
            print(f"✅ LLM input image saved: {llm_input_path}")
        
        # Create visualization image with word bounding boxes
        vis_image = image.copy()
        
        # Draw word bounding boxes
        words_by_line = result.get('words_by_line', [])
        for line_data in words_by_line:
            words = line_data.get('words', [])
            for word_array in words:
                if len(word_array) >= 3:
                    word_text = word_array[0]
                    start_pos = word_array[1]
                    end_pos = word_array[2]
                    
                    # Draw word bounding box (horizontal line)
                    y_center = image.shape[0] // 2  # Place in center for now
                    cv2.line(vis_image, (start_pos, y_center), (end_pos, y_center), (0, 255, 0), 2)
                    
                    # Add word text
                    cv2.putText(vis_image, word_text, (start_pos, y_center - 10), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        
        # Save visualization
        output_path = DEBUG_OUTPUT_DIR / "bounding_box_visualization.jpg"
        cv2.imwrite(str(output_path), vis_image)
        print(f"✅ Visualization saved: {output_path}")
        
        # Also save the overlay image if it exists (for reference)
        if overlay_path and Path(overlay_path).exists():
            overlay_output = DEBUG_OUTPUT_DIR / "overlay_image.jpg"
            import shutil
            shutil.copy2(overlay_path, overlay_output)
            print(f"✅ Overlay image saved: {overlay_output}")
        
    except Exception as e:
        print(f"❌ Visualization error: {e}")
        import traceback
        traceback.print_exc()


def save_json_results(result: Dict[str, Any]):
    """Save the JSON results to a file."""
    print("💾 Saving JSON results...")
    
    try:
        output_path = DEBUG_OUTPUT_DIR / "bounding_box_results.json"
        with open(output_path, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"✅ JSON results saved: {output_path}")
        
        # Also save a summary
        summary = {
            "success": result.get('success', False),
            "total_lines": len(result.get('lines', [])),
            "total_words": result.get('total_words', 0),
            "processing_time": result.get('total_processing_time', 0),
            "model_used": result.get('model_used', 'Unknown'),
            "complexity_level": result.get('complexity_level', 'Unknown'),
            "tokens_used": result.get('tokens_used', 0)
        }
        
        summary_path = DEBUG_OUTPUT_DIR / "summary.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"✅ Summary saved: {summary_path}")
        
    except Exception as e:
        print(f"❌ Error saving results: {e}")


def print_detailed_results(result: Dict[str, Any]):
    """Print detailed results to console."""
    print("\n" + "="*60)
    print("📋 DETAILED RESULTS")
    print("="*60)
    
    if not result or not result.get('success'):
        print("❌ No successful results to display")
        return
    
    # Basic info
    print(f"✅ Success: {result.get('success')}")
    print(f"📊 Total Lines: {len(result.get('lines', []))}")
    print(f"📊 Total Words: {result.get('total_words', 0)}")
    print(f"⏱️  Processing Time: {result.get('total_processing_time', 0):.2f}ms")
    print(f"🤖 Model Used: {result.get('model_used', 'Unknown')}")
    print(f"🎯 Complexity Level: {result.get('complexity_level', 'Unknown')}")
    print(f"🔢 Tokens Used: {result.get('tokens_used', 0)}")
    
    # Stage times
    stage_times = result.get('stage_times', {})
    if stage_times:
        print(f"\n⏱️  Stage Times:")
        print(f"   Line Detection: {stage_times.get('line_detection', 0):.2f}ms")
        print(f"   Word Segmentation: {stage_times.get('word_segmentation', 0):.2f}ms")
    
    # Line details
    lines = result.get('lines', [])
    if lines:
        print(f"\n📏 Line Details:")
        for i, line in enumerate(lines[:5]):  # Show first 5 lines
            bounds = line.get('bounds', {})
            print(f"   Line {i+1}: y1={bounds.get('y1', 0)}, y2={bounds.get('y2', 0)}, "
                  f"height={bounds.get('y2', 0) - bounds.get('y1', 0)}")
        if len(lines) > 5:
            print(f"   ... and {len(lines) - 5} more lines")
    
    # Word details (first few lines)
    words_by_line = result.get('words_by_line', [])
    if words_by_line:
        print(f"\n🔤 Word Details (first 3 lines):")
        for i, line_data in enumerate(words_by_line[:3]):
            words = line_data.get('words', [])
            print(f"   Line {i+1}: {len(words)} words")
            for j, word in enumerate(words[:5]):  # Show first 5 words per line
                # Handle new simplified format: ["word", start, end]
                if isinstance(word, list) and len(word) >= 3:
                    word_text = word[0]
                    start_pos = word[1]
                    end_pos = word[2]
                    print(f"     Word {j+1}: '{word_text}' (pos: {start_pos}-{end_pos})")
                # Handle old format: {"word": "...", "confidence": ...}
                elif isinstance(word, dict):
                    confidence = word.get('confidence', 0)
                    word_text = word.get('word', '')
                    print(f"     Word {j+1}: '{word_text}' (confidence: {confidence:.2f})")
                else:
                    print(f"     Word {j+1}: {word}")
            if len(words) > 5:
                print(f"     ... and {len(words) - 5} more words")
    
    print("="*60)


def main():
    """Main test function."""
    print("🧪 BOUNDING BOX API TEST SCRIPT")
    print("="*50)
    
    # Setup
    setup_test_environment()
    
    # Save original image
    save_original_image()
    
    # Check API status
    if not check_api_status():
        print("\n❌ Cannot proceed without API server")
        return
    
    print()
    
    # Test individual stages first (more reliable)
    print(" Testing Individual Stages")
    print("-" * 40)
    
    line_result = test_line_detection()
    if line_result:
        word_result = test_word_detection(line_result)
        if word_result:
            # Combine results manually
            combined_result = {
                "success": True,
                "lines": line_result.get('lines', []),
                "words_by_line": word_result.get('words_by_line', []),
                "total_processing_time": line_result.get('processing_time', 0) + word_result.get('processing_time', 0),
                "total_words": word_result.get('total_words', 0),
                "stage_times": {
                    "line_detection": line_result.get('processing_time', 0),
                    "word_segmentation": word_result.get('processing_time', 0)
                },
                "model_used": word_result.get('model_used', 'Unknown'),
                "complexity_level": word_result.get('complexity_level', 'Unknown'),
                "tokens_used": word_result.get('tokens_used', 0),
                "overlay_image_path": word_result.get('overlay_image_path')
            }
            
            # Save and display results
            save_json_results(combined_result)
            create_visualization(combined_result)
            print_detailed_results(combined_result)
            
            print(f"\n SUCCESS! Check the output directory: {DEBUG_OUTPUT_DIR}")
            print("📁 Files created:")
            print("   - original_test_image.jpg (original image without overlays)")
            print("   - llm_used_image.jpg (EXACT image sent to LLM with ruler lines)")
            print("   - overlay_image.jpg (same as llm_used_image.jpg, for reference)")
            print("   - bounding_box_visualization.jpg (word boxes drawn on image)")
            print("   - bounding_box_results.json (full API response)")
            print("   - summary.json (key metrics)")
            
        else:
            print("\n❌ Word detection stage failed")
    else:
        print("\n❌ Line detection stage failed")
    
    print("\n" + "="*50)
    print("🎯 Now Testing Full Pipeline (for comparison)")
    print("-" * 40)
    
    # Test full pipeline for comparison
    pipeline_result = test_full_pipeline()
    if pipeline_result and pipeline_result.get('success'):
        print("✅ Full pipeline also works!")
    else:
        print("❌ Full pipeline has issues (but individual stages work)")


if __name__ == "__main__":
    main() 