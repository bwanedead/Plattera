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

  // Load and display preview image
  useEffect(() => {
    if (!previewImage || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const img = new Image();
    img.onload = () => {
      // Store original image reference
      originalImageRef.current = img;
      
      // Set canvas size to fit the modal while maintaining aspect ratio
      const maxWidth = 400;
      const maxHeight = 300;
      const ratio = Math.min(maxWidth / img.width, maxHeight / img.height);
      
      canvas.width = img.width * ratio;
      canvas.height = img.height * ratio;
      
      // Draw the enhanced image
      applyEnhancements(ctx, img, localSettings, canvas.width, canvas.height);
    };
    
    const reader = new FileReader();
    reader.onload = (e) => {
      if (e.target?.result) {
        img.src = e.target.result as string;
      }
    };
    reader.readAsDataURL(previewImage);
  }, [previewImage, localSettings]);

  const applyEnhancements = useCallback((
    ctx: CanvasRenderingContext2D,
    img: HTMLImageElement,
    settings: EnhancementSettings,
    width: number,
    height: number
  ) => {
    // Clear canvas
    ctx.clearRect(0, 0, width, height);
    
    // Draw original image
    ctx.drawImage(img, 0, 0, width, height);
    
    // Apply filters using CSS filter syntax
    const filters = [
      `contrast(${settings.contrast})`,
      `brightness(${settings.brightness})`,
      `saturate(${settings.color})`,
      // Note: CSS filter doesn't have direct sharpness, but we can simulate with contrast
      settings.sharpness !== 1.0 ? `contrast(${1 + (settings.sharpness - 1) * 0.3})` : ''
    ].filter(Boolean).join(' ');
    
    if (filters) {
      ctx.filter = filters;
      ctx.drawImage(img, 0, 0, width, height);
      ctx.filter = 'none'; // Reset filter
    }
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
            <h4>Live Preview</h4>
            <div className="preview-container">
              {previewImage ? (
                <canvas 
                  ref={canvasRef}
                  className="preview-canvas"
                />
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