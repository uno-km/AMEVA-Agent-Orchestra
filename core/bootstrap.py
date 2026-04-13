import os
import time
import GPUtil
import psutil
from PyQt6.QtCore import QThread, pyqtSignal
import urllib.request
from .config import MODEL_DIR, AVAILABLE_MODELS
import logging

logger = logging.getLogger("AMEVA_Orchestra")

class HardwareProfiler:
    @staticmethod
    def get_system_specs():
        """Retrieve RAM and GPU capabilities"""
        specs = {
            "ram_gb": round(psutil.virtual_memory().total / (1024**3), 1),
            "cpu_cores": psutil.cpu_count(logical=False),
            "gpu_name": "None",
            "gpu_vram_gb": 0.0
        }
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                specs["gpu_name"] = gpus[0].name
                specs["gpu_vram_gb"] = round(gpus[0].memoryTotal / 1024, 1)
        except Exception as e:
            logger.warning(f"Failed to access GPU info: {e}")
            
        return specs

    @staticmethod
    def recommend_models():
        """Recommend models based on system RAM and VRAM"""
        specs = HardwareProfiler.get_system_specs()
        ram = specs["ram_gb"]
        
        # Calculate scores or basic filters
        recommended = []
        for model in AVAILABLE_MODELS:
            m = model.copy()
            m["is_installed"] = os.path.exists(os.path.join(MODEL_DIR, m["filename"]))
            if ram >= m["min_ram_gb"]:
                m["recommended"] = True
            else:
                m["recommended"] = False
            recommended.append(m)
            
        # Sort installed first, then recommended
        recommended.sort(key=lambda x: (not x["is_installed"], not x["recommended"]))
        return recommended

class ModelDownloader(QThread):
    progress = pyqtSignal(int)
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, url, filename):
        super().__init__()
        self.url = url
        self.filepath = os.path.join(MODEL_DIR, filename)

    def run(self):
        try:
            self.log_signal.emit(f"다운로드 시작: {os.path.basename(self.filepath)}")
            req = urllib.request.Request(self.url, headers={'User-Agent': 'Mozilla/5.0'})
            
            with urllib.request.urlopen(req) as response:
                total_size = int(response.info().get('Content-Length', 0))
                block_size = 8 * 1024 * 1024 # 8MB chunks
                downloaded = 0
                
                with open(self.filepath, 'wb') as f:
                    while True:
                        if self.isInterruptionRequested():
                            self.log_signal.emit("다운로드 취소됨.")
                            self.finished_signal.emit(False, "Canceled")
                            return
                            
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        f.write(buffer)
                        downloaded += len(buffer)
                        
                        if total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            self.progress.emit(percent)
                            
            self.progress.emit(100)
            self.log_signal.emit("다운로드 및 검증 완료.")
            self.finished_signal.emit(True, self.filepath)
            
        except Exception as e:
            self.log_signal.emit(f"다운로드 실패: {e}")
            if os.path.exists(self.filepath):
                os.remove(self.filepath)
            self.finished_signal.emit(False, str(e))
