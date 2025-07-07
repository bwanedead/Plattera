#!/usr/bin/env python3
"""
Focused test to debug degree symbol preservation
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from backend.alignment.format_mapping import FormatMapper
from backend.alignment.json_draft_tokenizer import JsonDraftTokenizer
from nltk.tokenize import word_tokenize

def test_degree_symbol_specifically():
    """Test specifically with degree symbols"""
    
    # Simple test with just degree symbols
    test_text = "bears N.4°00'W. distant"
    
    print("🔍 DEBUGGING DEGREE SYMBOLS")
    print("=" * 40)
    print(f"Test text: {test_text}")
    
    # Check NLTK tokenization on original
    nltk_original = word_tokenize(test_text)
    print(f"NLTK original: {nltk_original}")
    
    # Check tokenizer normalization
    tokenizer = JsonDraftTokenizer()
    normalized = tokenizer._normalize_text(test_text)
    print(f"Normalized: {normalized}")
    
    # Check NLTK tokenization on normalized
    nltk_normalized = word_tokenize(normalized)
    print(f"NLTK normalized: {nltk_normalized}")
    
    # Check final tokens from tokenizer
    final_tokens = tokenizer._tokenize_legal_text(test_text)
    print(f"Final tokens: {final_tokens}")
    
    # Check format mapping
    format_mapper = FormatMapper()
    mapping = format_mapper.create_mapping("test", test_text, final_tokens)
    
    print(f"\nFormat mapping ({len(mapping.token_positions)} positions):")
    for pos in mapping.token_positions:
        print(f"  Token {pos.token_index}: '{pos.normalized_text}' -> '{pos.original_text}'")
    
    # Test reconstruction
    reconstructed = format_mapper.reconstruct_formatted_text(
        final_tokens, mapping, list(range(len(final_tokens)))
    )
    print(f"\nReconstructed: {reconstructed}")
    
    # Analysis
    print(f"\nAnalysis:")
    if 'N.4°00\'W.' in test_text:
        print(f"✓ Original contains: N.4°00'W.")
    if 'N.4°00\'W.' in reconstructed:
        print(f"✅ Reconstructed contains: N.4°00'W.")
    else:
        print(f"❌ Reconstructed missing: N.4°00'W.")
        
    # Check what happened to the degree pattern
    if 'n' in final_tokens and '4' in final_tokens:
        print(f"❌ Degree pattern was split into separate tokens: n, 4, 00, w")
    
    return final_tokens, mapping

def test_format_mapper_patterns():
    """Test the format mapper's regex patterns"""
    
    print(f"\n🔍 TESTING FORMAT MAPPER PATTERNS")
    print("=" * 40)
    
    format_mapper = FormatMapper()
    
    test_patterns = [
        "N.4°00'W.",
        "S.21°30'E.", 
        "N.37°15'W.",
        "1,638",
        "(2)"
    ]
    
    for pattern in test_patterns:
        print(f"\nTesting pattern: {pattern}")
        
        # Check if any regex matches
        matches = []
        for i, regex in enumerate(format_mapper.compiled_patterns):
            if regex.search(pattern):
                matches.append(f"Pattern {i}: {format_mapper.formatting_patterns[i]}")
        
        if matches:
            print(f"  ✅ Matches: {matches}")
        else:
            print(f"  ❌ No regex matches found")

def test_with_alignment_engine():
    """Test the improved format reconstruction with alignment engine"""
    
    test_drafts = [
        {
            "draft_id": "Draft_1",
            "blocks": [
                {
                    "id": "block_1",
                    "text": "bears N.4°00'W. distant and S.21°30'E. with 1,638 acres"
                }
            ]
        },
        {
            "draft_id": "Draft_2", 
            "blocks": [
                {
                    "id": "block_1",
                    "text": "bears N.4°00'W. distant and S.21°30'E. with 1,638 acres"
                }
            ]
        }
    ]
    
    print(f"\n🧪 TESTING IMPROVED FORMAT RECONSTRUCTION")
    print("=" * 50)
    
    try:
        from backend.alignment.biopython_engine import BioPythonAlignmentEngine
        engine = BioPythonAlignmentEngine()
        result = engine.align_drafts(test_drafts)
        
        if result['success']:
            print("✅ Alignment completed")
            
            blocks = result.get('alignment_results', {}).get('blocks', {})
            for block_id, block_data in blocks.items():
                sequences = block_data.get('aligned_sequences', [])
                for seq in sequences:
                    draft_id = seq['draft_id']
                    tokens = seq.get('tokens', [])
                    formatting_applied = seq.get('formatting_applied', False)
                    
                    clean_tokens = [t for t in tokens if t != '-']
                    text = ' '.join(clean_tokens)
                    
                    print(f"\n{draft_id}: {text}")
                    print(f"Formatting applied: {formatting_applied}")
                    print(f"Raw tokens: {clean_tokens}")
                    
                    # Check for issues
                    issues = []
                    if 'N.4°00\'W.' in text and ('4' in clean_tokens or '00' in clean_tokens):
                        issues.append("❌ Duplicate degree tokens remain")
                    elif 'N.4°00\'W.' in text:
                        issues.append("✅ N.4°00'W. clean")
                        
                    if 'S.21°30\'E.' in text and ('21' in clean_tokens or '30' in clean_tokens):
                        issues.append("❌ Duplicate minute tokens remain")
                    elif 'S.21°30\'E.' in text:
                        issues.append("✅ S.21°30'E. clean")
                        
                    if '1,638' in text:
                        issues.append("✅ 1,638 preserved")
                    
                    for issue in issues:
                        print(f"  {issue}")
                        
        else:
            print(f"❌ Alignment failed: {result.get('error')}")
            
    except Exception as e:
        print(f"💥 Error: {e}")
        import traceback
        traceback.print_exc()

