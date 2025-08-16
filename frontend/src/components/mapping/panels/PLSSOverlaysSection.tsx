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
}

export const PLSSOverlaysSection: React.FC<PLSSOverlaysSectionProps> = ({ 
	parcelCfg, 
	setParcelCfg, 
	regionalCfg, 
	setRegionalCfg, 
	mode, 
	setMode,
	containerAvailable = false
}) => {
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
				<ToggleCheckbox 
					checked={parcelCfg.showTownship} 
					label="Township" 
					onChange={(v) => setParcelCfg({ ...parcelCfg, showTownship: v })} 
				/>
				<ToggleCheckbox 
					checked={parcelCfg.showRange} 
					label="Range" 
					onChange={(v) => setParcelCfg({ ...parcelCfg, showRange: v })} 
				/>
				<ToggleCheckbox 
					checked={parcelCfg.showGrid} 
					label="Township + Range Grid" 
					onChange={(v) => setParcelCfg({ ...parcelCfg, showGrid: v })} 
				/>
				<ToggleCheckbox 
					checked={parcelCfg.showSection} 
					label="Section" 
					onChange={(v) => setParcelCfg({ ...parcelCfg, showSection: v })} 
				/>
				<ToggleCheckbox 
					checked={parcelCfg.showQuarter} 
					label="Quarter" 
					onChange={(v) => setParcelCfg({ ...parcelCfg, showQuarter: v })} 
				/>
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
				</div>
			)}
		</SidePanelSection>
	);
};


