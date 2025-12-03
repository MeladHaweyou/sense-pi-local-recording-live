@echo off
setlocal

REM ======== CONFIGURE ========
set "PI_HOST=192.168.0.6"
set "PI_USER=verwalter"
set "PI_PASS=66442200"
set "REMOTE_BASE=/home/verwalter/logs/param_sweep"

set "LOCAL_BASE=C:\Projects\sense-pi-local-recording-live-main\param_sweep_data"

set "PSCP=C:\Program Files\PuTTY\pscp.exe"
REM ===========================

if not exist "%PSCP%" (
    echo [ERROR] pscp.exe not found at "%PSCP%"
    goto :EOF
)

if not exist "%LOCAL_BASE%" mkdir "%LOCAL_BASE%"

echo [INFO] Downloading all param_sweep data from %PI_USER%@%PI_HOST%:%REMOTE_BASE%
"%PSCP%" -r -pw %PI_PASS% %PI_USER%@%PI_HOST%:%REMOTE_BASE% "%LOCAL_BASE%"

if errorlevel 1 (
    echo [ERROR] PSCP failed. Check host, password, and paths.
) else (
    echo [INFO] Done. Data copied under "%LOCAL_BASE%\param_sweep\..."
)
endlocal
