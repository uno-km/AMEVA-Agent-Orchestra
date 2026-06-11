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
        "filename": "Llama-3.2-1B-Instruct-Q4_K_M.gguf",
        "url": "https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF/resolve/main/Llama-3.2-1B-Instruct-Q4_K_M.gguf",
        "min_ram_gb": 2,
        "is_default": False
    },
    {
        "id": "qwen_2.5_0.5b",
        "name": "Qwen2.5 0.5B (Nano - 권장 RAM 2GB)",
        "filename": "qwen2.5-0.5b-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-q4_k_m.gguf",
        "min_ram_gb": 1,
        "is_default": True
    },
    {
        "id": "qwen_2.5_7b",
        "name": "Qwen2.5 7B Instruct (Heavy - 권장 RAM 16GB) ⭐ Rec.",
        "filename": "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "url": "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "min_ram_gb": 12,
        "is_default": False
    },
    {
        "id": "llama_3.1_8b",
        "name": "Llama 3.1 8B Instruct (Pro - 권장 RAM 16GB)",
        "filename": "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
        "url": "https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
        "min_ram_gb": 14,
        "is_default": False
    },
    {
        "id": "qwen_2.5_32b",
        "name": "Qwen2.5 32B Instruct (Titan - 권장 RAM 24GB)",
        "filename": "qwen2.5-32b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-32B-Instruct-GGUF/resolve/main/qwen2.5-32b-instruct-q4_k_m.gguf",
        "min_ram_gb": 22,
        "is_default": False
    },
    {
        "id": "gemma_2_27b",
        "name": "Gemma 2 27B Instruct (Google Elite - 권장 RAM 20GB)",
        "filename": "gemma-2-27b-it-Q4_K_M.gguf",
        "url": "https://huggingface.co/bartowski/gemma-2-27b-it-GGUF/resolve/main/gemma-2-27b-it-Q4_K_M.gguf",
        "min_ram_gb": 18,
        "is_default": False
    }
]

# 인프라 디렉토리 물리적 존재 보장
for path in [LOG_DIR, WORKSPACE_DIR, MEMORY_DIR]:
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
