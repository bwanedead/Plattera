import React from 'react';

interface StableAllotmentContainerProps {
  /**
   * Render-prop child: return the <Allotment> tree.
   * This will only be invoked once the container has a stable, non-zero rect.
   */
  children: () => React.ReactNode;
  debugLabel?: string;
}

export const StableAllotmentContainer: React.FC<StableAllotmentContainerProps> = ({
  children,
  debugLabel = 'allotment',
}) => {
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const [ready, setReady] = React.useState(false);

  React.useEffect(() => {
    let frame = 0;
    let lastSize: { w: number; h: number } | null = null;
    let stableCount = 0;
    let sawNonZero = false;
    let cancelled = false;

    const measure = () => {
      if (cancelled) return;
      const el = containerRef.current;
      if (el) {
        const r = el.getBoundingClientRect();
        const size = { w: r.width, h: r.height };

        // Log a few frames for diagnosis; appears in the frontend logs panel.
        console.error('📐 [STABLE-CONTAINER]', {
          debugLabel,
          frame,
          width: size.w,
          height: size.h,
        });

        if (size.w > 0 && size.h > 0) {
          sawNonZero = true;
          if (lastSize && lastSize.w === size.w && lastSize.h === size.h) {
            stableCount += 1;
          } else {
            stableCount = 1;
          }
          lastSize = size;
        } else {
          stableCount = 0;
        }

        if (!ready && stableCount >= 2) {
          setReady(true);
        }

        // Failsafe: if we've seen any non-zero size but never reached a
        // "stable" reading within the first ~10 frames, still proceed to
        // render children so Allotment can't be permanently gated off by
        // tiny layout jitter in WebView2.
        if (!ready && frame >= 9 && sawNonZero) {
          console.error('📐 [STABLE-CONTAINER FALLBACK]', {
            debugLabel,
            frame,
            lastSize,
          });
          setReady(true);
        }
      }

      frame += 1;
      if (!ready && frame < 10) {
        requestAnimationFrame(measure);
      }
    };

    requestAnimationFrame(measure);
    return () => {
      cancelled = true;
    };
  }, [ready, debugLabel]);

  return (
    <div
      ref={containerRef}
      style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}
    >
      {ready ? children() : null}
    </div>
  );
}


