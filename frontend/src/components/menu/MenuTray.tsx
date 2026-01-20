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
          background: '#1c1f23',
          color: '#f3f4f6',
          border: '1px solid #2c3137',
          padding: '6px 10px',
          borderRadius: 10,
          cursor: 'pointer',
          fontSize: '0.8rem',
          letterSpacing: '0.02em'
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
          minWidth: 320,
          maxWidth: 560,
          background: '#15171a',
          color: '#f3f4f6',
          borderRight: '1px solid rgba(255, 255, 255, 0.06)',
          boxShadow: open ? '0 30px 60px rgba(0, 0, 0, 0.45)' : 'none',
          transform: open ? 'translateX(0)' : 'translateX(-100%)',
          transition: 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          zIndex: 2150,
          padding: '18px',
          pointerEvents: open ? 'auto' : 'none',
          display: 'flex',
          flexDirection: 'column',
          backdropFilter: 'blur(8px)',
          resize: 'horizontal',
          overflow: 'auto'
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', marginBottom: '16px' }}>
          <button
            onClick={() => setOpen(false)}
            style={{
              background: 'transparent',
              border: '1px solid #2c3137',
              color: '#9ca3af',
              padding: '4px 10px',
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '0.75rem',
              transition: 'all 0.2s',
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.borderColor = '#3a3f46';
              e.currentTarget.style.color = '#f3f4f6';
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.borderColor = '#2c3137';
              e.currentTarget.style.color = '#9ca3af';
            }}
          >
            Close
          </button>
        </div>

        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', borderBottom: '1px solid rgba(255, 255, 255, 0.06)', paddingBottom: '10px' }}>
          <button
            onClick={() => setActiveTab('assets')}
            style={{
              background: activeTab === 'assets' ? '#1f2328' : 'transparent',
              color: activeTab === 'assets' ? '#f9fafb' : '#9ca3af',
              border: 'none',
              padding: '6px 12px',
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '0.8rem',
              fontWeight: 500,
              transition: 'all 0.2s',
            }}
            onMouseOver={(e) => {
              if (activeTab !== 'assets') e.currentTarget.style.color = '#f3f4f6';
            }}
            onMouseOut={(e) => {
              if (activeTab !== 'assets') e.currentTarget.style.color = '#9ca3af';
            }}
          >
            Assets
          </button>
          <button
            onClick={() => setActiveTab('rag-index')}
            style={{
              background: activeTab === 'rag-index' ? '#1f2328' : 'transparent',
              color: activeTab === 'rag-index' ? '#f9fafb' : '#9ca3af',
              border: 'none',
              padding: '6px 12px',
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '0.8rem',
              fontWeight: 500,
              transition: 'all 0.2s',
            }}
            onMouseOver={(e) => {
              if (activeTab !== 'rag-index') e.currentTarget.style.color = '#f3f4f6';
            }}
            onMouseOut={(e) => {
              if (activeTab !== 'rag-index') e.currentTarget.style.color = '#9ca3af';
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
