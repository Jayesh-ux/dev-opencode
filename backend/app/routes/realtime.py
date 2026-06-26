import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from fastapi import HTTPException

from app.services.context_merger import merge_context, merge_context_with_security
from app.services.gemini import StreamError
from app.services.gemini_bidi import create_bidi_client, create_live_client
from app.services.token_monitor import token_monitor
from app.services import device_manager
from app.services.security_scanner import full_scan, get_security_gate_prompt
from app.services.ws_manager import pool, sessions

logger = logging.getLogger(__name__)
router = APIRouter(tags=["realtime"])

TRIGGER_PHRASE = "generate an opencode prompt"


@router.websocket("/ws/research")
async def research_session(ws: WebSocket):
    await ws.accept()
    session_id = ws.query_params.get("session_id") or str(uuid.uuid4())[:8]
    pool.add_research(session_id, ws)
    sessions.ensure(session_id)

    await ws.send_json({"type": "session_started", "session_id": session_id})

    bidi = await create_bidi_client()
    stream_task: asyncio.Task | None = None

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type", "text")

            if msg_type in ("text", "interrupt", "voice_start"):
                if stream_task and not stream_task.done():
                    stream_task.cancel()
                    stream_task = None
                    await ws.send_json({"type": "interrupted"})

                if msg_type == "text":
                    text = data.get("payload", "")
                    gen = data.get("gen", 0)
                    if not text.strip():
                        continue

                    sessions.add_message(session_id, "user", text)

                    if TRIGGER_PHRASE in text.lower():
                        await ws.send_json({"type": "trigger_detected", "payload": "Merging context for OpenCode..."})
                        history = sessions.get_formatted_history(session_id)
                        prompt, error, findings = await merge_context_with_security(history)
                        sessions.set_context(session_id, "last_opencode_prompt", prompt)
                        sessions.add_message(session_id, "system", "[Generated OpenCode prompt]")
                        await pool.broadcast_opencode(session_id, {
                            "type": "prompt_injection",
                            "payload": prompt,
                            "session_id": session_id,
                        })
                        msg = "Context merged. OpenCode prompt generated in the execution pane."
                        if findings:
                            msg += f" ⚠ {len(findings)} security issue(s) found."
                        await ws.send_json({
                            "type": "assistant",
                            "payload": msg,
                            "gen": gen,
                        })
                    else:
                        stream_task = asyncio.create_task(
                            _stream_research_response(ws, bidi, session_id, text, gen)
                        )

            elif msg_type == "check_tokens":
                result = token_monitor.check_session(session_id)
                if result:
                    await ws.send_json({
                        "type": "token_report",
                        **result,
                    })

            elif msg_type == "audio":
                if stream_task and not stream_task.done():
                    stream_task.cancel()
                    stream_task = None
                    await ws.send_json({"type": "interrupted"})
                payload = data.get("payload", "")
                mime = data.get("mime_type", "audio/pcm;rate=16000")
                await bidi.send_audio(payload, mime)
                sessions.add_message(session_id, "user", "[Audio input]")

            elif msg_type == "frame":
                payload = data.get("payload", "")
                mime = data.get("mime_type", "image/jpeg")
                await bidi.send_frame(payload, mime)

            elif msg_type == "ping":
                await ws.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info("Research WS disconnected: %s", session_id)
    except Exception as e:
        logger.error("Research WS error [%s]: %s", session_id, e)
    finally:
        if stream_task and not stream_task.done():
            stream_task.cancel()
        pool.remove_research(session_id)
        await bidi.disconnect()


