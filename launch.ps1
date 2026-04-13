# ==========================================
# PowerShell Environment & Encoding Setup
# ==========================================
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
if ($PSVersionTable.PSVersion.Major -le 5) { chcp 65001 | Out-Null }
$ErrorActionPreference = "Stop"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Definition
If ($ScriptPath) { Set-Location -Path $ScriptPath }

Write-Host "--- AMEVA Environment Setup (Enterprise Hardened Mode) ---" -ForegroundColor Cyan
Write-Host "Path: $(Get-Location)" -ForegroundColor Gray

# ==========================================
# [0] Hardware Profiling
# ==========================================
Write-Host "`n[0/5] Scanning Hardware Profile..." -ForegroundColor Yellow
$videoControllers = Get-CimInstance Win32_VideoController
$hasNvidia = $false
foreach ($vc in $videoControllers) {
    if ($vc.Name -match "NVIDIA") { $hasNvidia = $true }
}

if ($hasNvidia) {
    Write-Host "=> NVIDIA GPU detected. Target: GPU Acceleration" -ForegroundColor Green
} else {
    Write-Host "=> Intel/AMD Graphics detected. Target: CPU Optimized" -ForegroundColor Green
}

# ==========================================
# [1] System Hardening: Install C++ Build Tools
# ==========================================
Write-Host "`n[1/5] Hardening System: Checking MSVC C++ Compiler..." -ForegroundColor Yellow
$msvcPath = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC"
If (-Not (Test-Path $msvcPath)) {
    Write-Host "  -> C++ 빌드 도구가 없습니다. 시스템 무결성을 위해 설치를 시작합니다 (약 5GB)..." -ForegroundColor Yellow
    [string]$vsUrl = 'https://aka.ms/vs/17/release/vs_buildtools.exe'.Trim()
    Invoke-WebRequest -Uri $vsUrl -OutFile "vs_buildtools.exe"
    Start-Process -FilePath ".\vs_buildtools.exe" -ArgumentList "--quiet --wait --norestart --nocache --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended" -Wait
    Remove-Item -Force "vs_buildtools.exe"
    Write-Host "=> MSVC Hardening Complete." -ForegroundColor Green
} Else {
    Write-Host "=> MSVC Compiler is already providing system stability." -ForegroundColor Green
}

# ==========================================
# [2] Download Qwen Model
# ==========================================
Write-Host "`n[2/5] Downloading Qwen Model..." -ForegroundColor Yellow
[string]$modelUrl = 'https://huggingface.co/Qwen/Qwen1.5-1.8B-Chat-GGUF/resolve/main/qwen1_5-1_8b-chat-q4_k_m.gguf'.Trim()
If (-Not (Test-Path "qwen.gguf")) {
    Invoke-WebRequest -Uri $modelUrl -OutFile "model/qwen.gguf"
    Write-Host "=> Model Downloaded." -ForegroundColor Green
} Else {
    Write-Host "=> Model exists." -ForegroundColor Green
}

# ==========================================
# [3] Venv & Core Dependencies
# ==========================================
Write-Host "`n[3/5] Setting up Python Environment..." -ForegroundColor Yellow
If (Test-Path "ameva_orchestra_env") { Remove-Item -Recurse -Force "ameva_orchestra_env" }
python -m venv ameva_orchestra_env
& ".\ameva_orchestra_env\Scripts\python.exe" -m pip install --upgrade pip
& ".\ameva_orchestra_env\Scripts\python.exe" -m pip cache purge

# 기본 패키지 설치
& ".\ameva_orchestra_env\Scripts\python.exe" -m pip install PyQt6 watchdog psutil GPUtil

# ==========================================
# [4] Advanced LLM Engine Installation (Native Compilation)
# ==========================================
Write-Host "`n[4/5] Installing LLM Engine (Native Compilation)..." -ForegroundColor Yellow

# [핵심 패치] MSVC 컴파일러 환경 변수 활성화 스크립트 경로 찾기
$vcvarsPaths = @(
    "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat",
    "${env:ProgramFiles}\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat",
    "${env:ProgramFiles}\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat"
)
$vcvars = ""
foreach ($path in $vcvarsPaths) {
    if (Test-Path $path) { $vcvars = $path; break }
}

$pythonExe = ".\ameva_orchestra_env\Scripts\python.exe"

if ($hasNvidia) {
    Write-Host "  -> Attempting GPU Build with CUDA..." -ForegroundColor White
    If (-Not (Get-Command nvcc -ErrorAction SilentlyContinue)) {
        winget install -e --id Nvidia.CUDA --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    }
    $env:CMAKE_ARGS="-DGGML_CUDA=on"
} else {
    Write-Host "  -> Attempting Optimized CPU Build..." -ForegroundColor White
    Remove-Item Env:\CMAKE_ARGS -ErrorAction SilentlyContinue
    $env:CMAKE_ARGS="-DGGML_CUDA=off"
}

# 파이썬 3.12 이상의 환경을 위해, 백그라운드에서 C++ 컴파일러(nmake)를 연결한 후 설치를 진행합니다.
if ($vcvars -ne "") {
    Write-Host "  -> Injecting MSVC Compiler Environment..." -ForegroundColor Yellow
    cmd.exe /c "call `"$vcvars`" && `"$pythonExe`" -m pip install llama-cpp-python --no-cache-dir --force-reinstall --upgrade"
} else {
    Write-Host "  -> Warning: MSVC not found in standard paths. Attempting default install..." -ForegroundColor Red
    & $pythonExe -m pip install llama-cpp-python --no-cache-dir --force-reinstall --upgrade
}

# ==========================================
# [5] Finish
# ==========================================
Write-Host "`n🎉 All Systems Hardened and Ready!" -ForegroundColor Cyan
Write-Host "Run '.\ameva_orchestra_env\Scripts\Activate.ps1' and 'python code_god_enterprise.py' to start." -ForegroundColor White