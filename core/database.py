import sqlite3
import json
import uuid
import os
from datetime import datetime

DB_PATH = "ameva_orchestra.db"

def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def setup_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. workflows
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS workflows (
            workflow_id TEXT PRIMARY KEY,
            user_command TEXT,
            created_at TEXT
        )
    ''')
    
    # 2. tasks
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            workflow_id TEXT,
            task_seq_id INTEGER,
            agent_id TEXT,
            instruction TEXT,
            created_at TEXT,
            PRIMARY KEY (workflow_id, task_seq_id),
            FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id)
        )
    ''')
    
    # 3. task_dtl
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS task_dtl (
            dtl_id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id TEXT,
            task_seq_id INTEGER,
            agent_id TEXT,
            action_type TEXT,
            payload_json TEXT,
            result_content TEXT,
            created_at TEXT,
            FOREIGN KEY (workflow_id, task_seq_id) REFERENCES tasks(workflow_id, task_seq_id)
        )
    ''')
    
    # 4. exceptions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS exceptions (
            exc_id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id TEXT,
            task_seq_id INTEGER,
            agent_id TEXT,
            error_message TEXT,
            traceback TEXT,
            created_at TEXT
        )
    ''')
    
    # 5. system_logs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_type TEXT,
            message TEXT,
            created_at TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

# CRUD Utilities
class DatabaseManager:
    @staticmethod
    def create_workflow(user_command: str) -> str:
        workflow_id = str(uuid.uuid4())
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO workflows (workflow_id, user_command, created_at) VALUES (?, ?, ?)", 
                       (workflow_id, user_command, created_at))
        conn.commit()
        conn.close()
        return workflow_id

    @staticmethod
    def get_next_task_seq(workflow_id: str) -> int:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(task_seq_id) FROM tasks WHERE workflow_id = ?", (workflow_id,))
        row = cursor.fetchone()
        conn.close()
        max_seq = row[0]
        if max_seq is None:
            return 1000001
        return max_seq + 1

    @staticmethod
    def create_task(workflow_id: str, agent_id: str, instruction: str) -> int:
        task_seq_id = DatabaseManager.get_next_task_seq(workflow_id)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO tasks (workflow_id, task_seq_id, agent_id, instruction, created_at) VALUES (?, ?, ?, ?, ?)",
                       (workflow_id, task_seq_id, agent_id, instruction, created_at))
        conn.commit()
        conn.close()
        return task_seq_id

    @staticmethod
    def log_task_dtl(workflow_id: str, task_seq_id: int, agent_id: str, action_type: str, payload_json: dict, result_content: str):
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload_str = json.dumps(payload_json, ensure_ascii=False) if payload_json else ""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO task_dtl (workflow_id, task_seq_id, agent_id, action_type, payload_json, result_content, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (workflow_id, task_seq_id, agent_id, action_type, payload_str, result_content, created_at))
        conn.commit()
        conn.close()

    @staticmethod
    def log_exception(workflow_id: str, task_seq_id: int, agent_id: str, error_message: str, tb: str):
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO exceptions (workflow_id, task_seq_id, agent_id, error_message, traceback, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                       (workflow_id, task_seq_id, agent_id, error_message, tb, created_at))
        conn.commit()
        conn.close()

    @staticmethod
    def log_system(log_type: str, message: str):
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO system_logs (log_type, message, created_at) VALUES (?, ?, ?)",
                       (log_type, message, created_at))
        conn.commit()
        conn.close()

    @staticmethod
    def get_workflow_context(workflow_id: str) -> str:
        # Fetches past task details for context
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.agent_id, t.instruction, d.payload_json, d.created_at
            FROM tasks t
            LEFT JOIN task_dtl d ON t.workflow_id = d.workflow_id AND t.task_seq_id = d.task_seq_id
            WHERE t.workflow_id = ? AND d.payload_json IS NOT NULL
            ORDER BY t.task_seq_id ASC
        ''', (workflow_id,))
        rows = cursor.fetchall()
        conn.close()
        
        context = ""
        for row in rows[-15:]: # Last 15 actions to keep context window safe
            agent, instr, payload_str, ts = row
            
            try:
                payload = json.loads(payload_str)
            except:
                payload = {}
                
            context += f"### [{ts}] Agent: {agent.upper()}\n"
            context += f"**Instruction Received:** {instr}\n"
            
            if agent == "pm":
                thought = payload.get("thought", "")
                plan = payload.get("overall_plan", "")
                action = payload.get("next_action", {})
                target = action.get("target", "None")
                next_instr = action.get("instruction", "None")
                
                context += f"**PM Thought:** {thought}\n"
                context += f"**Overall Plan:** {plan}\n"
                context += f"**Decision (Next Action):** Delegated to '{target}' with instruction: '{next_instr}'\n\n"
            else:
                msg = payload.get("message", "")
                fname = payload.get("file_name", "")
                content = payload.get("content", "")
                
                if fname:
                    context += f"**Action Result:** Created/Modified file '{fname}'\n"
                    # To prevent context blowing up, only show a snippet if content is huge
                    if len(content) > 500:
                        content = content[:500] + "... (truncated)"
                    context += f"**File Content Snippet:**\n```\n{content}\n```\n\n"
                else:
                    context += f"**Action Result:** {msg}\n\n"
                    
        return context if context else "이전 히스토리 없음."

    @staticmethod
    def get_agent_history(agent_id: str) -> str:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT w.created_at, t.instruction, d.result_content
            FROM tasks t
            JOIN task_dtl d ON t.workflow_id = d.workflow_id AND t.task_seq_id = d.task_seq_id
            JOIN workflows w ON t.workflow_id = w.workflow_id
            WHERE t.agent_id = ?
            ORDER BY d.created_at DESC LIMIT 20
        ''', (agent_id,))
        rows = cursor.fetchall()
        conn.close()
        
        context = ""
        for row in reversed(rows):
            ts, instr, res = row
            context += f"### [{ts}] Workflow Task\nInstruction: {instr}\nResult: {res}\n\n"
        return context if context else "저장된 태스크 이력이 없습니다."
