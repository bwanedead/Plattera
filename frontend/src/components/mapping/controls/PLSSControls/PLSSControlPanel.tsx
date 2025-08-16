import React from 'react';

export interface PLSSControlPanelProps {
	onToggleCategory1: () => void; // Parcel-relative (container) panel
	onToggleCategory2: () => void; // Regional panel
}

export const PLSSControlPanel: React.FC<PLSSControlPanelProps> = ({ onToggleCategory1, onToggleCategory2 }) => {
	return (
		<div style={{ position: 'absolute', top: 12, left: 12, background: '#fff', borderRadius: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.12)', padding: 12, minWidth: 220, zIndex: 20 }}>
			<div style={{ fontSize: 12, fontWeight: 600, color: '#333', marginBottom: 8 }}>PLSS Overlays</div>
			<button onClick={onToggleCategory1} style={{ display: 'block', width: '100%', marginBottom: 8 }}>Parcel-relative</button>
			<button onClick={onToggleCategory2} style={{ display: 'block', width: '100%' }}>Regional</button>
		</div>
	);
};



