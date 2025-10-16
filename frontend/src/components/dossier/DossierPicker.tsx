import React, { useEffect, useRef, useState } from 'react';
import { dossierHighlightBus } from '../../services/dossier/dossierHighlightBus';

interface DossierOption {
  id: string;
  title?: string;
  name?: string;
}

interface DossierPickerProps {
  dossiers: DossierOption[];
  value: string | null;
  onChange: (dossierId: string | null) => void;
  className?: string;
}

export const DossierPicker: React.FC<DossierPickerProps> = ({ dossiers, value, onChange, className }) => {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const handleDocClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        dossierHighlightBus.emit(null);
      }
    };
    document.addEventListener('click', handleDocClick);
    return () => document.removeEventListener('click', handleDocClick);
  }, []);

  // Debug: Log when dossiers change
  useEffect(() => {
    console.log('📋 DossierPicker: dossiers prop updated:', dossiers);
    if (value) {
      const selectedDossier = dossiers.find(d => d.id === value);
      console.log('📋 DossierPicker: selected dossier:', selectedDossier);
    }
  }, [dossiers, value]);

  const selectedLabel = value
    ? (dossiers.find(d => d.id === value)?.title || dossiers.find(d => d.id === value)?.name || value)
    : 'Auto-create new dossier';

  return (
    <div ref={containerRef} className={className || ''} style={{ position: 'relative' }}>
      <button
        type="button"
        className="dossier-picker-trigger"
        onClick={() => setOpen(prev => !prev)}
      >
        {selectedLabel}
      </button>

      {open && (
        <div className="dossier-picker-menu" style={{
          position: 'absolute',
          zIndex: 20,
          left: 0,
          right: 0,
          marginTop: 6,
          background: 'var(--bg-primary)',
          border: '1px solid var(--border-color)',
          borderRadius: 6,
          boxShadow: '0 6px 20px rgba(0,0,0,0.25)'
        }}
          onMouseLeave={() => dossierHighlightBus.emit(null)}
        >
          <div
            className="dossier-picker-item"
            onMouseEnter={() => dossierHighlightBus.emit(null)}
            onClick={() => { onChange(null); setOpen(false); }}
            style={{ padding: '8px 10px', cursor: 'pointer' }}
          >
            Auto-create new dossier
          </div>
          <div style={{ borderTop: '1px solid var(--border-color)' }} />
          {dossiers.map(d => (
            <div
              key={d.id}
              className="dossier-picker-item"
              onMouseEnter={() => dossierHighlightBus.emit(d.id)}
              onClick={() => { onChange(d.id); setOpen(false); dossierHighlightBus.emit(null); }}
              style={{
                padding: '8px 10px',
                cursor: 'pointer',
                // Slightly stronger visual affordances on hover while preserving existing behavior
                transition: 'background 120ms ease, transform 80ms ease',
              }}
              onMouseOver={(e) => {
                (e.currentTarget as HTMLDivElement).style.background = 'var(--hover-bg, rgba(120,120,120,0.12))';
                (e.currentTarget as HTMLDivElement).style.transform = 'translateX(2px)';
              }}
              onMouseOut={(e) => {
                (e.currentTarget as HTMLDivElement).style.background = '';
                (e.currentTarget as HTMLDivElement).style.transform = '';
              }}
            >
              {d.title || d.name || d.id}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};


