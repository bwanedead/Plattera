// ============================================================================
// DOSSIER MANAGER - ELITE MODULAR ARCHITECTURE
// ============================================================================
// Core type definitions for the Dossier Management System
// Designed for maximum modularity, scalability, and future extensibility
// ============================================================================

// ============================================================================
// CORE DATA STRUCTURES
// ============================================================================

export interface DossierPath {
  dossierId?: string;
  segmentId?: string;
  runId?: string;
  draftId?: string;
}

export interface Dossier {
  id: string;
  name: string;
  description?: string;
  createdAt: Date;
  updatedAt: Date;
  segments: Segment[];
  metadata: DossierMetadata;
}

export interface Segment {
  id: string;
  name: string;
  description?: string;
  position: number;
  runs: Run[];
  metadata: SegmentMetadata;
}

export interface Run {
  id: string;
  position: number;
  transcriptionId: string;
  drafts: Draft[];
  metadata: RunMetadata;
}

export interface Draft {
  id: string;
  position: number;
  transcriptionId: string;
  isBest: boolean;
  metadata: DraftMetadata;
}

// ============================================================================
// METADATA STRUCTURES
// ============================================================================

export interface DossierMetadata {
  totalSegments: number;
  totalRuns: number;
  totalDrafts: number;
  totalSizeBytes: number;
  lastActivity: Date;
  tags?: string[];
}

export interface SegmentMetadata {
  sourceFile?: string;
  pageNumber?: number;
  section?: string;
  confidence?: number;
  wordCount?: number;
}

export interface RunMetadata {
  modelUsed: string;
  processingTimeMs: number;
  tokensUsed: number;
  createdAt: Date;
  status: 'completed' | 'processing' | 'failed';
}

export interface DraftMetadata {
  quality: 'high' | 'medium' | 'low';
  confidence: number;
  edited: boolean;
  wordCount: number;
  sizeBytes: number;
  createdAt: Date;
}

// ============================================================================
// UI STATE MANAGEMENT
// ============================================================================

export interface DossierManagerState {
  dossiers: Dossier[];
  selectedPath: DossierPath;
  expandedItems: Set<string>;
  loadingStates: LoadingStates;
  errorStates: ErrorStates;
  searchQuery: string;
  sortBy: SortOption;
  selectedItems: Set<string>;
}

export interface LoadingStates {
  dossiers: boolean;
  segments: Record<string, boolean>;
  runs: Record<string, boolean>;
  drafts: Record<string, boolean>;
}

export interface ErrorStates {
  dossiers: string | null;
  segments: Record<string, string>;
  runs: Record<string, string>;
  drafts: Record<string, string>;
}

export type SortOption = 'name' | 'date' | 'size' | 'activity';

// ============================================================================
// ACTION DEFINITIONS
// ============================================================================

export type DossierAction =
  | { type: 'SELECT_PATH'; payload: DossierPath }
  | { type: 'EXPAND_ITEM'; payload: string }
  | { type: 'COLLAPSE_ITEM'; payload: string }
  | { type: 'TOGGLE_EXPAND'; payload: string }
  | { type: 'SET_LOADING'; payload: { key: string; loading: boolean } }
  | { type: 'SET_ERROR'; payload: { key: string; error: string | null } }
  | { type: 'UPDATE_DOSSIERS'; payload: Dossier[] }
  | { type: 'ADD_DOSSIER'; payload: Dossier }
  | { type: 'UPDATE_DOSSIER'; payload: Dossier }
  | { type: 'DELETE_DOSSIER'; payload: string }
  | { type: 'SET_SEARCH'; payload: string }
  | { type: 'SET_SORT'; payload: SortOption }
  | { type: 'SELECT_ITEM'; payload: string }
  | { type: 'DESELECT_ITEM'; payload: string }
  | { type: 'CLEAR_SELECTION' };

// ============================================================================
// API INTERFACES
// ============================================================================

export interface CreateDossierData {
  title: string;
  description?: string;
}

export interface UpdateDossierData {
  title?: string;
  description?: string;
}

export interface CreateSegmentData {
  name: string;
  description?: string;
  position?: number;
}

export interface DossierApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

// ============================================================================
// COMPONENT PROP INTERFACES
// ============================================================================

export interface DossierManagerProps {
  onSelectionChange?: (path: DossierPath) => void;
  initialSelection?: DossierPath;
  onProcessingComplete?: () => void;
  className?: string;
}

export interface DossierItemProps {
  dossier: Dossier;
  isExpanded: boolean;
  isSelected: boolean;
  selectedPath: DossierPath;
  onToggle: (dossierId: string) => void;
  onSelect: (path: DossierPath) => void;
  onAction: (action: string, data?: any) => void;
}

export interface SegmentItemProps {
  segment: Segment;
  dossierId: string;
  isExpanded: boolean;
  isSelected: boolean;
  selectedPath: DossierPath;
  onToggle: (segmentId: string) => void;
  onSelect: (path: DossierPath) => void;
  onAction: (action: string, data?: any) => void;
}

export interface RunItemProps {
  run: Run;
  segmentId: string;
  dossierId: string;
  isExpanded: boolean;
  isSelected: boolean;
  selectedPath: DossierPath;
  onToggle: (runId: string) => void;
  onSelect: (path: DossierPath) => void;
  onAction: (action: string, data?: any) => void;
}

export interface DraftItemProps {
  draft: Draft;
  runId: string;
  segmentId: string;
  dossierId: string;
  isSelected: boolean;
  selectedPath: DossierPath;
  onSelect: (path: DossierPath) => void;
  onAction: (action: string, data?: any) => void;
}

// ============================================================================
// UTILITY TYPES
// ============================================================================

export type ItemType = 'dossier' | 'segment' | 'run' | 'draft';

export interface TreeNode {
  id: string;
  type: ItemType;
  name: string;
  children?: TreeNode[];
  metadata?: any;
}

export interface BulkAction {
  type: 'delete' | 'move' | 'tag' | 'export';
  targetIds: string[];
  data?: any;
}

export interface ContextMenuItem {
  id: string;
  label: string;
  icon?: string;
  action: () => void;
  disabled?: boolean;
  danger?: boolean;
  separator?: boolean;
}

// ============================================================================
// FUTURE EXTENSIBILITY HOOKS
// ============================================================================

// These interfaces ensure future AI consensus features can be easily integrated
export interface ConsensusMetadata {
  generatedBy: 'ai' | 'manual' | 'hybrid';
  confidence: number;
  alternatives?: string[];
  reasoning?: string;
}

export interface AutoNamingSuggestion {
  suggestedName: string;
  confidence: number;
  reasoning: string;
  source: 'ai' | 'pattern' | 'manual';
}

// ============================================================================
// PERFORMANCE & CACHING
// ============================================================================

export interface CacheEntry<T> {
  data: T;
  timestamp: number;
  ttl: number;
}

export interface VirtualScrollState {
  visibleStart: number;
  visibleEnd: number;
  itemHeight: number;
  containerHeight: number;
  scrollTop: number;
}

// ============================================================================
// ANALYTICS & MONITORING
// ============================================================================

export interface DossierMetrics {
  totalDossiers: number;
  totalSegments: number;
  totalRuns: number;
  totalDrafts: number;
  averageProcessingTime: number;
  storageUsed: number;
  lastActivity: Date;
}

export interface UserInteractionEvent {
  type: 'select' | 'expand' | 'action' | 'search';
  targetId: string;
  targetType: ItemType;
  timestamp: Date;
  metadata?: any;
}
