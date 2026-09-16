@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "ROOT_DIR=%%~fI"
set "BACKEND_DIR=%ROOT_DIR%\apps\backend-python"
set "SECRET_HELPER=%SCRIPT_DIR%generate_backend_secret.py"
set "BACKEND_HOST=0.0.0.0"
set "BACKEND_PORT=8000"

if "%~1"=="" goto usage

if /I "%~1"=="start" goto start
if /I "%~1"=="stop" goto stop
if /I "%~1"=="restart" goto restart
if /I "%~1"=="status" goto status
goto usage

:start
call :ensure_backend || exit /b 1
echo Starting MT5 Platform backend on http://%BACKEND_HOST%:%BACKEND_PORT%
start "MT5 Platform Backend" /D "%BACKEND_DIR%" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --host %BACKEND_HOST% --port %BACKEND_PORT%"
echo.
echo Local backend:   http://localhost:%BACKEND_PORT%/docs
echo Backend LAN API: http://YOUR-LAN-IP:%BACKEND_PORT%
exit /b 0

:stop
call :stop_port %BACKEND_PORT%
echo MT5 Platform backend stopped if it was running.
exit /b 0

:restart
call :stop
ping -n 3 127.0.0.1 >nul
call :start
exit /b %ERRORLEVEL%

:status
call :status_port "Backend" %BACKEND_PORT%
exit /b 0

:ensure_backend
if not exist "%BACKEND_DIR%\requirements.txt" (
  echo Backend requirements file not found at "%BACKEND_DIR%\requirements.txt".
  exit /b 1
)

if not exist "%BACKEND_DIR%\.env" (
  copy "%BACKEND_DIR%\.env.example" "%BACKEND_DIR%\.env" >nul
  echo Created "%BACKEND_DIR%\.env" from .env.example.
)

if not exist "%BACKEND_DIR%\.venv\Scripts\python.exe" (
  echo Creating backend Python virtual environment...
  py -3.12 -m venv "%BACKEND_DIR%\.venv"
  if errorlevel 1 (
    echo Python launcher for 3.12 was unavailable. Trying Python 3.13...
    py -3.13 -m venv "%BACKEND_DIR%\.venv"
    if errorlevel 1 (
      echo Python launcher for 3.13 was unavailable. Trying any Python 3 runtime...
      py -3 -m venv "%BACKEND_DIR%\.venv"
      if errorlevel 1 (
        echo Python launcher fallback failed. Trying default python...
        python -m venv "%BACKEND_DIR%\.venv"
        if errorlevel 1 exit /b 1
      )
    )
  )
)

echo Installing backend dependencies...
"%BACKEND_DIR%\.venv\Scripts\python.exe" -m pip install -r "%BACKEND_DIR%\requirements.txt"
if errorlevel 1 exit /b 1

set "BACKEND_PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"

findstr /C:"generate-with-python-command-in-readme" "%BACKEND_DIR%\.env" >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  echo Generating backend FERNET_KEY in .env...
  for /f "delims=" %%K in ('""!BACKEND_PYTHON!" "%SECRET_HELPER%" fernet"') do set "NEW_FERNET_KEY=%%K"
  if "!NEW_FERNET_KEY!"=="" (
    echo Failed to generate FERNET_KEY.
    exit /b 1
  )
  powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Content -LiteralPath '%BACKEND_DIR%\.env') -replace '^FERNET_KEY=.*', 'FERNET_KEY=!NEW_FERNET_KEY!' | Set-Content -LiteralPath '%BACKEND_DIR%\.env'"
  if errorlevel 1 exit /b 1
)

findstr /C:"change-this-to-a-long-random-secret" "%BACKEND_DIR%\.env" >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  echo Generating backend JWT_SECRET_KEY in .env...
  for /f "delims=" %%K in ('""!BACKEND_PYTHON!" "%SECRET_HELPER%" jwt"') do set "NEW_JWT_SECRET=%%K"
  if "!NEW_JWT_SECRET!"=="" (
    echo Failed to generate JWT_SECRET_KEY.
    exit /b 1
  )
  powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Content -LiteralPath '%BACKEND_DIR%\.env') -replace '^JWT_SECRET_KEY=.*', 'JWT_SECRET_KEY=!NEW_JWT_SECRET!' | Set-Content -LiteralPath '%BACKEND_DIR%\.env'"
  if errorlevel 1 exit /b 1
)
exit /b 0

:stop_port
set "PORT=%~1"
set "FOUND=0"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
  set "FOUND=1"
  echo Stopping process %%P on port %PORT%...
  taskkill /T /F /PID %%P >nul 2>nul
)
if "%FOUND%"=="0" echo No process is listening on port %PORT%.
exit /b 0

:status_port
set "NAME=%~1"
set "PORT=%~2"
set "FOUND=0"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
  set "FOUND=1"
  echo %NAME% is running on port %PORT% with PID %%P.
)
if "%FOUND%"=="0" echo %NAME% is not running on port %PORT%.
exit /b 0

:usage
echo Usage:
echo   mt5-backend start
echo   mt5-backend stop
echo   mt5-backend restart
echo   mt5-backend status
exit /b 1
