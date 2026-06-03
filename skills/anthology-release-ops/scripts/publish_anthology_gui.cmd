@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
title Anthology Release Control GUI
cd /d "%~dp0"
py -3 anthology_release_control_gui.py
if errorlevel 1 (
  echo.
  echo GUI failed. Check the error above.
  pause
)
