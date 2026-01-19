import React, { useState } from 'react';
import { AssetsTray } from '../assets/AssetsTray';
import { RagIndexPanel } from '../rag-index/RagIndexPanel';

type MenuTab = 'assets' | 'rag-index';

interface MenuTrayProps {
  visible?: boolean;
}

export const MenuTray: React.FC<MenuTrayProps> = ({ visible = true }) => {
  const [open, setOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<MenuTab>('assets');

  if (!visible) return null;

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
          borderRight: '1px solid rgba(148, 163, 184, 0.1)',
          boxShadow: open ? '0 25px 50px -12px rgba(0, 0, 0, 0.5)' : 'none',
          transform: open ? 'translateX(0)' : 'translateX(-100%)',
          transition: 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          zIndex: 2150,
          padding: '24px',
          pointerEvents: open ? 'auto' : 'none',
          display: 'flex',
          flexDirection: 'column',
          backdropFilter: 'blur(12px)'
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
          <h3 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 600, letterSpacing: '-0.025em', color: '#f8fafc' }}>Menu</h3>
          <button
            onClick={() => setOpen(false)}
            style={{
              background: 'transparent',
              border: '1px solid rgba(148, 163, 184, 0.2)',
              color: '#94a3b8',
              padding: '6px 12px',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '0.875rem',
              transition: 'all 0.2s',
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.borderColor = 'rgba(148, 163, 184, 0.4)';
              e.currentTarget.style.color = '#e2e8f0';
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.borderColor = 'rgba(148, 163, 184, 0.2)';
              e.currentTarget.style.color = '#94a3b8';
            }}
          >
            Close
          </button>
        </div>

        <div style={{ display: 'flex', gap: '8px', marginBottom: '24px', borderBottom: '1px solid rgba(148, 163, 184, 0.1)', paddingBottom: '12px' }}>
          <button
            onClick={() => setActiveTab('assets')}
            style={{
              background: activeTab === 'assets' ? '#1e293b' : 'transparent',
              color: activeTab === 'assets' ? '#f8fafc' : '#94a3b8',
              border: 'none',
              padding: '8px 16px',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '0.9rem',
              fontWeight: 500,
              transition: 'all 0.2s',
            }}
            onMouseOver={(e) => {
              if (activeTab !== 'assets') e.currentTarget.style.color = '#e2e8f0';
            }}
            onMouseOut={(e) => {
              if (activeTab !== 'assets') e.currentTarget.style.color = '#94a3b8';
            }}
          >
            Assets
          </button>
          <button
            onClick={() => setActiveTab('rag-index')}
            style={{
              background: activeTab === 'rag-index' ? '#1e293b' : 'transparent',
              color: activeTab === 'rag-index' ? '#f8fafc' : '#94a3b8',
              border: 'none',
              padding: '8px 16px',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '0.9rem',
              fontWeight: 500,
              transition: 'all 0.2s',
            }}
            onMouseOver={(e) => {
              if (activeTab !== 'rag-index') e.currentTarget.style.color = '#e2e8f0';
            }}
            onMouseOut={(e) => {
              if (activeTab !== 'rag-index') e.currentTarget.style.color = '#94a3b8';
            }}
          >
            RAG Index
          </button>
        </div>

        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {activeTab === 'assets' && <AssetsTray open={open} onClose={() => setOpen(false)} />}
          {activeTab === 'rag-index' && <RagIndexPanel />}
        </div>
      </div>
    </>
  );
};
