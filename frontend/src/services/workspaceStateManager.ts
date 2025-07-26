/**
 * Workspace State Manager
 * 
 * Centralized state management for persisting workspace data across navigation.
 * Maintains clean separation of concerns with domain-specific state handlers.
 */

// Domain-specific state interfaces
export interface ImageProcessingState {
  sessionResults: any[];
  selectedResult: any | null;
  selectedDraft: number | 'consensus' | 'best';
  alignmentResult: any | null;
  finalDraftText: string | null;
  finalDraftMetadata: any | null;
  isHistoryVisible: boolean;
  showHeatmap: boolean;
  showAlignmentPanel: boolean;
  showAlignmentTable: boolean;
}

export interface TextToSchemaState {
  finalDraftText: string | null;
  finalDraftMetadata: any | null;
  schemaResults: any | null;
  selectedModel: string;
  isProcessing: boolean;
}

export interface WorkspaceState {
  imageProcessing: ImageProcessingState;
  textToSchema: TextToSchemaState;
  lastActiveWorkspace: 'image-processing' | 'text-to-schema' | null;
}

// Default state values
const defaultImageProcessingState: ImageProcessingState = {
  sessionResults: [],
  selectedResult: null,
  selectedDraft: 'consensus', // Changed from 0 to 'consensus'
  alignmentResult: null,
  finalDraftText: null,
  finalDraftMetadata: null,
  isHistoryVisible: true,
  showHeatmap: false,
  showAlignmentPanel: false,
  showAlignmentTable: false,
};

const defaultTextToSchemaState: TextToSchemaState = {
  finalDraftText: null,
  finalDraftMetadata: null,
  schemaResults: null,
  selectedModel: 'gpt-4o',
  isProcessing: false,
};

const defaultWorkspaceState: WorkspaceState = {
  imageProcessing: defaultImageProcessingState,
  textToSchema: defaultTextToSchemaState,
  lastActiveWorkspace: null,
};

class WorkspaceStateManager {
  private static instance: WorkspaceStateManager;
  private state: WorkspaceState;
  private listeners: Map<string, Set<() => void>> = new Map();

  private constructor() {
    this.state = this.loadState();
  }

  static getInstance(): WorkspaceStateManager {
    if (!WorkspaceStateManager.instance) {
      WorkspaceStateManager.instance = new WorkspaceStateManager();
    }
    return WorkspaceStateManager.instance;
  }

  // State persistence
  private loadState(): WorkspaceState {
    try {
      const savedState = sessionStorage.getItem('plattera_workspace_state');
      if (savedState) {
        const parsed = JSON.parse(savedState);
        // Merge with defaults to handle missing properties
        return this.mergeWithDefaults(parsed);
      }
    } catch (error) {
      console.warn('Failed to load workspace state:', error);
    }
    return defaultWorkspaceState;
  }

  private saveState(): void {
    try {
      sessionStorage.setItem('plattera_workspace_state', JSON.stringify(this.state));
    } catch (error) {
      console.warn('Failed to save workspace state:', error);
    }
  }

  private mergeWithDefaults(savedState: any): WorkspaceState {
    return {
      imageProcessing: { ...defaultImageProcessingState, ...savedState.imageProcessing },
      textToSchema: { ...defaultTextToSchemaState, ...savedState.textToSchema },
      lastActiveWorkspace: savedState.lastActiveWorkspace || null,
    };
  }

  // State getters
  getImageProcessingState(): ImageProcessingState {
    return { ...this.state.imageProcessing };
  }

  getTextToSchemaState(): TextToSchemaState {
    return { ...this.state.textToSchema };
  }

  getLastActiveWorkspace(): string | null {
    return this.state.lastActiveWorkspace;
  }

  // State setters with persistence
  setImageProcessingState(newState: Partial<ImageProcessingState>): void {
    this.state.imageProcessing = { ...this.state.imageProcessing, ...newState };
    this.saveState();
    this.notifyListeners('imageProcessing');
  }

  setTextToSchemaState(newState: Partial<TextToSchemaState>): void {
    this.state.textToSchema = { ...this.state.textToSchema, ...newState };
    this.saveState();
    this.notifyListeners('textToSchema');
  }

  setLastActiveWorkspace(workspace: 'image-processing' | 'text-to-schema' | null): void {
    this.state.lastActiveWorkspace = workspace;
    this.saveState();
    this.notifyListeners('navigation');
  }

  // Event system for state changes
  subscribe(domain: string, callback: () => void): () => void {
    if (!this.listeners.has(domain)) {
      this.listeners.set(domain, new Set());
    }
    this.listeners.get(domain)!.add(callback);

    // Return unsubscribe function
    return () => {
      this.listeners.get(domain)?.delete(callback);
    };
  }

  private notifyListeners(domain: string): void {
    this.listeners.get(domain)?.forEach(callback => callback());
  }

  // Utility methods
  clearImageProcessingState(): void {
    this.state.imageProcessing = defaultImageProcessingState;
    this.saveState();
    this.notifyListeners('imageProcessing');
  }

  clearTextToSchemaState(): void {
    this.state.textToSchema = defaultTextToSchemaState;
    this.saveState();
    this.notifyListeners('textToSchema');
  }

  clearAllState(): void {
    this.state = defaultWorkspaceState;
    this.saveState();
    this.notifyListeners('imageProcessing');
    this.notifyListeners('textToSchema');
    this.notifyListeners('navigation');
  }

  // Final draft synchronization
  syncFinalDraft(text: string, metadata: any): void {
    this.setImageProcessingState({ finalDraftText: text, finalDraftMetadata: metadata });
    this.setTextToSchemaState({ finalDraftText: text, finalDraftMetadata: metadata });
  }
}

export const workspaceStateManager = WorkspaceStateManager.getInstance(); 