@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "PUTTY=C:\Program Files\PuTTY"
set "PSCP=%PUTTY%\pscp.exe"
set "PLINK=%PUTTY%\plink.exe"

set "LOCAL_ROOT=C:\Projects\sense-pi-local-recording-live"
set "PI_USER=verwalter"
set "PI_HOST=192.168.0.108"
set "REMOTE_DIR=/home/verwalter/sensor"
set "PI_PASS=66442200"
set "AUTH=-batch -noagent -pw %PI_PASS%"

if /I not "%REMOTE_DIR%"=="/home/verwalter/sensor" (echo Refusing to wipe %REMOTE_DIR% & exit /b 1)

"%PLINK%" %AUTH% -ssh %PI_USER%@%PI_HOST% "mkdir -p %REMOTE_DIR% && rm -rf %REMOTE_DIR%/* %REMOTE_DIR%/.[!.]* %REMOTE_DIR%/..?* && mkdir -p %REMOTE_DIR%/sensepi"
if errorlevel 1 exit /b 1

"%PSCP%" %AUTH% -r "%LOCAL_ROOT%\raspberrypi_scripts\*" %PI_USER%@%PI_HOST%:%REMOTE_DIR%/
if errorlevel 1 exit /b 1

"%PSCP%" %AUTH% -r "%LOCAL_ROOT%\src\sensepi\config" %PI_USER%@%PI_HOST%:%REMOTE_DIR%/sensepi/
if errorlevel 1 exit /b 1

"%PSCP%" %AUTH% "%LOCAL_ROOT%\src\sensepi\__init__.py" %PI_USER%@%PI_HOST%:%REMOTE_DIR%/sensepi/__init__.py
if errorlevel 1 exit /b 1

echo DONE
endlocal
