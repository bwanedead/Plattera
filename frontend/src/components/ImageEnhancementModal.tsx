import React, { useState, useEffect, useRef, useCallback } from 'react';

interface EnhancementSettings {
  contrast: number;
  sharpness: number;
  brightness: number;
  color: number;
}

interface EnhancementPreset {
  name: string;
  settings: EnhancementSettings;
}

interface ImageEnhancementModalProps {
  isOpen: boolean;
  onClose: () => void;
  enhancementSettings: EnhancementSettings;
  onSettingsChange: (settings: EnhancementSettings) => void;
  previewImage?: File;
}

const DEFAULT_PRESETS: EnhancementPreset[] = [
  {
    name: "Default",
    settings: { contrast: 1.5, sharpness: 1.2, brightness: 1.0, color: 1.0 }
  },
  {
    name: "High Contrast",
    settings: { contrast: 1.8, sharpness: 1.5, brightness: 1.1, color: 0.8 }
  },
  {
    name: "Soft Text",
    settings: { contrast: 1.1, sharpness: 0.8, brightness: 1.2, color: 1.1 }
  },
  {
    name: "Vintage Document",
    settings: { contrast: 1.4, sharpness: 1.0, brightness: 0.9, color: 0.7 }
  }
];

export const ImageEnhancementModal: React.FC<ImageEnhancementModalProps> = ({
  isOpen,
  onClose,
  enhancementSettings,
  onSettingsChange,
  previewImage
}) => {
  const [localSettings, setLocalSettings] = useState<EnhancementSettings>(enhancementSettings);
  const [customPresets, setCustomPresets] = useState<EnhancementPreset[]>([]);
  const [presetName, setPresetName] = useState('');
  const [showSavePreset, setShowSavePreset] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const originalImageRef = useRef<HTMLImageElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  // Load custom presets from localStorage
  useEffect(() => {
    const saved = localStorage.getItem('imageEnhancementPresets');
    if (saved) {
      try {
        setCustomPresets(JSON.parse(saved));
      } catch (e) {
        console.warn('Failed to load saved presets:', e);
      }
    }
  }, []);

  // Save custom presets to localStorage
  useEffect(() => {
    localStorage.setItem('imageEnhancementPresets', JSON.stringify(customPresets));
  }, [customPresets]);

  // Load preview image (only when image changes, NOT when settings change)
  useEffect(() => {
    if (!previewImage || !canvasRef.current || !containerRef.current) return;

    const canvas = canvasRef.current;
    const container = containerRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const img = new Image();
    img.onload = () => {
      // Store original image reference
      originalImageRef.current = img;
      
      // Calculate initial zoom to fit image in container (only on image load)
      const containerWidth = container.clientWidth - 32; // Account for padding
      const containerHeight = container.clientHeight - 32;
      const scaleX = containerWidth / img.width;
      const scaleY = containerHeight / img.height;
      const initialZoom = Math.min(scaleX, scaleY, 1); // Don't zoom in beyond 100%
      
      setZoom(initialZoom);
      setPan({ x: 0, y: 0 });
      
      // Set canvas to original dimensions
      canvas.width = img.width;
      canvas.height = img.height;
      
      // Draw the enhanced image at full resolution
      applyEnhancements(ctx, img, localSettings, img.width, img.height);
    };
    
    const reader = new FileReader();
    reader.onload = (e) => {
      if (e.target?.result) {
        img.src = e.target.result as string;
      }
    };
    reader.readAsDataURL(previewImage);
  }, [previewImage]); // ✅ Only depend on previewImage, NOT localSettings

  // Update canvas when settings change (preserve zoom/pan state)
  useEffect(() => {
    if (!originalImageRef.current || !canvasRef.current) return;
    
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    const img = originalImageRef.current;
    
    // Redraw with new settings but keep zoom/pan state intact
    applyEnhancements(ctx, img, localSettings, img.width, img.height);
  }, [localSettings]); // ✅ Only redraw when settings change, don't reset zoom/pan

  const applyEnhancements = useCallback((
    ctx: CanvasRenderingContext2D,
    img: HTMLImageElement,
    settings: EnhancementSettings,
    width: number,
    height: number
  ) => {
    // Enable high-quality image rendering
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    
    // Clear canvas
    ctx.clearRect(0, 0, width, height);
    
    // Apply filters using CSS filter syntax
    const filters = [
      `contrast(${settings.contrast})`,
      `brightness(${settings.brightness})`,
      `saturate(${settings.color})`,
      // Note: CSS filter doesn't have direct sharpness, but we can simulate with contrast
      settings.sharpness !== 1.0 ? `contrast(${1 + (settings.sharpness - 1) * 0.3})` : ''
    ].filter(Boolean).join(' ');
    
    // Apply filters and draw enhanced image at original size (1:1 pixel mapping)
    ctx.filter = filters || 'none';
    ctx.drawImage(img, 0, 0);
    ctx.filter = 'none'; // Reset filter
  }, []);

  const handleSettingChange = (setting: keyof EnhancementSettings, value: number) => {
    const newSettings = { ...localSettings, [setting]: value };
    setLocalSettings(newSettings);
  };

  const handleApplyPreset = (preset: EnhancementPreset) => {
    setLocalSettings(preset.settings);
  };

  const handleSavePreset = () => {
    if (!presetName.trim()) return;
    
    const newPreset: EnhancementPreset = {
      name: presetName.trim(),
      settings: { ...localSettings }
    };
    
    setCustomPresets(prev => [...prev, newPreset]);
    setPresetName('');
    setShowSavePreset(false);
  };

  const handleDeletePreset = (index: number) => {
    setCustomPresets(prev => prev.filter((_, i) => i !== index));
  };

  const handleApply = () => {
    onSettingsChange(localSettings);
    onClose();
  };

  const handleCancel = () => {
    setLocalSettings(enhancementSettings); // Reset to original
    onClose();
  };

  // Zoom and pan handlers
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setZoom(prev => Math.min(Math.max(prev * delta, 0.1), 5));
  }, []);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  }, [pan]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isDragging) return;
    setPan({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y
    });
  }, [isDragging, dragStart]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  const resetView = useCallback(() => {
    if (!originalImageRef.current || !containerRef.current) return;
    
    const container = containerRef.current;
    const img = originalImageRef.current;
    const containerWidth = container.clientWidth - 32;
    const containerHeight = container.clientHeight - 32;
    const scaleX = containerWidth / img.width;
    const scaleY = containerHeight / img.height;
    const fitZoom = Math.min(scaleX, scaleY, 1);
    
    setZoom(fitZoom);
    setPan({ x: 0, y: 0 });
  }, []);

  const zoomToFit = useCallback(() => {
    resetView();
  }, [resetView]);

  const zoomToActual = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  if (!isOpen) return null;

  return (
    <div className="enhancement-modal-overlay">
      <div className="enhancement-modal">
        <div className="enhancement-modal-header">
          <h3>🎨 Image Enhancement</h3>
          <button className="modal-close-btn" onClick={handleCancel}>×</button>
        </div>

        <div className="enhancement-modal-content">
          <div className="enhancement-preview-section">
            <div className="preview-header">
              <h4>Live Preview</h4>
              {previewImage && (
                <div className="preview-controls">
                  <button onClick={zoomToFit} className="zoom-btn" title="Fit to window">
                    📐
                  </button>
                  <button onClick={zoomToActual} className="zoom-btn" title="100% size">
                    🔍
                  </button>
                  <span className="zoom-level">{Math.round(zoom * 100)}%</span>
                </div>
              )}
            </div>
            <div 
              ref={containerRef}
              className="preview-container"
              onWheel={handleWheel}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={handleMouseUp}
            >
              {previewImage ? (
                <>
                  <div 
                    className="canvas-wrapper"
                    style={{
                      transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
                      transformOrigin: '0 0',
                      cursor: isDragging ? 'grabbing' : 'grab'
                    }}
                  >
                    <canvas 
                      ref={canvasRef}
                      className="preview-canvas"
                    />
                  </div>
                  <div className="preview-hint">
                    <small>🖱️ Scroll to zoom • Drag to pan</small>
                  </div>
                </>
              ) : (
                <div className="no-preview">
                  <p>📷 No image selected for preview</p>
                  <p><small>Add images to the workspace to see live preview</small></p>
                </div>
              )}
            </div>
          </div>

          <div className="enhancement-controls-section">
            <div className="controls-grid">
              <div className="control-group">
                <label>
                  Contrast: {localSettings.contrast.toFixed(1)}
                </label>
                <input
                  type="range"
                  min="0.5"
                  max="2.0"
                  step="0.1"
                  value={localSettings.contrast}
                  onChange={(e) => handleSettingChange('contrast', parseFloat(e.target.value))}
                  className="enhancement-slider"
                />
              </div>

              <div className="control-group">
                <label>
                  Sharpness: {localSettings.sharpness.toFixed(1)}
                </label>
                <input
                  type="range"
                  min="0.5"
                  max="2.0"
                  step="0.1"
                  value={localSettings.sharpness}
                  onChange={(e) => handleSettingChange('sharpness', parseFloat(e.target.value))}
                  className="enhancement-slider"
                />
              </div>

              <div className="control-group">
                <label>
                  Brightness: {localSettings.brightness.toFixed(1)}
                </label>
                <input
                  type="range"
                  min="0.5"
                  max="1.5"
                  step="0.1"
                  value={localSettings.brightness}
                  onChange={(e) => handleSettingChange('brightness', parseFloat(e.target.value))}
                  className="enhancement-slider"
                />
              </div>

              <div className="control-group">
                <label>
                  Color: {localSettings.color.toFixed(1)}
                </label>
                <input
                  type="range"
                  min="0.0"
                  max="2.0"
                  step="0.1"
                  value={localSettings.color}
                  onChange={(e) => handleSettingChange('color', parseFloat(e.target.value))}
                  className="enhancement-slider"
                />
              </div>
            </div>

            <div className="presets-section">
              <h4>Presets</h4>
              <div className="presets-grid">
                {DEFAULT_PRESETS.map((preset, index) => (
                  <button
                    key={`default-${index}`}
                    className="preset-btn"
                    onClick={() => handleApplyPreset(preset)}
                  >
                    {preset.name}
                  </button>
                ))}
                
                {customPresets.map((preset, index) => (
                  <div key={`custom-${index}`} className="custom-preset-item">
                    <button
                      className="preset-btn custom"
                      onClick={() => handleApplyPreset(preset)}
                    >
                      {preset.name}
                    </button>
                    <button
                      className="delete-preset-btn"
                      onClick={() => handleDeletePreset(index)}
                      title="Delete preset"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>

              <div className="save-preset-section">
                {!showSavePreset ? (
                  <button 
                    className="save-preset-toggle-btn"
                    onClick={() => setShowSavePreset(true)}
                  >
                    + Save Current as Preset
                  </button>
                ) : (
                  <div className="save-preset-form">
                    <input
                      type="text"
                      placeholder="Preset name..."
                      value={presetName}
                      onChange={(e) => setPresetName(e.target.value)}
                      onKeyPress={(e) => e.key === 'Enter' && handleSavePreset()}
                      autoFocus
                    />
                    <button 
                      onClick={handleSavePreset}
                      disabled={!presetName.trim()}
                    >
                      Save
                    </button>
                    <button onClick={() => setShowSavePreset(false)}>
                      Cancel
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="enhancement-modal-footer">
          <button className="modal-btn secondary" onClick={handleCancel}>
            Cancel
          </button>
          <button className="modal-btn primary" onClick={handleApply}>
            Apply Settings
          </button>
        </div>
      </div>
    </div>
  );
}; 