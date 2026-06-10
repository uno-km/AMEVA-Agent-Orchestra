// WebSocket Connection Reference
let socket = null;
const urlParams = new URLSearchParams(window.location.search);
const isAdmin = urlParams.get('admin') === 'true';

let wsUrl = (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host + '/ws' + (isAdmin ? '?admin=true' : '');
let reconnectInterval = 3000;

// SRE Resource Graph History data
let resourceHistory = [];

// Client-side Agent Timers
let agentTimers = {};
let agentElapsedSecs = {};

// Startup Hardware and Model Info
let currentRenderedModels = [];

// Accidental Reload Protection Keys (F5, Ctrl+R, Ctrl+Alt+Shift+R)
window.addEventListener('keydown', (e) => {
    const key = e.key.toLowerCase();
    
    // F5
    if (e.key === 'F5') {
        e.preventDefault();
        logTraceMessage("[보안] 새로고침(F5) 입력이 차단되었습니다.", "WARN");
        return;
    }
    
    // Ctrl + R
    if (e.ctrlKey && key === 'r') {
        e.preventDefault();
        logTraceMessage("[보안] 새로고침(Ctrl + R) 입력이 차단되었습니다.", "WARN");
        return;
    }
    
    // Ctrl + Alt + Shift + R
    if (e.ctrlKey && e.altKey && e.shiftKey && key === 'r') {
        e.preventDefault();
        logTraceMessage("[보안] 강제 새로고침(Ctrl+Alt+Shift+R) 입력이 안전 차단되었습니다.", "WARN");
        return;
    }
});

// Window BeforeUnload warning guard
window.addEventListener('beforeunload', (e) => {
    // Standard warning dialog
    e.preventDefault();
    e.returnValue = '에이전트 오케스트라가 작업 도중단될 수 있습니다. 정말로 퇴장하시겠습니까?';
    return e.returnValue;
});

// Setup WebSocket Connection
function connectWebSocket() {
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        logTraceMessage("시스템 관제 포트와 실시간 웹소켓 연결 성공.", "SUCCESS");
    };

    socket.onclose = () => {
        logTraceMessage("웹소켓 연결 종료. 3초 후 재연결 시도...", "WARN");
        setTimeout(connectWebSocket, reconnectInterval);
    };

    socket.onerror = (err) => {
        console.error("WebSocket Error: ", err);
    };

    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
    };
}

