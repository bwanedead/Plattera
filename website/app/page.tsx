"use client";

import { useEffect, useRef, useState } from "react";
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

export default function Home() {
  const [activeImageIndex, setActiveImageIndex] = useState(0);
  const [reduceMotion, setReduceMotion] = useState(false);
  const traceRef = useRef<SVGPathElement | null>(null);

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
          <div className={styles.previewHeader}>
            <h2>Product preview</h2>
            <p>
              Import handwritten deeds, refine transcripts, and map descriptions
              with PLSS context.
            </p>
          </div>
          <div className={styles.previewFrame}>
            <svg
              className={styles.previewSvg}
              viewBox="0 0 1000 560"
              preserveAspectRatio="xMidYMid slice"
              aria-hidden="true"
            >
              <defs>
                <clipPath id="frameClip" clipPathUnits="userSpaceOnUse">
                  <path d="M0 0 L900 0 L1000 45 L1000 560 L80 560 L0 505 Z" />
                </clipPath>
              </defs>
              <foreignObject
                x="0"
                y="0"
                width="1000"
                height="560"
                clipPath="url(#frameClip)"
              >
                <div className={styles.previewViewport}>
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
              </foreignObject>
              <path
                className={styles.previewTrace}
                d="M0 0 L900 0 L1000 45 L1000 560 L80 560 L0 505 Z"
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
