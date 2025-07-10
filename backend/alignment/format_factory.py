import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class FormatFactory:
    """
    Reconstructs original draft formatting onto raw alignment results.
    This class takes the output of the alignment engine and the initial
    tokenization data (which includes format mappings) and produces
    the final, human-readable, formatted alignment for the frontend.
    """

    def _apply_smart_spacing(self, text: str, original_whitespace: str) -> str:
        """
        Applies the original whitespace that followed a token.
        """
        return text + original_whitespace

    def reconstruct_formatted_alignment(
        self,
        alignment_results: Dict[str, Any],
        tokenized_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Creates the final, frontend-ready alignment results by re-applying
        original text and spacing.

        Args:
            alignment_results: The raw output from the alignment process.
            tokenized_data: The output from the tokenizer, containing format maps.

        Returns:
            A dictionary containing the reconstructed alignment, ready for display.
        """
        logger.info("✍️ Reconstructing formatted text from alignment results...")
        reformatted_blocks = {}

        # Extract format maps for easy lookup: {block_id: {draft_id: {token_idx: format_info}}}
        all_format_maps = {
            block_id: block.get('format_mappings', {})
            for block_id, block in tokenized_data.get('blocks', {}).items()
        }

        for block_id, block_data in alignment_results.get('blocks', {}).items():
            reformatted_sequences = []
            block_format_maps = all_format_maps.get(block_id, {})

            for seq_data in block_data.get('aligned_sequences', []):
                draft_id = seq_data['draft_id']
                draft_format_map = block_format_maps.get(draft_id, {})
                if not draft_format_map:
                    logger.warning(f"No format map for draft '{draft_id}' in block '{block_id}'")

                reconstructed_tokens = []
                # This map links an aligned index to its original index before alignment.
                # It is created by the alignment engine.
                original_to_alignment_map = {v: k for k, v in seq_data.get('alignment_to_original_map', {}).items()}

                for i, token in enumerate(seq_data['tokens']):
                    if token == '-':
                        reconstructed_tokens.append({'text': '-', 'is_gap': True})
                        continue

                    original_index = original_to_alignment_map.get(i)
                    if original_index is not None:
                        token_format_info = draft_format_map.get(str(original_index))
                        if token_format_info:
                            reconstructed_text = self._apply_smart_spacing(
                                token_format_info['original_text'],
                                token_format_info.get('whitespace_after', ' ')
                            )
                            reconstructed_tokens.append({
                                'text': reconstructed_text,
                                'is_gap': False
                            })
                        else:
                            # Fallback if format info is missing
                            reconstructed_tokens.append({'text': self._apply_smart_spacing(token, ' '), 'is_gap': False})
                    else:
                        # Fallback if alignment map is missing
                        reconstructed_tokens.append({'text': self._apply_smart_spacing(token, ' '), 'is_gap': False})

                reformatted_sequences.append({
                    'draft_id': draft_id,
                    # Join the tokens into a single string for display
                    'formatted_text': "".join(token['text'] for token in reconstructed_tokens)
                })

            reformatted_blocks[block_id] = {
                'block_id': block_id,
                'aligned_sequences': reformatted_sequences,
            }
        logger.info("✅ Formatted text reconstruction complete.")
        return {'blocks': reformatted_blocks} 