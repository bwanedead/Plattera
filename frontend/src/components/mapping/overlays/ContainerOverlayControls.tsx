/**
 * Container Overlay Controls
 * Dedicated controls for container-based PLSS overlays
 * Clean, focused UI for parcel-relative overlay management
 */

import React from 'react';
import { ContainerOverlayState } from './ContainerOverlayManager';
import { SidePanelSection, ToggleCheckbox } from '../panels/SidePanel';

interface ContainerOverlayControlsProps {
  overlayState: ContainerOverlayState;
  onStateChange: (newState: ContainerOverlayState) => void;
}

export const ContainerOverlayControls: React.FC<ContainerOverlayControlsProps> = ({
  overlayState,
  onStateChange,
}) => {
  const handleToggle = (key: keyof ContainerOverlayState) => {
    onStateChange({
      ...overlayState,
      [key]: !overlayState[key],
    });
  };

  return (
    <SidePanelSection title="PLSS Overlays">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {/* Column Headers */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid rgba(255, 255, 255, 0.1)' }}>
          <span style={{ fontSize: '12px', fontWeight: '600', color: 'rgba(255, 255, 255, 0.7)', textTransform: 'uppercase', letterSpacing: '0.5px', width: '120px' }}>Feature</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
            <span style={{ fontSize: '12px', fontWeight: '600', color: 'rgba(255, 255, 255, 0.7)', textTransform: 'uppercase', letterSpacing: '0.5px', width: '16px', textAlign: 'center' }}>Overlay</span>
            <div style={{ width: '1px', height: '12px', backgroundColor: 'rgba(255, 255, 255, 0.2)' }}></div>
            <span style={{ fontSize: '12px', fontWeight: '600', color: 'rgba(255, 255, 255, 0.7)', textTransform: 'uppercase', letterSpacing: '0.5px', width: '16px', textAlign: 'center' }}>Labels</span>
          </div>
        </div>

        {/* Grid Control */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: '14px', fontWeight: '500', color: 'rgba(255, 255, 255, 0.9)', width: '120px' }}>Grid</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
            <ToggleCheckbox
              checked={overlayState.showGrid}
              onChange={() => handleToggle('showGrid')}
              id="grid-toggle"
              size="small"
              type="overlay"
            />
            <ToggleCheckbox
              checked={overlayState.showGridLabels}
              onChange={() => handleToggle('showGridLabels')}
              id="grid-labels-toggle"
              size="small"
              type="label"
            />
          </div>
        </div>

        {/* Township Control */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: '14px', fontWeight: '500', color: 'rgba(255, 255, 255, 0.9)', width: '120px' }}>Township</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
            <ToggleCheckbox
              checked={overlayState.showTownship}
              onChange={() => handleToggle('showTownship')}
              id="township-toggle"
              size="small"
              type="overlay"
            />
            <ToggleCheckbox
              checked={overlayState.showTownshipLabels}
              onChange={() => handleToggle('showTownshipLabels')}
              id="township-labels-toggle"
              size="small"
              type="label"
            />
          </div>
        </div>

        {/* Range Control */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: '14px', fontWeight: '500', color: 'rgba(255, 255, 255, 0.9)', width: '120px' }}>Range</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
            <ToggleCheckbox
              checked={overlayState.showRange}
              onChange={() => handleToggle('showRange')}
              id="range-toggle"
              size="small"
              type="overlay"
            />
            <ToggleCheckbox
              checked={overlayState.showRangeLabels}
              onChange={() => handleToggle('showRangeLabels')}
              id="range-labels-toggle"
              size="small"
              type="label"
            />
          </div>
        </div>

        {/* Sections Control */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: '14px', fontWeight: '500', color: 'rgba(255, 255, 255, 0.9)', width: '120px' }}>Sections</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
            <ToggleCheckbox
              checked={overlayState.showSections}
              onChange={() => handleToggle('showSections')}
              id="sections-toggle"
              size="small"
              type="overlay"
            />
            <ToggleCheckbox
              checked={overlayState.showSectionLabels}
              onChange={() => handleToggle('showSectionLabels')}
              id="section-labels-toggle"
              size="small"
              type="label"
            />
          </div>
        </div>

        {/* Quarter Sections Control */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: '14px', fontWeight: '500', color: 'rgba(255, 255, 255, 0.9)', width: '120px' }}>Quarter Sections</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
            <ToggleCheckbox
              checked={overlayState.showQuarterSections}
              onChange={() => handleToggle('showQuarterSections')}
              id="quarter-sections-toggle"
              size="small"
              type="overlay"
            />
            <ToggleCheckbox
              checked={overlayState.showQuarterSectionLabels}
              onChange={() => handleToggle('showQuarterSectionLabels')}
              id="quarter-section-labels-toggle"
              size="small"
              type="label"
            />
          </div>
        </div>

        {/* Subdivisions Control */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: '14px', fontWeight: '500', color: 'rgba(255, 255, 255, 0.9)', width: '120px' }}>Subdivisions</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
            <ToggleCheckbox
              checked={overlayState.showSubdivisions}
              onChange={() => handleToggle('showSubdivisions')}
              id="subdivisions-toggle"
              size="small"
              type="overlay"
            />
            <ToggleCheckbox
              checked={overlayState.showSubdivisionLabels}
              onChange={() => handleToggle('showSubdivisionLabels')}
              id="subdivision-labels-toggle"
              size="small"
              type="label"
            />
          </div>
        </div>
      </div>
    </SidePanelSection>
  );
};


