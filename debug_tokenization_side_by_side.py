#!/usr/bin/env python3
"""
Side-by-side comparison of current vs unified path tokenization
"""

import json
import sys
import os
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from alignment.unified_path_tokenizer import UnifiedPathTokenizer, CurrentApproachTokenizer
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

def load_sample_texts():
    """Load real text samples from saved drafts"""
    saved_drafts_dir = Path("backend/saved_drafts")
    draft_file = saved_drafts_dir / "draft_1.json"
    
    if not draft_file.exists():
        print(f"❌ File not found: {draft_file}")
        return []
    
    with open(draft_file, 'r', encoding='utf-8') as f:
        draft_data = json.load(f)
    
    # Extract text samples from sections
    samples = []
    for section in draft_data["sections"]:
        if section.get("header"):
            samples.append(section["header"])
        
        body = section.get("body", "")
        if body:
            # Split into sentences and take first few
            sentences = body.split('. ')
            for sentence in sentences[:2]:
                if len(sentence.strip()) > 20:  # Only meaningful sentences
                    samples.append(sentence.strip() + '.')
    
    return samples[:8]  # Return first 8 samples

def compare_tokenization_approaches():
    """Compare current vs unified path tokenization side-by-side"""
    print("🔍 SIDE-BY-SIDE TOKENIZATION COMPARISON")
    print("="*80)
    
    # Load sample texts
    samples = load_sample_texts()
    if not samples:
        print("❌ No sample texts loaded!")
        return
    
    # Create tokenizers
    unified_tokenizer = UnifiedPathTokenizer()
    current_tokenizer = CurrentApproachTokenizer()
    
    total_tests = 0
    identical_results = 0
    
    for i, sample_text in enumerate(samples, 1):
        print(f"\n📝 TEST {i}: '{sample_text[:60]}...'")
        print("-" * 80)
        
        # Current approach
        print(f"🔵 CURRENT APPROACH:")
        current_tokens = current_tokenizer.tokenize_current_approach(sample_text)
        
        print(f"\n🟢 UNIFIED PATH APPROACH:")
        formatted_tokens, unified_tokens, mappings = unified_tokenizer.tokenize_with_unified_path(sample_text)
        
        # Compare results
        print(f"\n📊 COMPARISON:")
        print(f"   Current tokens:  {len(current_tokens):3d} → {current_tokens}")
        print(f"   Unified tokens:  {len(unified_tokens):3d} → {unified_tokens}")
        print(f"   Formatted tokens: {len(formatted_tokens):3d} → {formatted_tokens}")
        
        # Check if identical
        total_tests += 1
        if current_tokens == unified_tokens:
            print(f"   ✅ IDENTICAL RESULTS")
            identical_results += 1
        else:
            print(f"   ❌ DIFFERENT RESULTS!")
            
            # Show detailed differences
            max_len = max(len(current_tokens), len(unified_tokens))
            differences = []
            
            for j in range(max_len):
                curr = current_tokens[j] if j < len(current_tokens) else '<MISSING>'
                unif = unified_tokens[j] if j < len(unified_tokens) else '<MISSING>'
                
                if curr != unif:
                    differences.append(f"[{j}]: '{curr}' ≠ '{unif}'")
            
            print(f"   🔍 DIFFERENCES ({len(differences)}):")
            for diff in differences[:5]:  # Show first 5
                print(f"      {diff}")
            if len(differences) > 5:
                print(f"      ... and {len(differences) - 5} more")
        
        # Show token mappings for unified approach
        if mappings:
            print(f"\n🔗 UNIFIED PATH MAPPINGS:")
            for mapping in mappings[:10]:  # Show first 10
                print(f"      [{mapping.token_id}]: '{mapping.formatted_token}' → '{mapping.normalized_token}'")
            if len(mappings) > 10:
                print(f"      ... and {len(mappings) - 10} more mappings")
    
    # Summary
    print(f"\n" + "="*80)
    print(f"📈 SUMMARY:")
    print(f"   Total tests: {total_tests}")
    print(f"   Identical results: {identical_results}")
    print(f"   Different results: {total_tests - identical_results}")
    print(f"   Match rate: {(identical_results/total_tests)*100:.1f}%")
    
    if identical_results == total_tests:
        print(f"   🎉 ALL RESULTS IDENTICAL - Unified path works correctly!")
    else:
        print(f"   ⚠️ SOME DIFFERENCES FOUND - Need to investigate")

def test_specific_cases():
    """Test specific problematic cases"""
    print(f"\n" + "="*80)
    print(f"🧪 TESTING SPECIFIC PROBLEMATIC CASES")
    print("="*80)
    
    # Test cases that might cause issues
    test_cases = [
        "N. 4°00'W., 1,638 feet distant",
        "S.21°30'E. from the center line",
        "bears N. 37°00'W., 1,275 feet",
        "This Indenture, made this 3rd day",
        "Township Fourteen (14) North, Range Seventy-five (75)",
        "party of the first part, for and in consideration",
        "Right of Way Deed",
        "A.D. 1915, by and between",
    ]
    
    unified_tokenizer = UnifiedPathTokenizer()
    current_tokenizer = CurrentApproachTokenizer()
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n🧪 SPECIFIC TEST {i}: '{test_case}'")
        print("-" * 60)
        
        # Test both approaches
        current_tokens = current_tokenizer.tokenize_current_approach(test_case)
        formatted_tokens, unified_tokens, mappings = unified_tokenizer.tokenize_with_unified_path(test_case)
        
        print(f"Current:  {current_tokens}")
        print(f"Unified:  {unified_tokens}")
        print(f"Formatted: {formatted_tokens}")
        
        if current_tokens == unified_tokens:
            print(f"✅ MATCH")
        else:
            print(f"❌ MISMATCH")

def main():
    """Main comparison function"""
    print("🚀 TOKENIZATION SIDE-BY-SIDE COMPARISON")
    
    # Compare approaches
    compare_tokenization_approaches()
    
    # Test specific cases
    test_specific_cases()
    
    print(f"\n" + "="*80)
    print("✅ COMPARISON COMPLETE")
    print("="*80)

if __name__ == "__main__":
    main() 