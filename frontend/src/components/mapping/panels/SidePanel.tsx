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
		<label style={{ 
			display: 'flex', 
			alignItems: 'center', 
			gap: 10, 
			fontSize: 12,
			cursor: 'pointer',
			color: 'rgba(255, 255, 255, 0.9)',
			fontWeight: '500',
			letterSpacing: '0.2px',
			transition: 'all 0.2s ease'
		}}>
			<div style={{
				width: 16,
				height: 16,
				borderRadius: 3,
				border: '1px solid rgba(255, 255, 255, 0.3)',
				background: checked ? 'rgba(0, 122, 255, 0.9)' : 'rgba(255, 255, 255, 0.08)',
				display: 'flex',
				alignItems: 'center',
				justifyContent: 'center',
				transition: 'all 0.2s ease',
				position: 'relative'
			}}>
				{checked && (
					<div style={{
						width: 8,
						height: 8,
						background: 'white',
						borderRadius: 1,
						transform: 'scale(1)',
						transition: 'transform 0.2s ease'
					}} />
				)}
			</div>
			<input 
				type="checkbox" 
				checked={checked} 
				onChange={(e) => onChange(e.target.checked)}
				style={{ display: 'none' }}
			/>
			<span>{label}</span>
		</label>
	);


