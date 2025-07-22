"""
Section Normalizer Test Script
==============================

Tests the section normalizer with sample drafts that have different section counts.
Shows before/after sectioning and debug information.
Saves all results to one master file with original then normalized for each draft.
Also generates human-readable essay format files for easy review.
"""

import json
import os
import sys
from typing import List, Dict, Any
import logging

# Add backend to path
sys.path.append('backend')

from alignment.section_normalizer import SectionNormalizer

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


def clean_output_directory(output_dir: str = "normalized_drafts_output"):
    """Clean and recreate the output directory"""
    if os.path.exists(output_dir):
        print(f"🧹 Cleaning output directory: {output_dir}")
        import shutil
        shutil.rmtree(output_dir)
    
    os.makedirs(output_dir)
    print(f"✅ Created clean output directory: {output_dir}")


def load_sample_drafts() -> List[Dict[str, Any]]:
    """Load all sample drafts from the json_drafts_section_normalizer folder"""
    drafts = []
    folder_path = "json_drafts_section_normalizer"
    
    if not os.path.exists(folder_path):
        logger.error(f"❌ Folder not found: {folder_path}")
        return []
    
    # Load all JSON files in the folder
    for filename in os.listdir(folder_path):
        if filename.endswith('.json'):
            file_path = os.path.join(folder_path, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    draft_data = json.load(f)
                    
                # Extract draft info from filename: sample_draft_1_3_sections.json
                # Split by underscore and get the draft number and section count
                parts = filename.replace('.json', '').split('_')
                if len(parts) >= 4:
                    draft_number = parts[2]  # "1" from "sample_draft_1_3_sections"
                    section_count = parts[3]  # "3" from "sample_draft_1_3_sections"
                else:
                    # Fallback if filename format is different
                    draft_number = "unknown"
                    section_count = "0"
                
                # Create draft object
                draft = {
                    "draft_id": f"Draft_{draft_number}",
                    "sections": draft_data.get("sections", []),
                    "documentId": draft_data.get("documentId", "unknown"),
                    "filename": filename,
                    "original_section_count": int(section_count)
                }
                drafts.append(draft)
                
                logger.info(f" Loaded {filename}: {len(draft['sections'])} sections")
                
            except Exception as e:
                logger.error(f"❌ Error loading {filename}: {e}")
    
    return drafts


def format_section_as_essay(sections: List[Dict], title: str = "") -> str:
    """
    Format sections as a readable essay with clear section breaks.
    Shows where splits were made with visual markers.
    """
    essay = []
    
    if title:
        essay.append(f"# {title}")
        essay.append("")
    
    for i, section in enumerate(sections, 1):
        # Section header
        header = section.get('header', '')
        body = section.get('body', '')
        
        # Add section number and header
        if header:
            essay.append(f"## Section {i}: {header}")
        else:
            essay.append(f"## Section {i}")
        
        essay.append("")
        
        # Add body text with proper formatting
        if body:
            # Clean up whitespace and formatting
            body_lines = body.strip().split('\n')
            formatted_body = []
            
            for line in body_lines:
                line = line.strip()
                if line:
                    formatted_body.append(line)
                else:
                    formatted_body.append("")  # Preserve paragraph breaks
            
            essay.extend(formatted_body)
        
        essay.append("")
        essay.append("---")  # Section separator
        essay.append("")
    
    return "\n".join(essay)


def save_essay_format_files(drafts: List[Dict], normalized_drafts: List[Dict], output_dir: str):
    """
    Save only drafts that needed normalization in a single readable file each.
    Only creates files for drafts that actually changed.
    """
    print(f"\n📝 Generating essay format files for drafts that needed normalization...")
    
    files_created = 0
    
    for i, (original, normalized) in enumerate(zip(drafts, normalized_drafts)):
        original_count = len(original['sections'])
        normalized_count = len(normalized['sections'])
        
        # Only create files for drafts that actually changed
        if original_count == normalized_count:
            print(f"   ⏭️ {original['draft_id']}: No changes needed ({original_count} sections)")
            continue
        
        draft_id = original['draft_id']
        filename = original['filename']
        
        # Create single comprehensive file for this draft
        content = f"""# SECTION NORMALIZATION: {draft_id}
Filename: {filename}
Document ID: {original.get('documentId', 'unknown')}

## SUMMARY
- Original sections: {original_count}
- Normalized sections: {normalized_count}
- Action: Split {original_count} → {normalized_count} sections

{'='*80}

## ORIGINAL TEXT ({original_count} sections)
"""
        
        # Add original text
        original_essay = format_section_as_essay(original['sections'], "")
        content += original_essay
        
        content += f"""

{'='*80}

## NORMALIZED TEXT ({normalized_count} sections)
"""
        
        # Add normalized text
        normalized_essay = format_section_as_essay(normalized['sections'], "")
        content += normalized_essay
        
        content += f"""

{'='*80}

## SPLIT ANALYSIS
This draft was normalized to match the target section count of {max(len(d['sections']) for d in drafts)} sections.

The following changes were made:
"""
        
        # Show which sections were split
        for j, section in enumerate(original['sections'], 1):
            content += f"- Section {j}: Split into multiple parts\n"
        
        content += f"""

Target achieved: All drafts now have {normalized_count} sections.
"""
        
        # Save the single comprehensive file
        output_file = os.path.join(output_dir, f"{draft_id}_NORMALIZED.txt")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"   📄 {draft_id}: Normalization file created ({original_count} → {normalized_count} sections)")
        files_created += 1
    
    if files_created == 0:
        print(f"   ✅ No drafts needed normalization - all already have the same section count")
    else:
        print(f"✅ Created {files_created} normalization files in {output_dir}/")


