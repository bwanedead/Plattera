import React from 'react';
import { SidePanelSection, ToggleCheckbox } from './SidePanel';
import { type ParcelRelativeConfig } from '../controls/PLSSControls/ParcelRelativePanel';
import { type RegionalConfig } from '../controls/PLSSControls/RegionalPanel';

interface PLSSOverlaysSectionProps {
	parcelCfg: ParcelRelativeConfig;
	setParcelCfg: (cfg: ParcelRelativeConfig) => void;
	regionalCfg: RegionalConfig;
	setRegionalCfg: (cfg: RegionalConfig) => void;
	mode: 'container' | 'regional';
	setMode: (m: 'container' | 'regional') => void;
	containerAvailable?: boolean;
	// Add TRS and container bounds for debugging
	trsData?: { t?: number; td?: string; r?: number; rd?: string; s?: number };
	containerBounds?: { west: number; south: number; east: number; north: number };
}

const ParcelInfoComponent: React.FC<{ 
	trs?: { t?: number; td?: string; r?: number; rd?: string; s?: number };
	containerBounds?: { west: number; south: number; east: number; north: number };
}> = ({ trs, containerBounds }) => {
	if (!trs) return null;

	return (
		<div style={{
			fontSize: 11,
			background: 'rgba(0, 100, 200, 0.1)',
			border: '1px solid rgba(0, 100, 200, 0.2)',
			borderRadius: '4px',
			padding: '8px',
			marginBottom: '12px'
		}}>
			<div style={{ fontWeight: 'bold', marginBottom: '4px', color: '#4a90e2' }}>
				📍 Parcel Location
			</div>
			<div style={{ color: '#ccc', lineHeight: '1.3' }}>
				<div>
					Township: {trs.t || '?'}{trs.td || '?'} | Range: {trs.r || '?'}{trs.rd || '?'}
				</div>
				{trs.s && <div>Section: {trs.s}</div>}
				{containerBounds && (
					<div style={{ fontSize: 10, color: '#888', marginTop: '4px' }}>
						Bounds: {containerBounds.west.toFixed(3)}, {containerBounds.south.toFixed(3)} → {containerBounds.east.toFixed(3)}, {containerBounds.north.toFixed(3)}
					</div>
				)}
			</div>
		</div>
	);
};

export const PLSSOverlaysSection: React.FC<PLSSOverlaysSectionProps> = ({ 
	parcelCfg, 
	setParcelCfg, 
	regionalCfg, 
	setRegionalCfg, 
	mode, 
	setMode,
	containerAvailable = false,
	trsData,
	containerBounds
}) => {

	// Container mode filtering strategy
	const overlayOptions = mode === 'container' ? [
		{ id: 'showTownship', label: 'Township Box', description: 'Show township containing this parcel' },
		{ id: 'showRange', label: 'Range Box', description: 'Show range containing this parcel' },
		{ id: 'showGrid', label: 'Township + Range Grid', description: 'Show full grid containing this parcel' },
		{ id: 'showSection', label: 'Section Box', description: 'Show section containing this parcel' },
		{ id: 'showQuarter', label: 'Quarter Section', description: 'Show quarter section containing this parcel' }
	] : [
		{ id: 'showTownship', label: 'Townships', description: 'Township boundaries (E-W lines)' },
		{ id: 'showRange', label: 'Ranges', description: 'Range boundaries (N-S lines)' },
		{ id: 'showGrid', label: 'Township + Range Grid', description: 'Complete PLSS grid system' },
		{ id: 'showSection', label: 'Sections', description: 'Section boundaries' },
		{ id: 'showQuarter', label: 'Quarter Sections', description: 'Quarter section boundaries' }
	];

	return (
		<SidePanelSection title="PLSS Overlays">
			{/* Mode Selection */}
			<div style={{ display: 'flex', gap: 8, marginBottom: 12, fontSize: 12 }}>
				<label style={{ 
					display: 'flex', 
					alignItems: 'center', 
					gap: 4,
					opacity: containerAvailable ? 1 : 0.5,
					cursor: containerAvailable ? 'pointer' : 'not-allowed'
				}}>
					<input 
						type="radio" 
						name="plss-mode" 
						checked={mode === 'container'} 
						onChange={() => containerAvailable && setMode('container')}
						disabled={!containerAvailable}
					/> 
					Container
				</label>
				<label style={{ display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
					<input 
						type="radio" 
						name="plss-mode" 
						checked={mode === 'regional'} 
						onChange={() => setMode('regional')} 
					/> 
					All in View
				</label>
			</div>

			{/* Parcel Info Component - only show in container mode */}
			{mode === 'container' && containerAvailable && (
				<ParcelInfoComponent trs={trsData} containerBounds={containerBounds} />
			)}

			{/* Container mode helper text */}
			{mode === 'container' && !containerAvailable && (
				<div style={{ 
					fontSize: 11, 
					color: '#ffa500', 
					marginBottom: 8,
					padding: '6px 8px',
					background: 'rgba(255, 165, 0, 0.1)',
					borderRadius: '4px'
				}}>
					⚠️ Container mode requires schema data with parcel location
				</div>
			)}

			{/* PLSS Layer Toggles */}
			<div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
				{overlayOptions.map(option => (
					<div key={option.id} style={{ display: 'flex', flexDirection: 'column' }}>
						<ToggleCheckbox 
							checked={parcelCfg[option.id as keyof ParcelRelativeConfig] as boolean} 
							label={option.label}
							onChange={(newValue) => {
								// Special handling for grid option - make mutually exclusive
								if (option.id === 'showGrid' && newValue) {
									setParcelCfg({ 
										...parcelCfg, 
										showGrid: true,
										showTownship: false,
										showRange: false
									});
								} else if (option.id === 'showTownship' || option.id === 'showRange') {
									setParcelCfg({ 
										...parcelCfg, 
										[option.id]: newValue,
										showGrid: false
									});
								} else {
									setParcelCfg({ ...parcelCfg, [option.id]: newValue });
								}
							}} 
						/>
						<div style={{ 
							fontSize: 10, 
							color: '#666', 
							marginLeft: '20px', 
							marginTop: '2px' 
						}}>
							{option.description}
						</div>
					</div>
				))}
			</div>

			{/* Debug Info */}
			{mode === 'container' && containerAvailable && (
				<div style={{ 
					fontSize: 10, 
					color: '#888', 
					marginTop: 8,
					padding: '4px 6px',
					background: 'rgba(255,255,255,0.05)',
					borderRadius: '3px'
				}}>
					🎯 Showing PLSS features within parcel bounds
					{trsData && (
						<div style={{ marginTop: '4px' }}>
							TRS Query: T{trsData.t || '?'}{trsData.td || '?'} R{trsData.r || '?'}{trsData.rd || '?'} S{trsData.s || 'all'}
						</div>
					)}
				</div>
			)}
		</SidePanelSection>
	);
};


