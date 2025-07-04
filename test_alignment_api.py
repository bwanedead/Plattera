#!/usr/bin/env python3
"""
Test script to verify alignment API functionality
"""

import requests
import json
import sys

def test_alignment_api():
    """Test the alignment API with sample data"""
    
    # Sample drafts for testing - with actual differences
    test_drafts = [
        {
            "draft_id": "Draft_1",
            "blocks": [
                {
                    "id": "legal_text",
                    "text": "This Indenture, Made this 3rd day of August, A.D. 1915, by and between Harriet Rickard, a widow, of the County of Albany, State of Wyoming, party of the first part, and Laramie Water Company, a corporation formed and existing under and by virtue of the laws of the State of Wyoming, having its office at Laramie, in the county of Albany and State of Wyoming, party of the second part, witnesseth:"
                }
            ]
        },
        {
            "draft_id": "Draft_2", 
            "blocks": [
                {
                    "id": "legal_text",
                    "text": "This Indenture, Made this 3rd day of August, A.D. 1915, by and between Harriet Rickard, a widow, of the County of Albany, State of Wyoming, party of the first part, and Laramie Water Company, a corporation formed and existing under and by virtue of the laws of the State of Wyoming, having its office at Laramie, in the county of Albany and State of Wyoming, party of the second part, witnesseth:"
                }
            ]
        },
        {
            "draft_id": "Draft_3",
            "blocks": [
                {
                    "id": "legal_text", 
                    "text": "This Indenture, Made this 3rd day of August, A.D. 1915, by and between Harriet Rickard, a widow, of the County of Albany, State of Wyoming, party of the first part, and Laramie Water Company, a corporation formed and existing under and by virtue of the laws of the State of Wyoming, having its office at Laramie, in the county of Albany and State of Wyoming, party of the second part, witnesseth:"
                }
            ]
        }
    ]
    
    # API endpoint
    url = "http://localhost:8000/api/alignment/align-drafts"
    
    # Request payload
    payload = {
        "drafts": test_drafts,
        "generate_visualization": True,
        "consensus_strategy": "highest_confidence"
    }
    
    try:
        print("🚀 Testing alignment API...")
        print(f"URL: {url}")
        
        response = requests.post(url, json=payload)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ API call successful!")
            print(f"Success: {result.get('success')}")
            print(f"Processing time: {result.get('processing_time')}")
            
            # Check for key fields
            if 'confidence_results' in result:
                print("✅ confidence_results present")
                confidence_results = result['confidence_results']
                print(f"   confidence_results type: {type(confidence_results)}")
                print(f"   confidence_results keys: {list(confidence_results.keys()) if isinstance(confidence_results, dict) else 'Not a dict'}")
                
                if isinstance(confidence_results, dict) and 'block_confidences' in confidence_results:
                    print("✅ block_confidences present")
                    block_confidences = confidence_results['block_confidences']
                    for block_id, block_data in block_confidences.items():
                        print(f"   Block {block_id}:")
                        print(f"     Scores: {len(block_data.get('scores', []))}")
                        print(f"     Confidence levels: {len(block_data.get('confidence_levels', []))}")
                        print(f"     Token agreements: {len(block_data.get('token_agreements', []))}")
                        
                        # Show first few scores and levels
                        scores = block_data.get('scores', [])
                        levels = block_data.get('confidence_levels', [])
                        if scores:
                            print(f"     First 5 scores: {scores[:5]}")
                            print(f"     First 5 levels: {levels[:5]}")
                else:
                    print("❌ block_confidences missing or wrong type")
            else:
                print("❌ confidence_results missing")
                
            if 'alignment_results' in result:
                print("✅ alignment_results present")
                alignment_results = result['alignment_results']
                print(f"   alignment_results type: {type(alignment_results)}")
                print(f"   alignment_results keys: {list(alignment_results.keys()) if isinstance(alignment_results, dict) else 'Not a dict'}")
                
                if isinstance(alignment_results, dict) and 'blocks' in alignment_results:
                    print("✅ alignment blocks present")
                    blocks = alignment_results['blocks']
                    for block_id, block_data in blocks.items():
                        print(f"   Block {block_id}:")
                        aligned_sequences = block_data.get('aligned_sequences', [])
                        print(f"     Aligned sequences: {len(aligned_sequences)}")
                        for seq in aligned_sequences:
                            tokens = seq.get('tokens', [])
                            print(f"       {seq.get('draft_id')}: {len(tokens)} tokens")
                            if tokens:
                                print(f"         First 5 tokens: {tokens[:5]}")
                else:
                    print("❌ alignment blocks missing or wrong type")
            else:
                print("❌ alignment_results missing")
                
            # Print summary
            if 'summary' in result:
                print("✅ Summary:")
                summary = result['summary']
                for key, value in summary.items():
                    print(f"   {key}: {value}")
                    
        else:
            print(f"❌ API call failed with status {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error testing API: {e}")
        return False
        
    return True

if __name__ == "__main__":
    success = test_alignment_api()
    sys.exit(0 if success else 1) 