async def _stream_research_response(ws: WebSocket, bidi, session_id: str, user_text: str, gen: int = 0):
    try:
        if hasattr(bidi, "process_text_stream"):
            accumulated = ""
            for chunk in bidi.process_text_stream(user_text):
                accumulated += chunk
                await ws.send_json({"type": "assistant_chunk", "payload": chunk, "gen": gen})
                await asyncio.sleep(0)

            if accumulated:
                sessions.add_message(session_id, "assistant", accumulated)
                await ws.send_json({"type": "assistant", "payload": accumulated, "gen": gen})
                trigger_check = accumulated.lower()
                if TRIGGER_PHRASE in trigger_check:
                    await _handle_trigger_from_response(ws, session_id, accumulated)
            await _check_tokens_inline(ws, session_id)
            return

        if hasattr(bidi, "process_text"):
            result = bidi.process_text(user_text)
            if result.text:
                sessions.add_message(session_id, "assistant", result.text)
                await ws.send_json({"type": "assistant", "payload": result.text, "gen": gen})
                trigger_check = result.text.lower()
                if TRIGGER_PHRASE in trigger_check:
                    await _handle_trigger_from_response(ws, session_id, result.text)
            await _check_tokens_inline(ws, session_id)
            return

        turn_complete = False
        accumulated = ""
        while not turn_complete:
            reply = await bidi.receive()
            if reply is None:
                break
            if "text" in reply and reply["text"]:
                accumulated += reply["text"]
                await ws.send_json({"type": "assistant_chunk", "payload": reply["text"], "gen": gen})
                await asyncio.sleep(0)
                turn_complete = reply.get("turn_complete", False)
            elif "tool_call" in reply:
                await ws.send_json({"type": "tool_call", "payload": reply["tool_call"]})
                turn_complete = True
            else:
                turn_complete = True

        if accumulated:
            sessions.add_message(session_id, "assistant", accumulated)
            trigger_check = accumulated.lower()
            if TRIGGER_PHRASE in trigger_check:
                await _handle_trigger_from_response(ws, session_id, accumulated)
        await _check_tokens_inline(ws, session_id)

    except asyncio.CancelledError:
        logger.warning("Stream interrupted [%s]", session_id)
        raise


async def _check_tokens_inline(ws: WebSocket, session_id: str):
    result = token_monitor.check_session(session_id)
    if result and result.get("triggered"):
        try:
            await ws.send_json({
                "type": "token_warning",
                "pct": result["pct"],
                "total_tokens": result["total_tokens"],
                "max_tokens": result["max_tokens"],
                "snapshot": result.get("snapshot_file", ""),
            })
        except Exception:
            pass


async def _handle_trigger_from_response(ws: WebSocket, session_id: str, response_text: str):
    await ws.send_json({"type": "trigger_detected", "payload": "Trigger detected in model response. Merging context..."})
    history = sessions.get_formatted_history(session_id)
    prompt, error, findings = await merge_context_with_security(history)
    sessions.set_context(session_id, "last_opencode_prompt", prompt)
    sessions.add_message(session_id, "system", "[Generated OpenCode prompt]")
    await pool.broadcast_opencode(session_id, {
        "type": "prompt_injection",
        "payload": prompt,
        "session_id": session_id,
    })


@router.websocket("/ws/opencode")
async def opencode_session(ws: WebSocket):
    await ws.accept()
    session_id = ws.query_params.get("session_id") or str(uuid.uuid4())[:8]
    pool.add_opencode(session_id, ws)
    sessions.ensure(session_id)

    await ws.send_json({"type": "opencode_ready", "session_id": session_id})

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type", "")

            if msg_type == "ping":
                await ws.send_json({"type": "pong"})
            elif msg_type == "get_history":
                sid = data.get("session_id", session_id)
                history = sessions.get_context(sid).get("last_opencode_prompt", "No prompts yet")
                await ws.send_json({"type": "history", "payload": history})
            elif msg_type == "log":
                sessions.add_message(data.get("session_id", session_id), "system", f"[OpenCode] {data.get('payload', '')}")

    except WebSocketDisconnect:
        logger.info("OpenCode WS disconnected: %s", session_id)
    except Exception as e:
        logger.error("OpenCode WS error [%s]: %s", session_id, e)
    finally:
        pool.remove_opencode(session_id)


