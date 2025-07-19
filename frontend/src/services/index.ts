// --- Central API Services Exports ---
// This file provides a clean single point of import for all API services

// Image Processing API
export { processFilesAPI } from './imageProcessingApi';

// Model Management API  
export { fetchModelsAPI } from './modelApi';

// Alignment Engine API
export { alignDraftsAPI } from './alignmentApi';

// Bounding Box API
export { 
  detectLinesAPI, 
  detectWordsAPI, 
  runBoundingBoxPipeline,
  getBoundingBoxStatusAPI 
} from './boundingBoxApi';

// Re-export types for convenience
export type {
  EnhancementSettings,
  ProcessingResult,
  RedundancySettings,
  AlignmentDraft,
  AlignmentResult
} from '../types/imageProcessing';

// Bounding Box types
export type {
  BoundingBoxSettings,
  BoundingBoxResult,
  BoundingBoxState
} from '../types/boundingBox'; 