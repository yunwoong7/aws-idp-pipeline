"use client";

import * as React from "react";

interface ChatBackgroundProps {
  className?: string;
}

export const ChatBackground = ({ className = "" }: ChatBackgroundProps) => {
  return (
    <div className={`absolute inset-0 w-full h-full overflow-hidden pointer-events-none ${className}`}>
      {/* Gradient Effects */}
      <div className="flex gap-[10rem] rotate-[-20deg] absolute top-[-40rem] right-[-30rem] z-[0] blur-[4rem] skew-[-40deg] opacity-30">
        <div className="w-[10rem] h-[20rem] bg-gradient-to-b from-cyan-400 to-sky-600"></div>
        <div className="w-[10rem] h-[20rem] bg-gradient-to-b from-cyan-400 to-sky-600"></div>
        <div className="w-[10rem] h-[20rem] bg-gradient-to-b from-cyan-400 to-sky-600"></div>
      </div>
      <div className="flex gap-[10rem] rotate-[-20deg] absolute top-[-50rem] right-[-50rem] z-[0] blur-[4rem] skew-[-40deg] opacity-20">
        <div className="w-[10rem] h-[20rem] bg-gradient-to-b from-emerald-400 to-cyan-600"></div>
        <div className="w-[10rem] h-[20rem] bg-gradient-to-b from-emerald-400 to-cyan-600"></div>
        <div className="w-[10rem] h-[20rem] bg-gradient-to-b from-emerald-400 to-cyan-600"></div>
      </div>
      <div className="flex gap-[10rem] rotate-[-20deg] absolute top-[-60rem] right-[-60rem] z-[0] blur-[4rem] skew-[-40deg] opacity-25">
        <div className="w-[10rem] h-[30rem] bg-gradient-to-b from-sky-400 to-cyan-600"></div>
        <div className="w-[10rem] h-[30rem] bg-gradient-to-b from-sky-400 to-cyan-600"></div>
        <div className="w-[10rem] h-[30rem] bg-gradient-to-b from-sky-400 to-cyan-600"></div>
      </div>
    </div>
  );
};