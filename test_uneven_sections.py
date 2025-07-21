"""
Test Uneven Sections Scenario
=============================

Force the section normalizer to handle drafts with different section counts
to verify it's working properly in the alignment pipeline.
"""

import sys
import os
import json
import logging
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from alignment.biopython_engine import BioPythonAlignmentEngine

def create_uneven_test_drafts():
    """Create test drafts with deliberately different section counts"""
    
    # Draft 1: 3 sections (combines the land parcels)
    draft_1 = {
        "documentId": "test_61302",
        "sections": [
            {
                "id": 1,
                "header": None,
                "body": "Right of Way Deed.\n\nThis Indenture, made this 3rd day of August, A.D. 1915, by and between Harriet Richard, a widow, of the County of Albany, State of Wyoming, party of the first part, and Laramie Water Company, a corporation formed and existing under and by virtue of the laws of the State of Wyoming, having its office at Laramie, in the County of Albany and State of Wyoming, party of the second part, witnesseth:"
            },
            {
                "id": 2,
                "header": None,
                "body": "That the party of the first part, for and in consideration of the sum of One Dollar and other valuable considerations to her in hand paid by the party of the second part at or before the execution of this instrument, the receipt of which considerations is hereby acknowledged, has bargained, sold, granted and conveyed unto the party of the second part, its successors and assigns, those two (2) parcels of land situated in the Southwest Quarter of the Northwest Quarter of Section Two (2), Township Fourteen (14) North, Range Seventy-five (75) West of the Sixth Principal Meridian, in the County of Albany, State of Wyoming, the said parcels of land being more particularly described as follows:-"
            },
            {
                "id": 3,
                "header": None,
                "body": "Beginning at a point on the west boundary of Section Two (2), Township Fourteen (14) North, Range Seventy-four (74) West, whence the Northwest corner bears N. 4° 00' W., 1638 feet distant, and being 50 feet S. 21° 30' E. from the center line of the South canal of the Company; thence N. 68° 30' East parallel to and 50 feet distant from the center line of said canal 542 feet more or less to the North boundary of the Southwest Quarter of the Northwest Quarter of said Section Two (2); thence S. 87° 35' W. along the North boundary of said South West Quarter of the Northwest Quarter 518 feet; more or less, to the Northwest corner of said Southwest Quarter of the Northwest Quarter; thence S. 4° 00' E. on the West boundary of said Section Two (2) 180 feet, more or less, to the point of beginning; said parcel of land containing 1.9 acres, more or less:-\n\nAnd beginning on the north boundary of the Southwest Quarter of the Northwest Quarter of said Section Two (2), Township Fourteen (14) North, Range Seventy-four (74) West, at a point where the northeast corner of said Section Two (2) bears N. 37° 00' W., 1275 feet distant, and being 50 feet S. 53° 00' W. from the center line of the South canal of the Company; Thence N. 87° 35' E. along the North boundary of said South West Quarter of the Northwest Quarter, 400 feet, more or less, to"
            }
        ]
    }

    # Draft 2: 4 sections (splits the land parcels)
    draft_2 = {
        "documentId": "test_61302",
        "sections": [
            {
                "id": 1,
                "header": None,
                "body": "Right of Way Deed.\nThis indenture, made this 3rd day of August, A.D. 1915, by and between Harriet Rickard, a widow, of the County of Albany, State of Wyoming, party of the first part, and Laramie Water Company, a corporation formed and existing under and by virtue of the laws of the State of Wyoming, having its office at Laramie, in the County of Albany and State of Wyoming, party of the second part, Witnesseth:"
            },
            {
                "id": 2,
                "header": None,
                "body": "That the party of the first part, for and in consideration of the sum of One Dollar and other valuable considerations to her in hand paid by the party of the second part at or before the execution of this instrument, the receipt of which considerations is hereby acknowledged, has bargained, sold, granted and conveyed unto the party of the second part, its successors and assigns, those two (2) parcels of land situated in the Southwest Quarter of the Northwest Quarter of Section Two (2), Township Fourteen (14) North, Range seventy-five (75) West of the Sixth Principal Meridian, in the County of Albany, State of Wyoming, the said parcels of land being more particularly described as follows:-"
            },
            {
                "id": 3,
                "header": None,
                "body": "Beginning at a point on the west boundary of Section Two (2), Township Fourteen (14) North, Range seventy-four (74) West, whence the Northwest corner bears N. 4°00' W., 1638 feet distant, and being 50 feet S. 21°30' E. from the center line of the south canal of the company; Thence N. 68°30' East parallel to and 50 feet distant from the center line of said canal 542 feet more or less to the North boundary of the Southwest Quarter of the Northwest Quarter of said Section Two (2); Thence S. 87°35' W. along the North boundary of said Southwest Quarter of the Northwest Quarter 518 feet; more or less, to the Northwest corner of said Southwest Quarter of the Northwest Quarter; Thence S. 4°00' E. on the West boundary of said Section Two (2) 180 feet, more or less, to the point of beginning; said parcel of land containing 1.4 acres, more or less;"
            },
            {
                "id": 4,
                "header": None,
                "body": "And beginning on the North boundary of the Southwest Quarter of the Northwest Quarter of said Section Two (2), Township Fourteen (14) North, Range seventy-four (74) West, at a point where the Northeast corner of said Section Two (2) bears N. 37°00' W., 1275 feet distant, and being 50 feet S. 53°00' W. from the center line of the South canal of the company; Thence N. 87°35' E. along the North boundary of said Southwest Quarter of the Northwest Quarter, 400 feet, more or less, to"
            }
        ]
    }

    # Draft 3: 2 sections (combines everything into fewer sections)
    draft_3 = {
        "documentId": "test_61302",
        "sections": [
            {
                "id": 1,
                "header": "Right of Way Deed",
                "body": "This Indenture, made this 3rd day of August, A.D. 1915, by and between Harriet Rickards, a widow, of the County of Albany, State of Wyoming, party of the first part, and Laramie Water Company, a corporation formed and existing under and by virtue of the laws of the State of Wyoming, having its office at Laramie, in the County of Albany and State of Wyoming, party of the second part, Witnesseth:\nThat the party of the first part, for and in consideration of the sum of One Dollar and other valuable considerations to her in hand paid by the party of the second part at or before the execution of this instrument, the receipt of which consideration is hereby acknowledged, has bargained, sold, granted and conveyed unto the party of the second part, its successors and assigns, those two (2) parcels of land situated in the Southwest Quarter of the Northwest Quarter of Section Two (2), Township Fourteen (14) North, Range Seventy-five (75) West of the Sixth Principal Meridian, in the County of Albany, State of Wyoming, the said parcels of land being more particularly described as follows:-"
            },
            {
                "id": 2,
                "header": None,
                "body": "Beginning at a point on the west boundary of Section Two (2), Township Fourteen (14) North, Range seventy-four (74) West, whence the Northwest corner bears N. 4°00' W., 1638 feet distant, and being 50 feet S. 21°30' E. from the center line of the South canal of the Company; Thence N. 68°30' East parallel to and 50 feet distant from the center line of said canal 542 feet more or less to the North boundary of the Southwest Quarter of the Northwest Quarter of said Section Two (2);\nThence S. 87°35' W. along the North boundary of said Southwest Quarter of the Northwest Quarter 518 feet; more or less, to the Northwest corner of said Southwest Quarter of the Northwest Quarter;\nThence S. 4°00' E. on the West boundary of said Section Two (2) 180 feet, more or less, to the point of beginning; said parcel of land containing 1.4 acres, more or less:-\n\nAnd beginning on the north boundary of the Southwest Quarter of the Northwest Quarter of said Section Two (2), Township Fourteen (14) North, Range seventy-four (74) West, at a point where the Northeast corner of said Section Two (2) bears N. 37°00' W., 1275 feet distant, and being 50 feet S. 53°00' W. from the center line of the South canal of the Company; Thence N. 87°35' E. along the North boundary of said Southwest Quarter of the Northwest Quarter, 400 feet, more or less, to"
            }
        ]
    }

    return [draft_1, draft_2, draft_3]

