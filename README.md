# AMEVA Agent Orchestra

**Enterprise-Grade Local Multi-Agent Orchestration Framework**

AMEVA Agent Orchestra는 외부 API(OpenAI 등) 의존 없이 **100% 로컬 하드웨어 리소스(GPU/CPU)**만을 활용하여 구동되는 자율 주행형 계층적 멀티 에이전트 시스템입니다. 엔터프라이즈 환경의 요구사항을 충족하기 위해 **SRE(사이트 신뢰성 엔지니어링) 관제, 스레드 동기화, 제로 트러스트(Zero-Trust) 기반 보안 샌드박스**를 아키텍처 레벨에서 내재화했습니다.

---

## 1. Core Architecture & Features

### 🧠 지능형 계층 구조 (Hierarchical Multi-Agent)

역할과 책임(R&R)이 명확하게 분리된 5개의 특화 에이전트가 파이프라인을 구성하여 협업합니다.

* **Architect (`command`)**: 사용자 요구사항 분석 및 전체 태스크 파이프라인(JSON) 설계.
* **Secretary (`secretary`)**: 전체 에이전트 작업 로그 기반의 핵심 진행 현황 요약 및 브리핑.
* **File Manager (`file`)**: 프로젝트 폴더/파일 구조 설계 및 Boilerplate 코드 작성.
* **Sr. Developer (`code`)**: 이전 산출물을 기반으로 실제 동작하는 비즈니스 로직(Python 등) 구현.
* **Tech Writer (`doc`)**: 구현된 코드를 분석하여 배포용 기술 문서(`README.md`) 작성.

### 🛡️ 엔터프라이즈 보안 및 무결성 (Security & Integrity)

* **Zero-Trust Sandbox**: `Path Traversal` 공격 및 심볼릭 링크 조작을 물리적으로 차단하며, 화이트리스트 확장자만 허용.
* **Malicious Code Scanner**: 생성된 코드 내 `os.remove`, `subprocess`, `eval` 등 시스템 파괴/탈취 목적의 위험 명령어를 실시간 스캔 및 차단.
* **Guided Generation (JSON Schema)**: LLM 추론 시 `response_format`을 강제하여 JSON 파싱 실패율을 0%로 수렴시키는 구조적 안정성 확보.
* **Hybrid Parser**: 예외 상황 발생 시 중괄호 스택(`{}`) 기반의 2차 텍스트 구출 알고리즘 가동.

### 📈 SRE 모니터링 및 장애 복구 (Fault Tolerance)

* **Thread-Safe LLM Core**: `threading.Lock`을 통해 다중 에이전트의 LLM 엔진 동시 접근 시 발생하는 세그먼테이션 폴트(Segmentation Fault) 원천 차단.
* **Resource Watchdog**: CPU, RAM, GPU 사용률을 실시간 모니터링하며, OOM(Out of Memory) 임계치(93%) 도달 시 스레드를 안전하게 중단(Graceful Shutdown).
* **Deadlock Prevention**: 일정 시간(180초) 응답이 없는 에이전트 스레드를 식별하고 시스템 자원을 강제 회수.

---

## 2. System Requirements

| **항목** | **최소 사양** | **권장 사양** | 
| :--- | :--- | :--- | 
| **OS** | Windows 10 / 11 (64-bit) | Windows 11 (64-bit) | 
| **RAM** | 16 GB | 32 GB 이상 | 
| **GPU** | 미지원 (CPU 모드 구동) | NVIDIA GPU (VRAM 8GB 이상, CUDA 지원) | 
| **Python** | Python 3.10 이상 | Python 3.11 | 
| **Storage** | 10 GB 여유 공간 | NVMe SSD 20 GB 여유 공간 | 

---

## 3. Installation Guide

본 프로젝트는 설치 과정의 파편화를 막기 위해 **원클릭 자동 설치 스크립트**를 제공합니다. 시스템 정책상 자동 설치가 불가한 경우 하단의 **수동 설치 및 환경변수 설정 가이드**를 참조하십시오.

### Method A: 자동 설치 (권장)

1. 윈도우 **PowerShell**을 관리자 권한으로 실행합니다.
2. 프로젝트 루트 디렉토리에서 아래 스크립트를 실행합니다.

```powershell
.\setup.ps1
```

Note: 스크립트는 MSVC C++ 빌드 툴, CUDA Toolkit, GGUF 모델 다운로드, 가상환경 생성 및 GPU 가속이 활성화된 llama-cpp-python 컴파일을 순차적으로 자동 수행합니다.