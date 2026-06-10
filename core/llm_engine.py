import threading
import time
import os
import psutil
from .sre import logger
from .parser import StrictParser

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
        self.inference_lock = threading.Lock()
        
        self.cached_gpu_load = 0
        self.last_gpu_check = 0
        self.llm = None
        self.current_model_path = None

    def load_model(self, model_path):
        """동적으로 선택된 모델 로드"""
        with self.inference_lock:
            try:
                from llama_cpp import Llama
                import GPUtil
                
                logger.info(f"CORE: 모델 스위칭 시작... -> {model_path}")
                opt_threads = max(1, psutil.cpu_count(logical=False))
                
                gpu_layers = 0
                try:
                    gpus = GPUtil.getGPUs()
                    if gpus:
                        gpu_layers = -1
                        logger.info(f"CORE: GPU 가속 활성화 -> {gpus[0].name}")
                except Exception: pass

                if not os.path.exists(model_path):
                    raise FileNotFoundError("지정된 모델이 시스템에 없습니다.")

                # 기존 모델 해제 방어 (메모리 릭 방지)
                if self.llm:
                    del self.llm
                    
                self.llm = Llama(
                    model_path=model_path, 
                    n_ctx=4096, 
                    n_threads=opt_threads,
                    n_gpu_layers=gpu_layers,
                    use_mmap=True,
                    verbose=False
                )
                self.is_loaded = True
                self.current_model_path = model_path
                logger.info(f"CORE: 새로운 LLM 엔진 적재 완료. (Threads: {opt_threads})")
                return True
                
            except Exception as e:
                self.is_loaded = False
                logger.critical(f"CORE: 엔진 적재 실패: {e}")
                return False

    def get_gpu_load_safe(self):
        now = time.time()
        if now - self.last_gpu_check > 5:
            try:
                import GPUtil
                gpus = GPUtil.getGPUs()
                self.cached_gpu_load = gpus[0].load * 100 if gpus else 0
                self.last_gpu_check = now
            except: self.cached_gpu_load = 0
        return self.cached_gpu_load

    def generate(self, system_p, user_p, schema):
        if not self.is_loaded or not self.llm:
            return {"status": 503, "message": "모델 엔진 미로드"}, {"prompt_tokens": 0, "completion_tokens": 0}

        with self.inference_lock:
            try:
                import json
                schema_str = json.dumps(schema, indent=2, ensure_ascii=False)
                prompt = f"<|im_start|>system\n{system_p}\nYou MUST output a valid JSON object matching this JSON Schema:\n{schema_str}\nJSON Only. No markdown formatting.<|im_end|>\n<|im_start|>user\n{user_p}<|im_end|>\n<|im_start|>assistant\n"
                
                response = self.llm(
                    prompt, 
                    max_tokens=2500, 
                    stop=["<|im_end|>"], 
                    temperature=0.1,
                    stream=True
                )
                
                from datetime import datetime
                import sys
                print(f"\n\n[{datetime.now().strftime('%H:%M:%S')}] 🤖 [LLM 생성 중...] (실시간 스트리밍)\n" + "-"*50, flush=True)
                
                text_output = ""
                for chunk in response:
                    delta = chunk['choices'][0]['text']
                    text_output += delta
                    sys.stdout.write(delta)
                    sys.stdout.flush()
                
                print("\n" + "-"*50 + f"\n[{datetime.now().strftime('%H:%M:%S')}] ✅ [생성 완료]\n", flush=True)
                text_output = text_output.strip()
                
                usage = {"prompt_tokens": len(prompt)//3, "completion_tokens": len(text_output)//3, "total_tokens": (len(prompt)+len(text_output))//3}
                
                with self.token_lock:
                    self.total_tokens_used += usage.get('total_tokens', 0)
                
                try:
                    import json
                    parsed_json = json.loads(text_output)
                except:
                    parsed_json = StrictParser.parse_response(text_output)
                    
                return parsed_json, usage
            except Exception as e:
                logger.error(f"GENERATE FATAL: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return {"status": 500, "message": str(e), "raw_text": locals().get('text_output', '')}, {"prompt_tokens": 0, "completion_tokens": 0}
