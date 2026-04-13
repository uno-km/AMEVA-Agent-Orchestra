import os

# 엔터프라이즈 인프라 경로 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "CodeGod_Logs")
WORKSPACE_DIR = os.path.join(BASE_DIR, "CodeGod_Workspace") 
MEMORY_DIR = os.path.join(BASE_DIR, "CodeGod_Memory")       

# 보안 화이트리스트 확장자
ALLOWED_EXTENSIONS = ('.py', '.md', '.txt', '.js', '.html', '.json', '.css', '.yaml', '.yml', '.json')

# 기본 모델 저장 위치 및 다운로드 가능 모델 설정
MODEL_DIR = os.path.join(BASE_DIR, "model") # 기본 디렉토리에 모델 저장 (GGUF)

AVAILABLE_MODELS = [
    {
        "id": "qwen_1.5_1.8b",
        "name": "Qwen1.5 1.8B Chat (Light - 권장 RAM 8GB)",
        "filename": "qwen1_5-1_8b-chat-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen1.5-1.8B-Chat-GGUF/resolve/main/qwen1_5-1_8b-chat-q4_k_m.gguf",
        "min_ram_gb": 4,
        "is_default": True
    },
    {
        "id": "llama3_8b",
        "name": "Llama 3 8B Instruct (Pro - 권장 RAM 16GB)",
        "filename": "llama3-8b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/lmstudio-community/Meta-Llama-3-8B-Instruct-GGUF/resolve/main/Meta-Llama-3-8B-Instruct-Q4_K_M.gguf",
        "min_ram_gb": 12,
        "is_default": False
    }
]

# 인프라 디렉토리 물리적 존재 보장
for path in [LOG_DIR, WORKSPACE_DIR, MEMORY_DIR]:
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
