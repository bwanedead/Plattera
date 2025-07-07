#!/usr/bin/env python3
"""
Test script to verify alignment API functionality with real legal text
"""

import requests
import json
import sys

def test_alignment_api():
    """Test the alignment API with real legal text that has formatting issues"""
    
    # Real legal text with formatting issues - this is what should be formatted
    test_drafts = [
        {
            "draft_id": "Draft_1",
            "blocks": [
                {
                    "id": "legal_text",
                    "text": "Beginning at a point on the west boundary of Section Two (2), Township Fourteen (14) North, Range Seventy-four (74) West whence the northwest corner bears N.4°00'W. 1,638 feet distant and being 50 feet S.21°30'E. from the center line of the south canal of the company thence N.68°30'E. parallel to and 50 feet distant from the center line of said canal 542 feet more or less to the North boundary of the Southwest Quarter of the Northwest Quarter of said Section Two (2), thence S.87°35'W. along the North boundary of said Southwest Quarter of the Northwest Quarter 518 feet more or less to the northwest corner of said Southwest Quarter of the Northwest Quarter thence S.4°00'E. on the west boundary of said Section Two (2), 180 feet more or less to the point of Beginning said parcel of land containing 1.9 acres more or less."
                }
            ]
        },
        {
            "draft_id": "Draft_2", 
            "blocks": [
                {
                    "id": "legal_text",
                    "text": "Beginning at a point on the west boundary of Section Two (2), Township Fourteen (14) North, Range Seventy-four (74) West whence the northwest corner bears N.4°00'W. 1,638 feet distant and being 50 feet S.21°30'E. from the center line of the south canal of the company thence N.68°30'E. parallel to and 50 feet distant from the center line of said canal 542 feet more or less to the North boundary of the Southwest Quarter of the Northwest Quarter of said Section Two (2), thence S.87°35'W. along the North boundary of said Southwest Quarter of the Northwest Quarter 518 feet more or less to the northwest corner of said Southwest Quarter of the Northwest Quarter thence S.4°00'E. on the west boundary of said Section Two (2), 180 feet more or less to the point of Beginning said parcel of land containing 1.9 acres more or less."
                }
            ]
        },
        {
            "draft_id": "Draft_3",
            "blocks": [
                {
                    "id": "legal_text", 
                    "text": "Beginning at a point on the west boundary of Section Two (2), Township Fourteen (14) North, Range Seventy-four (74) West whence the northwest corner bears N.4°00'W. 1,638 feet distant and being 50 feet S.21°30'E. from the center line of the south canal of the company thence N.68°30'E. parallel to and 50 feet distant from the center line of said canal 542 feet more or less to the North boundary of the Southwest Quarter of the Northwest Quarter of said Section Two (2), thence S.87°35'W. along the North boundary of said Southwest Quarter of the Northwest Quarter 518 feet more or less to the northwest corner of said Southwest Quarter of the Northwest Quarter thence S.4°00'E. on the west boundary of said Section Two (2), 180 feet more or less to the point of Beginning said parcel of land containing 1.9 acres more or less."
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
        print("🚀 Testing alignment API with real legal text...")
        print(f"URL: {url}")
        
        response = requests.post(url, json=payload)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ API call successful!")
            print(f"Success: {result.get('success')}")
            print(f"Processing time: {result.get('processing_time')}")
            
            # Check for format reconstruction flag
            if 'alignment_results' in result:
                alignment_results = result['alignment_results']
                print(f"✅ Format reconstruction applied: {alignment_results.get('format_reconstruction_applied', False)}")
                
                if 'blocks' in alignment_results:
                    blocks = alignment_results['blocks']
                    for block_id, block_data in blocks.items():
                        print(f"\n📋 Block {block_id}:")
                        aligned_sequences = block_data.get('aligned_sequences', [])
                        print(f"   Aligned sequences: {len(aligned_sequences)}")
                        
                        for seq in aligned_sequences:
                            draft_id = seq.get('draft_id')
                            tokens = seq.get('tokens', [])
                            formatting_applied = seq.get('formatting_applied', False)
                            
                            print(f"\n   🔍 {draft_id}:")
                            print(f"     Token count: {len(tokens)}")
                            print(f"     Formatting applied: {formatting_applied}")
                            print(f"     First 10 tokens: {tokens[:10]}")
                            print(f"     Last 10 tokens: {tokens[-10:]}")
                            
                            # Show tokens around where degree symbols should be
                            print(f"     Tokens 25-35: {tokens[25:35]}")
                            print(f"     Tokens 100-120: {tokens[100:120]}")
                            
                            # Join tokens to see the final text
                            non_gap_tokens = [t for t in tokens if t != '-']
                            reconstructed_text = ' '.join(non_gap_tokens)
                            print(f"     Reconstructed text preview: {reconstructed_text[:200]}...")
                            
                            # Look for specific coordinate patterns in the full text
                            coord_patterns = ['N.4°00\'W.', 'n 4°00\' w', 'S.21°30\'E.', 's 21°30\' e']
                            found_patterns = []
                            for pattern in coord_patterns:
                                if pattern.lower() in reconstructed_text.lower():
                                    found_patterns.append(pattern)
                            
                            print(f"     Found coordinate patterns: {found_patterns}")
                            
                            # Show area around "bears" where coordinates should be
                            bears_pos = reconstructed_text.find('bears')
                            if bears_pos >= 0:
                                coord_area = reconstructed_text[bears_pos:bears_pos + 150]
                                print(f"     Coordinate area: bears{coord_area}")
                            
                            # Check if formatting is preserved
                            has_degrees = '°' in reconstructed_text
                            has_parentheses = '(' in reconstructed_text and ')' in reconstructed_text
                            has_comma_numbers = any(f'{i},' in reconstructed_text for i in range(1000, 10000))
                            
                            print(f"     ✅ Formatting preserved:")
                            print(f"       Degree symbols: {has_degrees}")
                            print(f"       Parentheses: {has_parentheses}")
                            print(f"       Comma numbers: {has_comma_numbers}")
                            
            # Check format reconstruction data
            if 'format_reconstruction' in result:
                print(f"\n🎨 Format reconstruction data available: {result['format_reconstruction'].get('reconstruction_available', False)}")
                
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