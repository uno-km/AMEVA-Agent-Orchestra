import sys
import json
import time
import os
import re
import ast
import traceback
import psutil
import logging
import threading
import GPUtil
from logging.handlers import RotatingFileHandler
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTextEdit, QLineEdit, QPushButton, 
                             QLabel, QTabWidget, QFrame, QSplitter, QListWidget,
                             QMessageBox, QProgressBar)
from PyQt6.QtCore import (Qt, QTimer, QPropertyAnimation, QPoint, QObject,
                          QThread, pyqtSignal, QEasingCurve, pyqtSlot)
from PyQt6.QtGui import QFont, QColor, QPainter, QPen

# ==============================================================================
# [0] 시스템 전역 환경 설정 및 보안 상수
# ==============================================================================
# UI 파서 및 마크다운 코드 펜스 충돌을 방지하기 위한 유니코드 우회 선언
BT = "\x60\x60\x60" 

# 엔터프라이즈 인프라 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "CodeGod_Logs")
WORKSPACE_DIR = os.path.join(BASE_DIR, "CodeGod_Workspace") 
MEMORY_DIR = os.path.join(BASE_DIR, "CodeGod_Memory")       
MODEL_PATH = os.path.join(BASE_DIR, "qwen.gguf")

# 보안 화이트리스트 확장자
ALLOWED_EXTENSIONS = ('.py', '.md', '.txt', '.js', '.html', '.json', '.css', '.yaml', '.yml')

# 인프라 디렉토리 물리적 존재 보장
for path in [LOG_DIR, WORKSPACE_DIR, MEMORY_DIR]:
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

# ==============================================================================
# [1] 엔터프라이즈 급 SRE 로깅 시스템 구축
# ==============================================================================
logger = logging.getLogger("AMEVA_Orchestra")
logger.setLevel(logging.DEBUG)

# 파일 로깅: 20MB 단위로 10개의 순환 로그 파일 유지 (시스템 정밀 추적)
file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, "system_orchestra_v27.log"), 
    maxBytes=20*1024*1024, 
    backupCount=10, 
    encoding="utf-8"
)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# 콘솔 로깅: 실시간 모니터링
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# ==============================================================================
# [2] 보안 엔진: 강화된 샌드박스 및 차등 스캐너
# ==============================================================================
def enforce_sandbox(target_path):
    """
    Path Traversal 및 심볼릭 링크 공격을 물리적으로 차단하는 강화된 샌드박스.
    realpath를 사용하여 모든 우회 경로를 해제한 후 검증합니다.
    """
    if not target_path or not isinstance(target_path, str):
        raise PermissionError("유효하지 않은 경로 데이터가 입력되었습니다.")
    
    # 1. 경로 정규화 및 실제 물리 경로 추출
    abs_target = os.path.realpath(os.path.join(WORKSPACE_DIR, target_path))
    
    # 2. 루트 디렉토리 이탈 검사 (Strict Prefix Check)
    if not abs_target.startswith(WORKSPACE_DIR + os.sep):
        logger.critical(f"SANDBOX BREACH ATTEMPT: {target_path}")
        raise PermissionError(f"[보안] 지정된 작업 공간(Workspace) 외부로 나갈 수 없습니다.")
    
    # 3. 확장자 화이트리스트 검사
    if not abs_target.lower().endswith(ALLOWED_EXTENSIONS):
        raise PermissionError(f"[보안] 허용되지 않는 파일 형식입니다: {os.path.splitext(abs_target)[1]}")
        
    return abs_target

