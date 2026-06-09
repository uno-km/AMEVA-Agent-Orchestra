import os
import time
import GPUtil
import psutil
import threading
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

class ModelDownloader(threading.Thread):
    def __init__(self, url, filename, progress_callback=None, log_callback=None, finished_callback=None):
        super().__init__()
        self.url = url
        self.filepath = os.path.join(MODEL_DIR, filename)
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        self.finished_callback = finished_callback
        self._stop_event = threading.Event()

    def requestInterruption(self):
        self._stop_event.set()

    def isInterruptionRequested(self):
        return self._stop_event.is_set()

    def run(self):
        try:
            if self.log_callback:
                self.log_callback(f"다운로드 시작: {os.path.basename(self.filepath)}")
            req = urllib.request.Request(self.url, headers={'User-Agent': 'Mozilla/5.0'})
            
            with urllib.request.urlopen(req) as response:
                total_size = int(response.info().get('Content-Length', 0))
                block_size = 8 * 1024 * 1024 # 8MB chunks
                downloaded = 0
                
                with open(self.filepath, 'wb') as f:
                    while True:
                        if self.isInterruptionRequested():
                            if self.log_callback:
                                self.log_callback("다운로드 취소됨.")
                            if self.finished_callback:
                                self.finished_callback(False, "Canceled")
                            return
                            
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        f.write(buffer)
                        downloaded += len(buffer)
                        
                        if total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            if self.progress_callback:
                                self.progress_callback(percent)
                            
            if self.progress_callback:
                self.progress_callback(100)
            if self.log_callback:
                self.log_callback("다운로드 및 검증 완료.")
            if self.finished_callback:
                self.finished_callback(True, self.filepath)
            
        except Exception as e:
            if self.log_callback:
                self.log_callback(f"다운로드 실패: {e}")
            if os.path.exists(self.filepath):
                try:
                    os.remove(self.filepath)
                except:
                    pass
            if self.finished_callback:
                self.finished_callback(False, str(e))

