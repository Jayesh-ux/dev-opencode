import os
import pty
import fcntl
import termios
import struct
import asyncio
import logging
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter(tags=["terminal"])

@router.websocket("/ws/terminal")
async def terminal_websocket(websocket: WebSocket):
    await websocket.accept()
    
    # Create the pseudo-terminal Master/Slave pair
    master_fd, slave_fd = pty.openpty()
    
    # Setup environment variables for the subprocess to inherit Gemini keys
    env = os.environ.copy()
    gemini_key = env.get("GEMINI_API_KEY")
    if gemini_key:
        env["GOOGLE_GENERATIVE_AI_API_KEY"] = gemini_key

    # Spawn the process (opencode) in the slave terminal with inherited env
    p = await asyncio.create_subprocess_exec(
        "/Users/rohitjaiswar/.opencode/bin/opencode",
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        preexec_fn=os.setsid,  # Start process in a new session group
        env=env,
    )
    
    # Close the slave FD in the parent process, we only use the master FD
    os.close(slave_fd)
    
    loop = asyncio.get_running_loop()
    
    async def read_from_pty():
        try:
            while p.returncode is None:
                future = loop.create_future()
                def ready():
                    loop.remove_reader(master_fd)
                    if not future.done():
                        future.set_result(None)
                        
                loop.add_reader(master_fd, ready)
                await future
                
                try:
                    data = os.read(master_fd, 4096)
                    if not data:
                        break
                    # Send bytes directly to client as binary or decode safely
                    await websocket.send_text(data.decode("utf-8", errors="replace"))
                except OSError:
                    break
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error("Error reading from PTY: %s", e)
            
    async def write_to_pty():
        try:
            while p.returncode is None:
                raw_msg = await websocket.receive_text()
                try:
                    msg = json.loads(raw_msg)
                    msg_type = msg.get("type")
                    if msg_type == "input":
                        os.write(master_fd, msg.get("data", "").encode())
                    elif msg_type == "resize":
                        cols = msg.get("cols", 80)
                        rows = msg.get("rows", 24)
                        s = struct.pack('HHHH', rows, cols, 0, 0)
                        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, s)
                except json.JSONDecodeError:
                    os.write(master_fd, raw_msg.encode())
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error("Error writing to PTY: %s", e)
            
    read_task = asyncio.create_task(read_from_pty())
    write_task = asyncio.create_task(write_to_pty())
    
    try:
        await p.wait()
    except Exception:
        pass
    finally:
        read_task.cancel()
        write_task.cancel()
        try:
            loop.remove_reader(master_fd)
        except Exception:
            pass
        try:
            os.close(master_fd)
        except Exception:
            pass
        try:
            p.kill()
        except Exception:
            pass
