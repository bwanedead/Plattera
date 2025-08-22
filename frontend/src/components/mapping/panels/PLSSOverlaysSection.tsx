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
			fontSize: 12,
			background: 'rgba(255, 255, 255, 0.08)',
			border: '1px solid rgba(255, 255, 255, 0.12)',
			borderRadius: '8px',
			padding: '12px',
			marginBottom: '16px',
			backdropFilter: 'blur(10px)',
			boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)'
		}}>
			<div style={{ 
				fontWeight: '600', 
				marginBottom: '8px', 
				color: 'rgba(255, 255, 255, 0.95)',
				fontSize: '13px',
				letterSpacing: '0.3px'
			}}>
				Parcel Location
			</div>
			<div style={{ color: 'rgba(255, 255, 255, 0.7)', lineHeight: '1.4', fontSize: '11px' }}>
				<div style={{ marginBottom: '4px' }}>
					Township: {trs.t || '?'}{trs.td || '?'} | Range: {trs.r || '?'}{trs.rd || '?'}
				</div>
				{trs.s && <div style={{ marginBottom: '4px' }}>Section: {trs.s}</div>}
				{containerBounds && (
					<div style={{ 
						fontSize: '10px', 
						color: 'rgba(255, 255, 255, 0.5)', 
						marginTop: '6px',
						fontFamily: 'SF Mono, Monaco, Consolas, monospace'
					}}>
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
		{ id: 'showTownship', label: 'Township Lines', description: 'Horizontal lines spanning the township containing this parcel' },
		{ id: 'showRange', label: 'Range Lines', description: 'Vertical lines spanning the range containing this parcel' },
		{ id: 'showGrid', label: 'Township + Range Cell', description: 'Grid cell (box) where township and range lines intersect' },
		{ id: 'showSection', label: 'Sections', description: 'Sections within the township-range cell' },
		{ id: 'showQuarter', label: 'Quarter Sections', description: 'Quarter sections within the township-range cell' },
		{ id: 'showSubdivisions', label: 'Subdivisions', description: 'All subdivision features within the township-range cell' }
	] : [
		{ id: 'showTownship', label: 'Townships', description: 'Township boundaries (E-W lines)' },
		{ id: 'showRange', label: 'Ranges', description: 'Range boundaries (N-S lines)' },
		{ id: 'showGrid', label: 'Township + Range Grid', description: 'Complete PLSS grid system' },
		{ id: 'showSection', label: 'Sections', description: 'Section boundaries' },
		{ id: 'showQuarter', label: 'Quarter Sections', description: 'Quarter section boundaries' },
		{ id: 'showSubdivisions', label: 'Subdivisions', description: 'All subdivision features' }
	];

	return (
		<SidePanelSection title="PLSS Overlays">
			{/* Mode Selection */}
			<div style={{ 
				display: 'flex', 
				gap: 2, 
				marginBottom: 16, 
				fontSize: 12,
				background: 'rgba(255, 255, 255, 0.06)',
				borderRadius: '6px',
				padding: '2px'
			}}>
				<label style={{ 
					display: 'flex', 
					alignItems: 'center', 
					gap: 6,
					opacity: containerAvailable ? 1 : 0.4,
					cursor: containerAvailable ? 'pointer' : 'not-allowed',
					padding: '6px 12px',
					borderRadius: '4px',
					background: mode === 'container' ? 'rgba(255, 255, 255, 0.15)' : 'transparent',
					color: 'rgba(255, 255, 255, 0.9)',
					fontWeight: mode === 'container' ? '500' : '400',
					transition: 'all 0.2s ease',
					fontSize: '11px',
					letterSpacing: '0.2px'
				}}>
					<input 
						type="radio" 
						name="plss-mode" 
						checked={mode === 'container'} 
						onChange={() => containerAvailable && setMode('container')}
						disabled={!containerAvailable}
						style={{ display: 'none' }}
					/> 
					Container
				</label>
				<label style={{ 
					display: 'flex', 
					alignItems: 'center', 
					gap: 6, 
					cursor: 'pointer',
					padding: '6px 12px',
					borderRadius: '4px',
					background: mode === 'regional' ? 'rgba(255, 255, 255, 0.15)' : 'transparent',
					color: 'rgba(255, 255, 255, 0.9)',
					fontWeight: mode === 'regional' ? '500' : '400',
					transition: 'all 0.2s ease',
					fontSize: '11px',
					letterSpacing: '0.2px'
				}}>
					<input 
						type="radio" 
						name="plss-mode" 
						checked={mode === 'regional'} 
						onChange={() => setMode('regional')} 
						style={{ display: 'none' }}
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
					color: 'rgba(255, 193, 7, 0.9)', 
					marginBottom: 12,
					padding: '10px 12px',
					background: 'rgba(255, 193, 7, 0.08)',
					borderRadius: '6px',
					border: '1px solid rgba(255, 193, 7, 0.2)',
					backdropFilter: 'blur(10px)'
				}}>
					Container mode requires schema data with parcel location
				</div>
			)}

			{/* PLSS Layer Toggles */}
			<div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
				{overlayOptions.map(option => (
					<div key={option.id} style={{ 
						display: 'flex', 
						flexDirection: 'column',
						padding: '8px 0',
						borderBottom: '1px solid rgba(255, 255, 255, 0.06)'
					}}>
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
							color: 'rgba(255, 255, 255, 0.5)', 
							marginLeft: '24px', 
							marginTop: '4px',
							lineHeight: '1.3',
							fontWeight: '400'
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
					color: 'rgba(255, 255, 255, 0.4)', 
					marginTop: 12,
					padding: '8px 10px',
					background: 'rgba(255, 255, 255, 0.03)',
					borderRadius: '6px',
					border: '1px solid rgba(255, 255, 255, 0.08)',
					fontFamily: 'SF Mono, Monaco, Consolas, monospace'
				}}>
					Showing PLSS features within parcel bounds
					{trsData && (
						<div style={{ marginTop: '6px', fontSize: '9px' }}>
							TRS Query: T{trsData.t || '?'}{trsData.td || '?'} R{trsData.r || '?'}{trsData.rd || '?'} S{trsData.s || 'all'}
						</div>
					)}
				</div>
			)}
		</SidePanelSection>
	);
};


