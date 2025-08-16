import React from 'react';
import { SidePanelSection } from './SidePanel';

interface PropertiesSectionProps {
	polygon?: any;
}

export const PropertiesSection: React.FC<PropertiesSectionProps> = ({ polygon }) => {
	if (!polygon || !polygon.properties) return null;

	const props = polygon.properties || {};
	const area = typeof props.area_calculated === 'number' ? props.area_calculated : undefined;
	const perim = typeof props.perimeter === 'number' ? props.perimeter : undefined;
	const closure = typeof props.closure_error === 'number' ? props.closure_error : undefined;
	const courses = props.courses_count != null ? props.courses_count : undefined;

	return (
		<SidePanelSection title="Properties">
			<div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 13 }}>
				{area !== undefined && (
					<div style={{ display: 'flex', justifyContent: 'space-between' }}>
						<span>Area (Calculated):</span>
						<span>
							{area.toLocaleString()} sq ft
							<div style={{ fontSize: 11, color: '#bbb' }}>
								({(area / 43560).toFixed(3)} acres)
							</div>
						</span>
					</div>
				)}
				
				{perim !== undefined && (
					<div style={{ display: 'flex', justifyContent: 'space-between' }}>
						<span>Perimeter:</span>
						<span>{perim.toLocaleString()} ft</span>
					</div>
				)}
				
				{closure !== undefined && (
					<div style={{ display: 'flex', justifyContent: 'space-between' }}>
						<span>Closure Error:</span>
						<span style={{ color: closure > 1 ? '#ff6b6b' : '#51cf66' }}>
							{closure.toFixed(2)} ft
						</span>
					</div>
				)}
				
				{courses !== undefined && (
					<div style={{ display: 'flex', justifyContent: 'space-between' }}>
						<span>Boundary Courses:</span>
						<span>{courses}</span>
					</div>
				)}

				{polygon.coordinate_system && (
					<div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid #444' }}>
						<div style={{ fontSize: 12, color: '#bbb', marginBottom: 4 }}>Coordinate System</div>
						<div style={{ fontSize: 11 }}>{polygon.coordinate_system}</div>
						{polygon.origin && (
							<div style={{ fontSize: 11, color: '#bbb' }}>
								Origin: {polygon.origin.type}
							</div>
						)}
					</div>
				)}
			</div>
		</SidePanelSection>
	);
};
