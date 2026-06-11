# AMEVA Agent Orchestra 실행 및 환경 진단 스크립트

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Definition
If ($ScriptPath) { Set-Location -Path $ScriptPath }

# [1] 파이썬 가상환경(venv) 검증 및 패키지 실행 단계
$EnvDir = ".\ameva_orchestra_env"
if (-not (Test-Path -Path $EnvDir)) {
    Write-Host "Virtual environment not found. Running setup via launch.bat..." -ForegroundColor Yellow
    cmd.exe /c launch.bat
} else {
    # [2] 하드웨어와 설치된 LLM 엔진 정합성 검증
    Write-Host "Verifying hardware and LLM engine match..." -ForegroundColor Cyan
    $videoControllers = Get-CimInstance Win32_VideoController
    $hasNvidia = $false
    foreach ($vc in $videoControllers) {
        if ($vc.Name -match "NVIDIA") { $hasNvidia = $true }
    }

    $pythonExe = "$EnvDir\Scripts\python.exe"
    $checkScript = "try: from llama_cpp import llama_supports_gpu_offload; print(llama_supports_gpu_offload())`nexcept: print('False')"
    $isGpuInstalled = & $pythonExe -c $checkScript

    if ($hasNvidia -and $isGpuInstalled -match "False") {
        Write-Host "=> NVIDIA GPU detected, but CPU engine is installed. Fixing..." -ForegroundColor Yellow
        & $pythonExe -m pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121 --force-reinstall --no-cache-dir
    } elseif (-not $hasNvidia -and $isGpuInstalled -match "True") {
        Write-Host "=> No NVIDIA GPU detected, but GPU engine is installed. Fixing..." -ForegroundColor Yellow
        & $pythonExe -m pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu --force-reinstall --no-cache-dir
    } else {
        Write-Host "=> Hardware and Engine configuration matches." -ForegroundColor Green
    }
    
    # [3] 가상환경 활성화 단계
    Write-Host "Activating virtual environment..." -ForegroundColor Cyan
    . "$EnvDir\Scripts\Activate.ps1"
    
    # [4] 메인 어플리케이션 진입 및 기동
    Write-Host "Launching AMEVA Agent Orchestra..." -ForegroundColor Cyan
    & "$EnvDir\Scripts\python.exe" main.py
}
