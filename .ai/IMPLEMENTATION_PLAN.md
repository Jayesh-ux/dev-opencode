# Implementation Plan

## Architecture

```
User (Voice/Text)
    |
    v
[Next.js Frontend] --HTTP/WS--> [FastAPI Backend] --API--> [Gemini AI]
    |                               |
    v                               v
[Browser UI]               [Python Services]
```

## Phases

### Phase 1: Foundation
Set up both projects with proper configuration, create the state management layer, and integrate the Gemini API key.

### Phase 2: Voice Control Loop
Build real-time voice capture on the frontend, speech-to-text and text-to-speech endpoints on the backend, and wire them together.

### Phase 3: AI Integration
Implement Gemini chat completions with conversation memory, establishing the core AI control loop.

### Phase 4: Polish & Deploy
Add error handling, loading states, tests, and deployment configuration.

## Key Design Decisions
- FastAPI for async Python backend (supports WebSocket for real-time voice)
- Next.js App Router for modern React frontend
- Gemini API for both text and multimodal (voice) interactions
- .ai/ directory as the source of truth for project state
