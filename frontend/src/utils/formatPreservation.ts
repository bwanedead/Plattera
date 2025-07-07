/**
 * Format Preservation Utility
 * 
 * Handles detection, storage, and re-application of formatting patterns
 * found in legal documents (degrees, parentheses, directions, etc.)
 */

export interface FormatPattern {
  name: string;
  pattern: RegExp;
  template: string;
  priority: number; // Higher priority patterns are applied first
  description: string;
}

export interface FormattedToken {
  cleanValue: string;      // "4" - what gets edited
  formattedValue: string;  // "4°" - what gets displayed
  originalValue: string;   // "4°" - original from document
  formatPattern?: string;  // "degree" - pattern name if detected
  formatTemplate?: string; // "{{value}}°" - template for re-application
}

export interface FormatMapping {
  blockIndex: number;
  tokenIndex: number;
  token: FormattedToken;
}

/**
 * Predefined formatting patterns for legal documents
 */
export const LEGAL_FORMAT_PATTERNS: FormatPattern[] = [
  {
    name: 'degree_minute',
    pattern: /(\d+)°\s*(\d+)'/g,
    template: '{{deg}}° {{min}}\'',
    priority: 10,
    description: 'Degrees and minutes (e.g., 4° 00\')'
  },
  {
    name: 'degree_only',
    pattern: /(\d+)°/g,
    template: '{{value}}°',
    priority: 9,
    description: 'Degrees only (e.g., 68°)'
  },
  {
    name: 'parenthetical_number',
    pattern: /\((\d+)\)/g,
    template: '({{value}})',
    priority: 8,
    description: 'Parenthetical numbers (e.g., (2))'
  },
  {
    name: 'directional_abbrev',
    pattern: /\b([NSEW])\.(?:\s|$)/g,
    template: '{{value}}.',
    priority: 7,
    description: 'Directional abbreviations (e.g., N., S., E., W.)'
  },
  {
    name: 'section_reference',
    pattern: /\bSection\s+([A-Za-z]+)/g,
    template: 'Section {{value}}',
    priority: 6,
    description: 'Section references (e.g., Section Two)'
  },
  {
    name: 'township_reference',
    pattern: /\bTownship\s+([A-Za-z]+)/g,
    template: 'Township {{value}}',
    priority: 5,
    description: 'Township references (e.g., Township Fourteen)'
  },
  {
    name: 'range_reference',
    pattern: /\bRange\s+([A-Za-z\-]+)/g,
    template: 'Range {{value}}',
    priority: 4,
    description: 'Range references (e.g., Range Seventy-four)'
  }
];

/**
 * Extract formatting information from original text tokens
 */