// Handle Incoming Server Events (Restoration Session & Real-Time Events)
function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'init':
            // 1. Session Restoration (새로고침 시 상태 복원)
            restoreSessionState(data);
            break;
            
        case 'trace_log':
            logTraceMessage(data.message, "INFO");
            updateTotalTokens(data.tokens);
            break;
            
        case 'console_log':
            logConsoleMessage(data.message);
            break;
            
        case 'sre_event':
            logSreMessage(data.message);
            break;
            
        case 'resource_stats':
            // Update resource variables and draw on canvas
            resourceHistory.push([data.cpu, data.ram, data.gpu]);
            if (resourceHistory.length > 50) {
                resourceHistory.shift();
            }
            drawResourceGraph();
            updateResourceText(data.cpu, data.ram, data.gpu);
            break;
            
        case 'worker_started':
            setAgentStatus(data.agent_id, "🔥 Working", true);
            startAgentTimer(data.agent_id);
            break;
            
        case 'task_assigned':
            agentTaskPayloads[data.agent_id] = data.task_data;
            if (currentOpenedLogAgentId === data.agent_id) {
                const payloadBox = document.getElementById('agent-modal-payload');
                if (payloadBox) payloadBox.innerText = JSON.stringify(data.task_data, null, 2);
            }
            setAgentTaskData(data.agent_id, data.task_data.instruction, data.task_data.passed_result);
            break;
            
        case 'llm_stream':
            if (currentOpenedLogAgentId === data.agent_id) {
                const logsBox = document.getElementById('agent-modal-logs');
                if (logsBox) {
                    const isAtBottom = logsBox.scrollHeight - logsBox.scrollTop <= logsBox.clientHeight + 15;
                    logsBox.innerText += data.delta;
                    if (isAtBottom) {
                        logsBox.scrollTop = logsBox.scrollHeight;
                    }
                }
            }
            break;
            
        case 'worker_finished':
            setAgentStatus(data.agent_id, "💤 Standby", false);
            stopAgentTimer(data.agent_id);
            updateAgentTokens(data.agent_id, data.usage);
            
            // Secretary report alert popup
            if (data.agent_id === 'secretary' && data.result.message) {
                alert(`🎩 SECRETARY REPORT:\n\n${data.result.message}`);
            }
            break;
            
        case 'worker_error':
            setAgentStatus(data.agent_id, "💤 Standby", false);
            stopAgentTimer(data.agent_id);
            break;
            
        case 'handoff_triggered':
            triggerHandoffAnimation(data.from_id, data.to_id);
            break;
            
        case 'model_loaded':
            logTraceMessage(`CORE: 모델 로드 완료 -> ${data.model_path}`, "SUCCESS");
            document.getElementById('model-modal').classList.remove('show');
            break;
            
        case 'model_load_failed':
            alert(`Boot Error: ${data.message}`);
            break;
            
        case 'download_progress':
            document.getElementById('download-progress-panel').style.display = 'block';
            document.getElementById('download-progress-inner').style.width = data.percent + '%';
            document.getElementById('download-percentage').innerText = data.percent + '%';
            break;
            
        case 'download_status':
            document.getElementById('download-progress-panel').style.display = 'block';
            document.getElementById('download-status-label').innerText = data.status;
            break;
            
        case 'download_finished':
            document.getElementById('download-progress-panel').style.display = 'none';
            if (data.success) {
                logTraceMessage("모델 다운로드 완료. 목록을 갱신합니다.", "SUCCESS");
                loadModelList();
            } else {
                alert(`Download Failed: ${data.path_or_err}`);
            }
            break;
            
        case 'concurrency_changed':
            document.getElementById('concurrency-select').value = data.value;
            break;
            
        case 'orchestrator_stopped':
            logTraceMessage("오케스트레이터의 모든 에이전트 스레드가 안전 중단되었습니다.", "WARN");
            resetAllAgentCards();
            break;
            
        default:
            break;
    }
}

