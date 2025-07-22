
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
import datetime
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
                parts = filename.replace('.json', '').split('_')
                if len(parts) >= 4:
                    draft_number = parts[2]
                    section_count = parts[3]
                else:
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
    """Format sections as a readable essay with clear section breaks."""
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
    """Save individual essay files for drafts that needed normalization."""
    print(f"\n📝 Generating essay format files for drafts that needed normalization...")
    
    files_created = 0
    target_count = max(len(d.get('sections', [])) for d in drafts)
    
    for i, (original, normalized) in enumerate(zip(drafts, normalized_drafts)):
        original_count = len(original.get('sections', []))
        normalized_count = len(normalized.get('sections', []))
        
        print(f"    DEBUG {original['draft_id']}: Original={original_count}, Normalized={normalized_count}")
        
        # Create files for drafts that were processed
        if original_count != target_count:
            draft_id = original['draft_id']
            filename = original.get('filename', 'unknown')
            
            content = f"""# SECTION NORMALIZATION: {draft_id}
Filename: {filename}
Document ID: {original.get('documentId', 'unknown')}

## SUMMARY
- Original sections: {original_count}
- Normalized sections: {normalized_count}
- Target sections: {target_count}
- Action: Attempted to normalize {original_count} → {target_count} sections
- Result: {'✅ Success' if normalized_count == target_count else '❌ Failed - got ' + str(normalized_count)}

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

## NORMALIZATION ANALYSIS
This draft was processed to match the target section count of {target_count} sections.

Original section count: {original_count}
Normalized section count: {normalized_count}
Target section count: {target_count}

Status: {'✅ SUCCESS' if normalized_count == target_count else '❌ FAILED'}

The following changes were attempted:
"""
            
            # Show which sections were processed
            for j, section in enumerate(original['sections'], 1):
                content += f"- Section {j}: Processed for normalization\n"
            
            if normalized_count != target_count:
                content += f"""

⚠️ ISSUE DETECTED:
The section normalizer failed to create the expected {target_count} sections.
This may be due to:
1. Mapping issues in the alignment algorithm
2. Empty sections being filtered out
3. Target section indices not being properly mapped

Please check the section normalizer logs for more details.
"""
            else:
                content += f"""

✅ SUCCESS:
All drafts now have {normalized_count} sections as expected.
"""
            
            # Save the individual file
            output_file = os.path.join(output_dir, f"{draft_id}_NORMALIZED.txt")
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"   {draft_id}: Normalization file created ({original_count} → {normalized_count} sections)")
            files_created += 1
        else:
            print(f"   ⏭️ {original['draft_id']}: No normalization needed ({original_count} sections)")
    
    if files_created == 0:
        print(f"   ✅ No drafts needed normalization - all already have the same section count")
    else:
        print(f"✅ Created {files_created} normalization files in {output_dir}/")


def create_master_essay_file(drafts: List[Dict], normalized_drafts: List[Dict], output_dir: str):
    """Create a single master file containing all normalization results."""
    print(f"\n📚 Generating master essay file...")
    
    master_content = f"""# MASTER SECTION NORMALIZATION REPORT
Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Total Drafts Processed: {len(drafts)}

## SUMMARY
- Original drafts: {len(drafts)}
- Target section count: {max(len(d.get('sections', [])) for d in drafts)}

{'='*80}

"""
    
    # Add each draft's results
    for i, (original, normalized) in enumerate(zip(drafts, normalized_drafts)):
        original_count = len(original.get('sections', []))
        normalized_count = len(normalized.get('sections', []))
        target_count = max(len(d.get('sections', [])) for d in drafts)
        
        master_content += f"""## DRAFT {i+1}: {original['draft_id']}
Filename: {original.get('filename', 'unknown')}
Document ID: {original.get('documentId', 'unknown')}

### SUMMARY
- Original sections: {original_count}
- Normalized sections: {normalized_count}
- Target sections: {target_count}
- Status: {'✅ Success' if normalized_count == target_count else '❌ Failed - got ' + str(normalized_count)}

{'='*80}

### ORIGINAL TEXT ({original_count} sections)
"""
        
        # Add original text
        original_essay = format_section_as_essay(original['sections'], "")
        master_content += original_essay
        
        master_content += f"""

{'='*80}

### NORMALIZED TEXT ({normalized_count} sections)
"""
        
        # Add normalized text
        normalized_essay = format_section_as_essay(normalized['sections'], "")
        master_content += normalized_essay
        
        master_content += f"""

{'='*80}

"""
    
    # Save the master file
    master_essay_file = os.path.join(output_dir, "MASTER_NORMALIZATION_ESSAY.txt")
    with open(master_essay_file, 'w', encoding='utf-8') as f:
        f.write(master_content)
    
    print(f"   📚 Master essay file created: {master_essay_file}")
    print(f"   📄 Contains all {len(drafts)} drafts in single document")
    
    return master_essay_file


