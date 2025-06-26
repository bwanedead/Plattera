import React, { useState, useEffect, useRef } from 'react';

interface AnimatedBorderProps {
  children: React.ReactNode;
  className?: string;
  isHovered?: boolean;
  borderRadius?: number;
  strokeWidth?: number;
  color?: string;
}

interface BorderSegment {
  id: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  length: number;
}

const generateBorderSegments = (width: number, height: number, borderRadius: number = 0): BorderSegment[] => {
  const segments: BorderSegment[] = [];
  
  if (borderRadius > 0) {
    // For rounded rectangles, we'll create segments that approximate the rounded corners
    const r = Math.min(borderRadius, Math.min(width, height) / 2);
    
    // Top edge (left to right, accounting for radius)
    segments.push({
      id: 'top',
      x1: r,
      y1: 0,
      x2: width - r,
      y2: 0,
      length: width - 2 * r
    });
    
    // Right edge (top to bottom, accounting for radius)
    segments.push({
      id: 'right',
      x1: width,
      y1: r,
      x2: width,
      y2: height - r,
      length: height - 2 * r
    });
    
    // Bottom edge (right to left, accounting for radius)
    segments.push({
      id: 'bottom',
      x1: width - r,
      y1: height,
      x2: r,
      y2: height,
      length: width - 2 * r
    });
    
    // Left edge (bottom to top, accounting for radius)
    segments.push({
      id: 'left',
      x1: 0,
      y1: height - r,
      x2: 0,
      y2: r,
      length: height - 2 * r
    });
  } else {
    // Sharp corners - simple rectangle
    segments.push(
      {
        id: 'top',
        x1: 0,
        y1: 0,
        x2: width,
        y2: 0,
        length: width
      },
      {
        id: 'right',
        x1: width,
        y1: 0,
        x2: width,
        y2: height,
        length: height
      },
      {
        id: 'bottom',
        x1: width,
        y1: height,
        x2: 0,
        y2: height,
        length: width
      },
      {
        id: 'left',
        x1: 0,
        y1: height,
        x2: 0,
        y2: 0,
        length: height
      }
    );
  }
  
  return segments;
};

export const AnimatedBorder: React.FC<AnimatedBorderProps> = ({
  children,
  className = '',
  isHovered = false,
  borderRadius = 0,
  strokeWidth = 2,
  color = 'var(--accent-primary)'
}) => {
  const [currentSegmentIndex, setCurrentSegmentIndex] = useState(-1);
  const [isComplete, setIsComplete] = useState(false);
  const [animationKey, setAnimationKey] = useState(0);
  const [segments, setSegments] = useState<BorderSegment[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);

  // Update segments when container size changes
  useEffect(() => {
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      setSegments(generateBorderSegments(rect.width, rect.height, borderRadius));
    }
  }, [borderRadius, isHovered]);

  // Animation logic
  useEffect(() => {
    if (!isHovered || segments.length === 0) {
      setCurrentSegmentIndex(-1);
      setIsComplete(false);
      return;
    }

    let index = 0;
    const interval = setInterval(() => {
      if (index < segments.length) {
        setCurrentSegmentIndex(index);
        index++;
      } else {
        clearInterval(interval);
        setIsComplete(true);
        
        // Pulse and restart cycle
        setTimeout(() => {
          setCurrentSegmentIndex(-1);
          setIsComplete(false);
          setAnimationKey(prev => prev + 1);
        }, 1200); // Match the ParcelTracerLoader timing
      }
    }, 150); // Faster than the loader for snappier button feel

    return () => clearInterval(interval);
  }, [isHovered, segments, animationKey]);

  return (
    <div 
      ref={containerRef}
      className={`animated-border-container ${className}`}
      style={{ position: 'relative' }}
    >
      {children}
      
      {isHovered && segments.length > 0 && (
        <svg 
          className="animated-border-svg"
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            pointerEvents: 'none',
            overflow: 'visible'
          }}
        >
          <g className={`border-tracer-group ${isComplete ? 'completed' : ''}`}>
            {segments.map((segment, index) => {
              const isVisible = index <= currentSegmentIndex;
              const isAnimating = index === currentSegmentIndex;
              
              return (
                <line
                  key={`${segment.id}-${animationKey}`}
                  className={`border-tracer-edge ${isVisible ? 'visible' : ''} ${isAnimating ? 'animating' : ''}`}
                  x1={segment.x1}
                  y1={segment.y1}
                  x2={segment.x2}
                  y2={segment.y2}
                  strokeDasharray={segment.length}
                  style={{ 
                    '--segment-length': segment.length,
                    '--border-color': color,
                    strokeWidth
                  } as React.CSSProperties}
                />
              );
            })}
          </g>
        </svg>
      )}
    </div>
  );
}; 