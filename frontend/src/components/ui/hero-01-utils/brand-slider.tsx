"use client";

import { useEffect, useRef, useState } from "react";
import {
  Stethoscope,
  Pill,
  Brain,
  ShieldCheck,
  Microscope,
  HeartPulse,
} from "lucide-react";

export interface BrandItem {
  name: string;
  icon: React.ReactNode;
}

export type BrandList = BrandItem[];

interface BrandSliderProps {
  brands?: BrandList;
  speed?: number;
  title?: string;
}

const defaultBrands: BrandList = [
  { name: "Smart Diagnosis", icon: <Stethoscope className="h-5 w-5" /> },
  { name: "Digital Prescriptions", icon: <Pill className="h-5 w-5" /> },
  { name: "AI Memory Engine", icon: <Brain className="h-5 w-5" /> },
  { name: "HIPAA Secure", icon: <ShieldCheck className="h-5 w-5" /> },
  { name: "Lab Integration", icon: <Microscope className="h-5 w-5" /> },
  { name: "Vitals Tracking", icon: <HeartPulse className="h-5 w-5" /> },
];

export default function BrandSlider({
  brands = defaultBrands,
  speed = 30,
  title = "Powered by cutting-edge healthcare technology",
}: BrandSliderProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [isPaused, setIsPaused] = useState(false);

  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;

    let animationId: number;
    let position = 0;

    const animate = () => {
      if (!isPaused) {
        position -= 0.5;
        const firstChild = container.firstElementChild as HTMLElement;
        if (firstChild && Math.abs(position) >= firstChild.offsetWidth) {
          position = 0;
          container.appendChild(firstChild);
        }
        container.style.transform = `translateX(${position}px)`;
      }
      animationId = requestAnimationFrame(animate);
    };

    animationId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationId);
  }, [isPaused, speed]);

  // Double the brands for seamless loop
  const displayBrands = [...brands, ...brands, ...brands];

  return (
    <section className="relative border-y border-border/30 bg-card/30 py-8 backdrop-blur-sm">
      <div className="container mx-auto max-w-7xl px-4 md:px-6">
        <p className="mb-6 text-center text-sm font-medium uppercase tracking-wider text-muted-foreground">
          {title}
        </p>
      </div>
      <div
        className="overflow-hidden"
        onMouseEnter={() => setIsPaused(true)}
        onMouseLeave={() => setIsPaused(false)}
      >
        <div ref={scrollRef} className="flex gap-12 whitespace-nowrap px-4">
          {displayBrands.map((brand, i) => (
            <div
              key={`${brand.name}-${i}`}
              className="flex shrink-0 items-center gap-3 rounded-lg border border-border/30 bg-background/50 px-5 py-2.5 text-muted-foreground transition-colors hover:border-teal-500/30 hover:text-teal-500"
            >
              {brand.icon}
              <span className="text-sm font-medium">{brand.name}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
