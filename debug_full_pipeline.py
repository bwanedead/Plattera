#!/usr/bin/env python3
"""
Debug script to test the full alignment pipeline
"""

import sys
sys.path.append('backend')

from backend.alignment.biopython_engine import BioPythonAlignmentEngine

def test_full_pipeline():
    """Test the complete alignment pipeline with degree symbols"""
    
    # Test drafts with degree symbols
    test_drafts = [
        {
            "draft_id": "Draft_1",
            "blocks": [
                {
                    "id": "legal_text",
                    "text": "Beginning at a point on the west boundary of Section Two (2), Township Fourteen (14) North, Range Seventy-four (74) West whence the northwest corner bears N.4°00'W. 1,638 feet distant and being 50 feet S.21°30'E. from the center line"
                }
            ]
        },
        {
            "draft_id": "Draft_2", 
            "blocks": [
                {
                    "id": "legal_text",
                    "text": "Beginning at a point on the west boundary of Section Two (2), Township Fourteen (14) North, Range Seventy-four (74) West whence the northwest corner bears N.4°00'W. 1,638 feet distant and being 50 feet S.21°30'E. from the center line"
                }
            ]
        }
    ]
    
    print("🔍 Testing Full Alignment Pipeline")
    print("=" * 50)
    
    # Initialize engine
    engine = BioPythonAlignmentEngine()
    
    # Run alignment
    print("🚀 Running alignment...")
    result = engine.align_drafts(test_drafts, generate_visualization=False)
    
    if result['success']:
        print("✅ Alignment successful!")
        
        # Check alignment results
        alignment_results = result['alignment_results']
        blocks = alignment_results.get('blocks', {})
        
        for block_id, block_data in blocks.items():
            print(f"\n📋 Block: {block_id}")
            
            aligned_sequences = block_data.get('aligned_sequences', [])
            for seq in aligned_sequences:
                draft_id = seq.get('draft_id')
                tokens = seq.get('tokens', [])
                formatting_applied = seq.get('formatting_applied', False)
                
                print(f"\n🔍 {draft_id}:")
                print(f"   Formatting applied: {formatting_applied}")
                print(f"   Token count: {len(tokens)}")
                
                # Look for degree symbols
                degree_tokens = [t for t in tokens if '°' in str(t)]
                paren_tokens = [t for t in tokens if '(' in str(t) and ')' in str(t)]
                comma_tokens = [t for t in tokens if ',' in str(t) and str(t).replace(',', '').isdigit()]
                
                print(f"   Degree symbols: {len(degree_tokens)} - {degree_tokens[:3]}")
                print(f"   Parentheses: {len(paren_tokens)} - {paren_tokens[:3]}")
                print(f"   Comma numbers: {len(comma_tokens)} - {comma_tokens[:3]}")
                
                # Show tokens around where degree symbols should be
                print(f"   Tokens 25-35: {tokens[25:35]}")
                
                # Join tokens to see reconstructed text
                non_gap_tokens = [t for t in tokens if t != '-']
                reconstructed_text = ' '.join(non_gap_tokens)
                
                # Check specific patterns
                has_n_degree = 'N.4°00\'W.' in reconstructed_text or 'n 4°00\' w' in reconstructed_text.lower()
                has_s_degree = 'S.21°30\'E.' in reconstructed_text or 's 21°30\' e' in reconstructed_text.lower()
                
                print(f"   Has N.4°00'W. pattern: {has_n_degree}")
                print(f"   Has S.21°30'E. pattern: {has_s_degree}")
                
                # Show a sample of the reconstructed text around coordinates
                coord_start = reconstructed_text.find('bears')
                if coord_start >= 0:
                    coord_sample = reconstructed_text[coord_start:coord_start + 100]
                    print(f"   Coordinate area: ...{coord_sample}...")
        
        # Check format reconstruction data
        if 'format_reconstruction' in result:
            print(f"\n🎨 Format reconstruction available: {result['format_reconstruction'].get('reconstruction_available', False)}")
            
    else:
        print(f"❌ Alignment failed: {result.get('error')}")

if __name__ == "__main__":
    test_full_pipeline() 