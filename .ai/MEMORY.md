# MEMORY

This file tracks the evolving context, decisions, and state of the project.

## Project Summary

- **Project:** Voice-controlled AI assistant with Next.js frontend + FastAPI backend
- **Status:** Phase 8 — device tooling (ADB + system Chromium) integrated into workspace, OWASP Top 10 security gate auto-injected into OpenCode pipeline
- **Last Updated:** 2026-06-24

## Key Decisions

- Next.js with App Router + Tailwind for frontend
- FastAPI with pydantic v1 (no Rust needed on this platform) for backend
- Gemini API via direct HTTP requests + Live WebSocket (BidiGenerateContent)
- .ai/ directory as DAG-based state management
- Cyclic state loop: LISTEN → THINK → ACT → OBSERVE → (repeat or PAUSED)
- **Memory rotation**: Proactive context trimming at 65% token threshold → summarize → archive → reset
- **Self-prompting**: System prompt with autonomous instructions + task tracking injected before each THINK cycle

## Architecture (Phase 8)

```
page.tsx
  └── FloatingWorkspace (manages sessionId, sheet state, floating widget)
       ├── Floating icon (framer-motion drag + gsap idle float)
       └── Sheet (85vh overlay)
            ├── Header (session ID, close, token bar)
            ├── ResearchPane compact (chat history + input + live audio)
            ├── TAP TO INTERRUPT button
            │    → speechSynthesis.cancel()
            │    → LiveAudioSession.interrupt() (flushes audio queue + sends interrupt WS)
            │    → research WS {"type": "interrupt"}
            │    → resets liveAccumRef
            ├── DevicePane (collapsible — ADB + Chromium controls)
            │    ├── List Devices, Screenshot, Battery, Get HTML, Logcat
            │    └── Output area with log/status/screenshot display
            └── Collapsible OpenCode terminal
                 → OpenCodePane compact (log streams via /ws/opencode)
```

## Security Gate Pipeline

```
User sends "generate an opencode prompt"
  → merge_context_with_security()
     → context_merger.merge_context() [Gemini or local fallback]
     → security_scanner.scan_directory() [OWASP patterns + npm audit]
     → get_security_gate_prompt() [appends findings as gate block]
  → prompt_injection sent to OpenCode pane + security findings reported
```

## Current State

- [x] Phase 1-6 complete: full-stack voice assistant with Gemini API, cyclic loop, task tracker, memory rotation
- [x] Floating workspace with draggable sparkles icon + GSAP idle animation
- [x] Sheet overlay replaces split-screen dual pane
- [x] ResearchPane compact mode (no redundant header when embedded)
- [x] OpenCodePane compact mode (no redundant header when embedded)
- [x] Tap to Interrupt button: speechSynthesis + live audio flush + WS interrupt + accumulator reset
- [x] LiveAudioSession public interrupt() method
- [x] Backend connection safeguards: rate limit detection, structured error JSON, telemetry logging
- [x] Frontend exponential backoff reconnection (1.5s init, 10s max, 3 attempts)
- [x] Phase 8 complete: ADB installed and verified, Playwright replaced with system Chromium subprocess, DevicePane UI in workspace
- [x] Security Scanner with OWASP Top 10 regex patterns + npm/pip dependency audit in OpenCode pipeline

## Session Flow

1. User opens page → sees clean viewport with floating sparkles icon
2. Tap icon → 85vh sheet workspace opens
3. Chat section shows full Gemini conversation history + text/audio input
4. Live/Chat toggle switches between SSE text mode and Gemini Live WebSocket mode
5. "TAP TO INTERRUPT" button halts model mid-sentence: stops TTS, flushes audio queue, sends interrupt WS packet
6. OpenCode Terminal toggle shows collapsable log monitor from /ws/opencode
7. Copy & Pipe sends model responses to the OpenCode pane as execution prompts

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /api/chat | Send message (runs state loop) |
| GET | /api/chat/status | Loop state + memory + tasks + tools + tokens |
| POST | /api/chat/resume | Resume from PAUSED |
| POST | /api/chat/tools | Execute a specific tool |
| GET | /api/chat/tools | List available tools |
| POST | /api/voice/stt | Speech-to-text (upload audio, get transcript) |
| POST | /api/voice/transcribe | Alias for /api/voice/stt |
| POST | /api/voice/tts | Text-to-speech (get WAV audio) |
| WS | /ws/research | Research SSE text session |
| WS | /ws/opencode | OpenCode log + prompt injection session |
| WS | /ws/live | Gemini Live bidirectional audio WebSocket |
| POST | /api/tools/capabilities | Device tool capabilities (ADB + Playwright) |
| POST | /api/tools/adb/devices | List connected ADB devices |
| POST | /api/tools/adb/shell | Execute ADB shell command |
| POST | /api/tools/adb/install | Install APK via ADB |
| POST | /api/tools/adb/logcat | Fetch ADB logcat |
| POST | /api/tools/adb/screenshot | ADB screencap (base64 PNG) |
| POST | /api/tools/adb/start | Start Android activity |
| POST | /api/tools/adb/stop | Force-stop Android app |
| POST | /api/tools/playwright/launch | Launch headless Chromium |
| POST | /api/tools/playwright/navigate | Navigate to URL |
| POST | /api/tools/playwright/screenshot | Chromium screenshot |
| POST | /api/tools/playwright/evaluate | Execute JS in Chromium |
| POST | /api/tools/playwright/html | Get page HTML |
| POST | /api/tools/playwright/close | Close headless session |
| POST | /api/tools/security/scan | Full OWASP + dependency scan |
| WS | /ws/device | Stream ADB logcat / shell / screenshot |

## Key Files

| File | Purpose |
|------|---------|
| `frontend/components/FloatingWorkspace.tsx` | Root workspace — floating widget + sheet + interrupt + embedded panes |
| `frontend/components/ResearchPane.tsx` | Chat messages, WS connection, live audio, voice input |
| `frontend/components/OpenCodePane.tsx` | OpenCode terminal logs |
| `frontend/lib/live-audio.ts` | LiveAudioSession class for bidirectional audio WS |
| `frontend/lib/use-websocket.ts` | Generic WebSocket React hook |
| `frontend/components/ui/sheet.tsx` | Radix Dialog-based bottom sheet |
| `frontend/components/DevicePane.tsx` | Device control panel (ADB + Playwright actions) |
| `backend/app/services/device_manager.py` | ADB + Chromium subprocess wrapper (runtime binary detection) |
| `backend/app/services/security_scanner.py` | OWASP Top 10 regex scan + npm/pip dependency audit |
| `backend/app/services/context_merger.py` | OpenCode prompt synthesis with auto-injected security gate |
| `backend/app/routes/realtime.py` | WS routes for research, opencode, and live sessions; device + security REST endpoints |
| `backend/app/services/gemini_bidi.py` | LiveSession + ResearchSession classes for Gemini interaction |
