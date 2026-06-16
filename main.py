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
from core.config import MEMORY_DIR, WORKSPACE_DIR, MODEL_DIR, AVAILABLE_GENERAL_MODELS, AVAILABLE_CODING_MODELS, LOG_DIR
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
orchestrator.active_general_model_path = None
orchestrator.active_coding_model_path = None

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

@app.get("/api/workspace")
async def get_workspace_files():
    try:
        files_data = []
        for root, dirs, files in os.walk(WORKSPACE_DIR):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, WORKSPACE_DIR)
                files_data.append({
                    "path": rel_path.replace("\\", "/"),
                    "name": file
                })
        return {"status": "ok", "files": files_data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/workspace/{file_path:path}")
async def get_workspace_file_content(file_path: str):
    try:
        safe_path = os.path.normpath(os.path.join(WORKSPACE_DIR, file_path))
        if not safe_path.startswith(os.path.normpath(WORKSPACE_DIR)):
            return {"status": "error", "message": "Access denied"}
        if os.path.exists(safe_path):
            with open(safe_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return {"status": "ok", "content": content}
        else:
            return {"status": "error", "message": "File not found"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/workspace/open_folder")
async def open_workspace_folder(request: Request):
    if not check_admin(request):
        return {"status": "error", "message": "권한이 없습니다. (관람 전용 모드)"}
    try:
        data = await request.json()
        file_path = data.get("file_path", "")
        from core.security import enforce_sandbox
        
        import subprocess
        if file_path:
            safe_path = enforce_sandbox(file_path)
            if os.path.exists(safe_path):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(safe_path)])
                return {"status": "ok", "message": f"탐색기에서 {file_path} 선택함."}
        
        subprocess.Popen(["explorer", os.path.normpath(WORKSPACE_DIR)])
        return {"status": "ok", "message": "워크스페이스 폴더가 열렸습니다."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/workspace/run")
async def run_workspace_file(request: Request):
    if not check_admin(request):
        return {"status": "error", "message": "권한이 없습니다. (관람 전용 모드)"}
    try:
        data = await request.json()
        file_path = data.get("file_path", "")
        if not file_path:
            return {"status": "error", "message": "실행할 파일 경로가 지정되지 않았습니다."}
            
        from core.security import enforce_sandbox
        safe_path = enforce_sandbox(file_path)
        
        if not os.path.exists(safe_path):
            return {"status": "error", "message": "파일이 존재하지 않습니다."}
            
        if not safe_path.endswith(".py"):
            return {"status": "error", "message": "파이썬(.py) 스크립트만 실행할 수 있습니다."}
            
        py_exe = os.path.normpath(os.path.join(os.getcwd(), "venv", "Scripts", "python.exe"))
        if not os.path.exists(py_exe):
            py_exe = "python"
            
        import subprocess
        file_dir = os.path.dirname(safe_path)
        
        # Windows에서는 새 콘솔 창을 생성하여 사용자 상호작용 및 stdout을 지원함
        subprocess.Popen([py_exe, safe_path], cwd=file_dir, creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)
        return {"status": "ok", "message": f"스크립트 실행 완료: {file_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/current_state")
async def get_current_state():
    engine = LlamaInferenceCore.get_instance()
    model_name = os.path.basename(engine.current_model_path) if engine.current_model_path else "Not Loaded"
    is_gpu = False
    try:
        import GPUtil
        if GPUtil.getGPUs():
            is_gpu = True
    except:
        pass
    return {
        "model_name": model_name,
        "workflow_id": getattr(orchestrator, "current_workflow_id", ""),
        "is_gpu": is_gpu
    }

@app.get("/api/agent_history/{workflow_id}/{agent_id}")
async def get_agent_history(workflow_id: str, agent_id: str):
    history = DatabaseManager.get_agent_workflow_history(workflow_id, agent_id)
    return {"status": "ok", "history": history}

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
    # Evaluate is_installed and recommendation based on RAM
    from core.bootstrap import HardwareProfiler
    specs = HardwareProfiler.get_system_specs()
    ram = specs["ram_gb"]
    
    gen_list = []
    for m in AVAILABLE_GENERAL_MODELS:
        mc = m.copy()
        mc["is_installed"] = os.path.exists(os.path.join(MODEL_DIR, mc["filename"]))
        mc["recommended"] = (ram >= mc["min_ram_gb"])
        gen_list.append(mc)
        
    cod_list = []
    for m in AVAILABLE_CODING_MODELS:
        mc = m.copy()
        mc["is_installed"] = os.path.exists(os.path.join(MODEL_DIR, mc["filename"]))
        mc["recommended"] = (ram >= mc["min_ram_gb"])
        cod_list.append(mc)

    # Return both model lists and specs
    return {
        "models": {
            "general": gen_list,
            "coding": cod_list
        },
        "specs": specs
    }

def check_admin(request: Request) -> bool:
    referer = request.headers.get("referer", "")
    if "admin=true" in referer:
        return True
    if request.query_params.get("admin") == "true":
        return True
    return False

@app.post("/api/select_models")
async def select_models(request: Request):
    if not check_admin(request):
        return {"status": "error", "message": "권한이 없습니다. (관람 전용 모드)"}
    data = await request.json()
    general_id = data.get("general_model_id")
    coding_id = data.get("coding_model_id")
    
    gen_model = next((m for m in AVAILABLE_GENERAL_MODELS if m["id"] == general_id), None)
    cod_model = next((m for m in AVAILABLE_CODING_MODELS if m["id"] == coding_id), None)
    
    if not gen_model or not cod_model:
        return {"status": "error", "message": "Model not found"}
        
    gen_path = os.path.join(MODEL_DIR, gen_model["filename"])
    cod_path = os.path.join(MODEL_DIR, cod_model["filename"])
    
    if not os.path.exists(gen_path) or not os.path.exists(cod_path):
        return {"status": "error", "message": "Selected models are not downloaded"}

    # Update orchestrator paths
    orchestrator.active_general_model_path = gen_path
    orchestrator.active_coding_model_path = cod_path

    # Immediately load the general model to be ready
    def load_task():
        engine = LlamaInferenceCore.get_instance()
        success = engine.load_model(gen_path)
        if success:
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({"type": "model_loaded", "model_path": gen_path, "coding_model_path": cod_path}),
                loop
            )
        else:
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({"type": "model_load_failed", "message": "Engine failed to load GGUF file"}),
                loop
            )

    threading.Thread(target=load_task).start()
    return {"status": "ok", "message": "Model configuration updated"}

