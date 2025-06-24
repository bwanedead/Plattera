import React, { useState, useEffect } from 'react';

const VIEWBOX_SIZE = 120; // Made the viewbox larger

interface Point { x: number; y: number; }
interface Segment { id: string; x1: number; y1: number; x2: number; y2: number; }

// Enhanced generation for more variety
const generatePolygonSegments = (numVertices: number): Segment[] => {
  const points: Point[] = [];
  const angleStep = (Math.PI * 2) / numVertices;

  for (let i = 0; i < numVertices; i++) {
    const angle = i * angleStep;
    // Increased radius and variability for bigger, more interesting shapes
    const radius = VIEWBOX_SIZE / 2.8 + (Math.random() - 0.5) * 25; 
    
    points.push({
      x: VIEWBOX_SIZE / 2 + Math.cos(angle) * radius,
      y: VIEWBOX_SIZE / 2 + Math.sin(angle) * radius
    });
  }

  // Create segments from points
  const segments: Segment[] = [];
  for (let i = 0; i < points.length; i++) {
    const p1 = points[i];
    const p2 = points[(i + 1) % points.length]; // Loop back to the start
    segments.push({ id: `seg-${i}`, x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y });
  }
  return segments;
};

export const ParcelTracerLoader: React.FC = () => {
  const [allSegments, setAllSegments] = useState<Segment[]>([]);
  const [drawnSegments, setDrawnSegments] = useState<Segment[]>([]);
  const [isComplete, setIsComplete] = useState(false);

  // Initialize segments on mount
  useEffect(() => {
    setAllSegments(generatePolygonSegments(5));
  }, []);

  useEffect(() => {
    // Only start animation if we have segments
    if (allSegments.length === 0) return;

    // Reset and start a new polygon animation
    const animatePolygon = () => {
      setIsComplete(false);
      setDrawnSegments([]);
      
      const segmentsToDraw = allSegments;
      let currentIndex = 0;
      
      const interval = setInterval(() => {
        if (currentIndex < segmentsToDraw.length) {
          // Add one segment at a time to trigger the animation
          setDrawnSegments(prev => [...prev, segmentsToDraw[currentIndex]]);
          currentIndex++;
        } else {
          // Polygon is complete
          setIsComplete(true);
          clearInterval(interval);
          
          // After a pause, generate a new shape
          setTimeout(() => {
            const newVertexCount = Math.floor(Math.random() * 5) + 4; // 4 to 8 vertices
            setAllSegments(generatePolygonSegments(newVertexCount));
          }, 1500); // Pause before new shape
        }
      }, 600); // Slower speed per edge

      return () => clearInterval(interval);
    };

    const cleanup = animatePolygon();
    return cleanup;
  }, [allSegments]); // Re-run the entire effect when a new set of segments is generated

  return (
    <div className="parcel-tracer-loader">
      <svg viewBox={`0 0 ${VIEWBOX_SIZE} ${VIEWBOX_SIZE}`} preserveAspectRatio="xMidYMid meet">
        <g className={`tracer-group ${isComplete ? 'completed' : ''}`}>
          {drawnSegments.filter(seg => seg && seg.x1 !== undefined).map((seg) => (
            <line
              key={seg.id}
              className="tracer-edge"
              x1={seg.x1}
              y1={seg.y1}
              x2={seg.x2}
              y2={seg.y2}
              // Set the origin for the 3D rotation to the start of the line
              style={{ transformOrigin: `${seg.x1}px ${seg.y1}px` }}
            />
          ))}
        </g>
      </svg>
    </div>
  );
}; 