import React from 'react';

interface ToolTrayProps {
  children: React.ReactNode;
  topRem?: number; // vertical offset in rem under the Copy button
  leftPx?: number; // horizontal offset inside the viewer
  zIndex?: number; // layering between text and overlays
}

export const ToolTray: React.FC<ToolTrayProps> = ({ children, topRem = 7.5, leftPx = 8, zIndex = 3000 }) => {
  return (
    <div
      className="tool-tray"
      style={{
        position: 'absolute',
        top: `${topRem}rem`,
        left: leftPx,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        gap: 6,
        zIndex
      }}
    >
      {children}
    </div>
  );
};

export default ToolTray;

