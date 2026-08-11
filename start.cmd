@echo off
set PORT=%1
if "%PORT%"=="" set PORT=8000
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" -Port %PORT%
