import React from 'react';

interface SidePanelProps {
	children: React.ReactNode;
}

export const SidePanel: React.FC<SidePanelProps> = ({ children }) => {
	return (
		<div className="map-side-panel" style={{ display: 'flex', flexDirection: 'column', gap: 12, background: 'rgba(20,20,25,0.92)', padding: 12, borderRadius: 8, height: '100%', overflowY: 'auto', width: '100%' }}>
			{children}
		</div>
	);
};

interface SectionProps {
	title: string;
	children: React.ReactNode;
}

export const SidePanelSection: React.FC<SectionProps> = ({ title, children }) => {
	return (
		<div className="control-section" style={{ 
			background: 'rgba(255, 255, 255, 0.02)', 
			borderRadius: 8, 
			padding: 16, 
			border: '1px solid rgba(255, 255, 255, 0.06)',
			marginBottom: 8
		}}>
			<h4 style={{ 
				fontSize: 14, 
				fontWeight: 600, 
				color: 'rgba(255, 255, 255, 0.9)', 
				marginBottom: 12,
				letterSpacing: '0.5px'
			}}>{title}</h4>
			<div>{children}</div>
		</div>
	);
};

interface ToggleCheckboxProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  id: string;
  size?: 'normal' | 'small';
  type?: 'overlay' | 'label';
}

export const ToggleCheckbox: React.FC<ToggleCheckboxProps> = ({ 
  checked, 
  onChange, 
  id,
  size = 'normal',
  type = 'overlay'
}) => {
  const bubbleSize = size === 'small' ? 12 : 16;
  
  // Different colors for overlay vs label toggles
  const getColors = () => {
    if (type === 'label') {
      return {
        checked: { border: '#F59E0B', background: '#F59E0B' }, // Yellow for labels
        unchecked: { border: '#6B7280', background: '#374151' }
      };
    } else {
      return {
        checked: { border: '#3B82F6', background: '#3B82F6' }, // Blue for overlays
        unchecked: { border: '#6B7280', background: '#374151' }
      };
    }
  };
  
  const colors = getColors();
    
  return (
    <div 
      style={{
        width: bubbleSize,
        height: bubbleSize,
        borderRadius: '50%',
        border: '1px solid',
        borderColor: checked ? colors.checked.border : colors.unchecked.border,
        backgroundColor: checked ? colors.checked.background : colors.unchecked.background,
        cursor: 'pointer',
        transition: 'all 0.2s ease'
      }}
      onClick={() => onChange(!checked)}
    >
      <input
        type="checkbox"
        id={id}
        checked={checked}
        onChange={() => {}} // Handled by onClick above
        style={{ display: 'none' }}
      />
    </div>
  );
};


