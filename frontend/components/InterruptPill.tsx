"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Square } from "lucide-react";
import { useStore } from "@/lib/store";

export default function InterruptPill() {
  const isStreaming = useStore((s) => s.isStreaming);
  const isPlaying = useStore((s) => s.isPlaying);
  const sessionId = useStore((s) => s.sessionId);

  const visible = isStreaming || isPlaying;

  function handleInterrupt() {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      speechSynthesis.cancel();
    }
    window.dispatchEvent(new CustomEvent("interrupt-request", { detail: sessionId }));
    useStore.getState().setIsStreaming(false);
    useStore.getState().setIsPlaying(false);
  }

  return (
    <AnimatePresence>
      {visible && (
        <motion.button
          initial={{ opacity: 0, y: -12, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -12, scale: 0.9 }}
          transition={{ duration: 0.2, ease: "easeOut" }}
          onClick={handleInterrupt}
          whileTap={{ scale: 0.95 }}
          className="fixed top-4 left-1/2 -translate-x-1/2 z-50 pointer-events-auto 
                     bg-red-500/20 border border-red-500/40 text-red-400 
                     rounded-full px-5 py-2 text-xs font-semibold tracking-widest 
                     backdrop-blur-sm hover:bg-red-500/30 transition-colors 
                     select-none"
        >
          <span className="flex items-center gap-2">
            <Square size={10} fill="currentColor" />
            TAP TO INTERRUPT
          </span>
        </motion.button>
      )}
    </AnimatePresence>
  );
}
