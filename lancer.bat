@echo off
cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo Environnement virtuel introuvable.
    echo Executez d'abord : python -m venv venv
    echo puis : venv\Scripts\activate et pip install -r requirements.txt
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo Demarrage du serveur Fee Mazine...
echo Le navigateur va s'ouvrir automatiquement sur http://127.0.0.1:8000
echo Pour arreter : fermez cette fenetre, ou Ctrl+C, ou lancez arreter.bat.
echo.

start "" /min cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:8000"

uvicorn app:app
