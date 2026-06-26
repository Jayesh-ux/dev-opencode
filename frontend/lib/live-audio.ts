"use client";

import { useStore } from "@/lib/store";

const TARGET_SAMPLE_RATE = 16000;
const BUFFER_SIZE = 2048;

const RECONNECT_INITIAL_DELAY = 1500;
const RECONNECT_MAX_DELAY = 10000;
const RECONNECT_MAX_ATTEMPTS = 3;

export interface LiveAudioCallbacks {
  onText: (text: string) => void;
  onInterrupted: () => void;
  onTurnComplete: () => void;
  onConnected: () => void;
  onDisconnected: () => void;
  onError: (error: string) => void;
}

export class LiveAudioSession {
  onMessage: ((msg: Record<string, unknown>) => void) | null = null;
  onError: ((err: string) => void) | null = null;

  private ws: WebSocket | null = null;
  private ctx: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private processor: ScriptProcessorNode | null = null;
  private stream: MediaStream | null = null;
  private playbackQueue: AudioBuffer[] = [];
  private playing = false;
  private stopped = false;
  private callbacks: LiveAudioCallbacks;
  private wsUrl = "";
  private reconnectAttempts = 0;
  private _sendTs = 0;

  constructor(callbacks: LiveAudioCallbacks) {
    this.callbacks = callbacks;
  }

  async start(wsUrl: string): Promise<void> {
    this.stopped = false;
    this.reconnectAttempts = 0;
    this.wsUrl = wsUrl;
    this._connect();
    await this._initCapture();
    await this._initPlayback();
  }

  private _connect(): void {
    if (this.stopped) return;
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.ws = new WebSocket(this.wsUrl);
    this.ws.binaryType = "blob";

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.callbacks.onConnected();
    };

    this.ws.onmessage = (event) => this._handleWsMessage(event.data);

    this.ws.onclose = () => {
      this._cleanupCapture();
      this._flushPlayback();
      if (!this.stopped) {
        this.callbacks.onDisconnected();
        this._tryReconnect();
      }
    };

