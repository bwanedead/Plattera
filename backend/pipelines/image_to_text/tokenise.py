"""
Tokenization Module
==================

Tokenizes text with special handling for legal document elements.
Implements the regex-based tokenization from the specification.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from .alignment_config import ANCHOR_PATTERNS, TOKENIZATION

logger = logging.getLogger(__name__)

@dataclass
class Token:
    """Represents a single token with metadata"""
    text: str
    type: str
    position: int
    is_anchor: bool = False
    original_position: Optional[Tuple[int, int]] = None

class DocumentTokenizer:
    """Tokenizes legal documents with anchor-aware processing"""
    
    def __init__(self):
        # Compile patterns with priority order (anchors first)
        self.patterns = {}
        self.pattern_order = ["FRAC", "BEAR", "DEG", "ID", "NUM", "WORD", "PUN"]
        
        for name, pattern in ANCHOR_PATTERNS.items():
            self.patterns[name] = re.compile(pattern, re.IGNORECASE)
        
        # Special composite patterns
        self.composite_patterns = [
            (re.compile(r'(Township|Section|Range)\s+(\d+)', re.IGNORECASE), "ID"),
            (re.compile(r'(N|S|E|W)\s+(\d+°(?:\d+′\d+″)?)\s*(E|W)', re.IGNORECASE), "BEAR")
        ]
    
    def tokenize(self, text: str, keep_positions: bool = False) -> List[Token]:
        """
        Tokenize text into legal document tokens
        
        Args:
            text: Input text to tokenize
            keep_positions: Whether to retain position information
            
        Returns:
            List of Token objects (excluding punctuation)
        """
        if not text or not text.strip():
            return []
        
        # First pass: identify composite tokens
        composite_replacements = []
        working_text = text
        
        for pattern, token_type in self.composite_patterns:
            for match in pattern.finditer(text):
                composite_token = match.group().strip()
                placeholder = f"__COMPOSITE_{len(composite_replacements)}__"
                composite_replacements.append((placeholder, composite_token, token_type))
                working_text = working_text.replace(match.group(), placeholder, 1)
        
        # Second pass: tokenize with pattern priority
        tokens = []
        position = 0
        text_index = 0
        
        while text_index < len(working_text):
            found_match = False
            
            # Check for composite placeholders first
            for placeholder, original_text, token_type in composite_replacements:
                if working_text[text_index:].startswith(placeholder):
                    tokens.append(Token(
                        text=original_text,
                        type=token_type,
                        position=position,
                        is_anchor=True,
                        original_position=(text_index, text_index + len(placeholder)) if keep_positions else None
                    ))
                    text_index += len(placeholder)
                    position += 1
                    found_match = True
                    break
            
            if found_match:
                continue
            
            # Check patterns in priority order
            for pattern_name in self.pattern_order:
                if pattern_name not in self.patterns:
                    continue
                
                pattern = self.patterns[pattern_name]
                match = pattern.match(working_text, text_index)
                
                if match:
                    token_text = match.group()
                    
                    # Skip if this is punctuation and we're dropping it
                    if pattern_name in TOKENIZATION["DROP_PATTERNS"]:
                        text_index = match.end()
                        found_match = True
                        break
                    
                    # Add token if we're keeping this pattern
                    if pattern_name in TOKENIZATION["KEEP_PATTERNS"]:
                        is_anchor = pattern_name in ["NUM", "FRAC", "BEAR", "DEG", "ID"]
                        tokens.append(Token(
                            text=token_text,
                            type=pattern_name,
                            position=position,
                            is_anchor=is_anchor,
                            original_position=(text_index, match.end()) if keep_positions else None
                        ))
                        position += 1
                    
                    text_index = match.end()
                    found_match = True
                    break
            
            # If no pattern matched, skip character
            if not found_match:
                if not working_text[text_index].isspace():
                    logger.debug(f"Unmatched character: '{working_text[text_index]}'")
                text_index += 1
        
        logger.debug(f"Tokenized '{text[:50]}...' into {len(tokens)} tokens")
        return tokens
    
    def tokenize_sections(self, sections: List[Dict[str, Any]]) -> Dict[int, List[Token]]:
        """
        Tokenize all sections of a document
        
        Args:
            sections: List of section dictionaries with 'id' and 'body'
            
        Returns:
            Dictionary mapping section_id -> list of tokens
        """
        tokenized_sections = {}
        
        for section in sections:
            section_id = section.get("id")
            body = section.get("body", "")
            
            if section_id is not None:
                tokens = self.tokenize(body)
                tokenized_sections[section_id] = tokens
                logger.debug(f"Section {section_id}: {len(tokens)} tokens")
        
        return tokenized_sections
    
    def tokens_to_text(self, tokens: List[Token]) -> str:
        """Convert tokens back to text with appropriate spacing"""
        if not tokens:
            return ""
        
        text_parts = []
        for i, token in enumerate(tokens):
            # Add space before token (except first token and after certain punctuation)
            if i > 0 and not text_parts[-1].endswith((' ', '\n', '\t')):
                # Add space unless this token or previous token suggests no space needed
                prev_token = tokens[i-1]
                if not (prev_token.type == "PUN" and prev_token.text in "([{") and not (token.type == "PUN" and token.text in ")]}.,;"):
                    text_parts.append(" ")
            
            text_parts.append(token.text)
        
        return "".join(text_parts)
