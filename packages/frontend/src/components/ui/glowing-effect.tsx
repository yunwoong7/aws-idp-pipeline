"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface GlowingEffectProps {
  variant?: "default" | "blue" | "green" | "red" | "purple";
  proximity?: number;
  spread?: number;
  borderWidth?: number;
  movementDuration?: number;
  className?: string;
  disabled?: boolean;
  children?: React.ReactNode;
}

export function GlowingEffect({
  variant = "default",
  proximity = 60,
  spread = 20,
  borderWidth = 1,
  movementDuration = 1.5,
  className,
  disabled = false,
  children
}: GlowingEffectProps) {
  if (disabled) return children ? <>{children}</> : null;

  const getVariantColors = () => {
    switch (variant) {
      case "blue":
        return "from-blue-400/50 to-blue-600/50";
      case "green":
        return "from-emerald-400/50 to-emerald-600/50";
      case "red":
        return "from-red-400/50 to-red-600/50";
      case "purple":
        return "from-purple-400/50 to-purple-600/50";
      default:
        return "from-slate-400/30 to-slate-600/30";
    }
  };

  return (
    <div 
      className={cn(
        "absolute inset-0 rounded-lg overflow-hidden pointer-events-none",
        className
      )}
      style={{
        borderWidth: `${borderWidth}px`,
        borderStyle: "solid",
        borderImage: `linear-gradient(45deg, ${getVariantColors()}) 1`,
        background: `linear-gradient(45deg, ${getVariantColors()})`,
        backgroundSize: "200% 200%",
        animation: `glowing-move ${movementDuration}s ease-in-out infinite alternate`,
        opacity: 0.6
      }}
    >
      <style jsx>{`
        @keyframes glowing-move {
          0% {
            background-position: 0% 50%;
          }
          100% {
            background-position: 100% 50%;
          }
        }
      `}</style>
      {children}
    </div>
  );
} 