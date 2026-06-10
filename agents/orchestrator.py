from agents.worker import AgentWorker
from agents.schemas import PROMPTS
from core.sre import logger

class Orchestrator:
    VALID_TARGETS = {"command", "secretary", "file", "code", "doc", "tester"}
    MAX_HANDOFFS = 12

    def __init__(self):
        self.workers = {}
        self.max_concurrent_processors = 1
        self.task_queue = [] # For concurrent execution holding
        self.event_callbacks = [] # list of callbacks: callback(event_type, *args)

    def register_callback(self, callback):
        self.event_callbacks.append(callback)

    def unregister_callback(self, callback):
        if callback in self.event_callbacks:
            self.event_callbacks.remove(callback)

    def emit_event(self, event_type, *args):
        for callback in self.event_callbacks:
            try:
                callback(event_type, *args)
            except Exception as e:
                logger.error(f"Callback error in Orchestrator event: {e}")

    def set_max_processors(self, max_proc):
        self.max_concurrent_processors = max_proc

    def _validate_task(self, agent_id, task_data):
        hop_count = task_data.get("hop_count", 0)
        if hop_count > self.MAX_HANDOFFS:
            return False, f"Maximum handoff limit exceeded ({hop_count}/{self.MAX_HANDOFFS})."

        target = task_data.get("target", agent_id)
        if target not in self.VALID_TARGETS:
            return False, f"Invalid target '{target}'. Allowed targets: {', '.join(sorted(self.VALID_TARGETS))}."

        visited = list(task_data.get("visited_targets", []))
        if visited.count(target) >= 5:
            return False, f"Loop detected: target '{target}' has already appeared in visited path {visited}."

        if agent_id != "command" and not task_data.get("instruction"):
            return False, "Invalid task: missing instruction for non-command agent."

        return True, ""

    def start_mission(self, user_request, workflow_id=None):
        """총괄 지휘관(command) 에이전트를 통해 초기 계획(plan) 수립 시작"""
        if not workflow_id:
            from core.database import DatabaseManager
            workflow_id = DatabaseManager.create_workflow(user_request)
            
        initial_task = {
            "workflow_id": workflow_id,
            "original_goal": user_request,
            "instruction": (
                f"Goal: {user_request}. Analyze the objective and design an optimal multi-agent workflow. "
                "You are not restricted to any fixed sequence. You may choose to find existing files, "
                "modify code, summarize documents, or create new assets as needed. "
                "Assign tasks to file, code, or doc agents in the most logical order to achieve the goal efficiently."
            ),
            "hop_count": 0,
            "visited_targets": []
        }
        self.dispatch_worker("command", initial_task)

    def dispatch_worker(self, agent_id, task_data):
        if "hop_count" not in task_data:
            task_data["hop_count"] = 0
        if "visited_targets" not in task_data:
            task_data["visited_targets"] = []

        valid, err = self._validate_task(agent_id, task_data)
        if not valid:
            logger.error(f"Orchestrator: Task rejected for {agent_id}: {err}")
            self.emit_event("worker_error", agent_id, f"Task rejected: {err}")
            return

        self.emit_event("task_assigned", agent_id, dict(task_data))

        # max concurrent process 검사
        if len(self.workers) >= self.max_concurrent_processors:
            self.task_queue.append((agent_id, task_data))
            return

        if agent_id in self.workers and self.workers[agent_id].is_alive():
            logger.warning(f"Orchestrator: Agent {agent_id} is already running.")
            return

        w = AgentWorker(
            agent_id=agent_id,
            role_prompt=PROMPTS[agent_id],
            task_data=task_data,
            on_done=self.on_worker_done,
            on_fail=self.on_worker_fail,
            on_stream=self._handle_worker_stream
        )
        self.workers[agent_id] = w
        self.emit_event("worker_started", agent_id)
        w.start()

    def _handle_worker_stream(self, agent_id, delta):
        self.emit_event("llm_stream", agent_id, delta)

    def on_worker_done(self, agent_id, result_json, next_task, usage):
        if agent_id in self.workers:
            del self.workers[agent_id]

        self.emit_event("worker_finished", agent_id, result_json, usage)

        # 다음 태스크가 있다면 시그널 발송 -> 웹 UI 브로드캐스트
        if next_task and "target" in next_task:
            target_id = next_task["target"]
            self.emit_event("handoff_triggered", agent_id, target_id, next_task)
            self.dispatch_worker(target_id, next_task)

        # 큐에 남은 작업이 있고 동시성 레벨이 허락하면 실행
        self._process_queue()

    def on_worker_fail(self, agent_id, err_msg):
        if agent_id in self.workers:
            del self.workers[agent_id]
        self.emit_event("worker_error", agent_id, err_msg)
        self._process_queue()

    def _process_queue(self):
        while len(self.workers) < self.max_concurrent_processors and self.task_queue:
            aid, tdata = self.task_queue.pop(0)
            self.dispatch_worker(aid, tdata)

    def shutdown_all(self):
        for aid, w in list(self.workers.items()):
            w.requestInterruption()
            w.join(2.0)
        self.workers.clear()