export function extractFormatMapping(
  originalText: string,
  cleanTokens: string[],
  blockIndex: number = 0
): FormatMapping[] {
  console.log(`📝 FORMAT EXTRACTION Block ${blockIndex} START`);
  console.log(`📝 Original text length: ${originalText.length}, Clean tokens: ${cleanTokens.length}`);
  console.log(`📝 Text preview: "${originalText.substring(0, 200)}..."`);
  console.log(`📝 First 10 clean tokens: [${cleanTokens.slice(0, 10).map(t => `"${t}"`).join(', ')}]`);
  
  const mappings: FormatMapping[] = [];
  const words = originalText.split(/\s+/);
  
  console.log(`📝 Original words: ${words.length}, First 10: [${words.slice(0, 10).map(w => `"${w}"`).join(', ')}]`);
  
  // Create a mapping between clean tokens and original words
  let cleanIndex = 0;
  let originalIndex = 0;
  let formatPatternsFound = 0;
  
  while (cleanIndex < cleanTokens.length && originalIndex < words.length) {
    const cleanToken = cleanTokens[cleanIndex].toLowerCase();
    const originalWord = words[originalIndex];
    const cleanOriginal = originalWord.toLowerCase().replace(/[^\w]/g, '');
    
    if (cleanIndex < 10) { // Only log first 10 for brevity
      console.log(`📝 Comparing token ${cleanIndex}: clean="${cleanToken}" vs original="${originalWord}" (cleaned="${cleanOriginal}")`);
    }
    
    if (cleanToken === cleanOriginal || cleanToken === originalWord.toLowerCase()) {
      // Direct match - check for formatting patterns
      const formatInfo = detectFormatting(originalWord, cleanToken);
      
      if (formatInfo.formatPattern) {
        formatPatternsFound++;
        console.log(`🎨 FORMAT PATTERN FOUND #${formatPatternsFound}: "${originalWord}" -> pattern: ${formatInfo.formatPattern}, template: ${formatInfo.formatTemplate}`);
      }
      
      mappings.push({
        blockIndex,
        tokenIndex: cleanIndex,
        token: {
          cleanValue: cleanToken,
          formattedValue: formatInfo.formattedValue,
          originalValue: originalWord,
          formatPattern: formatInfo.formatPattern,
          formatTemplate: formatInfo.formatTemplate
        }
      });
      
      cleanIndex++;
      originalIndex++;
    } else if (cleanToken.length > cleanOriginal.length) {
      // Clean token might be multiple original words combined
      let combinedOriginal = '';
      let tempOriginalIndex = originalIndex;
      
      while (tempOriginalIndex < words.length && 
             combinedOriginal.replace(/[^\w]/g, '').toLowerCase().length < cleanToken.length) {
        combinedOriginal += words[tempOriginalIndex] + ' ';
        tempOriginalIndex++;
      }
      
      if (cleanIndex < 10) { // Only log first 10
        console.log(`📝 Multi-word attempt: "${cleanToken}" vs "${combinedOriginal.trim()}"`);
      }
      
      if (combinedOriginal.trim().replace(/[^\w\s]/g, '').toLowerCase() === cleanToken) {
        mappings.push({
          blockIndex,
          tokenIndex: cleanIndex,
          token: {
            cleanValue: cleanToken,
            formattedValue: combinedOriginal.trim(),
            originalValue: combinedOriginal.trim(),
            formatPattern: undefined,
            formatTemplate: undefined
          }
        });
        
        cleanIndex++;
        originalIndex = tempOriginalIndex;
      } else {
        // Skip this original word
        if (originalIndex < 10) console.log(`📝 Skipping original: "${originalWord}"`);
        originalIndex++;
      }
    } else {
      // Skip this original word
      if (originalIndex < 10) console.log(`📝 Skipping original: "${originalWord}"`);
      originalIndex++;
    }
  }
  
  console.log(`📝 FORMAT EXTRACTION COMPLETE: ${mappings.length} mappings created, ${formatPatternsFound} format patterns found`);
  console.log(`📝 Mappings with formatting: ${mappings.filter(m => m.token.formatPattern).length}`);
  
  // Log first few format mappings for debugging
  const formattedMappings = mappings.filter(m => m.token.formatPattern).slice(0, 5);
  formattedMappings.forEach((m, i) => {
    console.log(`📝 Format mapping ${i + 1}: token[${m.tokenIndex}] "${m.token.originalValue}" -> pattern: ${m.token.formatPattern}`);
  });
  
  return mappings;
}

/**
 * Detect formatting pattern in a single word/token
 */
