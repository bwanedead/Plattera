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
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
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
      console.log('✅ Image loaded successfully with bounding boxes');
    };

    img.onerror = (error) => {
      console.error('❌ Failed to load image:', imagePath);
      console.error('❌ Image error details:', error);
      setImageError(true);
      setImageLoaded(false);
      setErrorMessage('Failed to load image from server');
    };

    // Test different API endpoint paths
    const testEndpoints = [
      `/api/system/serve-image?image_path=${encodeURIComponent(imagePath)}`,
      `/api/serve-image?image_path=${encodeURIComponent(imagePath)}`,
      `/serve-image?image_path=${encodeURIComponent(imagePath)}`
    ];

    const tryLoadImage = async () => {
      for (const endpoint of testEndpoints) {
        try {
          console.log('🔄 Trying endpoint:', endpoint);
          
          const response = await fetch(endpoint, { method: 'HEAD' });
          console.log('🔍 Endpoint response:', endpoint, 'Status:', response.status);
          
          if (response.ok) {
            console.log('✅ Using working endpoint:', endpoint);
            img.src = endpoint;
            return;
          }
        } catch (error) {
          console.error('❌ Endpoint failed:', endpoint, error);
        }
      }
      
      // If all endpoints fail, try direct file loading as fallback
      console.warn('⚠️ All API endpoints failed, trying direct file access');
      setErrorMessage('All API endpoints failed. Image serving may not be configured correctly.');
      setImageError(true);
    };

    tryLoadImage();
  }, [imagePath, boundingBoxes]);

  const drawBoundingBoxes = (ctx: CanvasRenderingContext2D, boxes: BoundingBox[]) => {
    // Box styling
    ctx.strokeStyle = '#00ff00'; // Bright green
    ctx.lineWidth = 2;

    boxes.forEach((box) => {
      const [x1, y1, x2, y2] = box.bbox;
      const width = x2 - x1;
      const height = y2 - y1;

      // Draw bounding box rectangle
      ctx.strokeRect(x1, y1, width, height);
      
      // Draw semi-transparent fill
      ctx.fillStyle = 'rgba(0, 255, 0, 0.1)';
      ctx.fillRect(x1, y1, width, height);

      // Draw index label (only for first 20 boxes to avoid clutter)
      if (box.index < 20) {
        ctx.fillStyle = '#00ff00';
        ctx.font = '12px Arial';
        ctx.fillText(`${box.index}`, x1 + 2, y1 - 5);
      }
    });
  };

  const getDisplayDimensions = () => {
    if (!imageDimensions.width || !imageDimensions.height) {
      return { width: 350, height: 500 };
    }
    
    const maxWidth = 350;
    const maxHeight = 500;
    const aspectRatio = imageDimensions.width / imageDimensions.height;
    
    let displayWidth = imageDimensions.width;
    let displayHeight = imageDimensions.height;
    
    // Scale to fit container
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
    <div className="bounding-box-overlay-panel">
      <div className="bounding-box-panel-header">
        <h4>Original Document</h4>
        <button className="close-btn" onClick={onClose}>
          ×
        </button>
      </div>
      
      <div className="bounding-box-panel-content">
        {imageError ? (
          <div className="error-message">
            <p>❌ Image Loading Failed</p>
            <p className="error-detail">{errorMessage}</p>
            <p className="error-detail">Path: {imagePath}</p>
            <button 
              className="retry-btn"
              onClick={() => window.location.reload()}
            >
              Retry
            </button>
          </div>
        ) : !imageLoaded ? (
          <div className="loading-message">
            <div className="loading-spinner"></div>
            <p>Loading document image...</p>
          </div>
        ) : (
          <div className="image-container">
            <canvas
              ref={canvasRef}
              style={{
                width: `${displayDimensions.width}px`,
                height: `${displayDimensions.height}px`,
                border: '1px solid #333',
                borderRadius: '4px',
              }}
            />
          </div>
        )}
        
        {stats && (
          <div className="bounding-box-mini-stats">
            <div className="mini-stat">
              <span>{stats.total_boxes}</span>
              <small>regions</small>
            </div>
            <div className="mini-stat">
              <span>{Math.round(stats.avg_width)}px</span>
              <small>avg width</small>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}; 