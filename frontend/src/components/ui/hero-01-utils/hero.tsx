"use client";

import Image from "next/image";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ArrowRight, Shield, Clock, Heart } from "lucide-react";

export interface AvatarItem {
  src: string;
  alt: string;
}

export type AvatarList = AvatarItem[];

interface HeroSectionProps {
  badge?: string;
  title: string;
  titleHighlight?: string;
  description: string;
  primaryCta?: { text: string; href: string };
  secondaryCta?: { text: string; href: string };
  imageSrc: string;
  imageAlt: string;
  avatars?: AvatarList;
  avatarText?: string;
  stats?: { value: string; label: string }[];
  features?: { icon: React.ReactNode; text: string }[];
}

export default function HeroSection({
  badge = "AI-Powered Healthcare",
  title = "Your Family's Health,",
  titleHighlight = "Our Memory.",
  description = "From the doctor's desk to the pharmacy counter — every prescription, every history, one seamless journey. Powered by AI that remembers.",
  primaryCta = { text: "Start Consultation", href: "#consultation" },
  secondaryCta = { text: "How It Works", href: "#how-it-works" },
  imageSrc = "/hero-image.jpg",
  imageAlt = "Family Clinic & Pharmacy",
  avatars,
  avatarText = "Trusted by 2,000+ families",
  stats = [
    { value: "10K+", label: "Patients Served" },
    { value: "99.8%", label: "Accuracy Rate" },
    { value: "24/7", label: "AI Memory" },
  ],
  features = [
    { icon: <Shield className="h-4 w-4" />, text: "HIPAA Compliant" },
    { icon: <Clock className="h-4 w-4" />, text: "Instant History Recall" },
    { icon: <Heart className="h-4 w-4" />, text: "Family-First Care" },
  ],
}: HeroSectionProps) {
  return (
    <section className="relative overflow-hidden">
      {/* Background gradient */}
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -top-1/2 left-1/2 h-[800px] w-[800px] -translate-x-1/2 rounded-full bg-gradient-to-br from-teal-500/10 via-emerald-500/5 to-transparent blur-3xl" />
        <div className="absolute -bottom-1/4 right-0 h-[600px] w-[600px] rounded-full bg-gradient-to-tl from-cyan-500/8 via-teal-500/5 to-transparent blur-3xl" />
      </div>

      <div className="container mx-auto max-w-7xl px-4 py-16 md:px-6 md:py-24 lg:py-32">
        <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-16">
          {/* Left Content */}
          <div className="flex flex-col gap-6">
            {/* Badge */}
            <div className="inline-flex w-fit items-center gap-2 rounded-full border border-teal-500/20 bg-teal-500/5 px-4 py-1.5 text-sm font-medium text-teal-600 dark:text-teal-400">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-teal-400 opacity-75"></span>
                <span className="relative inline-flex h-2 w-2 rounded-full bg-teal-500"></span>
              </span>
              {badge}
            </div>

            {/* Title */}
            <h1 className="text-4xl font-bold tracking-tight sm:text-5xl md:text-6xl lg:text-7xl">
              {title}
              <br />
              <span className="bg-gradient-to-r from-teal-500 via-emerald-500 to-cyan-500 bg-clip-text text-transparent">
                {titleHighlight}
              </span>
            </h1>

            {/* Description */}
            <p className="max-w-lg text-lg leading-relaxed text-muted-foreground md:text-xl">
              {description}
            </p>

            {/* Feature Pills */}
            {features && (
              <div className="flex flex-wrap gap-3">
                {features.map((feature, i) => (
                  <div
                    key={i}
                    className="inline-flex items-center gap-2 rounded-lg border border-border/50 bg-card/50 px-3 py-1.5 text-sm text-muted-foreground backdrop-blur-sm"
                  >
                    <span className="text-teal-500">{feature.icon}</span>
                    {feature.text}
                  </div>
                ))}
              </div>
            )}

            {/* CTAs */}
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <Button
                asChild
                size="lg"
                className="group bg-gradient-to-r from-teal-500 to-emerald-600 text-white shadow-xl shadow-teal-500/25 transition-all duration-300 hover:shadow-teal-500/40 hover:scale-[1.02] px-8"
              >
                <Link href={primaryCta.href}>
                  {primaryCta.text}
                  <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
                </Link>
              </Button>
              <Button
                asChild
                variant="outline"
                size="lg"
                className="border-border/50 backdrop-blur-sm hover:bg-accent/50 px-8"
              >
                <Link href={secondaryCta.href}>{secondaryCta.text}</Link>
              </Button>
            </div>

            {/* Social Proof / Stats */}
            {stats && (
              <div className="mt-4 flex items-center gap-8 border-t border-border/40 pt-6">
                {stats.map((stat, i) => (
                  <div key={i} className="flex flex-col">
                    <span className="text-2xl font-bold tracking-tight bg-gradient-to-r from-teal-500 to-emerald-500 bg-clip-text text-transparent">
                      {stat.value}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {stat.label}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right Image */}
          <div className="relative">
            <div className="relative overflow-hidden rounded-2xl border border-border/40 bg-card/30 shadow-2xl shadow-teal-500/5 backdrop-blur-sm">
              <Image
                src={imageSrc}
                alt={imageAlt}
                width={800}
                height={500}
                className="h-auto w-full object-cover"
                priority
              />
              {/* Overlay gradient */}
              <div className="absolute inset-0 bg-gradient-to-t from-background/20 via-transparent to-transparent" />
            </div>

            {/* Floating cards */}
            <div className="absolute -bottom-4 -left-4 rounded-xl border border-border/40 bg-card/90 px-4 py-3 shadow-lg backdrop-blur-md md:-left-8">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-teal-500 to-emerald-600">
                  <Shield className="h-5 w-5 text-white" />
                </div>
                <div>
                  <p className="text-sm font-semibold">Secure & Private</p>
                  <p className="text-xs text-muted-foreground">End-to-end encrypted</p>
                </div>
              </div>
            </div>

            <div className="absolute -right-4 -top-4 rounded-xl border border-border/40 bg-card/90 px-4 py-3 shadow-lg backdrop-blur-md md:-right-8">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-500 to-teal-600">
                  <Heart className="h-5 w-5 text-white" />
                </div>
                <div>
                  <p className="text-sm font-semibold">AI Memory</p>
                  <p className="text-xs text-muted-foreground">Powered by Hindsight</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
