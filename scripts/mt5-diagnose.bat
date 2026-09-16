@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "ROOT_DIR=%%~fI"
set "BACKEND_PYTHON=%ROOT_DIR%\apps\backend-python\.venv\Scripts\python.exe"

if not exist "%BACKEND_PYTHON%" (
  echo Backend virtual environment not found. Run mt5-platform start first.
  exit /b 1
)

"%BACKEND_PYTHON%" "%SCRIPT_DIR%mt5_diagnose.py"
