# TODO (DAG Format)

Dependencies are listed in brackets after each task.

## Phase 1: Foundation ✓
- [x] P1-T1: Initialize Next.js frontend []
- [x] P1-T2: Initialize FastAPI backend []
- [x] P1-T3: Create .ai/ state management structure []
- [x] P1-T4: Integrate Gemini API key [P1-T2]

## Phase 2: Core Orchestration ✓
- [x] P2-T1: Build cyclic state loop (LISTEN→THINK→ACT→OBSERVE) [P1-T1]
- [x] P2-T2: Build memory snapshotter (429 + 70% token triggers) [P1-T2, P1-T4]
- [x] P2-T3: Implement session recovery from snapshots [P2-T2]
- [x] P2-T4: Wire snapshot triggers into state loop [P2-T1, P2-T2]

## Phase 3: Tool Framework + UI Integration ✓
- [x] P3-T1: Build tool execution framework (execute, read, write, ls) [P2-T1]
- [x] P3-T2: Add tool registry and sandboxing [P3-T1]
- [x] P3-T3: Wire tool execution into ACT phase [P3-T1, P2-T1]
- [x] P3-T4: Frontend status indicator + token bar + resume UI [P1-T1]
- [x] P3-T5: Frontend tool results display [P3-T3, P3-T4]

## Phase 4: Voice Control Loop ✓
- [x] P4-T1: Build voice capture module (MediaRecorder) [P3-T3]
- [x] P4-T2: Build speech-to-text endpoint (Gemini multimodal) [P1-T2, P1-T4]
- [x] P4-T3: Build text-to-speech endpoint (WAV generation) [P1-T2]
- [x] P4-T4: Frontend voice UI (record button, transcript, SpeechSynthesis) [P4-T1, P4-T2, P4-T3]

## Phase 5: Memory Manager + Self-Prompting ✓
- [x] P5-T1: Build MemoryManager with context rotation [P2-T2]
- [x] P5-T2: Auto-summarize + archive old frames to .ai/MEMORY/ [P5-T1]
- [x] P5-T3: Build TaskTracker for autonomous task management [P1-T4]
- [x] P5-T4: Inject self-prompting system prompt before each cycle [P2-T1, P5-T3]
- [x] P5-T5: Frontend task progress bar + memory stats display [P3-T4, P5-T1]

## Phase 6: Polish & Deploy ✓
- [x] P6-T1: Error handling & loading states [P4-T4, P5-T4]
- [x] P6-T2: Testing & QA [P6-T1]
- [x] P6-T3: Deployment configuration [P6-T2]

## Phase 7: Floating Overlay Workspace (IN PROGRESS)
- [x] P7-T1: Create FloatingWorkspace with framer-motion drag + GSAP idle animation []
- [x] P7-T2: Eliminate SplitScreen.tsx, use single clean viewport [P7-T1]
- [x] P7-T3: Embed ResearchPane + OpenCodePane in 85vh sheet with compact mode [P7-T2]
- [x] P7-T4: Tap to Interrupt kill-switch button (speechSynthesis + WS interrupt + audio flush) [P7-T3]
- [x] P7-T5: Backend connection safeguards (rate limit detection, structured error JSON) [P6-T1]
- [x] P7-T6: Frontend exponential backoff WebSocket reconnection [P7-T3]
- [x] P7-T7: Telemetry logging (turn latency in backend + frontend) [P7-T5]
- [x] P7-T8: Build + typecheck passes with zero errors []
- [x] P7-T9: TokenMonitor background service (30s interval, 70% threshold, auto-snapshot) [P7-T5]
- [x] P7-T10: Frontend token usage bar + snapshot indicator in workspace header [P7-T9, P7-T3]
- [x] P7-T11: Inline token check after each assistant response in /ws/research [P7-T9]

## Phase 8: Device Tooling + Security Gate (COMPLETE)
- [x] P8-T1: Install ADB binary in PRoot environment []
- [x] P8-T2: Make device_manager.py detect ADB/Chromium at runtime (not import time) [P8-T1]
- [x] P8-T3: Refactor Playwright support to use system Chromium via subprocess (no Python package) []
- [x] P8-T4: Create DevicePane.tsx frontend component (list devices, screenshot, get HTML, logcat, battery) [P7-T1]
- [x] P8-T5: Integrate DevicePane into FloatingWorkspace.tsx sheet [P8-T4]
- [x] P8-T6: Build SecurityScanner service (OWASP Top 10 regex patterns + npm/pip dependency audit) []
- [x] P8-T7: Add REST endpoint `/api/tools/security/scan` [P8-T6]
- [x] P8-T8: Auto-integrate security scanning into OpenCode prompt generation pipeline [P8-T6, P7-T3]
- [x] P8-T9: Frontend build passes with zero errors (TypeScript + ESLint) []
- [x] P8-T10: All device/security endpoints verified end-to-end [P8-T1, P8-T3, P8-T6]
