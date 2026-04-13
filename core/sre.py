import os
import logging
from logging.handlers import RotatingFileHandler
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PyQt6.QtCore import QObject, pyqtSignal
from .config import LOG_DIR, WORKSPACE_DIR

logger = logging.getLogger("AMEVA_Orchestra")
logger.setLevel(logging.DEBUG)

# 20MB 단위로 10개의 순환 로그 파일 유지
file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, "system_orchestra_v3.log"), 
    maxBytes=20*1024*1024, 
    backupCount=10, 
    encoding="utf-8"
)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

class WatchdogSignalEmitter(QObject):
    """Watchdog(별도 스레드)의 이벤트를 UI 스레드로 안전하게 전달하는 시그널 브릿지"""
    file_modified = pyqtSignal(str, str)

class WorkspaceWatcher(FileSystemEventHandler):
    """파일 변경을 실시간 감지하여 시그널을 통해 UI에 안전하게 주입합니다."""
    def __init__(self, emitter):
        self.emitter = emitter
        
    def on_modified(self, event):
        if not event.is_directory:
            self.emitter.file_modified.emit(f"수정: {os.path.basename(event.src_path)}", "WATCHER")
            
    def on_created(self, event):
        if not event.is_directory:
            self.emitter.file_modified.emit(f"생성: {os.path.basename(event.src_path)}", "WATCHER")
