"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Square, Mic, Send, Monitor, VolumeX, Volume2, X, Smartphone } from "lucide-react";
import { useStore } from "@/lib/store";
import { LiveAudioSession, type LiveAudioCallbacks } from "@/lib/live-audio";
import DevicePane from "./DevicePane";

const STT_API = "http://127.0.0.1:8000/api/voice/stt";

interface Message {
  role: "user" | "assistant" | "system";
  text: string;
  interrupted?: boolean;
}

const SpeechRecognitionAPI =
  (typeof window !== "undefined" &&
    ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)) ||
  null;

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-2 py-3">
      <span className="typing-dot" />
      <span className="typing-dot" />
      <span className="typing-dot" />
    </div>
  );
}

export default function GlassPanel({ sessionId, send, readyState, setWsHandler }: { sessionId: string; send: (msg: any) => void; readyState: number; setWsHandler: (fn: ((data: any) => void) | null) => void }) {
  const isPanelOpen = useStore((s) => s.isPanelOpen);
  const setPanelOpen = useStore((s) => s.setPanelOpen);
  const mode = useStore((s) => s.mode);
  const setMode = useStore((s) => s.setMode);
  const isAudioMuted = useStore((s) => s.isAudioMuted);
  const toggleAudioMuted = useStore((s) => s.toggleAudioMuted);
  const setGeminiConnected = useStore((s) => s.setGeminiConnected);
  const setFloatingText = useStore((s) => s.setFloatingText);
  const setIsStreaming = useStore((s) => s.setIsStreaming);
  const setIsPlaying = useStore((s) => s.setIsPlaying);
  const setSessionState = useStore((s) => s.setSessionState);
  const setTokenUsage = useStore((s) => s.setTokenUsage);
  const setTasks = useStore((s) => s.setTasks);
  const setOrbActive = useStore((s) => s.setOrbActive);

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [connected, setConnected] = useState(false);
  const [recording, setRecording] = useState(false);
  const [interim, setInterim] = useState("");
  const [thinking, setThinking] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [isLiveActive, setIsLiveActive] = useState(false);
  const [isDeviceOpen, setIsDeviceOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const genRef = useRef(0);
  const completedMsgsRef = useRef(0);
  const liveAudioRef = useRef<LiveAudioSession | null>(null);
  const liveAccumRef = useRef("");
  const recognitionRef = useRef<any>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const screenStreamRef = useRef<MediaStream | null>(null);
  const shareIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const onMessage = useCallback((data: any) => {
    if (data.type === "session_started") {
      setGeminiConnected(true);
      return;
    } else if (data.type === "interrupted") {
      setIsStreaming(false);
      setThinking(false);
      setMessages((prev) => {
        if (prev.length > 0 && prev[prev.length - 1].role === "assistant") {
          const updated = [...prev];
          updated[updated.length - 1] = { ...updated[updated.length - 1], interrupted: true };
          return updated;
        }
        return prev;
      });
    } else if (data.type === "assistant" || data.type === "assistant_chunk") {
      if (data.gen !== undefined && data.gen !== genRef.current) return;
      setThinking(false);
      if (data.type === "assistant_chunk") {
        setMessages((prev) => {
          if (prev.length > 0 && prev[prev.length - 1].role === "assistant") {
            const updated = [...prev];
            updated[updated.length - 1] = {
              ...updated[updated.length - 1],
              text: updated[updated.length - 1].text + data.payload,
            };
            return updated;
          }
          return [...prev, { role: "assistant", text: data.payload }];
        });
      } else {
        completedMsgsRef.current += 1;
        setIsStreaming(false);
        setMessages((prev) => {
          if (prev.length > 0 && prev[prev.length - 1].role === "assistant") {
            const updated = [...prev];
            updated[updated.length - 1] = { ...updated[updated.length - 1], text: data.payload };
            return updated;
          }
          return [...prev, { role: "assistant", text: data.payload }];
        });
        setOrbActive(true);
        setFloatingText(data.payload);
      }
    } else if (data.type === "token_warning" || data.type === "token_report") {
      setTokenUsage(data.pct || 0, data.total_tokens || 0);
    } else if (data.type === "trigger_detected") {
      setMessages((prev) => [...prev, { role: "system", text: data.payload }]);
    } else if (data.state) {
      setSessionState(data.state);
    }
  }, [setGeminiConnected, setIsStreaming, setOrbActive, setFloatingText, setTokenUsage, setSessionState]);

  useEffect(() => {
    if (readyState === WebSocket.OPEN) {
      setConnected(true);
    } else {
      setConnected(false);
    }
  }, [readyState]);

  useEffect(() => {
    setWsHandler(onMessage);
    return () => setWsHandler(null);
  }, [onMessage]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  useEffect(() => {
    if (mode !== "live" && liveAudioRef.current) {
      liveAudioRef.current.stop();
      liveAudioRef.current = null;
      setIsLiveActive(false);
    }
  }, [mode]);

  async function toggleLiveMic() {
    if (mode !== "live") return;
    if (isLiveActive) {
      liveAudioRef.current?.stop();
      liveAudioRef.current = null;
      setIsLiveActive(false);
      return;
    }

    try {
      await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setMessages((prev) => [...prev, { role: "system", text: "⚠️ Mic permission denied. Allow microphone access in browser settings." }]);
      return;
    }

    const callbacks: LiveAudioCallbacks = {
      onText: (text) => {
        setMessages((prev) => [...prev, { role: "assistant", text }]);
        setFloatingText(text);
        window.dispatchEvent(new CustomEvent("gemini-response", { detail: { text } }));
      },
      onInterrupted: () => {
        setMessages((prev) => [...prev, { role: "system", text: "⏹ Interrupted" }]);
      },
      onTurnComplete: () => {},
      onConnected: () => {},
      onDisconnected: () => setMode("chat"),
      onError: (err) => {
        setMessages((prev) => [...prev, { role: "system", text: `Live error: ${err}` }]);
        setIsLiveActive(false);
        liveAudioRef.current = null;
      },
    };

    try {
      const session = new LiveAudioSession(callbacks);
      session.onMessage = (msg) => {
        const type = msg.type as string;
        if (type === "audio") {
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.role === "system" && last?.text?.includes("🔊")) return prev;
            return [...prev, { role: "system", text: "🔊 Audio response playing..." }];
          });
        }
        if (type === "turn_complete") {
          setMessages((prev) =>
            prev.map((m, i) =>
              i === prev.length - 1 && m.text?.includes("🔊")
                ? { ...m, text: "✓ Response complete" }
                : m
            )
          );
        }
      };
      liveAudioRef.current = session;
      const url = `ws://127.0.0.1:8000/ws/live?session_id=${encodeURIComponent(sessionId)}&voice=Puck`;
      await session.start(url);
      setIsLiveActive(true);
      setMessages((prev) => [...prev, { role: "system", text: "🔴 Live audio active — speak now" }]);
    } catch (err) {
      setMessages((prev) => [...prev, { role: "system", text: `Failed to start live: ${err}` }]);
      liveAudioRef.current = null;
      setIsLiveActive(false);
    }
  }

  const doInterrupt = useCallback(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      speechSynthesis.cancel();
    }
    setThinking(false);
    setIsStreaming(false);
    setIsPlaying(false);
    liveAudioRef.current?.interrupt();
    send({ type: "interrupt" });
    liveAccumRef.current = "";
    setMessages((prev) => {
      if (prev.length > 0 && prev[prev.length - 1].role === "assistant") {
        const updated = [...prev];
        updated[updated.length - 1] = { ...updated[updated.length - 1], interrupted: true };
        return updated;
      }
      return prev;
    });
  }, [send, setIsStreaming, setIsPlaying]);

  useEffect(() => {
    const handler = () => doInterrupt();
    window.addEventListener("interrupt-request", handler);
    return () => window.removeEventListener("interrupt-request", handler);
  }, [doInterrupt]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    if (mode === "live") {
      liveAudioRef.current?.sendText(text);
      setMessages((prev) => [...prev, { role: "user", text }]);
    } else {
      const gen = ++genRef.current;
      if (thinking) send({ type: "interrupt" });
      setMessages((prev) => [...prev, { role: "user", text }]);
      setThinking(true);
      setIsStreaming(true);
      send({ type: "text", payload: text, gen });
    }
    setInput("");
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  }

  function startVoice() {
    if (mode === "live") return;
    if (thinking) send({ type: "interrupt" });
    if (SpeechRecognitionAPI) {
      const recog = new SpeechRecognitionAPI();
      recog.continuous = false;
      recog.interimResults = true;
      recog.lang = "en-US";
      recognitionRef.current = recog;
      recog.onresult = (event: any) => {
        let final = "";
        let ci = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          if (event.results[i].isFinal) final += event.results[i][0].transcript;
          else ci += event.results[i][0].transcript;
        }
        setInterim(ci);
        if (final) {
          const gen = ++genRef.current;
          setMessages((prev) => [...prev, { role: "user", text: final.trim() }]);
          setThinking(true);
          setIsStreaming(true);
          send({ type: "text", payload: final.trim(), gen });
        }
      };
      recog.onend = () => { setRecording(false); setInterim(""); };
      recog.onerror = () => { setRecording(false); setInterim(""); };
      setRecording(true);
      setInterim("Listening...");
      recog.start();
    } else {
      startMediaRecorder();
    }
  }

  function stopVoice() {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current = null;
    }
    setRecording(false);
    setInterim("");
  }

  async function startMediaRecorder() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
          ? "audio/webm"
          : "audio/ogg;codecs=opus";
      const chunks: Blob[] = [];
      const recorder = new MediaRecorder(stream, { mimeType: mime });
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks, { type: mime });
        if (blob.size === 0) return;
        const ext = mime.includes("webm") ? "webm" : "ogg";
        setThinking(true);
        setIsStreaming(true);
        setMessages((prev) => [...prev, { role: "user", text: "[Transcribing...]" }]);
        const fd = new FormData();
        fd.append("file", blob, `voice.${ext}`);
        try {
          const resp = await fetch(STT_API, { method: "POST", body: fd });
          const data = await resp.json();
          const transcript = (data.transcript || "").trim();
          if (transcript && !transcript.startsWith("[STT")) {
            const gen = ++genRef.current;
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = { role: "user", text: transcript };
              return updated;
            });
            send({ type: "text", payload: transcript, gen });
          } else {
            setThinking(false);
            setIsStreaming(false);
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = { role: "system", text: "No speech detected" };
              return updated;
            });
          }
        } catch {
          setThinking(false);
          setIsStreaming(false);
        }
      };
      recorder.start();
      setRecording(true);
      setInterim("Recording...");
    } catch {
      setRecording(false);
      setInterim("");
    }
  }

  async function toggleScreenShare() {
    if (sharing) {
      if (shareIntervalRef.current) { clearInterval(shareIntervalRef.current); shareIntervalRef.current = null; }
      if (screenStreamRef.current) { screenStreamRef.current.getTracks().forEach((t) => t.stop()); screenStreamRef.current = null; }
      setSharing(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: { width: 1280, height: 720 } });
      screenStreamRef.current = stream;
      stream.getVideoTracks()[0].onended = () => {
        if (shareIntervalRef.current) clearInterval(shareIntervalRef.current);
        screenStreamRef.current = null;
        setSharing(false);
      };
      const video = document.createElement("video");
      video.srcObject = stream;
      await video.play();
      const canvas = document.createElement("canvas");
      canvas.width = 640;
      canvas.height = 360;
      const ctx = canvas.getContext("2d")!;
      shareIntervalRef.current = setInterval(() => {
        if (screenStreamRef.current?.active) {
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          const jpeg = canvas.toDataURL("image/jpeg", 0.5).split(",")[1];
          send({ type: "frame", payload: jpeg, mime_type: "image/jpeg" });
        }
      }, 500);
      setSharing(true);
    } catch {
      setSharing(false);
    }
  }

  const displayMessages = showAll ? messages : messages.slice(-20);

  return (
    <AnimatePresence>
      {isPanelOpen && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 20 }}
          transition={{ duration: 0.2 }}
          className="fixed inset-0 z-50 flex flex-col pointer-events-auto
                     bg-[#0d0d11]/95 backdrop-blur-xl overflow-hidden"
        >
          {/* Header */}
          <div className="flex items-center gap-3 px-5 py-3 border-b border-white/5 shrink-0">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${connected ? "bg-blue-500" : "bg-red-500"}`} />
              <span className="text-sm font-semibold text-white">Gemini</span>
            </div>
            <div className="flex items-center gap-1 ml-auto">
              <button
                onClick={() => {
                  localStorage.removeItem("ai_session_id");
                  window.location.reload();
                }}
                className="px-2.5 py-1 text-[10px] font-mono text-white/40 hover:text-white/70 bg-white/5 border border-white/10 rounded-full hover:bg-white/10 transition-colors mr-2 shrink-0"
              >
                new session
              </button>
              <button
                onClick={() => setMode("chat")}
                className={`px-3 py-1 text-[11px] font-medium rounded-full transition-colors ${
                  mode === "chat"
                    ? "bg-blue-500/20 text-blue-400 border border-blue-500/30"
                    : "text-text-muted hover:text-text-primary"
                }`}
              >
                Chat
              </button>
              <button
                onClick={() => setMode("live")}
                className={`px-3 py-1 text-[11px] font-medium rounded-full transition-colors ${
                  mode === "live"
                    ? "bg-red-500/20 text-red-400 border border-red-500/30"
                    : "text-text-muted hover:text-text-primary"
                }`}
              >
                Live
              </button>
            </div>
            <button
              onClick={toggleAudioMuted}
              className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-white/5 transition-colors"
            >
              {isAudioMuted ? <VolumeX size={14} /> : <Volume2 size={14} />}
            </button>
            <button
              onClick={doInterrupt}
              className="p-1.5 rounded-lg text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-colors"
              title="Interrupt"
            >
              <Square size={14} />
            </button>
            <button
              onClick={() => setIsDeviceOpen(!isDeviceOpen)}
              className={`p-1.5 rounded-lg transition-colors ${isDeviceOpen ? "text-white/70 bg-white/5" : "text-white/40 hover:text-white/70 hover:bg-white/5"}`}
              title="Device Control"
            >
              <Smartphone size={14} />
            </button>
            <button
              onClick={() => setPanelOpen(false)}
              className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-white/5 transition-colors"
            >
              <X size={14} />
            </button>
          </div>

          {/* Device pane inline */}
          {isDeviceOpen && (
            <div className="border-b border-white/5 max-h-48 overflow-y-auto">
              <DevicePane sessionId={sessionId} />
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-text-muted select-none">
                <p className="text-sm font-medium">Ask anything</p>
                <p className="text-xs mt-1">Type a message or use voice input</p>
              </div>
            )}

            {!showAll && messages.length > 20 && (
              <button
                onClick={() => setShowAll(true)}
                className="w-full py-2 text-[11px] text-text-muted hover:text-text-primary bg-white/5 rounded-lg transition-colors"
              >
                Show earlier messages ({messages.length - 20} more)
              </button>
            )}

            {displayMessages.map((msg, i) => (
              <div
                key={i}
                className={`animate-fade-in flex ${
                  msg.role === "user" ? "justify-end" :
                  msg.role === "system" ? "justify-center" : "justify-start"
                }`}
              >
                {msg.role === "user" ? (
                  <div className="max-w-[80%] px-4 py-2.5 rounded-2xl bg-user-bubble text-sm text-text-primary leading-relaxed">
                    {msg.text}
                  </div>
                ) : msg.role === "system" ? (
                  <div className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] text-text-muted bg-white/5 rounded-full border border-white/10">
                    {msg.text}
                  </div>
                ) : (
                  <div className="group max-w-[85%] px-4 py-3 rounded-2xl bg-white/5 border border-white/5 text-sm text-text-primary leading-relaxed">
                    {msg.text}
                    {msg.interrupted && (
                      <span className="ml-2 inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium text-yellow-500 bg-yellow-500/10 rounded-full">
                        interrupted
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}

            {thinking && (
              <div className="animate-fade-in flex justify-start">
                <div className="px-4 py-1 rounded-2xl bg-white/5 border border-white/5">
                  <TypingIndicator />
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <form
            onSubmit={handleSubmit}
            className="px-4 py-3 border-t border-white/5 bg-[#0d0d11]/60 shrink-0"
          >
            <div className="flex items-end gap-2 max-w-full">
              <button
                type="button"
                onClick={mode === "live" ? toggleLiveMic : (recording ? stopVoice : startVoice)}
                disabled={mode !== "live" && readyState !== WebSocket.OPEN}
                className={`p-2.5 rounded-lg transition-all duration-200 ${
                  recording || isLiveActive
                    ? "bg-red-500/20 text-red-400"
                    : "text-text-muted hover:text-text-primary hover:bg-white/5"
                } disabled:opacity-20`}
              >
                {isLiveActive ? (
                  <div className="flex items-end gap-0.5 h-4">
                    <span className="w-0.5 bg-red-400 rounded-full animate-pulse h-3" />
                    <span className="w-0.5 bg-red-400 rounded-full animate-pulse h-4" />
                    <span className="w-0.5 bg-red-400 rounded-full animate-pulse h-2" />
                  </div>
                ) : (
                  <Mic size={16} />
                )}
              </button>
              <button
                type="button"
                onClick={toggleScreenShare}
                disabled={readyState !== WebSocket.OPEN}
                className={`p-2.5 rounded-lg transition-all duration-200 ${
                  sharing
                    ? "bg-green-500/20 text-green-400"
                    : "text-text-muted hover:text-text-primary hover:bg-white/5"
                } disabled:opacity-20`}
              >
                <Monitor size={16} />
              </button>
              <div className="flex-1 relative">
                <input
                  className="w-full px-4 py-2.5 bg-white/5 border border-white/10 rounded-xl text-sm text-white placeholder-white/30 outline-none transition-colors focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 disabled:opacity-20"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={interim || "Message..."}
                  disabled={readyState !== WebSocket.OPEN}
                />
              </div>
              <button
                type="submit"
                disabled={readyState !== WebSocket.OPEN || !input.trim()}
                className="p-2.5 rounded-xl bg-blue-600 text-white transition-all hover:bg-blue-500 disabled:opacity-20"
              >
                <Send size={16} />
              </button>
            </div>
          </form>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
