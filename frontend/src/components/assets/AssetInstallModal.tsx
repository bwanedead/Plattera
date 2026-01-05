import React from 'react';
import { createPortal } from 'react-dom';

interface AssetInstallModalProps {
  open: boolean;
  assetName: string;
  onConfirm: () => void;
  onClose: () => void;
  isInstalling: boolean;
}

export const AssetInstallModal: React.FC<AssetInstallModalProps> = ({
  open,
  assetName,
  onConfirm,
  onClose,
  isInstalling,
}) => {
  if (!open) return null;

  return createPortal(
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1200,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: 420,
          background: '#111',
          color: '#f9fafb',
          borderRadius: 10,
          padding: 20,
          border: '1px solid rgba(255,255,255,0.08)',
          boxShadow: '0 24px 60px rgba(0,0,0,0.5)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ marginTop: 0, marginBottom: 8 }}>Install asset</h3>
        <p style={{ marginTop: 0, color: '#cbd5f5' }}>
          Download and install <strong>{assetName}</strong> for offline use.
        </p>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
          <button
            onClick={onClose}
            style={{
              padding: '8px 14px',
              background: 'transparent',
              color: '#e2e8f0',
              border: '1px solid rgba(148, 163, 184, 0.4)',
              borderRadius: 6,
              cursor: 'pointer',
            }}
          >
            Close
          </button>
          <button
            onClick={onConfirm}
            disabled={isInstalling}
            style={{
              padding: '8px 14px',
              background: isInstalling ? '#1f2937' : '#4f46e5',
              color: '#fff',
              border: 'none',
              borderRadius: 6,
              cursor: isInstalling ? 'default' : 'pointer',
            }}
          >
            {isInstalling ? 'Installing…' : 'Install'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
};
