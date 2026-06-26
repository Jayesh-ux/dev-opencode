"use client";

import { useEffect, useRef } from "react";

export default function OpenCodePane({ sessionId, compact, fullscreen }: { sessionId: string | null; compact?: boolean; fullscreen?: boolean }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    let ws: WebSocket | null = null;
    let term: any = null;
    let fitAddon: any = null;

    // Create link tag for CSS
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.min.css";
    document.head.appendChild(link);

    // Load xterm.js
    const script = document.createElement("script");
    script.src = "https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.min.js";
    script.onload = () => {
      if (!active) return;

      // Load fit addon after xterm core is loaded
      const fitScript = document.createElement("script");
      fitScript.src = "https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.min.js";
      fitScript.onload = () => {
        if (!active || !containerRef.current) return;

        const xterm = (window as any).Terminal;
        const FitAddon = (window as any).FitAddon.FitAddon;

        term = new xterm({
          theme: {
            background: "#09090b",
            foreground: "#f4f4f5",
            cursor: "#a1a1aa",
          },
          cursorBlink: true,
          fontFamily: 'Menlo, Monaco, Consolas, "Courier New", monospace',
          fontSize: 13,
        });

        fitAddon = new FitAddon();
        term.loadAddon(fitAddon);
        term.open(containerRef.current);
        
        // Wait a small tick to ensure DOM is ready before fitting
        setTimeout(() => {
          if (active && fitAddon) fitAddon.fit();
        }, 100);

        // Connect to WebSocket pointing directly to the backend port 8000
        const wsUrl = `ws://${window.location.hostname}:8000/ws/terminal`;
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
          ws?.send(JSON.stringify({
            type: "resize",
            cols: term.cols,
            rows: term.rows
          }));
        };

        ws.onmessage = (e) => {
          term.write(e.data);
        };

        term.onData((data: string) => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "input", data }));
          }
        });

        const handleResize = () => {
          if (!fitAddon || !term) return;
          try {
            fitAddon.fit();
            if (ws && ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({
                type: "resize",
                cols: term.cols,
                rows: term.rows
              }));
            }
          } catch (err) {
            console.warn("Resize error:", err);
          }
        };

        window.addEventListener("resize", handleResize);
        (term as any)._cleanResize = handleResize;
      };
      document.body.appendChild(fitScript);
    };
    document.body.appendChild(script);

    return () => {
      active = false;
      document.head.removeChild(link);
      if (script.parentNode) script.parentNode.removeChild(script);
      if (ws) ws.close();
      if (term) {
        if ((term as any)._cleanResize) {
          window.removeEventListener("resize", (term as any)._cleanResize);
        }
        term.dispose();
      }
    };
  }, []);

  return (
    <div 
      className="bg-[#09090b] flex items-center justify-center" 
      style={{ 
        position: "absolute", 
        inset: 0, 
        width: "100%", 
        height: "100%", 
        overflow: "hidden" 
      }}
    >
      <div 
        ref={containerRef} 
        style={{ 
          width: "95%", 
          maxWidth: "850px", 
          height: "90%", 
          maxHeight: "550px",
          padding: "12px",
          boxSizing: "border-box" 
        }} 
      />
    </div>
  );
}
