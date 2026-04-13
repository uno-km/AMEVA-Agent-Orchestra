# ==========================================
# PowerShell Environment & Encoding Setup
# ==========================================
# Force UTF-8 for console output and file operations
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
if ($PSVersionTable.PSVersion.Major -le 5) {
    # Set console code page to UTF-8 for older PowerShell versions
    chcp 65001 | Out-Null
}

$ErrorActionPreference = "Stop"

# [Security] Force location to the script's directory
$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Definition
If ($ScriptPath) { Set-Location -Path $ScriptPath }

Write-Host "👑 Starting AMEVA-Agent-Orchestra Environment Setup." -ForegroundColor Cyan
Write-Host "📍 Current working directory: $(Get-Location)" -ForegroundColor Gray

# ==========================================
# [0] Initialize Environment
# ==========================================
Write-Host "`n[0/5] Initializing data..." -ForegroundColor Yellow
If (Test-Path "ameva_orchestra_env") { 
    Write-Host "  -> Removing existing virtual environment (ameva_orchestra_env)..." -ForegroundColor Red
    Remove-Item -Recurse -Force "ameva_orchestra_env" 
}
If (Test-Path "vs_buildtools.exe") { Remove-Item -Force "vs_buildtools.exe" }
Write-Host "=> Initialization complete." -ForegroundColor Green

# ==========================================
# [1] Install C++ Build Tools
# ==========================================
Write-Host "`n[1/5] Checking MSVC C++ Compiler..." -ForegroundColor Yellow
$msvcPath = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC"
If (-Not (Test-Path $msvcPath)) {
    Write-Host "  -> Starting C++ compiler installation (this may take a few minutes)..." -ForegroundColor Yellow
    # Fixed: Removed markdown link syntax
    $vsUrl = "[https://aka.ms/vs/17/release/vs_buildtools.exe](https://aka.ms/vs/17/release/vs_buildtools.exe)"
    Invoke-WebRequest -Uri $vsUrl -OutFile "vs_buildtools.exe"
    Start-Process -FilePath ".\vs_buildtools.exe" -ArgumentList "--quiet --wait --norestart --nocache --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended" -Wait
    Remove-Item -Force "vs_buildtools.exe"
    Write-Host "=> C++ compiler installed successfully!" -ForegroundColor Green
} Else {
    Write-Host "=> C++ compiler is already installed. (Skipping)" -ForegroundColor Green
}

# ==========================================
# [2] Install NVIDIA CUDA Toolkit
# ==========================================
Write-Host "`n[2/5] Checking NVIDIA CUDA Toolkit..." -ForegroundColor Yellow
If (-Not (Get-Command nvcc -ErrorAction SilentlyContinue)) {
    Write-Host "  -> Installing CUDA Toolkit package..." -ForegroundColor Yellow
    winget install -e --id Nvidia.CUDA --accept-package-agreements --accept-source-agreements
    
    Write-Host "  -> [System] Refreshing environment variables (PATH)..." -ForegroundColor Yellow
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    
    Write-Host "=> CUDA Toolkit installed and PATH updated!" -ForegroundColor Green
} Else {
    Write-Host "=> CUDA Toolkit is already installed. (Skipping)" -ForegroundColor Green
}

# ==========================================
# [3] Download GGUF Model
# ==========================================
Write-Host "`n[3/5] Checking Qwen 1.5B GGUF Model..." -ForegroundColor Yellow
# Fixed: Removed markdown link syntax
$modelUrl = "[https://huggingface.co/Qwen/Qwen1.5-1.8B-Chat-GGUF/resolve/main/qwen1_5-1_8b-chat-q4_k_m.gguf](https://huggingface.co/Qwen/Qwen1.5-1.8B-Chat-GGUF/resolve/main/qwen1_5-1_8b-chat-q4_k_m.gguf)"
If (-Not (Test-Path "qwen.gguf")) {
    Write-Host "  -> Downloading model (this may take time depending on your network)..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $modelUrl -OutFile "qwen.gguf"
    Write-Host "=> Model download complete!" -ForegroundColor Green
} Else {
    Write-Host "=> Model file already exists. (Skipping)" -ForegroundColor Green
}

# ==========================================
# [4] Create Virtual Environment & Install Dependencies
# ==========================================
Write-Host "`n[4/5] Creating virtual environment and installing packages..." -ForegroundColor Yellow
python -m venv ameva_orchestra_env
& ".\ameva_orchestra_env\Scripts\python.exe" -m pip install --upgrade pip
& ".\ameva_orchestra_env\Scripts\python.exe" -m pip cache purge

If (Test-Path "requirements.txt") {
    Write-Host "  -> requirements.txt detected. Installing all packages..." -ForegroundColor Yellow
    & ".\ameva_orchestra_env\Scripts\python.exe" -m pip install -r requirements.txt
} Else {
    Write-Host "  -> Installing core packages..." -ForegroundColor Yellow
    & ".\ameva_orchestra_env\Scripts\python.exe" -m pip install PyQt6 watchdog psutil GPUtil
}

# ==========================================
# [5] Install Llama-CPP (CUDA Enabled)
# ==========================================
Write-Host "`n[5/5] Compiling llama-cpp-python with GPU acceleration..." -ForegroundColor Yellow
$env:CMAKE_ARGS="-DGGML_CUDA=on"
& ".\ameva_orchestra_env\Scripts\python.exe" -m pip install llama-cpp-python --no-cache-dir --force-reinstall --upgrade

Write-Host "`n🎉 All settings have been completed! You can now run the application." -ForegroundColor Cyan