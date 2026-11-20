@echo off
rem Double-click to start CreatorKit (interactive menu)
chcp 65001 >nul
title CreatorKit
"%~dp0..\.venv\Scripts\ck.exe"
echo.
pause
