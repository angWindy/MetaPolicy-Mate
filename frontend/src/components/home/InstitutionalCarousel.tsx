"use client";

import Image from "next/image";
import { ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import { useEffect, useState } from "react";

import styles from "./InstitutionalCarousel.module.css";

const slides = [
  {
    src: "/images/institutional/student-policy-showcase.jpg",
    alt: "Sinh viên cùng trao đổi tài liệu học tập",
  },
  {
    src: "/images/institutional/engineering-lab.jpg",
    alt: "Sinh viên học tập trong phòng thực hành kỹ thuật",
  },
  {
    src: "/images/institutional/graduation.jpg",
    alt: "Sinh viên trong lễ tốt nghiệp",
  },
] as const;

function wrapIndex(index: number) {
  return (index + slides.length) % slides.length;
}

export function InstitutionalCarousel() {
  const reduceMotion = true; // safe fallback when motion package is not installed
  const [activeIndex, setActiveIndex] = useState(0);
  const [paused, setPaused] = useState(false);

  function moveTo(index: number) {
    setActiveIndex(wrapIndex(index));
  }

  useEffect(() => {
    if (paused || reduceMotion) return;

    const timer = window.setInterval(() => {
      setActiveIndex((current) => wrapIndex(current + 1));
    }, 6500);

    return () => window.clearInterval(timer);
  }, [paused, reduceMotion]);

  const activeSlide = slides[activeIndex];

  return (
    <div className={styles.carousel} role="region" aria-label="Hình ảnh trường">
      <div className={styles.viewport}>
        <Image
          key={activeIndex}
          src={activeSlide.src}
          alt={activeSlide.alt}
          fill
          priority
          sizes="(max-width: 720px) 100vw, 720px"
          className={styles.image}
        />
      </div>
      <div className={styles.controls}>
        <button
          type="button"
          className={styles.iconButton}
          aria-label="Ảnh trước"
          onClick={() => moveTo(activeIndex - 1)}
        >
          <ChevronLeft size={16} aria-hidden="true" />
        </button>
        <button
          type="button"
          className={styles.iconButton}
          aria-label={paused ? "Tiếp tục" : "Tạm dừng"}
          onClick={() => setPaused((p) => !p)}
        >
          {paused ? <Play size={16} aria-hidden="true" /> : <Pause size={16} aria-hidden="true" />}
        </button>
        <button
          type="button"
          className={styles.iconButton}
          aria-label="Ảnh sau"
          onClick={() => moveTo(activeIndex + 1)}
        >
          <ChevronRight size={16} aria-hidden="true" />
        </button>
      </div>
      <div className={styles.dots} role="tablist" aria-label="Chọn ảnh">
        {slides.map((slide, index) => {
          const active = index === activeIndex;
          return (
            <button
              key={slide.src}
              role="tab"
              type="button"
              aria-selected={active}
              aria-label={`Slide ${index + 1}`}
              className={`${styles.dot} ${active ? styles.dotActive : ""}`}
              onClick={() => moveTo(index)}
            />
          );
        })}
      </div>
    </div>
  );
}
