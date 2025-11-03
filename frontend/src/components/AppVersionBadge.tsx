import React, { useEffect, useState } from 'react'

export const AppVersionBadge: React.FC = () => {
  const [version, setVersion] = useState<string>('dev')

  useEffect(() => {
    (async () => {
      try {
        // Try Tauri app version first (works in desktop, throws in web)
        const { getVersion } = await import('@tauri-apps/api/app')
        const v = await getVersion()
        setVersion(v)
        return
      } catch {}
      // Web/dev fallback via env
      const envVer = (process as any)?.env?.NEXT_PUBLIC_APP_VERSION
      setVersion(envVer ? String(envVer) : 'dev')
    })()
  }, [])

  return (
    <span
      style={{
        position: 'fixed',
        left: 12,
        bottom: 12,
        opacity: 0.7,
        fontSize: 12,
        padding: '4px 8px',
        background: 'rgba(255,255,255,0.06)',
        border: '1px solid rgba(255,255,255,0.12)',
        borderRadius: 4,
        pointerEvents: 'none',
        zIndex: 9999
      }}
    >
      v{version}
    </span>
  )
}


