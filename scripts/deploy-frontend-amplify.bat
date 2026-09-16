@echo off
setlocal
REM Zip-based Amplify deploy for forex frontend (signalbridge.in).
REM
REM Build zip only (for console drag-and-drop):
REM   scripts\deploy-frontend-amplify.bat build
REM
REM Build + upload via AWS CLI:
REM   set AMPLIFY_FOREX_APP_ID=your-app-id
REM   set AWS_REGION=ap-south-1
REM   scripts\deploy-frontend-amplify.bat
REM
REM   scripts\deploy-frontend-amplify.bat YOUR_APP_ID main

set "ARG1=%~1"
set "ARG2=%~2"
set "PS_ARGS="

if /I "%ARG1%"=="build" (
  set "PS_ARGS=-BuildOnly"
) else if not "%ARG1%"=="" (
  set "PS_ARGS=-AppId %ARG1%"
  if not "%ARG2%"=="" set "PS_ARGS=%PS_ARGS% -Branch %ARG2%"
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy-frontend-amplify-zip.ps1" %PS_ARGS%
exit /b %ERRORLEVEL%
