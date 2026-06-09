# AMEVA Agent Orchestra 실행 및 환경 진단 스크립트

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Definition
If ($ScriptPath) { Set-Location -Path $ScriptPath }

# [1] 파이썬 가상환경(venv) 검증 및 패키지 실행 단계
$EnvDir = ".\ameva_orchestra_env"
if (-not (Test-Path -Path $EnvDir)) {
    Write-Host "Virtual environment not found. Running setup via launch.bat..." -ForegroundColor Yellow
    cmd.exe /c launch.bat
} else {
    # [2] 가상환경 활성화 단계
    Write-Host "Activating virtual environment..." -ForegroundColor Cyan
    . "$EnvDir\Scripts\Activate.ps1"
    
    # [3] 메인 어플리케이션 진입 및 기동
    Write-Host "Launching AMEVA Agent Orchestra..." -ForegroundColor Cyan
    & "$EnvDir\Scripts\python.exe" main.py
}
