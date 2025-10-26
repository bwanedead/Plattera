import React from 'react';

interface ConfirmDialogProps {
  open: boolean;
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  open,
  title = 'Confirm',
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onConfirm,
  onCancel
}) => {
  if (!open) return null;
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 10000, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(2,6,23,0.6)' }}>
      <div style={{ background: '#0b1220', color: '#e5e7eb', border: '1px solid #1f2937', borderRadius: 10, padding: 16, width: 420, boxShadow: '0 10px 30px rgba(0,0,0,0.4)' }}>
        {title && <div style={{ fontWeight: 700, marginBottom: 8 }}>{title}</div>}
        <div style={{ fontSize: 14, color: '#cbd5e1', lineHeight: 1.4 }}>{message}</div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 14 }}>
          <button onClick={onCancel} style={{ background: 'transparent', color: '#93c5fd', border: '1px solid #334155', padding: '6px 10px', borderRadius: 6, fontSize: 13 }}> {cancelLabel} </button>
          <button onClick={onConfirm} style={{ background: '#7f1d1d', color: '#fde68a', border: '1px solid #991b1b', padding: '6px 10px', borderRadius: 6, fontSize: 13 }}> {confirmLabel} </button>
        </div>
      </div>
    </div>
  );
};