def test_uneven_sections():
    """Test the alignment pipeline with uneven section counts"""
    
    print("🧪 TESTING UNEVEN SECTIONS SCENARIO")
    print("=" * 60)
    
    # Create test drafts with different section counts
    test_drafts = create_uneven_test_drafts()
    
    print("📋 Input Drafts:")
    for i, draft in enumerate(test_drafts):
        print(f"  Draft {i+1}: {len(draft['sections'])} sections")
        for j, section in enumerate(draft['sections']):
            print(f"    Section {j+1}: {len(section['body'])} chars")
    
    print(f"\n🎯 Expected: Draft 2 has most sections ({len(test_drafts[1]['sections'])}), others should be normalized to match")
    
    print("\n🚀 Running Full Alignment Pipeline...")
    
    try:
        # Initialize the alignment engine
        engine = BioPythonAlignmentEngine()
        
        # Run the complete alignment pipeline
        result = engine.align_drafts(test_drafts, generate_visualization=False)
        
        if result.get('success'):
            print("\n✅ SUCCESS: Alignment completed!")
            print(f"⏱️ Processing time: {result.get('processing_time', 0):.2f} seconds")
            
            # Check if we have alignment results
            alignment_results = result.get('alignment_results', {})
            if alignment_results and alignment_results.get('blocks'):
                print(f"📊 Alignment blocks: {len(alignment_results['blocks'])}")
                
                # Show sample of normalized sections
                for block_id, block_data in alignment_results['blocks'].items():
                    sequences = block_data.get('aligned_sequences', [])
                    print(f"\n🔍 Block '{block_id}':")
                    for seq in sequences:
                        draft_id = seq.get('draft_id', 'unknown')
                        tokens = seq.get('tokens', [])
                        print(f"  Draft {draft_id}: {len(tokens)} tokens")
                        if tokens:
                            print(f"    Sample: {' '.join(tokens[:10])}...")
            else:
                print("⚠️ No alignment blocks found in results")
                
        else:
            print(f"\n❌ FAILURE: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"\n💥 EXCEPTION: {e}")
        import traceback
        traceback.print_exc()

def test_section_normalizer_only():
    """Test just the section normalizer in isolation"""
    
    print("\n🔧 TESTING SECTION NORMALIZER ONLY")
    print("=" * 50)
    
    from alignment.section_normalizer import SectionNormalizer
    
    test_drafts = create_uneven_test_drafts()
    
    try:
        normalizer = SectionNormalizer()
        normalized_drafts = normalizer.normalize_draft_sections(test_drafts)
        
        print("📋 Normalized Drafts:")
        for i, draft in enumerate(normalized_drafts):
            print(f"  Draft {i+1}: {len(draft['sections'])} sections")
            for j, section in enumerate(draft['sections']):
                print(f"    Section {j+1}: {len(section['body'])} chars - {section['body'][:50]}...")
                
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Test section normalizer in isolation first
    test_section_normalizer_only()
    
    # Then test the full alignment pipeline
    test_uneven_sections() 