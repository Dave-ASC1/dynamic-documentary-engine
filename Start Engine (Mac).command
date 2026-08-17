#!/bin/bash
#
# Start Engine (Mac).command
# ---------------------------------------------------------------------------
# Double-click this file to run the Dynamic Documentary Engine.
#
# Written for someone who has never used a terminal: it checks what's
# installed, says plainly what to do if something is missing, and never
# asks the person running it to type a command. A Terminal window opens
# because that is how macOS runs a .command file — nothing needs to be
# typed into it, and closing it stops the engine.

# Run from the folder this file lives in, so it works wherever the project
# is kept — Desktop, Documents, an external drive.
cd "$(dirname "$0")" || exit 1

clear 2>/dev/null
echo "==========================================================="
echo "   Dynamic Documentary Engine"
echo "   Penn State University, College of IST"
echo "==========================================================="
echo ""

# --- Python ---------------------------------------------------------------

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
else
  echo "  Python is not installed yet."
  echo ""
  echo "  To install it:"
  echo "    1. Go to  https://www.python.org/downloads/"
  echo "    2. Click the big yellow 'Download Python' button"
  echo "    3. Open the file it downloads and click through the installer"
  echo "    4. Double-click this Start Engine file again"
  echo ""
  echo "  Press any key to close this window."
  read -n 1 -s
  exit 1
fi

echo "  Python ....... found"

# --- FFmpeg ---------------------------------------------------------------

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "  FFmpeg ....... NOT FOUND"
  echo ""
  echo "  FFmpeg is the tool that assembles the video. Without it the"
  echo "  engine can choose the clips but cannot build the film."
  echo ""
  echo "  To install it, copy the line below, paste it into this window,"
  echo "  and press Return:"
  echo ""
  echo "      /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\" && brew install ffmpeg"
  echo ""
  echo "  That installs Homebrew (a software installer for Macs) and then"
  echo "  FFmpeg. It takes a few minutes and will ask for your password."
  echo "  When it finishes, double-click Start Engine again."
  echo ""
  echo "  Press any key to close this window."
  read -n 1 -s
  exit 1
fi

echo "  FFmpeg ....... found"

# --- Python packages ------------------------------------------------------

# Checked rather than installed every time, so a normal start stays quick
# and works with no internet connection.
if ! $PYTHON -c "import flask, PIL, jsonschema" >/dev/null 2>&1; then
  echo "  Add-ons ...... installing (first run only, takes a minute)"
  if ! $PYTHON -m pip install --quiet --user -r requirements.txt 2>/dev/null; then
    $PYTHON -m pip install --quiet -r requirements.txt
  fi
  if ! $PYTHON -c "import flask, PIL, jsonschema" >/dev/null 2>&1; then
    echo ""
    echo "  Those add-ons could not be installed automatically."
    echo "  Check you are connected to the internet and try again, or"
    echo "  send this window to David."
    echo ""
    echo "  Press any key to close this window."
    read -n 1 -s
    exit 1
  fi
else
  echo "  Add-ons ...... found"
fi

echo ""
echo "  Starting up. Your browser will open in a moment."
echo "  Leave this window open while you use the engine."
echo ""

$PYTHON web/backend/app.py

# Only reached if the engine stops or fails to start.
echo ""
echo "  The engine has stopped."
echo "  Press any key to close this window."
read -n 1 -s
