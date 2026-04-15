from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QProgressBar, QListWidget, QListWidgetItem, QWidget, QTextEdit)
from PyQt6.QtCore import Qt
from core.bootstrap import HardwareProfiler, ModelDownloader
from core.config import AVAILABLE_MODELS

class Style:
    MODAL_BG = "#1e272e"
    TEXT = "#dcdde1"
    BTN_PRIMARY = "#0984e3"
    BTN_DISABLED = "#636e72"
    BTN_INSTALL = "#00b894"

class StartupModelModal(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AMEVA System Boot - AI Model Selection")
        self.setFixedSize(550, 450)
        self.setStyleSheet(f"background-color: {Style.MODAL_BG}; color: {Style.TEXT}; font-family: 'Segoe UI';")
        self.selected_model_path = None
        self.downloader = None

        self.init_ui()
        self.load_specs()
        self.load_models()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Header
        title = QLabel("🖥️ AMEVA Startup & Hardware Check")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #fbc531;")
        layout.addWidget(title)
        
        # Spec Panel
        self.spec_label = QLabel("Analyzing hardware...")
        self.spec_label.setStyleSheet("background: #2f3640; padding: 10px; border-radius: 8px;")
        layout.addWidget(self.spec_label)

        # Action Label
        act_label = QLabel("📌 Recommended Models (Select one to Boot)")
        act_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(act_label)

        # Model List
        self.model_list = QListWidget()
        self.model_list.setStyleSheet("background: #2f3640; border-radius: 8px; outline: none; padding: 5px;")
        layout.addWidget(self.model_list)
        
        # Download Panel (Hidden initially)
        self.download_panel = QWidget()
        dl_layout = QVBoxLayout(self.download_panel)
        dl_layout.setContentsMargins(0,0,0,0)
        self.dl_status = QLabel("Ready")
        self.dl_progress = QProgressBar()
        self.dl_progress.setTextVisible(False)
        self.dl_progress.setStyleSheet("QProgressBar { border: 1px solid #7f8fa6; border-radius: 5px; height: 10px; } QProgressBar::chunk { background-color: #00b894; border-radius: 5px; }")
        dl_layout.addWidget(self.dl_status)
        dl_layout.addWidget(self.dl_progress)
        self.download_panel.hide()
        layout.addWidget(self.download_panel)

    def load_specs(self):
        specs = HardwareProfiler.get_system_specs()
        txt = (f"RAM: {specs['ram_gb']} GB | CPU Cores: {specs['cpu_cores']}\n"
               f"GPU: {specs['gpu_name']} (VRAM: {specs['gpu_vram_gb']} GB)")
        self.spec_label.setText(txt)

    def load_models(self):
        self.model_list.clear()
        models = HardwareProfiler.recommend_models()
        self.current_rendered_models = models
        
        for idx, m in enumerate(models):
            item = QListWidgetItem()
            widget = QWidget()
            wl = QHBoxLayout(widget)
            wl.setContentsMargins(5, 5, 5, 5)

            name_lbl = QLabel(f"{m['name']} {'⭐ Rec.' if m['recommended'] else ''}")
            name_lbl.setStyleSheet("font-weight: bold;" if m['recommended'] else "")
            
            btn = QPushButton()
            btn.setFixedSize(100, 30)
            btn.setStyleSheet("border-radius: 5px; font-weight: bold;")
            
            if m["is_installed"]:
                btn.setText("Load")
                btn.setStyleSheet(f"background: {Style.BTN_PRIMARY}; color: white;")
                btn.clicked.connect(lambda chk, i=idx: self.select_model(i))
            else:
                btn.setText("Install")
                btn.setStyleSheet(f"background: {Style.BTN_INSTALL}; color: white;")
                btn.clicked.connect(lambda chk, i=idx: self.install_model(i))
            
            wl.addWidget(name_lbl)
            wl.addStretch()
            wl.addWidget(btn)
            
            item.setSizeHint(widget.sizeHint())
            self.model_list.addItem(item)
            self.model_list.setItemWidget(item, widget)

    def install_model(self, model_idx):
        if self.downloader and self.downloader.isRunning():
            return

        m = self.current_rendered_models[model_idx]
        self.model_list.setEnabled(False)
        self.download_panel.show()
        
        self.downloader = ModelDownloader(m["url"], m["filename"])
        self.downloader.progress.connect(self.dl_progress.setValue)
        self.downloader.log_signal.connect(self.dl_status.setText)
        self.downloader.finished_signal.connect(self.on_download_finished)
        self.downloader.start()

    def on_download_finished(self, success, path):
        self.download_panel.hide()
        self.model_list.setEnabled(True)
        if success:
            self.load_models() # Refresh UI to show "Load"
        else:
            self.dl_status.setText(f"Error: {path}")

    def select_model(self, model_idx):
        from core.config import MODEL_DIR
        import os
        m = self.current_rendered_models[model_idx]
        self.selected_model_path = os.path.join(MODEL_DIR, m["filename"])
        self.accept()


class AgentLogModal(QDialog):
    def __init__(self, agent_id, parent=None):
        super().__init__(parent)
        self.agent_id = agent_id
        self.setWindowTitle(f"{agent_id.upper()} Log")
        self.setWindowModality(Qt.WindowModal)
        self.resize(620, 420)
        self.setStyleSheet("background:#1e272e; color:#f5f6fa; font-family: 'Segoe UI';")

        layout = QVBoxLayout(self)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background:#121f2f; color:#f5f6fa; border-radius:8px; padding:10px;")
        layout.addWidget(self.log_text)

    def append_log(self, message):
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def closeEvent(self, event):
        self.hide()
        event.accept()