def test_final_comprehensive():
    """Final comprehensive test with legal document patterns"""
    
    test_drafts = [
        {
            "draft_id": "Draft_1",
            "blocks": [
                {
                    "id": "block_1",
                    "text": "Beginning at Section Two (2), Township Fourteen (14) North whence the northwest corner bears N.4°00'W. 1,638 feet distant and being 50 feet S.21°30'E. from the center line thence N.68°30'E. parallel to and 50 feet distant"
                }
            ]
        },
        {
            "draft_id": "Draft_2", 
            "blocks": [
                {
                    "id": "block_1",
                    "text": "Beginning at Section Two (2), Township Fourteen (14) North whence the northwest corner bears N.4°00'W. 1,638 feet distant and being 50 feet S.21°30'E. from the center line thence N.68°30'E. parallel to and 50 feet distant"
                }
            ]
        }
    ]
    
    print(f"\n🎯 FINAL COMPREHENSIVE TEST")
    print("=" * 50)
    
    try:
        from backend.alignment.biopython_engine import BioPythonAlignmentEngine
        engine = BioPythonAlignmentEngine()
        result = engine.align_drafts(test_drafts)
        
        if result['success']:
            print("✅ Alignment completed successfully")
            
            blocks = result.get('alignment_results', {}).get('blocks', {})
            for block_id, block_data in blocks.items():
                sequences = block_data.get('aligned_sequences', [])
                for seq in sequences:
                    draft_id = seq['draft_id']
                    tokens = seq.get('tokens', [])
                    formatting_applied = seq.get('formatting_applied', False)
                    
                    clean_tokens = [t for t in tokens if t != '-']
                    text = ' '.join(clean_tokens)
                    
                    print(f"\n{draft_id}:")
                    print(f"Text: {text}")
                    print(f"Formatting applied: {formatting_applied}")
                    
                    # Check all key patterns
                    patterns_found = []
                    
                    if 'N.4°00\'W.' in text:
                        patterns_found.append("✅ N.4°00'W.")
                    if 'S.21°30\'E.' in text:
                        patterns_found.append("✅ S.21°30'E.")
                    if 'N.68°30\'E.' in text:
                        patterns_found.append("✅ N.68°30'E.")
                    if '(2)' in text:
                        patterns_found.append("✅ (2)")
                    if '(14)' in text:
                        patterns_found.append("✅ (14)")
                    if '1,638' in text:
                        patterns_found.append("✅ 1,638")
                    
                    print(f"Patterns: {' | '.join(patterns_found)}")
                    
                    # Check for any remaining duplicate tokens
                    duplicate_issues = []
                    degree_numbers = ['4', '00', '21', '30', '68']
                    for num in degree_numbers:
                        if num in clean_tokens and any(f'{num}°' in token for token in clean_tokens):
                            duplicate_issues.append(f"❌ Duplicate {num}")
                    
                    if duplicate_issues:
                        print(f"Issues: {' | '.join(duplicate_issues)}")
                    else:
                        print("✅ No duplicate tokens detected")
                        
            print(f"\n🎉 FORMAT RECONSTRUCTION: {'SUCCESS' if len(patterns_found) >= 5 else 'NEEDS WORK'}")
                        
        else:
            print(f"❌ Alignment failed: {result.get('error')}")
            
    except Exception as e:
        print(f"💥 Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_degree_symbol_specifically()
    test_format_mapper_patterns()
    test_with_alignment_engine()
    test_final_comprehensive() 