"""
BioPython Alignment Utilities
============================

Basic utilities and dependency management for BioPython-based alignment engine.
"""

import logging
from typing import Dict, List, Any, Tuple
import numpy as np

logger = logging.getLogger(__name__)

# Check BioPython availability
try:
    from Bio.Align import PairwiseAligner
    from Bio import Align
    BIOPYTHON_AVAILABLE = True
    logger.info("✅ BioPython available for alignment processing")
except ImportError:
    BIOPYTHON_AVAILABLE = False
    logger.warning("❌ BioPython not available - install with: pip install biopython")

# Check other dependencies
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.warning("❌ NumPy not available - install with: pip install numpy")

try:
    import seaborn as sns
    import matplotlib.pyplot as plt
    VISUALIZATION_AVAILABLE = True
except ImportError:
    VISUALIZATION_AVAILABLE = False
    logger.warning("❌ Visualization libraries not available - install with: pip install seaborn matplotlib")


class AlignmentError(Exception):
    """Raised when alignment operations fail"""
    pass


def check_dependencies() -> Tuple[bool, List[str]]:
    """
    Check if all required dependencies are available
    
    Returns:
        Tuple[bool, List[str]]: (all_available, missing_packages)
    """
    missing = []
    
    if not BIOPYTHON_AVAILABLE:
        missing.append("biopython")
    if not NUMPY_AVAILABLE:
        missing.append("numpy")
    if not VISUALIZATION_AVAILABLE:
        missing.extend(["seaborn", "matplotlib"])
    
    return len(missing) == 0, missing


def get_installation_instructions() -> str:
    """Get installation instructions for missing dependencies"""
    available, missing = check_dependencies()
    
    if available:
        return "✅ All dependencies available"
    
    packages = " ".join(missing)
    return f"""
Missing Dependencies Installation:
pip install {packages}

Required packages:
- biopython: For sequence alignment
- numpy: For matrix operations  
- seaborn: For heatmap generation
- matplotlib: For visualization rendering
"""


def create_scoring_matrix() -> Dict[str, int]:
    """
    Create custom scoring parameters for legal document alignment
    
    Returns:
        Dict with scoring parameters
    """
    return {
        "match_score": 5,           # +5 for identical tokens
        "mismatch_score": -5,       # -5 for significant mismatches
        "trivial_mismatch_score": -1,  # -1 for trivial mismatches
        "gap_score": -2             # -2 for gaps (insertions/deletions)
    }


def encode_tokens_for_alignment(tokens: List[str]) -> Tuple[List[int], Dict[str, int], Dict[int, str]]:
    """
    Convert tokens to numeric IDs for BioPython alignment
    
    Args:
        tokens: List of string tokens
        
    Returns:
        Tuple of (encoded_sequence, token_to_id, id_to_token)
    """
    token_to_id = {}
    id_to_token = {}
    encoded_sequence = []
    next_id = 0
    
    for token in tokens:
        if token not in token_to_id:
            token_to_id[token] = next_id
            id_to_token[next_id] = token
            next_id += 1
        
        encoded_sequence.append(token_to_id[token])
    
    return encoded_sequence, token_to_id, id_to_token


def decode_alignment_to_tokens(encoded_alignment: Any, id_to_token: Dict[int, str]) -> List[str]:
    """
    Convert encoded alignment back to tokens
    
    Args:
        encoded_alignment: BioPython alignment object
        id_to_token: Mapping from IDs back to tokens
        
    Returns:
        List of aligned tokens (with gaps as '-')
    """
    decoded_tokens = []
    
    # Handle BioPython alignment format
    if hasattr(encoded_alignment, '__iter__'):
        for item in encoded_alignment:
            if item == -1:  # Gap character in BioPython
                decoded_tokens.append('-')
            else:
                decoded_tokens.append(id_to_token.get(item, f'UNK_{item}'))
    
    return decoded_tokens


def calculate_alignment_consistency(alignments: List[Any], position: int) -> float:
    """
    Calculate consistency score for a position across multiple alignments
    
    Args:
        alignments: List of alignment objects
        position: Position to analyze
        
    Returns:
        Consistency score (0.0 to 1.0)
    """
    if not alignments:
        return 0.0
    
    # Get tokens at this position from all alignments
    position_tokens = []
    for alignment in alignments:
        if position < len(alignment) and alignment[position] != -1:
            position_tokens.append(alignment[position])
    
    if not position_tokens:
        return 0.0
    
    # Calculate most common token frequency
    from collections import Counter
    token_counts = Counter(position_tokens)
    most_common_count = token_counts.most_common(1)[0][1]
    
    return most_common_count / len(position_tokens)


class BioPythonAlignerConfig:
    """Configuration for BioPython PairwiseAligner"""
    
    def __init__(self, scoring_params: Dict[str, int] = None):
        if scoring_params is None:
            scoring_params = create_scoring_matrix()
        
        self.scoring_params = scoring_params
        self.aligner = None
        self._configure_aligner()
    
    def _configure_aligner(self):
        """Configure BioPython PairwiseAligner with custom scoring"""
        if not BIOPYTHON_AVAILABLE:
            raise AlignmentError("BioPython not available")
        
        self.aligner = PairwiseAligner()
        
        # Set scoring parameters
        self.aligner.match_score = self.scoring_params["match_score"]
        self.aligner.mismatch_score = self.scoring_params["mismatch_score"]
        self.aligner.open_gap_score = self.scoring_params["gap_score"]
        self.aligner.extend_gap_score = self.scoring_params["gap_score"]
        
        # Use global alignment for similar legal documents
        self.aligner.mode = 'global'
        
        logger.info(f"🔧 BioPython aligner configured: match={self.aligner.match_score}, "
                   f"mismatch={self.aligner.mismatch_score}, gap={self.aligner.open_gap_score}")
    
    def align_sequences(self, seq1: List[int], seq2: List[int]) -> Any:
        """
        Align two encoded sequences
        
        Args:
            seq1, seq2: Encoded token sequences
            
        Returns:
            Best alignment from BioPython
        """
        if not self.aligner:
            raise AlignmentError("Aligner not configured")
        
        try:
            # Convert integer sequences to strings for BioPython
            # Each integer becomes a single character (A, B, C, etc.)
            str_seq1 = ''.join([chr(65 + (i % 26)) for i in seq1])  # A-Z mapping
            str_seq2 = ''.join([chr(65 + (i % 26)) for i in seq2])
            
            alignments = self.aligner.align(str_seq1, str_seq2)
            # Return the best (first) alignment
            return alignments[0] if len(alignments) > 0 else None
        except Exception as e:
            raise AlignmentError(f"Alignment failed: {e}")


def log_alignment_statistics(alignments: Dict[str, Any]):
    """Log alignment statistics for debugging"""
    total_blocks = len(alignments.get('blocks', {}))
    total_positions = 0
    total_differences = 0
    
    for block_id, block_data in alignments.get('blocks', {}).items():
        block_positions = len(block_data.get('aligned_sequences', [{}])[0].get('tokens', []))
        block_differences = len(block_data.get('differences', []))
        total_positions += block_positions
        total_differences += block_differences
        
        logger.info(f"   📋 Block '{block_id}': {block_positions} positions, {block_differences} differences")
    
    logger.info(f"📊 ALIGNMENT STATS ► {total_blocks} blocks, {total_positions} total positions, "
               f"{total_differences} differences ({total_differences/max(total_positions,1)*100:.1f}%)") 