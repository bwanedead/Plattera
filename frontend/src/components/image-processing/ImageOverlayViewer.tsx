import React, { useEffect, useRef, useState, useCallback } from 'react';

interface ImageOverlayViewerProps {
  zIndex?: number;
}

export const ImageOverlayViewer: React.FC<ImageOverlayViewerProps> = ({ zIndex = 9999 }) => {
  const [visible, setVisible] = useState(false);
  const [images, setImages] = useState<string[]>([]);
  const [index, setIndex] = useState(0);
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 100, y: 100 });
  const dragging = useRef(false);
  const last = useRef({ x: 0, y: 0 });

  const close = useCallback(() => setVisible(false), []);

  useEffect(() => {
    const handler = (e: Event) => {
      const ce = e as CustomEvent<{ images: string[]; initialIndex?: number }>;
      const imgs = Array.isArray(ce.detail?.images) ? ce.detail.images : [];
      if (imgs.length === 0) return;
      setImages(imgs);
      setIndex(Math.max(0, Math.min(imgs.length - 1, ce.detail?.initialIndex ?? 0)));
      setScale(1);
      setPosition({ x: 100, y: 100 });
      setVisible(true);
    };
    document.addEventListener('image-overlay:open', handler as EventListener);
    return () => document.removeEventListener('image-overlay:open', handler as EventListener);
  }, []);

  const onMouseDown = (e: React.MouseEvent) => {
    dragging.current = true;
    last.current = { x: e.clientX - position.x, y: e.clientY - position.y };
  };
  const onMouseMove = (e: React.MouseEvent) => {
    if (!dragging.current) return;
    setPosition({ x: e.clientX - last.current.x, y: e.clientY - last.current.y });
  };
  const onMouseUp = () => { dragging.current = false; };

  const zoomIn = () => setScale(s => Math.min(8, s * 1.2));
  const zoomOut = () => setScale(s => Math.max(0.2, s / 1.2));
  const reset = () => { setScale(1); setPosition({ x: 100, y: 100 }); };

  if (!visible) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex,
        pointerEvents: 'none'
      }}
    >
      <div
        style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.25)', pointerEvents: 'auto' }}
        onClick={close}
      />
      <div
        style={{
          position: 'absolute',
          left: position.x,
          top: position.y,
          width: 600,
          height: 400,
          background: '#111',
          border: '1px solid #333',
          borderRadius: 8,
          boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
          overflow: 'hidden',
          pointerEvents: 'auto'
        }}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: '#1c1c1c',
            color: '#eee',
            padding: '6px 8px',
            cursor: 'move'
          }}
          onMouseDown={onMouseDown}
        >
          <div>Image Viewer</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={(e) => { e.stopPropagation(); zoomOut(); }}>−</button>
            <button onClick={(e) => { e.stopPropagation(); reset(); }}>100%</button>
            <button onClick={(e) => { e.stopPropagation(); zoomIn(); }}>+</button>
            <button onClick={(e) => { e.stopPropagation(); close(); }}>✕</button>
          </div>
        </div>
        <div style={{ position: 'relative', width: '100%', height: 'calc(100% - 36px)', background: '#000' }}>
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <img
              src={images[index]}
              alt={`image-${index}`}
              style={{
                maxWidth: '100%',
                maxHeight: '100%',
                transform: `scale(${scale})`,
                transformOrigin: 'center center',
                imageRendering: 'auto'
              }}
              draggable={false}
            />
          </div>
          {images.length > 1 && (
            <div style={{ position: 'absolute', bottom: 8, left: 8, display: 'flex', gap: 8 }}>
              <button onClick={(e) => { e.stopPropagation(); setIndex(i => Math.max(0, i - 1)); }}>‹</button>
              <span style={{ color: '#fff' }}>{index + 1} / {images.length}</span>
              <button onClick={(e) => { e.stopPropagation(); setIndex(i => Math.min(images.length - 1, i + 1)); }}>›</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ImageOverlayViewer;
