import React, { useEffect } from 'react';
import { useMapContext } from '../core/MapContext';

interface OverlayManagerProps {
	children?: React.ReactNode;
}

// Placeholder for coordinating overlays; will expand in subsequent steps
export const OverlayManager: React.FC<OverlayManagerProps> = ({ children }) => {
	const { map, isLoaded } = useMapContext();

	useEffect(() => {
		if (!map || !isLoaded) return;
		// Reserved for global overlay init or ordering
	}, [map, isLoaded]);

	return <>{children}</>;
};



