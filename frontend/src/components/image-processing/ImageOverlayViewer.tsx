import React, { useEffect, useRef, useState, useCallback } from 'react';

interface ImageOverlayViewerProps {
  zIndex?: number;
}

type ViewerImage = {
  url: string;
  naturalWidth: number;
  naturalHeight: number;
};

// Lightweight, modern-styled toolbar button
const ToolbarButton: React.FC<{ title: string; onClick: (e: React.MouseEvent) => void; children: React.ReactNode }> = ({ title, onClick, children }) => {
  const [hover, setHover] = useState(false);
  const [active, setActive] = useState(false);
  return (
    <button
      title={title}
      onClick={(e) => { e.stopPropagation(); onClick(e); }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => { setHover(false); setActive(false); }}
      onMouseDown={() => setActive(true)}
      onMouseUp={() => setActive(false)}
      style={{
        appearance: 'none',
        border: '1px solid ' + (active ? '#2a2a2a' : hover ? '#2f2f2f' : '#2a2a2a'),
        color: '#ddd',
        background: active ? '#1b1b1b' : hover ? '#212121' : 'transparent',
        padding: '4px 10px',
        borderRadius: 6,
        lineHeight: 1.1,
        cursor: 'pointer',
        fontSize: 13,
        boxShadow: active ? 'inset 0 1px 3px rgba(0,0,0,0.35)' : 'none'
      }}
    >
      {children}
    </button>
  );
};

