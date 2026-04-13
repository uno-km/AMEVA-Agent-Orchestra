# ==========================================
# PowerShell 한글 깨짐 방지 및 환경 설정
# ==========================================
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"

# [보안/안전] 스크립트가 실행되는 파일의 실제 위치로 경로를 강제 고정합니다.
$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Definition
If ($ScriptPath) { Set-Location -Path $ScriptPath }

Write-Host "👑 AMEVA-Agent-Orchestra 무결점 환경 셋팅을 시작합니다." -ForegroundColor Cyan
Write-Host "📍 현재 작업 경로: $(Get-Location)" -ForegroundColor Gray

# ==========================================
# [0] 기존 환경 초기화 (무균실 확보)
# ==========================================
Write-Host "`n[0/5] 기존 데이터 초기화 중..." -ForegroundColor Yellow
If (Test-Path "ameva_orchestra_env") { 
    Write-Host "  -> 기존 가상환경(ameva_orchestra_env)을 삭제합니다." -ForegroundColor Red
    Remove-Item -Recurse -Force "ameva_orchestra_env" 
}
If (Test-Path "vs_buildtools.exe") { Remove-Item -Force "vs_buildtools.exe" }
Write-Host "=> 초기화 완료." -ForegroundColor Green

# ==========================================
# [1] C++ 빌드 툴 설치
# ==========================================
Write-Host "`n[1/5] MSVC C++ 컴파일러 확인 중..." -ForegroundColor Yellow
$msvcPath = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC"
If (-Not (Test-Path $msvcPath)) {
    Write-Host "  -> C++ 컴파일러 설치를 시작합니다 (수 분 소요)..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri "[https://aka.ms/vs/17/release/vs_buildtools.exe](https://aka.ms/vs/17/release/vs_buildtools.exe)" -OutFile "vs_buildtools.exe"
    Start-Process -FilePath ".\vs_buildtools.exe" -ArgumentList "--quiet --wait --norestart --nocache --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended" -Wait
    Remove-Item -Force "vs_buildtools.exe"
    Write-Host "=> C++ 컴파일러 설치 완료!" -ForegroundColor Green
} Else {
    Write-Host "=> C++ 컴파일러가 이미 설치되어 있습니다. (건너뜀)" -ForegroundColor Green
}

# ==========================================
# [2] NVIDIA CUDA Toolkit 설치 및 환경변수 핫-리로드
# ==========================================
Write-Host "`n[2/5] NVIDIA CUDA Toolkit 확인 중..." -ForegroundColor Yellow
If (-Not (Get-Command nvcc -ErrorAction SilentlyContinue)) {
    Write-Host "  -> CUDA Toolkit 패키지 설치를 진행합니다..." -ForegroundColor Yellow
    winget install -e --id Nvidia.CUDA --accept-package-agreements --accept-source-agreements
    
    # [핵심] 설치된 CUDA 경로를 터미널 껐다 켜지 않고 즉시 현재 세션에 주입
    Write-Host "  -> [시스템] 환경변수(PATH)를 실시간으로 다시 불러옵니다..." -ForegroundColor Yellow
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    
    Write-Host "=> CUDA Toolkit 설치 및 환경변수 갱신 완료!" -ForegroundColor Green
} Else {
    Write-Host "=> CUDA Toolkit이 이미 설치되어 있습니다. (건너뜀)" -ForegroundColor Green
}

# ==========================================
# [3] GGUF 모델 다운로드
# ==========================================
Write-Host "`n[3/5] Qwen 1.5B GGUF 모델 확인 중..." -ForegroundColor Yellow
$modelUrl = "[https://huggingface.co/Qwen/Qwen1.5-1.8B-Chat-GGUF/resolve/main/qwen1_5-1_8b-chat-q4_k_m.gguf](https://huggingface.co/Qwen/Qwen1.5-1.8B-Chat-GGUF/resolve/main/qwen1_5-1_8b-chat-q4_k_m.gguf)"
If (-Not (Test-Path "qwen.gguf")) {
    Write-Host "  -> 모델을 다운로드합니다..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $modelUrl -OutFile "qwen.gguf"
    Write-Host "=> 모델 다운로드 완료!" -ForegroundColor Green
} Else {
    Write-Host "=> 모델 파일이 이미 존재합니다. (건너뜀)" -ForegroundColor Green
}

# ==========================================
# [4] 파이썬 가상환경 생성 및 의존성 주입
# ==========================================
Write-Host "`n[4/5] 가상환경 생성 및 패키지 설치 중..." -ForegroundColor Yellow
python -m venv ameva_orchestra_env
& ".\ameva_orchestra_env\Scripts\python.exe" -m pip install --upgrade pip
& ".\ameva_orchestra_env\Scripts\python.exe" -m pip cache purge

# 깃허브 등에서 클론한 프로젝트의 requirements.txt가 있는지 확인 후 자동 설치
If (Test-Path "requirements.txt") {
    Write-Host "  -> requirements.txt 파일이 감지되었습니다. 전체 패키지를 설치합니다..." -ForegroundColor Yellow
    & ".\ameva_orchestra_env\Scripts\python.exe" -m pip install -r requirements.txt
} Else {
    Write-Host "  -> 기본 에이전트 구동 패키지를 설치합니다..." -ForegroundColor Yellow
    & ".\ameva_orchestra_env\Scripts\python.exe" -m pip install PyQt6 watchdog psutil
}

# ==========================================
# [5] Llama-CPP 설치 (CUDA 활성화)
# ==========================================
Write-Host "`n[5/5] GPU 가속을 위한 llama-cpp-python 컴파일 및 설치 중..." -ForegroundColor Yellow
$env:CMAKE_ARGS="-DGGML_CUDA=on"
& ".\ameva_orchestra_env\Scripts\python.exe" -m pip install llama-cpp-python --no-cache-dir --force-reinstall --upgrade

Write-Host "`n🎉 모든 셋팅이 완벽하게 완료되었습니다! 즉시 코드를 실행할 수 있습니다." -ForegroundColor Cyan
