@echo off
setlocal

cd /d "%~dp0"

echo [ChatSystem] Starting server...
start "ChatSystem Server" cmd /k python server\server.py

timeout /t 1 /nobreak >nul

echo [ChatSystem] Starting GUI client...
start "ChatSystem GUI Client" python client_gui.py

echo [ChatSystem] Done. Server and GUI client are starting in separate windows.
