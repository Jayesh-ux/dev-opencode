"use client";

import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { gsap } from "gsap";
import { Mic } from "lucide-react";
import { useStore } from "@/lib/store";
import { useWebSocket } from "@/lib/use-websocket";
import GlassPanel from "./GlassPanel";
import Sidebar from "./Sidebar";
import TranscriptionOverlay from "./TranscriptionOverlay";
import InterruptPill from "./InterruptPill";

export default function FloatingWorkspace({ sessionId }: { sessionId: string }) {
  const orbActive = useStore((s) => s.orbActive);
  const setOrbActive = useStore((s) => s.setOrbActive);
  const isPanelOpen = useStore((s) => s.isPanelOpen);
  const setPanelOpen = useStore((s) => s.setPanelOpen);
  const mode = useStore((s) => s.mode);
  const floatingText = useStore((s) => s.floatingText);
  const setFloatingText = useStore((s) => s.setFloatingText);
  const setSessionId = useStore((s) => s.setSessionId);
  const setGeminiConnected = useStore((s) => s.setGeminiConnected);
  const setConnectionStatus = useStore((s) => s.setConnectionStatus);

  const orbRef = useRef<HTMLDivElement>(null);
  const onWsMessageRef = useRef<((data: any) => void) | null>(null);
  const glowRef = useRef<HTMLDivElement>(null);
  const textTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    setSessionId(sessionId);
  }, [sessionId, setSessionId]);

  const { send: wsSend, readyState: wsReadyState } = useWebSocket("/ws/research", {
    sessionId,
    onMessage: (data) => onWsMessageRef.current?.(data),
  });

  useEffect(() => {
    if (wsReadyState === WebSocket.OPEN) {
      setGeminiConnected(true);
      setConnectionStatus("connected");
    } else {
      setGeminiConnected(false);
    }
  }, [wsReadyState, setGeminiConnected, setConnectionStatus]);

  useEffect(() => {
    if (!orbRef.current) return;
    const ctx = gsap.context(() => {
      gsap.to(orbRef.current, {
        scale: 1.08,
        duration: 1.8,
        ease: "power1.inOut",
        yoyo: true,
        repeat: -1,
      });
    }, orbRef);
    return () => ctx.revert();
  }, [orbActive]);

  useEffect(() => {
    if (!glowRef.current) return;
    const ctx = gsap.context(() => {
      gsap.to(glowRef.current, {
        boxShadow: orbActive
          ? "0 0 48px rgba(99,102,241,0.9), 0 0 80px rgba(99,102,241,0.4)"
          : "0 0 12px rgba(99,102,241,0.3)",
        duration: 1.0,
        ease: "power2.inOut",
      });
    }, glowRef);
    return () => ctx.revert();
  }, [orbActive]);

  useEffect(() => {
    const handler = (e: CustomEvent) => {
      const text = e.detail;
      if (text && typeof text === "string" && text.length > 10) {
        setFloatingText(text);
        setOrbActive(true);
        if (textTimeoutRef.current) clearTimeout(textTimeoutRef.current);
        textTimeoutRef.current = setTimeout(() => setOrbActive(false), 4000);
      }
    };
    window.addEventListener("gemini-response", handler as EventListener);
    return () => window.removeEventListener("gemini-response", handler as EventListener);
  }, [setFloatingText, setOrbActive]);

  return (
    <>
      <InterruptPill />
      <TranscriptionOverlay />

      {/* Glass Panel — only mounted when open, to avoid wasted WS connection */}
      {isPanelOpen && <GlassPanel sessionId={sessionId} send={wsSend} readyState={wsReadyState} setWsHandler={(fn) => { onWsMessageRef.current = fn; }} />}

      {/* Sidebar drawer */}
      <Sidebar />

      {/* Floating elements container — pointer-events-none so clicks pass through to terminal */}
      <div className="fixed inset-0 z-50 pointer-events-none">
        {/* Orb — bottom right */}
        {!isPanelOpen && (
          <motion.div
            drag
            dragMomentum
            dragElastic={0.1}
            ref={orbRef}
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{
              scale: orbActive ? 1 : 0.9,
              opacity: orbActive ? 1 : 0.4,
            }}
            transition={{ duration: 0.4 }}
            className="absolute right-6 bottom-6 pointer-events-auto cursor-grab active:cursor-grabbing z-50"
            onClick={() => setPanelOpen(!isPanelOpen)}
          >
            <div
              ref={glowRef}
              className="relative h-14 w-14 rounded-full flex items-center justify-center"
              style={{
                background: "radial-gradient(circle at 35% 25%, #818cf8, #4f46e5 50%, #6d28d9)",
                boxShadow: orbActive
                  ? "0 0 32px rgba(99,102,241,0.7), 0 0 64px rgba(99,102,241,0.3)"
                  : "0 0 16px rgba(99,102,241,0.35)",
              }}
            >
              <div className="absolute inset-0 rounded-full bg-blue-400/20 animate-pulse" />
              {mode === "live" && orbActive ? (
                <div className="flex items-end gap-0.5 relative z-10 h-5">
                  <span className="w-0.5 bg-white rounded-full animate-pulse h-3" />
                  <span className="w-0.5 bg-white rounded-full animate-pulse h-5" />
                  <span className="w-0.5 bg-white rounded-full animate-pulse h-4" />
                  <span className="w-0.5 bg-white rounded-full animate-pulse h-5" />
                  <span className="w-0.5 bg-white rounded-full animate-pulse h-3" />
                </div>
              ) : (
                <Mic size={20} className="text-white relative z-10" />
              )}
            </div>
          </motion.div>
        )}

      </div>
    </>
  );
}
