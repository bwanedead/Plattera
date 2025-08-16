import React from 'react';

export interface RegionalConfig {
	mode: 'all-in-view' | 'selected-areas' | 'custom';
	maxFeatures: number;
}

export interface RegionalPanelProps {
	config: RegionalConfig;
	onChange: (cfg: RegionalConfig) => void;
}

export const RegionalPanel: React.FC<RegionalPanelProps> = ({ config, onChange }) => {
	const update = (patch: Partial<RegionalConfig>) => onChange({ ...config, ...patch });

	return (
		<div style={{ position: 'absolute', top: 280, left: 12, background: '#fff', borderRadius: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.12)', padding: 12, minWidth: 260, zIndex: 20 }}>
			<div style={{ fontSize: 12, fontWeight: 600, color: '#333', marginBottom: 8 }}>Regional overlays</div>
			<label style={{ display: 'block', marginBottom: 8 }}>
				<span style={{ fontSize: 12, color: '#555' }}>Mode</span>
				<select value={config.mode} onChange={(e) => update({ mode: e.target.value as RegionalConfig['mode'] })} style={{ width: '100%' }}>
					<option value="all-in-view">All in view</option>
					<option value="selected-areas">Selected areas</option>
					<option value="custom">Custom</option>
				</select>
			</label>
			<label style={{ display: 'block' }}>
				<span style={{ fontSize: 12, color: '#555' }}>Max features</span>
				<input type="number" value={config.maxFeatures} onChange={(e) => update({ maxFeatures: parseInt(e.target.value || '0', 10) })} style={{ width: '100%' }} />
			</label>
		</div>
	);
};



