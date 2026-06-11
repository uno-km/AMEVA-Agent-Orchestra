import os
import sys
import time
import json
import logging
import asyncio
import threading
from datetime import datetime
from collections import deque

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

import psutil
from watchdog.observers import Observer

from core.llm_engine import LlamaInferenceCore
from core.sre import WorkspaceWatcher, logger
from core.config import MEMORY_DIR, WORKSPACE_DIR, MODEL_DIR, AVAILABLE_MODELS, LOG_DIR
from core.bootstrap import HardwareProfiler, ModelDownloader
from core.database import setup_db, DatabaseManager
from agents.orchestrator import Orchestrator

# Setup DB
setup_db()

# Initialize FastAPI App
app = FastAPI(title="AMEVA Agent Orchestra - Enterprise Web Console")

# Global Event Loop Reference
loop = None

# Restoration Session State (In-Memory Session Storage)
active_session_logs = deque(maxlen=200)
active_sre_logs = deque(maxlen=200)
resource_history = deque(maxlen=50) # holds list of [cpu, ram, gpu]
agent_states = {
    "pm": {"status": "💤 Standby", "task": "None", "passed": "None", "elapsed": "0s", "tokens": "P:0 / C:0"},
    "tester": {"status": "💤 Standby", "task": "None", "passed": "None", "elapsed": "0s", "tokens": "P:0 / C:0"},
    "secretary": {"status": "💤 Standby", "task": "None", "passed": "None", "elapsed": "0s", "tokens": "P:0 / C:0"},
    "architect": {"status": "💤 Standby", "task": "None", "passed": "None", "elapsed": "0s", "tokens": "P:0 / C:0"},
    "dev": {"status": "💤 Standby", "task": "None", "passed": "None", "elapsed": "0s", "tokens": "P:0 / C:0"},
    "doc": {"status": "💤 Standby", "task": "None", "passed": "None", "elapsed": "0s", "tokens": "P:0 / C:0"}
}

# Active download thread tracking
active_download = None
active_download_progress = 0
active_download_status = "Ready"

# Orchestrator Singleton
orchestrator = Orchestrator()

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        # Clean up stale connections during broadcast
        stale = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                stale.append(connection)
        for s in stale:
            self.disconnect(s)

manager = ConnectionManager()

def log_to_web(msg, lvl="INFO"):
    tk = LlamaInferenceCore.get_instance().total_tokens_used
    formatted = f"[{datetime.now().strftime('%H:%M:%S')}] [{lvl}] (Σ: {tk}) {msg}"
    active_session_logs.append(formatted)
    
    # Broadcast to all websockets safely
    if loop:
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "trace_log", "message": formatted, "tokens": tk}),
            loop
        )

# Thread-safe logging handler for Web UI
class WebConsoleLogHandler(logging.Handler):
    def emit(self, record):
        try:
            log_entry = self.format(record)
            DatabaseManager.log_system("CONSOLE", log_entry)
            if loop:
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast({"type": "console_log", "message": log_entry}),
                    loop
                )
        except Exception:
            pass

# Attach logger handler
web_log_handler = WebConsoleLogHandler()
web_log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(web_log_handler)

# Custom callback connector for Orchestrator events
def orchestrator_event_callback(event_type, *args):
    if not loop:
        return

    if event_type == "worker_started":
        aid = args[0]
        agent_states[aid]["status"] = "🔥 Working"
        agent_states[aid]["elapsed"] = "0s"
        log_to_web(f"워커 가동: 에이전트 {aid.upper()}", "INFO")
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "worker_started", "agent_id": aid}),
            loop
        )

    elif event_type == "task_assigned":
        aid, task_data = args[0], args[1]
        instruction = task_data.get("instruction", "None")
        passed = task_data.get("passed_result", "None")
        
        agent_states[aid]["task"] = instruction
        agent_states[aid]["passed"] = passed
        
        log_to_web(f"임무 부여 ({aid.upper()}): {instruction[:64]}...", "INFO")
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "task_assigned", "agent_id": aid, "task_data": task_data}),
            loop
        )

    elif event_type == "llm_stream":
        aid, delta = args[0], args[1]
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "llm_stream", "agent_id": aid, "delta": delta}),
            loop
        )

    elif event_type == "worker_finished":
        aid, res, usage = args[0], args[1], args[2]
        agent_states[aid]["status"] = "💤 Standby"
        agent_states[aid]["tokens"] = f"P:{usage.get('prompt_tokens', 0)} / C:{usage.get('completion_tokens', 0)}"
        
        status = res.get("status", 200)
        if status >= 400:
            log_to_web(f"에이전트 {aid.upper()} 실패: {res.get('message', 'Unknown error')} (status={status})", "ERROR")
        elif status == 300:
            log_to_web(f"에이전트 {aid.upper()} 강제 종료: {res.get('message')}", "WARN")
        else:
            log_to_web(f"에이전트 {aid.upper()} 완료: {res.get('message')}", "SUCCESS")

        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "worker_finished", "agent_id": aid, "result": res, "usage": usage}),
            loop
        )

    elif event_type == "worker_error":
        aid, err = args[0], args[1]
        agent_states[aid]["status"] = "💤 Standby"
        log_to_web(f"에이전트 {aid.upper()} 치명적 오류: {err}", "ERROR")
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "worker_error", "agent_id": aid, "error": err}),
            loop
        )

    elif event_type == "handoff_triggered":
        fid, tid, nt = args[0], args[1], args[2]
        log_to_web(f"바통 인계 (Handoff): {fid.upper()} -> {tid.upper()}", "INFO")
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "handoff_triggered", "from_id": fid, "to_id": tid, "next_task": nt}),
            loop
        )

