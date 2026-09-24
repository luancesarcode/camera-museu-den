@echo off
setlocal
cd /d "%~dp0"
python camera_museu.py
if errorlevel 1 pause

