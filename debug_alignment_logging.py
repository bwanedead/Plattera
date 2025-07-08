#!/usr/bin/env python3
"""
Debug script for alignment logging
"""

import sys
import os
import logging

# Add the backend directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from alignment.biopython_engine import BioPythonAlignmentEngine

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('alignment_debug.log'),
        logging.StreamHandler()
    ]
)

# Test text with known issues
test_text = """Right of Way Deed This Indenture, made this 3rd day of August, A.D. and 1915 by and between harriet rickard a widow of the county of albany state of wyoming party of the first part and laramie water company a corporation formed and existing under and by virtue of the laws of the state of wyoming having its office at laramie in the county of albany and state of wyoming party of the second part witnesseth

That the party of the first part, for and in consideration of the sum of One Dollar and other valuable considerations to her in hand paid by the party of the second part at or before the execution of this instrument, the receipt of which considerations is hereby acknowledged, has bargained, sold, granted and conveyed unto the party of the second part, its successors and assigns, those two (2) parcels of land situated in the Southwest Quarter of the Northwest Quarter of Section Two (2) Township Fourteen (14) North, Range Seventy-five (75) West of the Sixth Principal Meridian, in the County of Albany, State of Wyoming, the said parcels of land being more particularly described as follows:-

Beginning at a point on the west boundary of Section Two (2) Township Fourteen (14) North, Range Seventy-four (74) West, whence the Northwest corner bears N. 4°00' 4°00'W., 1,638 feet distant and being 50 feet S.21°30'E. 21°30' the from the center line of the Southwest canal of the company thence N. 68°30' E. parallel to and 50 feet distant from the center line of said canal 542 feet more or less to the north boundary of the southwest quarter of the northwest quarter of said section two 2 thence S. 87°35' W. along the north boundary of said southwest quarter of the northwest quarter 518 feet, more or less to the northwest corner of said southwest quarter of the northwest quarter thence S. 4° 00'E on the west boundary of said section two 2 180 feet, more or less to the point of beginning said parcel of land containing 1.9 acres, more or less

And beginning on the north boundary of the Southwest Quarter of the Northwest Quarter of said Section Two (2) Township Fourteen (14) North, Range seventy-four (74) West, at a point where the northeast corner of said Section Two (2) bears N. 37°00' 37°00'W., 1,275 feet distant and being 50 feet S.53°00'W. 53°00' Southwest from the center line of the south canal of the company thence N. 87°35' E. along the north boundary of said southwest quarter of the northwest quarter 400 feet, more or less to"""

def main():
    print("🔍 Starting alignment logging debug")
    
    # Create test drafts
    draft_jsons = [
        {
            'draft_id': 'Draft_1',
            'blocks': {
                'block_1': {
                    'text': test_text
                }
            }
        },
        {
            'draft_id': 'Draft_2', 
            'blocks': {
                'block_1': {
                    'text': test_text  # Same text to see how it processes
                }
            }
        }
    ]
    
    # Initialize engine
    engine = BioPythonAlignmentEngine()
    
    # Run alignment with detailed logging
    print("🚀 Running alignment with detailed logging...")
    results = engine.align_drafts(draft_jsons, generate_visualization=False)
    
    print(f"✅ Alignment complete. Success: {results.get('success', False)}")
    print(f"📊 Processing time: {results.get('processing_time', 0):.2f}s")
    
    # Print any errors
    if not results.get('success', False):
        print(f"❌ Error: {results.get('error', 'Unknown error')}")
    
    print("📝 Check 'alignment_debug.log' for detailed logging output")

if __name__ == '__main__':
    main() 