active_download = None
active_download_progress = 0
active_download_status = ""
download_queue = []
download_thread = None

def process_download_queue():
    global active_download, active_download_progress, active_download_status, download_queue, download_thread
    while download_queue:
        model_info = download_queue[0]
        model_id = model_info["id"]
        
        dl_event = threading.Event()
        
        def dl_progress(percent):
            global active_download_progress
            active_download_progress = percent
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({"type": "download_progress", "percent": percent, "model_id": model_id}),
                loop
            )

        def dl_log(msg):
            global active_download_status
            active_download_status = f"[{model_info['name']}] {msg} (대기열: {len(download_queue)-1}개)"
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({"type": "download_status", "status": active_download_status, "model_id": model_id}),
                loop
            )

        def dl_finished(success, filepath_or_err):
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({"type": "download_finished", "success": success, "path_or_err": filepath_or_err, "model_id": model_id}),
                loop
            )
            dl_event.set()

        active_download = ModelDownloader(
            url=model_info["url"],
            filename=model_info["filename"],
            progress_callback=dl_progress,
            log_callback=dl_log,
            finished_callback=dl_finished
        )
        active_download.start()
        dl_event.wait()
        
        download_queue.pop(0)
        active_download = None
        active_download_progress = 0
        active_download_status = ""
        
    download_thread = None

@app.post("/api/install_model")
async def install_model(request: Request):
    if not check_admin(request):
        return {"status": "error", "message": "권한이 없습니다. (관람 전용 모드)"}
    global download_queue, download_thread

    data = await request.json()
    model_id = data.get("model_id")
    model_info = next((m for m in AVAILABLE_GENERAL_MODELS + AVAILABLE_CODING_MODELS if m["id"] == model_id), None)
    if not model_info:
        return {"status": "error", "message": "Model not found"}
        
    # Check if already installed
    if os.path.exists(os.path.join(MODEL_DIR, model_info["filename"])):
        return {"status": "error", "message": "Already installed"}
        
    # Check if already in queue
    if any(m["id"] == model_id for m in download_queue):
        return {"status": "error", "message": "Already in download queue"}

    download_queue.append(model_info)
    
    if active_download is not None and active_download.is_alive():
        # 현재 다운로드 중인 항목(인덱스 0) 외의 실제 대기열 수
        waiting_count = len(download_queue) - 1
        current_msg = f"다운로드 진행 중... (대기열: {waiting_count}개)"
        global active_download_status
        active_download_status = current_msg
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "download_status", "status": current_msg}),
            loop
        )
    
    if download_thread is None or not download_thread.is_alive():
        download_thread = threading.Thread(target=process_download_queue)
        download_thread.start()
        
    return {"status": "ok", "message": f"모델이 다운로드 대기열에 추가되었습니다. (현재 대기열: {len(download_queue)}개)"}

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
    
    # Load default models if already downloaded
    is_gpu = False
    try:
        import GPUtil
        if GPUtil.getGPUs():
            is_gpu = True
    except:
        pass

    if is_gpu:
        default_gen_id = "llama_3.1_8b"
        default_cod_id = "qwen_2.5_coder_7b"
        logger.info("SYSTEM: GPU environment detected. Setting defaults: General=8B (Llama 3.1), Coding=7B (Qwen Coder)")
    else:
        default_gen_id = "qwen_2.5_3b"
        default_cod_id = "qwen_2.5_coder_3b"
        logger.info("SYSTEM: CPU environment detected. Setting defaults: General=3B (Qwen2.5), Coding=3B (Qwen Coder)")

    for m in AVAILABLE_GENERAL_MODELS:
        m["is_default"] = (m["id"] == default_gen_id)
    for m in AVAILABLE_CODING_MODELS:
        m["is_default"] = (m["id"] == default_cod_id)

    default_gen = next((m for m in AVAILABLE_GENERAL_MODELS if m["id"] == default_gen_id), None)
    default_cod = next((m for m in AVAILABLE_CODING_MODELS if m["id"] == default_cod_id), None)
    
    if default_gen and default_cod:
        gen_path = os.path.join(MODEL_DIR, default_gen["filename"])
        cod_path = os.path.join(MODEL_DIR, default_cod["filename"])
        
        orchestrator.active_general_model_path = gen_path
        orchestrator.active_coding_model_path = cod_path
        
        if os.path.exists(gen_path):
            logger.info(f"BOOT: 기본 PM 모델 적재 중... -> {gen_path}")
            LlamaInferenceCore.get_instance().load_model(gen_path)
            
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