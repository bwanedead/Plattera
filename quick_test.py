import requests
import traceback

try:
    with open('sample text image/legal_text_image.jpg', 'rb') as f:
        files = {'file': f}
        data = {'process_format': 'true'}
        response = requests.post('http://localhost:8000/api/alignment/align-drafts', files=files, data=data)
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc() 