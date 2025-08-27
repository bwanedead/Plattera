import React, { useEffect, useState } from 'react';
import { georeferenceApi, GeoreferenceProjectRequest, GeoreferenceProjectResponse } from '../../services/georeferenceApi';
import { MapViewer } from './MapViewer';

interface GeoreferenceControllerProps {
  request: GeoreferenceProjectRequest;
  className?: string;
}

/**
 * GeoreferenceController
 * - Calls dedicated georeference API
 * - Passes resulting polygon to MapViewer for display
 * - Handles loading/error state simply (no UI polish per instruction)
 */
export const GeoreferenceController: React.FC<GeoreferenceControllerProps> = ({ request, className = '' }) => {
  const [polygonData, setPolygonData] = useState<GeoreferenceProjectResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const res = await georeferenceApi.project(request);
        if (cancelled) return;
        if (!res.success) {
          setError(res.error || 'Georeference failed');
        } else {
          setPolygonData(res);
        }
      } catch (e: any) {
        if (!cancelled) setError(e?.message || 'Unknown error');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [request]);

  return (
    <div className={`georeference-controller ${className}`} style={{ width: '100%', height: '100%' }}>
      {/* Minimal display logic; MapViewer will handle centering/fit when polygonData provided */}
      <MapViewer polygonData={polygonData || undefined} className="w-full h-full" />
    </div>
  );
};

export default GeoreferenceController;