// Session restoration on refresh/init
function restoreSessionState(data) {
    // Total tokens counter
    updateTotalTokens(data.total_tokens);
    
    // Concurrency value
    document.getElementById('concurrency-select').value = data.max_processors;
    
    // Log restoring
    const traceView = document.getElementById('trace-log-view');
    traceView.innerHTML = '';
    data.session_logs.forEach(msg => {
        const p = document.createElement('div');
        p.className = getLogClass(msg);
        p.innerText = msg;
        traceView.appendChild(p);
    });
    traceView.scrollTop = traceView.scrollHeight;
    
    // Watchdog SRE logs
    const sreView = document.getElementById('sre-trace-view');
    sreView.innerHTML = '';
    data.sre_logs.forEach(msg => {
        const p = document.createElement('div');
        p.innerText = msg;
        sreView.appendChild(p);
    });
    sreView.scrollTop = sreView.scrollHeight;

    // Resource Graph data
    resourceHistory = data.resource_history;
    drawResourceGraph();
    
    // Restore Agent Cards states
    for (const [aid, state] of Object.entries(data.agent_states)) {
        const card = document.getElementById(`agent-${aid}`);
        if (!card) continue;
        
        card.querySelector('.agent-status').innerText = state.status;
        card.querySelector('.agent-task').innerText = `Task: ${state.task ? state.task.slice(0, 64) : 'None'}`;
        card.querySelector('.agent-passed').innerText = `Received: ${state.passed ? state.passed.slice(0, 64) : 'None'}`;
        card.querySelector('.agent-runtime').innerText = state.elapsed;
        card.querySelector('.agent-tokens').innerText = state.tokens;
        
        if (state.status === "🔥 Working") {
            card.classList.add('working');
            // Parse seconds from "Elapsed: Xs" if present
            const match = state.elapsed.match(/(\d+)m\s+(\d+)s|(\d+)s/);
            let elapsed = 0;
            if (match) {
                if (match[3]) elapsed = parseInt(match[3]);
                else elapsed = parseInt(match[1]) * 60 + parseInt(match[2]);
            }
            agentElapsedSecs[aid] = elapsed;
            startAgentTimer(aid, true);
        } else {
            card.classList.remove('working');
        }
    }
    
    // Active model boot verification
    if (!data.model_loaded) {
        document.getElementById('model-modal').classList.add('show');
        loadModelList();
        loadHardwareSpecs();
    } else {
        document.getElementById('model-modal').classList.remove('show');
    }
    
    // If download is in progress, restore panel
    if (data.download_in_progress) {
        document.getElementById('download-progress-panel').style.display = 'block';
        document.getElementById('download-progress-inner').style.width = data.download_percent + '%';
        document.getElementById('download-percentage').innerText = data.download_percent + '%';
        document.getElementById('download-status-label').innerText = data.download_status;
    }
    
    // Refresh memory assets list
    loadMemoryList();
}

// Log formatting classes
function getLogClass(msg) {
    if (msg.includes("[SUCCESS]")) return "log-success";
    if (msg.includes("[ERROR]")) return "log-error";
    if (msg.includes("[WARN]")) return "log-warn";
    return "";
}

// Helper to write to local Trace Log
function logTraceMessage(msg, lvl = "INFO") {
    const view = document.getElementById('trace-log-view');
    const p = document.createElement('div');
    
    let lvlClass = "";
    if (lvl === "SUCCESS") lvlClass = "log-success";
    if (lvl === "ERROR") lvlClass = "log-error";
    if (lvl === "WARN") lvlClass = "log-warn";
    
    p.className = lvlClass;
    p.innerText = `[${new Date().toLocaleTimeString()}] [${lvl}] ${msg}`;
    view.appendChild(p);
    view.scrollTop = view.scrollHeight;
}

// Helper to write to CLI Console Log
function logConsoleMessage(msg) {
    const view = document.getElementById('console-log-view');
    if (!view) return;
    const p = document.createElement('div');
    p.innerText = msg;
    view.appendChild(p);
    view.scrollTop = view.scrollHeight;
}

// Switch Log Tabs
function switchLogTab(tabId) {
    document.querySelectorAll('.log-tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.terminal-view').forEach(view => {
        if(view.id === 'trace-log-view' || view.id === 'console-log-view') {
            view.classList.remove('active-tab');
        }
    });

    if (tabId === 'trace') {
        document.querySelectorAll('.log-tab-btn')[0].classList.add('active');
        document.getElementById('trace-log-view').classList.add('active-tab');
    } else {
        document.querySelectorAll('.log-tab-btn')[1].classList.add('active');
        document.getElementById('console-log-view').classList.add('active-tab');
    }
}

// Helper to write to SRE log
function logSreMessage(msg) {
    const view = document.getElementById('sre-trace-view');
    const p = document.createElement('div');
    p.innerText = msg;
    view.appendChild(p);
    view.scrollTop = view.scrollHeight;
}

// Total tokens counter update
function updateTotalTokens(tokens) {
    const header = document.querySelector('.logo-area h1');
    if (header) {
        header.innerHTML = `AMEVA AGENT OPERATIONS BOARD <span style="font-family:'Roboto Mono'; font-size:12px; color:#fbc531;">(Σ: ${tokens})</span>`;
    }
}

