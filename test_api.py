#!/usr/bin/env python3
"""
Simple test script for the text-to-schema API endpoint
"""
import requests
import json

def test_text_to_schema_api():
    """Test the text-to-schema conversion API"""
    
    # API endpoint
    url = "http://localhost:8000/api/text-to-schema/convert"
    
    # Test payload
    payload = {
        "text": "Situated in the Southwest Quarter of the Northwest Quarter of Section Two (2), Township Fourteen (14) North, Range Seventy-five (75) West of the Sixth Principal Meridian, Albany County, Wyoming. Beginning at a point on the west boundary of Section Two (2), said point being 50 feet S.21°30'E. from the center line of the South Canal, whence the Northwest corner bears N. 4°00'W., 1,638 feet distant; thence N. 68°30'E. parallel to and 50 feet distant from the center line of said canal 542 feet more or less.",
        "model": "gpt-4o"
    }
    
    print("🔧 Testing text-to-schema API endpoint...")
    print(f"📡 URL: {url}")
    print(f"📏 Text length: {len(payload['text'])} characters")
    print(f"🤖 Model: {payload['model']}")
    print()
    
    try:
        # Make the API call
        response = requests.post(url, json=payload, timeout=60)
        
        print(f"📊 Response Status: {response.status_code}")
        print(f"📋 Response Headers: {dict(response.headers)}")
        print()
        
        if response.status_code == 200:
            result = response.json()
            print("✅ SUCCESS! API call completed")
            print(f"📄 Status: {result.get('status')}")
            print(f"🤖 Model Used: {result.get('model_used')}")
            print(f"🔢 Tokens Used: {result.get('tokens_used')}")
            print(f"⚠️ Validation Warnings: {len(result.get('validation_warnings', []))}")
            
            if result.get('structured_data'):
                structured_data = result['structured_data']
                print("\n🏗️ Structured Data Extract:")
                print(f"  📍 Parcel ID: {structured_data.get('parcel_id')}")
                if 'plss_description' in structured_data:
                    plss = structured_data['plss_description']
                    print(f"  🌍 State: {plss.get('state')}")
                    print(f"  🏘️ County: {plss.get('county')}")
                    print(f"  📏 Township: {plss.get('township')}")
                    print(f"  📏 Range: {plss.get('range')}")
                    print(f"  📍 Section: {plss.get('section')}")
                
                if 'metes_and_bounds' in structured_data:
                    mb = structured_data['metes_and_bounds']
                    courses = mb.get('boundary_courses', [])
                    print(f"  🗺️ Boundary Courses: {len(courses)}")
                    for i, course in enumerate(courses[:2]):  # Show first 2 courses
                        print(f"    {i+1}. {course.get('course')} - {course.get('distance')} {course.get('distance_units')}")
            
            print(f"\n📄 Full Response JSON (truncated):")
            print(json.dumps(result, indent=2)[:1000] + "..." if len(json.dumps(result)) > 1000 else json.dumps(result, indent=2))
            
        else:
            print(f"❌ ERROR! Status Code: {response.status_code}")
            print(f"📄 Response Text: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"💥 REQUEST ERROR: {str(e)}")
    except Exception as e:
        print(f"💥 UNEXPECTED ERROR: {str(e)}")

if __name__ == "__main__":
    test_text_to_schema_api() 