@echo off
setlocal

echo ============================================================
echo  Yebom Radio Recorder - Build Script
echo  Server: FastAPI + sounddevice + lameenc
echo  Port: 8090
echo ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10 or later.
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/4] Installing dependencies...
pip install pyaudiowpatch sounddevice lameenc fastapi uvicorn numpy scipy pyinstaller --upgrade -q
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo       Done.
echo.

echo [2/4] Cleaning previous build...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
echo       Done.
echo.

echo [3/4] Building executable...
pyinstaller yebom_recorder.spec
if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)
echo       Done.
echo.

echo [4/4] Build complete!
echo.
echo Output: dist\yebom_recorder.exe
echo.
echo Usage:
echo   1. Run dist\yebom_recorder.exe  (rename as you wish)
echo   2. Open radio.yebom.org in Chrome
echo   3. Click the record button
echo.
echo The server listens on http://localhost:8090
echo Chrome allows http://localhost from HTTPS pages (no Mixed Content block)
echo.
pause