def test_section_normalizer():
    """Main test function"""
    print("🚀 SECTION NORMALIZER TEST")
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
        # Create deep copies of original drafts before normalization
        import copy
        original_drafts = [copy.deepcopy(draft) for draft in drafts]
        
        normalized_drafts = normalizer.normalize_draft_sections(drafts)
        
        print(f"\n✅ Normalization completed successfully!")
        print(f"   Input drafts: {len(drafts)}")
        print(f"   Output drafts: {len(normalized_drafts)}")
        
        # Create master results file (JSON)
        master_results = []
        for i, (original, normalized) in enumerate(zip(original_drafts, normalized_drafts)):
            master_results.append({
                "type": "ORIGINAL",
                "draft_number": i + 1,
                "draft_id": original['draft_id'],
                "filename": original['filename'],
                "documentId": original['documentId'],
                "section_count": len(original.get('sections', [])),
                "sections": original['sections']
            })
            master_results.append({
                "type": "NORMALIZED",
                "draft_number": i + 1,
                "draft_id": normalized['draft_id'],
                "filename": normalized['filename'],
                "documentId": normalized['documentId'],
                "section_count": len(normalized.get('sections', [])),
                "sections": normalized['sections']
            })
        
        # Save master JSON file
        master_file = os.path.join(output_dir, "MASTER_SECTION_NORMALIZATION_RESULTS.json")
        with open(master_file, 'w', encoding='utf-8') as f:
            json.dump(master_results, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Saved master results: {master_file}")
        
        # Generate individual essay files
        save_essay_format_files(original_drafts, normalized_drafts, output_dir)
        
        # Create master essay file
        create_master_essay_file(original_drafts, normalized_drafts, output_dir)
        
        # Show results summary
        print("\n📊 NORMALIZATION RESULTS:")
        for i, (original, normalized) in enumerate(zip(original_drafts, normalized_drafts)):
            original_count = len(original.get('sections', []))
            normalized_count = len(normalized.get('sections', []))
            
            print(f"\n   Draft {i+1}: {original['draft_id']}")
            print(f"     Original sections: {original_count}")
            print(f"     Normalized sections: {normalized_count}")
            print(f"     Changed: {'✅' if original_count != normalized_count else '❌'}")
            
            if original_count != normalized_count:
                print(f"     Action: Split {original_count} → {normalized_count}")
        
        print(f"\n📁 Output files created:")
        print(f"   📄 Master JSON: {master_file}")
        print(f"   📝 Individual files: {output_dir}/*_NORMALIZED.txt")
        print(f"   📚 Master essay file: {output_dir}/MASTER_NORMALIZATION_ESSAY.txt")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Normalization failed: {e}")
        import traceback
        print(f"Full traceback:\n{traceback.format_exc()}")
        return False


if __name__ == "__main__":
    print("🚀 Starting Section Normalizer Tests...")
    
    # Run main test
    success = test_section_normalizer()
    
    if success:
        print("\n✅ Test completed successfully!")
    else:
        print("\n❌ Test failed!")
    
    print("📁 Check the 'normalized_drafts_output/' folder for:")
    print("   📄 MASTER_SECTION_NORMALIZATION_RESULTS.json (JSON format)")
    print("   📝 Individual files: *_NORMALIZED.txt")
    print("   📚 Master essay file: MASTER_NORMALIZATION_ESSAY.txt") 