export function detectFormatting(originalWord: string, cleanValue: string): {
  formattedValue: string;
  formatPattern?: string;
  formatTemplate?: string;
} {
  // Only log if word has special characters
  const hasSpecialChars = /[°'"().,;:-]/.test(originalWord);
  if (hasSpecialChars) {
    console.log(`🔍 Checking pattern for: "${originalWord}" -> "${cleanValue}"`);
  }
  
  for (const pattern of LEGAL_FORMAT_PATTERNS) {
    const match = originalWord.match(pattern.pattern);
    if (match) {
      console.log(`✅ PATTERN MATCHED: "${originalWord}" -> ${pattern.name} (template: ${pattern.template})`);
      
      return {
        formattedValue: originalWord,
        formatPattern: pattern.name,
        formatTemplate: pattern.template
      };
    }
  }
  
  // No pattern detected, check for simple case differences
  if (originalWord.toLowerCase() === cleanValue.toLowerCase() && originalWord !== cleanValue) {
    console.log(`💡 Case formatting: "${originalWord}" vs "${cleanValue}"`);
    return {
      formattedValue: originalWord,
      formatPattern: 'case_formatting',
      formatTemplate: originalWord.replace(cleanValue, '{{value}}')
    };
  }
  
  if (hasSpecialChars) {
    console.log(`❌ No pattern detected for: "${originalWord}"`);
  }
  return {
    formattedValue: cleanValue,
    formatPattern: undefined,
    formatTemplate: undefined
  };
}

/**
 * Apply formatting pattern to a new value
 */
export function applyFormattingPattern(
  originalFormatting: FormattedToken,
  newCleanValue: string
): string {
  if (!originalFormatting.formatPattern || !originalFormatting.formatTemplate) {
    return newCleanValue;
  }
  
  console.log(`🎨 Applying format: "${originalFormatting.originalValue}" (${originalFormatting.formatPattern}) to "${newCleanValue}"`);
  
  const pattern = LEGAL_FORMAT_PATTERNS.find(p => p.name === originalFormatting.formatPattern);
  if (!pattern) {
    console.log(`❌ Pattern not found: ${originalFormatting.formatPattern}`);
    return newCleanValue;
  }
  
  let result = newCleanValue;
  
  switch (originalFormatting.formatPattern) {
    case 'degree_minute':
      // Handle "4° 00'" pattern - preserve minute value when degree changes
      const degreeMatch = originalFormatting.originalValue.match(/(\d+)°\s*(\d+)'/);
      if (degreeMatch) {
        const [, , minutes] = degreeMatch;
        result = `${newCleanValue}° ${minutes}'`;
      }
      break;
      
    case 'degree_only':
      result = `${newCleanValue}°`;
      break;
      
    case 'parenthetical_number':
      result = `(${newCleanValue})`;
      break;
      
    case 'directional_abbrev':
      result = `${newCleanValue.toUpperCase()}.`;
      break;
      
    case 'section_reference':
      result = `Section ${capitalizeFirst(newCleanValue)}`;
      break;
      
    case 'township_reference':
      result = `Township ${capitalizeFirst(newCleanValue)}`;
      break;
      
    case 'range_reference':
      result = `Range ${capitalizeFirst(newCleanValue)}`;
      break;
      
    case 'case_formatting':
      // Try to preserve original casing pattern
      result = preserveCasing(originalFormatting.originalValue, newCleanValue);
      break;
      
    default:
      result = originalFormatting.formatTemplate?.replace(/\{\{value\}\}/g, newCleanValue) || newCleanValue;
  }
  
  console.log(`✅ Format applied: "${newCleanValue}" -> "${result}" using ${originalFormatting.formatPattern}`);
  return result;
}

/**
 * Apply formatting to entire text blocks
 */
export function applyFormattingToText(
  cleanText: string,
  formatMappings: FormatMapping[]
): string {
  console.log(`🎨 APPLYING FORMATTING: Text length: ${cleanText.length}, Mappings: ${formatMappings.length}`);
  console.log(`🎨 Text preview: "${cleanText.substring(0, 200)}..."`);
  
  let formattedText = cleanText;
  const tokens = cleanText.split(/\s+/);
  
  // Sort mappings by token index to apply in correct order
  const sortedMappings = formatMappings
    .filter(mapping => mapping.blockIndex === 0) // Assuming single block for now
    .sort((a, b) => a.tokenIndex - b.tokenIndex);
  
  console.log(`🎨 Applicable mappings for block 0: ${sortedMappings.length}`);
  
  let changesApplied = 0;
  
  // Apply formatting patterns from right to left to preserve indices
  for (let i = sortedMappings.length - 1; i >= 0; i--) {
    const mapping = sortedMappings[i];
    const { tokenIndex, token } = mapping;
    
    if (tokenIndex < tokens.length) {
      const cleanToken = tokens[tokenIndex];
      const formattedToken = applyFormattingPattern(token, cleanToken);
      
      if (formattedToken !== cleanToken) {
        tokens[tokenIndex] = formattedToken;
        changesApplied++;
        console.log(`🎨 Applied format ${changesApplied}: token[${tokenIndex}] "${cleanToken}" -> "${formattedToken}"`);
      }
    }
  }
  
  const result = tokens.join(' ');
  console.log(`🎨 FORMATTING COMPLETE: ${changesApplied} changes applied`);
  console.log(`🎨 Result preview: "${result.substring(0, 200)}..."`);
  
  return result;
}

/**
 * Helper function to capitalize first letter
 */
function capitalizeFirst(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
}

/**
 * Helper function to preserve casing pattern
 */
function preserveCasing(originalWord: string, newValue: string): string {
  if (originalWord === originalWord.toUpperCase()) {
    return newValue.toUpperCase();
  } else if (originalWord === originalWord.toLowerCase()) {
    return newValue.toLowerCase();
  } else if (originalWord.charAt(0) === originalWord.charAt(0).toUpperCase()) {
    return capitalizeFirst(newValue);
  }
  return newValue;
}

/**
 * Handle coordinate-specific editing (degrees, minutes)
 */
export function handleCoordinateEdit(
  originalValue: string,
  newValue: string,
  isDegreePart: boolean
): string {
  console.log(`🧭 Coordinate edit: "${originalValue}" -> "${newValue}" (isDegreePart: ${isDegreePart})`);
  
  const degreeMinutePattern = /(\d+)°\s*(\d+)'/;
  const match = originalValue.match(degreeMinutePattern);
  
  if (match) {
    const [, degrees, minutes] = match;
    if (isDegreePart) {
      const result = `${newValue}° ${minutes}'`;
      console.log(`🧭 Updated degrees: "${result}"`);
      return result;
    } else {
      const result = `${degrees}° ${newValue}'`;
      console.log(`🧭 Updated minutes: "${result}"`);
      return result;
    }
  }
  
  return newValue;
} 