def scan_malicious_content(content, filename, agent_id):
    """
    생성된 코드 내 위험 명령어를 스캔합니다. 
    문서 작업(doc)과 코딩 작업(code)에 대해 차등화된 보안 정책을 적용합니다.
    """
    if filename.endswith(".md") or agent_id == "doc":
        # 문서는 텍스트 설명이므로 엄격한 키워드 차단 대신 경고 로깅만 수행
        return

    # 난독화 및 우회 패턴을 포함한 정밀 위험 키워드 셋
    danger_patterns = [
        (r"os\.(remove|rmdir|system|spawn|exe|popen|kill|chmod)", "OS 파괴 및 권한 조작 명령"),
        (r"shutil\.(rmtree|move|copy)", "파일 시스템 대량 조작"),
        (r"subprocess\.", "외부 프로세스 제어 권한 탈취"),
        (r"(socket|urllib|requests|http\.client)\.", "비인가 네트워크 연결"),
        (r"eval\(|exec\(", "동적 코드 실행 취약점"),
        (r"__import__", "모듈 은닉 로딩 시도"),
        (r"base64\.b64decode", "난독화 해제 의심 패턴"),
        (r"pathlib\.Path\..*?\.unlink", "파일 시스템 영구 삭제 명령")
    ]
    
    for pattern, desc in danger_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            logger.warning(f"MALICIOUS CODE BLOCKED: {desc} in {filename} by {agent_id}")
            raise ValueError(f"보안 위험 요소 감지({desc})로 인해 작성이 강제 중단되었습니다.")

# ==============================================================================
# [3] 데이터 파서 및 시그널 인터페이스 (Watchdog Bridge)
# ==============================================================================
class WatchdogSignalEmitter(QObject):
    """Watchdog(별도 스레드)의 이벤트를 UI 스레드로 안전하게 전달하는 시그널 브릿지"""
    file_modified = pyqtSignal(str, str)

class StrictParser:
    """중괄호 스택 기반의 정밀 JSON 객체 적출 및 위생 처리기"""
    
    @staticmethod
    def extract_first_valid_json(text):
        """
        중괄호 스택 알고리즘을 사용하여 텍스트 내에서 첫 번째로 완결된 JSON 객체만 적출합니다.
        LLM의 앞뒤 수다나 부연 설명을 완벽하게 무시합니다.
        """
        start_idx = text.find('{')
        if start_idx == -1:
            raise ValueError("JSON 데이터의 시작점({)을 찾을 수 없습니다.")
            
        stack = 0
        for i in range(start_idx, len(text)):
            if text[i] == '{':
                stack += 1
            elif text[i] == '}':
                stack -= 1
                if stack == 0:
                    return text[start_idx:i+1]
        
        raise ValueError("JSON 중괄호 쌍이 일치하지 않아 파싱할 수 없습니다.")

    @staticmethod
    def parse_response(text_output):
        """
        1차: 표준 JSON 로드
        2차: 마크다운 펜스 제거 후 로드
        3차: 스택 기반 객체 추출 (최후 구출)
        """
        clean_text = text_output.strip()
        
        # 1. 다이렉트 json.loads
        try:
            return json.loads(clean_text)
        except: pass

        # 2. 마크다운 코드 블록 우회 파싱
        json_pattern = rf'{BT}json\s*(.*?)\s*{BT}'
        match = re.search(json_pattern, clean_text, re.DOTALL)
        if match:
            try: return json.loads(match.group(1))
            except: pass

        # 3. 스택 기반 최후 구출 로직 가동
        try:
            target_json_str = StrictParser.extract_first_valid_json(clean_text)
            return json.loads(target_json_str)
        except Exception as e:
            logger.error(f"HYBRID PARSE FAILED: {str(e)}")
            raise ValueError("유효한 JSON 구조를 식별할 수 없습니다.")

    @staticmethod
    def sanitize_code(content, filename, agent_id):
        """코드 추출, 인사말 필터링, 보안 스캔, 문법 검증 통합"""
        # 마크다운 블록 적출
        code_pattern = rf'{BT}(?:python|js|javascript|html|css)?\s*(.*?)\s*{BT}'
        code_match = re.search(code_pattern, content, re.DOTALL)
        clean_code = code_match.group(1).strip() if code_match else content
        
        # README.md 파일이 아닐 때만 한국어 군더더기 서술어 제거
        if not filename.endswith(".md"):
            lines = clean_code.split('\n')
            clean_lines = [l for l in lines if not re.match(r'^(안녕하세요|반갑습니다|감사합니다|네, 알겠습니다|결과입니다|코드입니다)', l.strip())]
            clean_code = '\n'.join(clean_lines).strip()

        # 보안 스캐너 가동
        scan_malicious_content(clean_code, filename, agent_id)

        # 파이썬 문법 검증 (AST)
        if filename.endswith(".py") and clean_code:
            try:
                ast.parse(clean_code)
                logger.info(f"AST VERIFIED: {filename}")
            except SyntaxError as se:
                logger.error(f"SYNTAX ERROR in {filename}: {se}")
                raise SyntaxError(f"파이썬 문법 오류가 감지되었습니다: {se.msg}")
                
        return clean_code

