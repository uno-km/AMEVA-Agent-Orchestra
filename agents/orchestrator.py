from PyQt6.QtCore import QObject, pyqtSignal
from agents.worker import AgentWorker
from agents.schemas import PROMPTS
from core.sre import logger

class Orchestrator(QObject):
    worker_started = pyqtSignal(str) # agent_id
    worker_finished = pyqtSignal(str, dict, dict) # agent_id, result_json, usage
    worker_error = pyqtSignal(str, str) # agent_id, error
    handoff_triggered = pyqtSignal(str, str, dict) # from_id, to_id, next_task

    def __init__(self):
        super().__init__()
        self.workers = {}
        self.max_concurrent_processors = 1
        self.task_queue = [] # For concurrent execution holding

    def set_max_processors(self, max_proc):
        self.max_concurrent_processors = max_proc

    def start_mission(self, user_request):
        """총괄 지휘관(command) 에이전트를 통해 초기 계획(plan) 수립 시작"""
        initial_task = {
            "instruction": f"Goal: {user_request}. Design tasks and plan for file, code, and doc agents. You must respect strictly sequential assignment (file -> code -> doc)."
        }
        self.dispatch_worker("command", initial_task)

    def dispatch_worker(self, agent_id, task_data):
        # max concurrent process 검사
        if len(self.workers) >= self.max_concurrent_processors:
            self.task_queue.append((agent_id, task_data))
            return

        if agent_id in self.workers and self.workers[agent_id].isRunning():
            logger.warning(f"Orchestrator: Agent {agent_id} is already running.")
            return

        w = AgentWorker(agent_id, PROMPTS[agent_id], task_data)
        w.finished_task.connect(self.on_worker_done)
        w.error_signal.connect(self.on_worker_fail)
        
        self.workers[agent_id] = w
        self.worker_started.emit(agent_id)
        w.start()

    def on_worker_done(self, agent_id, result_json, next_task, usage):
        if agent_id in self.workers:
            del self.workers[agent_id]

        self.worker_finished.emit(agent_id, result_json, usage)

        # 다음 태스크가 있다면 시그널 발송 -> UI 측에서 픽업 후 애니메이션 -> dispatch
        if next_task and "target" in next_task:
            target_id = next_task["target"]
            self.handoff_triggered.emit(agent_id, target_id, next_task)

        # 큐에 남은 작업이 있고 동시성 레벨이 허락하면 실행
        self._process_queue()

    def on_worker_fail(self, agent_id, err_msg):
        if agent_id in self.workers:
            del self.workers[agent_id]
        self.worker_error.emit(agent_id, err_msg)
        self._process_queue()

    def _process_queue(self):
        while len(self.workers) < self.max_concurrent_processors and self.task_queue:
            aid, tdata = self.task_queue.pop(0)
            self.dispatch_worker(aid, tdata)

    def shutdown_all(self):
        for aid, w in list(self.workers.items()):
            w.requestInterruption()
            w.quit()
            w.wait(2000)
            if w.isRunning():
                w.terminate()
        self.workers.clear()
