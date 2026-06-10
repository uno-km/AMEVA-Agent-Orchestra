import os

# 엔터프라이즈 인프라 경로 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "CodeGod_Logs")
WORKSPACE_DIR = os.path.join(BASE_DIR, "CodeGod_Workspace") 
MEMORY_DIR = os.path.join(BASE_DIR, "CodeGod_Memory")       

# 보안 화이트리스트 확장자
ALLOWED_EXTENSIONS = ('.py', '.md', '.txt', '.js', '.html', '.json', '.css', '.yaml', '.yml', '.json')

# 기본 모델 저장 위치 및 다운로드 가능 모델 설정
MODEL_DIR = "C:/ameva/models/llm"

AVAILABLE_MODELS = [
    {
        "id": "qwen_2.5_3b",
        "name": "Qwen2.5 3B Instruct (Balance - 권장 RAM 12GB)",
        "filename": "qwen2.5-3b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf",
        "min_ram_gb": 8,
        "is_default": False
    },
    {
        "id": "qwen_2.5_1.5b",
        "name": "Qwen2.5 1.5B Instruct (Light - 권장 RAM 8GB)",
        "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "min_ram_gb": 4,
        "is_default": False
    },
    {
        "id": "llama3.2_1b",
        "name": "Llama 3.2 1B (Ultra Light - 권장 RAM 4GB)",
        "filename": "llama3.2-1b.gguf",
        "url": "https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF/resolve/main/Llama-3.2-1B-Instruct-Q4_K_M.gguf",
        "min_ram_gb": 2,
        "is_default": False
    },
    {
        "id": "qwen_2.5_0.5b",
        "name": "Qwen2.5 0.5B (Nano - 권장 RAM 2GB)",
        "filename": "qwen2.5-0.5b.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-q4_k_m.gguf",
        "min_ram_gb": 1,
        "is_default": True
    }
]

# 인프라 디렉토리 물리적 존재 보장
for path in [LOG_DIR, WORKSPACE_DIR, MEMORY_DIR]:
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
