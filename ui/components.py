from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QProgressBar, QPushButton
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPainter, QPen

class ResourceGraph(QFrame):
    """엔터프라이즈 모니터링: CPU, RAM, GPU 사용률 실시간 그래프"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(140)
        self.cpu_h, self.ram_h, self.gpu_h = [0]*50, [0]*50, [0]*50
        
    def update_data(self, c, r, g):
        self.cpu_h.pop(0); self.cpu_h.append(c)
        self.ram_h.pop(0); self.ram_h.append(r)
        self.gpu_h.pop(0); self.gpu_h.append(g)
        self.update()
        
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#1e272e"))
        p.setPen(QPen(QColor("#3d4b53"), 1, Qt.PenStyle.DashLine))
        p.drawLine(0, h//2, w, h//2)
        
        def draw_line(data, color):
            p.setPen(QPen(QColor(color), 2))
            for i in range(len(data)-1):
                p.drawLine(int((i/50)*w), int(h-(data[i]/100)*h), int(((i+1)/50)*w), int(h-(data[i+1]/100)*h))
                
        draw_line(self.cpu_h, "#e67e22") # CPU logic
        draw_line(self.ram_h, "#3498db") # RAM
        draw_line(self.gpu_h, "#2ecc71") # GPU

class AgentWidget(QFrame):
    """에이전트 카드: 상태, 토큰 사용량, 진행도 표시"""
    detail_requested = pyqtSignal(str)

    def __init__(self, a_id, emoji, name, rank, parent=None):
        super().__init__(parent)
        self.a_id = a_id
        self.rank = rank
        self.setFixedSize(180, 240)
        self.home_pos = QPoint(0,0)
        
        self.bg_color = '#f39c12' if rank == 'noble' else '#1abc9c' if rank == 'writer' else '#2980b9'
        self.setStyleSheet(f"background: {self.bg_color}; border-radius:15px; border:2px solid #222f3e;")
        
        l = QVBoxLayout(self)
        self.emo = QLabel(emoji)
        self.emo.setFont(QFont("Arial", 48))
        self.emo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.nm = QLabel(name)
        self.nm.setStyleSheet("font-weight:bold; font-size:14px; color:white;")
        self.nm.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.st = QLabel("💤 Standby")
        self.st.setStyleSheet("font-size:11px; color:#ecf0f1;")
        self.st.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.task = QLabel("Task: None")
        self.task.setWordWrap(True)
        self.task.setStyleSheet("font-size:10px; color:#f5f6fa;")
        
        self.passed = QLabel("Received: None")
        self.passed.setWordWrap(True)
        self.passed.setStyleSheet("font-size:10px; color:#dcdde1;")
        
        self.runtime = QLabel("Elapsed: 0s")
        self.runtime.setStyleSheet("font-size:10px; color:#dcdde1;")
        self.runtime.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.tk = QLabel("P:0 / C:0")
        self.tk.setStyleSheet("font-family:Consolas; font-size:10px; color:#ecf0f1;")
        self.tk.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.detail_btn = QPushButton("Details")
        self.detail_btn.setFixedHeight(24)
        self.detail_btn.setStyleSheet("background:#000000; color:#ffffff; border-radius:6px; font-size:10px;")
        self.detail_btn.clicked.connect(lambda: self.detail_requested.emit(self.a_id))
        
        self.pr = QProgressBar()
        self.pr.setFixedHeight(12)
        self.pr.setRange(0, 0)
        self.pr.setStyleSheet("QProgressBar { border-radius: 6px; background-color: #34495e; text-align: center; color: transparent; } QProgressBar::chunk { background-color: #2ecc71; border-radius: 6px; }")
        self.pr.hide()
        
        l.addWidget(self.emo)
        l.addWidget(self.nm)
        l.addWidget(self.st)
        l.addWidget(self.task)
        l.addWidget(self.passed)
        l.addWidget(self.runtime)
        l.addWidget(self.tk)
        l.addWidget(self.detail_btn)
        l.addWidget(self.pr)

    def update_usage(self, u):
        self.tk.setText(f"P:{u.get('prompt_tokens', 0)} / C:{u.get('completion_tokens', 0)}")

    def update_task(self, instruction, passed_result):
        self.task.setText(f"Task: {instruction[:64]}" if instruction else "Task: None")
        self.passed.setText(f"Received: {passed_result[:64]}" if passed_result else "Received: None")

    def update_runtime(self, elapsed_seconds):
        mins, secs = divmod(int(elapsed_seconds), 60)
        self.runtime.setText(f"Elapsed: {mins}m {secs}s")

    def set_working(self, is_w, txt="🔥 Working"):
        if is_w: 
            self.st.setText(txt)
            self.pr.show()
            self.setStyleSheet("background: #c0392b; border-radius:15px; border:3px solid #e74c3c;")
        else: 
            self.st.setText("💤 Standby")
            self.pr.hide()
            self.setStyleSheet(f"background: {self.bg_color}; border-radius:15px; border: 2px solid #222f3e;")
