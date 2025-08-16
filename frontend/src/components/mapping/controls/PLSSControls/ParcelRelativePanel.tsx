import React from 'react';

export interface ParcelRelativeConfig {
	showTownship: boolean;
	showRange: boolean;
	showSection: boolean;
	showQuarter: boolean;
	showGrid: boolean; // Add the new grid option
	selectedParcelId?: string;
}

export interface ParcelRelativePanelProps {
	config: ParcelRelativeConfig;
	onChange: (cfg: ParcelRelativeConfig) => void;
	parcels: { id: string; label?: string }[];
}

export const ParcelRelativePanel: React.FC<ParcelRelativePanelProps> = ({ config, onChange, parcels }) => {
	const update = (patch: Partial<ParcelRelativeConfig>) => onChange({ ...config, ...patch });

	return (
		<div style={{ position: 'absolute', top: 120, left: 12, background: '#fff', borderRadius: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.12)', padding: 12, minWidth: 260, zIndex: 20 }}>
			<div style={{ fontSize: 12, fontWeight: 600, color: '#333', marginBottom: 8 }}>Container-relative overlays</div>
			<label style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
				<input type="checkbox" checked={config.showTownship} onChange={(e) => update({ showTownship: e.target.checked })} />
				<span>Township</span>
			</label>
			<label style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
				<input type="checkbox" checked={config.showRange} onChange={(e) => update({ showRange: e.target.checked })} />
				<span>Range</span>
			</label>
			<label style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
				<input type="checkbox" checked={config.showSection} onChange={(e) => update({ showSection: e.target.checked })} />
				<span>Section</span>
			</label>
			<label style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
				<input type="checkbox" checked={config.showQuarter} onChange={(e) => update({ showQuarter: e.target.checked })} />
				<span>Quarter Section</span>
			</label>
			<label style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
				<input type="checkbox" checked={config.showGrid} onChange={(e) => update({ showGrid: e.target.checked })} />
				<span>Township + Range Grid</span>
			</label>

			{parcels.length > 1 && (
				<div style={{ marginTop: 8 }}>
					<div style={{ fontSize: 12, color: '#555', marginBottom: 4 }}>Select parcel for container reference</div>
					<select value={config.selectedParcelId || parcels[0].id} onChange={(e) => update({ selectedParcelId: e.target.value })} style={{ width: '100%' }}>
						{parcels.map((p) => (
							<option key={p.id} value={p.id}>{p.label || p.id}</option>
						))}
					</select>
				</div>
			)}
		</div>
	);
};