def analyze_draft_sections(draft: Dict[str, Any], label: str = "") -> None:
    """Analyze and display section information for a draft"""
    sections = draft.get('sections', [])
    
    print(f"\n📋 {label} DRAFT ANALYSIS:")
    print(f"   Draft ID: {draft.get('draft_id', 'unknown')}")
    print(f"   Document ID: {draft.get('documentId', 'unknown')}")
    print(f"   Section Count: {len(sections)}")
    print(f"   Filename: {draft.get('filename', 'unknown')}")
    
    # Analyze each section
    for i, section in enumerate(sections, 1):
        header = section.get('header', 'null')
        body = section.get('body', '')
        body_preview = body[:100] + "..." if len(body) > 100 else body
        
        print(f"   Section {i}:")
        print(f"     Header: {header}")
        print(f"     Body Preview: {body_preview}")
        print(f"     Body Length: {len(body)} characters")


def test_section_normalizer():
    """Main test function"""
    print(" SECTION NORMALIZER TEST")
    print("=" * 50)
    
    # Clean and create output directory
    output_dir = "normalized_drafts_output"
    clean_output_directory(output_dir)
    
    # Load sample drafts
    print("\n📂 Loading sample drafts...")
    drafts = load_sample_drafts()
    
    if not drafts:
        print("❌ No drafts loaded. Exiting.")
        return
    
    print(f"\n✅ Loaded {len(drafts)} drafts")
    
    # Show original section counts
    print("\n📊 ORIGINAL SECTION COUNTS:")
    section_counts = []
    for draft in drafts:
        count = len(draft.get('sections', []))
        section_counts.append(count)
        print(f"   {draft['draft_id']}: {count} sections")
    
    print(f"\n📈 Section count distribution: {section_counts}")
    print(f"   Min: {min(section_counts)}")
    print(f"   Max: {max(section_counts)}")
    print(f"   Target (max): {max(section_counts)}")
    
    # Initialize section normalizer
    print("\n🔧 Initializing Section Normalizer...")
    normalizer = SectionNormalizer()
    
    # Test section normalization
    print("\n🔄 Testing Section Normalization...")
    try:
        normalized_drafts = normalizer.normalize_draft_sections(drafts)
        
        print(f"\n✅ Normalization completed successfully!")
        print(f"   Input drafts: {len(drafts)}")
        print(f"   Output drafts: {len(normalized_drafts)}")
        
        # Create master results file with simple sequential format
        master_results = []
        
        # Add each original and normalized draft sequentially
        for i, (original, normalized) in enumerate(zip(drafts, normalized_drafts)):
            # Add original draft
            original_draft = {
                "type": "ORIGINAL",
                "draft_number": i + 1,
                "draft_id": original['draft_id'],
                "filename": original['filename'],
                "documentId": original['documentId'],
                "section_count": len(original.get('sections', [])),
                "sections": original['sections']
            }
            master_results.append(original_draft)
            
            # Add normalized draft
            normalized_draft = {
                "type": "NORMALIZED",
                "draft_number": i + 1,
                "draft_id": normalized['draft_id'],
                "filename": normalized['filename'],
                "documentId": normalized['documentId'],
                "section_count": len(normalized.get('sections', [])),
                "sections": normalized['sections']
            }
            master_results.append(normalized_draft)
        
        # Save master file
        master_file = os.path.join(output_dir, "MASTER_SECTION_NORMALIZATION_RESULTS.json")
        with open(master_file, 'w', encoding='utf-8') as f:
            json.dump(master_results, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Saved master results: {master_file}")
        
        # Generate essay format files
        save_essay_format_files(drafts, normalized_drafts, output_dir)
        
        # Analyze results
        print("\n📊 NORMALIZATION RESULTS:")
        for i, (original, normalized) in enumerate(zip(drafts, normalized_drafts)):
            original_count = len(original.get('sections', []))
            normalized_count = len(normalized.get('sections', []))
            
            print(f"\n   Draft {i+1}: {original['draft_id']}")
            print(f"     Original sections: {original_count}")
            print(f"     Normalized sections: {normalized_count}")
            print(f"     Changed: {'✅' if original_count != normalized_count else '❌'}")
            
            if original_count != normalized_count:
                print(f"     Action: Split {original_count} → {normalized_count}")
        
        # Show detailed analysis of first draft
        if drafts:
            print("\n" + "="*50)
            analyze_draft_sections(drafts[0], "ORIGINAL")
            analyze_draft_sections(normalized_drafts[0], "NORMALIZED")
        
        # Show detailed analysis of a draft that was split
        split_drafts = [(i, d, n) for i, (d, n) in enumerate(zip(drafts, normalized_drafts)) 
                       if len(d.get('sections', [])) != len(n.get('sections', []))]
        
        if split_drafts:
            print("\n" + "="*50)
            print("🔍 DETAILED SPLIT ANALYSIS:")
            for i, original, normalized in split_drafts[:2]:  # Show first 2 splits
                print(f"\n Split Example {i+1}: {original['draft_id']}")
                analyze_draft_sections(original, "BEFORE")
                analyze_draft_sections(normalized, "AFTER")
        
        print(f"\n📁 Output files created:")
        print(f"   📄 Master JSON: {master_file}")
        print(f"   📝 Essay files: {output_dir}/*_essay.txt")
        print(f"   🔍 Comparison files: {output_dir}/*_COMPARISON_essay.txt")
        print(f"   📋 Format: Original → Normalized → Original → Normalized...")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Normalization failed: {e}")
        import traceback
        print(f"Full traceback:\n{traceback.format_exc()}")
        return False


def test_specific_scenarios():
    """Test specific scenarios with different section counts"""
    print("\n🎯 SPECIFIC SCENARIO TESTS")
    print("=" * 50)
    
    # Test 1: 3 sections vs 4 sections
    print("\n Test 1: 3 sections vs 4 sections")
    drafts_3_4 = [
        {
            "draft_id": "Draft_3",
            "sections": [{"id": 1, "header": "Test", "body": "Section 1 content"}, 
                        {"id": 2, "header": None, "body": "Section 2 content"},
                        {"id": 3, "header": None, "body": "Section 3 content"}]
        },
        {
            "draft_id": "Draft_4", 
            "sections": [{"id": 1, "header": "Test", "body": "Section 1 content"},
                        {"id": 2, "header": None, "body": "Section 2 part A"},
                        {"id": 3, "header": None, "body": "Section 2 part B"},
                        {"id": 4, "header": None, "body": "Section 3 content"}]
        }
    ]
    
    normalizer = SectionNormalizer()
    try:
        normalized = normalizer.normalize_draft_sections(drafts_3_4)
        print(f"   ✅ Test passed: {len(normalized[0]['sections'])} → {len(normalized[1]['sections'])} sections")
    except Exception as e:
        print(f"   ❌ Test failed: {e}")


if __name__ == "__main__":
    print("🚀 Starting Section Normalizer Tests...")
    
    # Run main test
    success = test_section_normalizer()
    
    if success:
        # Run specific scenario tests
        test_specific_scenarios()
    
    print("\n✅ Test completed!")
    print("📁 Check the 'normalized_drafts_output/' folder for:")
    print("   📄 MASTER_SECTION_NORMALIZATION_RESULTS.json (JSON format)")
    print("   📝 *_essay.txt files (human-readable format)")
    print("   🔍 Comparison files: {output_dir}/*_COMPARISON_essay.txt") 