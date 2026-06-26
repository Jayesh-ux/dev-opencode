"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useWebSocket } from "@/lib/use-websocket";
import { useStore } from "@/lib/store";
import { Copy, Check, Clock } from "lucide-react";

interface LogEntry {
  ts: string;
  text: string;
  type: "prompt" | "log" | "status" | "error" | "logcat" | "device_shell" | "device" | "info";
}

function borderColor(type: string): string {
  switch (type) {
    case "prompt":
      return "border-l-blue-500/60";
    case "logcat":
      return "border-l-green-500/60";
    case "device_shell":
      return "border-l-yellow-500/60";
    case "error":
      return "border-l-red-500/60";
    default:
      return "border-l-white/10";
  }
}

function labelFor(type: string): { text: string; cls: string } | null {
  switch (type) {
    case "prompt":
      return { text: "Prompt", cls: "text-blue-400 bg-blue-500/10" };
    case "logcat":
      return { text: "Logcat", cls: "text-green-400 bg-green-500/10" };
    case "device_shell":
    case "device":
      return { text: "Device", cls: "text-yellow-400 bg-yellow-500/10" };
    case "error":
      return { text: "Error", cls: "text-red-400 bg-red-500/10" };
    case "status":
    case "info":
      return { text: "Info", cls: "text-text-muted bg-white/5" };
    default:
      return null;
  }
}

function BlinkingCursor() {
  return (
    <span className="inline-block w-[2px] h-4 bg-white/40 animate-pulse align-middle ml-0.5" />
  );
}

