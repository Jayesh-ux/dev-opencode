"use client";

import { useState } from "react";
import OpenCodePane from "@/components/OpenCodePane";
import FloatingWorkspace from "@/components/FloatingWorkspace";
import { useStore } from "@/lib/store";

export default function Home() {
  const [sessionId] = useState(() => {
    if (typeof window === "undefined") return "ssr";
    const stored = localStorage.getItem("ai_session_id");
    if (stored) return stored;
    const newId = Math.random().toString(36).substring(2, 8);
    localStorage.setItem("ai_session_id", newId);
    return newId;
  });
  const isPanelOpen = useStore((s) => s.isPanelOpen);

  return (
    <main className="relative w-screen h-screen overflow-hidden bg-[#09090b]">
      {/* Layer 0: Terminal fills entire screen */}
      <div className={`absolute inset-0 z-0 ${isPanelOpen ? "pointer-events-none" : ""}`}>
        <OpenCodePane sessionId={sessionId} fullscreen />
      </div>

      {/* Layer 1: All floating UI on top */}
      <div className="absolute inset-0 z-10 pointer-events-none">
        <FloatingWorkspace sessionId={sessionId} />
      </div>
    </main>
  );
}
