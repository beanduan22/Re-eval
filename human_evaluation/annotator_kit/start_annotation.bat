@echo off
cd /d "%~dp0"
python annotate.py
if errorlevel 1 pause
