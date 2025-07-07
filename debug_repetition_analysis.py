#!/usr/bin/env python3
"""
Debug script to analyze specific repetition and formatting issues
that persist after the initial fixes
"""

import sys
sys.path.append('backend')

from backend.alignment.biopython_engine import BioPythonAlignmentEngine
from backend.alignment.json_draft_tokenizer import JsonDraftTokenizer
from backend.alignment.format_mapping import FormatMapper

def debug_persistent_issues():
    """Debug the persistent repetition and formatting issues"""
    
    print("🔍 DEBUGGING PERSISTENT ISSUES")
    print("=" * 60)
    
    # The actual problematic text from the user's results
    problematic_text = """Right of Way Deed This Indenture, made this 3rd day of August, A.D. 1915, by and between Harriet Rickard, a widow, of the County of Albany, State of Wyoming, party of the first part, and Laramie Water Company, a corporation formed and existing under and by virtue of the laws of the State of Wyoming, having its office at Laramie, in the County of Albany and State of Wyoming, party of the second part, witnesseth: That the party of the first part, for and in consideration of the sum of One Dollar and other valuable considerations to her in hand paid by the party of the second part at or before the execution of this instrument, the receipt of which considerations is hereby acknowledged, has bargained, sold, granted and conveyed unto the party of the second part, its successors and assigns, those two (2) parcels of land situated in the Southwest Quarter of the Northwest Quarter of Section Two (2), Township Fourteen (14) North, Range Seventy-five (75) West of the Sixth Principal Meridian, in the County of Albany, State of Wyoming, the said parcels of land being more particularly described as follows:- Beginning at a point on the west boundary of Section Two (2), Township Fourteen (14) North, Range Seventy-four (74) West; whence the Northwest corner bears N. 4° 00' W., 1,638 feet distant, and being 50 feet S. 21° 30' E. from the center line of the South Canal of the Company; Thence N. 68° 30' East parallel to and 50 feet distant from the center line of said canal 542 feet more or less to the North boundary of the Southwest Quarter of the Northwest Quarter of said Section Two (2); Thence S. 87° 35' W. along the North boundary of said Southwest Quarter of the Northwest Quarter 518 feet; more or less, to the Northwest corner of said Southwest Quarter of the Northwest Quarter; Thence S. 4° 00' E. on the West boundary of said Section Two (2) 180 feet, more or less, to the point of beginning; said parcel of land containing 1.9 acres, more or less:- And beginning on the north boundary of the Southwest Quarter of the Northwest Quarter of said Section Two (2), Township Fourteen (14) North, Range seventy-four (74) West, at a point where the northeast corner of said Section Two (2) bears N. 37° 00' W., 1,275 feet distant, and being 50 feet S. 53° 00' W. from the center line of the South Canal of the Company; Thence N. 87° 35' E. along the north boundary of said Southwest Quarter of the Northwest Quarter, 400 feet, more or less, to"""
    
    # Create test drafts
    test_drafts = [
        {
            "draft_id": "Draft_1",
            "blocks": [
                {
                    "id": "legal_text",
                    "text": problematic_text
                }
            ]
        },
        {
            "draft_id": "Draft_2",
            "blocks": [
                {
                    "id": "legal_text",
                    "text": problematic_text
                }
            ]
        }
    ]
    
    print("🔧 Step 1: Analyzing tokenization")
    tokenizer = JsonDraftTokenizer()
    tokenized_data = tokenizer.process_json_drafts(test_drafts)
    
    legal_text_block = tokenized_data['blocks']['legal_text']
    draft_1_tokens = legal_text_block['tokenized_drafts'][0]['tokens']
    
    print(f"📊 Total tokens: {len(draft_1_tokens)}")
    
    # Look for the specific repetition patterns
    print(f"\n🔍 Searching for repetition patterns...")
    
    # Pattern 1: "section two 2 180 feet more or less to the point of beginning said parcel of land containing"
    section_pattern_1 = ['section', 'two', '2', '180', 'feet', 'more', 'or', 'less', 'to', 'the', 'point', 'of', 'beginning', 'said', 'parcel', 'of', 'land', 'containing']
    section_pattern_occurrences = []
    
    for i in range(len(draft_1_tokens) - len(section_pattern_1)):
        window = draft_1_tokens[i:i+len(section_pattern_1)]
        if window == section_pattern_1:
            section_pattern_occurrences.append(i)
    
    print(f"   Found 'section two 2 180...' pattern at indices: {section_pattern_occurrences}")
    
    # Pattern 2: "1 9 acres more or less"
    acres_pattern = ['1', '9', 'acres', 'more', 'or', 'less']
    acres_pattern_occurrences = []
    
    for i in range(len(draft_1_tokens) - len(acres_pattern)):
        window = draft_1_tokens[i:i+len(acres_pattern)]
        if window == acres_pattern:
            acres_pattern_occurrences.append(i)
    
    print(f"   Found '1 9 acres more or less' pattern at indices: {acres_pattern_occurrences}")
    
    # Pattern 3: "quarter of the northwest quarter"
    quarter_pattern = ['quarter', 'of', 'the', 'northwest', 'quarter']
    quarter_pattern_occurrences = []
    
    for i in range(len(draft_1_tokens) - len(quarter_pattern)):
        window = draft_1_tokens[i:i+len(quarter_pattern)]
        if window == quarter_pattern:
            quarter_pattern_occurrences.append(i)
    
    print(f"   Found 'quarter of the northwest quarter' pattern at indices: {quarter_pattern_occurrences}")
    
    # Look for "seventy-four four" and "seventy-five five" issues
    number_issues = []
    for i in range(len(draft_1_tokens) - 2):
        if (draft_1_tokens[i].startswith('seventy') and 
            draft_1_tokens[i+1] in ['four', 'five'] and 
            draft_1_tokens[i+2] in ['74', '75']):
            number_issues.append((i, draft_1_tokens[i:i+3]))
    
    print(f"   Found number formatting issues: {number_issues}")
    
    print(f"\n🎨 Step 2: Analyzing format mapping")
    format_mapper = FormatMapper()
    
    draft_1_data = legal_text_block['tokenized_drafts'][0]
    mapping = format_mapper.create_mapping(
        draft_1_data['draft_id'],
        draft_1_data['text'],
        draft_1_data['tokens']
    )
    
    print(f"📊 Format positions found: {len(mapping.token_positions)}")
    
    # Check for overlapping mappings around repetition areas
    print(f"\n📊 Analyzing mappings around repetition areas:")
    
    for pattern_start in section_pattern_occurrences + acres_pattern_occurrences + quarter_pattern_occurrences:
        mappings_in_area = []
        for pos in mapping.token_positions:
            if pattern_start - 5 <= pos.token_index <= pattern_start + 20:
                mappings_in_area.append(pos)
        
        print(f"   Mappings around index {pattern_start}:")
        for pos in mappings_in_area:
            tokens_consumed = len(pos.normalized_text.split()) if ' ' in pos.normalized_text else 1
            print(f"     {pos.token_index}: '{pos.normalized_text}' → '{pos.original_text}' (consumes {tokens_consumed})")
    
    print(f"\n🚀 Step 3: Testing full alignment pipeline")
    engine = BioPythonAlignmentEngine()
    result = engine.align_drafts(test_drafts, generate_visualization=False)
    
    if result['success']:
        print("✅ Alignment successful!")
        
        # Extract formatted text
        alignment_results = result['alignment_results']
        blocks = alignment_results.get('blocks', {})
        
        for block_id, block_data in blocks.items():
            print(f"\n📋 Block: {block_id}")
            
            aligned_sequences = block_data.get('aligned_sequences', [])
            if aligned_sequences:
                seq = aligned_sequences[0]  # First draft
                tokens = seq.get('tokens', [])
                formatting_applied = seq.get('formatting_applied', False)
                
                print(f"   Token count: {len(tokens)}")
                print(f"   Formatting applied: {formatting_applied}")
                
                # Reconstruct text for analysis
                non_gap_tokens = [t for t in tokens if t != '-']
                reconstructed_text = ' '.join(non_gap_tokens)
                
                print(f"   Reconstructed text length: {len(reconstructed_text)}")
                
                # Identify the exact repetition issues
                print(f"\n🔍 Detailed Issue Analysis:")
                
                # Check for the specific repetitions mentioned by user
                repetition_1 = "of said section two 2 180 feet more or less to the point of beginning said parcel of land containing"
                repetition_count_1 = reconstructed_text.count(repetition_1)
                if repetition_count_1 > 1:
                    print(f"   ⚠️ Found repetition (count: {repetition_count_1}): ...{repetition_1}...")
                
                repetition_2 = "quarter of the northwest quarter 400 feet more or less to"
                repetition_count_2 = reconstructed_text.count(repetition_2)
                if repetition_count_2 > 1:
                    print(f"   ⚠️ Found repetition (count: {repetition_count_2}): ...{repetition_2}...")
                
                # Check for number formatting issues
                if "seventy-four four (74)" in reconstructed_text:
                    print(f"   ⚠️ Found number issue: 'seventy-four four (74)' should be 'seventy-four (74)'")
                
                if "seventy-five five (75)" in reconstructed_text:
                    print(f"   ⚠️ Found number issue: 'seventy-five five (75)' should be 'seventy-five (75)'")
                
                # Show the problematic areas
                section_pos = reconstructed_text.find('section two 2 180')
                if section_pos >= 0:
                    section_area = reconstructed_text[max(0, section_pos-50):section_pos+300]
                    print(f"\n   Section area: ...{section_area}...")
                
                quarter_pos = reconstructed_text.find('quarter of the northwest quarter 400')
                if quarter_pos >= 0:
                    quarter_area = reconstructed_text[max(0, quarter_pos-50):quarter_pos+200]
                    print(f"\n   Quarter area: ...{quarter_area}...")
                    
    else:
        print(f"❌ Alignment failed: {result.get('error')}")

if __name__ == "__main__":
    debug_persistent_issues() 