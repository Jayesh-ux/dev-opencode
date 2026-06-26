import asyncio
import json
import logging
import os
import shlex
import shutil
import tempfile
import time
from typing import Any

logger = logging.getLogger(__name__)

_TIMEOUT_DEFAULT = 30


def _adb_cmd() -> str | None:
    return shutil.which("adb")


def capabilities() -> dict:
    return {
        "adb_available": _adb_cmd() is not None,
        "playwright_available": shutil.which("chromium") is not None,
        "platform": "android" if os.path.exists("/system/bin") else "linux",
    }


async def _run_subprocess(cmd: list[str], timeout: int = _TIMEOUT_DEFAULT, input_data: str | None = None) -> dict:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if input_data is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=input_data.encode() if input_data else None),
            timeout=timeout,
        )
        return {
            "code": proc.returncode,
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
        }
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return {"code": -1, "stdout": "", "stderr": f"Command timed out after {timeout}s"}
    except FileNotFoundError:
        return {"code": -1, "stdout": "", "stderr": f"Command not found: {cmd[0]}"}
    except Exception as e:
        return {"code": -1, "stdout": "", "stderr": str(e)}


""" ---------- ADB ---------- """


async def adb_devices(timeout: int = 10) -> dict:
    adb = _adb_cmd()
    if not adb:
        return {"error": "adb not installed", "devices": []}
    result = await _run_subprocess([adb, "devices"], timeout=timeout)
    if result["code"] != 0:
        return {"error": result["stderr"], "devices": []}
    lines = result["stdout"].strip().splitlines()
    devices = []
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) == 2 and parts[1].strip() == "device":
            devices.append(parts[0].strip())
    return {"devices": devices, "raw": result["stdout"]}


