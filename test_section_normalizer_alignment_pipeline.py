#!/usr/bin/env python3
"""
Test Section Normalizer + Alignment Pipeline
============================================

Simple test that sends drafts through the alignment service pipeline
exactly as it would in a live run.
"""

import sys
import os
import json
import logging
import shutil
from typing import List, Dict, Any

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from services.alignment_service import AlignmentService

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def clean_output_directory(output_dir: str):
    """Clean the output directory before each test run."""
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)
    logger.info(f"Cleaned output directory: {output_dir}")

def save_alignment_result(alignment_result: Dict[str, Any], output_dir: str):
    """Save the alignment result for inspection."""
    filename = "alignment_result.json"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(alignment_result, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved alignment result: {filename}")

def save_error_log(error: Exception, output_dir: str):
    """Save error details for debugging."""
    filename = "error_log.txt"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"ERROR: {type(error).__name__}: {str(error)}\n\n")
        f.write("Full traceback:\n")
        import traceback
        f.write(traceback.format_exc())
    
    logger.error(f"Saved error log: {filename}")

def main():
    """Main test function - simple pipeline test."""
    logger.info("Starting Alignment Service Pipeline Test")
    
    # Test files
    test_files = [
        "json_drafts_section_normalizer/new_strct_sample_draft_7_5_sections.json",
        "json_drafts_section_normalizer/new_strct_sample_draft_8_4_sections.json", 
        "json_drafts_section_normalizer/new_strct_sample_draft_9_5_sections.json",
        "json_drafts_section_normalizer/new_strct_sample_draft_10_4_sections.json",
        "json_drafts_section_normalizer/new_strct_sample_draft_11_3_sections.json",
        "json_drafts_section_normalizer/new_strct_sample_draft_12_4_sections.json"
    ]
    
    # Output directory
    output_dir = "test_results"
    clean_output_directory(output_dir)
    
    # Load drafts
    logger.info("Loading test drafts...")
    drafts = []
    for filepath in test_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                draft = json.load(f)
                drafts.append(draft)
                logger.info(f"Loaded: {filepath} ({len(draft.get('sections', []))} sections)")
        except Exception as e:
            logger.error(f"Failed to load {filepath}: {e}")
    
    if not drafts:
        logger.error("No drafts loaded!")
        return
    
    # Send through alignment service pipeline (exactly as live run)
    logger.info("Sending drafts through alignment service pipeline...")
    try:
        alignment_service = AlignmentService()
        
        # This is the exact same call as the live system would make
        alignment_result = alignment_service.process_alignment_request(
            drafts,
            generate_visualization=True,
            consensus_strategy="highest_confidence"
        )
        
        logger.info("Alignment pipeline completed successfully!")
        save_alignment_result(alignment_result, output_dir)
        
    except Exception as e:
        logger.error(f"Alignment pipeline failed: {e}")
        save_error_log(e, output_dir)
        return
    
    logger.info("Test completed!")
    logger.info(f"Results saved in: {output_dir}")

if __name__ == "__main__":
    main() 