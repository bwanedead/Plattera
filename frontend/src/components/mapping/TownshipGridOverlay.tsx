import React, { useMemo } from 'react';

interface TownshipGridOverlayProps {
  features: Array<{ geometry: any; label: { lat: number; lon: number }; attrs: any }>;
  geoToScreen: (lat: number, lon: number) => { x: number; y: number } | null;
}

function ringToPath(ring: [number, number][], proj: TownshipGridOverlayProps['geoToScreen']): string {
  const pts = ring.map(([lon, lat]) => proj(lat, lon)).filter(Boolean) as { x: number; y: number }[];
  if (pts.length < 2) return '';
  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 1; i < pts.length; i++) d += ` L ${pts[i].x} ${pts[i].y}`;
  return d + ' Z';
}

export const TownshipGridOverlay: React.FC<TownshipGridOverlayProps> = ({ features, geoToScreen }) => {
  const items = useMemo(() => {
    return features.map((f, idx) => {
      const g = f.geometry;
      const paths: string[] = [];
      if (!g) return { id: idx, paths, labelPx: null as any, label: '' };
      if (g.type === 'Polygon') {
        const ring = (g.coordinates?.[0] || []) as [number, number][];
        paths.push(ringToPath(ring, geoToScreen));
      } else if (g.type === 'MultiPolygon') {
        for (const poly of g.coordinates || []) {
          const ring = (poly?.[0] || []) as [number, number][];
          paths.push(ringToPath(ring, geoToScreen));
        }
      }
      const labelPx = geoToScreen(f.label.lat, f.label.lon);
      const t = f.attrs?.township ?? '';
      const td = (f.attrs?.t_dir || '').toUpperCase();
      const r = f.attrs?.range ?? '';
      const rd = (f.attrs?.r_dir || '').toUpperCase();
      const label = `T${t}${td} R${r}${rd}`;
      return { id: idx, paths, labelPx, label };
    });
  }, [features, geoToScreen]);

  return (
    <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 8 }}>
      {items.flatMap((it) =>
        it.paths.map((p, i) => (
          <path key={`${it.id}-${i}`} d={p} fill="none" stroke="#999" strokeDasharray="8 8" strokeWidth={1} />
        ))
      )}
      {items.map(
        (it) =>
          it.labelPx && (
            <text
              key={`lbl-${it.id}`}
              x={it.labelPx.x}
              y={it.labelPx.y}
              fontSize={12}
              fill="#333"
              stroke="#fff"
              strokeWidth={3}
              paintOrder="stroke"
              textAnchor="middle"
            >
              {it.label}
            </text>
          )
      )}
    </svg>
  );
};





