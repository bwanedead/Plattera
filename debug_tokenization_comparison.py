#!/usr/bin/env python3
"""
Debug script to compare current vs new tokenization approaches
using the actual saved draft files.
"""

import json
import sys
import os
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from alignment.json_draft_tokenizer import JsonDraftTokenizer
import logging

# Set up detailed logging
logging.basicConfig(
    level=logging.INFO,  # Change to DEBUG for more detail
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

def load_saved_drafts():
    """Load the saved draft JSON files and convert to tokenizer format"""
    saved_drafts_dir = Path("backend/saved_drafts")
    draft_files = ["draft_1.json", "draft_2.json", "draft_3.json"]
    
    drafts = []
    for draft_file in draft_files:
        file_path = saved_drafts_dir / draft_file
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                draft_data = json.load(f)
                # Convert to the format expected by the tokenizer
                draft_id = draft_file.replace('.json', '').replace('draft_', 'Draft_')
                formatted_draft = {
                    "draft_id": draft_id,
                    "blocks": [{
                        "id": "full_document",
                        "text": json.dumps(draft_data)  # JSON as text in first block
                    }]
                }
                drafts.append(formatted_draft)
                print(f"✅ Loaded {draft_file} as {draft_id}")
        else:
            print(f"❌ File not found: {file_path}")
    
    return drafts

def test_current_tokenization():
    """Test the current tokenization approach with actual data"""
    print("\n" + "="*80)
    print("🔍 TESTING CURRENT TOKENIZATION WITH SAVED DRAFTS")
    print("="*80)
    
    # Load drafts
    drafts = load_saved_drafts()
    if not drafts:
        print("❌ No drafts loaded!")
        return None
    
    # Create tokenizer
    tokenizer = JsonDraftTokenizer()
    
    # Process the drafts
    try:
        result = tokenizer.process_json_drafts(drafts)
        print(f"✅ Processing successful!")
        return result
    except Exception as e:
        print(f"❌ Processing failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def analyze_detailed_tokens(result):
    """Show detailed token analysis"""
    if not result:
        return
    
    print(f"\n📊 DETAILED TOKEN ANALYSIS")
    
    for block_id, block_data in result['blocks'].items():
        print(f"\n📋 BLOCK: {block_id}")
        
        # Show ALL tokens for each draft
        for draft_data in block_data['tokenized_drafts']:
            draft_id = draft_data['draft_id']
            tokens = draft_data['tokens']
            original_tokens = draft_data.get('original_tokens', [])
            
            print(f"\n   📝 {draft_id} COMPLETE TOKEN LIST:")
            print(f"      Text preview: {draft_data['text'][:100]}...")
            print(f"      Total normalized tokens: {len(tokens)}")
            
            # Show ALL normalized tokens
            print(f"      ALL NORMALIZED TOKENS:")
            for i, token in enumerate(tokens):
                if i % 10 == 0:
                    print(f"        [{i:3d}-{min(i+9, len(tokens)-1):3d}]: ", end="")
                print(f"'{token}'", end="")
                if (i + 1) % 10 == 0 or i == len(tokens) - 1:
                    print()
                else:
                    print(", ", end="")
            
            # Show original tokens if available
            if original_tokens:
                print(f"      Total original tokens: {len(original_tokens)}")
                print(f"      SAMPLE ORIGINAL TOKENS:")
                for i, token in enumerate(original_tokens[:20]):
                    if i % 10 == 0:
                        print(f"        [{i:3d}-{min(i+9, len(original_tokens[:20])-1):3d}]: ", end="")
                    print(f"'{token}'", end="")
                    if (i + 1) % 10 == 0 or i == len(original_tokens[:20]) - 1:
                        print()
                    else:
                        print(", ", end="")
            
            # Look for problematic patterns
            problematic = []
            for i, token in enumerate(tokens):
                if token in ['.', ',', '(', ')', ':', ';', '-', "'", '"', '{', '}', '[', ']']:
                    problematic.append(f"[{i}]:'{token}'")
                elif not token or token.isspace():
                    problematic.append(f"[{i}]:EMPTY")
                elif len(token) == 1 and not token.isalnum():
                    problematic.append(f"[{i}]:'{token}'")
            
            if problematic:
                print(f"      ⚠️ PROBLEMATIC TOKENS: {problematic[:10]}")
                if len(problematic) > 10:
                    print(f"         ... and {len(problematic) - 10} more")

def compare_normalization_approaches():
    """Compare different normalization approaches on real text samples"""
    print("\n" + "="*80)
    print("🔬 COMPARING NORMALIZATION APPROACHES")
    print("="*80)
    
    tokenizer = JsonDraftTokenizer()
    
    # Extract real text samples from the drafts
    drafts = load_saved_drafts()
    if not drafts:
        return
    
    # Get some real text samples from the JSON
    for draft in drafts[:1]:  # Just test first draft
        json_text = draft["blocks"][0]["text"]
        json_data = json.loads(json_text)
        
        for section in json_data["sections"][:2]:  # Test first 2 sections
            body_text = section.get("body", "")
            if body_text:
                # Take first sentence for testing
                sentences = body_text.split('. ')
                test_text = sentences[0] + '.'
                
                print(f"\n🔬 TESTING: '{test_text[:80]}...'")
                
                # Method 1: Current approach (normalize whole text, then tokenize)
                normalized_text = tokenizer._normalize_text(test_text)
                from nltk.tokenize import word_tokenize
                current_tokens = word_tokenize(normalized_text)
                
                print(f"   Method 1 (Current):")
                print(f"      Normalized text: '{normalized_text}'")
                print(f"      Final tokens ({len(current_tokens)}): {current_tokens}")
                
                # Method 2: Tokenize first, then normalize each
                formatted_tokens = word_tokenize(test_text)
                per_token_normalized = []
                
                print(f"   Method 2 (Token-first):")
                print(f"      Formatted tokens: {formatted_tokens}")
                print(f"      Per-token normalization:")
                
                for i, token in enumerate(formatted_tokens):
                    normalized = tokenizer._normalize_text(token)
                    print(f"         '{token}' → '{normalized}'")
                    if normalized and not normalized.isspace():
                        # Split in case normalization creates multiple tokens
                        norm_parts = normalized.split()
                        per_token_normalized.extend(norm_parts)
                
                print(f"      Final tokens ({len(per_token_normalized)}): {per_token_normalized}")
                
                # Compare
                if current_tokens == per_token_normalized:
                    print(f"   ✅ IDENTICAL RESULTS")
                else:
                    print(f"   ❌ DIFFERENT RESULTS!")
                    
                    # Show differences
                    max_len = max(len(current_tokens), len(per_token_normalized))
                    differences = []
                    for j in range(max_len):
                        t1 = current_tokens[j] if j < len(current_tokens) else '<MISSING>'
                        t2 = per_token_normalized[j] if j < len(per_token_normalized) else '<MISSING>'
                        if t1 != t2:
                            differences.append(f"[{j}]: '{t1}' ≠ '{t2}'")
                    
                    print(f"      Differences: {differences[:5]}")

def main():
    """Main debug function"""
    print("🚀 TOKENIZATION DEBUG SCRIPT")
    print("="*50)
    
    # Test with current system
    result = test_current_tokenization()
    
    # Show detailed analysis
    analyze_detailed_tokens(result)
    
    # Compare approaches
    compare_normalization_approaches()
    
    print("\n" + "="*80)
    print("✅ DEBUG COMPLETE - Check output above for issues")
    print("="*80)

if __name__ == "__main__":
    main() 