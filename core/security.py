import os
import re
import logging
from .config import WORKSPACE_DIR, ALLOWED_EXTENSIONS

logger = logging.getLogger("AMEVA_Orchestra")

def enforce_sandbox(target_path):
    """
    Path Traversal 및 심볼릭 링크 공격을 물리적으로 차단하는 강화된 샌드박스.
    realpath를 사용하여 모든 우회 경로를 해제한 후 검증합니다.
    """
    if not target_path or not isinstance(target_path, str):
        raise PermissionError("유효하지 않은 경로 데이터가 입력되었습니다.")
    
    # 1. 경로 정규화 및 실제 물리 경로 추출
    abs_target = os.path.realpath(os.path.join(WORKSPACE_DIR, target_path))
    
    # 2. 루트 디렉토리 이탈 검사 (Strict Prefix Check)
    if not abs_target.startswith(WORKSPACE_DIR + os.sep):
        logger.critical(f"SANDBOX BREACH ATTEMPT: {target_path}")
        raise PermissionError(f"[보안] 지정된 작업 공간(Workspace) 외부로 나갈 수 없습니다.")
    
    # 3. 확장자 화이트리스트 검사
    if not abs_target.lower().endswith(ALLOWED_EXTENSIONS):
        raise PermissionError(f"[보안] 허용되지 않는 파일 형식입니다: {os.path.splitext(abs_target)[1]}")
        
    return abs_target

def scan_malicious_content(content, filename, agent_id):
    """
    생성된 코드 내 위험 명령어를 스캔합니다. 
    문서 작업(doc)과 코딩 작업(code)에 대해 차등화된 보안 정책을 적용합니다.
    """
    if filename.endswith(".md") or agent_id == "doc":
        # 문서는 텍스트 설명이므로 엄격한 키워드 차단 대신 경고 로깅만 수행
        return

    # 난독화 및 우회 패턴을 포함한 정밀 위험 키워드 셋
    danger_patterns = [
        (r"os\.(remove|rmdir|system|spawn|exe|popen|kill|chmod)", "OS 파괴 및 권한 조작 명령"),
        (r"shutil\.(rmtree|move|copy)", "파일 시스템 대량 조작"),
        (r"subprocess\.", "외부 프로세스 제어 권한 탈취"),
        (r"(socket|urllib|requests|http\.client)\.", "비인가 네트워크 연결"),
        (r"eval\(|exec\(", "동적 코드 실행 취약점"),
        (r"__import__", "모듈 은닉 로딩 시도"),
        (r"base64\.b64decode", "난독화 해제 의심 패턴"),
        (r"pathlib\.Path\..*?\.unlink", "파일 시스템 영구 삭제 명령")
    ]
    
    for pattern, desc in danger_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            logger.warning(f"MALICIOUS CODE BLOCKED: {desc} in {filename} by {agent_id}")
            raise ValueError(f"보안 위험 요소 감지({desc})로 인해 작성이 강제 중단되었습니다.")
