import React, { useRef, useEffect, useState } from 'react';
import { BoundingBox, BoundingBoxStats } from '../../types/imageProcessing';

interface BoundingBoxViewerProps {
  imagePath: string;
  boundingBoxes: BoundingBox[];
  stats?: BoundingBoxStats;
  onClose: () => void;
}

export const BoundingBoxViewer: React.FC<BoundingBoxViewerProps> = ({
  imagePath,
  boundingBoxes,
  stats,
  onClose,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
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
    const imageUrl = `/api/system/serve-image?image_path=${encodeURIComponent(imagePath)}`;
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

      // Draw index label
      ctx.fillStyle = '#00ff00';
      ctx.fillText(`${box.index}`, x1 + 2, y1 - 5);
    });
  };

  const getDisplayDimensions = () => {
    if (!imageDimensions.width || !imageDimensions.height) return { width: 800, height: 600 };
    
    const maxWidth = 800;
    const maxHeight = 600;
    const aspectRatio = imageDimensions.width / imageDimensions.height;
    
    let displayWidth = imageDimensions.width;
    let displayHeight = imageDimensions.height;
    
    if (displayWidth > maxWidth) {
      displayWidth = maxWidth;
      displayHeight = displayWidth / aspectRatio;
    }
    
    if (displayHeight > maxHeight) {
      displayHeight = maxHeight;
      displayWidth = displayHeight * aspectRatio;
    }
    
    return { width: displayWidth, height: displayHeight };
  };

  const displayDimensions = getDisplayDimensions();

  return (
    <div className="bounding-box-viewer-overlay">
      <div className="bounding-box-viewer">
        <div className="bounding-box-viewer-header">
          <h3>Bounding Box Detection</h3>
          <button className="close-btn" onClick={onClose}>
            ×
          </button>
        </div>
        
        <div className="bounding-box-viewer-content">
          {imageError ? (
            <div className="error-message">
              <p>Failed to load image: {imagePath}</p>
              <p>Check browser console for details. The image might not be accessible.</p>
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
                  border: '1px solid #ccc',
                  maxWidth: '100%',
                  maxHeight: '100%',
                }}
              />
            </div>
          )}
          
          {stats && (
            <div className="bounding-box-stats">
              <h4>Detection Statistics</h4>
              <div className="stats-grid">
                <div className="stat-item">
                  <span className="stat-label">Total Boxes:</span>
                  <span className="stat-value">{stats.total_boxes}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Avg Width:</span>
                  <span className="stat-value">{stats.avg_width.toFixed(1)}px</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Avg Height:</span>
                  <span className="stat-value">{stats.avg_height.toFixed(1)}px</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Avg Area:</span>
                  <span className="stat-value">{stats.avg_area.toFixed(0)}px²</span>
                </div>
              </div>
            </div>
          )}
          
          <div className="bounding-box-info">
            <p>{boundingBoxes.length} word regions detected</p>
            <p>Green boxes show detected word boundaries</p>
          </div>
        </div>
      </div>
    </div>
  );
}; 