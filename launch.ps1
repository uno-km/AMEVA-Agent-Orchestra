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

function Write-Section {
    param([string]$Text)
    Write-Host "`n$Text" -ForegroundColor Yellow
}

function Test-HuggingFaceConnectivity {
    try {
        $check = Test-NetConnection huggingface.co -Port 443 -InformationLevel Quiet
        return $check
    } catch {
        return $false
    }
}

function Download-Model {
    param(
        [string]$Url,
        [string]$Destination
    )
    if (Test-Path $Destination) {
        Write-Host "=> 모델이 이미 있습니다: $Destination" -ForegroundColor Green
        return $true
    }

    Write-Host "=> 다운로드 중: $Destination" -ForegroundColor White
    try {
        Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing -TimeoutSec 3600
        Write-Host "=> 다운로드 성공: $Destination" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "=> 다운로드 실패: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

# ==========================================
# [0] Hardware Profiling
# ==========================================
Write-Section "[0/6] Scanning Hardware Profile..."
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
# [1] Prepare Workspace and Model Directory
# ==========================================
Write-Section "[1/6] Preparing workspace directories..."
$ModelDir = Join-Path $ScriptPath "model"
$EnvDir = Join-Path $ScriptPath "ameva_orchestra_env"

if (-Not (Test-Path $ModelDir)) {
    New-Item -ItemType Directory -Path $ModelDir | Out-Null
    Write-Host "=> Created model directory: $ModelDir" -ForegroundColor Green
} else {
    Write-Host "=> Model directory exists: $ModelDir" -ForegroundColor Green
}

# ==========================================
# [2] Download GGUF Model Assets
# ==========================================
Write-Section "[2/6] Checking GGUF model assets..."
if (-Not (Test-HuggingFaceConnectivity)) {
    Write-Host "[Warning] HuggingFace connectivity may be blocked by firewall. 모델 다운로드가 실패할 수 있습니다." -ForegroundColor Yellow
}

$models = @{
    "qwen.gguf" = "https://huggingface.co/Qwen/Qwen1.5-1.8B-Chat-GGUF/resolve/main/qwen1_5-1_8b-chat-q4_k_m.gguf"
    "qwen2.5-0.5b.gguf" = "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q8_0.gguf"
    "llama3.2-1b.gguf" = "https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF/resolve/main/Llama-3.2-1B-Instruct-Q4_K_M.gguf"
}

foreach ($name in $models.Keys) {
    $dest = Join-Path $ModelDir $name
    if (-Not (Test-Path $dest)) {
        Download-Model -Url $models[$name] -Destination $dest | Out-Null
    } else {
        Write-Host "=> 이미 존재하는 모델: $name" -ForegroundColor Green
    }
}

# 기본 로드 모델은 qwen.gguf로 유지
$PrimaryModel = Join-Path $ModelDir "qwen2.5-0.5b.gguf"
if (-Not (Test-Path $PrimaryModel)) {
    Write-Host "[Error] 핵심 모델 qwen.gguf를 찾을 수 없습니다. 설치를 다시 시도하세요." -ForegroundColor Red
    exit 1
}

# ==========================================
# [3] Python Virtual Environment
# ==========================================
Write-Section "[3/6] Setting up Python virtual environment..."
if (Test-Path $EnvDir) {
    Write-Host "=> Existing virtual environment detected. Recreating for clean install..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $EnvDir
}

python -m venv $EnvDir
& "$EnvDir\Scripts\python.exe" -m ensurepip --upgrade
& "$EnvDir\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel

# 핵심 의존성 설치
& "$EnvDir\Scripts\python.exe" -m pip install -r "$ScriptPath\requirements.txt"

# ==========================================
# [4] LLM Engine Installation and GPU Policy
# ==========================================
Write-Section "[4/6] Installing llama-cpp-python and configuring acceleration..."
$pythonExe = "$EnvDir\Scripts\python.exe"
$env:CMAKE_ARGS = if ($hasNvidia) { "-DGGML_CUDA=on" } else { "-DGGML_CUDA=off" }

$vcvarsPaths = @(
    "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat",
    "${env:ProgramFiles}\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat",
    "${env:ProgramFiles}\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat"
)
$vcvars = $vcvarsPaths | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($vcvars) {
    Write-Host "=> MSVC environment found. Installing with native compiler support..." -ForegroundColor Green
    cmd.exe /c "call `"$vcvars`" && `"$pythonExe`" -m pip install llama-cpp-python --no-cache-dir --force-reinstall --upgrade"
} else {
    Write-Host "=> MSVC environment not found. Installing normally..." -ForegroundColor Yellow
    & $pythonExe -m pip install llama-cpp-python --no-cache-dir --force-reinstall --upgrade
}

$llamaCheck = & $pythonExe -c "import importlib.util; print(importlib.util.find_spec('llama_cpp') is not None)"
if ($llamaCheck -match "False") {
    Write-Host "=> llama-cpp-python import failed. Falling back to prebuilt wheel." -ForegroundColor Yellow
    & $pythonExe -m pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu --no-cache-dir
}

# ==========================================
# [5] Final Validation
# ==========================================
Write-Section "[5/6] Validating installation..."
$pythonExe = "$EnvDir\Scripts\python.exe"
try {
    & $pythonExe -c "import PyQt6, psutil, GPUtil, watchdog, llama_cpp" | Out-Null
    Write-Host "=> Dependency check passed." -ForegroundColor Green
} catch {
    Write-Host "[Error] 일부 의존성 로드에 실패했습니다: $_" -ForegroundColor Red
    exit 1
}

# ==========================================
# [6] Finish
# ==========================================
Write-Section "[6/6] Finish"
Write-Host "🎉 AMEVA setup complete." -ForegroundColor Cyan
Write-Host "Run '$EnvDir\Scripts\Activate.ps1' and then 'python code_god_enterprise.py'" -ForegroundColor White
