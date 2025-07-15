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
import nltk
from nltk.tokenize import word_tokenize
import os
from dataclasses import dataclass

from .alignment_config import ANCHOR_PATTERNS
from .alignment_utils import encode_tokens_for_alignment
from .format_mapping import FormatMapper, FormatMapping, TokenPosition

logger = logging.getLogger(__name__)


@dataclass
class DirectTokenMapping:
    """Direct mapping between formatted and normalized tokens"""
    token_id: int           # Position in original formatted sequence
    formatted_token: str    # Original token with formatting
    normalized_tokens: List[str]  # List of normalized tokens (can be multiple)

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
        
        # NEW: Initialize format mapper for preserving formatting
        self.format_mapper = FormatMapper()
    
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
        Parses drafts to extract text from each section, grouping corresponding sections across drafts.
        
        Handles two cases:
        1. JSON payload in first block's text (legacy format)
        2. Simple text blocks (new format)
        
        Returns:
            Dict[block_id, Dict[draft_id, text]] 
            e.g. {'section_1': {'Draft_1': 'text...', 'Draft_2': 'text...'}, 'section_2': ...}
        """
        blocks_by_id = defaultdict(dict)

        for draft_container in draft_jsons:
            draft_id = draft_container.get('draft_id')
            
            if not draft_container.get('blocks'):
                continue
            
            # Check if this is a JSON payload or simple text blocks
            first_block_text = draft_container['blocks'][0].get('text', '')
            
            # Try to parse as JSON first (legacy format)
            try:
                document_data = json.loads(first_block_text)
                sections = document_data.get('sections', [])
                
                if not isinstance(sections, list):
                    logger.warning(f"Draft '{draft_id}' has a 'sections' field that is not a list. Skipping.")
                    continue

                # Process JSON sections (legacy format)
                for section in sections:
                    section_id = section.get('id')
                    if section_id is None:
                        continue
                    
                    # Combine header and body to form the text for this section.
                    header = section.get('header') or ""
                    body = section.get('body') or ""
                    section_text = f"{header} {body}".strip()

                    # Use a consistent block ID, e.g., "section_1"
                    block_id_key = f"section_{section_id}"
                    blocks_by_id[block_id_key][draft_id] = section_text

            except json.JSONDecodeError:
                # Not JSON, treat as simple text blocks (new format)
                logger.info(f"Draft '{draft_id}' contains simple text blocks, not JSON payload.")
                
                for block in draft_container['blocks']:
                    block_id = block.get('id')
                    block_text = block.get('text', '')
                    
                    if block_id and block_text:
                        blocks_by_id[block_id][draft_id] = block_text
                        
            except Exception as e:
                logger.error(f"Error processing blocks for draft '{draft_id}': {e}")
                continue

        return dict(blocks_by_id)
    
    def _tokenize_with_unified_path(self, text: str) -> Tuple[List[str], List[str], List[DirectTokenMapping]]:
        """
        Unified tokenization path: original text -> formatted tokens -> normalized tokens
        
        This creates direct 1:1+ mapping while preserving the exact same normalization 
        logic as the current system.
        
        Returns:
            Tuple of (formatted_tokens, normalized_tokens, mappings)
        """
        if not text or not text.strip():
            return [], [], []
        
        # STEP 1: Get formatted tokens (same as current _tokenize_original_text)
        formatted_tokens = word_tokenize(text)
        
        # STEP 2: Apply existing normalization logic to each formatted token
        all_normalized_tokens = []
        mappings = []
        
        for token_id, formatted_token in enumerate(formatted_tokens):
            # Apply the EXACT same normalization as current _normalize_text() but to each token
            normalized_result = self._apply_normalization_to_token(formatted_token)
            
            # Split the normalized result into individual tokens (handles multi-word results)
            if normalized_result and not normalized_result.isspace():
                # Split on whitespace to handle multi-word results like 'a d' -> ['a', 'd']
                normalized_sub_tokens = normalized_result.split()
                
                if normalized_sub_tokens:
                    # Add all normalized sub-tokens to the final list
                    all_normalized_tokens.extend(normalized_sub_tokens)
                    
                    # Create mapping with list of normalized tokens
                    mappings.append(DirectTokenMapping(
                        token_id=token_id,
                        formatted_token=formatted_token,
                        normalized_tokens=normalized_sub_tokens
                    ))
        
        return formatted_tokens, all_normalized_tokens, mappings
    
    def _apply_normalization_to_token(self, token: str) -> str:
        """
        Apply the EXACT same normalization logic as _normalize_text() to a single token.
        
        This preserves the current normalization behavior exactly.
        """
        if not token:
            return ""
        
        # Apply the exact same steps as the current _normalize_text()
        normalized = token
        
        # Step 1: Lowercase
        normalized = normalized.lower()
        
        # Step 2: Canonicalize numbers (same regex as current)
        normalized = re.sub(r'(?<=\d)[,\s]+(?=\d)', '', normalized)
        
        # Step 3: Protect decimal points (same as current)
        normalized = re.sub(r'(?<=\d)\.(?=\d)', 'DOT', normalized)
        
        # Step 4: Replace non-alphanumeric chars with space (same as current)
        normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized.replace('DOT', ' ')).replace('DOT', '.')
        
        # Step 5: Collapse spaces and strip (same as current)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    def _process_single_block(self, block_id: str, draft_texts: Dict[str, str], 
                            global_token_mappings: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single block across all drafts with unified tokenization path"""
        
        logger.info(f"🔍 UNIFIED TOKENIZATION PATH ► Block '{block_id}'")
        
        # Tokenize all drafts for this block with unified path
        tokenized_drafts = []
        all_tokens = set()  # Collect all unique normalized tokens
        
        for draft_id, text in draft_texts.items():
            logger.info(f"   📝 {draft_id} PROCESSING ► {len(text)} chars")
            logger.info(f"      Original text: {text[:100]}...")
            
            # NEW: Use unified tokenization path
            formatted_tokens, normalized_tokens, token_mappings = self._tokenize_with_unified_path(text)
            
            logger.info(f"   🔧 {draft_id} UNIFIED RESULTS:")
            logger.info(f"      Formatted tokens ({len(formatted_tokens)}): {formatted_tokens[:10]}...")
            logger.info(f"      Normalized tokens ({len(normalized_tokens)}): {normalized_tokens[:10]}...")
            
            # Log sample mappings to verify the process
            logger.info(f"   🎯 {draft_id} SAMPLE MAPPINGS:")
            for i, mapping in enumerate(token_mappings[:5]):
                logger.info(f"      [{mapping.token_id}]: '{mapping.formatted_token}' → {mapping.normalized_tokens}")
            
            tokenized_drafts.append({
                'draft_id': draft_id,
                'tokens': normalized_tokens,           # For alignment (same as before)
                'original_tokens': formatted_tokens,   # For format preservation 
                'token_mappings': token_mappings,      # NEW: Direct mapping
                'text': text,
                'token_count': len(normalized_tokens)
            })
            all_tokens.update(normalized_tokens)
        
        # Add detailed character-level analysis of the source text
        logger.info(f"   🔍 SOURCE TEXT CHARACTER ANALYSIS:")
        for i, (draft_id, text) in enumerate(draft_texts.items()):
            logger.info(f"      {draft_id} chars: {[ord(c) for c in text[:50]]}")
            if i > 0:
                prev_text = list(draft_texts.values())[0]
                if text == prev_text:
                    logger.warning(f"         ❌ SOURCE TEXT IS IDENTICAL TO FIRST DRAFT")
                else:
                    logger.info(f"         ✅ SOURCE TEXT IS DIFFERENT FROM FIRST DRAFT")

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
            
            # Update the encoded_drafts creation to include token_mappings
            encoded_drafts.append({
                'draft_id': draft_data['draft_id'],
                'tokens': draft_data['tokens'],
                'encoded_tokens': encoded_tokens,
                'text': draft_data['text'],
                'token_count': draft_data['token_count'],
                'original_text': draft_data['text'],
                # NEW: Add direct token mappings for perfect traceability
                'token_mappings': draft_data['token_mappings'],
                'original_tokens': draft_data['original_tokens']
            })
        
        # Replace the format mapping creation section with:
        format_mappings = {}
        for draft_data in tokenized_drafts:
            # NEW: Create format mapping using direct token mappings (no guesswork!)
            mapping = self._create_direct_format_mapping(
                draft_data['draft_id'],
                draft_data['text'],
                draft_data['token_mappings']
            )
            format_mappings[draft_data['draft_id']] = mapping
            
            logger.info(f"🎯 DIRECT FORMAT MAPPING ► {draft_data['draft_id']}: {len(mapping.token_positions)} exact mappings")
        
        return {
            'block_id': block_id,
            'tokenized_drafts': tokenized_drafts,
            'encoded_drafts': encoded_drafts,
            'token_to_id': token_to_id,
            'id_to_token': id_to_token,
            'unique_token_count': len(token_to_id),
            'draft_count': len(encoded_drafts),
            'format_mappings': format_mappings
        }
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for alignment with debug logging
        """
        original_text = text
        logger.debug(f"🔍 NORMALIZATION DEBUG ► Input: '{text[:50]}...'")
        
        text = text.lower()
        logger.debug(f"   After lowercase: '{text[:50]}...'")
        
        # Canonicalize numbers before stripping punctuation
        text = re.sub(r'(?<=\d)[,\s]+(?=\d)', '', text)
        logger.debug(f"   After number canonicalization: '{text[:50]}...'")
        
        # Protect decimal points by replacing them with a sentinel
        text = re.sub(r'(?<=\d)\.(?=\d)', 'DOT', text)
        
        # Replace all non-alphanumeric chars (except our sentinel) with a space
        text = re.sub(r'[^a-z0-9\s]', ' ', text.replace('DOT', ' ')).replace('DOT','.')
        logger.debug(f"   After punctuation removal: '{text[:50]}...'")
        
        # Collapse multiple spaces into one
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        logger.debug(f"   Final normalized: '{text[:50]}...'")
        
        return text
    
    def _tokenize_legal_text(self, text: str) -> List[str]:
        """
        Tokenize text into meaningful legal document tokens using NLTK's word_tokenize.
        """
        if not text or not text.strip():
            return []
        text = self._normalize_text(text)
        tokens = word_tokenize(text)
        return tokens
    
    def _tokenize_original_text(self, text: str) -> List[str]:
        """
        Tokenize original text WITHOUT normalization for format mapping.
        
        This preserves the original tokens so format mapper can properly map
        between original text and tokens containing formatting symbols.
        """
        if not text or not text.strip():
            return []
        
        # Tokenize original text directly without normalization to preserve formatting
        tokens = word_tokenize(text)
        return tokens
    
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

    def _create_direct_format_mapping(self, draft_id: str, original_text: str, 
                                    token_mappings: List[DirectTokenMapping]) -> FormatMapping:
        """
        Create format mapping using direct token mappings (no similarity calculations needed).
        """
        token_positions = []
        
        # Calculate character positions for each formatted token in the original text
        text_pos = 0
        normalized_token_index = 0  # Track position in normalized token sequence
        
        for mapping in token_mappings:
            # Find this formatted token in the original text
            token_start = original_text.find(mapping.formatted_token, text_pos)
            if token_start == -1:
                # Fallback: use current position
                token_start = text_pos
            token_end = token_start + len(mapping.formatted_token)
            text_pos = token_end
            
            # Create a TokenPosition for each normalized token produced by this formatted token
            for norm_token in mapping.normalized_tokens:
                token_positions.append(TokenPosition(
                    token_index=normalized_token_index,  # Position in normalized sequence
                    start_char=token_start,
                    end_char=token_end,
                    original_text=mapping.formatted_token,  # The formatted token that produced this
                    normalized_text=norm_token              # The specific normalized token
                ))
                normalized_token_index += 1
        
        return FormatMapping(
            draft_id=draft_id,
            original_text=original_text,
            token_positions=token_positions
        )


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