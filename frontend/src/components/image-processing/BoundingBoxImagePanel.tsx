import React, { useState, useEffect } from 'react';
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

  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [imageDimensions, setImageDimensions] = useState({ width: 0, height: 0 });

  // Get the image endpoint URL
  const imageUrl = `http://localhost:8000/api/serve-image?image_path=${encodeURIComponent(imagePath)}`;

  console.log('🔗 Image URL:', imageUrl);

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
  const scaleX = displayDimensions.width / (imageDimensions.width || 1);
  const scaleY = displayDimensions.height / (imageDimensions.height || 1);

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
            <p className="error-detail">URL: {imageUrl}</p>
            <button 
              className="retry-btn"
              onClick={() => window.location.reload()}
            >
              Retry
            </button>
          </div>
        ) : (
          <div className="image-container" style={{ position: 'relative' }}>
            <img
              src={imageUrl}
              alt="Document with bounding boxes"
              onLoad={handleImageLoad}
              onError={handleImageError}
              style={{
                width: `${displayDimensions.width}px`,
                height: `${displayDimensions.height}px`,
                border: '1px solid #333',
                borderRadius: '4px',
                display: 'block'
              }}
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
                    border: '2px solid #00ff00',
                    backgroundColor: 'rgba(0, 255, 0, 0.1)',
                    pointerEvents: 'none',
                    fontSize: '10px',
                    color: '#00ff00',
                    fontWeight: 'bold'
                  }}
                >
                  {index < 20 && (
                    <span style={{ 
                      position: 'absolute', 
                      top: '-15px', 
                      left: '2px',
                      backgroundColor: '#00ff00',
                      color: 'black',
                      padding: '1px 3px',
                      fontSize: '10px'
                    }}>
                      {index}
                    </span>
                  )}
                </div>
              );
            })}
            
            {!imageLoaded && !imageError && (
              <div className="loading-message">
                <div className="loading-spinner"></div>
                <p>Loading document image...</p>
              </div>
            )}
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