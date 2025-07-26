/**
 * Workspace State Hooks
 * 
 * Custom hooks for managing workspace state with automatic persistence.
 * Provides clean, reactive state management for each workspace domain.
 */

import { useState, useEffect, useCallback } from 'react';
import { workspaceStateManager, ImageProcessingState, TextToSchemaState } from '../services/workspaceStateManager';

// Hook for image processing state
export const useImageProcessingState = () => {
  const [state, setState] = useState<ImageProcessingState>(workspaceStateManager.getImageProcessingState());

  useEffect(() => {
    const unsubscribe = workspaceStateManager.subscribe('imageProcessing', () => {
      setState(workspaceStateManager.getImageProcessingState());
    });

    return unsubscribe;
  }, []);

  const updateState = useCallback((updates: Partial<ImageProcessingState>) => {
    workspaceStateManager.setImageProcessingState(updates);
  }, []);

  return { state, updateState };
};

// Hook for text-to-schema state
export const useTextToSchemaState = () => {
  const [state, setState] = useState<TextToSchemaState>(workspaceStateManager.getTextToSchemaState());

  useEffect(() => {
    const unsubscribe = workspaceStateManager.subscribe('textToSchema', () => {
      setState(workspaceStateManager.getTextToSchemaState());
    });

    return unsubscribe;
  }, []);

  const updateState = useCallback((updates: Partial<TextToSchemaState>) => {
    workspaceStateManager.setTextToSchemaState(updates);
  }, []);

  return { state, updateState };
};

// Hook for navigation state
export const useWorkspaceNavigation = () => {
  const [lastActiveWorkspace, setLastActiveWorkspace] = useState<string | null>(
    workspaceStateManager.getLastActiveWorkspace()
  );

  useEffect(() => {
    const unsubscribe = workspaceStateManager.subscribe('navigation', () => {
      setLastActiveWorkspace(workspaceStateManager.getLastActiveWorkspace());
    });

    return unsubscribe;
  }, []);

  const setActiveWorkspace = useCallback((workspace: 'image-processing' | 'text-to-schema' | null) => {
    workspaceStateManager.setLastActiveWorkspace(workspace);
  }, []);

  return { lastActiveWorkspace, setActiveWorkspace };
}; 