    this.ws.onerror = () => {
      if (!this.stopped) {
        this.callbacks.onError("Live WebSocket error");
        this.onError?.("Live WebSocket error");
      }
    };
  }

  private _tryReconnect(): void {
    if (this.stopped) return;
    if (this.reconnectAttempts >= RECONNECT_MAX_ATTEMPTS) {
      this.callbacks.onError("Max reconnection attempts reached");
      return;
    }
    this.reconnectAttempts++;
    const delay = Math.min(
      RECONNECT_INITIAL_DELAY * Math.pow(2, this.reconnectAttempts - 1),
      RECONNECT_MAX_DELAY
    );
    console.log(
      `[LiveAudio] reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${RECONNECT_MAX_ATTEMPTS})`
    );
    setTimeout(() => this._connect(), delay);
  }

  stop(): void {
    this.stopped = true;
    this._cleanupCapture();
    this._cleanupPlayback();
    if (this.ws) {
      this.ws.onclose = null;
      if (this.ws.readyState === WebSocket.OPEN) {
        try {
          this.ws.send(JSON.stringify({ type: "disconnect" }));
        } catch {
          // ignore send errors during teardown
        }
      }
      this.ws.close();
      this.ws = null;
    }
  }

  sendText(text: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this._sendTs = performance.now();
      this.ws.send(JSON.stringify({ type: "text", payload: text }));
    }
  }

  interrupt(): void {
    this._flushPlayback();
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "interrupt" }));
    }
  }

  private _handleWsMessage(raw: string): void {
    try {
      const data = JSON.parse(raw);
      this.onMessage?.(data);
      switch (data.type) {
        case "live_connected":
          this.callbacks.onConnected();
          break;
        case "audio":
          useStore.getState().setIsPlaying(true);
          this._enqueueAudio(data.data);
          break;
        case "text":
          this.callbacks.onText(data.data);
          break;
        case "interrupted":
          this._flushPlayback();
          useStore.getState().setIsPlaying(false);
          this.callbacks.onInterrupted();
          break;
        case "turn_complete":
          if (this._sendTs > 0) {
            const latency = performance.now() - this._sendTs;
            console.log(`[LiveAudio] turn latency: ${latency.toFixed(1)}ms`);
            this._sendTs = 0;
          }
          useStore.getState().setIsPlaying(false);
          this.callbacks.onTurnComplete();
          break;
        case "error":
          console.warn(`[LiveAudio] server error: ${data.code} — ${data.detail || ""}`);
          this.callbacks.onError(data.code);
          this.onError?.(data.code);
          break;
      }
    } catch {
      // ignore malformed messages
    }
  }

  /* -------- Capture -------- */

  private async _initCapture(): Promise<void> {
    this.ctx = new AudioContext();
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.processor = this.ctx.createScriptProcessor(BUFFER_SIZE, 1, 1);

    this.processor.onaudioprocess = (e) => {
      if (this.stopped) return;
      const input = e.inputBuffer.getChannelData(0);
      const downsampled = _downsample(input, this.ctx!.sampleRate, TARGET_SAMPLE_RATE);
      const pcm16 = _float32ToPCM16(downsampled);
      const base64 = _arrayBufferToBase64(pcm16);
      if (this.ws?.readyState === WebSocket.OPEN) {
        this._sendTs = this._sendTs || performance.now();
        this.ws.send(JSON.stringify({ type: "audio", data: base64 }));
      }
    };

    this.source.connect(this.processor);
    this.processor.connect(this.ctx.destination);
  }

  private _cleanupCapture(): void {
    if (this.processor) {
      this.processor.disconnect();
      this.processor = null;
    }
    if (this.source) {
      this.source.disconnect();
      this.source = null;
    }
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
    }
    if (this.ctx) {
      this.ctx.close();
      this.ctx = null;
    }
  }

  /* -------- Playback -------- */

  private async _initPlayback(): Promise<void> {
    // reuse the same AudioContext from capture
  }

  private _enqueueAudio(base64Data: string): void {
    if (this.stopped) return;
    const pcm16 = _base64ToArrayBuffer(base64Data);
    const float32 = _pcm16ToFloat32(pcm16);
    if (!this.ctx) return;
    const buffer = this.ctx.createBuffer(1, float32.length, TARGET_SAMPLE_RATE);
    buffer.getChannelData(0).set(float32);
    this.playbackQueue.push(buffer);
    if (!this.playing) this._playNext();
  }

  private _playNext(): void {
    if (this.stopped || this.playbackQueue.length === 0 || !this.ctx) {
      this.playing = false;
      return;
    }
    this.playing = true;
    const buffer = this.playbackQueue.shift()!;
    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.ctx.destination);
    source.onended = () => this._playNext();
    source.start();
  }

  private _flushPlayback(): void {
    this.playbackQueue = [];
    this.playing = false;
  }

  private _cleanupPlayback(): void {
    this._flushPlayback();
  }
}

/* -------- DSP utilities -------- */

function _downsample(buffer: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate === toRate) return buffer;
  const ratio = fromRate / toRate;
  const newLen = Math.round(buffer.length / ratio);
  const out = new Float32Array(newLen);
  for (let i = 0; i < newLen; i++) {
    out[i] = buffer[Math.min(Math.round(i * ratio), buffer.length - 1)];
  }
  return out;
}

function _float32ToPCM16(float32: Float32Array): ArrayBuffer {
  const buf = new ArrayBuffer(float32.length * 2);
  const view = new DataView(buf);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buf;
}

function _arrayBufferToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function _base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const buf = new ArrayBuffer(binary.length);
  const view = new Uint8Array(buf);
  for (let i = 0; i < binary.length; i++) {
    view[i] = binary.charCodeAt(i);
  }
  return buf;
}

function _pcm16ToFloat32(buf: ArrayBuffer): Float32Array {
  const view = new DataView(buf);
  const out = new Float32Array(buf.byteLength / 2);
  for (let i = 0; i < out.length; i++) {
    const int16 = view.getInt16(i * 2, true);
    out[i] = int16 / (int16 < 0 ? 0x8000 : 0x7fff);
  }
  return out;
}
