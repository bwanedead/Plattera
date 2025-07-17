import React, { useState, useEffect, useRef, useCallback } from 'react';
import { BoundingBox, BoundingBoxStats } from '../../types/imageProcessing';

interface BoundingBoxImagePanelProps {
  imagePath: string;
  boundingBoxes: BoundingBox[];
  stats?: BoundingBoxStats;
  onClose: () => void;
}

export const BoundingBoxImagePanel: React.FC<BoundingBoxImagePanelProps> = ({
  imagePath,
  boundingBoxes,
  stats,
  onClose,
}) => {
  console.log('🖼️ BoundingBoxImagePanel rendering with:', {
    imagePath,
    boundingBoxesCount: boundingBoxes.length,
    stats
  });

  // Panel state
  const [panelPosition, setPanelPosition] = useState({ x: 50, y: 50 });
  const [panelSize, setPanelSize] = useState({ width: 600, height: 700 });
  const [isDragging, setIsDragging] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  // Image state
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [imageDimensions, setImageDimensions] = useState({ width: 0, height: 0 });

  // Zoom and pan state
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });

  const panelRef = useRef<HTMLDivElement>(null);
  const imageContainerRef = useRef<HTMLDivElement>(null);

  // Get the image endpoint URL
  const imageUrl = `http://localhost:8000/api/serve-image?image_path=${encodeURIComponent(imagePath)}`;

  const handleImageLoad = (event: React.SyntheticEvent<HTMLImageElement>) => {
    const img = event.currentTarget;
    setImageDimensions({ width: img.naturalWidth, height: img.naturalHeight });
    setImageLoaded(true);
    setImageError(false);
    console.log('✅ Image loaded successfully:', img.naturalWidth, 'x', img.naturalHeight);
  };

  const handleImageError = (event: React.SyntheticEvent<HTMLImageElement>) => {
    console.error('❌ Failed to load image:', imagePath);
    console.error('❌ Image URL that failed:', imageUrl);
    setImageError(true);
    setImageLoaded(false);
    setErrorMessage('Failed to load image from server');
  };

  // Panel drag handlers
  const handlePanelMouseDown = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget || (e.target as HTMLElement).classList.contains('bounding-box-panel-header')) {
      setIsDragging(true);
      setDragStart({
        x: e.clientX - panelPosition.x,
        y: e.clientY - panelPosition.y
      });
    }
  };

  const handlePanelMouseMove = useCallback((e: MouseEvent) => {
    if (isDragging) {
      setPanelPosition({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y
      });
    }
  }, [isDragging, dragStart]);

  const handlePanelMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Panel resize handlers
  const handleResizeMouseDown = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsResizing(true);
    setDragStart({
      x: e.clientX - panelSize.width,
      y: e.clientY - panelSize.height
    });
  };

  const handleResizeMouseMove = useCallback((e: MouseEvent) => {
    if (isResizing) {
      setPanelSize({
        width: Math.max(400, e.clientX - dragStart.x),
        height: Math.max(300, e.clientY - dragStart.y)
      });
    }
  }, [isResizing, dragStart]);

  const handleResizeMouseUp = useCallback(() => {
    setIsResizing(false);
  }, []);

  // Image zoom handlers
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const zoomFactor = 0.1;
    const newZoom = e.deltaY > 0 
      ? Math.max(0.1, zoom - zoomFactor)
      : Math.min(5, zoom + zoomFactor);
    setZoom(newZoom);
  };

  // Image pan handlers
  const handleImageMouseDown = (e: React.MouseEvent) => {
    if (e.button === 0) { // Left mouse button
      setIsPanning(true);
      setPanStart({
        x: e.clientX - pan.x,
        y: e.clientY - pan.y
      });
      e.preventDefault();
    }
  };

  const handleImageMouseMove = useCallback((e: MouseEvent) => {
    if (isPanning) {
      setPan({
        x: e.clientX - panStart.x,
        y: e.clientY - panStart.y
      });
    }
  }, [isPanning, panStart]);

  const handleImageMouseUp = useCallback(() => {
    setIsPanning(false);
  }, []);

  // Reset zoom and pan
  const resetView = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  // Global mouse event listeners
  useEffect(() => {
    if (isDragging || isResizing) {
      const handleMouseMove = isDragging ? handlePanelMouseMove : handleResizeMouseMove;
      const handleMouseUp = isDragging ? handlePanelMouseUp : handleResizeMouseUp;
      
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      
      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDragging, isResizing, handlePanelMouseMove, handlePanelMouseUp, handleResizeMouseMove, handleResizeMouseUp]);

  useEffect(() => {
    if (isPanning) {
      document.addEventListener('mousemove', handleImageMouseMove);
      document.addEventListener('mouseup', handleImageMouseUp);
      
      return () => {
        document.removeEventListener('mousemove', handleImageMouseMove);
        document.removeEventListener('mouseup', handleImageMouseUp);
      };
    }
  }, [isPanning, handleImageMouseMove, handleImageMouseUp]);

  const getDisplayDimensions = () => {
    if (!imageDimensions.width || !imageDimensions.height) {
      return { width: 500, height: 600 };
    }
    
    // Use the image's natural dimensions as base, then apply zoom
    const baseWidth = Math.min(imageDimensions.width, panelSize.width - 40);
    const baseHeight = Math.min(imageDimensions.height, panelSize.height - 120);
    
    // Maintain aspect ratio
    const aspectRatio = imageDimensions.width / imageDimensions.height;
    let displayWidth = baseWidth;
    let displayHeight = baseWidth / aspectRatio;
    
    if (displayHeight > baseHeight) {
      displayHeight = baseHeight;
      displayWidth = displayHeight * aspectRatio;
    }
    
    return { 
      width: displayWidth * zoom, 
      height: displayHeight * zoom 
    };
  };

  const displayDimensions = getDisplayDimensions();
  const scaleX = displayDimensions.width / (imageDimensions.width || 1);
  const scaleY = displayDimensions.height / (imageDimensions.height || 1);

  return (
    <div
      ref={panelRef}
      className="bounding-box-overlay-panel"
      style={{
        position: 'fixed',
        left: `${panelPosition.x}px`,
        top: `${panelPosition.y}px`,
        width: `${panelSize.width}px`,
        height: `${panelSize.height}px`,
        zIndex: 1000,
        backgroundColor: '#1a1a1a',
        border: '2px solid #333',
        borderRadius: '8px',
        boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
        cursor: isDragging ? 'grabbing' : 'grab',
        userSelect: 'none'
      }}
      onMouseDown={handlePanelMouseDown}
    >
      {/* Header */}
      <div 
        className="bounding-box-panel-header"
        style={{
          padding: '8px 12px',
          backgroundColor: '#2a2a2a',
          borderBottom: '1px solid #333',
          borderRadius: '6px 6px 0 0',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          cursor: 'grab'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <h4 style={{ margin: 0, color: '#fff', fontSize: '14px' }}>
            Original Document
          </h4>
          <div style={{ display: 'flex', gap: '5px' }}>
            <button
              onClick={resetView}
              style={{
                padding: '2px 6px',
                fontSize: '10px',
                backgroundColor: '#444',
                color: '#fff',
                border: 'none',
                borderRadius: '3px',
                cursor: 'pointer'
              }}
            >
              Reset
            </button>
            <span style={{ fontSize: '10px', color: '#ccc' }}>
              {Math.round(zoom * 100)}%
            </span>
          </div>
        </div>
        <button 
          onClick={onClose}
          style={{
            backgroundColor: 'transparent',
            border: 'none',
            color: '#fff',
            fontSize: '18px',
            cursor: 'pointer',
            padding: '0 4px'
          }}
        >
          ×
        </button>
      </div>
      
      {/* Content */}
      <div 
        style={{ 
          height: 'calc(100% - 50px)', 
          overflow: 'hidden',
          position: 'relative'
        }}
      >
        {imageError ? (
          <div style={{ padding: '20px', color: '#fff' }}>
            <p>❌ Image Loading Failed</p>
            <p style={{ fontSize: '12px', color: '#ccc' }}>{errorMessage}</p>
            <p style={{ fontSize: '12px', color: '#ccc' }}>Path: {imagePath}</p>
            <p style={{ fontSize: '12px', color: '#ccc' }}>URL: {imageUrl}</p>
            <button 
              onClick={() => window.location.reload()}
              style={{
                padding: '8px 12px',
                backgroundColor: '#444',
                color: '#fff',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              Retry
            </button>
          </div>
        ) : (
          <div 
            ref={imageContainerRef}
            style={{ 
              position: 'relative', 
              width: '100%', 
              height: '100%',
              overflow: 'hidden',
              cursor: isPanning ? 'grabbing' : 'grab'
            }}
            onWheel={handleWheel}
            onMouseDown={handleImageMouseDown}
          >
            <div
              style={{
                position: 'relative',
                transform: `translate(${pan.x}px, ${pan.y}px)`,
                transition: isPanning ? 'none' : 'transform 0.1s ease',
                display: 'inline-block'
              }}
            >
              <img
                src={imageUrl}
                alt="Document with bounding boxes"
                onLoad={handleImageLoad}
                onError={handleImageError}
                style={{
                  width: `${displayDimensions.width}px`,
                  height: `${displayDimensions.height}px`,
                  border: '1px solid #555',
                  borderRadius: '4px',
                  display: 'block',
                  userSelect: 'none',
                  pointerEvents: 'none'
                }}
                draggable={false}
              />
              
              {/* Bounding box overlays */}
              {imageLoaded && boundingBoxes.map((box, index) => {
                const [x1, y1, x2, y2] = box.bbox;
                const width = (x2 - x1) * scaleX;
                const height = (y2 - y1) * scaleY;
                const left = x1 * scaleX;
                const top = y1 * scaleY;

                return (
                  <div
                    key={index}
                    style={{
                      position: 'absolute',
                      left: `${left}px`,
                      top: `${top}px`,
                      width: `${width}px`,
                      height: `${height}px`,
                      border: '1px solid #00ff00',
                      backgroundColor: 'rgba(0, 255, 0, 0.1)',
                      pointerEvents: 'none',
                      fontSize: `${Math.max(8, 10 * zoom)}px`,
                      color: '#00ff00',
                      fontWeight: 'bold'
                    }}
                  >
                    {index < 20 && zoom > 0.5 && (
                      <span style={{ 
                        position: 'absolute', 
                        top: '-16px', 
                        left: '2px',
                        backgroundColor: '#00ff00',
                        color: 'black',
                        padding: '1px 3px',
                        fontSize: `${Math.max(8, 10 * zoom)}px`,
                        borderRadius: '2px'
                      }}>
                        {index}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
            
            {!imageLoaded && !imageError && (
              <div style={{
                position: 'absolute',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                color: '#fff',
                textAlign: 'center'
              }}>
                <div style={{
                  width: '40px',
                  height: '40px',
                  border: '3px solid #333',
                  borderTop: '3px solid #00ff00',
                  borderRadius: '50%',
                  animation: 'spin 1s linear infinite',
                  margin: '0 auto 10px'
                }}></div>
                <p>Loading document image...</p>
              </div>
            )}
          </div>
        )}
        
        {/* Stats */}
        {stats && (
          <div style={{
            position: 'absolute',
            bottom: '10px',
            left: '10px',
            display: 'flex',
            gap: '10px',
            backgroundColor: 'rgba(0,0,0,0.7)',
            padding: '5px 10px',
            borderRadius: '4px',
            fontSize: '12px',
            color: '#ccc'
          }}>
            <div>
              <span style={{ color: '#00ff00', fontWeight: 'bold' }}>{stats.total_boxes}</span>
              <span> regions</span>
            </div>
            <div>
              <span style={{ color: '#00ff00', fontWeight: 'bold' }}>{Math.round(stats.avg_width)}px</span>
              <span> avg width</span>
            </div>
          </div>
        )}
      </div>

      {/* Resize handle */}
      <div
        onMouseDown={handleResizeMouseDown}
        style={{
          position: 'absolute',
          bottom: 0,
          right: 0,
          width: '20px',
          height: '20px',
          cursor: 'se-resize',
          background: 'linear-gradient(-45deg, transparent 30%, #666 30%, #666 70%, transparent 70%)',
          backgroundSize: '4px 4px'
        }}
      />
    </div>
  );
}; 