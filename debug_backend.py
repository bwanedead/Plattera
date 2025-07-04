#!/usr/bin/env python3
"""
Debug script to test the alignment engine directly
"""

import sys
import os
sys.path.append('backend')

def test_alignment_engine():
    """Test the alignment engine directly"""
    
    try:
        from alignment import BioPythonAlignmentEngine
        
        # Sample drafts
        test_drafts = [
            {
                "draft_id": "Draft_1",
                "blocks": [
                    {
                        "id": "legal_text",
                        "text": "This is a test document with some text."
                    }
                ]
            },
            {
                "draft_id": "Draft_2", 
                "blocks": [
                    {
                        "id": "legal_text",
                        "text": "This is a test document with different text."
                    }
                ]
            },
            {
                "draft_id": "Draft_3",
                "blocks": [
                    {
                        "id": "legal_text", 
                        "text": "This is a test document with some other text."
                    }
                ]
            }
        ]
        
        print("🧪 Testing BioPython engine directly...")
        
        # Initialize engine
        engine = BioPythonAlignmentEngine()
        
        # Run alignment
        results = engine.align_drafts(test_drafts, generate_visualization=True)
        
        print(f"✅ Alignment complete!")
        print(f"Success: {results.get('success')}")
        print(f"Processing time: {results.get('processing_time')}")
        print(f"Result keys: {list(results.keys())}")
        
        # Check specific keys
        if 'confidence_results' in results:
            print("✅ confidence_results present")
            confidence_results = results['confidence_results']
            print(f"   Type: {type(confidence_results)}")
            print(f"   Keys: {list(confidence_results.keys())}")
            
            if 'block_confidences' in confidence_results:
                print("✅ block_confidences present")
                block_confidences = confidence_results['block_confidences']
                for block_id, block_data in block_confidences.items():
                    print(f"   Block {block_id}:")
                    print(f"     Keys: {list(block_data.keys())}")
                    print(f"     Scores: {len(block_data.get('scores', []))}")
                    print(f"     First 5 scores: {block_data.get('scores', [])[:5]}")
                    
        else:
            print("❌ confidence_results missing")
            
        if 'alignment_results' in results:
            print("✅ alignment_results present")
            alignment_results = results['alignment_results']
            print(f"   Type: {type(alignment_results)}")
            print(f"   Keys: {list(alignment_results.keys())}")
            
            if 'blocks' in alignment_results:
                print("✅ alignment blocks present")
                blocks = alignment_results['blocks']
                for block_id, block_data in blocks.items():
                    print(f"   Block {block_id}:")
                    print(f"     Keys: {list(block_data.keys())}")
                    aligned_sequences = block_data.get('aligned_sequences', [])
                    print(f"     Aligned sequences: {len(aligned_sequences)}")
                    for seq in aligned_sequences:
                        tokens = seq.get('tokens', [])
                        print(f"       {seq.get('draft_id')}: {len(tokens)} tokens")
                        if tokens:
                            print(f"         First 5 tokens: {tokens[:5]}")
        else:
            print("❌ alignment_results missing")
            
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_alignment_engine()
    sys.exit(0 if success else 1) 