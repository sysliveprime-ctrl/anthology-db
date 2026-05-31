@echo off
setlocal
cd /d "%~dp0"
py -3 anthology_publish_wizard.py %*
if errorlevel 1 (
  echo.
  echo Publish failed. Check the error above.
  pause
)
