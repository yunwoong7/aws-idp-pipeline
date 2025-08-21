"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { MoveRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useBranding } from "@/contexts/branding-context";

function Hero() {
  const router = useRouter();
  const { settings, loading } = useBranding();
  const [titleNumber, setTitleNumber] = useState(0);
  const titles = useMemo(
    () => ["documents", "videos", "audio", "images"],
    []
  );

  useEffect(() => {
    const timeoutId = setTimeout(() => {
      if (titleNumber === titles.length - 1) {
        setTitleNumber(0);
      } else {
        setTitleNumber(titleNumber + 1);
      }
    }, 2000);
    return () => clearTimeout(timeoutId);
  }, [titleNumber, titles]);

      return (
        <div className="w-full min-h-screen bg-black">
            <div className="absolute inset-0 bg-gradient-to-b from-cyan-500/5 via-transparent to-sky-500/8 blur-3xl" />

            <div className="container mx-auto relative z-10">
                <div className="flex gap-8 py-20 lg:py-40 items-center justify-center flex-col min-h-screen">
                    <div className="flex gap-6 flex-col">
                        <h1 className="text-5xl md:text-7xl max-w-6xl tracking-tighter text-center font-regular">
                            <span className="text-white mb-4 block">{settings.companyName || 'AWS IDP'} for</span>
                            <div className="relative h-28 md:h-36 w-full flex justify-center items-center overflow-visible">
                                <div className="relative w-full max-w-2xl h-full flex justify-center items-center">
                                    {titles.map((title, index) => (
                                        <motion.span
                                            key={index}
                                            className="absolute font-bold bg-clip-text text-transparent bg-gradient-to-r from-cyan-300 via-sky-300 to-cyan-400 text-5xl md:text-7xl whitespace-nowrap"
                                            initial={{ opacity: 0, y: 100 }}
                                            transition={{ type: "spring", stiffness: 50, damping: 20 }}
                                            animate={
                                                titleNumber === index
                                                    ? {
                                                        y: 0,
                                                        opacity: 1,
                                                        scale: 1,
                                                    }
                                                    : {
                                                        y: titleNumber > index ? -100 : 100,
                                                        opacity: 0,
                                                        scale: 0.8,
                                                    }
                                            }
                                        >
                                            {title}
                                        </motion.span>
                                    ))}
                                </div>
                            </div>
                        </h1>

                        <p className="text-lg md:text-xl leading-relaxed tracking-tight text-white/70 max-w-4xl text-center">
                            {!loading && settings.description ? (
                                settings.description.split('\n').map((line, index, array) => (
                                    <span key={index}>
                                        {line}
                                        {index < array.length - 1 && <br />}
                                    </span>
                                ))
                            ) : (
                                settings.description || "Transform Documents into Actionable Insights"
                            )}
                        </p>
                    </div>
                    <div className="flex justify-center mt-8">
                        <Button
                            size="lg"
                            className="gap-4 bg-gradient-to-b from-emerald-600 to-cyan-700 hover:from-emerald-700 hover:to-cyan-800 text-white border border-white/10 hover:border-white/20 px-8 py-4 text-lg font-semibold rounded-xl shadow-[0_8px_16px_rgb(0_0_0/0.4)] hover:shadow-[0_12px_24px_rgb(0_0_0/0.6)] transition-all duration-300 transform hover:scale-105"
                            onClick={() => router.push('/studio')}
                        >
                            Get Started <MoveRight className="w-5 h-5" />
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    );
}

export { Hero };