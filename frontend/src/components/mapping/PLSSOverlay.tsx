import React, { useMemo } from 'react';

interface PLSSOverlayProps {
  overlay: {
    section?: any;
    township?: any | null;
    splits?: any[];
  } | null;
  geoToScreen: (lat: number, lon: number) => { x: number; y: number } | null;
}

function ringToScreenPath(ring: [number, number][], proj: PLSSOverlayProps['geoToScreen']): string {
  const pts = ring.map(([lon, lat]) => proj(lat, lon)).filter(Boolean) as {x:number;y:number}[];
  if (pts.length < 2) return '';
  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 1; i < pts.length; i++) d += ` L ${pts[i].x} ${pts[i].y}`;
  return d + ' Z';
}

function lineToScreenPath(lineCoords: [number, number][], proj: PLSSOverlayProps['geoToScreen']): string {
  const pts = lineCoords.map(([lon, lat]) => proj(lat, lon)).filter(Boolean) as {x:number;y:number}[];
  if (pts.length < 2) return '';
  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 1; i < pts.length; i++) d += ` L ${pts[i].x} ${pts[i].y}`;
  return d;
}

export const PLSSOverlay: React.FC<PLSSOverlayProps> = ({ overlay, geoToScreen }) => {
  if (!overlay) return null;

  const sectionPath = useMemo(() => {
    const gj = overlay.section;
    if (!gj || gj.type !== 'Polygon') return '';
    const ring = (gj.coordinates?.[0] || []) as [number, number][];
    return ringToScreenPath(ring, geoToScreen);
  }, [overlay, geoToScreen]);

  const townshipPath = useMemo(() => {
    const gj = overlay.township;
    if (!gj || gj.type !== 'Polygon') return '';
    const ring = (gj.coordinates?.[0] || []) as [number, number][];
    return ringToScreenPath(ring, geoToScreen);
  }, [overlay, geoToScreen]);

  const splitPaths = useMemo(() => {
    const lines = overlay.splits || [];
    return lines
      .map((l: any) => {
        const coords = (l.coordinates || []) as [number, number][];
        return lineToScreenPath(coords, geoToScreen);
      })
      .filter(Boolean);
  }, [overlay, geoToScreen]);

  return (
    <svg
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 9 }}
    >
      {townshipPath && (
        <path d={townshipPath} fill="none" stroke="#666" strokeDasharray="6 6" strokeWidth={1.5} />
      )}
      {sectionPath && (
        <path d={sectionPath} fill="none" stroke="#16a34a" strokeDasharray="4 4" strokeWidth={2} />
      )}
      {splitPaths.map((p, i) => (
        <path key={i} d={p} fill="none" stroke="#16a34a" strokeDasharray="2 6" strokeWidth={1} />
      ))}
    </svg>
  );
};