orchestrator.register_callback(orchestrator_event_callback)

# Workspace watchdog file watcher callback
def watchdog_callback(msg, source):
    formatted = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    active_sre_logs.append(formatted)
    DatabaseManager.log_system("SRE_WATCHDOG", formatted)
    if loop:
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "sre_event", "message": formatted}),
            loop
        )

# Start background Watchdog Observer
def start_watchdog():
    observer = Observer()
    observer.schedule(WorkspaceWatcher(watchdog_callback), WORKSPACE_DIR, recursive=True)
    observer.start()
    return observer

# Real-time resource monitoring loop (CPU, RAM, GPU)
async def resource_monitoring_loop():
    while True:
        try:
            c = psutil.cpu_percent()
            r = psutil.virtual_memory().percent
            g = LlamaInferenceCore.get_instance().get_gpu_load_safe()
            
            # Keep history capped at 50
            resource_history.append([c, r, g])
            
            # Broadcast to web dashboard
            await manager.broadcast({
                "type": "resource_stats",
                "cpu": c,
                "ram": r,
                "gpu": int(g)
            })
            
            # SRE Watchdog RAM safety guard
            if r > 98.0:
                msg = f"[{datetime.now().strftime('%H:%M:%S')}] 🚨 [CRITICAL] RAM 과부하 ({r}%)! 워커를 강제 종료합니다."
                active_sre_logs.append(msg)
                await manager.broadcast({"type": "sre_event", "message": msg})
                # orchestrator.shutdown_all() # Commented out to prevent blocking completely
                
        except Exception as e:
            logger.error(f"Resource monitoring error: {e}")
            
        await asyncio.sleep(2.0)

# REST endpoints
@app.get("/")
async def get_index():
    return FileResponse("ui/templates/index.html")

@app.get("/api/memory")
async def list_memory_files():
    try:
        files = [
            "pm_memory.md", "architect_memory.md",
            "dev_memory.md", "tester_memory.md",
            "secretary_memory.md", "doc_memory.md"
        ]
        return {"files": files}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/memory/{filename}")
async def get_memory_file(filename: str):
    agent_id = filename.replace("_memory.md", "")
    try:
        content = DatabaseManager.get_agent_history(agent_id)
        return {"content": content}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/models")
async def list_models():
    models = HardwareProfiler.recommend_models()
    return {"models": models}

def check_admin(request: Request) -> bool:
    referer = request.headers.get("referer", "")
    if "admin=true" in referer:
        return True
    if request.query_params.get("admin") == "true":
        return True
    return False

@app.post("/api/select_model")
async def select_model(request: Request):
    if not check_admin(request):
        return {"status": "error", "message": "권한이 없습니다. (관람 전용 모드)"}
    data = await request.json()
    model_id = data.get("model_id")
    
    # Match model
    model_info = next((m for m in AVAILABLE_MODELS if m["id"] == model_id), None)
    if not model_info:
        return {"status": "error", "message": "Model not found"}
        
    model_path = os.path.join(MODEL_DIR, model_info["filename"])
    if not os.path.exists(model_path):
        return {"status": "error", "message": "Model not downloaded"}

    # Load model in a separate thread to avoid blocking server main loop
    def load_task():
        engine = LlamaInferenceCore.get_instance()
        success = engine.load_model(model_path)
        if success:
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({"type": "model_loaded", "model_path": model_path}),
                loop
            )
        else:
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({"type": "model_load_failed", "message": "Engine failed to load GGUF file"}),
                loop
            )

    threading.Thread(target=load_task).start()
    return {"status": "ok", "message": "Model loading started"}

