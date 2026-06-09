@echo off
:: AMEVA Orchestra 원클릭 가동 래퍼
:: PowerShell 보안 정책을 우회하여 run.ps1을 실행합니다.

echo [AMEVA] 오케스트라 시스템 가동 중...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"

echo.
echo 시스템이 종료되었습니다. 아무 키나 누르면 닫힙니다.
pause