// Set Agent working status
function setAgentStatus(aid, status, isWorking) {
    const card = document.getElementById(`agent-${aid}`);
    if (!card) return;
    
    card.querySelector('.agent-status').innerText = status;
    if (isWorking) {
        card.classList.add('working');
    } else {
        card.classList.remove('working');
    }
}

// Set Agent task text
function setAgentTaskData(aid, task, passed) {
    const card = document.getElementById(`agent-${aid}`);
    if (!card) return;
    
    card.querySelector('.agent-task').innerText = `Task: ${task ? task.slice(0, 64) : 'None'}`;
    card.querySelector('.agent-passed').innerText = `Received: ${passed ? passed.slice(0, 64) : 'None'}`;
}

// Update Agent token metrics
function updateAgentTokens(aid, usage) {
    const card = document.getElementById(`agent-${aid}`);
    if (!card) return;
    card.querySelector('.agent-tokens').innerText = `P:${usage.prompt_tokens || 0} / C:${usage.completion_tokens || 0}`;
}

// Handoff vector drawing (SVG) & Bounce trigger
function triggerHandoffAnimation(fromId, toId) {
    const fromCard = document.getElementById(`agent-${fromId}`);
    const toCard = document.getElementById(`agent-${toId}`);
    if (!fromCard || !toCard) return;

    const board = document.getElementById('office-board');
    const boardRect = board.getBoundingClientRect();
    const fromRect = fromCard.getBoundingClientRect();
    const toRect = toCard.getBoundingClientRect();

    const x1 = (fromRect.left + fromRect.width / 2) - boardRect.left;
    const y1 = (fromRect.top + fromRect.height / 2) - boardRect.top;
    const x2 = (toRect.left + toRect.width / 2) - boardRect.left;
    const y2 = (toRect.top + toRect.height / 2) - boardRect.top;

    const svg = document.getElementById('handoff-overlay');
    
    // Draw neon laser handoff line
    svg.innerHTML = `
        <line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" 
              stroke="#0984e3" stroke-width="4" stroke-linecap="round" class="glowing-line" />
    `;

    // Bounce target to show impact
    toCard.classList.add('bounce-target');

    setTimeout(() => {
        toCard.classList.remove('bounce-target');
        svg.innerHTML = '';
    }, 2000);
}

// Agent run timer controllers
function startAgentTimer(aid, isResuming = false) {
    if (agentTimers[aid]) {
        clearInterval(agentTimers[aid]);
    }
    
    if (!isResuming) {
        agentElapsedSecs[aid] = 0;
    }
    
    agentTimers[aid] = setInterval(() => {
        agentElapsedSecs[aid]++;
        const mins = Math.floor(agentElapsedSecs[aid] / 60);
        const secs = agentElapsedSecs[aid] % 60;
        
        const card = document.getElementById(`agent-${aid}`);
        if (card) {
            card.querySelector('.agent-runtime').innerText = `Elapsed: ${mins}m ${secs}s`;
        }
    }, 1000);
}

function stopAgentTimer(aid) {
    if (agentTimers[aid]) {
        clearInterval(agentTimers[aid]);
        delete agentTimers[aid];
    }
}

function resetAllAgentCards() {
    for (const aid of ['command', 'secretary', 'file', 'code', 'tester', 'doc']) {
        setAgentStatus(aid, "💤 Standby", false);
        stopAgentTimer(aid);
    }
}

// Resource graph drawing on Canvas (CPU, RAM, GPU)
function drawResourceGraph() {
    const canvas = document.getElementById('resourceCanvas');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#1e272e';
    ctx.fillRect(0, 0, w, h);
    
    // Draw reference dashed center line
    ctx.strokeStyle = '#3d4b53';
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    ctx.moveTo(0, h / 2);
    ctx.lineTo(w, h / 2);
    ctx.stroke();
    ctx.setLineDash([]); // reset

    if (resourceHistory.length < 2) return;
    
    function drawLine(index, color) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        for (let i = 0; i < resourceHistory.length; i++) {
            const val = resourceHistory[i][index];
            const x = (i / 50) * w;
            const y = h - (val / 100) * h;
            
            if (i === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
        }
        ctx.stroke();
    }
    
    drawLine(0, '#e67e22'); // CPU (Orange)
    drawLine(1, '#3498db'); // RAM (Blue)
    drawLine(2, '#2ecc71'); // GPU (Green)
}

