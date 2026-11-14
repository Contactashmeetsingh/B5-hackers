"use client";

import { useEffect, useRef } from "react";

/** Decorative mathematical sculpture, not a molecular structure or model result. */
export function Helix() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let frame = 0;
    let visible = true;
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const draw = (time: number) => {
      const { width, height } = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      if (
        canvas.width !== Math.round(width * dpr) ||
        canvas.height !== Math.round(height * dpr)
      ) {
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      const scale = Math.min(width / 600, height / 650);
      const phase = motion.matches ? 0.4 : time * 0.00013;
      type Point = {
        x: number;
        y: number;
        z: number;
        side: number;
        radius: number;
      };
      const points: Point[][] = [[], []];
      for (let side = 0; side < 2; side++) {
        for (let i = 0; i < 93; i++) {
          const t = i / 92;
          const angle = t * Math.PI * 5.3 + phase + side * Math.PI;
          const taper = 0.63 + 0.37 * Math.sin(t * Math.PI);
          const x = Math.cos(angle) * 116 * taper;
          const y = (t - 0.5) * 605;
          const z = Math.sin(angle);
          const rotation = 0.44;
          points[side].push({
            x:
              width * 0.51 +
              (x * Math.cos(rotation) - y * Math.sin(rotation)) * scale,
            y:
              height * 0.49 +
              (x * Math.sin(rotation) + y * Math.cos(rotation)) * scale,
            z,
            side,
            radius: (5.2 + (z + 1) * 2.7) * scale,
          });
        }
      }
      // Fine base-pair rungs and continuous helical backbones.
      for (let i = 0; i < 93; i += 2) {
        const a = points[0][i],
          b = points[1][i];
        const gradient = ctx.createLinearGradient(a.x, a.y, b.x, b.y);
        gradient.addColorStop(0, "rgba(190,95,79,0.35)");
        gradient.addColorStop(0.5, "rgba(213,154,130,0.12)");
        gradient.addColorStop(1, "rgba(84,46,69,0.32)");
        ctx.strokeStyle = gradient;
        ctx.lineWidth = 1.4 * scale;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
        for (let n = 1; n < 7; n++) {
          const f = n / 7;
          ctx.fillStyle =
            n < 4 ? "rgba(201,122,102,0.34)" : "rgba(103,73,92,0.25)";
          ctx.beginPath();
          ctx.arc(
            a.x + (b.x - a.x) * f,
            a.y + (b.y - a.y) * f,
            2 * scale,
            0,
            Math.PI * 2,
          );
          ctx.fill();
        }
      }
      for (const strand of points) {
        ctx.beginPath();
        strand.forEach((p, i) =>
          i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y),
        );
        ctx.strokeStyle = strand[0].side
          ? "rgba(82,44,66,0.32)"
          : "rgba(210,112,83,0.4)";
        ctx.lineWidth = 3 * scale;
        ctx.stroke();
      }
      const sorted = points.flat().sort((a, b) => a.z - b.z);
      for (const p of sorted) {
        const opacity = 0.55 + (p.z + 1) * 0.225;
        const gradient = ctx.createRadialGradient(
          p.x - p.radius * 0.35,
          p.y - p.radius * 0.35,
          0,
          p.x,
          p.y,
          p.radius,
        );
        if (p.side) {
          gradient.addColorStop(0, `rgba(170,128,145,${opacity})`);
          gradient.addColorStop(0.5, `rgba(111,64,92,${opacity})`);
          gradient.addColorStop(1, `rgba(59,30,51,${opacity})`);
        } else {
          gradient.addColorStop(0, `rgba(255,215,182,${opacity})`);
          gradient.addColorStop(0.5, `rgba(237,151,117,${opacity})`);
          gradient.addColorStop(1, `rgba(183,82,66,${opacity})`);
        }
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fill();
      }
      if (!motion.matches && visible) frame = requestAnimationFrame(draw);
    };
    const restart = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(draw);
    };
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible) restart();
      else cancelAnimationFrame(frame);
    });
    observer.observe(canvas);
    const resize = new ResizeObserver(restart);
    resize.observe(canvas);
    motion.addEventListener("change", restart);
    restart();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      resize.disconnect();
      motion.removeEventListener("change", restart);
    };
  }, []);
  return <canvas ref={ref} className="helix-canvas" aria-hidden="true" />;
}
