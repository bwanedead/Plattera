interface DocumentSection {
  id: number
  header: string | null
  body: string
}

interface DocumentTranscription {
  documentId: string
  sections: DocumentSection[]
}

export interface ProcessingResult {
  extracted_text: string
  tokens_used?: number
  model_used?: string
  service_type?: string
  confidence_score?: number
  metadata?: any
  pipeline_stats?: {
    word_count?: number
    tokens_used?: number
    confidence?: number
  }
}

const VERBOSE_DEBUG = typeof process !== 'undefined' && (process as any).env && (process as any).env.NEXT_PUBLIC_VERBOSE_LOGS === 'true';

/**
 * Check if the extracted text is JSON format
 */
export function isJsonResult(extractedText: string): boolean {
  if (!extractedText) return false
  
  try {
    const parsed = JSON.parse(extractedText)
    const hasSections = parsed && typeof parsed === 'object' && Array.isArray((parsed as any).sections)
    const hasMainText = parsed && typeof parsed === 'object' && typeof (parsed as any).mainText === 'string'
    const isStructuredJson = !!(hasSections || hasMainText)
    
    if (VERBOSE_DEBUG) console.log('🔍 JSON Detection:', {
      textLength: extractedText.length,
      textPreview: extractedText.substring(0, 100),
      canParse: true,
      hasDocumentId: !!(parsed as any).documentId,
      hasSections,
      hasMainText,
      isStructuredJson
    });
    
    return isStructuredJson
  } catch (error) {
    if (VERBOSE_DEBUG) console.log('❌ JSON Detection failed:', {
      textLength: extractedText.length,
      textPreview: extractedText.substring(0, 100),
      error: error instanceof Error ? error.message : 'Unknown error'
    });
    return false
  }
}

// Accept any valid JSON (used for JSON tab visibility even for non-sections schemas)
export function canParseJson(text: string): boolean {
  if (!text) return false;
  try {
    JSON.parse(text);
    return true;
  } catch {
    return false;
  }
}

/**
 * Parse JSON result into structured format
 */
