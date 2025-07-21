"""
Debug Section Mapping Issues
============================

Test the section mapping logic with the actual failing data to identify the problem.
"""

import sys
import os
import json
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from alignment.section_normalizer import SectionNormalizer

def test_actual_mapping():
    """Test with the actual failing data"""
    
    # Your actual drafts
    draft_1 = {
        "documentId": "61302",
        "sections": [
            {
                "id": 1,
                "header": "Right of Way Deed.",
                "body": "This Indenture, made this 3rd day of August, A.D. 1915, by and between Harriet Rickard, a widow, of the County of Albany, State of Wyoming, party of the first part, and Laramie Water Company, a corporation formed and existing under and by virtue of the laws of the State of Wyoming, having its office at Laramie, in the County of Albany and State of Wyoming, party of the second part, witnesseth:"
            },
            {
                "id": 2,
                "header": None,
                "body": "That the party of the first part, for and in consideration of the sum of One Dollar and other valuable considerations to her in hand paid by the party of the second part at or before the execution of this instrument, the receipt of which consideration is hereby acknowledged, has bargained, sold, granted and conveyed unto the party of the second part, its successors and assigns, those two (2) parcels of land situated in the Southwest Quarter of the Northwest Quarter of Section Two (2), Township Fourteen (14) North, Range seventy-five (75) West of the Sixth Principal Meridian, in the County of Albany, State of Wyoming, the said parcels of land being more particularly described as follows:-"
            },
            {
                "id": 3,
                "header": None,
                "body": "Beginning at a point on the west boundary of Section Two (2), Township Fourteen (14) North, Range seventy-four (74) West, whence the northwest corner bears N. 4° 00' W., 1638 feet distant, and being 50 feet S. 21° 30' E. from the center line of the South Canal of the Company; thence N. 68° 30' East parallel to and 50 feet distant from the center line of said canal 542 feet more or less to the north boundary of the Southwest Quarter of the Northwest Quarter of said Section Two (2);\nThence S. 87° 35' W. along the north boundary of said Southwest Quarter of the Northwest Quarter 518 feet; more or less, to the northwest corner of said Southwest Quarter of the Northwest Quarter; thence S. 4° 00' E. on the west boundary of said Section Two (2) 180 feet, more or less, to the point of beginning; said parcel of land containing 1.9 acres, more or less:-"
            },
            {
                "id": 4,
                "header": None,
                "body": "And, beginning on the north boundary of the Southwest Quarter of the Northwest Quarter of said Section Two (2), Township Fourteen (14) North, Range seventy-four (74) West, at a point where the northeast corner of said Section Two (2) bears N. 7° 00' W., 1275 feet distant, and being 50 feet S. 53° 00' E. from the center line of the South Canal of the Company; Thence N. 87° 35' E. along the north boundary of said Southwest Quarter of the Northwest Quarter, 400 feet, more or less, to"
            }
        ]
    }

    draft_2 = {
        "documentId": "61302",
        "sections": [
            {
                "id": 1,
                "header": "Right of Way Deed.",
                "body": "This indenture, made this 3rd day of August, A.D. 1915, by and between Harriet Rickard, a widow, of the county of Albany, state of Wyoming, party of the first part, and Laramie Water Company, a corporation formed and existing under and by virtue of the laws of the State of Wyoming, having its office at Laramie, in the county of Albany and State of Wyoming, party of the second part, witnesseth:\nThat the party of the first part, for and in consideration of the sum of One Dollar and other valuable considerations to her in hand paid by the party of the second part at or before the execution of this instrument, the receipt of which considerations is hereby acknowledged, has bargained, sold, granted and conveyed unto the party of the second part, its successors and assigns, those two (2) parcels of land situated in the Southwest Quarter of the Northwest Quarter of Section Two (2), Township Fourteen (14) North, Range seventy-five (75) West of the Sixth Principal Meridian, in the county of Albany, state of Wyoming, the said parcels of land being more particularly described as follows:-"
            },
            {
                "id": 2,
                "header": None,
                "body": "Beginning at a point on the west boundary of Section Two (2), Township Fourteen (14) North, Range seventy-four (74) West, whence the Northwest corner bears N. 2°00'W., 1638 feet distant, and being 50 feet S.21°30'E. from the center line of the South Canal of the Company; thence N.68°30'East parallel to and 50 feet distant from the center line of said canal 542 feet more or less to the North boundary of the Southwest Quarter of the Northwest Quarter of said Section Two (2); thence S.87°35'W. along the North boundary of said Southwest Quarter of the Northwest Quarter 518 feet; more or less, to the Northwest corner of said Southwest Quarter of the Northwest Quarter; thence S.2°00'E. on the West boundary of said Section Two (2) 180 feet, more or less, to the point of beginning; said parcel of land containing 1.9 acres, more or less:-\nAnd beginning on the north boundary of the Southwest Quarter of the Northwest Quarter of said Section Two (2), Township Fourteen (14) North, Range seventy-four (74) West, at a point where the Northeast corner of said Section Two (2) bears N.37°00'W., 1275 feet distant, and being 50 feet S.53°00'W. from the center line of the South Canal of the Company; thence N.87°35'E. along the North boundary of said Southwest Quarter of the Northwest Quarter, 400 feet, more or less, to"
            }
        ]
    }

    drafts = [draft_1, draft_2]
    
    print("🔍 DEBUGGING SECTION MAPPING")
    print("=" * 50)
    
    # Test the mapping logic directly
    normalizer = SectionNormalizer()
    
    # Extract sections
    sections_1 = normalizer._extract_sections_from_draft(draft_1, "Draft_1")
    sections_2 = normalizer._extract_sections_from_draft(draft_2, "Draft_2")
    
    print(f"Draft 1: {len(sections_1)} sections")
    for i, section in enumerate(sections_1):
        text = normalizer._get_section_text(section)
        print(f"  Section {i+1}: {len(text)} chars - {text[:100]}...")
    
    print(f"\nDraft 2: {len(sections_2)} sections")
    for i, section in enumerate(sections_2):
        text = normalizer._get_section_text(section)
        print(f"  Section {i+1}: {len(text)} chars - {text[:100]}...")
    
    # Test mapping
    print(f"\n🔧 Testing mapping logic...")
    mapping = normalizer._create_section_mapping(sections_2, sections_1)
    
    print(f"\n📋 Mapping Results:")
    for current_idx, target_indices in mapping:
        current_text = normalizer._get_section_text(sections_2[current_idx])
        print(f"  Current section {current_idx} ({len(current_text)} chars) → Target sections {target_indices}")
        
        # Show what content should go where
        for target_idx in target_indices:
            target_text = normalizer._get_section_text(sections_1[target_idx])
            print(f"    → Target {target_idx}: {len(target_text)} chars - {target_text[:80]}...")

if __name__ == "__main__":
    test_actual_mapping() 