@echo off
setlocal

set "CAMPSCOUT_ROOT=%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%CAMPSCOUT_ROOT%scripts\run_campscout.ps1" %*
set "CAMPSCOUT_EXIT_CODE=%ERRORLEVEL%"

if not "%CAMPSCOUT_EXIT_CODE%"=="0" (
    echo.
    echo CampScout could not start. Review the error above, then press any key to close.
    pause >nul
)

exit /b %CAMPSCOUT_EXIT_CODE%
