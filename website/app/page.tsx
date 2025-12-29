"use client";

import { useEffect, useRef, useState, type TouchEvent } from "react";
import styles from "./page.module.css";

const previewImages = [
  {
    src: "/assets/images/screenshots/home_screen_demo_screen_shots/full_homescreen.png",
    alt: "Plattera dashboard overview",
  },
  {
    src: "/assets/images/screenshots/home_screen_demo_screen_shots/right_of_way_deed_handwritten.png",
    alt: "Handwritten right-of-way deed scan",
  },
  {
    src: "/assets/images/screenshots/home_screen_demo_screen_shots/handwritten_deed.png",
    alt: "Handwritten deed source document",
  },
  {
    src: "/assets/images/screenshots/home_screen_demo_screen_shots/right_of_way_deed_transcript.png",
    alt: "Transcript workspace for a right-of-way deed",
  },
  {
    src: "/assets/images/screenshots/home_screen_demo_screen_shots/image_to_text_full_workspace.png",
    alt: "Image-to-text workspace with transcription tools",
  },
  {
    src: "/assets/images/screenshots/home_screen_demo_screen_shots/map_workspace.png",
    alt: "Mapping workspace with PLSS context",
  },
  {
    src: "/assets/images/screenshots/home_screen_demo_screen_shots/polygon_viewer.png",
    alt: "Polygon viewer highlighting a traced parcel",
  },
];

const RAIL_PATH_D = "M0 0 L900 0 L1000 45 L1000 560 L80 560 L0 505 Z";

const buildRailMaskDataUrl = (pathD: string) => {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 560"><path fill="white" d="${pathD}"/></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
};

export default function Home() {
  const [activeImageIndex, setActiveImageIndex] = useState(0);
  const [reduceMotion, setReduceMotion] = useState(false);
  const traceRef = useRef<SVGPathElement | null>(null);
  const touchStartRef = useRef<{ x: number; y: number } | null>(null);
  const railMaskUrl = buildRailMaskDataUrl(RAIL_PATH_D);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    const prefersReducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    setReduceMotion(prefersReducedMotion);

    if (prefersReducedMotion) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      setActiveImageIndex((prev) => (prev + 1) % previewImages.length);
    }, 5200);

    return () => window.clearInterval(intervalId);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    const trace = traceRef.current;
    if (!trace) {
      return undefined;
    }

    if (reduceMotion) {
      trace.style.opacity = "0.7";
      trace.style.strokeDasharray = "none";
      trace.style.strokeDashoffset = "0";
      return undefined;
    }

    const length = trace.getTotalLength();
    const dashLength = Math.max(160, length * 0.2);
    trace.style.strokeDasharray = `0 ${length}`;
    trace.style.strokeDashoffset = "0";
    trace.style.opacity = "0";

    const runDuration = 7000;
    const cooldown = 3000;
    let startTime: number | null = null;
    let rafId = 0;

    const step = (timestamp: number) => {
      if (startTime === null) {
        startTime = timestamp;
      }

      const elapsed = timestamp - startTime;
      if (elapsed < runDuration) {
        const progress = elapsed / runDuration;
        if (progress < 0.08) {
          const reveal = progress / 0.08;
          const currentDash = dashLength * reveal;
          trace.style.strokeDasharray = `${currentDash} ${length}`;
          trace.style.strokeDashoffset = "0";
          trace.style.opacity = `${reveal}`;
        } else if (progress > 0.9) {
          const fade = (progress - 0.9) / 0.1;
          trace.style.strokeDasharray = `${dashLength} ${length}`;
          trace.style.strokeDashoffset = `${-(length + dashLength) * progress}`;
          trace.style.opacity = `${1 - fade}`;
        } else {
          trace.style.strokeDasharray = `${dashLength} ${length}`;
          trace.style.strokeDashoffset = `${-(length + dashLength) * progress}`;
          trace.style.opacity = "1";
        }
      } else if (elapsed < runDuration + cooldown) {
        trace.style.opacity = "0";
      } else {
        startTime = timestamp;
      }

      rafId = window.requestAnimationFrame(step);
    };

    rafId = window.requestAnimationFrame(step);
    return () => window.cancelAnimationFrame(rafId);
  }, [reduceMotion]);

  const handleTouchStart = (event: TouchEvent<HTMLDivElement>) => {
    const touch = event.touches[0];
    if (!touch) {
      return;
    }

    touchStartRef.current = { x: touch.clientX, y: touch.clientY };
  };

  const handleTouchEnd = (event: TouchEvent<HTMLDivElement>) => {
    const start = touchStartRef.current;
    touchStartRef.current = null;

    if (!start) {
      return;
    }

    const touch = event.changedTouches[0];
    if (!touch) {
      return;
    }

    const deltaX = touch.clientX - start.x;
    const deltaY = touch.clientY - start.y;
    const threshold = 40;

    if (Math.abs(deltaX) < threshold || Math.abs(deltaX) < Math.abs(deltaY)) {
      return;
    }

    setActiveImageIndex((prev) => {
      const nextIndex = deltaX > 0 ? prev - 1 : prev + 1;
      return (nextIndex + previewImages.length) % previewImages.length;
    });
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <a className={styles.brand} href="/">
          <span className={styles.brandName}>
            Plattera<span className={styles.dot}>.</span>
          </span>
        </a>
        <nav className={styles.nav}>
          <a href="/download">Download</a>
          <a href="/resources">Resources</a>
          <a href="/contact">Contact</a>
        </nav>
      </header>

      <main className={styles.hero}>
        <div className={styles.heroTitle}>
          <h1>
            Plattera<span className={styles.dot}>.</span>
          </h1>
          <a className={styles.primaryButton} href="/download">
            Get Plattera
          </a>
        </div>

        <section className={styles.preview}>
          <div className={styles.previewFrame}>
            <div
              className={styles.previewViewport}
              onTouchStart={handleTouchStart}
              onTouchEnd={handleTouchEnd}
              onTouchCancel={handleTouchEnd}
              style={{
                maskImage: `url("${railMaskUrl}")`,
                WebkitMaskImage: `url("${railMaskUrl}")`,
                maskRepeat: "no-repeat",
                WebkitMaskRepeat: "no-repeat",
                maskSize: "100% 100%",
                WebkitMaskSize: "100% 100%",
                maskPosition: "center",
                WebkitMaskPosition: "center",
              }}
            >
              <div
                className={styles.previewTrack}
                style={{
                  transform: `translateX(-${activeImageIndex * 100}%)`,
                }}
              >
                {previewImages.map((image) => (
                  <div className={styles.previewSlide} key={image.src}>
                    <img src={image.src} alt={image.alt} />
                  </div>
                ))}
              </div>
            </div>
            <svg
              className={styles.previewSvg}
              viewBox="0 0 1000 560"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              <path
                className={styles.previewTrace}
                d={RAIL_PATH_D}
                ref={traceRef}
                fill="none"
                stroke="currentColor"
                strokeWidth="1"
                vectorEffect="non-scaling-stroke"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <div className={styles.previewControls}>
              <div className={styles.previewDots} role="tablist">
                {previewImages.map((image, index) => (
                  <button
                    key={image.src}
                    type="button"
                    className={
                      index === activeImageIndex
                        ? styles.previewDotActive
                        : styles.previewDot
                    }
                    aria-label={`Show preview ${index + 1}`}
                    aria-selected={index === activeImageIndex}
                    onClick={() => setActiveImageIndex(index)}
                  />
                ))}
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