export const ImageOverlayViewer: React.FC<ImageOverlayViewerProps> = ({ zIndex = 9999 }) => {
  const [visible, setVisible] = useState(false);
  const [images, setImages] = useState<ViewerImage[]>([]);
  const [index, setIndex] = useState(0);

  // Window position and size (outer window)
  const [position, setPosition] = useState({ x: 100, y: 100 });
  const [size, setSize] = useState({ w: 600, h: 400 });

  // Image viewport state (inner transform)
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });

  // Filters
  const [showSettings, setShowSettings] = useState(false);
  const [contrast, setContrast] = useState(1);
  const [brightness, setBrightness] = useState(1);
  const [saturation, setSaturation] = useState(1);

  // Drag state
  const draggingWindow = useRef(false);
  const dragStart = useRef({ x: 0, y: 0 });
  const dragOffset = useRef({ x: 0, y: 0 });

  const panningImage = useRef(false);
  const panStart = useRef({ x: 0, y: 0 });
  const panOffsetStart = useRef({ x: 0, y: 0 });

  const close = useCallback(() => setVisible(false), []);

  // Compute container size to fit image with minimal margin
  const computeWindowSize = (iw: number, ih: number) => {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const margin = 24; // minimal border
    const headerH = 36; // header height

    // Max usable area
    const maxW = vw - margin * 2;
    const maxH = vh - margin * 2;

    // Fit image inside (maxW x maxH - header)
    const ratio = iw / ih;
    let w = Math.min(iw, maxW);
    let h = w / ratio;
    if (h + headerH > maxH) {
      h = Math.min(ih, maxH - headerH);
      w = h * ratio;
    }

    // Ensure minimum reasonable size
    w = Math.max(240, Math.floor(w));
    h = Math.max(200, Math.floor(h));

    return { w, h: h + headerH };
  };

  // Load images (get natural size) then open viewer
  useEffect(() => {
    const handler = (e: Event) => {
      const ce = e as CustomEvent<{ images: string[]; initialIndex?: number }>;
      const urls = Array.isArray(ce.detail?.images) ? ce.detail.images : [];
      if (urls.length === 0) return;

      // Reset state
      setScale(1);
      setOffset({ x: 0, y: 0 });
      setContrast(1); setBrightness(1); setSaturation(1);
      setShowSettings(false);

      // Preload first image (or initial index) to compute window size
      const startIdx = Math.max(0, Math.min(urls.length - 1, ce.detail?.initialIndex ?? 0));
      const img = new Image();
      img.onload = () => {
        const vw = computeWindowSize(img.naturalWidth, img.naturalHeight);
        setSize(vw);
        setPosition({ x: Math.max(16, (window.innerWidth - vw.w) / 2), y: Math.max(16, (window.innerHeight - vw.h) / 2) });
        setVisible(true);
      };
      img.onerror = () => {
        // Fallback default size
        setSize({ w: 600, h: 400 });
        setVisible(true);
      };
      img.src = urls[startIdx];

      // Load all images metadata
      Promise.all(urls.map(url => new Promise<ViewerImage>(resolve => {
        const i = new Image();
        i.onload = () => resolve({ url, naturalWidth: i.naturalWidth, naturalHeight: i.naturalHeight });
        i.onerror = () => resolve({ url, naturalWidth: 0, naturalHeight: 0 });
        i.src = url;
      }))).then(vimgs => {
        setImages(vimgs);
        setIndex(startIdx);
      });
    };
    document.addEventListener('image-overlay:open', handler as EventListener);
    return () => document.removeEventListener('image-overlay:open', handler as EventListener);
  }, []);

  const onHeaderMouseDown = (e: React.MouseEvent) => {
    draggingWindow.current = true;
    dragStart.current = { x: e.clientX, y: e.clientY };
    dragOffset.current = { x: position.x, y: position.y };
  };
  const onMouseMove = (e: React.MouseEvent) => {
    if (draggingWindow.current) {
      const dx = e.clientX - dragStart.current.x;
      const dy = e.clientY - dragStart.current.y;
      setPosition({ x: dragOffset.current.x + dx, y: dragOffset.current.y + dy });
    }
    if (panningImage.current) {
      const dx = e.clientX - panStart.current.x;
      const dy = e.clientY - panStart.current.y;
      setOffset({ x: panOffsetStart.current.x + dx, y: panOffsetStart.current.y + dy });
    }
  };
  const onMouseUp = () => { draggingWindow.current = false; panningImage.current = false; };

  const startPan = (e: React.MouseEvent) => {
    e.preventDefault();
    panningImage.current = true;
    panStart.current = { x: e.clientX, y: e.clientY };
    panOffsetStart.current = { x: offset.x, y: offset.y };
  };

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = -e.deltaY; // wheel up => zoom in
    const factor = delta > 0 ? 1.1 : 1 / 1.1;
    const newScale = Math.min(8, Math.max(0.2, scale * factor));
    setScale(newScale);
  };

  const zoomIn = () => setScale(s => Math.min(8, s * 1.2));
  const zoomOut = () => setScale(s => Math.max(0.2, s / 1.2));
  const resetView = () => { setScale(1); setOffset({ x: 0, y: 0 }); };
  const resetFilters = () => { setContrast(1); setBrightness(1); setSaturation(1); };
  const resetAll = () => { resetView(); resetFilters(); };

  const current = images[index];
  const filterStyle = `contrast(${contrast}) brightness(${brightness}) saturate(${saturation})`;

  if (!visible) return null;

  return (
    <div
      // Important: do not swallow events outside the window
      style={{ position: 'fixed', inset: 0, zIndex, pointerEvents: 'none' }}
    >
      {/* Floating window (receives pointer events) */}
      <div
        style={{
          position: 'absolute',
          left: position.x,
          top: position.y,
          width: size.w,
          height: size.h,
          background: 'linear-gradient(180deg, #121212 0%, #0f0f10 100%)',
          border: '1px solid #2a2a2a',
          borderRadius: 10,
          boxShadow: '0 12px 32px rgba(0,0,0,0.55)',
          overflow: 'hidden',
          pointerEvents: 'auto',
          display: 'flex',
          flexDirection: 'column'
        }}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      >
        {/* Header (draggable) */}
        <div
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            background: 'rgba(28,28,28,0.95)', color: '#e6e6e6', padding: '6px 8px', cursor: 'move', flex: '0 0 36px',
            borderBottom: '1px solid #222'
          }}
          onMouseDown={onHeaderMouseDown}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ fontWeight: 600, letterSpacing: 0.2 }}>Image Viewer</div>
            {current && (
              <div style={{ fontSize: 12, opacity: 0.7 }}>
                {current.naturalWidth}×{current.naturalHeight}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8, cursor: 'default' }} onMouseDown={e => e.stopPropagation()}>
            <ToolbarButton title="Zoom out" onClick={() => zoomOut()}>−</ToolbarButton>
            <ToolbarButton title="Reset zoom" onClick={() => resetView()}>100%</ToolbarButton>
            <ToolbarButton title="Zoom in" onClick={() => zoomIn()}>+</ToolbarButton>
            <ToolbarButton title="Settings" onClick={() => setShowSettings(s => !s)}>⚙️</ToolbarButton>
            <ToolbarButton title="Close" onClick={() => close()}>✕</ToolbarButton>
          </div>
        </div>

        {/* Content area */}
        <div style={{ position: 'relative', flex: '1 1 auto', background: '#000' }} onWheel={onWheel}>
          {/* Settings panel */}
          {showSettings && (
            <div
              style={{
                position: 'absolute', top: 8, right: 8, zIndex: 2,
                background: 'rgba(20,20,20,0.97)', color: '#eee', border: '1px solid #2a2a2a', borderRadius: 8,
                padding: 10, minWidth: 240, boxShadow: '0 8px 24px rgba(0,0,0,0.4)'
              }}
              onMouseDown={e => e.stopPropagation()}
            >
              <div style={{ fontWeight: 600, marginBottom: 8 }}>Adjustments</div>
              <label style={{ display: 'block', fontSize: 12, marginTop: 2 }}>Contrast: {contrast.toFixed(2)}</label>
              <input type="range" min={0.2} max={3} step={0.05} value={contrast} onChange={e => setContrast(parseFloat(e.target.value))} />
              <label style={{ display: 'block', fontSize: 12, marginTop: 6 }}>Brightness: {brightness.toFixed(2)}</label>
              <input type="range" min={0.2} max={2} step={0.05} value={brightness} onChange={e => setBrightness(parseFloat(e.target.value))} />
              <label style={{ display: 'block', fontSize: 12, marginTop: 6 }}>Saturation: {saturation.toFixed(2)}</label>
              <input type="range" min={0} max={3} step={0.05} value={saturation} onChange={e => setSaturation(parseFloat(e.target.value))} />
              <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                <ToolbarButton title="Reset filters" onClick={() => { setContrast(1); setBrightness(1); setSaturation(1); }}>Reset Filters</ToolbarButton>
                <ToolbarButton title="Reset all" onClick={() => { resetAll(); }}>Reset All</ToolbarButton>
              </div>
            </div>
          )}

          {/* Image stage */}
          <div
            style={{
              position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
              overflow: 'hidden', cursor: panningImage.current ? 'grabbing' : 'grab'
            }}
            onMouseDown={(e) => { if (e.button === 0) startPan(e); }}
          >
            {current && (
              <img
                src={current.url}
                alt={`image-${index}`}
                style={{
                  transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
                  transformOrigin: 'center center',
                  imageRendering: 'auto',
                  filter: filterStyle,
                  maxWidth: '100%',
                  maxHeight: '100%'
                }}
                draggable={false}
              />
            )}
          </div>

          {/* Pager */}
          {images.length > 1 && (
            <div style={{ position: 'absolute', bottom: 8, left: 8, display: 'flex', gap: 8, zIndex: 2 }}>
              <ToolbarButton title="Previous" onClick={() => setIndex(i => Math.max(0, i - 1))}>‹</ToolbarButton>
              <span style={{ color: '#fff', fontSize: 12, alignSelf: 'center' }}>{index + 1} / {images.length}</span>
              <ToolbarButton title="Next" onClick={() => setIndex(i => Math.min(images.length - 1, i + 1))}>›</ToolbarButton>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ImageOverlayViewer;
