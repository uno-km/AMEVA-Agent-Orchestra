import os
import psutil
from datetime import datetime
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QTextEdit, QLineEdit, QPushButton, QLabel, QFrame, QListWidget, QComboBox, QMessageBox)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QPoint, QEasingCurve, pyqtSlot
from ui.components import ResourceGraph, AgentWidget
from ui.modals import StartupModelModal, AgentLogModal
from agents.orchestrator import Orchestrator
from core.llm_engine import LlamaInferenceCore
from core.sre import WorkspaceWatcher, WatchdogSignalEmitter, logger
from core.config import MEMORY_DIR, WORKSPACE_DIR
from watchdog.observers import Observer

class CodeGodEnterprise(QMainWindow):
    def __init__(self):
        super().__init__()
        self.agents = {}
        self.anims = {}
        self.orchestrator = Orchestrator()
        self.orchestrator.worker_started.connect(self.on_worker_started)
        self.orchestrator.task_assigned.connect(self.on_task_assigned)
        self.orchestrator.worker_finished.connect(self.on_worker_done)
        self.orchestrator.worker_error.connect(self.on_worker_fail)
        self.orchestrator.handoff_triggered.connect(self.trigger_handoff)

        self.agent_start_times = {}
        self.agent_log_messages = {}
        self.agent_modals = {}

        self.init_ui()
        self.setup_agents()
        self.setup_sre_police()
        self.setup_watchdog_bridge()
        logger.info("SYSTEM: AMEVA 통합 관제 콘솔 가동.")

    def init_ui(self):
        self.setWindowTitle("AMEVA Agent Orchestra - Enterprise Console")
        self.setGeometry(10, 10, 1800, 1050)
        self.setStyleSheet("background-color: #2f3640; color: white; font-family: 'Segoe UI';")
        
        c = QWidget()
        self.setCentralWidget(c)
        ml = QHBoxLayout(c)
        
        # [좌측 영역] 대시보드 및 로그
        ll = QVBoxLayout()
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("🏢 AGENT OPERATIONS BOARD"))
        
        self.concurrency_combo = QComboBox()
        self.concurrency_combo.addItems([str(i) for i in range(1, 9)])
        self.concurrency_combo.setCurrentText("1")
        self.concurrency_combo.setStyleSheet("background: #1e272e; padding: 5px; border-radius: 5px;")
        self.concurrency_combo.currentTextChanged.connect(
            lambda t: self.orchestrator.set_max_processors(int(t))
        )
        header_layout.addStretch()
        header_layout.addWidget(QLabel("Max Concurrent Processors:"))
        header_layout.addWidget(self.concurrency_combo)
        
        ll.addLayout(header_layout)
        
        self.office = QFrame()
        self.office.setMinimumHeight(560)
        self.office.setStyleSheet("background:#353b48; border-radius:25px; border:1px solid #7f8fa6;")
        ll.addWidget(self.office)
        
        il = QHBoxLayout()
        self.chat = QLineEdit()
        self.chat.setPlaceholderText("오케스트라 가동 지시 (예: SQLite를 사용하는 연락처 관리 프로그램 짜줘)...")
        self.chat.setStyleSheet("padding:22px; background:#222f3e; border-radius:12px; font-size:16px; border:1px solid #718093;")
        self.chat.returnPressed.connect(self.process_command)
        
        rb = QPushButton("⚡ 지휘 개시")
        rb.clicked.connect(self.process_command)
        rb.setStyleSheet("background:#0097e6; padding:22px; font-weight:bold; border-radius:12px; font-size:16px;")
        
        il.addWidget(self.chat, 7)
        il.addWidget(rb, 1)
        ll.addLayout(il)
        
        ll.addWidget(QLabel("🖥️ SYSTEM TRACE LOG"))
        self.log_v = QTextEdit()
        self.log_v.setReadOnly(True)
        self.log_v.setStyleSheet("background:#1e272e; color:#4cd137; font-family:Consolas; border-radius:10px;")
        ll.addWidget(self.log_v)

        # [우측 영역] 모니터링 및 기억소장고
        rl = QVBoxLayout()
        rl.addWidget(QLabel("📈 REAL-TIME INFRA RESOURCES"))
        self.graph = ResourceGraph()
        rl.addWidget(self.graph)

        self.resource_status = QLabel("CPU: 0% | RAM: 0% | GPU: 0%")
        self.resource_status.setStyleSheet("font-size:12px; color:#dcdde1; margin-bottom:8px;")
        rl.addWidget(self.resource_status)
        
        rl.addWidget(QLabel("🚨 WATCHDOG & SRE EVENTS"))
        self.sre_trace = QTextEdit()
        self.sre_trace.setReadOnly(True)
        self.sre_trace.setFixedHeight(180)
        self.sre_trace.setStyleSheet("background:#1e272e; color:#e1b12c; font-family:Consolas; border-radius:10px;")
        rl.addWidget(self.sre_trace)
        
        rl.addWidget(QLabel("📂 PERSISTENT MEMORY ASSETS"))
        self.m_list = QListWidget()
        self.m_list.setFixedHeight(130)
        self.m_list.addItems(["command_memory.md", "file_memory.md", "code_memory.md", "doc_memory.md"])
        self.m_list.itemClicked.connect(self.view_m)
        self.m_list.setStyleSheet("background:#353b48; border-radius:8px;")
        rl.addWidget(self.m_list)
        
        self.m_view = QTextEdit()
        self.m_view.setReadOnly(True)
        self.m_view.setStyleSheet("background:#2f3640; color:#dcdde1; font-family:Consolas; border-radius:8px; border:1px solid #7f8fa6;")
        rl.addWidget(self.m_view)

        ml.addLayout(ll, 2)
        ml.addLayout(rl, 1)

    def setup_agents(self):
        roles = [
            ("command", "🐶", 270, 75, "noble"), 
            ("secretary", "🎩", 720, 75, "noble"), 
            ("file", "🐹", 130, 350, "dev"), 
            ("code", "🦊", 480, 350, "dev"), 
            ("doc", "🐻", 830, 350, "writer")
        ]
        for aid, emo, x, y, rank in roles:
            a = AgentWidget(aid, emo, aid.upper(), rank, self.office)
            a.home_pos = QPoint(x, y)
            a.move(a.home_pos)
            a.detail_requested.connect(self.open_agent_log)
            self.agents[aid] = a
            self.agent_log_messages[aid] = []

    def setup_sre_police(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.monitor)
        self.timer.start(2000)

    def setup_watchdog_bridge(self):
        self.emitter = WatchdogSignalEmitter()
        self.emitter.file_modified.connect(self.log_msg)
        self.observer = Observer()
        self.observer.schedule(WorkspaceWatcher(self.emitter), WORKSPACE_DIR, recursive=True)
        self.observer.start()

    def monitor(self):
        c = psutil.cpu_percent()
        r = psutil.virtual_memory().percent
        g = LlamaInferenceCore.get_instance().get_gpu_load_safe()
        self.graph.update_data(c, r, g)
        self.resource_status.setText(f"CPU: {c}% | RAM: {r}% | GPU: {int(g)}%")
        self.update_agent_runtimes()
        
        if r > 93.0:
            self.sre_trace.append("🚨 [CRITICAL] RAM 과부하! OS OOM 보호를 위해 워커 강제 종료...")
            self.orchestrator.shutdown_all()

    def log_msg(self, msg, lvl="INFO"):
        tk = LlamaInferenceCore.get_instance().total_tokens_used
        self.log_v.append(f"[{datetime.now().strftime('%H:%M:%S')}] [{lvl}] (Σ: {tk}) {msg}")

    def process_command(self):
        req = self.chat.text().strip()
        if not req: return
        self.chat.clear()
        self.log_msg(f"COMMANDER: {req}")
        self.orchestrator.start_mission(req)

    @pyqtSlot(str)
    def on_worker_started(self, aid):
        if aid in self.agents:
            self.agents[aid].set_working(True)
            self.agent_start_times[aid] = datetime.now()
            self.append_agent_history(aid, "Worker started.")

    @pyqtSlot(str, str)
    def on_worker_fail(self, aid, err):
        self.log_msg(f"[{aid}] FAILED: {err[:120]}", "ERROR")
        if aid in self.agents:
            self.agents[aid].set_working(False)
            if aid in self.agent_start_times:
                elapsed = (datetime.now() - self.agent_start_times.pop(aid)).total_seconds()
                self.agents[aid].update_runtime(elapsed)
        self.append_agent_history(aid, f"Task failed: {err[:120]}")

    @pyqtSlot(str, dict, dict)
    def on_worker_done(self, aid, res, usage):
        if aid in self.agents:
            self.agents[aid].set_working(False)
            self.agents[aid].update_usage(usage)
            if aid in self.agent_start_times:
                elapsed = (datetime.now() - self.agent_start_times.pop(aid)).total_seconds()
                self.agents[aid].update_runtime(elapsed)
        
        status = res.get("status", 200)
        if status >= 400:
            self.log_msg(f"[{aid}] ERROR: {res.get('message', 'Unknown error')} (status={status})", "ERROR")
            self.append_agent_history(aid, f"Task failed: {res.get('message', 'Unknown error')} (status={status})")
            return
        if status == 300:
            self.log_msg(f"[{aid}] TERMINATED: {res.get('message', 'Task ended with no further action.')}")
            self.append_agent_history(aid, f"Task terminated: {res.get('message', 'Task ended with no further action.')}")
            return
        
        self.log_msg(f"[{aid}] COMPLETED: {res.get('message', 'Mission Done.')}")
        self.append_agent_history(aid, f"Task completed: {res.get('message', 'Mission Done.')}")
        
        # 비서 보고
        if aid == "secretary":
            QMessageBox.information(self, "SECRETARY REPORT", res.get('message'))

    @pyqtSlot(str, str, dict)
    def trigger_handoff(self, fid, tid, nt):
        if fid not in self.agents or tid not in self.agents:
            self.orchestrator.dispatch_worker(tid, nt) # fallback
            return
            
        fa = self.agents[fid]
        ta = self.agents[tid]
        
        anim = QPropertyAnimation(fa, b"pos", self)
        anim.setDuration(800)
        anim.setStartValue(fa.home_pos)
        anim.setEndValue(ta.home_pos)
        anim.setEasingCurve(QEasingCurve.Type.OutBounce)
        
        anim.finished.connect(lambda: self._finish_handoff(fa, tid, nt))
        self.anims[fid] = anim
        anim.start()

    def _finish_handoff(self, fa, tid, nt):
        fa.move(fa.home_pos)
        self.orchestrator.dispatch_worker(tid, nt)

    def view_m(self, item):
        p = os.path.join(MEMORY_DIR, item.text())
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f: 
                self.m_view.setText(f.read())

    @pyqtSlot(str, dict)
    def on_task_assigned(self, aid, task_data):
        if aid in self.agents:
            instruction = task_data.get("instruction", "None")
            passed = task_data.get("passed_result", "None")
            self.agents[aid].update_task(instruction, passed)
            self.append_agent_history(aid, f"Assigned task: {instruction}\nReceived: {passed}")

    def append_agent_history(self, aid, message):
        if aid not in self.agent_log_messages:
            self.agent_log_messages[aid] = []
        formatted = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
        self.agent_log_messages[aid].append(formatted)
        if aid in self.agent_modals and self.agent_modals[aid].isVisible():
            self.agent_modals[aid].append_log(formatted)

    def open_agent_log(self, aid):
        if aid not in self.agent_modals:
            self.agent_modals[aid] = AgentLogModal(aid, self)
        modal = self.agent_modals[aid]
        modal.log_text.clear()
        if self.agent_log_messages.get(aid):
            for line in self.agent_log_messages[aid]:
                modal.append_log(line)
        if not modal.isVisible():
            modal.show()
        modal.raise_()
        modal.activateWindow()

    def update_agent_runtimes(self):
        for aid, start_time in self.agent_start_times.items():
            if aid in self.agents:
                elapsed = (datetime.now() - start_time).total_seconds()
                self.agents[aid].update_runtime(elapsed)

    def closeEvent(self, event):
        self.observer.stop()
        self.observer.join()
        self.orchestrator.shutdown_all()
        event.accept()
