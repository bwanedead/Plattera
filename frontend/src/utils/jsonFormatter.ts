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

/**
 * Check if the extracted text is JSON format
 */
export function isJsonResult(extractedText: string): boolean {
  if (!extractedText) return false
  
  try {
    const parsed = JSON.parse(extractedText)
    return parsed && typeof parsed === 'object' && 
           parsed.documentId && Array.isArray(parsed.sections)
  } catch {
    return false
  }
}

/**
 * Parse JSON result into structured format
 */
export function parseJsonResult(extractedText: string): DocumentTranscription | null {
  try {
    const parsed = JSON.parse(extractedText)
    if (parsed && parsed.documentId && Array.isArray(parsed.sections)) {
      return parsed as DocumentTranscription
    }
    return null
  } catch {
    return null
  }
}

/**
 * Format JSON result as readable text with proper section formatting
 */
export function formatJsonAsText(extractedText: string): string {
  const parsed = parseJsonResult(extractedText)
  if (!parsed) return extractedText

  let formattedText = ''
  
  parsed.sections.forEach((section, index) => {
    // Add section header if it exists
    if (section.header && section.header.trim()) {
      formattedText += `${section.header.trim()}\n`
      formattedText += '─'.repeat(Math.min(section.header.trim().length, 50)) + '\n'
    }
    
    // Add section body
    if (section.body && section.body.trim()) {
      formattedText += `${section.body.trim()}\n`
    }
    
    // Add spacing between sections (except for the last one)
    if (index < parsed.sections.length - 1) {
      formattedText += '\n\n'
    }
  })
  
  return formattedText
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