@echo off
:: 코드의 신 - AMEVA Orchestra 원클릭 가동 래퍼
:: 관리자 권한으로 PowerShell을 실행하며 보안 정책을 우회합니다.

echo [AMEVA] Preparing orchestra system...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch.ps1"

echo.
echo All operations completed. Press any key to exit.
pause
