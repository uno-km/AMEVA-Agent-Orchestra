import json
import re
import ast
import logging
from .security import scan_malicious_content

logger = logging.getLogger("AMEVA_Orchestra")
BT = "\x60\x60\x60" 

class StrictParser:
    """중괄호 스택 기반의 정밀 JSON 객체 적출 및 위생 처리기"""
    
    @staticmethod
    def extract_first_valid_json(text):
        """
        중괄호 스택 알고리즘을 사용하여 텍스트 내에서 첫 번째로 완결된 JSON 객체만 적출합니다.
        LLM의 앞뒤 수다나 부연 설명을 완벽하게 무시합니다.
        """
        start_idx = text.find('{')
        if start_idx == -1:
            raise ValueError("JSON 데이터의 시작점({)을 찾을 수 없습니다.")
            
        stack = 0
        for i in range(start_idx, len(text)):
            if text[i] == '{':
                stack += 1
            elif text[i] == '}':
                stack -= 1
                if stack == 0:
                    return text[start_idx:i+1]
        
        raise ValueError("JSON 중괄호 쌍이 일치하지 않아 파싱할 수 없습니다.")

    @staticmethod
    def parse_response(text_output):
        clean_text = text_output.strip()
        
        # 1. 다이렉트 json.loads
        try:
            return json.loads(clean_text)
        except: pass

        # 2. 마크다운 코드 블록 우회 파싱
        json_pattern = rf'{BT}json\s*(.*?)\s*{BT}'
        match = re.search(json_pattern, clean_text, re.DOTALL)
        if match:
            try: return json.loads(match.group(1))
            except: pass

        # 3. 스택 기반 최후 구출 로직 가동
        try:
            target_json_str = StrictParser.extract_first_valid_json(clean_text)
            return json.loads(target_json_str)
        except Exception as e:
            logger.error(f"HYBRID PARSE FAILED: {str(e)}")
            raise ValueError("유효한 JSON 구조를 식별할 수 없습니다.")

    @staticmethod
    def sanitize_code(content, filename, agent_id):
        # 마크다운 블록 적출
        code_pattern = rf'{BT}(?:python|js|javascript|html|css)?\s*(.*?)\s*{BT}'
        code_match = re.search(code_pattern, content, re.DOTALL)
        clean_code = code_match.group(1).strip() if code_match else content
        
        # README.md 파일이 아닐 때만 한국어 군더더기 서술어 제거
        if not filename.endswith(".md"):
            lines = clean_code.split('\n')
            clean_lines = [l for l in lines if not re.match(r'^(안녕하세요|반갑습니다|감사합니다|네, 알겠습니다|결과입니다|코드입니다)', l.strip())]
            clean_code = '\n'.join(clean_lines).strip()

        scan_malicious_content(clean_code, filename, agent_id)

        # 파이썬 문법 검증 (AST)
        if filename.endswith(".py") and clean_code:
            try:
                ast.parse(clean_code)
                logger.info(f"AST VERIFIED: {filename}")
            except SyntaxError as se:
                logger.error(f"SYNTAX ERROR in {filename}: {se}")
                raise SyntaxError(f"파이썬 문법 오류가 감지되었습니다: {se.msg}")
                
        return clean_code
