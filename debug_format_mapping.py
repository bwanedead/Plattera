#!/usr/bin/env python3
"""
Debug Format Mapping - Check Original Formatted Tokens
"""

import requests
import json
import sys
import os

# Add backend to path
sys.path.append('backend')

def test_format_mapping():
    """Test if original formatted tokens are being properly extracted"""
    
    print("🔧 Testing Format Mapping Original Tokens...")
    
    # Test with legal text image
    image_path = 'sample text image/legal_text_image.jpg'
    
    if not os.path.exists(image_path):
        print(f"❌ Test image not found: {image_path}")
        return False
    
    url = "http://localhost:8000/api/alignment/align-drafts"
    
    try:
        with open(image_path, 'rb') as f:
            files = {'file': f}
            data = {'process_format': 'true'}
            response = requests.post(url, files=files, data=data)
        
        if response.status_code != 200:
            print(f"❌ API call failed with status {response.status_code}")
            return False
        
        result = response.json()
        
        if not result.get('success'):
            print("❌ API returned failure")
            return False
        
        # Check alignment results
        alignment_results = result.get('alignment_results', {})
        blocks = alignment_results.get('blocks', {})
        
        if not blocks:
            print("❌ No alignment blocks found")
            return False
        
        print(f"✅ Found {len(blocks)} alignment blocks")
        
        # Check each block for original formatted tokens
        for block_id, block_data in blocks.items():
            print(f"\n📋 Block: {block_id}")
            
            sequences = block_data.get('aligned_sequences', [])
            print(f"   Sequences: {len(sequences)}")
            
            for seq in sequences:
                draft_id = seq.get('draft_id')
                tokens = seq.get('tokens', [])
                original_formatted_tokens = seq.get('original_formatted_tokens', [])
                
                print(f"\n   🔍 {draft_id}:")
                print(f"      Token count: {len(tokens)}")
                print(f"      Original formatted count: {len(original_formatted_tokens)}")
                
                # Look for specific formatting patterns
                formatted_examples = []
                degree_symbols = []
                parentheses = []
                decimals = []
                
                for i, token in enumerate(original_formatted_tokens):
                    if token and token != '-':
                        # Check for degree symbols
                        if '°' in token:
                            degree_symbols.append(f"[{i}] {token}")
                        # Check for parentheses  
                        if '(' in token or ')' in token:
                            parentheses.append(f"[{i}] {token}")
                        # Check for decimals
                        if '.' in token and any(c.isdigit() for c in token):
                            decimals.append(f"[{i}] {token}")
                        
                        # Collect first 10 examples
                        if len(formatted_examples) < 10:
                            formatted_examples.append(f"[{i}] {token}")
                
                print(f"      First 10 formatted tokens: {formatted_examples[:10]}")
                
                if degree_symbols:
                    print(f"      ✅ Degree symbols found: {degree_symbols[:5]}")
                else:
                    print(f"      ❌ No degree symbols found")
                
                if parentheses:
                    print(f"      ✅ Parentheses found: {parentheses[:5]}")
                else:
                    print(f"      ❌ No parentheses found")
                    
                if decimals:
                    print(f"      ✅ Decimals found: {decimals[:5]}")
                else:
                    print(f"      ❌ No decimals found")
                
                # Compare with normalized tokens
                print(f"\n      Comparison (first 10 positions):")
                for i in range(min(10, len(tokens), len(original_formatted_tokens))):
                    norm_token = tokens[i] if i < len(tokens) else "N/A"
                    orig_token = original_formatted_tokens[i] if i < len(original_formatted_tokens) else "N/A"
                    if norm_token != orig_token:
                        print(f"        [{i}] '{norm_token}' → '{orig_token}'")
        
        print("\n✅ Format mapping test completed!")
        return True
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        return False

if __name__ == "__main__":
    success = test_format_mapping()
    exit(0 if success else 1) 