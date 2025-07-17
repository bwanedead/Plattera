"""
Debug script to test image serving functionality.
Run this to test if the image serving endpoint is working.
"""

import requests
import urllib.parse
from pathlib import Path

def test_image_endpoints():
    """Test the image serving endpoints."""
    
    # Test image path
    image_path = r"C:\projects\Plattera\sample text image\legal_text_image.jpg"
    
    print("🔧 IMAGE SERVING DEBUG TEST")
    print("=" * 50)
    
    # Check if image exists
    print(f"\n1. Checking if image exists...")
    if Path(image_path).exists():
        print(f"✅ Image found: {image_path}")
        print(f"   Size: {Path(image_path).stat().st_size} bytes")
    else:
        print(f"❌ Image not found: {image_path}")
        return
    
    # Test different endpoint formats
    base_url = "http://localhost:8000"
    endpoints_to_test = [
        f"{base_url}/api/system/serve-image",
        f"{base_url}/api/serve-image", 
        f"{base_url}/serve-image"
    ]
    
    for endpoint in endpoints_to_test:
        print(f"\n2. Testing endpoint: {endpoint}")
        
        # Test with URL encoded path
        encoded_path = urllib.parse.quote(image_path)
        full_url = f"{endpoint}?image_path={encoded_path}"
        
        print(f"   Full URL: {full_url}")
        
        try:
            # Test HEAD request first
            response = requests.head(full_url, timeout=5)
            print(f"   HEAD Response: {response.status_code}")
            
            if response.status_code == 200:
                print(f"   ✅ Endpoint working!")
                print(f"   Content-Type: {response.headers.get('content-type')}")
                print(f"   Content-Length: {response.headers.get('content-length')}")
                
                # Test actual GET request
                get_response = requests.get(full_url, timeout=10)
                if get_response.status_code == 200:
                    print(f"   ✅ GET request successful!")
                    print(f"   Image data size: {len(get_response.content)} bytes")
                    return endpoint  # Return working endpoint
                else:
                    print(f"   ❌ GET request failed: {get_response.status_code}")
            else:
                print(f"   ❌ HEAD request failed: {response.status_code}")
                if response.status_code == 404:
                    print(f"   🔍 Endpoint not found")
                elif response.status_code == 422:
                    print(f"   🔍 Validation error - check parameters")
                
        except requests.exceptions.ConnectionError:
            print(f"   ❌ Connection failed - is backend running?")
        except requests.exceptions.Timeout:
            print(f"   ❌ Request timed out")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print(f"\n❌ No working endpoints found!")
    return None

def test_backend_health():
    """Test if backend is running."""
    try:
        response = requests.get("http://localhost:8000/api", timeout=5)
        if response.status_code == 200:
            print("✅ Backend is running and responding")
            data = response.json()
            print(f"   API Version: {data.get('message', 'Unknown')}")
            return True
        else:
            print(f"❌ Backend responded with status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Backend connection failed: {e}")
        return False

if __name__ == "__main__":
    print("🔧 BACKEND CONNECTION TEST")
    print("=" * 50)
    
    # Test 1: Backend health
    print("\n1. Testing backend connection...")
    backend_ok = test_backend_health()
    
    if not backend_ok:
        print("\n❌ Backend is not running or not accessible.")
        print("   Please start the backend with: python backend/main.py")
        exit(1)
    
    # Test 2: Image serving endpoints
    print("\n" + "=" * 50)
    working_endpoint = test_image_endpoints()
    
    if working_endpoint:
        print(f"\n✅ SUCCESS! Working endpoint found: {working_endpoint}")
        print("\nYou can update the frontend to use this endpoint.")
    else:
        print(f"\n❌ FAILED! No working endpoints found.")
        print("\nPossible issues:")
        print("- Image serving endpoint not registered properly")
        print("- Path encoding issues")
        print("- Backend routing problems") 