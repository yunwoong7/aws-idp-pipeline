"use client";

import { motion } from "framer-motion";
import { 
  MessageCircle, 
  Sparkles,
  Zap,
  Image as ImageIcon,
} from "lucide-react";
import React from "react";

interface AnalysisHeroProps {
  onExampleClick?: (example: string) => void;
  title?: string;
  subtitle?: string;
  examples?: string[];
  onAttachClick?: () => void;
}

export function AnalysisHero({ 
  onExampleClick,
  title = "Talk to the Document Analysis AI",
  subtitle = "Ask me anything about your documents. I'll search, analyze and provide detailed answers with intelligent insights.",
  examples,
  onAttachClick
}: AnalysisHeroProps) {
  const features: { label: string; icon: React.ElementType; color: string }[] = [];

  return (
    <div className="relative w-full">

      {/* Main content */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="relative text-center py-16 px-4"
      >
        {/* Logo/Icon */}
        <motion.div
          initial={{ scale: 0, rotate: -180 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ 
            type: "spring",
            stiffness: 260,
            damping: 20,
            delay: 0.1 
          }}
          className="w-20 h-20 mx-auto mb-6 relative"
        >
          <div className="relative w-full h-full bg-white/5 border border-white/20 rounded-2xl flex items-center justify-center backdrop-blur-sm">
            <Sparkles className="h-10 w-10 text-white" />
          </div>
        </motion.div>

        {/* Title */}
        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="text-3xl md:text-4xl font-bold text-white mb-4"
        >
          {title}
        </motion.h1>

        {/* Subtitle */}
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="text-white/70 mb-12 max-w-2xl mx-auto text-lg leading-relaxed"
        >
          {subtitle}
        </motion.p>

        {/* Attach image button removed per request */}

        {/* Feature badges */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="flex items-center justify-center gap-6 mb-12 flex-wrap"
        >
          {features.map((feature, index) => (
            <motion.div
              key={feature.label}
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.5 + index * 0.1 }}
              whileHover={{ scale: 1.05 }}
              className="relative group"
            >
              <div className={`absolute inset-0 bg-gradient-to-r ${feature.color} rounded-xl blur-xl opacity-20 group-hover:opacity-40 transition-opacity`} />
              <div className="relative flex items-center gap-2 px-4 py-2 bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl">
                <feature.icon className="h-4 w-4 text-white/80" />
                <span className="text-sm font-medium text-white/80">{feature.label}</span>
              </div>
            </motion.div>
          ))}
        </motion.div>

        {/* Example prompts */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6 }}
          className="grid md:grid-cols-2 gap-3 max-w-3xl mx-auto"
        >
          {[
            { display: "Summarize the key content of this document", value: "이 문서의 핵심 내용을 요약해줘" },
            { display: "Find specific information in the document", value: "문서에서 특정 정보를 찾아줘" },
            { display: "Analyze data and provide insights", value: "데이터를 분석하고 인사이트를 제공해줘" },
            { display: "Analyze relationships between documents", value: "문서들 간의 관계를 분석해줘" }
          ].map((example, index) => (
            <motion.button
              key={index}
              onClick={() => onExampleClick?.(example.value)}
              className="group relative overflow-hidden"
              initial={{ opacity: 0, x: index % 2 === 0 ? -20 : 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.7 + index * 0.1 }}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              {/* Button content */}
              <div className="relative flex items-center gap-3 px-4 py-3 bg-white/[0.02] hover:bg-white/[0.05] border border-white/[0.08] rounded-lg text-left transition-all">
                <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center">
                  <MessageCircle className="w-4 h-4 text-white" />
                </div>
                <span className="text-sm text-white/70 group-hover:text-white/90 transition-colors">
                  {example.display}
                </span>
                
                {/* Hover arrow */}
                <div className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity">
                  <motion.div
                    animate={{ x: [0, 3, 0] }}
                    transition={{ duration: 1, repeat: Infinity }}
                  >
                    <Zap className="w-4 h-4 text-white" />
                  </motion.div>
                </div>
              </div>
            </motion.button>
          ))}
        </motion.div>

      </motion.div>
    </div>
  );
}