function updateResourceText(c, r, g) {
    document.getElementById('resource-status-text').innerText = `CPU: ${c}% | RAM: ${r}% | GPU: ${g}%`;
}

// REST Api queries
async function loadHardwareSpecs() {
    try {
        const res = await fetch('/api/models');
        const data = await res.json();
        
        // Find specs or ask server
        const specsText = document.getElementById('specs-text');
        // Retrieve recomended specs
        if (data.models && data.models.length > 0) {
            // Pick specs from profiler recommendation
            const rec = data.models[0];
            specsText.innerText = `Detected CPU Cores and RAM requirements. Ready for operations.`;
        }
    } catch (e) {
        console.error("Failed to load specs: ", e);
    }
}

async function loadModelList() {
    const list = document.getElementById('model-selection-list');
    list.innerHTML = '<div class="loading-spinner">목록 로딩 중...</div>';
    
    try {
        const res = await fetch('/api/models');
        const data = await res.json();
        list.innerHTML = '';
        currentRenderedModels = data.models || [];
        
        currentRenderedModels.forEach((m, idx) => {
            const div = document.createElement('div');
            div.className = 'model-item';
            
            const label = document.createElement('span');
            label.className = 'model-name';
            label.innerText = `${m.name} ${m.recommended ? '⭐ Rec.' : ''}`;
            if (m.recommended) {
                label.style.color = '#fbc531';
            }
            
            const btn = document.createElement('button');
            if (m.is_installed) {
                btn.className = 'btn-primary';
                btn.innerText = 'Load';
                btn.onclick = () => selectModel(m.id);
            } else {
                btn.className = 'btn-secondary';
                btn.innerText = 'Install';
                btn.onclick = () => installModel(m.id);
            }
            
            div.appendChild(label);
            div.appendChild(btn);
            list.appendChild(div);
        });
    } catch (e) {
        list.innerHTML = `<div class="loading-spinner" style="color:var(--accent-red)">Failed to load models: ${e}</div>`;
    }
}

async function selectModel(modelId) {
    logTraceMessage(`CORE: 모델 로딩 시도... -> ${modelId}`, "INFO");
    try {
        const res = await fetch('/api/select_model', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({model_id: modelId})
        });
        const data = await res.json();
        if (data.status === 'ok') {
            logTraceMessage("모델 스위칭 명령 전송됨. 백그라운드 적재 중...", "INFO");
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert(`Request failed: ${e}`);
    }
}

async function installModel(modelId) {
    try {
        const res = await fetch('/api/install_model', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({model_id: modelId})
        });
        const data = await res.json();
        if (data.status === 'ok') {
            logTraceMessage("모델 다운로드 지시 전송 완료.", "INFO");
        } else {
            alert(data.message);
        }
    } catch (e) {
        alert(`Request failed: ${e}`);
    }
}

async function loadMemoryList() {
    const list = document.getElementById('memory-list');
    list.innerHTML = '';
    
    try {
        const res = await fetch('/api/memory');
        const data = await res.json();
        if (data.files) {
            data.files.forEach(f => {
                const li = document.createElement('li');
                li.innerText = f;
                li.onclick = () => selectMemoryFile(li, f);
                list.appendChild(li);
            });
        }
    } catch (e) {
        console.error("Failed to load memory list: ", e);
    }
}

