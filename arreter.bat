@echo off
cd /d "%~dp0"
echo Recherche du serveur Fee Mazine...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0arreter.ps1"
pause
