import React, { useRef, useEffect, useState } from 'react';
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
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);
  const [imageDimensions, setImageDimensions] = useState({ width: 0, height: 0 });

  useEffect(() => {
    if (!canvasRef.current || !boundingBoxes.length) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const img = new Image();
    
    img.onload = () => {
      // Set canvas size to match image
      canvas.width = img.width;
      canvas.height = img.height;
      setImageDimensions({ width: img.width, height: img.height });

      // Draw the image
      ctx.drawImage(img, 0, 0);

      // Draw bounding boxes
      drawBoundingBoxes(ctx, boundingBoxes);
      setImageLoaded(true);
      setImageError(false);
    };

    img.onerror = () => {
      console.error('Failed to load image:', imagePath);
      setImageError(true);
      setImageLoaded(false);
    };

    // Use the backend API to serve the image
    const imageUrl = `/api/serve-image?image_path=${encodeURIComponent(imagePath)}`;
    console.log('Loading image from:', imageUrl);
    
    img.src = imageUrl;
  }, [imagePath, boundingBoxes]);

  const drawBoundingBoxes = (ctx: CanvasRenderingContext2D, boxes: BoundingBox[]) => {
    // Box styling
    ctx.strokeStyle = '#00ff00'; // Bright green
    ctx.lineWidth = 2;
    ctx.fillStyle = 'rgba(0, 255, 0, 0.1)'; // Semi-transparent green fill

    // Font for labels
    ctx.font = '12px Arial';
    ctx.fillStyle = '#00ff00';

    boxes.forEach((box) => {
      const [x1, y1, x2, y2] = box.bbox;
      const width = x2 - x1;
      const height = y2 - y1;

      // Draw bounding box rectangle
      ctx.strokeRect(x1, y1, width, height);
      
      // Draw semi-transparent fill
      ctx.fillStyle = 'rgba(0, 255, 0, 0.1)';
      ctx.fillRect(x1, y1, width, height);

      // Draw index label (only for first few boxes to avoid clutter)
      if (box.index < 50) {
        ctx.fillStyle = '#00ff00';
        ctx.fillText(`${box.index}`, x1 + 2, y1 - 5);
      }
    });
  };

  const getDisplayDimensions = () => {
    if (!imageDimensions.width || !imageDimensions.height || !containerRef.current) {
      return { width: 300, height: 400 };
    }
    
    const container = containerRef.current;
    const containerWidth = container.clientWidth - 20; // Account for padding
    const containerHeight = container.clientHeight - 100; // Account for header and stats
    
    const aspectRatio = imageDimensions.width / imageDimensions.height;
    
    let displayWidth = imageDimensions.width;
    let displayHeight = imageDimensions.height;
    
    // Scale to fit container
    if (displayWidth > containerWidth) {
      displayWidth = containerWidth;
      displayHeight = displayWidth / aspectRatio;
    }
    
    if (displayHeight > containerHeight) {
      displayHeight = containerHeight;
      displayWidth = displayHeight * aspectRatio;
    }
    
    return { width: displayWidth, height: displayHeight };
  };

  const displayDimensions = getDisplayDimensions();

  return (
    <div ref={containerRef} className="bounding-box-image-panel">
      <div className="bounding-box-panel-header">
        <h4>Original Document</h4>
        <button className="close-btn" onClick={onClose}>
          ×
        </button>
      </div>
      
      <div className="bounding-box-panel-content">
        {imageError ? (
          <div className="error-message">
            <p>Failed to load image</p>
            <p className="error-detail">Check browser console</p>
          </div>
        ) : !imageLoaded ? (
          <div className="loading-message">
            <p>Loading image...</p>
          </div>
        ) : (
          <div className="image-container">
            <canvas
              ref={canvasRef}
              style={{
                width: `${displayDimensions.width}px`,
                height: `${displayDimensions.height}px`,
                border: '1px solid #333',
                maxWidth: '100%',
                maxHeight: '100%',
              }}
            />
          </div>
        )}
        
        {stats && (
          <div className="bounding-box-mini-stats">
            <div className="mini-stat">
              <span>{stats.total_boxes}</span>
              <small>boxes</small>
            </div>
            <div className="mini-stat">
              <span>{stats.avg_width.toFixed(0)}px</span>
              <small>avg width</small>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}; 