# ==============================================================================
# [4] 스레드 경합 차단 및 최적화 LLM 엔진 (The Core)
# ==============================================================================
class LlamaInferenceCore:
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = LlamaInferenceCore()
        return cls._instance

    def __init__(self):
        self.is_loaded = False
        self.total_tokens_used = 0
        self.token_lock = threading.Lock()
        self.inference_lock = threading.Lock() # 동시 추론 방지를 위한 핵심 뮤텍스
        
        # GPU 리소스 캐싱 (불필요한 반복 호출 방지)
        self.cached_gpu_load = 0
        self.last_gpu_check = 0

        try:
            from llama_cpp import Llama
            logger.info("CORE: 하드웨어 프로파일링 기반 엔진 최적화 시작...")
            
            # 1. 물리 코어 기반 멀티스레딩 최적화
            opt_threads = max(1, psutil.cpu_count(logical=False))
            
            # 2. GPU 가속 환경 정밀 진단
            gpu_layers = 0
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu_layers = -1 # 모든 연산 레이어를 VRAM으로 최대 오프로드
                    logger.info(f"CORE: GPU 가속 활성화 -> {gpus[0].name} (VRAM: {gpus[0].memoryTotal}MB)")
                else:
                    logger.info("CORE: NVIDIA GPU 미감지. CPU 연산 모드로 구동합니다.")
            except Exception as e: 
                logger.warning(f"CORE: GPUtil 접근 실패 ({e}). 기본 모드 사용.")

            if not os.path.exists(MODEL_PATH):
                raise FileNotFoundError(f"모델 파일이 존재하지 않습니다: {MODEL_PATH}")

            # 3. Llama-cpp 엔진 적재
            self.llm = Llama(
                model_path=MODEL_PATH, 
                n_ctx=4096, 
                n_threads=opt_threads,
                n_gpu_layers=gpu_layers,
                use_mmap=True,
                verbose=False
            )
            self.is_loaded = True
            logger.info(f"CORE: 엔진 가동 준비 완료. (Threads: {opt_threads})")
        except Exception as e:
            self.llm = None
            logger.critical(f"CORE: 치명적 엔진 적재 오류: {e}")

    def get_gpu_load_safe(self):
        """UI 타이머 부하를 줄이기 위한 캐싱된 GPU 정보 반환"""
        now = time.time()
        if now - self.last_gpu_check > 5:
            try:
                gpus = GPUtil.getGPUs()
                self.cached_gpu_load = gpus[0].load * 100 if gpus else 0
                self.last_gpu_check = now
            except: self.cached_gpu_load = 0
        return self.cached_gpu_load

    def generate(self, system_p, user_p, schema_type="worker"):
        """
        schema_type에 따른 Guided Generation 수행.
        'architect' 타입은 전체 에이전트 파이프라인 계획을 강제합니다.
        """
        if not self.is_loaded:
            return {"status": 503, "message": "모델 엔진 미로드"}, {"prompt_tokens": 0, "completion_tokens": 0}

        # 에이전트 역할별 JSON Schema 정의
        if schema_type == "architect":
            schema = {
                "type": "object",
                "properties": {
                    "plan": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "target": {"type": "string"},
                                "instruction": {"type": "string"}
                            },
                            "required": ["target", "instruction"]
                        }
                    },
                    "summary": {"type": "string"}
                },
                "required": ["plan", "summary"]
            }
        else:
            schema = {
                "type": "object",
                "properties": {
                    "status": {"type": "integer"},
                    "file_name": {"type": "string"},
                    "content": {"type": "string"},
                    "message": {"type": "string"}
                },
                "required": ["status", "file_name", "content"]
            }

        # [핵심] 여러 에이전트가 동시에 엔진을 호출하지 못하도록 락을 겁니다. (Race Condition 방지)
        with self.inference_lock:
            try:
                prompt = f"<|im_start|>system\n{system_p}\nJSON Only.<|im_end|>\n<|im_start|>user\n{user_p}<|im_end|>\n<|im_start|>assistant\n"
                
                response = self.llm(
                    prompt, 
                    max_tokens=2500, 
                    stop=["<|im_end|>"], 
                    temperature=0.1,
                    response_format={"type": "json_object", "schema": schema}
                )
                
                text_output = response['choices'][0]['text'].strip()
                
                # Usage 데이터 확보 (Fallback: 문자수 기반 추정)
                usage = response.get('usage')
                if not usage:
                    p_tk, c_tk = len(prompt)//3, len(text_output)//3
                    usage = {"prompt_tokens": p_tk, "completion_tokens": c_tk, "total_tokens": p_tk + c_tk}
                
                # 스레드 안전하게 누적 토큰 합산
                with self.token_lock:
                    self.total_tokens_used += usage.get('total_tokens', 0)
                
                # 하이브리드 파싱 (표준 -> 구출)
                try:
                    parsed_json = json.loads(text_output)
                except:
                    parsed_json = StrictParser.parse_response(text_output)
                    
                return parsed_json, usage
            except Exception as e:
                logger.error(f"GENERATE FATAL: {e}")
                return {"status": 500, "message": str(e)}, {"prompt_tokens": 0, "completion_tokens": 0}