export default function OpenCodePane({ sessionId, compact, fullscreen }: { sessionId: string | null; compact?: boolean; fullscreen?: boolean }) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const [promptInput, setPromptInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const sendRef = useRef<((data: any) => void) | null>(null);
  const tokenPct = useStore((s) => s.tokenPct);
  const setOpencodeConnected = useStore((s) => s.setOpencodeConnected);

  const onMessage = useCallback((data: any) => {
    const ts = new Date().toLocaleTimeString();

    if (data.type === "prompt_injection") {
      setLogs((prev) => [...prev, { ts, text: (data.payload as string) || "", type: "prompt" }]);
    } else if (data.type === "history") {
      const prompts = (data.prompts as string[]) || [];
      setLogs((prev) => [...prev, ...prompts.map((p) => ({ ts, text: p, type: "prompt" as const }))]);
    } else if (data.type === "logcat") {
      setLogs((prev) => [...prev, { ts, text: (data.payload as string) || "", type: "logcat" }]);
    } else if (data.type === "device_shell") {
      setLogs((prev) => [...prev, { ts, text: (data.payload as string) || "", type: "device" }]);
    } else if (data.type === "error") {
      setLogs((prev) => [...prev, { ts, text: (data.payload as string) || "", type: "error" }]);
    } else if (data.type === "connected" || data.type === "session_started") {
      setLogs((prev) => [...prev, { ts, text: `OpenCode session ready: ${sessionId}`, type: "info" }]);
    }
  }, [sessionId]);

  const onOpen = useCallback(() => {
    setConnected(true);
    setOpencodeConnected(true);
  }, [setOpencodeConnected]);

  const onClose = useCallback(() => {
    setConnected(false);
    setOpencodeConnected(false);
  }, [setOpencodeConnected]);

  const { send, readyState } = useWebSocket("/ws/opencode", { sessionId, onMessage, onOpen, onClose });
  sendRef.current = send;

  useEffect(() => {
    const handler = (e: CustomEvent) => {
      const text = e.detail;
      setLogs((prev) => [...prev, { ts: new Date().toLocaleTimeString(), text, type: "prompt" }]);
      if (sendRef.current && readyState === WebSocket.OPEN) {
        sendRef.current({ type: "log", payload: text, session_id: sessionId });
      }
    };
    window.addEventListener("pipe-to-opencode", handler as EventListener);
    return () => window.removeEventListener("pipe-to-opencode", handler as EventListener);
  }, [readyState, sessionId]);

  useEffect(() => {
    if (connected && sendRef.current) {
      sendRef.current({ type: "get_history", session_id: sessionId });
    }
  }, [connected, sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  function sendPrompt() {
    if (!promptInput.trim() || !sendRef.current) return;
    sendRef.current({ type: "inject_prompt", payload: promptInput.trim(), session_id: sessionId });
    setLogs((prev) => [...prev, { ts: new Date().toLocaleTimeString(), text: `→ ${promptInput.trim()}`, type: "prompt" }]);
    setPromptInput("");
  }

  function requestHistory() {
    send({ type: "get_history", session_id: sessionId });
  }

  function clearLogs() {
    setLogs([]);
  }

  async function copyText(text: string, idx: number) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedIdx(idx);
      setTimeout(() => setCopiedIdx(null), 2000);
    } catch {
      // fallback
    }
  }

  function tokenBarColor(pct: number): string {
    if (pct > 85) return "bg-red-500";
    if (pct > 60) return "bg-yellow-500";
    return "bg-green-500";
  }

  return (
    <div className={`flex flex-col bg-[#09090b] ${fullscreen ? "h-full w-full" : "h-full"}`}>
      {!compact && (
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border/20 bg-[#0d0d14]">
          <span className={`w-1.5 h-1.5 rounded-full transition-colors duration-300 ${connected ? "bg-success" : "bg-danger"}`} />
          <span className="text-xs font-medium text-text-secondary">OpenCode Terminal</span>
          <div className="flex items-center gap-1 ml-auto">
            <button
              onClick={requestHistory}
              disabled={readyState !== WebSocket.OPEN}
              className="flex items-center gap-1.5 px-2 py-1 text-[11px] font-medium text-text-muted bg-[#1a1a25]/50 border border-white/10 rounded-lg hover:bg-[#22222f] hover:text-text-primary transition-all duration-200 disabled:opacity-30"
            >
              <Clock size={12} />
              History
            </button>
            <button
              onClick={clearLogs}
              className="flex items-center gap-1.5 px-2 py-1 text-[11px] font-medium text-text-muted bg-[#1a1a25]/50 border border-white/10 rounded-lg hover:bg-[#22222f] hover:text-text-primary transition-all duration-200"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              </svg>
              Clear
            </button>
          </div>
        </div>
      )}

      <div className={`overflow-y-auto p-4 space-y-3 ${fullscreen ? "flex-1" : "flex-1"} bg-[#09090b]`}>
        {logs.length === 0 && !connected && (
          <div className="flex flex-col items-center justify-center h-full select-none">
            <p className="text-xl font-semibold text-white/50">
              ⬡ OpenCode Terminal<BlinkingCursor />
            </p>
            <p className="text-xs text-white/30 mt-2">waiting for connection...</p>
          </div>
        )}

        {logs.length === 0 && connected && (
          <div className="flex items-center justify-center h-full">
            <div className="border border-white/10 rounded-lg p-4 m-4 font-mono text-xs text-white/50">
              <div className="text-green-400/80 mb-2">⬡ OPENCODE ENGINE</div>
              <div>Session: {sessionId}</div>
              <div>Backend: ws://127.0.0.1:8000</div>
              <div className="text-green-400">Status: Connected</div>
              <div className="mt-2 text-white/30">Waiting for agent activity...</div>
              <div className="mt-1 text-white/20 text-[10px]">Tip: Use the inject bar below to send prompts to the agent</div>
            </div>
          </div>
        )}

        {logs.map((entry, i) => {
          const label = labelFor(entry.type);
          return (
            <div key={i} className={`animate-slide-up space-y-1.5 border-l-2 ${borderColor(entry.type)} pl-3 group`}>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono text-text-muted">{entry.ts}</span>
                {label && (
                  <span className={`px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wider rounded ${label.cls}`}>
                    {label.text}
                  </span>
                )}
                <button
                  onClick={() => copyText(entry.text, i)}
                  className="ml-auto p-0.5 rounded text-text-muted hover:text-text-primary hover:bg-white/5 transition-colors opacity-0 group-hover:opacity-100"
                  title="Copy to clipboard"
                >
                  {copiedIdx === i ? <Check size={10} className="text-green-400" /> : <Copy size={10} />}
                </button>
              </div>
              <pre
                className={`text-xs font-mono leading-relaxed whitespace-pre-wrap overflow-x-auto ${
                  entry.type === "prompt"
                    ? "p-3 bg-[#0d0d1a] border border-blue-500/15 rounded-lg text-blue-400/90"
                    : entry.type === "error"
                      ? "p-2.5 bg-red-500/5 border border-red-500/20 rounded-lg text-red-400/80"
                      : entry.type === "status"
                        ? "p-2.5 bg-[#1a1a25]/30 border border-white/5 rounded-lg text-text-secondary"
                        : "p-2.5 bg-[#1a1a25]/20 border border-white/5 rounded-lg text-text-secondary"
                }`}
              >
                {entry.text}
              </pre>
            </div>
          );
        })}

        <div ref={bottomRef} />
      </div>

      {/* Prompt input bar */}
      <div className="border-t border-white/5 p-2 flex gap-2 shrink-0 pointer-events-auto">
        <input
          value={promptInput}
          onChange={(e) => setPromptInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") sendPrompt(); }}
          placeholder="Inject prompt to OpenCode agent..."
          className="bg-transparent text-white/70 text-xs font-mono flex-1 outline-none placeholder-white/20 px-2"
        />
        <button
          onClick={sendPrompt}
          className="text-blue-400 hover:text-blue-300 text-xs font-mono px-2 py-1 hover:bg-blue-500/10 rounded"
        >
          inject
        </button>
      </div>

      {/* Token usage mini-bar */}
      {tokenPct > 0 && (
        <div className="shrink-0 h-0.5 bg-white/5">
          <div
            className={`h-full ${tokenBarColor(tokenPct)} transition-all duration-500`}
            style={{ width: `${Math.min(tokenPct, 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}
