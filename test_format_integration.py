#!/usr/bin/env python3
"""
Test script to verify format reconstruction integration - Direct tokenizer test
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from backend.alignment.json_draft_tokenizer import JsonDraftTokenizer
from backend.alignment.format_mapping import FormatMapper

def test_format_mapping_directly():
    """Test format mapping directly without going through the complex JSON parsing"""
    
    print("🧪 Testing format mapping directly...")
    
    # Test the format mapper directly
    format_mapper = FormatMapper()
    
    # Test text with formatting
    test_text = "Beginning at N.37°15'W. thence along the boundary"
    print(f"📋 Input text: {test_text}")
    
    # Create tokenizer and tokenize
    tokenizer = JsonDraftTokenizer()
    tokens = tokenizer._tokenize_legal_text(test_text)
    print(f"📝 Tokenized: {tokens}")
    
    # Create format mapping
    mapping = format_mapper.create_mapping("test_draft", test_text, tokens)
    print(f"🗺️ Format mapping created: {len(mapping.token_positions)} positions")
    
    # Test reconstruction
    reconstructed = format_mapper.reconstruct_formatted_text(tokens, mapping, list(range(len(tokens))))
    print(f"🔧 Reconstructed: {reconstructed}")
    
    # Check if formatting is preserved
    if 'N.37°15\'W.' in reconstructed:
        print("🎯 SUCCESS: Format mapping preserves original formatting!")
    else:
        print("❌ FAILURE: Format mapping does not preserve formatting")
        print(f"   Expected: N.37°15'W.")
        print(f"   Got: {reconstructed}")
    
    return reconstructed

def test_simple_alignment():
    """Test a simple alignment workflow that bypasses the JSON parsing issue"""
    
    print("\n🧪 Testing simple alignment workflow...")
    
    # Create a simple test that uses the tokenizer's create_sample_json_drafts
    from backend.alignment.json_draft_tokenizer import create_sample_json_drafts
    from backend.alignment.biopython_engine import BioPythonAlignmentEngine
    
    # Use the built-in sample drafts which are known to work
    sample_drafts = create_sample_json_drafts()
    print(f"📋 Using {len(sample_drafts)} sample drafts")
    
    # Print first draft to see format
    print(f"📝 Sample draft format: {sample_drafts[0]}")
    
    # Create engine and process
    engine = BioPythonAlignmentEngine()
    results = engine.align_drafts(sample_drafts, generate_visualization=False)
    
    if results['success']:
        print("✅ Alignment successful!")
        
        # Check if format reconstruction is available
        format_reconstruction = results.get('format_reconstruction', {})
        if format_reconstruction.get('reconstruction_available', False):
            print("✅ Format reconstruction available!")
            
            # Check alignment results for formatted tokens
            alignment_results = results.get('alignment_results', {})
            blocks = alignment_results.get('blocks', {})
            
            print(f"📋 Found blocks: {list(blocks.keys())}")
            
            for block_key, block_data in blocks.items():
                sequences = block_data.get('aligned_sequences', [])
                print(f"📝 Block '{block_key}' has {len(sequences)} sequences")
                
                for seq in sequences:
                    tokens = seq.get('tokens', [])
                    draft_id = seq.get('draft_id', 'unknown')
                    
                    print(f"📝 {draft_id} tokens: {tokens}")
                    
                    # Test frontend text extraction logic
                    non_gap_tokens = [t for t in tokens if t and t != '-']
                    reconstructed_text = ' '.join(non_gap_tokens)
                    print(f"🔧 Frontend would show: {reconstructed_text}")
                    
        else:
            print("⚠️ Format reconstruction not available")
    else:
        print(f"❌ Alignment failed: {results.get('error', 'Unknown error')}")

if __name__ == "__main__":
    # Test format mapping directly first
    test_format_mapping_directly()
    
    # Then test with sample drafts that are known to work
    test_simple_alignment() 