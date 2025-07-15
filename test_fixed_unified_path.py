#!/usr/bin/env python3
"""
Test the fixed unified path tokenizer
"""

import sys
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from alignment.unified_path_tokenizer_fixed import UnifiedPathTokenizerFixed, CurrentApproachTokenizer
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def test_problematic_cases():
    """Test the specific cases that were failing"""
    
    current = CurrentApproachTokenizer()
    fixed_unified = UnifiedPathTokenizerFixed()
    
    test_cases = [
        "A.D. 1915, by and between",
        "N. 4°00'W., 1,638 feet distant", 
        "S.21°30'E. from the center",
        "Seventy-four (74) West",
        "Township Fourteen (14) North",
        "Right of Way Deed"
    ]
    
    total_tests = 0
    matches = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n🧪 TEST {i}: '{test_case}'")
        print("-" * 60)
        
        # Current approach
        current_tokens = current.tokenize_current_approach(test_case)
        print(f"Current:       {current_tokens}")
        
        # Fixed unified approach  
        formatted, unified_tokens, mappings = fixed_unified.tokenize_with_unified_path(test_case)
        print(f"Fixed Unified: {unified_tokens}")
        print(f"Formatted:     {formatted}")
        
        # Compare
        total_tests += 1
        if current_tokens == unified_tokens:
            print(f"✅ MATCH!")
            matches += 1
            
            # Show mappings
            print(f"Mappings:")
            for mapping in mappings:
                print(f"  [{mapping.token_id}]: '{mapping.formatted_token}' → {mapping.normalized_tokens}")
        else:
            print(f"❌ MISMATCH!")
            print(f"  Differences:")
            max_len = max(len(current_tokens), len(unified_tokens))
            for j in range(max_len):
                curr = current_tokens[j] if j < len(current_tokens) else '<MISSING>'
                unif = unified_tokens[j] if j < len(unified_tokens) else '<MISSING>'
                if curr != unif:
                    print(f"    [{j}]: '{curr}' ≠ '{unif}'")
    
    print(f"\n📊 SUMMARY: {matches}/{total_tests} tests passed ({matches/total_tests*100:.1f}%)")
    
    if matches == total_tests:
        print("🎉 ALL TESTS PASSED! Fixed unified path works correctly!")
    else:
        print("⚠️ Some tests still failing - need more investigation")

if __name__ == "__main__":
    test_problematic_cases() 