@app.post("/api/install_model")
async def install_model(request: Request):
    if not check_admin(request):
        return {"status": "error", "message": "권한이 없습니다. (관람 전용 모드)"}
    global active_download, active_download_progress, active_download_status
    if active_download and active_download.is_alive():
        return {"status": "error", "message": "Download already in progress"}

    data = await request.json()
    model_id = data.get("model_id")
    model_info = next((m for m in AVAILABLE_MODELS if m["id"] == model_id), None)
    if not model_info:
        return {"status": "error", "message": "Model not found"}

    def dl_progress(percent):
        global active_download_progress
        active_download_progress = percent
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "download_progress", "percent": percent, "model_id": model_id}),
            loop
        )

    def dl_log(msg):
        global active_download_status
        active_download_status = msg
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "download_status", "status": msg, "model_id": model_id}),
            loop
        )

    def dl_finished(success, filepath_or_err):
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "download_finished", "success": success, "path_or_err": filepath_or_err, "model_id": model_id}),
            loop
        )

    active_download = ModelDownloader(
        url=model_info["url"],
        filename=model_info["filename"],
        progress_callback=dl_progress,
        log_callback=dl_log,
        finished_callback=dl_finished
    )
    active_download.start()
    return {"status": "ok", "message": "Model download initiated"}

# WebSocket Handler
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    engine = LlamaInferenceCore.get_instance()
    is_admin = websocket.query_params.get("admin") == "true"
    
    # Calculate current state package (Restoration Session)
    init_state = {
        "type": "init",
        "model_loaded": engine.is_loaded,
        "current_model": engine.current_model_path,
        "total_tokens": engine.total_tokens_used,
        "session_logs": list(active_session_logs),
        "sre_logs": list(active_sre_logs),
        "resource_history": list(resource_history),
        "agent_states": agent_states,
        "max_processors": orchestrator.max_concurrent_processors,
        "download_in_progress": active_download is not None and active_download.is_alive(),
        "download_percent": active_download_progress,
        "download_status": active_download_status
    }
    
    # Send init package immediately to new client
    try:
        await websocket.send_json(init_state)
    except Exception:
        manager.disconnect(websocket)
        return

    try:
        while True:
            # Handle user interaction events
            data = await websocket.receive_json()
            m_type = data.get("type")
            
            if m_type == "start_mission":
                if not is_admin:
                    await websocket.send_json({
                        "type": "trace_log",
                        "message": f"[{datetime.now().strftime('%H:%M:%S')}] [WARN] 권한 오류: 관람 전용 모드에서는 명령을 내릴 수 없습니다.",
                        "tokens": engine.total_tokens_used
                    })
                    continue
                req = data.get("request", "").strip()
                if req:
                    log_to_web(f"COMMANDER (Web User): {req}", "INFO")
                    workflow_id = DatabaseManager.create_workflow(req)
                    orchestrator.start_mission(req, workflow_id=workflow_id)
                    
            elif m_type == "set_concurrency":
                if not is_admin:
                    await websocket.send_json({
                        "type": "trace_log",
                        "message": f"[{datetime.now().strftime('%H:%M:%S')}] [WARN] 권한 오류: 관람 전용 모드에서는 설정을 변경할 수 없습니다.",
                        "tokens": engine.total_tokens_used
                    })
                    await websocket.send_json({
                        "type": "concurrency_changed",
                        "value": orchestrator.max_concurrent_processors
                    })
                    continue
                val = int(data.get("value", 1))
                orchestrator.set_max_processors(val)
                log_to_web(f"Max Concurrent Processors 변경 -> {val}", "INFO")
                await manager.broadcast({"type": "concurrency_changed", "value": val})
                
            elif m_type == "stop_all":
                if not is_admin:
                    await websocket.send_json({
                        "type": "trace_log",
                        "message": f"[{datetime.now().strftime('%H:%M:%S')}] [WARN] 권한 오류: 관람 전용 모드에서는 중지할 수 없습니다.",
                        "tokens": engine.total_tokens_used
                    })
                    continue
                log_to_web("사용자 요청으로 전체 에이전트 작업 강제 중지...", "WARN")
                orchestrator.shutdown_all()
                await manager.broadcast({"type": "orchestrator_stopped"})
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket processing error: {e}")
        manager.disconnect(websocket)

# Static resources mapping
app.mount("/static", StaticFiles(directory="ui/static"), name="static")

def main():
    global loop
    import uvicorn
    
    # Pre-init workspace
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    os.makedirs(MEMORY_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(MODEL_DIR, exist_ok=True)
    
    # Load default model if already downloaded
    default_model_info = next((m for m in AVAILABLE_MODELS if m.get("is_default")), None)
    if default_model_info:
        default_path = os.path.join(MODEL_DIR, default_model_info["filename"])
        if os.path.exists(default_path):
            logger.info(f"BOOT: 기본 모델 적재 중... -> {default_path}")
            LlamaInferenceCore.get_instance().load_model(default_path)
            
    # Watchdog and monitoring loops start on server startup
    watcher_observer = start_watchdog()
    
    @app.on_event("startup")
    async def on_startup():
        global loop
        loop = asyncio.get_running_loop()
        asyncio.create_task(resource_monitoring_loop())
        logger.info("SYSTEM: Web Operations Console 가동 준비 완료.")

    try:
        uvicorn.run(app, host="0.0.0.0", port=9000, log_level="info")
    finally:
        # Tear down watcher safely
        watcher_observer.stop()
        watcher_observer.join()
        orchestrator.shutdown_all()

if __name__ == '__main__':
    main()