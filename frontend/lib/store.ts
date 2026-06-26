"use client";

import { create } from "zustand";

export interface TaskItem {
  step: number;
  status: string;
  description: string;
}

export type SessionState = "LISTEN" | "THINK" | "ACT" | "OBSERVE" | "PAUSED";
export type ConnectionStatus = "connected" | "disconnected" | "reconnecting";
export type Mode = "chat" | "live";

interface AppState {
  sessionId: string;
  setSessionId: (id: string) => void;

  isStreaming: boolean;
  setIsStreaming: (v: boolean) => void;

  isPlaying: boolean;
  setIsPlaying: (v: boolean) => void;

  orbActive: boolean;
  setOrbActive: (v: boolean) => void;

  tokenPct: number;
  tokenTotal: number;
  setTokenUsage: (pct: number, total: number) => void;

  taskProgress: number;
  taskList: TaskItem[];
  setTasks: (progress: number, tasks: TaskItem[]) => void;

  sessionState: SessionState;
  setSessionState: (s: SessionState) => void;

  connectionStatus: ConnectionStatus;
  setConnectionStatus: (s: ConnectionStatus) => void;

  floatingText: string;
  setFloatingText: (t: string) => void;

  isPanelOpen: boolean;
  setPanelOpen: (v: boolean) => void;

  mode: Mode;
  setMode: (m: Mode) => void;

  isAudioMuted: boolean;
  toggleAudioMuted: () => void;

  geminiConnected: boolean;
  setGeminiConnected: (v: boolean) => void;

  opencodeConnected: boolean;
  setOpencodeConnected: (v: boolean) => void;
}

export const useStore = create<AppState>((set) => ({
  sessionId: "",
  setSessionId: (id) => set({ sessionId: id }),

  isStreaming: false,
  setIsStreaming: (v) => set({ isStreaming: v }),

  isPlaying: false,
  setIsPlaying: (v) => set({ isPlaying: v }),

  orbActive: false,
  setOrbActive: (v) => set({ orbActive: v }),

  tokenPct: 0,
  tokenTotal: 0,
  setTokenUsage: (pct, total) => set({ tokenPct: pct, tokenTotal: total }),

  taskProgress: 0,
  taskList: [],
  setTasks: (progress, tasks) => set({ taskProgress: progress, taskList: tasks }),

  sessionState: "LISTEN",
  setSessionState: (s) => set({ sessionState: s }),

  connectionStatus: "disconnected",
  setConnectionStatus: (s) => set({ connectionStatus: s }),

  floatingText: "",
  setFloatingText: (t) => set({ floatingText: t }),

  isPanelOpen: false,
  setPanelOpen: (v) => set({ isPanelOpen: v }),

  mode: "chat",
  setMode: (m) => set({ mode: m }),

  isAudioMuted: false,
  toggleAudioMuted: () => set((s) => ({ isAudioMuted: !s.isAudioMuted })),

  geminiConnected: false,
  setGeminiConnected: (v) => set({ geminiConnected: v }),

  opencodeConnected: false,
  setOpencodeConnected: (v) => set({ opencodeConnected: v }),
}));
