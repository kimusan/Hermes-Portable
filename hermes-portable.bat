@echo off
setlocal
set "ROOT=%~dp0"
powershell -ExecutionPolicy Bypass -File "%ROOT%bin\hermes-portable.ps1" %*
exit /b %ERRORLEVEL%
