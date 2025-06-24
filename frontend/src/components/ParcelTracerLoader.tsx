import React, { useState, useEffect } from 'react';

const VIEWBOX_SIZE = 120;

interface Point { x: number; y: number; }
interface Segment { 
  id: string; 
  // For the <g> transform
  tx: number; 
  ty: number;
  // For the <line> element
  x2: number; 
  y2: number; 
  length: number;
}

const generatePolygonSegments = (numVertices: number): Segment[] => {
  const points: Point[] = [];
  const angleStep = (Math.PI * 2) / numVertices;

  for (let i = 0; i < numVertices; i++) {
    const angle = i * angleStep;
    const radius = VIEWBOX_SIZE / 2.8 + (Math.random() - 0.5) * 25; 
    
    points.push({
      x: VIEWBOX_SIZE / 2 + Math.cos(angle) * radius,
      y: VIEWBOX_SIZE / 2 + Math.sin(angle) * radius
    });
  }

  const segments: Segment[] = [];
  for (let i = 0; i < points.length; i++) {
    const p1 = points[i];
    const p2 = points[(i + 1) % points.length];
    
    const length = Math.sqrt(Math.pow(p2.x - p1.x, 2) + Math.pow(p2.y - p1.y, 2));
    
    segments.push({ 
      id: `seg-${i}`,
      tx: p1.x,
      ty: p1.y,
      x2: p2.x - p1.x,
      y2: p2.y - p1.y,
      length: length,
    });
  }
  
  return segments;
};

const PolygonAnimation: React.FC<{ segments: Segment[]; onComplete: () => void }> = ({ segments, onComplete }) => {
  const [currentSegmentIndex, setCurrentSegmentIndex] = useState(-1);
  const [isComplete, setIsComplete] = useState(false);
  const [randomHue] = useState(() => Math.random() * 360);

  useEffect(() => {
    let index = 0;
    const interval = setInterval(() => {
      if (index < segments.length) {
        setCurrentSegmentIndex(index);
        index++;
      } else {
        clearInterval(interval);
        setIsComplete(true);
        
        // After completion, wait for the color-shifting effect to play out
        setTimeout(() => {
          onComplete();
        }, 2500); // Give it 2.5 seconds to show the color shifting
      }
    }, 600);

    return () => clearInterval(interval);
  }, [segments, onComplete]);

  return (
    <g 
      className={`tracer-group ${isComplete ? 'completed' : ''}`}
      style={{ '--random-hue': randomHue } as React.CSSProperties}
    >
      {segments.map((seg, index) => {
        const isVisible = index <= currentSegmentIndex;
        const isAnimating = index === currentSegmentIndex;
        
        return (
          <g
            key={seg.id}
            className={`tracer-edge-group ${isVisible ? 'visible' : ''} ${isAnimating ? 'animating' : ''}`}
            transform={`translate(${seg.tx}, ${seg.ty})`}
          >
            <line
              className="tracer-edge"
              x1={0}
              y1={0}
              x2={seg.x2}
              y2={seg.y2}
              strokeDasharray={seg.length}
              style={{ '--segment-length': seg.length } as React.CSSProperties}
            />
          </g>
        );
      })}
    </g>
  );
};

export const ParcelTracerLoader: React.FC = () => {
  const [polygonKey, setPolygonKey] = useState(0);
  const [segments, setSegments] = useState<Segment[]>([]);

  const generateNewPolygon = () => {
    const newVertexCount = Math.floor(Math.random() * 4) + 4;
    setSegments(generatePolygonSegments(newVertexCount));
    setPolygonKey(prev => prev + 1);
  };

  const handlePolygonComplete = () => {
    generateNewPolygon();
  };

  useEffect(() => {
    generateNewPolygon();
  }, []);

  return (
    <div className="parcel-tracer-loader">
      <svg viewBox={`0 0 ${VIEWBOX_SIZE} ${VIEWBOX_SIZE}`} preserveAspectRatio="xMidYMid meet">
        <PolygonAnimation 
          key={polygonKey} 
          segments={segments} 
          onComplete={handlePolygonComplete}
        />
      </svg>
    </div>
  );
}; 