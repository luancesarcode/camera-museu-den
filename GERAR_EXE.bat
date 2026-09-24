@echo off
setlocal
cd /d "%~dp0"

python -m PyInstaller --noconfirm --clean CameraMuseuDEN.spec

if errorlevel 1 (
  echo.
  echo Falha ao gerar o executavel.
  pause
  exit /b 1
)

echo.
echo Executavel criado em: %~dp0dist\CameraMuseuDEN.exe
pause
