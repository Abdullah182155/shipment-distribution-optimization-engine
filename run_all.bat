@echo off
title Courier Optimizer V2 Launcher
color 0A

echo ===================================================
echo     COURIER OPTIMIZER V2 - ALL-IN-ONE LAUNCHER
echo ===================================================
echo.
echo Starting Backend (FastAPI)...
start "Courier Optimizer Backend" cmd /k "cd backend && python run.py"

echo Starting Frontend (React/Vite)...
start "Courier Optimizer Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo Both servers have been launched in separate windows!
echo Backend API: http://localhost:8000
echo Frontend UI: http://localhost:5173
echo.
pause
