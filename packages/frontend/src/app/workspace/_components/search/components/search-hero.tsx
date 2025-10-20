"use client";

import { motion } from "framer-motion";
import { Search } from "lucide-react";
import React from "react";

interface SearchHeroProps {
  onExampleClick?: (example: string) => void;
  title?: string;
  subtitle?: string;
  examples?: string[];
}

export function SearchHero({
  onExampleClick,
  title = "AI-Powered Document Search",
  subtitle = "Search across all your documents with advanced AI. Find information instantly with semantic understanding and intelligent filtering.",
  examples
}: SearchHeroProps) {

  return (
    <div className="relative w-full min-h-[60vh] flex items-center justify-center">
      {/* Main content */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="relative text-center py-12 px-4 max-w-5xl mx-auto"
      >
        {/* Logo/Icon with glow effect */}
        <motion.div
          initial={{ scale: 0, rotate: -180 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{
            type: "spring",
            stiffness: 200,
            damping: 15,
            delay: 0.1
          }}
          className="w-24 h-24 mx-auto mb-8 relative"
        >
          <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/30 to-purple-500/30 rounded-3xl blur-2xl" />
          <div className="relative w-full h-full bg-gradient-to-br from-white/10 to-white/5 border border-white/20 rounded-3xl flex items-center justify-center backdrop-blur-xl shadow-2xl">
            <Search className="h-12 w-12 text-white drop-shadow-lg" />
            <motion.div
              className="absolute inset-0 rounded-3xl"
              animate={{
                boxShadow: [
                  "0 0 20px rgba(6, 182, 212, 0.3)",
                  "0 0 40px rgba(168, 85, 247, 0.3)",
                  "0 0 20px rgba(6, 182, 212, 0.3)",
                ]
              }}
              transition={{
                duration: 3,
                repeat: Infinity,
                ease: "easeInOut"
              }}
            />
          </div>
        </motion.div>

        {/* Title with gradient */}
        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="text-4xl md:text-5xl lg:text-6xl font-bold mb-6 bg-gradient-to-r from-white via-cyan-200 to-purple-200 bg-clip-text text-transparent leading-tight"
        >
          {title}
        </motion.h1>

        {/* Subtitle */}
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="text-white/60 max-w-2xl mx-auto text-lg md:text-xl leading-relaxed"
        >
          {subtitle}
        </motion.p>

      </motion.div>
    </div>
  );
}
