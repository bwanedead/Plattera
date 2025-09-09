// ============================================================================
// DOSSIER CONTEXT MENU COMPONENT
// ============================================================================
// Right-click context menu for dossier actions
// ============================================================================

import React from 'react';

interface DossierContextMenuProps {
  selectedItems: Set<string>;
  onAction: (action: string, data?: any) => void;
}

export const DossierContextMenu: React.FC<DossierContextMenuProps> = ({
  selectedItems,
  onAction
}) => {
  // For now, this is a placeholder that doesn't render anything
  // The context menu functionality will be implemented in the individual item components
  return null;
};
