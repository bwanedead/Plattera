import React, { useState } from 'react';
import { AssetsTray } from '../assets/AssetsTray';

type MenuTab = 'assets';

export const MenuTray: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<MenuTab>('assets');

  return (
    <>
      <button
        onClick={() => setOpen(prev => !prev)}
        style={{
          position: 'fixed',
          top: 14,
          left: 14,
          zIndex: 2200,
          background: '#0f172a',
          color: '#e2e8f0',
          border: '1px solid rgba(148, 163, 184, 0.4)',
          padding: '8px 12px',
          borderRadius: 8,
          cursor: 'pointer',
        }}
      >
        Menu
      </button>

      {open && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(2, 6, 23, 0.45)',
            zIndex: 2100,
          }}
          onClick={() => setOpen(false)}
        />
      )}

      <div
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          height: '100vh',
          width: 380,
          background: '#0b1220',
          color: '#f8fafc',
          borderRight: '1px solid rgba(148, 163, 184, 0.2)',
          boxShadow: open ? '18px 0 40px rgba(0,0,0,0.35)' : 'none',
          transform: open ? 'translateX(0)' : 'translateX(-100%)',
          transition: 'transform 0.2s ease',
          zIndex: 2150,
          padding: 16,
          pointerEvents: open ? 'auto' : 'none',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0 }}>Menu</h3>
          <button
            onClick={() => setOpen(false)}
            style={{
              background: 'transparent',
              border: '1px solid rgba(148, 163, 184, 0.4)',
              color: '#e2e8f0',
              padding: '6px 10px',
              borderRadius: 6,
              cursor: 'pointer',
            }}
          >
            Close
          </button>
        </div>

        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          <button
            onClick={() => setActiveTab('assets')}
            style={{
              background: activeTab === 'assets' ? '#1e293b' : 'transparent',
              color: '#e2e8f0',
              border: '1px solid rgba(148, 163, 184, 0.3)',
              padding: '6px 10px',
              borderRadius: 6,
              cursor: 'pointer',
            }}
          >
            Assets
          </button>
        </div>

        <div style={{ marginTop: 16 }}>
          {activeTab === 'assets' && <AssetsTray open={open} onClose={() => setOpen(false)} />}
        </div>
      </div>
    </>
  );
};
