import os
import logging
from logging.handlers import RotatingFileHandler
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
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


class WorkspaceWatcher(FileSystemEventHandler):
    """파일 변경을 실시간 감지하여 콜백을 호출합니다."""
    def __init__(self, callback):
        self.callback = callback
        
    def on_modified(self, event):
        if not event.is_directory:
            if self.callback:
                self.callback(f"수정: {os.path.basename(event.src_path)}", "WATCHER")
            
    def on_created(self, event):
        if not event.is_directory:
            if self.callback:
                self.callback(f"생성: {os.path.basename(event.src_path)}", "WATCHER")

