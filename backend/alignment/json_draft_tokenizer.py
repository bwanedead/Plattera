"""
JSON Draft Tokenizer Module
===========================

Handles JSON draft parsing, legal document tokenization, and encoding for BioPython alignment.
Processes multiple JSON drafts with semantic blocks to prepare them for consistency-based alignment.
"""

import json
import re
import logging
from typing import Dict, List, Tuple, Any
from collections import defaultdict

from .alignment_config import ANCHOR_PATTERNS
from .alignment_utils import encode_tokens_for_alignment

logger = logging.getLogger(__name__)


class JsonDraftTokenizer:
    """Handles JSON draft parsing and tokenization for BioPython alignment"""
    
    def __init__(self):
        # Legal phrases to treat as single tokens (longer phrases first for proper matching)
        self.legal_phrases = [
            "This Indenture", "Warranty Deed", "Quit Claim Deed", "Special Warranty Deed",
            "Southwest Quarter", "Southeast Quarter", "Northwest Quarter", "Northeast Quarter",
            "Sixth Principal Meridian", "Fifth Principal Meridian", "Township Range", "Section Township",
            "South Half", "North Half", "East Half", "West Half",
            "Beginning at a point", "thence running", "point of beginning", "more or less",
            "according to the plat", "as recorded in", "all that certain"
        ]
        
        # Enhanced coordinate patterns for legal documents
        self.coordinate_patterns = [
            r'[NS]\s*\.\s*\d+°\s*\d+\'\s*[EW]\s*\.',     # N.4°00'W.
            r'[NS]\s*\d+°\s*\d+\'\s*\d+"\s*[EW]',        # N 37°15'30" W
            r'[NS]\s*\d+°\s*\d+\'\s*[EW]',               # N 37°15' W
            r'[NS]\s*\d+°\s*[EW]',                       # N 37° W
            r'\d+°\s*\d+\'\s*\d+"',                      # 37°15'30"
            r'\d+°\s*\d+\'',                             # 37°15'
            r'\d+°',                                     # 37°
            r'[NS]\s+\d+°\s+\d+\'\s+\d+"\s+[EW]',       # N 37° 15' 30" W (with spaces)
            r'[NS]\s+\d+°\s+\d+\'\s+[EW]',              # N 37° 15' W (with spaces)
            r'[NS]\s+\d+°\s+[EW]'                       # N 37° W (with spaces)
        ]
        
        # Compile regex patterns for efficiency
        self.compiled_coordinate_patterns = [re.compile(pattern, re.IGNORECASE) 
                                           for pattern in self.coordinate_patterns]
        self.compiled_anchor_patterns = {name: re.compile(pattern) 
                                       for name, pattern in ANCHOR_PATTERNS.items()}
    
    def process_json_drafts(self, draft_jsons: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process multiple JSON drafts for BioPython alignment
        
        Args:
            draft_jsons: List of draft dictionaries with 'draft_id' and 'blocks'
            
        Returns:
            Dict containing processed data ready for BioPython alignment
        """
        logger.info(f"🔧 JSON TOKENIZATION ► Processing {len(draft_jsons)} JSON drafts")
        
        # Validate input format
        self._validate_json_format(draft_jsons)
        
        # Organize blocks by ID across drafts
        blocks_by_id = self._organize_blocks_by_id(draft_jsons)
        logger.info(f"   📋 Found {len(blocks_by_id)} unique blocks across drafts")
        
        # Process each block independently
        processed_blocks = {}
        global_token_mappings = {}  # Share token mappings across blocks for consistency
        
        for block_id, draft_texts in blocks_by_id.items():
            logger.info(f"   🧩 Tokenizing block '{block_id}' with {len(draft_texts)} drafts")
            
            # Tokenize and encode each draft's text for this block
            block_data = self._process_single_block(block_id, draft_texts, global_token_mappings)
            processed_blocks[block_id] = block_data
            
            # Log tokenization statistics
            avg_tokens = sum(len(draft['tokens']) for draft in block_data['tokenized_drafts']) / len(block_data['tokenized_drafts'])
            logger.info(f"   📊 Block '{block_id}': avg {avg_tokens:.1f} tokens per draft, {block_data['unique_token_count']} unique tokens")
        
        logger.info("✅ JSON TOKENIZATION COMPLETE ► All blocks processed successfully")
        
        return {
            'blocks': processed_blocks,
            'draft_count': len(draft_jsons),
            'block_count': len(blocks_by_id),
            'global_token_mappings': global_token_mappings
        }
    
    def _validate_json_format(self, draft_jsons: List[Dict[str, Any]]):
        """Validate JSON draft format and structure"""
        if not draft_jsons:
            raise ValueError("No draft JSONs provided")
        
        for i, draft in enumerate(draft_jsons):
            if not isinstance(draft, dict):
                raise ValueError(f"Draft {i} must be a dictionary")
            
            if 'draft_id' not in draft:
                raise ValueError(f"Draft {i} missing required 'draft_id' field")
            
            if 'blocks' not in draft:
                raise ValueError(f"Draft {i} missing required 'blocks' field")
            
            if not isinstance(draft['blocks'], list):
                raise ValueError(f"Draft {i} 'blocks' must be a list")
            
            # Validate each block
            for j, block in enumerate(draft['blocks']):
                if not isinstance(block, dict):
                    raise ValueError(f"Draft {i}, block {j} must be a dictionary")
                
                if 'id' not in block:
                    raise ValueError(f"Draft {i}, block {j} missing required 'id' field")
                
                if 'text' not in block:
                    raise ValueError(f"Draft {i}, block {j} missing required 'text' field")
                
                if not isinstance(block['text'], str):
                    raise ValueError(f"Draft {i}, block {j} 'text' must be a string")
    
    def _organize_blocks_by_id(self, draft_jsons: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
        """
        Organize draft blocks by block ID for alignment
        
        Returns:
            Dict[block_id, Dict[draft_id, text]]
        """
        blocks_by_id = defaultdict(dict)
        
        for draft_data in draft_jsons:
            draft_id = draft_data.get('draft_id', f'draft_{id(draft_data)}')
            blocks = draft_data.get('blocks', [])
            
            for block in blocks:
                block_id = block.get('id')
                block_text = block.get('text', '')
                
                if block_id:
                    blocks_by_id[block_id][draft_id] = block_text
        
        # Validate that all blocks have the same number of drafts
        expected_draft_count = len(draft_jsons)
        for block_id, drafts in blocks_by_id.items():
            if len(drafts) != expected_draft_count:
                logger.warning(f"⚠️ Block '{block_id}' has {len(drafts)} drafts, expected {expected_draft_count}")
        
        return dict(blocks_by_id)
    
    def _process_single_block(self, block_id: str, draft_texts: Dict[str, str], 
                            global_token_mappings: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single block across all drafts with consistent tokenization"""
        
        # Tokenize all drafts for this block
        tokenized_drafts = []
        all_tokens = set()  # Collect all unique tokens for consistent encoding
        
        for draft_id, text in draft_texts.items():
            tokens = self._tokenize_legal_text(text)
            tokenized_drafts.append({
                'draft_id': draft_id,
                'tokens': tokens,
                'text': text,
                'token_count': len(tokens)
            })
            all_tokens.update(tokens)
        
        # Create consistent token encoding across all drafts in this block
        if block_id not in global_token_mappings:
            # Create encoding for unique tokens in this block
            unique_tokens = sorted(all_tokens)  # Sort for consistency
            encoded_dummy, token_to_id, id_to_token = encode_tokens_for_alignment(unique_tokens)
            global_token_mappings[block_id] = {
                'token_to_id': token_to_id,
                'id_to_token': id_to_token
            }
        
        token_to_id = global_token_mappings[block_id]['token_to_id']
        id_to_token = global_token_mappings[block_id]['id_to_token']
        
        # Encode each draft's tokens using consistent mapping
        encoded_drafts = []
        for draft_data in tokenized_drafts:
            # Encode tokens to numeric IDs, using -1 for unknown tokens
            encoded_tokens = []
            for token in draft_data['tokens']:
                if token in token_to_id:
                    encoded_tokens.append(token_to_id[token])
                else:
                    # This shouldn't happen since we collected all tokens above
                    logger.warning(f"Unknown token '{token}' in block '{block_id}'")
                    encoded_tokens.append(-1)
            
            encoded_drafts.append({
                'draft_id': draft_data['draft_id'],
                'tokens': draft_data['tokens'],
                'encoded_tokens': encoded_tokens,
                'text': draft_data['text'],
                'token_count': draft_data['token_count']
            })
        
        return {
            'block_id': block_id,
            'tokenized_drafts': tokenized_drafts,
            'encoded_drafts': encoded_drafts,
            'token_to_id': token_to_id,
            'id_to_token': id_to_token,
            'unique_token_count': len(token_to_id),
            'draft_count': len(encoded_drafts)
        }
    
    def _tokenize_legal_text(self, text: str) -> List[str]:
        """
        Tokenize text into meaningful legal document tokens
        
        Args:
            text: Raw text to tokenize
            
        Returns:
            List of tokens preserving legal document structure and meaning
        """
        if not text or not text.strip():
            return []
        
        tokens = []
        remaining_text = text.strip()
        position = 0
        
        while position < len(remaining_text):
            token_found = False
            original_position = position
            
            # Skip whitespace
            while position < len(remaining_text) and remaining_text[position].isspace():
                position += 1
            
            if position >= len(remaining_text):
                break
            
            # Check for legal phrases first (longest matches prioritized)
            for phrase in self.legal_phrases:
                phrase_len = len(phrase)
                if position + phrase_len <= len(remaining_text):
                    text_segment = remaining_text[position:position + phrase_len]
                    if text_segment.lower() == phrase.lower():
                        tokens.append(phrase)
                        position += phrase_len
                        token_found = True
                        break
            
            if token_found:
                continue
            
            # Check for coordinate patterns
            for pattern in self.compiled_coordinate_patterns:
                match = pattern.match(remaining_text, position)
                if match:
                    coordinate = match.group(0)
                    tokens.append(coordinate)
                    position = match.end()
                    token_found = True
                    break
            
            if token_found:
                continue
            
            # Check for other anchor patterns (excluding punctuation for separate handling)
            for pattern_name, compiled_pattern in self.compiled_anchor_patterns.items():
                if pattern_name == 'PUN':  # Handle punctuation separately
                    continue
                    
                match = compiled_pattern.match(remaining_text, position)
                if match:
                    token = match.group(0)
                    tokens.append(token)
                    position = match.end()
                    token_found = True
                    break
            
            if token_found:
                continue
            
            # Check for punctuation (single characters that are legally significant)
            if remaining_text[position] in '.,;:!?()[]{}"\'-':
                tokens.append(remaining_text[position])
                position += 1
                continue
            
            # Check for regular words (alphanumeric sequences)
            word_match = re.match(r'[A-Za-z0-9]+', remaining_text[position:])
            if word_match:
                word = word_match.group(0)
                tokens.append(word)
                position += len(word)
                continue
            
            # Single character fallback (but skip whitespace)
            if not remaining_text[position].isspace():
                tokens.append(remaining_text[position])
            position += 1
            
            # Safety check to prevent infinite loops
            if position == original_position:
                logger.warning(f"Tokenization stuck at position {position}, character: '{remaining_text[position]}'")
                position += 1
        
        # Filter out empty tokens and return
        final_tokens = [token for token in tokens if token.strip()]
        return final_tokens
    
    def get_tokenization_statistics(self, processed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get detailed tokenization statistics for analysis
        
        Args:
            processed_data: Output from process_json_drafts
            
        Returns:
            Dict with tokenization statistics
        """
        stats = {
            'total_blocks': processed_data['block_count'],
            'total_drafts': processed_data['draft_count'],
            'blocks': {}
        }
        
        for block_id, block_data in processed_data['blocks'].items():
            token_counts = [draft['token_count'] for draft in block_data['tokenized_drafts']]
            
            stats['blocks'][block_id] = {
                'unique_tokens': block_data['unique_token_count'],
                'avg_tokens_per_draft': sum(token_counts) / len(token_counts),
                'min_tokens': min(token_counts),
                'max_tokens': max(token_counts),
                'token_variance': max(token_counts) - min(token_counts)
            }
        
        return stats


def create_sample_json_drafts() -> List[Dict[str, Any]]:
    """
    Create sample JSON drafts for testing BioPython alignment
    
    Returns:
        List of sample draft dictionaries with realistic legal document content
    """
    return [
        {
            "draft_id": "Draft_1",
            "blocks": [
                {
                    "id": "block_1",
                    "text": "This Indenture, made this 3rd day of August, between John Smith, a widow, and Mary Jones."
                },
                {
                    "id": "block_2", 
                    "text": "Beginning at a point N.37°00'W. from the corner, thence South to the boundary."
                },
                {
                    "id": "block_3",
                    "text": "The Southwest Quarter of Section 15, Township 2 North, Range 3 West."
                }
            ]
        },
        {
            "draft_id": "Draft_2",
            "blocks": [
                {
                    "id": "block_1",
                    "text": "This Indenture, made this 3rd day of August, between John Smith, a window, and Mary Jones."
                },
                {
                    "id": "block_2",
                    "text": "Beginning at a point N.3°00'W. from the corner, thence South to the boundary."
                },
                {
                    "id": "block_3",
                    "text": "The Southwest Quarter of Section 15, Township 2 North, Range 3 West."
                }
            ]
        },
        {
            "draft_id": "Draft_3", 
            "blocks": [
                {
                    "id": "block_1",
                    "text": "This Indenture, made this 3rd day of August, between John Smith, a widow, and Mary Jones."
                },
                {
                    "id": "block_2",
                    "text": "Beginning at a point N.37°00'W. from the corner, thence South to the boundary."
                },
                {
                    "id": "block_3",
                    "text": "The Southwest Quarter of Section 15, Township 2 North, Range 3 West."
                }
            ]
        }
    ]


def validate_json_draft_format(draft_json: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate a single JSON draft format
    
    Args:
        draft_json: Single draft dictionary to validate
        
    Returns:
        Tuple[bool, str]: (is_valid, error_message)
    """
    try:
        if not isinstance(draft_json, dict):
            return False, "Draft must be a dictionary"
        
        if 'draft_id' not in draft_json:
            return False, "Missing required 'draft_id' field"
        
        if 'blocks' not in draft_json:
            return False, "Missing required 'blocks' field"
        
        if not isinstance(draft_json['blocks'], list):
            return False, "'blocks' must be a list"
        
        for i, block in enumerate(draft_json['blocks']):
            if not isinstance(block, dict):
                return False, f"Block {i} must be a dictionary"
            
            if 'id' not in block:
                return False, f"Block {i} missing required 'id' field"
            
            if 'text' not in block:
                return False, f"Block {i} missing required 'text' field"
            
            if not isinstance(block['text'], str):
                return False, f"Block {i} 'text' must be a string"
        
        return True, "Valid JSON draft format"
        
    except Exception as e:
        return False, f"Validation error: {e}" 