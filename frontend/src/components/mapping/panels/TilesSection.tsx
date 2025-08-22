import React, { useEffect, useMemo, useState } from 'react';
import { SidePanelSection } from './SidePanel';

type SourceType = 'USGS' | 'NASA GIBS';

interface TilesSectionProps {
	onChange?: (config: { source: SourceType; usgsLayerId: string; gibsLayerId: string; time?: string }) => void;
}

// Fixed USGS basemaps per spec
const USGS_BASEMAPS = [
	{ id: 'usgs_topo', name: 'USGS Topo' },
	{ id: 'usgs_imagery_only', name: 'USGS Imagery Only' },
	{ id: 'usgs_imagery_topo', name: 'USGS Imagery + Topo' },
	{ id: 'usgs_shaded_relief', name: 'USGS Shaded Relief' },
];

export const TilesSection: React.FC<TilesSectionProps> = ({ onChange }) => {
	const [source, setSource] = useState<SourceType>('USGS');
	const [usgsLayerId, setUsgsLayerId] = useState<string>('usgs_topo');
	const [gibsLayerId, setGibsLayerId] = useState<string>('VIIRS_CorrectedReflectance_TrueColor');
	const [time, setTime] = useState<string | undefined>();

	useEffect(() => {
		onChange?.({ source, usgsLayerId, gibsLayerId, time });
	}, [source, usgsLayerId, gibsLayerId, time, onChange]);

	return (
		<SidePanelSection title="Background">
			<div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
				<label>
					<span style={{ display: 'block', fontSize: 12, color: 'rgba(255, 255, 255, 0.6)', marginBottom: 4 }}>Source</span>
					<select value={source} onChange={(e) => setSource(e.target.value as SourceType)} style={{ 
						width: '100%', 
						background: 'rgba(255, 255, 255, 0.08)', 
						border: '1px solid rgba(255, 255, 255, 0.2)', 
						borderRadius: 6, 
						padding: '8px 12px', 
						color: 'rgba(255, 255, 255, 0.9)',
						fontSize: 13
					}}>
						<option>USGS</option>
						<option>NASA GIBS</option>
					</select>
				</label>

				{source === 'USGS' && (
					<label>
						<span style={{ display: 'block', fontSize: 12, color: 'rgba(255, 255, 255, 0.6)', marginBottom: 4 }}>Basemap</span>
						<select value={usgsLayerId} onChange={(e) => setUsgsLayerId(e.target.value)} style={{ 
							width: '100%', 
							background: 'rgba(255, 255, 255, 0.08)', 
							border: '1px solid rgba(255, 255, 255, 0.2)', 
							borderRadius: 6, 
							padding: '8px 12px', 
							color: 'rgba(255, 255, 255, 0.9)',
							fontSize: 13
						}}>
							{USGS_BASEMAPS.map((b) => (
								<option key={b.id} value={b.id}>{b.name}</option>
							))}
						</select>
					</label>
				)}

				{source === 'NASA GIBS' && (
					<>
						<label>
							<span style={{ display: 'block', fontSize: 12, color: '#bbb' }}>Layer</span>
							<input type="text" value={gibsLayerId} onChange={(e) => setGibsLayerId(e.target.value)} placeholder="GIBS Layer Identifier" style={{ width: '100%' }} />
						</label>
						<label>
							<span style={{ display: 'block', fontSize: 12, color: '#bbb' }}>Time (optional)</span>
							<input type="date" value={time || ''} onChange={(e) => setTime(e.target.value || undefined)} style={{ width: '100%' }} />
						</label>
					</>
				)}
			</div>
		</SidePanelSection>
	);
};


