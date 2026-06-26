"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useStore } from "@/lib/store";

export default function TranscriptionOverlay() {
  const floatingText = useStore((s) => s.floatingText);
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    if (floatingText) {
      setVisible(true);
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        setVisible(false);
      }, 3000);
    }
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [floatingText]);

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.2, ease: "easeOut" }}
          className="absolute top-[38%] left-8 right-8 pointer-events-none z-40 text-center"
        >
          <p
            style={{
              filter:
                "drop-shadow(0 4px 12px rgba(0,0,0,1)) drop-shadow(0 2px 6px rgba(0,0,0,0.9))",
            }}
            className="text-2xl font-semibold text-white leading-snug"
          >
            {floatingText}
          </p>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
