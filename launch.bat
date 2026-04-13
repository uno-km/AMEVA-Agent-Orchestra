@echo off
:: 코드의 신 - AMEVA Orchestra 원클릭 가동 래퍼
:: 관리자 권한으로 PowerShell을 실행하며 보안 정책을 우회합니다.

echo [AMEVA] 오케스트라 시스템 가동 준비 중...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch.ps1"

echo.
echo 모든 작업이 완료되었습니다. 아무 키나 누르면 종료합니다.
pause
