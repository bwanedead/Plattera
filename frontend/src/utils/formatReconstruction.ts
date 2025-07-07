/**
 * Format Reconstruction Utility
 * 
 * Works with backend format reconstruction data to restore original formatting
 * in aligned text. Integrates with the existing formatPreservation.ts utility.
 */

export interface TokenPosition {
  token_index: number;
  start_char: number;
  end_char: number;
  original_text: string;
  normalized_text: string;
}

export interface FormatMappingData {
  draft_id: string;
  original_text: string;
  token_positions: TokenPosition[];
}

export interface DraftReconstructionData {
  aligned_tokens: string[];
  original_to_alignment: number[];
  format_mapping: FormatMappingData;
}

export interface BlockReconstructionData {
  [draft_id: string]: DraftReconstructionData;
}

export interface FormatReconstructionResult {
  blocks: {
    [block_id: string]: BlockReconstructionData;
  };
  reconstruction_available: boolean;
}

/**
 * Reconstruct formatted text from alignment results with format reconstruction data
 */
export function reconstructFormattedText(
  blockId: string,
  draftId: string,
  formatReconstruction: FormatReconstructionResult
): string {
  console.log(`🔄 RECONSTRUCTING formatted text for block: ${blockId}, draft: ${draftId}`);
  
  if (!formatReconstruction.reconstruction_available) {
    console.log('❌ No format reconstruction data available');
    return '';
  }

  const blockData = formatReconstruction.blocks[blockId];
  if (!blockData) {
    console.log(`❌ No reconstruction data for block: ${blockId}`);
    return '';
  }

  const draftData = blockData[draftId];
  if (!draftData) {
    console.log(`❌ No reconstruction data for draft: ${draftId}`);
    return '';
  }

  const { aligned_tokens, original_to_alignment, format_mapping } = draftData;
  
  console.log(`📊 Reconstruction data:`, {
    alignedTokens: aligned_tokens.length,
    mappingPositions: format_mapping.token_positions.length,
    originalText: format_mapping.original_text.substring(0, 100) + '...'
  });

  // Reconstruct the formatted text
  const reconstructedParts: string[] = [];
  
  for (let alignedIdx = 0; alignedIdx < aligned_tokens.length; alignedIdx++) {
    const token = aligned_tokens[alignedIdx];
    
    if (token === '-') {
      // Skip alignment gaps
      continue;
    }
    
    // Find which original token this aligned position corresponds to
    const originalTokenIdx = original_to_alignment.findIndex(
      (alignedPos) => alignedPos === alignedIdx
    );
    
    if (originalTokenIdx !== -1) {
      // Get the original formatting for this token
      const position = format_mapping.token_positions.find(
        (pos) => pos.token_index === originalTokenIdx
      );
      
      if (position) {
        // Check if the token has been modified during editing
        if (token.toLowerCase() === position.normalized_text.toLowerCase()) {
          // Token unchanged - use original formatting
          reconstructedParts.push(position.original_text);
          console.log(`✅ Token ${originalTokenIdx}: "${position.original_text}" (preserved)`);
        } else {
          // Token was edited - apply formatting pattern to new value
          const formattedToken = applyFormattingPattern(token, position.original_text);
          reconstructedParts.push(formattedToken);
          console.log(`🔄 Token ${originalTokenIdx}: "${position.original_text}" → "${formattedToken}" (pattern applied)`);
        }
      } else {
        // No position mapping found - use token as-is
        reconstructedParts.push(token);
        console.log(`⚠️ Token ${originalTokenIdx}: "${token}" (no mapping)`);
      }
    } else {
      // No original token mapping found - use token as-is
      reconstructedParts.push(token);
      console.log(`⚠️ Aligned token: "${token}" (no original mapping)`);
    }
  }
  
  const result = reconstructedParts.join(' ');
  console.log(`✅ RECONSTRUCTION COMPLETE: "${result.substring(0, 100)}..."`);
  
  return result;
}

/**
 * Apply formatting pattern from original text to new token value
 */
function applyFormattingPattern(newToken: string, originalText: string): string {
  // Degree symbol preservation
  if (originalText.includes('°')) {
    if (/^\d+$/.test(newToken)) {
      return `${newToken}°`;
    } else if (originalText.includes("'")) {
      // Handle degree-minute format
      const parts = newToken.split(/\s+/);
      if (parts.length === 2 && /^\d+$/.test(parts[0]) && /^\d+$/.test(parts[1])) {
        return `${parts[0]}° ${parts[1]}'`;
      }
    }
  }
  
  // Parentheses preservation
  if (originalText.startsWith('(') && originalText.endsWith(')')) {
    return `(${newToken})`;
  }
  
  // Directional abbreviation preservation
  if (originalText.endsWith('.') && originalText.length <= 3) {
    return `${newToken}.`;
  }
  
  // Comma in numbers preservation
  if (originalText.includes(',') && /^\d+$/.test(newToken)) {
    // Add comma for thousands separator if number is large enough
    if (newToken.length >= 4) {
      return `${newToken.slice(0, -3)},${newToken.slice(-3)}`;
    }
  }
  
  // Default: return new token as-is
  return newToken;
}

/**
 * Check if format reconstruction is available for a specific block and draft
 */
export function isFormatReconstructionAvailable(
  blockId: string,
  draftId: string,
  formatReconstruction?: FormatReconstructionResult
): boolean {
  if (!formatReconstruction?.reconstruction_available) {
    return false;
  }
  
  const blockData = formatReconstruction.blocks[blockId];
  if (!blockData) {
    return false;
  }
  
  const draftData = blockData[draftId];
  return !!draftData && !!draftData.format_mapping;
}

/**
 * Get formatting statistics for a block
 */
export function getFormattingStatistics(
  blockId: string,
  formatReconstruction: FormatReconstructionResult
): {
  totalDrafts: number;
  draftsWithFormatting: number;
  totalTokensWithFormatting: number;
} {
  const blockData = formatReconstruction.blocks[blockId];
  if (!blockData) {
    return { totalDrafts: 0, draftsWithFormatting: 0, totalTokensWithFormatting: 0 };
  }
  
  const draftIds = Object.keys(blockData);
  let draftsWithFormatting = 0;
  let totalTokensWithFormatting = 0;
  
  for (const draftId of draftIds) {
    const draftData = blockData[draftId];
    if (draftData.format_mapping.token_positions.length > 0) {
      draftsWithFormatting++;
      
      // Count tokens that have different original vs normalized text
      const formattedTokens = draftData.format_mapping.token_positions.filter(
        pos => pos.original_text !== pos.normalized_text
      );
      totalTokensWithFormatting += formattedTokens.length;
    }
  }
  
  return {
    totalDrafts: draftIds.length,
    draftsWithFormatting,
    totalTokensWithFormatting
  };
} 