"""
Detailed Debug Section Normalizer
================================

Test the section normalizer with detailed logging to see why Draft 1 isn't being normalized properly.
"""

import sys
import os
import json
import logging
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

# Set up detailed logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from alignment.section_normalizer import SectionNormalizer

def test_section_normalizer_detailed():
    """Test section normalizer with detailed logging"""
    
    # Your actual drafts that are causing the issue
    draft_1 = {
        "documentId": "#61302",
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

    draft_2 = {
        "documentId": "61302",
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

    print("�� DETAILED SECTION NORMALIZER TEST")
    print("=" * 60)
    
    drafts = [draft_1, draft_2]
    
    print(f"Input: {len(drafts)} drafts with section counts:")
    for i, draft in enumerate(drafts):
        print(f"  Draft {i+1}: {len(draft['sections'])} sections")
        for j, section in enumerate(draft['sections']):
            print(f"    Section {j+1}: {len(section['body'])} chars")
    
    print("\n🔧 Running Section Normalizer with detailed logging...")
    
    try:
        normalizer = SectionNormalizer()
        normalized_drafts = normalizer.normalize_draft_sections(drafts)
        
        print(f"\n✅ RESULT: Normalized to {len(normalized_drafts)} drafts")
        for i, draft in enumerate(normalized_drafts):
            print(f"  Draft {i+1}: {len(draft['sections'])} sections")
            for j, section in enumerate(draft['sections']):
                print(f"    Section {j+1}: {len(section['body'])} chars - {section['body'][:80]}...")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_section_normalizer_detailed() 