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

### Method B: 수동 설치 및 환경변수 설정 (Manual Setup)
보안이 엄격한 사내망 또는 개별 인프라 환경에서 직접 구성할 때의 절차입니다.

#### Step 1. MSVC C++ 빌드 툴 설치
Python C-Extension 모듈(llama-cpp-python) 빌드를 위해 C++ 컴파일러가 필요합니다.

* Visual Studio Build Tools 다운로드 및 설치.

* 설치 시 "C++를 사용한 데스크톱 개발" 워크로드 체크 필수.

#### Step 2. NVIDIA CUDA Toolkit 설치
GPU 가속을 위해 하드웨어 아키텍처에 맞는 CUDA Toolkit을 설치해야 합니다.

* NVIDIA CUDA Toolkit Archive에서 설치 (권장 버전: 12.x).

* **[필수] 환경변수 수동 설정 방법:**

  * 윈도우 키 + R 입력 -> sysdm.cpl 실행 -> [고급] 탭 -> [환경 변수] 클릭.

  * "시스템 변수"의 Path 선택 후 [편집] 클릭.

  * 다음 경로가 존재하는지 확인하고, 없다면 **[새로 만들기]**로 추가합니다.

    * C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x\bin

    * C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.x\libnvvp

  * 확인을 눌러 저장 후, 터미널을 껐다가 다시 실행하여 nvcc --version 명령어로 인식을 확인합니다.

#### Step 3. 가상환경 및 의존성 라이브러리 설치
프로젝트 디렉토리에서 터미널을 열고 다음 명령어를 순차적으로 실행합니다.

```Bash
# 가상환경 생성 및 활성화
python -m venv ameva_env
.\ameva_env\Scripts\activate
# 기본 패키지 설치
pip install --upgrade pip
pip install -r requirements.txt
```
#### Step 4. LLM 모델 준비
* Qwen1.5-1.8B-Chat-GGUF (q4_k_m) 모델을 다운로드합니다.

* 다운로드한 파일을 qwen.gguf로 이름을 변경하여 프로젝트 루트 디렉토리에 위치시킵니다.

#### Step 5. GPU 가속 Llama-CPP 강제 컴파일
환경변수 적용 상태에서 CUDA 가속을 활성화하여 엔진을 빌드합니다. (PowerShell 기준)

```PowerShell
$env:CMAKE_ARGS="-DGGML_CUDA=on"
pip install llama-cpp-python --no-cache-dir --force-reinstall --upgrade
```

## 4. Usage
모든 환경이 구축되었다면, 가상환경이 활성화된 터미널에서 메인 컨트롤 패널을 가동합니다.

```Bash
python code_god_enterprise.py
```
1.  **지휘 명령 입력**: UI 좌측 상단의 입력창에 목표(예: PyQt를 이용한 계산기 앱 작성)를 입력하고 [⚡ 지휘 개시] 버튼을 클릭합니다.

2. **실시간 관제** : 우측 패널의 SRE 모니터링 그래프(CPU/RAM/GPU) 및 Watchdog 트레이스 로그를 통해 파이프라인 진행 및 시스템 부하 상태를 확인합니다.

3. **산출물 확인** : 생성된 파일은 CodeGod_Workspace 폴더에, 각 에이전트의 수행 이력은 CodeGod_Memory 폴더에 마크다운 형태로 영속 저장됩니다.

## 5. Troubleshooting / FAQ
* Q. GPU 가동률이 0%로 나옵니다.

  * A: llama-cpp-python 컴파일 시 CUDA 환경변수가 정상적으로 로드되지 않아 CPU 모드로 Fallback된 상태입니다. 터미널을 재시작한 후 Step 5 과정을 다시 수행하십시오.

* Q. RAM 사용량이 90%를 넘어가며 에이전트가 강제 종료됩니다.

  * A: SRE Watchdog이 OS 멈춤(Freezing)을 방지하기 위해 개입한 정상적인 현상입니다. 더 가벼운 GGUF 모델을 사용하거나 백그라운드 프로세스를 정리하십시오.
