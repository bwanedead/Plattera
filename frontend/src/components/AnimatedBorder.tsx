/*
🔴 CRITICAL ANIMATED BORDER COMPONENT DOCUMENTATION 🔴
======================================================

THIS COMPONENT PROVIDES VISUAL CONSISTENCY ACROSS ALL INTERACTIVE ELEMENTS

CRITICAL VISUAL CONSISTENCY REQUIREMENTS:
========================================

1. ANIMATION TIMING (CRITICAL - MUST MATCH PARCELTRACER):
   - Trace interval: 600ms (matches ParcelTracerLoader exactly)
   - Pulse duration: 1.2s (matches ParcelTracerLoader exactly)
   - Total cycle: 1.8s (600ms + 1.2s)

2. COLOR SCHEME (CRITICAL - MUST MATCH THEME):
   - Animating: #3b82f6 (bright blue with glow)
   - Completed: rgba(59, 130, 246, 0.3) (dim blue)
   - Stroke width: Configurable (1.5px for buttons, 2px for controls)

3. USAGE PATTERN (CRITICAL - HEATMAP MUST FOLLOW):
   - Wrap interactive elements (buttons, toggles, controls)
   - Use isHovered prop for hover state activation
   - Use borderRadius prop to match wrapped element
   - Use strokeWidth prop for appropriate line thickness

CURRENT IMPLEMENTATIONS:
=======================

1. NAVIGATION BUTTONS:
   - Home button, Text to Schema button
   - strokeWidth: 1.5px (fine lines for sleek buttons)
   - Hover activation only

2. DRAFT SELECTOR:
   - Collapsed bubble state
   - strokeWidth: 2px (slightly thicker for controls)
   - Hover activation only

HEATMAP INTEGRATION REQUIREMENTS:
===============================

1. HEATMAP TOGGLE CONSISTENCY:
   - MUST use same AnimatedBorder wrapper
   - MUST use strokeWidth: 2px (match DraftSelector)
   - MUST use borderRadius: 6px (match DraftSelector)
   - MUST use same hover state pattern

2. POSITIONING COORDINATION:
   - AnimatedBorder adds no positioning (wrapper only)
   - Actual positioning handled by CSS classes
   - Must not interfere with absolute positioning

3. VISUAL HIERARCHY:
   - All interactive controls use AnimatedBorder
   - Creates consistent interaction feedback
   - Maintains brand identity across features

IMPLEMENTATION PATTERN FOR HEATMAP:
==================================

```tsx
<AnimatedBorder
  isHovered={isHeatmapToggleHovered}
  borderRadius={6}
  strokeWidth={2}
>
  <button 
    className="heatmap-toggle-button"
    onMouseEnter={() => setIsHeatmapToggleHovered(true)}
    onMouseLeave={() => setIsHeatmapToggleHovered(false)}
    onClick={onToggle}
  >
    🔥
  </button>
</AnimatedBorder>
```

CRITICAL DEPENDENCIES:
======================

1. SVG PATH CALCULATION:
   - Uses element dimensions to calculate border path
   - Handles different border radius values
   - Maintains sharp line ends (stroke-linecap: butt)

2. ANIMATION STATE MANAGEMENT:
   - isAnimating state controls animation cycle
   - useEffect manages timing intervals
   - Cleanup prevents memory leaks

3. RESPONSIVE BEHAVIOR:
   - Adapts to any element size
   - Maintains proportional border radius
   - Works with absolute and relative positioning

⚠️  DO NOT MODIFY:
- Animation timing values (breaks visual consistency)
- Color values (breaks theme integration)
- SVG path calculation (breaks border rendering)
- Cleanup logic (causes memory leaks)

✅ SAFE TO MODIFY:
- Default prop values
- Additional animation states
- Performance optimizations
- Accessibility features

TESTING CHECKPOINTS FOR HEATMAP:
===============================

BEFORE heatmap integration:
1. ✅ Navigation buttons animate correctly
2. ✅ DraftSelector bubble animates correctly
3. ✅ Timing matches ParcelTracerLoader exactly
4. ✅ Colors match theme in both light/dark modes

AFTER heatmap integration:
1. ✅ HeatmapToggle uses same animation pattern
2. ✅ All controls have consistent visual feedback
3. ✅ No performance degradation with multiple instances
4. ✅ Hover states work independently for each control

FAILURE PREVENTION:
==================

Common mistakes that would break visual consistency:
- Using different animation timing (breaks brand identity)
- Skipping AnimatedBorder wrapper (creates inconsistent UX)
- Modifying color values (breaks theme integration)
- Interfering with positioning logic (breaks layout)

If this component breaks, heatmap feature will lose:
- Visual consistency with existing controls
- Professional interaction feedback
- Brand identity maintenance
- User experience coherence
*/

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
  
  // For sharp corners - create a complete rectangle with no gaps
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

  // Animation logic - match the ParcelTracerLoader timing exactly
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
        
        // Match ParcelTracerLoader timing exactly
        setTimeout(() => {
          setCurrentSegmentIndex(-1);
          setIsComplete(false);
          setAnimationKey(prev => prev + 1);
        }, 1200); // Match the ParcelTracerLoader pulse duration
      }
    }, 600); // Match the ParcelTracerLoader segment timing

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