@echo off
REM ===========================================================================
REM  Start Engine (Windows).bat
REM ---------------------------------------------------------------------------
REM  Double-click this file to run the Dynamic Documentary Engine.
REM
REM  Written for someone who has never used a command prompt: it checks what's
REM  installed, says plainly what to do if something is missing, and never asks
REM  the person running it to type a command. A black window opens because that
REM  is how Windows runs a .bat file — nothing needs to be typed into it, and
REM  closing it stops the engine.
REM ===========================================================================

REM Run from the folder this file lives in, so it works wherever the project
REM is kept — Desktop, Documents, a USB drive.
cd /d "%~dp0"

cls
echo ===========================================================
echo    Dynamic Documentary Engine
echo    Penn State University, College of IST
echo ===========================================================
echo.

REM --- Python ---------------------------------------------------------------

REM "py" is the launcher the official Python installer adds; "python" is the
REM fallback. Windows also ships a stub named python.exe that only opens the
REM Microsoft Store, so a version check is the reliable test.
set PYTHON=
py --version >nul 2>&1
if %errorlevel%==0 set PYTHON=py
if not defined PYTHON (
  python --version >nul 2>&1
  if %errorlevel%==0 set PYTHON=python
)

if not defined PYTHON (
  echo   Python is not installed yet.
  echo.
  echo   To install it:
  echo     1. Go to  https://www.python.org/downloads/
  echo     2. Click the big yellow "Download Python" button
  echo     3. Open the file it downloads
  echo     4. IMPORTANT: tick "Add python.exe to PATH" at the bottom
  echo        of the first installer screen, then click Install Now
  echo     5. Double-click this Start Engine file again
  echo.
  pause
  exit /b 1
)

echo   Python ....... found

REM --- FFmpeg ---------------------------------------------------------------

where ffmpeg >nul 2>&1
if not %errorlevel%==0 (
  echo   FFmpeg ....... NOT FOUND
  echo.
  echo   FFmpeg is the tool that assembles the video. Without it the
  echo   engine can choose the clips but cannot build the film.
  echo.
  echo   To install it, copy the line below, paste it into this window
  echo   by right-clicking, and press Enter:
  echo.
  echo       winget install --id Gyan.FFmpeg -e
  echo.
  echo   When it finishes, CLOSE this window and double-click Start
  echo   Engine again — Windows only notices new programs in a fresh
  echo   window.
  echo.
  echo   If that command is not recognised, see SETUP-GUIDE.md for the
  echo   manual steps.
  echo.
  pause
  exit /b 1
)

echo   FFmpeg ....... found

REM --- Python packages ------------------------------------------------------

REM Checked rather than installed every time, so a normal start stays quick
REM and works with no internet connection.
%PYTHON% -c "import flask, PIL, jsonschema" >nul 2>&1
if not %errorlevel%==0 (
  echo   Add-ons ...... installing ^(first run only, takes a minute^)
  %PYTHON% -m pip install --quiet -r requirements.txt
  %PYTHON% -c "import flask, PIL, jsonschema" >nul 2>&1
  if not %errorlevel%==0 (
    echo.
    echo   Those add-ons could not be installed automatically.
    echo   Check you are connected to the internet and try again, or
    echo   send this window to David.
    echo.
    pause
    exit /b 1
  )
) else (
  echo   Add-ons ...... found
)

echo.
echo   Starting up. Your browser will open in a moment.
echo   Leave this window open while you use the engine.
echo.

%PYTHON% web\backend\app.py

REM Only reached if the engine stops or fails to start.
echo.
echo   The engine has stopped.
pause
