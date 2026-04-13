import os
import time
import traceback
from datetime import datetime
from PyQt6.QtCore import QThread, pyqtSignal

from core.llm_engine import LlamaInferenceCore
from core.sre import logger
from core.config import MEMORY_DIR
from core.security import enforce_sandbox
from core.parser import StrictParser
from agents.schemas import ARCHITECT_SCHEMA, WORKER_SCHEMA

class AgentWorker(QThread):
    finished_task = pyqtSignal(str, dict, dict, dict) # agent_id, result_json, next_task, usage
    error_signal = pyqtSignal(str, str)
    
    def __init__(self, agent_id, role_prompt, task_data):
        super().__init__()
        self.agent_id = agent_id
        self.role_prompt = role_prompt
        self.task_data = task_data
        self.heartbeat = time.time()
        self.llm_core = LlamaInferenceCore.get_instance()

    def run(self):
        try:
            if self.isInterruptionRequested(): return
            self.heartbeat = time.time()
            
            past_mem = self.read_memory()
            instruction = self.task_data.get("instruction", "주어진 목표를 완수하십시오.")
            passed_result = self.task_data.get("passed_result", "이전 에이전트의 산출물 없음.")
            
            full_prompt = f"### [PAST LOGS]\n{past_mem}\n\n### [INPUT DATA]\n{passed_result}\n\n### [MISSION]\n{instruction}"
            
            schema = ARCHITECT_SCHEMA if self.agent_id == "command" else WORKER_SCHEMA
            result_json, usage = self.llm_core.generate(self.role_prompt, full_prompt, schema)
            
            if self.isInterruptionRequested(): return

            # 파일 생성형 에이전트(file, code, doc)만 물리 파일 작업 수행
            if self.agent_id not in ["command", "secretary"]:
                if result_json.get("status") == 200 and "file_name" in result_json:
                    if "content" in result_json and isinstance(result_json["content"], str):
                        safe_path = enforce_sandbox(result_json["file_name"])
                        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
                        
                        final_content = StrictParser.sanitize_code(result_json["content"], result_json["file_name"], self.agent_id)
                        
                        with open(safe_path, 'w', encoding='utf-8') as f:
                            f.write(final_content)
                        
                        result_json["message"] = f"성공: {result_json['file_name']} 파일 작성 완료"
                        self.save_memory(instruction, result_json["message"])

            # 릴레이 로직 파싱 (Orchestrator가 사용할 데이터 전송)
            next_plan = self.task_data.get("plan", [])
            
            if self.agent_id == "command" and "plan" in result_json:
                next_plan = result_json["plan"]
                result_json["message"] = result_json.get("summary", "전체 파이프라인 설계 완료.")

            next_task = None
            if next_plan:
                next_task = next_plan.pop(0)
                next_task["plan"] = next_plan
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
                return "".join(f.readlines()[-30:])
        except: return "기억 읽기 오류."

    def save_memory(self, action, res):
        p = os.path.join(MEMORY_DIR, f"{self.agent_id}_memory.md")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(p, 'a', encoding='utf-8') as f:
                f.write(f"### [{ts}] {action}\n- Result: {res}\n\n")
        except: pass
