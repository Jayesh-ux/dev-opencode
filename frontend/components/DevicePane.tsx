"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Smartphone, Wifi, WifiOff, Loader2, Monitor, Image, Terminal, X } from "lucide-react";

interface LogEntry {
  ts: string;
  text: string;
  type: "log" | "status" | "error" | "screenshot";
  screenshotBase64?: string;
}

interface Capabilities {
  adb_available: boolean;
  playwright_available: boolean;
  platform: string;
}

export default function DevicePane({ sessionId }: { sessionId: string | null }) {
  const [expanded, setExpanded] = useState(false);
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    fetch("/api/tools/capabilities").then(r => r.json()).then(setCaps).catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  function addLog(text: string, type: LogEntry["type"] = "log", screenshotBase64?: string) {
    setLogs(prev => [...prev, { ts: new Date().toLocaleTimeString(), text, type, screenshotBase64 }]);
  }

  async function callApi(endpoint: string, body?: Record<string, unknown>) {
    setLoading(endpoint);
    try {
      const params = body ? "?" + new URLSearchParams(
        Object.entries(body).map(([k, v]) => [k, String(v)])
      ).toString() : "";
      const res = await fetch(endpoint + params, { method: "POST" });
      const data = await res.json();
      addLog(JSON.stringify(data, null, 2), data.error ? "error" : "status");
    } catch (e: any) {
      addLog(String(e), "error");
    } finally {
      setLoading(null);
    }
  }

  function toggleLogcat() {
    if (streaming) {
      wsRef.current?.close();
      setStreaming(false);
      addLog("Logcat stopped", "status");
      return;
    }

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${proto}//${window.location.host}/ws/device?session_id=${sessionId || ""}&action=logcat`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    setStreaming(true);
    addLog("Connecting to logcat stream...", "status");

    ws.onopen = () => addLog("Logcat connected", "status");
    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === "logcat") {
          addLog(data.payload, "log");
        } else if (data.type === "error") {
          addLog(data.payload, "error");
        }
      } catch {}
    };
    ws.onerror = () => addLog("Logcat WebSocket error", "error");
    ws.onclose = () => {
      setStreaming(false);
      addLog("Logcat disconnected", "status");
    };
  }

  async function takeScreenshot() {
    setLoading("screenshot");
    try {
      const res = await fetch("/api/tools/playwright/screenshot", { method: "POST" });
      const data = await res.json();
      if (data.screenshot_base64) {
        addLog("Screenshot captured", "screenshot", data.screenshot_base64);
      } else {
        addLog(data.error || "Screenshot failed", "error");
      }
    } catch (e: any) {
      addLog(String(e), "error");
    } finally {
      setLoading(null);
    }
  }

  function clearLogs() {
    setLogs([]);
  }

  const hasAdb = caps?.adb_available;
  const hasPw = caps?.playwright_available;

  return (
    <div className="border border-border rounded-xl overflow-hidden bg-surface">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2.5 text-xs font-medium text-text-secondary hover:text-text-primary transition-colors bg-panel"
      >
        <Smartphone size={14} />
        Device Control
        <span className="ml-auto flex items-center gap-2">
          {caps && (
            <>
              {hasAdb ? <Wifi size={12} className="text-success" /> : <WifiOff size={12} className="text-danger" />}
              {hasPw ? <Monitor size={12} className="text-success" /> : <Monitor size={12} className="text-danger" />}
            </>
          )}
        </span>
      </button>

      {expanded && (
        <div className="p-3 space-y-2 animate-fade-in">
          {/* Action buttons */}
          <div className="flex flex-wrap gap-1.5">
            <button
              onClick={() => callApi("/api/tools/adb/devices")}
              disabled={!hasAdb || loading !== null}
              className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-lg border border-border bg-panel hover:bg-panel-hover text-text-secondary hover:text-text-primary transition-all disabled:opacity-30"
            >
              {loading === "/api/tools/adb/devices" ? <Loader2 size={12} className="animate-spin" /> : <Smartphone size={12} />}
              List Devices
            </button>
            <button
              onClick={takeScreenshot}
              disabled={!hasPw || loading !== null}
              className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-lg border border-border bg-panel hover:bg-panel-hover text-text-secondary hover:text-text-primary transition-all disabled:opacity-30"
            >
              {loading === "screenshot" ? <Loader2 size={12} className="animate-spin" /> : <Image size={12} />}
              Screenshot
            </button>
            <button
              onClick={() => callApi("/api/tools/adb/shell", { command: "dumpsys battery" })}
              disabled={!hasAdb || loading !== null}
              className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-lg border border-border bg-panel hover:bg-panel-hover text-text-secondary hover:text-text-primary transition-all disabled:opacity-30"
            >
              {loading === "/api/tools/adb/shell" ? <Loader2 size={12} className="animate-spin" /> : <Terminal size={12} />}
              Battery
            </button>
            <button
              onClick={() => callApi("/api/tools/playwright/html", { url: "https://example.com" })}
              disabled={!hasPw || loading !== null}
              className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-lg border border-border bg-panel hover:bg-panel-hover text-text-secondary hover:text-text-primary transition-all disabled:opacity-30"
            >
              {loading === "/api/tools/playwright/html" ? <Loader2 size={12} className="animate-spin" /> : <Terminal size={12} />}
              Get HTML
            </button>
            <button
              onClick={toggleLogcat}
              disabled={!hasAdb}
              className={`flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-lg border transition-all disabled:opacity-30 ${
                streaming
                  ? "bg-danger/20 border-danger/40 text-danger hover:bg-danger/30"
                  : "bg-panel border-border text-text-secondary hover:bg-panel-hover hover:text-text-primary"
              }`}
            >
              {streaming ? <X size={12} /> : <Wifi size={12} />}
              {streaming ? "Stop Logcat" : "Logcat"}
            </button>
          </div>

          {/* Output area */}
          <div className="bg-[#0a0a12] border border-border rounded-lg max-h-48 overflow-y-auto p-2 space-y-1">
            {logs.length === 0 && (
              <p className="text-[11px] text-text-muted text-center py-4">Run a device command to see output</p>
            )}
            {logs.map((entry, i) => (
              <div key={i} className="animate-slide-up">
                {entry.type === "screenshot" && entry.screenshotBase64 ? (
                  <img
                    src={`data:image/png;base64,${entry.screenshotBase64}`}
                    alt="Screenshot"
                    className="w-full rounded border border-border"
                  />
                ) : (
                  <div className="flex gap-1.5">
                    <span className="text-[9px] font-mono text-text-muted shrink-0 mt-0.5">{entry.ts}</span>
                    <span className={`text-[11px] font-mono leading-relaxed whitespace-pre-wrap ${
                      entry.type === "error" ? "text-danger" :
                      entry.type === "status" ? "text-accent" : "text-text-secondary"
                    }`}>
                      {entry.text.length > 500 ? entry.text.slice(0, 500) + "..." : entry.text}
                    </span>
                  </div>
                )}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>

          {/* Clear button */}
          {logs.length > 0 && (
            <button
              onClick={clearLogs}
              className="text-[10px] text-text-muted hover:text-text-secondary transition-colors"
            >
              Clear output
            </button>
          )}
        </div>
      )}
    </div>
  );
}
