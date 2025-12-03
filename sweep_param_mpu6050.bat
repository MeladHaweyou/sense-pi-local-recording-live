@echo off
setlocal

REM ======== CONFIGURE THESE FOR YOUR SETUP ========
set "PI_HOST=192.168.0.6"
set "PI_USER=verwalter"
set "PI_PASS=66442200"          REM make sure this matches the Pi password
set "PI_BASE=~/sensor"
set "PI_CONFIG=pi_config.yaml"

REM Where logs live on the Pi
set "REMOTE_BASE=~/logs/param_sweep"

REM Local folder on your PC to store Pi stdout logs (run summaries)
set "LOCAL_LOG_DIR=param_sweep_logs"

REM Recording duration per run (seconds)
set "DURATION=15"

REM Path to PuTTY plink.exe
set "PLINK=C:\Program Files\PuTTY\plink.exe"

REM Non-interactive SSH with password
set "PLINK_OPTS=-ssh -batch -pw %PI_PASS%"
REM =================================================

if not exist "%PLINK%" (
    echo [ERROR] plink.exe not found at "%PLINK%"
    goto :EOF
)

if not exist "%LOCAL_LOG_DIR%" mkdir "%LOCAL_LOG_DIR%"

echo [INFO] Creating base directory on Pi: %REMOTE_BASE%
"%PLINK%" %PLINK_OPTS% %PI_USER%@%PI_HOST% "mkdir -p %REMOTE_BASE%"
if errorlevel 1 (
    echo [ERROR] Failed to create base directory on Pi.
    goto :EOF
)

echo.
echo [INFO] Starting parametric MPU6050 sweep...
echo [INFO] NOTE: DLPF is taken from pi_config.yaml in this version.

REM ===== SINGLE “CONFIGURATION” TAGS =====
REM General 1-sensor default channels
for %%R in (20 40 60 80 100 120 140 160 180 200) do (
    call :RUN 1 default %%R GEN_S1_default
)

REM General 3-sensor default channels
for %%R in (20 40 60 80 100 120 140 160 180 200) do (
    call :RUN "1,2,3" default %%R GEN_S123_default
)


REM 1 sensor, "1 channel" ~ acc only (ax,ay,az)
for %%R in (50 100 150 200 250 300 350 400 450 500) do (
    call :RUN 1 acc %%R SPEC_S1_1ch_acc
)

REM 1 sensor, 3 channels = default (ax,ay,gz)
for %%R in (50 100 150 200 250 300 350 400 450 500) do (
    call :RUN 1 default %%R SPEC_S1_3ch_default
)

REM 1 sensor, 6 channels = both
for %%R in (50 100 150 200) do (
    call :RUN 1 both %%R SPEC_S1_6ch_both
)

REM 3 sensors, 6 channels = both
for %%R in (50 100 150 200) do (
    call :RUN "1,2,3" both %%R SPEC_S123_6ch_both
)

echo.
echo [INFO] All parametric runs finished.
echo [INFO] Pi stdout logs are in "%LOCAL_LOG_DIR%".
echo [INFO] Each log contains: device_rate, samples per sensor, Overruns, output directory, etc.

goto :EOF

REM ==================== SUBROUTINE: RUN ONE CONFIG ====================

:RUN
REM Args: %1 = SENSORS, %2 = CHANNELS, %3 = RATE, %4 = TAG
set "SENSORS=%1"
set "CHANNELS=%2"
set "RATE=%3"
set "TAG=%4"

REM Remote output directory on Pi for this run
set "SESSION_DIR=%REMOTE_BASE%/%TAG%/%RATE%Hz"

REM Local log file (captured stdout+stderr)
set "LOG_FILE=%LOCAL_LOG_DIR%\%TAG%_%RATE%Hz.log"

echo.
echo [INFO] Running: SENSORS=%SENSORS% CHANNELS=%CHANNELS% RATE=%RATE% Hz
echo [INFO]   Remote out dir: %SESSION_DIR%
echo [INFO]   Local log file: %LOG_FILE%

set "REMOTE_CMD=cd %PI_BASE% && python3 mpu6050_multi_logger.py --config %PI_CONFIG% --rate %RATE% --sensors %SENSORS% --channels %CHANNELS% --duration %DURATION% --out %SESSION_DIR%"

"%PLINK%" %PLINK_OPTS% %PI_USER%@%PI_HOST% "%REMOTE_CMD%" > "%LOG_FILE%" 2>&1

if errorlevel 1 (
    echo [WARN] Run failed (see %LOG_FILE%)
) else (
    echo [INFO] Finished run (SENSORS=%SENSORS% CHANNELS=%CHANNELS% RATE=%RATE% Hz)
)
goto :EOF