LIVE_VOICES = {"Puck", "Charon", "Aoede", "Fenrir", "Kore"}


@router.websocket("/ws/live")
async def live_session(ws: WebSocket):
    await ws.accept()
    voice = ws.query_params.get("voice", "Puck")
    if voice not in LIVE_VOICES:
        voice = "Puck"

    live = await create_live_client(voice)
    await ws.send_json({"type": "live_connected", "voice": voice})

    async def client_to_gemini():
        try:
            while True:
                raw = await ws.receive_text()
                data = json.loads(raw)
                msg_type = data.get("type", "")
                if msg_type == "audio":
                    mime = data.get("mime_type", "audio/pcm")
                    await live.send_audio(data.get("data", ""), mime)
                elif msg_type == "text":
                    await live.send_text(data.get("payload", ""))
                elif msg_type == "disconnect":
                    break
        except WebSocketDisconnect:
            logger.info("live client_to_gemini: client disconnected")
            raise
        except Exception as e:
            logger.error("live client_to_gemini: %s", e)

    async def gemini_to_client():
        try:
            while live.connected:
                result = await live.receive()
                if result is None:
                    break
                if result.get("type") == "setup_complete":
                    continue
                if result.get("type") == "error":
                    try:
                        await ws.send_json(result)
                    except WebSocketDisconnect:
                        raise
                    if result.get("code") in ("RATE_LIMIT_EXCEEDED", "CONNECTION_LOST"):
                        logger.warning("Gemini error, exiting relay: %s", result.get("code"))
                        break
                    continue
                if result.get("interrupted"):
                    try:
                        await ws.send_json({"type": "interrupted"})
                    except WebSocketDisconnect:
                        raise
                if result.get("turn_complete"):
                    try:
                        await ws.send_json({"type": "turn_complete"})
                    except WebSocketDisconnect:
                        raise
                if "audio" in result:
                    try:
                        await ws.send_json({"type": "audio", "data": result["audio"]})
                    except WebSocketDisconnect:
                        raise
                if "text" in result:
                    try:
                        await ws.send_json({"type": "text", "data": result["text"]})
                    except WebSocketDisconnect:
                        raise
                if "tool_call" in result:
                    try:
                        await ws.send_json({"type": "tool_call", "payload": result["tool_call"]})
                    except WebSocketDisconnect:
                        raise
        except WebSocketDisconnect:
            logger.info("live gemini_to_client: client disconnected")
            raise
        except Exception as e:
            logger.error("live gemini_to_client: %s", e)

    tasks = [
        asyncio.create_task(client_to_gemini(), name="client_to_gemini"),
        asyncio.create_task(gemini_to_client(), name="gemini_to_client"),
    ]

    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        results = await asyncio.gather(*pending, return_exceptions=True)
        for t, r in zip(pending, results):
            if isinstance(r, Exception):
                logger.error("Task %s raised: %s", t.get_name(), r)
                try:
                    await ws.send_json({"type": "error", "code": "TASK_CRASHED", "detail": str(r)})
                except Exception:
                    pass
    except Exception as e:
        logger.error("Live orchestration crashed: %s", e)
        try:
            await ws.send_json({"type": "error", "code": "ORCHESTRATION_ERROR", "detail": str(e)})
        except Exception:
            pass
    finally:
        await live.disconnect()


""" ---------- Device Debugging API ---------- """


@router.get("/api/tools/capabilities")
async def tool_capabilities():
    return device_manager.capabilities()


@router.post("/api/tools/adb/devices")
async def api_adb_devices():
    return await device_manager.adb_devices()


@router.post("/api/tools/adb/shell")
async def api_adb_shell(command: str, device: str | None = None):
    return await device_manager.adb_shell(command, device=device)


@router.post("/api/tools/adb/install")
async def api_adb_install(apk_path: str, device: str | None = None):
    return await device_manager.adb_install(apk_path, device=device)


