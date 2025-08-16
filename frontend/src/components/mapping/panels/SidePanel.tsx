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
		<div className="control-section">
			<h4>{title}</h4>
			<div>{children}</div>
		</div>
	);
};

export const ToggleCheckbox: React.FC<{ checked: boolean; label: string; onChange: (v: boolean) => void }>
	= ({ checked, label, onChange }) => (
		<label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
			<input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
			<span>{label}</span>
		</label>
	);


