/**
 * PLSS Services Index
 * Central export for all PLSS-related services
 */

export { ContainerApi } from './containerApi';
export type { ContainerLayer, ContainerRequest, ContainerResponse } from './containerApi';

// PLSS Data Service
export { plssDataService, PLSSDataService } from './dataService';
export type { 
  PLSSDataStatus, 
  PLSSDataState, 
  PLSSDataCheckResult, 
  PLSSDataDownloadResult 
} from './dataService';

// Legacy exports for backward compatibility (will be removed)
export { default as plssOverlayApi } from '../plssOverlayApi';