@router.post("/api/tools/adb/logcat")
async def api_adb_logcat(device: str | None = None, filter_expr: str = "*:I", lines: int = 100):
    return await device_manager.adb_logcat(device=device, filter_expr=filter_expr, lines=lines)


@router.post("/api/tools/adb/screenshot")
async def api_adb_screenshot(device: str | None = None):
    return await device_manager.adb_screenshot(device=device)


@router.post("/api/tools/adb/start")
async def api_adb_start(package: str, activity: str, device: str | None = None):
    return await device_manager.adb_start_activity(package, activity, device=device)


@router.post("/api/tools/adb/stop")
async def api_adb_stop(package: str, device: str | None = None):
    return await device_manager.adb_force_stop(package, device=device)


@router.post("/api/tools/playwright/launch")
async def api_pw_launch(headless: bool = True):
    return await device_manager.playwright_launch(headless=headless)


@router.post("/api/tools/playwright/navigate")
async def api_pw_navigate(url: str):
    return await device_manager.playwright_navigate(url)


@router.post("/api/tools/playwright/screenshot")
async def api_pw_screenshot(full_page: bool = False):
    return await device_manager.playwright_screenshot(full_page=full_page)


@router.post("/api/tools/playwright/evaluate")
async def api_pw_evaluate(js: str):
    return await device_manager.playwright_evaluate(js)


@router.post("/api/tools/playwright/html")
async def api_pw_html(url: str = "about:blank"):
    return await device_manager.playwright_html(url=url)


@router.post("/api/tools/playwright/close")
async def api_pw_close():
    return await device_manager.playwright_close()


""" ---------- Security Gate ---------- """


@router.post("/api/tools/security/scan")
async def api_security_scan(path: str | None = None):
    return await full_scan(path=path)


@router.websocket("/ws/device")
async def device_log_stream(ws: WebSocket):
    await ws.accept()
    session_id = ws.query_params.get("session_id") or str(uuid.uuid4())[:8]
    pool.add_opencode(session_id, ws)
    sessions.ensure(session_id)

    await ws.send_json({
        "type": "device_ready",
        "session_id": session_id,
        "capabilities": device_manager.capabilities(),
    })

    device = ws.query_params.get("device") or None
    action = ws.query_params.get("action", "logcat")

    logcat_gen = None
    try:
        if action == "logcat":
            filter_expr = ws.query_params.get("filter", "*:I")
            logcat_gen = device_manager.stream_logcat(device=device, filter_expr=filter_expr)
            async for line in logcat_gen:
                try:
                    await ws.send_json(line)
                    text = line.get("payload", "")
                    if text.strip():
                        await pool.broadcast_opencode(session_id, {
                            "type": "logcat",
                            "payload": text,
                            "session_id": session_id,
                        })
                except WebSocketDisconnect:
                    raise
                except Exception:
                    break
        elif action == "shell":
            command = ws.query_params.get("command", "")
            if command:
                result = await device_manager.adb_shell(command, device=device, timeout=30)
                result["type"] = "shell_result"
                await ws.send_json(result)
                await pool.broadcast_opencode(session_id, {
                    "type": "device_shell",
                    "payload": result.get("stdout", ""),
                    "session_id": session_id,
                })
        elif action == "screenshot":
            result = await device_manager.adb_screenshot(device=device)
            result["type"] = "screenshot_result"
            await ws.send_json(result)
        else:
            await ws.send_json({"type": "error", "payload": f"Unknown action: {action}"})
    except WebSocketDisconnect:
        logger.info("Device WS disconnected: %s", session_id)
    except Exception as e:
        logger.error("Device WS error [%s]: %s", session_id, e)
    finally:
        if logcat_gen is not None:
            try:
                await logcat_gen.aclose()
            except Exception:
                pass
        pool.remove_opencode(session_id)
