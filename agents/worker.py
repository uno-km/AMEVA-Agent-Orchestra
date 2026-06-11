import os
import time
import traceback
import threading
from datetime import datetime

from core.llm_engine import LlamaInferenceCore
from core.sre import logger
from core.config import MEMORY_DIR
from core.security import enforce_sandbox
from core.parser import StrictParser
from agents.schemas import ARCHITECT_SCHEMA, WORKER_SCHEMA
from core.database import DatabaseManager

class AgentWorker(threading.Thread):
    def __init__(self, agent_id, role_prompt, task_data, on_done=None, on_fail=None, on_stream=None):
        super().__init__()
        self.agent_id = agent_id
        self.role_prompt = role_prompt
        self.task_data = task_data
        self.on_done = on_done
        self.on_fail = on_fail
        self.on_stream = on_stream
        self.heartbeat = time.time()
        self.llm_core = LlamaInferenceCore.get_instance()
        self._stop_event = threading.Event()

    def requestInterruption(self):
        self._stop_event.set()

    def isInterruptionRequested(self):
        return self._stop_event.is_set()

    def run(self):
        try:
            if self.isInterruptionRequested(): return
            self.heartbeat = time.time()
            
            workflow_id = self.task_data.get("workflow_id")
            original_goal = self.task_data.get("original_goal", "목표가 지정되지 않았습니다.")
            instruction = self.task_data.get("instruction", "주어진 목표를 완수하십시오.")
            
            if workflow_id:
                task_seq_id = DatabaseManager.create_task(workflow_id, self.agent_id, instruction)
                past_mem = DatabaseManager.get_workflow_context(workflow_id)
            else:
                task_seq_id = 0
                past_mem = "이전 히스토리 없음."
            
            json_warning = ""
            if self.agent_id in ["architect", "dev"]:
                json_warning = "\n\n[CRITICAL WARNING] When outputting Python code inside JSON, ensure all double quotes and newlines are properly escaped so it does not cause 'unterminated string literal' errors. Use standard JSON formatting."

            full_prompt = f"### [PAST LOGS & CONTEXT]\n{past_mem}\n\n### [CURRENT MISSION]\n{instruction}{json_warning}"
            
            schema = ARCHITECT_SCHEMA if self.agent_id == "pm" else WORKER_SCHEMA
            
            def stream_cb(delta):
                if self.on_stream:
                    self.on_stream(self.agent_id, delta)

            result_json, usage = self.llm_core.generate(self.role_prompt, full_prompt, schema, stream_callback=stream_cb)
            
            if self.isInterruptionRequested(): return

            if result_json.get("status") == 500:
                logger.warning(f"Agent {self.agent_id} generated invalid response. Injecting fallback.")
                if self.agent_id == "pm":
                    result_json = {
                        "status": 200,
                        "overall_plan": "파싱 오류 발생. 기본 파일 생성/조회 단계부터 재추론을 시도합니다.",
                        "thought": "JSON 파싱 오류가 발생하여 기본 폴백 모드로 복구합니다.",
                        "summary": "JSON 파싱 실패로 인한 폴백 전환",
                        "next_action": {"target": "architect", "instruction": instruction}
                    }
                else:
                    import re
                    raw = result_json.get("raw_text", "")
                    
                    fname_match = re.search(r'"file_name"\s*:\s*"([^"]+)"', raw)
                    fname = fname_match.group(1) if fname_match else "generated_script.py"
                    
                    code_match = re.search(r'```(?:python)?\s*(.*?)\s*```', raw, re.DOTALL)
                    extracted_code = code_match.group(1).strip() if code_match else raw
                    
                    if not extracted_code.strip():
                        extracted_code = "LLM failed to generate valid output."
                    
                    result_json = {
                        "status": 200,
                        "message": "Extracted raw code due to JSON parsing failure.",
                        "file_name": fname,
                        "content": extracted_code
                    }

            if self.agent_id == "pm":
                try:
                    self._validate_pm_plan(result_json)
                except ValueError as ve:
                    logger.warning(f"PM validation failed: {ve}. Injecting fallback plan.")
                    result_json = {
                        "status": 200,
                        "thought": "스키마 유효성 검증 실패로 인해 기본 폴백 모드로 전환합니다.",
                        "summary": "유효하지 않은 계획 스키마로 인한 폴백 전환",
                        "overall_plan": result_json.get("overall_plan", "Fallback Plan"),
                        "next_action": {
                            "target": "architect",
                            "instruction": instruction
                        }
                    }
            elif self.agent_id != "pm" and "plan" in result_json:
                logger.warning(f"{self.agent_id.upper()} returned plan data unexpectedly. Removing plan field.")
                result_json.pop("plan")
                result_json["message"] = (result_json.get("message", "") + " [WARNING] Non-pm agents must not generate new plans.").strip()

            # 파일 생성형 에이전트(architect, dev, doc, tester)만 물리 파일 작업 수행
            if self.agent_id not in ["pm", "secretary"]:
                if result_json.get("status") == 200 and "file_name" in result_json:
                    if "content" in result_json and isinstance(result_json["content"], str):
                        safe_path = enforce_sandbox(result_json["file_name"])
                        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
                        
                        final_content = StrictParser.sanitize_code(result_json["content"], result_json["file_name"], self.agent_id)
                        
                        with open(safe_path, 'w', encoding='utf-8') as f:
                            f.write(final_content)
                        
                        result_json["message"] = f"성공: {result_json['file_name']} 파일 작성 완료"

            # 릴레이 로직 파싱
            next_plan = self.task_data.get("plan", [])
            next_task = None
            
            # tester 백그라운드 테스트 수행 로직
            if self.agent_id == "tester" and result_json.get("status") == 200 and "file_name" in result_json:
                import subprocess
                try:
                    safe_path = enforce_sandbox(result_json["file_name"])
                    proc = subprocess.run(["python", safe_path], capture_output=True, text=True, timeout=10)
                    if proc.returncode != 0:
                        logger.error(f"TESTER FAILED: {proc.stderr}")
                        result_json["message"] = f"[TEST FAILED] {proc.stderr}"
                    else:
                        result_json["message"] = f"테스트 하네스 성공: {proc.stdout.strip()}"
                except subprocess.TimeoutExpired:
                    result_json["message"] = "[TEST FAILED] Timeout Exceeded (10s)."

            if self.agent_id == "pm":
                next_action = result_json.get("next_action", {})
                target = next_action.get("target", "secretary")
                instruction = next_action.get("instruction", "최종 보고를 수행하십시오.")
                
                result_json["message"] = f"재귀 추론 완료 -> 다음 행동: {target.upper()} ({result_json.get('summary', 'N/A')})"
                
                next_task = {
                    "target": target,
                    "instruction": instruction,
                    "plan": []
                }
                
                # target이 비서가 아닌 경우, 에이전트 수행 종료 후 다시 pm 에이전트로 복귀하도록 plan에 강제 예약 주입
                if target != "secretary":
                    next_task["plan"] = [{
                        "target": "pm",
                        "instruction": f"Goal: {original_goal}. 이전 에이전트({target})의 산출물과 피드백을 분석하여 다음 재귀 추론 단계를 결정하십시오."
                    }]
            else:
                if next_plan:
                    next_task = next_plan.pop(0)
                    next_task["plan"] = next_plan

            if next_task:
                next_task["hop_count"] = self.task_data.get("hop_count", 0) + 1
                next_task["visited_targets"] = list(self.task_data.get("visited_targets", [])) + [self.agent_id]
                next_task["workflow_id"] = workflow_id
                next_task["original_goal"] = original_goal

            if workflow_id:
                DatabaseManager.log_task_dtl(workflow_id, task_seq_id, self.agent_id, "execution", result_json, result_json.get("message", "완료"))

            if self.on_done:
                self.on_done(self.agent_id, result_json, next_task if next_task else {}, usage)
            
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"WORKER FATAL [{self.agent_id}]: {tb}")
            workflow_id = getattr(self, 'task_data', {}).get("workflow_id", "")
            if workflow_id:
                # We might not have task_seq_id if it failed very early
                seq_id = locals().get('task_seq_id', 0)
                DatabaseManager.log_exception(workflow_id, seq_id, self.agent_id, str(e), tb)
                
            if self.on_fail:
                self.on_fail(self.agent_id, f"워커 치명적 오류: {str(e)}")

    def _validate_pm_plan(self, result_json):
        if "next_action" not in result_json or not isinstance(result_json["next_action"], dict):
            raise ValueError("PM agent returned invalid or missing next_action structure.")

        action = result_json["next_action"]
        target = action.get("target")
        instruction = action.get("instruction")

        valid_targets = {"architect", "dev", "doc", "tester", "secretary"}
        if target not in valid_targets:
            raise ValueError(f"Invalid next_action target '{target}'. Allowed: {valid_targets}")

        if not instruction or not isinstance(instruction, str):
            raise ValueError("next_action instruction must be a non-empty string.")
