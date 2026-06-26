"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import { useStore, type TaskItem } from "@/lib/store";

function tokenBarColor(pct: number): string {
  if (pct > 85) return "bg-red-500";
  if (pct > 60) return "bg-yellow-500";
  return "bg-green-500";
}

function tokenBarBg(pct: number): string {
  if (pct > 85) return "bg-red-500/20";
  if (pct > 60) return "bg-yellow-500/20";
  return "bg-green-500/20";
}

interface SnapshotInfo {
  file: string;
  timestamp: string;
  reason: string;
}

export default function Sidebar() {
  const [open, setOpen] = useState(false);
  const tokenPct = useStore((s) => s.tokenPct);
  const tokenTotal = useStore((s) => s.tokenTotal);
  const taskProgress = useStore((s) => s.taskProgress);
  const taskList = useStore((s) => s.taskList);
  const sessionState = useStore((s) => s.sessionState);
  const sessionId = useStore((s) => s.sessionId);
  const opencodeConnected = useStore((s) => s.opencodeConnected);
  const geminiConnected = useStore((s) => s.geminiConnected);
  const setSessionState = useStore((s) => s.setSessionState);
  const [snapshots, setSnapshots] = useState<SnapshotInfo[]>([]);
  const [resuming, setResuming] = useState(false);

  useEffect(() => {
    fetch("http://127.0.0.1:8000/snapshots")
      .then((r) => r.json())
      .then((d) => setSnapshots((d.snapshots || []).slice(0, 3)))
      .catch(() => {});
  }, []);

  async function handleResume() {
    setResuming(true);
    try {
      const res = await fetch("http://127.0.0.1:8000/api/chat/resume", { method: "POST" });
      const data = await res.json();
      setSessionState(data.state as any);
    } catch {
      // ignore
    } finally {
      setResuming(false);
    }
  }

  const isPaused = sessionState === "PAUSED";

  return (
    <>
      {/* Pill tab — always visible on right edge */}
      <button
        onClick={() => setOpen(true)}
        className="fixed right-0 top-1/2 -translate-y-1/2 z-40
                   bg-[#0d0d11]/80 border-l border-t border-b border-white/10
                   rounded-l-xl px-1.5 py-4
                   hover:bg-[#0d0d11] transition-colors
                   pointer-events-auto"
      >
        <span className="text-white/40 text-sm font-mono">≡</span>
      </button>

      {/* Backdrop */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 z-30 bg-black/40 pointer-events-auto"
            onClick={() => setOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* Drawer panel */}
      <AnimatePresence>
        {open && (
          <motion.aside
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="fixed right-0 top-0 h-full z-40 pointer-events-auto
                       w-[85vw] max-w-[320px]
                       bg-[#0d0d11]/95 backdrop-blur-xl
                       border-l border-white/5
                       flex flex-col overflow-y-auto
                       shadow-2xl"
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
              <span className="text-xs font-semibold text-white/60 uppercase tracking-widest">
                Info
              </span>
              <button
                onClick={() => setOpen(false)}
                className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-white/5 transition-colors"
              >
                <X size={14} />
              </button>
            </div>

            <div className="p-4 space-y-5">
              {/* Session ID */}
              <div>
                <div className="text-[10px] uppercase tracking-widest text-text-muted mb-1.5">
                  Session
                </div>
                <div className="text-xs font-mono text-text-secondary truncate bg-white/5 rounded px-2 py-1.5">
                  {sessionId || "—"}
                </div>
              </div>

              {/* Connection Status */}
              <div>
                <div className="text-[10px] uppercase tracking-widest text-text-muted mb-1.5">
                  Connections
                </div>
                <div className="space-y-1.5">
                  <div className="flex items-center gap-2 text-xs">
                    <span className={`w-1.5 h-1.5 rounded-full ${geminiConnected ? "bg-green-500" : "bg-red-500"}`} />
                    <span className="text-text-secondary">Gemini</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    <span className={`w-1.5 h-1.5 rounded-full ${opencodeConnected ? "bg-green-500" : "bg-red-500"}`} />
                    <span className="text-text-secondary">OpenCode</span>
                  </div>
                </div>
              </div>

              {/* Token Health Bar */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[10px] uppercase tracking-widest text-text-muted">
                    Token Usage
                  </span>
                  <span className="text-[10px] font-mono text-text-secondary">
                    {tokenPct.toFixed(0)}%
                  </span>
                </div>
                <div className={`h-2 rounded-full ${tokenBarBg(tokenPct)} overflow-hidden`}>
                  <motion.div
                    className={`h-full rounded-full ${tokenBarColor(tokenPct)}`}
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(tokenPct, 100)}%` }}
                    transition={{ duration: 0.4, ease: "easeOut" }}
                  />
                </div>
                {tokenTotal > 0 && (
                  <div className="text-[9px] text-text-muted mt-1 font-mono">
                    {(tokenTotal / 1000).toFixed(0)}K / 1,000K
                  </div>
                )}
              </div>

              {/* Task Progress */}
              {taskList.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-[10px] uppercase tracking-widest text-text-muted">
                      Tasks
                    </span>
                    <span className="text-[10px] text-text-secondary">
                      {taskProgress.toFixed(0)}%
                    </span>
                  </div>
                  <div className="space-y-1">
                    {taskList.map((t: TaskItem) => (
                      <div key={t.step} className="flex items-start gap-1.5 text-[11px]">
                        <span
                          className={`shrink-0 mt-0.5 ${
                            t.status === "DONE"
                              ? "text-green-500"
                              : t.status === "IN_PROGRESS"
                                ? "text-yellow-500"
                                : "text-text-muted"
                          }`}
                        >
                          {t.status === "DONE" ? "✓" : t.status === "IN_PROGRESS" ? "●" : "○"}
                        </span>
                        <span className="text-text-secondary leading-tight">{t.description}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* State */}
              <div>
                <div className="text-[10px] uppercase tracking-widest text-text-muted mb-1.5">
                  State
                </div>
                <div
                  className={`text-xs font-mono rounded px-2 py-1.5 inline-block ${
                    isPaused
                      ? "bg-red-500/20 text-red-400"
                      : "bg-green-500/10 text-green-400"
                  }`}
                >
                  {sessionState}
                </div>
              </div>

              {/* Resume Button */}
              <AnimatePresence>
                {isPaused && (
                  <motion.button
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    onClick={handleResume}
                    disabled={resuming}
                    className="w-full px-3 py-2 text-xs font-semibold rounded-lg 
                               bg-accent/20 text-accent border border-accent/30 
                               hover:bg-accent/30 transition-colors disabled:opacity-50"
                  >
                    {resuming ? "Resuming..." : "▶ RESUME SESSION"}
                  </motion.button>
                )}
              </AnimatePresence>

              {/* Recent Snapshots */}
              <div>
                <div className="text-[10px] uppercase tracking-widest text-text-muted mb-1.5">
                  Recent Snapshots
                </div>
                {snapshots.length === 0 ? (
                  <div className="text-[10px] font-mono text-text-muted bg-white/5 rounded px-2 py-1">
                    No snapshots yet
                  </div>
                ) : (
                  <div className="space-y-1">
                    {snapshots.map((s) => (
                      <div
                        key={s.file}
                        className="text-[10px] font-mono text-text-muted bg-white/5 rounded px-2 py-1 truncate"
                      >
                        <span
                          className={
                            s.reason === "429_ERROR"
                              ? "text-red-400"
                              : s.reason === "TOKEN_THRESHOLD"
                                ? "text-yellow-400"
                                : "text-text-secondary"
                          }
                        >
                          {s.reason}
                        </span>
                        <span className="ml-2">{s.timestamp}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  );
}
