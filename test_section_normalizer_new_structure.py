#!/usr/bin/env python3
"""
Test Section Normalizer with New Structure (No Headers)
======================================================

Test the section normalizer with the new JSON structure that doesn't have header fields.
This tests the exact issue we were having with the simplified structure.
"""

import sys
import os
import json
import logging
import shutil
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from alignment.section_normalizer import SectionNormalizer

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def clean_output_directory():
    """Clean the output directory before each test run"""
    output_dir = "normalized_sections_output"
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)
    logger.info(f"🧹 Cleaned output directory: {output_dir}")

def load_test_draft(file_path):
    """Load a test draft from JSON file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"❌ Failed to load {file_path}: {e}")
        return None

def save_comparison_results(draft_name, original_draft, normalized_draft, output_dir):
    """Save both original and normalized sections as clean .txt file for comparison"""
    output_file = os.path.join(output_dir, f"{draft_name}_comparison.txt")
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"=== COMPARISON: ORIGINAL vs NORMALIZED FOR {draft_name.upper()} ===\n\n")
            
            original_sections = original_draft.get('sections', [])
            normalized_sections = normalized_draft.get('sections', [])
            
            f.write(f"ORIGINAL SECTIONS: {len(original_sections)}\n")
            f.write("=" * 80 + "\n\n")
            
            # Show original sections
            for section in original_sections:
                section_id = section.get('id', '?')
                body = section.get('body', '')
                
                f.write(f"ORIGINAL SECTION {section_id}:\n")
                f.write("-" * 40 + "\n")
                f.write(f"{body}\n\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write(f"NORMALIZED SECTIONS: {len(normalized_sections)}\n")
            f.write("=" * 80 + "\n\n")
            
            # Show normalized sections
            for section in normalized_sections:
                section_id = section.get('id', '?')
                body = section.get('body', '')
                
                f.write(f"NORMALIZED SECTION {section_id}:\n")
                f.write("-" * 40 + "\n")
                f.write(f"{body}\n\n")
            
            # Add summary
            f.write("\n" + "=" * 80 + "\n")
            f.write("SUMMARY:\n")
            f.write(f"Original sections: {len(original_sections)}\n")
            f.write(f"Normalized sections: {len(normalized_sections)}\n")
            f.write(f"Change: {len(normalized_sections) - len(original_sections)} sections\n")
                
        logger.info(f"✅ Saved comparison results: {output_file}")
        return output_file
    except Exception as e:
        logger.error(f"❌ Failed to save {output_file}: {e}")
        return None

def test_section_normalizer():
    """Test the section normalizer with new structure JSON files"""
    
    # Clean output directory
    clean_output_directory()
    
    # Test files
    test_files = [
        "json_drafts_section_normalizer/new_strct_sample_draft_7_5_sections.json",
        "json_drafts_section_normalizer/new_strct_sample_draft_8_4_sections.json", 
        "json_drafts_section_normalizer/new_strct_sample_draft_9_5_sections.json"
    ]
    
    # Initialize section normalizer
    normalizer = SectionNormalizer()
    
    logger.info("🚀 Starting section normalizer tests with new structure...")
    
    # Load all test drafts first
    all_drafts = []
    for test_file in test_files:
        if not os.path.exists(test_file):
            logger.warning(f"⚠️  Test file not found: {test_file}")
            continue
            
        logger.info(f"📄 Loading: {test_file}")
        
        # Load test draft
        original_draft = load_test_draft(test_file)
        if not original_draft:
            continue
            
        all_drafts.append(original_draft)
    
    if len(all_drafts) < 2:
        logger.error("❌ Need at least 2 drafts to test normalization")
        return
    
    logger.info(f"📊 Loaded {len(all_drafts)} drafts for normalization")
    
    # Log original section counts
    for i, draft in enumerate(all_drafts):
        sections = draft.get('sections', [])
        logger.info(f"   Draft {i+1}: {len(sections)} sections")
    
    # Normalize all drafts together
    try:
        logger.info("\n🔄 Starting normalization process...")
        normalized_drafts = normalizer.normalize_draft_sections(all_drafts)
        logger.info(f"✅ Normalization completed for all {len(normalized_drafts)} drafts")
        
        # Log normalized section counts
        for i, draft in enumerate(normalized_drafts):
            sections = draft.get('sections', [])
            logger.info(f"   Normalized Draft {i+1}: {len(sections)} sections")
        
        # Save comparison for each draft
        for i, (original_draft, normalized_draft) in enumerate(zip(all_drafts, normalized_drafts)):
            draft_name = f"draft_{i+1}_comparison"
            output_file = save_comparison_results(draft_name, original_draft, normalized_draft, "normalized_sections_output")
            
            if output_file:
                logger.info(f" Output saved to: {output_file}")
        
        # Verify invariant - all drafts should have same section count
        section_counts = [len(draft.get('sections', [])) for draft in normalized_drafts]
        if len(set(section_counts)) == 1:
            logger.info(f"✅ INVARIANT VERIFIED: All drafts have {section_counts[0]} sections")
        else:
            logger.error(f"❌ INVARIANT FAILED: Section counts vary: {section_counts}")
            
    except Exception as e:
        logger.error(f"❌ Normalization failed: {e}")
        import traceback
        traceback.print_exc()
    
    logger.info(f"\n🎉 Test completed! Check 'normalized_sections_output/' directory for comparison results.")

if __name__ == "__main__":
    test_section_normalizer() 