# ==============================================================================
# [5] 자율 에이전트 워커: 일감 꾸러미(Task Plan) 전달 로직
# ==============================================================================
class AgentWorker(QThread):
    finished_task = pyqtSignal(str, dict, dict, dict)
    error_signal = pyqtSignal(str, str)
    
    def __init__(self, agent_id, role_prompt, task_data):
        super().__init__()
        self.agent_id = agent_id
        self.role_prompt = role_prompt
        self.task_data = task_data # 'plan' 배열과 'instruction'이 포함됨
        self.heartbeat = time.time()
        self.llm_core = LlamaInferenceCore.get_instance()

    def run(self):
        try:
            # 작업 시작 전 중단 요청 확인
            if self.isInterruptionRequested(): return
            self.heartbeat = time.time()
            
            # 컨텍스트 및 지시사항 조립
            past_mem = self.read_memory()
            instruction = self.task_data.get("instruction", "주어진 목표를 완수하십시오.")
            passed_result = self.task_data.get("passed_result", "이전 에이전트의 산출물 없음.")
            
            full_prompt = f"### [PAST LOGS]\n{past_mem}\n\n### [INPUT DATA]\n{passed_result}\n\n### [MISSION]\n{instruction}"
            
            # 아키텍트(command) 여부에 따른 스키마 분기
            stype = "architect" if self.agent_id == "command" else "worker"
            result_json, usage = self.llm_core.generate(self.role_prompt, full_prompt, schema_type=stype)
            
            # 추론 후 중단 요청 확인 (파일 쓰기 이전)
            if self.isInterruptionRequested(): return

            # [핵심] 파일 생성형 에이전트(file, code, doc)만 물리 파일 작업 수행
            if self.agent_id not in ["command", "secretary"]:
                if result_json.get("status") == 200 and "file_name" in result_json:
                    if "content" in result_json and isinstance(result_json["content"], str):
                        safe_path = enforce_sandbox(result_json["file_name"])
                        
                        # 하위 디렉토리 자동 생성 (계층 구조 지원)
                        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
                        
                        # 코드 정제 및 검증
                        final_content = StrictParser.sanitize_code(result_json["content"], result_json["file_name"], self.agent_id)
                        
                        with open(safe_path, 'w', encoding='utf-8') as f:
                            f.write(final_content)
                        
                        result_json["message"] = f"성공: {result_json['file_name']} 파일 작성 완료"
                        self.save_memory(instruction, result_json["message"])

            # [핵심] 일감 꾸러미(Task Plan) 릴레이 로직
            next_plan = self.task_data.get("plan", [])
            
            # 아키텍트가 새로 수립한 계획이 있다면 주입
            if self.agent_id == "command" and "plan" in result_json:
                next_plan = result_json["plan"]
                result_json["message"] = result_json.get("summary", "전체 파이프라인 설계 완료.")

            next_task = None
            if next_plan:
                next_task = next_plan.pop(0) # 다음 에이전트 할일 꺼내기
                next_task["plan"] = next_plan # 남은 할일들 전달
                # 이전 결과 데이터 전파
                next_task["passed_result"] = f"Prev Agent({self.agent_id}) Result: {result_json.get('message')}\nSummary: {result_json.get('summary', 'N/A')}"

            self.finished_task.emit(self.agent_id, result_json, next_task if next_task else {}, usage)
            
        except Exception as e:
            logger.error(f"WORKER FATAL [{self.agent_id}]: {traceback.format_exc()}")
            self.error_signal.emit(self.agent_id, f"워커 치명적 오류: {str(e)}")

    def read_memory(self):
        p = os.path.join(MEMORY_DIR, f"{self.agent_id}_memory.md")
        if not os.path.exists(p): return "이전 히스토리 없음."
        try:
            with open(p, 'r', encoding='utf-8') as f:
                return "".join(f.readlines()[-30:]) # 컨텍스트 최적화를 위해 최근 30줄만
        except: return "기억 읽기 오류."

    def save_memory(self, action, res):
        p = os.path.join(MEMORY_DIR, f"{self.agent_id}_memory.md")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(p, 'a', encoding='utf-8') as f:
                f.write(f"### [{ts}] {action}\n- Result: {res}\n\n")
        except: pass

