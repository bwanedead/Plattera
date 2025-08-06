/**
 * PLSS Services Domain
 * 
 * Centralized exports for all PLSS-related services and types.
 * Provides clean domain boundaries and easy imports.
 */

// Core data service
export { PLSSDataService, plssDataService } from './dataService';

// Types
export type { 
  PLSSDataStatus, 
  PLSSDataState, 
  PLSSDataCheckResult, 
  PLSSDataDownloadResult 
} from './dataService';

// Future PLSS services can be added here:
// export { PLSSCacheService } from './cacheService';
// export { PLSSValidationService } from './validationService';
// export { PLSSCoordinateService } from './coordinateService';