async function selectMemoryFile(liElement, filename) {
    // Highlight item
    const list = document.getElementById('memory-list');
    list.querySelectorAll('li').forEach(item => item.classList.remove('selected'));
    liElement.classList.add('selected');
    
    try {
        const res = await fetch(`/api/memory/${filename}`);
        const data = await res.json();
        if (data.content) {
            document.getElementById('memory-view-content').innerText = data.content;
        } else {
            document.getElementById('memory-view-content').innerText = `Error loading file: ${data.error}`;
        }
    } catch (e) {
        document.getElementById('memory-view-content').innerText = `Error loading file: ${e}`;
    }
}

// Agent details logs popup
let currentOpenedLogAgentId = null;
let agentTaskPayloads = {};

function openAgentLog(aid) {
    currentOpenedLogAgentId = aid;
    const modal = document.getElementById('agent-log-modal');
    modal.querySelector('#agent-modal-title').innerText = `${aid.toUpperCase()} AGENT LOGS`;
    modal.classList.add('show');
    
    // Show JSON Payload
    const payloadBox = document.getElementById('agent-modal-payload');
    if (agentTaskPayloads[aid]) {
        payloadBox.innerText = JSON.stringify(agentTaskPayloads[aid], null, 2);
    } else {
        payloadBox.innerText = "No active task payload.";
    }

    // Reset streaming area
    const logsBox = document.getElementById('agent-modal-logs');
    logsBox.innerText = "대기 중... (실시간 스트리밍은 작업이 시작되면 여기에 표시됩니다.)\n\n";

    // Read or ask memory file
    fetch(`/api/memory/${aid}_memory.md`)
        .then(res => res.json())
        .then(data => {
            logsBox.innerText += "--- [이전 수행 기록] ---\n" + (data.content || "이전 수행 기록이 아직 없습니다.");
            logsBox.scrollTop = logsBox.scrollHeight;
        })
        .catch(err => {
            logsBox.innerText += "\n이력을 불러오지 못했습니다.";
        });
}

function closeAgentLogModal() {
    document.getElementById('agent-log-modal').classList.remove('show');
    currentOpenedLogAgentId = null;
}

// UI Controls mapping
document.getElementById('btn-send-command').onclick = sendCommandRequest;
document.getElementById('chat-input').onkeydown = (e) => {
    if (e.key === 'Enter') sendCommandRequest();
};

function sendCommandRequest() {
    const input = document.getElementById('chat-input');
    const txt = input.value.trim();
    if (!txt || !socket || socket.readyState !== WebSocket.OPEN) return;
    
    socket.send(JSON.stringify({
        type: 'start_mission',
        request: txt
    }));
    
    input.value = '';
}

// Concurrency dropdown triggers socket change
document.getElementById('concurrency-select').onchange = (e) => {
    const val = parseInt(e.target.value);
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
            type: 'set_concurrency',
            value: val
        }));
    }
};

// Stop tasks button
document.getElementById('btn-stop-all').onclick = () => {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({type: 'stop_all'}));
    }
};

// Model switch modal buttons
document.getElementById('btn-show-model-settings').onclick = () => {
    document.getElementById('model-modal').classList.add('show');
    loadModelList();
    loadHardwareSpecs();
};

document.getElementById('btn-close-modal').onclick = () => {
    document.getElementById('model-modal').classList.remove('show');
};

// Start websocket loop
connectWebSocket();

// Enforce role-based controls (View-Only Mode)
if (!isAdmin) {
    const inputArea = document.getElementById('command-input-area');
    if (inputArea) inputArea.style.display = 'none';
    
    const stopBtn = document.getElementById('btn-stop-all');
    if (stopBtn) stopBtn.style.display = 'none';
    
    const settingsBtn = document.getElementById('btn-show-model-settings');
    if (settingsBtn) settingsBtn.style.display = 'none';
    
    const concurrencySel = document.getElementById('concurrency-select');
    if (concurrencySel) concurrencySel.disabled = true;
}
