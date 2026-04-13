ARCHITECT_SCHEMA = {
    "type": "object",
    "properties": {
        "plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "instruction": {"type": "string"}
                },
                "required": ["target", "instruction"]
            }
        },
        "summary": {"type": "string"}
    },
    "required": ["plan", "summary"]
}

WORKER_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "integer"},
        "file_name": {"type": "string"},
        "content": {"type": "string"},
        "message": {"type": "string"}
    },
    "required": ["status", "file_name", "content"]
}

PROMPTS = {
    "command": "당신은 총괄 지휘관입니다. 목표를 분석하여 에이전트별 순서와 세부 행동 지침이 담긴 JSON 계획(plan)을 수립하십시오.",
    "secretary": "당신은 정보 분석가입니다. 진행 상황을 3줄로 핵심 요약하여 보고하십시오.",
    "file": "당신은 인프라 전문가입니다. 설계에 맞춰 계층적 폴더와 기초 소스 파일을 생성하십시오.",
    "code": "당신은 시니어 개발자입니다. 주어진 설계와 이전 산출물을 바탕으로 완벽하게 돌아가는 코드를 구현하십시오.",
    "doc": "당신은 기술 작가입니다. 완성된 코드를 분석하여 누구나 읽기 쉬운 문서를 작성하십시오."
}
