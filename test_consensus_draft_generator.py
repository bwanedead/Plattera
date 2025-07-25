#!/usr/bin/env python3
"""
Test script for consensus draft generator
=========================================

Simple test to verify the consensus draft generator works correctly.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from alignment.consensus_draft_generator import ConsensusDraftGenerator

def test_consensus_generation():
    """Test basic consensus draft generation"""
    
    # Sample Type 2 alignment results
    sample_alignment_results = {
        "blocks": {
            "block_1": {
                "aligned_sequences": [
                    {
                        "draft_id": "Draft_1",
                        "display_tokens": ["This", "is", "a", "test", "document"]
                    },
                    {
                        "draft_id": "Draft_2", 
                        "display_tokens": ["This", "was", "a", "test", "document"]
                    },
                    {
                        "draft_id": "Draft_3",
                        "display_tokens": ["This", "is", "the", "test", "document"]
                    }
                ]
            },
            "block_2": {
                "aligned_sequences": [
                    {
                        "draft_id": "Draft_1",
                        "display_tokens": ["with", "some", "content"]
                    },
                    {
                        "draft_id": "Draft_2",
                        "display_tokens": ["with", "more", "content"]
                    },
                    {
                        "draft_id": "Draft_3", 
                        "display_tokens": ["with", "some", "content"]
                    }
                ]
            }
        }
    }
    
    # Create generator and test
    generator = ConsensusDraftGenerator()
    
    try:
        enhanced_results = generator.generate_consensus_drafts(sample_alignment_results)
        
        print("✅ Consensus generation successful!")
        print(f"Enhanced results keys: {list(enhanced_results.keys())}")
        
        # Check if consensus sequences were added
        for block_id, block in enhanced_results["blocks"].items():
            consensus_found = any(seq.get("draft_id") == "consensus" for seq in block["aligned_sequences"])
            print(f"Block {block_id}: Consensus found = {consensus_found}")
            
            if consensus_found:
                consensus_seq = next(seq for seq in block["aligned_sequences"] if seq["draft_id"] == "consensus")
                print(f"  Consensus tokens: {consensus_seq['display_tokens']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Consensus generation failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Consensus Draft Generator...")
    success = test_consensus_generation()
    
    if success:
        print("\n🎉 All tests passed!")
    else:
        print("\n💥 Tests failed!")
        sys.exit(1) 