export function parseJsonResult(extractedText: string): DocumentTranscription | null {
  try {
    const parsed = JSON.parse(extractedText)
    if (parsed && Array.isArray((parsed as any).sections)) {
      return parsed as DocumentTranscription
    }
    if (VERBOSE_DEBUG) console.log('⚠️ Parsed JSON but missing required structure:', {
      hasDocumentId: !!(parsed as any).documentId,
      hasSections: Array.isArray((parsed as any).sections),
      keys: Object.keys(parsed)
    });
    return null
  } catch (error) {
    if (VERBOSE_DEBUG) console.log('❌ JSON parse error, attempting to fix common issues:', error instanceof Error ? error.message : 'Unknown error');
    
    // Try to fix common JSON issues that might occur from editing
    try {
      // Common fixes for edited JSON
      let fixedText = extractedText
        .replace(/([^"\\])"/g, '$1\\"') // Fix unescaped quotes
        .replace(/\\"/g, '"') // Remove unnecessary escaping
        .replace(/'/g, '"') // Replace single quotes with double quotes
        .replace(/,(\s*[}\]])/g, '$1'); // Remove trailing commas
      
      if (VERBOSE_DEBUG) console.log('🔧 Attempting to parse fixed JSON...');
      const parsed = JSON.parse(fixedText)
      if (parsed && Array.isArray((parsed as any).sections)) {
        if (VERBOSE_DEBUG) console.log('✅ Successfully parsed fixed JSON!');
        return parsed as DocumentTranscription
      }
    } catch (fixError) {
      if (VERBOSE_DEBUG) console.log('❌ Could not fix JSON:', fixError instanceof Error ? fixError.message : 'Unknown error');
    }
    
    return null
  }
}

/**
 * Format JSON result as readable text with proper formatting
 */
export function formatJsonAsText(extractedText: string): string {
  if (VERBOSE_DEBUG) console.log('🎨 Formatting JSON text:', {
    inputLength: extractedText.length,
    inputPreview: extractedText.substring(0, 100)
  });
  
  try {
    const parsed: any = JSON.parse(extractedText)

    // LEGAL (sections) path — unchanged
    if (Array.isArray(parsed?.sections)) {
      let formattedText = ''
      parsed.sections.forEach((section: any, index: number) => {
        if (section.header && section.header.trim()) {
          formattedText += `${section.header.trim()}\n`
        }
        if (section.body && section.body.trim()) {
          const normalizedBody = section.body.trim();
          formattedText += `${normalizedBody}\n`;
        }
        if (index < parsed.sections.length - 1) {
          formattedText += '\n';
        }
      })
      const result = formattedText.trim();
      if (VERBOSE_DEBUG) console.log('🎨 Formatting complete (sections):', {
        outputLength: result.length,
        outputPreview: result.substring(0, 200)
      });
      return result;
    }

    // GENERIC (mainText + sideTexts) path
    if (typeof parsed?.mainText === 'string') {
      let formatted = (parsed.mainText || '').trim()

      const sideTexts = Array.isArray(parsed.sideTexts) ? parsed.sideTexts : []
      if (sideTexts.length) {
        const sideFormatted = sideTexts
          .map((s: any) => {
            const type = (s?.type || 'other').toString().toUpperCase()
            const text = (s?.text || '').toString().trim()
            if (!text) return ''
            return `[${type}]\n${text}`
          })
          .filter(Boolean)
          .join('\n\n')
        if (sideFormatted) {
          formatted += (formatted ? '\n\n' : '') + sideFormatted
        }
      }

      const result = formatted.trim()
      if (VERBOSE_DEBUG) console.log('🎨 Formatting complete (generic):', {
        outputLength: result.length,
        outputPreview: result.substring(0, 200)
      });
      return result
    }

    // Fallback: pretty-print JSON
    const prettyFormatted = JSON.stringify(parsed, null, 2);
    if (VERBOSE_DEBUG) console.log('📝 Applied basic JSON pretty-formatting as fallback');
    return prettyFormatted;
  } catch {
    // Last-resort minimal formatting if JSON fails
    if (VERBOSE_DEBUG) console.log('📝 Applying minimal text formatting as last resort');
    return extractedText
      .replace(/},/g, '},\n')
      .replace(/{"/g, '{\n  "')
      .replace(/}/g, '\n}')
      .replace(/","/g, '",\n  "');
  }
}

/**
 * Pretty format JSON with proper indentation and line breaks
 */
export function formatJsonPretty(extractedText: string): string {
  try {
    const parsed = JSON.parse(extractedText)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return extractedText
  }
}

/**
 * Get word count from text (works for both plain text and JSON)
 */
export function getWordCount(text: string): number {
  if (!text) return 0
  
  // If it's JSON, count words from the formatted text version
  if (isJsonResult(text)) {
    const formatted = formatJsonAsText(text)
    return formatted.trim().split(/\s+/).filter(word => word.length > 0).length
  }
  
  return text.trim().split(/\s+/).filter(word => word.length > 0).length
}

/**
 * Extract metadata for display
 */
export function extractDisplayMetadata(result: ProcessingResult): Record<string, any> {
  const metadata: Record<string, any> = {}
  
  // Basic processing info
  if (result.model_used) metadata['Model'] = result.model_used
  if (result.service_type) metadata['Service'] = result.service_type
  if (result.tokens_used) metadata['Tokens Used'] = result.tokens_used
  if (result.confidence_score) metadata['Confidence'] = `${(result.confidence_score * 100).toFixed(1)}%`
  
  // Pipeline stats
  if (result.pipeline_stats) {
    if (result.pipeline_stats.word_count) metadata['Word Count'] = result.pipeline_stats.word_count
    if (result.pipeline_stats.tokens_used && !metadata['Tokens Used']) {
      metadata['Tokens Used'] = result.pipeline_stats.tokens_used
    }
    if (result.pipeline_stats.confidence && !metadata['Confidence']) {
      metadata['Confidence'] = `${(result.pipeline_stats.confidence * 100).toFixed(1)}%`
    }
  }
  
  // Additional metadata
  if (result.metadata) {
    Object.entries(result.metadata).forEach(([key, value]) => {
      if (value !== null && value !== undefined) {
        metadata[key.charAt(0).toUpperCase() + key.slice(1)] = value
      }
    })
  }
  
  return metadata
} 

// New function to extract clean text from potentially JSON-formatted content
export const extractCleanText = (content: string): string => {
  if (!content || typeof content !== 'string') {
    return '';
  }

  let cleanText = content.trim();
  
  // Check if this looks like JSON
  if (cleanText.startsWith('{') || cleanText.startsWith('[') || cleanText.includes('"content":')) {
    try {
      const parsed: any = JSON.parse(cleanText);
      
      // Handle different JSON structures
      if (parsed && typeof parsed === 'object') {
        if (parsed.content && typeof parsed.content === 'string') {
          cleanText = parsed.content;
        } else if (parsed.sections && Array.isArray(parsed.sections)) {
          // Handle document with sections - PRESERVE FORMATTING
          cleanText = parsed.sections
            .map((section: any) => {
              let sectionText = '';
              if (section.header && section.header.trim()) {
                sectionText += section.header.trim() + '\n';
              }
              if (section.body && section.body.trim()) {
                sectionText += section.body.trim();
              }
              return sectionText;
            })
            .filter((text: string) => text.length > 0)
            .join('\n\n'); // Use double newlines to separate sections
        } else if (typeof parsed.mainText === 'string') {
          let formatted = parsed.mainText.trim();
          const sideTexts = Array.isArray(parsed.sideTexts) ? parsed.sideTexts : [];
          if (sideTexts.length) {
            const sideFormatted = sideTexts
              .map((s: any) => (s?.text || '').toString().trim())
              .filter((t: string) => t.length > 0)
              .join('\n\n');
            if (sideFormatted) {
              formatted += (formatted ? '\n\n' : '') + sideFormatted;
            }
          }
          cleanText = formatted;
        } else if (parsed.text) {
          cleanText = parsed.text;
        } else if (typeof parsed === 'string') {
          cleanText = parsed;
        }
      } else if (Array.isArray(parsed)) {
        cleanText = parsed.join(' ');
      } else if (typeof parsed === 'string') {
        cleanText = parsed;
      }
    } catch (e) {
      // If JSON parsing fails, clean up manually
      if (VERBOSE_DEBUG) console.log('Cleaning non-JSON text manually');
    }
  }
  
  // Remove any remaining JSON artifacts but preserve basic formatting
  cleanText = cleanText
    .replace(/^\{.*?"content":\s*"/i, '') // Remove leading JSON up to content
    .replace(/",.*\}$/i, '') // Remove trailing JSON after content
    .replace(/\\n/g, '\n') // Convert escaped newlines to actual newlines
    .replace(/\\"/g, '"') // Unescape quotes
    .replace(/[{}[\]]/g, '') // Remove any remaining brackets
    .replace(/^\s*"/, '') // Remove leading quote
    .replace(/"\s*$/, '') // Remove trailing quote
    .replace(/\n\s*\n\s*\n/g, '\n\n') // Normalize multiple newlines to double
    .replace(/[ \t]+/g, ' ') // Normalize horizontal whitespace only
    .trim();
  
  return cleanText;
}; 