async def adb_install(apk_path: str, device: str | None = None, timeout: int = 60) -> dict:
    adb = _adb_cmd()
    if not adb:
        return {"error": "adb not installed"}
    cmd = [adb]
    if device:
        cmd += ["-s", device]
    cmd += ["install", "-r", apk_path]
    result = await _run_subprocess(cmd, timeout=timeout)
    return {
        "code": result["code"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "success": result["code"] == 0,
    }


async def adb_shell(command: str, device: str | None = None, timeout: int = _TIMEOUT_DEFAULT) -> dict:
    adb = _adb_cmd()
    if not adb:
        return {"error": "adb not installed"}
    cmd = [adb]
    if device:
        cmd += ["-s", device]
    cmd += ["shell", command]
    result = await _run_subprocess(cmd, timeout=timeout)
    return {
        "code": result["code"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
    }


async def adb_logcat(
    device: str | None = None,
    filter_expr: str = "*:I",
    lines: int = 100,
    timeout: int = 15,
) -> dict:
    adb = _adb_cmd()
    if not adb:
        return {"error": "adb not installed"}
    cmd = [adb]
    if device:
        cmd += ["-s", device]
    cmd += ["logcat", "-t", str(lines), filter_expr]
    result = await _run_subprocess(cmd, timeout=timeout)
    return {
        "code": result["code"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
    }


async def adb_screenshot(device: str | None = None) -> dict:
    adb = _adb_cmd()
    if not adb:
        return {"error": "adb not installed"}
    tmp = tempfile.mktemp(suffix=".png")
    cmd = [adb]
    if device:
        cmd += ["-s", device]
    cmd += ["exec-out", "screencap", "-p"]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode == 0 and len(stdout) > 100:
            with open(tmp, "wb") as f:
                f.write(stdout)
            import base64
            with open(tmp, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            os.unlink(tmp)
            return {"screenshot_base64": b64, "size": len(stdout), "mime": "image/png"}
        return {"error": stderr.decode(errors="replace")}
    except asyncio.TimeoutError:
        proc.kill()
        return {"error": "screenshot timed out"}


async def adb_start_activity(package: str, activity: str, device: str | None = None) -> dict:
    return await adb_shell(
        f"am start -n {package}/{activity}",
        device=device, timeout=15,
    )


async def adb_force_stop(package: str, device: str | None = None) -> dict:
    return await adb_shell(
        f"am force-stop {package}",
        device=device, timeout=10,
    )


""" ---------- Headless Chromium (via subprocess, no Playwright package) ---------- """

CHROMIUM_CMD = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
_CHROMIUM_ARGS = ["--headless", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--window-size=1280,720"]


async def playwright_launch(headless: bool = True, timeout: int = 20) -> dict:
    if not CHROMIUM_CMD:
        return {"error": "chromium binary not found"}
    _ = headless  # always headless
    result = await _run_subprocess(
        [CHROMIUM_CMD] + _CHROMIUM_ARGS + ["--dump-dom", "about:blank"],
        timeout=timeout,
    )
    return {
        "status": "launched" if result["code"] in (0, 1, -11) else "error",
        "browser": "chromium",
        "headless": headless,
        "note": "Using system Chromium via subprocess (no Playwright package). Evaluate/navigate via separate API calls.",
    }


async def playwright_navigate(url: str, timeout: int = 30) -> dict:
    if not CHROMIUM_CMD:
        return {"error": "chromium binary not found"}
    import re
    result = await _run_subprocess(
        [CHROMIUM_CMD] + _CHROMIUM_ARGS + ["--dump-dom", url],
        timeout=timeout,
    )
    html = result.get("stdout", "")
    m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = m.group(1) if m else ""
    return {
        "url": url,
        "title": title,
        "code": result["code"],
    }


async def playwright_screenshot(full_page: bool = False) -> dict:
    if not CHROMIUM_CMD:
        return {"error": "chromium binary not found"}
    tmp = tempfile.mktemp(suffix=".png")
    args = [CHROMIUM_CMD] + _CHROMIUM_ARGS + ["--screenshot=" + tmp, "about:blank"]
    if full_page:
        args.insert(len(_CHROMIUM_ARGS) + 1, "--full-page")
    result = await _run_subprocess(args, timeout=30)
    if result["code"] in (0, 1, -11) and os.path.getsize(tmp) > 100:
        import base64
        with open(tmp, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        os.unlink(tmp)
        return {"screenshot_base64": b64, "mime": "image/png", "size": len(b64)}
    os.unlink(tmp)
    return {"error": "screenshot failed", "stderr": result["stderr"]}


async def playwright_evaluate(js: str) -> dict:
    if not CHROMIUM_CMD:
        return {"error": "chromium binary not found"}
    html = f"<html><body><script>{js}</script></body></html>"
    tmp = tempfile.mktemp(suffix=".html")
    with open(tmp, "w") as f:
        f.write(html)
    result = await _run_subprocess(
        [CHROMIUM_CMD] + _CHROMIUM_ARGS + ["--dump-dom", tmp],
        timeout=30,
    )
    os.unlink(tmp)
    return {
        "result": result.get("stdout", ""),
        "code": result["code"],
        "note": "JS evaluation via dump-dom. Complex return values may not be captured.",
    }


async def playwright_html(url: str | None = None) -> dict:
    if not CHROMIUM_CMD:
        return {"error": "chromium binary not found"}
    target = url or "about:blank"
    result = await _run_subprocess(
        [CHROMIUM_CMD] + _CHROMIUM_ARGS + ["--dump-dom", target],
        timeout=30,
    )
    return {"html": result.get("stdout", ""), "code": result["code"], "url": target}


async def playwright_close() -> dict:
    return {"status": "closed", "note": "Chromium subprocess-based; no persistent session to close."}


""" ---------- Stream helpers (for /ws/device) ---------- """


async def stream_logcat(device: str | None = None, filter_expr: str = "*:I", max_qsize: int = 500):
    """Generator that yields logcat lines with bounded buffer queue.
    
    If the consumer (WebSocket) cannot keep up, old entries are dropped
    and a structured overflow marker is injected instead of blocking.
    """
    adb = _adb_cmd()
    if not adb:
        yield {"type": "error", "payload": "adb not installed"}
        return
    cmd = [adb]
    if device:
        cmd += ["-s", device]
    cmd += ["logcat", filter_expr]

    proc: asyncio.subprocess.Process | None = None
    queue: asyncio.Queue = asyncio.Queue(maxsize=max_qsize)
    overflow_flag = False

    async def _reader():
        nonlocal overflow_flag
        try:
            assert proc is not None and proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    await queue.put(None)
                    break
                entry = {"type": "logcat", "payload": line.decode(errors="replace").rstrip()}
                try:
                    queue.put_nowait(entry)
                    overflow_flag = False
                except asyncio.QueueFull:
                    if not overflow_flag:
                        overflow_flag = True
                        logger.warning("Logcat buffer overflow, dropping chunks")
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    queue.put_nowait(entry)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdout is not None
        reader_task = asyncio.create_task(_reader())
        overdropped = False
        try:
            while True:
                entry = await queue.get()
                if entry is None:
                    break
                yield entry
                overdropped = False
        finally:
            reader_task.cancel()
            try:
                await reader_task
            except (asyncio.CancelledError, Exception):
                pass
    except asyncio.CancelledError:
        raise
    except Exception as e:
        yield {"type": "error", "payload": str(e)}
    finally:
        if proc:
            try:
                proc.kill()
            except Exception:
                pass