# ==============================================================================
# [6] SRE 관제 모니터 및 Watchdog UI 위젯
# ==============================================================================
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

class ResourceGraph(QFrame):
    """엔터프라이즈 모니터링: CPU, RAM, GPU 사용률 실시간 그래프"""
    def __init__(self, parent=None):
        super().__init__(parent); self.setMinimumHeight(140)
        self.cpu_h, self.ram_h, self.gpu_h = [0]*50, [0]*50, [0]*50
    def update_data(self, c, r, g):
        self.cpu_h.pop(0); self.cpu_h.append(c)
        self.ram_h.pop(0); self.ram_h.append(r)
        self.gpu_h.pop(0); self.gpu_h.append(g); self.update()
    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#1e272e"))
        p.setPen(QPen(QColor("#3d4b53"), 1, Qt.PenStyle.DashLine)); p.drawLine(0, h//2, w, h//2)
        def draw_line(data, color):
            p.setPen(QPen(QColor(color), 2))
            for i in range(len(data)-1):
                p.drawLine(int((i/50)*w), int(h-(data[i]/100)*h), int(((i+1)/50)*w), int(h-(data[i+1]/100)*h))
        draw_line(self.cpu_h, "#e67e22"); draw_line(self.ram_h, "#3498db"); draw_line(self.gpu_h, "#2ecc71")

class AgentWidget(QFrame):
    """에이전트 카드: 상태, 토큰 사용량, 진행도 표시"""
    def __init__(self, a_id, emoji, name, rank, parent=None):
        super().__init__(parent); self.a_id, self.rank = a_id, rank
        self.setFixedSize(145, 195); self.home_pos = QPoint(0,0)
        self.setStyleSheet(f"background: {'#f39c12' if rank=='noble' else '#2c3e50'}; border-radius:15px; border:2px solid #222f3e;")
        l = QVBoxLayout(self)
        self.emo = QLabel(emoji); self.emo.setFont(QFont("Arial", 48)); self.emo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nm = QLabel(name); self.nm.setStyleSheet("font-weight:bold; font-size:14px; color:white;"); self.nm.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.st = QLabel("💤 Standby"); self.st.setStyleSheet("font-size:11px; color:#bdc3c7;"); self.st.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tk = QLabel("P:0 / C:0"); self.tk.setStyleSheet("font-family:Consolas; font-size:10px; color:#7f8c8d;"); self.tk.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pr = QProgressBar(); self.pr.setFixedHeight(12); self.pr.setRange(0, 0); self.pr.hide()
        l.addWidget(self.emo); l.addWidget(self.nm); l.addWidget(self.st); l.addWidget(self.tk); l.addWidget(self.pr)

    def update_usage(self, u):
        self.tk.setText(f"P:{u.get('prompt_tokens', 0)} / C:{u.get('completion_tokens', 0)}")

    def set_working(self, is_w, txt="🔥 처리 중"):
        if is_w: 
            self.st.setText(txt); self.pr.show()
            self.setStyleSheet("background: #c0392b; border-radius:15px; border:3px solid #e74c3c;")
        else: 
            self.st.setText("💤 Standby"); self.pr.hide()
            base_color = "#f39c12" if self.rank == "noble" else "#2c3e50"
            self.setStyleSheet(f"background: {base_color}; border-radius:15px; border: 2px solid #222f3e;")

# ==============================================================================
# [7] 메인 애플리케이션 코어: 통합 지휘 콘솔
# ==============================================================================
class CodeGodEnterprise(QMainWindow):
    def __init__(self):
        super().__init__(); self.agents, self.workers, self.anims = {}, {}, {}
        
        # 정밀 프롬프트 설계
        self.prompts = {
            "command": "당신은 총괄 지휘관입니다. 목표를 분석하여 에이전트별 순서와 세부 행동 지침이 담긴 JSON 계획(plan)을 수립하십시오.",
            "secretary": "당신은 정보 분석가입니다. 진행 상황을 3줄로 핵심 요약하여 보고하십시오.",
            "file": "당신은 인프라 전문가입니다. 설계에 맞춰 계층적 폴더와 기초 소스 파일을 생성하십시오.",
            "code": "당신은 시니어 개발자입니다. 주어진 설계와 이전 산출물을 바탕으로 완벽하게 돌아가는 파이썬 코드를 구현하십시오.",
            "doc": "당신은 기술 작가입니다. 완성된 코드를 분석하여 누구나 읽기 쉬운 README.md를 작성하십시오."
        }
        
        self.init_ui()
        self.setup_agents()
        self.setup_sre_police()
        self.setup_watchdog_bridge()
        logger.info("SYSTEM: AMEVA 통합 관제 콘솔 가동.")

    def init_ui(self):
        self.setWindowTitle("AMEVA Agent Orchestra v2.7 - Ultimate Enterprise Console")
        self.setGeometry(10, 10, 1800, 1050); self.setStyleSheet("background-color: #2f3640; color: white; font-family: 'Segoe UI';")
        c = QWidget(); self.setCentralWidget(c); ml = QHBoxLayout(c)
        
        # [좌측 영역] 대시보드 및 로그
        ll = QVBoxLayout(); self.office = QFrame(); self.office.setMinimumHeight(560); self.office.setStyleSheet("background:#353b48; border-radius:25px; border:1px solid #7f8fa6;")
        
        il = QHBoxLayout(); self.chat = QLineEdit(); self.chat.setPlaceholderText("오케스트라 가동 지시 (예: SQLite를 사용하는 연락처 관리 프로그램 짜줘)...")
        self.chat.setStyleSheet("padding:22px; background:#222f3e; border-radius:12px; font-size:16px; border:1px solid #718093;")
        self.chat.returnPressed.connect(self.process_command); rb = QPushButton("⚡ 지휘 개시"); rb.clicked.connect(self.process_command)
        rb.setStyleSheet("background:#0097e6; padding:22px; font-weight:bold; border-radius:12px; font-size:16px;")
        il.addWidget(self.chat, 7); il.addWidget(rb, 1)
        
        self.log_v = QTextEdit(); self.log_v.setReadOnly(True); self.log_v.setStyleSheet("background:#1e272e; color:#4cd137; font-family:Consolas; border-radius:10px;")
        ll.addWidget(QLabel("🏢 AGENT OPERATIONS BOARD")); ll.addWidget(self.office); ll.addLayout(il); ll.addWidget(QLabel("🖥️ SYSTEM TRACE LOG")); ll.addWidget(self.log_v)

        # [우측 영역] 모니터링 및 기억소장고
        rl = QVBoxLayout(); self.graph = ResourceGraph(); rl.addWidget(QLabel("📈 REAL-TIME INFRA RESOURCES")); rl.addWidget(self.graph)
        
        self.sre_trace = QTextEdit(); self.sre_trace.setReadOnly(True); self.sre_trace.setFixedHeight(180); self.sre_trace.setStyleSheet("background:#1e272e; color:#e1b12c; font-family:Consolas; border-radius:10px;")
        rl.addWidget(QLabel("🚨 WATCHDOG & SRE EVENTS")); rl.addWidget(self.sre_trace)
        
        self.m_list = QListWidget(); self.m_list.setFixedHeight(130); self.m_list.addItems(["command_memory.md", "file_memory.md", "code_memory.md", "doc_memory.md"])
        self.m_list.itemClicked.connect(self.view_m); self.m_list.setStyleSheet("background:#353b48; border-radius:8px;")
        
        self.m_view = QTextEdit(); self.m_view.setReadOnly(True); self.m_view.setStyleSheet("background:#2f3640; color:#dcdde1; font-family:Consolas; border-radius:8px; border:1px solid #7f8fa6;")
        rl.addWidget(QLabel("📂 PERSISTENT MEMORY ASSETS")); rl.addWidget(self.m_list); rl.addWidget(self.m_view)

        ml.addLayout(ll, 2); ml.addLayout(rl, 1)

    def setup_agents(self):
        roles = [("command", "🐶", 270, 75), ("secretary", "🎩", 720, 75), ("file", "🐹", 130, 350), ("code", "🦊", 480, 350), ("doc", "🐻", 830, 350)]
        for aid, emo, x, y in roles:
            a = AgentWidget(aid, emo, aid.upper(), "noble" if y < 200 else "worker", self.office)
            a.home_pos = QPoint(x, y); a.move(a.home_pos); self.agents[aid] = a

    def setup_sre_police(self):
        self.timer = QTimer(self); self.timer.timeout.connect(self.monitor); self.timer.start(2000)

    def setup_watchdog_bridge(self):
        self.emitter = WatchdogSignalEmitter(); self.emitter.file_modified.connect(self.log_msg)
        self.observer = Observer(); self.observer.schedule(WorkspaceWatcher(self.emitter), WORKSPACE_DIR, recursive=True); self.observer.start()

    def monitor(self):
        c, r = psutil.cpu_percent(), psutil.virtual_memory().percent
        g = LlamaInferenceCore.get_instance().get_gpu_load_safe()
        self.graph.update_data(c, r, g)
        
        # RAM OOM 방지 (93% 임계치)
        if r > 93.0:
            self.sre_trace.append("🚨 [CRITICAL] RAM 과부하! 안전 종료 시퀀스 가동...");
            for aid, w in list(self.workers.items()): self.graceful_stop_worker(aid, w)
            self.workers.clear()

        # 스레드 데드락 감시 (180초 무응답 시)
        curr = time.time()
        for aid, worker in list(self.workers.items()):
            if worker.isRunning() and (curr - worker.heartbeat > 180.0):
                self.sre_trace.append(f"🚨 [TIMEOUT] {aid} 응답 없음. 강제 사살.");
                self.graceful_stop_worker(aid, worker)
                self.agents[aid].set_working(False); del self.workers[aid]

    def graceful_stop_worker(self, aid, w):
        """Request interruption -> quit -> wait(2s) -> terminate (최후의 수단)"""
        w.requestInterruption(); w.quit()
        if not w.wait(2000):
            logger.warning(f"Worker {aid} did not stop gracefully. Force terminating.")
            w.terminate(); w.wait()

    def log_msg(self, msg, lvl="INFO"):
        tk = LlamaInferenceCore.get_instance().total_tokens_used
        self.log_v.append(f"[{datetime.now().strftime('%H:%M:%S')}] [{lvl}] (Σ: {tk}) {msg}")

    def process_command(self):
        req = self.chat_input.text().strip(); if not req: return
        self.chat_input.clear(); self.log_msg(f"COMMANDER: {req}")
        # 아키텍트에게 전체 계획 수립 미션 부여
        self.start_worker("command", {"instruction": f"Goal: {req}. Design tasks and plan for file, code, and doc agents."})

    def start_worker(self, aid, data):
        if aid in self.workers and self.workers[aid].isRunning(): return
        self.agents[aid].set_working(True)
        w = AgentWorker(aid, self.prompts[aid], data)
        w.finished_task.connect(self.on_worker_done); w.error_signal.connect(self.on_worker_fail)
        self.workers[aid] = w; w.start()

    @pyqtSlot(str, str)
    def on_worker_fail(self, aid, err):
        self.log_msg(f"[{aid}] FAILED: {err[:120]}", "ERROR"); self.agents[aid].set_working(False)

    @pyqtSlot(str, dict, dict, dict)
    def on_worker_done(self, aid, res, nt, usage):
        self.agents[aid].set_working(False); self.agents[aid].update_usage(usage)
        if res.get("status", 200) != 200: self.log_msg(f"[{aid}] ERROR: {res.get('message')}", "ERROR"); return
        self.log_msg(f"[{aid}] COMPLETED: {res.get('message', 'Mission Done.')}")
        
        # 비서(secretary) 보고는 알림창으로 표시
        if aid == "secretary":
            QMessageBox.information(self, "SECRETARY REPORT", res.get('message'))
            return

        if nt: self.trigger_handoff(aid, nt["target"], nt)

    def trigger_handoff(self, fid, tid, nt):
        fa, ta = self.agents[fid], self.agents[tid]
        anim = QPropertyAnimation(fa, b"pos", self); anim.setDuration(800)
        anim.setStartValue(fa.home_pos); anim.setEndValue(ta.home_pos); anim.setEasingCurve(QEasingCurve.Type.OutBounce)
        anim.finished.connect(lambda: (fa.move(fa.home_pos), self.start_worker(tid, nt)))
        self.anims[fid] = anim; anim.start()

    def view_m(self, item):
        p = os.path.join(MEMORY_DIR, item.text())
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f: self.m_view.setText(f.read())

    def closeEvent(self, event):
        """시스템 종료 시 스레드 및 관찰자 자원 완전 회수 (OS 클린업)"""
        self.observer.stop(); self.observer.join()
        for w in self.workers.values(): w.quit(); w.wait()
        event.accept()

if __name__ == '__main__':
    # 고해상도 DPI 스케일링 대응
    if hasattr(Qt, 'AA_EnableHighDpiScaling'): QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv); app.setStyle("Fusion"); ex = CodeGodEnterprise(); ex.show(); sys.exit(app.exec())