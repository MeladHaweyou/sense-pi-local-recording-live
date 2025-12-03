@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ====== Configuration ======
set "OUTPUT_FILE=combined.py"

REM Use the current directory as the root (run this from your main folder)
set "ROOT=%CD%"
set "OUT_FULL=%ROOT%\%OUTPUT_FILE%"

REM Delete output file if it exists
del "%OUTPUT_FILE%" 2>nul

REM ================== Directory Details (Tree + Detailed DIR) ==================
>>"%OUTPUT_FILE%" echo ============================= DIRECTORY OVERVIEW =============================
>>"%OUTPUT_FILE%" echo Root: %ROOT%
>>"%OUTPUT_FILE%" echo Timestamp: %DATE% %TIME%
>>"%OUTPUT_FILE%" echo.
>>"%OUTPUT_FILE%" echo ----------------------------- TREE (with files) -----------------------------
tree "%ROOT%" /F >>"%OUTPUT_FILE%"
>>"%OUTPUT_FILE%" echo.
>>"%OUTPUT_FILE%" echo ------------------------- DETAILED DIRECTORY LISTING -------------------------
dir "%ROOT%" /S /A >>"%OUTPUT_FILE%"
>>"%OUTPUT_FILE%" echo.
>>"%OUTPUT_FILE%" echo ============================================================================
>>"%OUTPUT_FILE%" echo(

REM ================== Concatenate ALL files (any extension) ======================
for /f "delims=" %%f in ('
  dir /b /s /a:-d "%ROOT%\*" ^| sort
') do (
  REM Skip the output file itself
  if /i not "%%~f"=="%OUT_FULL%" (
    REM Build nice relative labels
    set "ABS=%%~f"
    set "REL=!ABS:%ROOT%\=!"          REM e.g. sub\pkg\file.ext
    set "DIRABS=%%~dpf"
    set "DIRREL=!DIRABS:%ROOT%\=!"     REM e.g. sub\pkg\
    set "SIZE=%%~zf"
    set "TIME=%%~tf"
    set "EXT=%%~xf"

    echo Adding !REL!...

    REM Safe header lines (use echo() so parentheses are harmless)
    >>"%OUTPUT_FILE%" echo(============================= !REL!
    >>"%OUTPUT_FILE%" echo(# File: %%~nxf (ext: !EXT!)
    >>"%OUTPUT_FILE%" echo(# Dir : !DIRREL!
    >>"%OUTPUT_FILE%" echo(# Size: !SIZE! bytes
    >>"%OUTPUT_FILE%" echo(# Time: !TIME!
    >>"%OUTPUT_FILE%" echo(============================= !REL!

    REM Append file contents (binary files will be dumped raw)
    type "%%~f">>"%OUTPUT_FILE%"

    REM Separator line after content
    >>"%OUTPUT_FILE%" echo(
    >>"%OUTPUT_FILE%" echo ------------------------------ END OF FILE ------------------------------
    >>"%OUTPUT_FILE%" echo(
  )
)

echo All files from "%ROOT%" and subfolders combined into "%OUTPUT_FILE%".
pause
