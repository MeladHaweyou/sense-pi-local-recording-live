@echo off
setlocal EnableDelayedExpansion

REM ======== CONFIGURE THESE FOR YOUR SETUP ========
set "PI_HOST=192.168.0.6"
set "PI_USER=verwalter"
set "PI_BASE=~/sensor"
set "PI_CONFIG=pi_config.yaml"
set "SENSORS=1,2,3"
set "CHANNELS=default"
set "DURATION=20"
set "REMOTE_BASE=~/logs/rate_sweep"
REM =================================================

REM Local folder on your PC to store Pi stdout logs
set "LOCAL_OUT_DIR=rate_sweep_pi_logs"
if not exist "%LOCAL_OUT_DIR%" mkdir "%LOCAL_OUT_DIR%"

echo [INFO] Creating base directory on Pi: %REMOTE_BASE%
ssh %PI_USER%@%PI_HOST% "mkdir -p %REMOTE_BASE%"

REM Sweep requested rates: 20, 40, 60, ... 500 Hz
for /L %%R in (20,20,500) do (
    echo.
    echo ==================== RATE %%R Hz ====================
    set "SESSION_DIR=%REMOTE_BASE%/%%RHz"

    set "REMOTE_CMD=cd %PI_BASE% && python3 mpu6050_multi_logger.py --config %PI_CONFIG% --rate %%R --sensors %SENSORS% --channels %CHANNELS% --duration %DURATION% --out !SESSION_DIR!"

    set "LOG_FILE=%LOCAL_OUT_DIR%\pi_rate_%%RHz.log"
    echo [INFO] Running on Pi: rate=%%R Hz, duration=%DURATION%s
    echo [INFO] Log file: !LOG_FILE!

    REM Run on Pi and capture stdout+stderr into local log file
    ssh %PI_USER%@%PI_HOST% "!REMOTE_CMD!" > "!LOG_FILE!" 2>&1

    echo [INFO] Finished rate=%%R Hz
)

echo.
echo [INFO] All Pi-side rate sweep runs complete.
echo [INFO] Check the folder "%LOCAL_OUT_DIR%" for:
echo        - pi_rate_XXXHz.log (device_rate_hz, Overruns, samples, errors)
endlocal
