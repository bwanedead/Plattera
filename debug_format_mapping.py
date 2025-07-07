#!/usr/bin/env python3
"""
Debug script to test format mapping directly
"""

import sys
sys.path.append('backend')

from backend.alignment.format_mapping import FormatMapper
from backend.alignment.json_draft_tokenizer import JsonDraftTokenizer

def test_format_mapping():
    """Test format mapping with degree symbols"""
    
    # Test text with degree symbols
    test_text = "Beginning at a point on the west boundary of Section Two (2), Township Fourteen (14) North, Range Seventy-four (74) West whence the northwest corner bears N.4°00'W. 1,638 feet distant and being 50 feet S.21°30'E. from the center line"
    
    print("🔍 Testing Format Mapping")
    print(f"Original text: {test_text}")
    print()
    
    # Initialize tokenizer and format mapper
    tokenizer = JsonDraftTokenizer()
    format_mapper = FormatMapper()
    
    # Tokenize the text
    tokens = tokenizer._tokenize_legal_text(test_text)
    print(f"📋 Tokenized ({len(tokens)} tokens): {tokens}")
    print()
    
    # Show text around coordinate patterns
    print("🔍 Coordinate Pattern Analysis:")
    coord_patterns = ['N.4°00\'W.', 'S.21°30\'E.']
    for pattern in coord_patterns:
        if pattern in test_text:
            start_pos = test_text.find(pattern)
            end_pos = start_pos + len(pattern)
            context_start = max(0, start_pos - 20)
            context_end = min(len(test_text), end_pos + 20)
            context = test_text[context_start:context_end]
            print(f"   Pattern '{pattern}' at {start_pos}-{end_pos}")
            print(f"   Context: ...{context}...")
            
            # Find what tokens are around this position
            print(f"   Looking for tokens around position {start_pos}")
            
            # Reconstruct token positions manually
            normalized_text = tokenizer._normalize_text(test_text)
            print(f"   Normalized text: {normalized_text}")
            
            # Find the normalized version of the pattern
            pattern_start_in_norm = normalized_text.find('n 4 00 w')
            if pattern_start_in_norm >= 0:
                print(f"   Found 'n 4 00 w' at position {pattern_start_in_norm} in normalized text")
                
                # Count tokens up to this position
                tokens_before = normalized_text[:pattern_start_in_norm].split()
                print(f"   Tokens before pattern: {len(tokens_before)}")
                print(f"   Tokens at pattern position: {tokens[len(tokens_before):len(tokens_before)+4]}")
            
            pattern_start_in_norm = normalized_text.find('s 21 30 e')
            if pattern_start_in_norm >= 0:
                print(f"   Found 's 21 30 e' at position {pattern_start_in_norm} in normalized text")
                
                # Count tokens up to this position
                tokens_before = normalized_text[:pattern_start_in_norm].split()
                print(f"   Tokens before pattern: {len(tokens_before)}")
                print(f"   Tokens at pattern position: {tokens[len(tokens_before):len(tokens_before)+4]}")
    
    print()
    
    # Create format mapping
    mapping = format_mapper.create_mapping("test_draft", test_text, tokens)
    print(f"🎯 Format mapping created with {len(mapping.token_positions)} position mappings")
    
    # Show mappings
    print("\n📊 Token Position Mappings:")
    for pos in mapping.token_positions:
        if pos.original_text != pos.normalized_text:
            print(f"   {pos.token_index}: '{pos.normalized_text}' → '{pos.original_text}'")
    
    # Test special pattern detection
    print("\n🔍 Special Pattern Detection:")
    patterns = format_mapper._find_special_patterns(test_text)
    for pattern in patterns:
        print(f"   Pattern: '{pattern['original']}' at {pattern['start']}-{pattern['end']}")
    
    # Test reconstruction
    print("\n🔧 Testing Reconstruction:")
    reconstructed = format_mapper.reconstruct_formatted_text(
        tokens, mapping, list(range(len(tokens)))
    )
    print(f"Reconstructed: {reconstructed}")
    
    # Show detailed reconstruction
    print("\n🔍 Detailed Reconstruction Analysis:")
    for i, token in enumerate(tokens):
        pos = mapping.get_position_for_token(i)
        if pos:
            print(f"   Token {i}: '{token}' → '{pos.original_text}' (from mapping)")
        else:
            print(f"   Token {i}: '{token}' → '{token}' (no mapping)")
    
    # Check if degree symbols are preserved
    has_degrees = '°' in reconstructed
    has_parentheses = '(' in reconstructed and ')' in reconstructed
    has_comma_numbers = '1,638' in reconstructed
    
    print(f"\n✅ Results:")
    print(f"   Degree symbols preserved: {has_degrees}")
    print(f"   Parentheses preserved: {has_parentheses}")
    print(f"   Comma numbers preserved: {has_comma_numbers}")

if __name__ == "__main__":
    test_format_mapping() 