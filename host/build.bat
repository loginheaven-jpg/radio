@echo off
echo === 봄소리 라이브 호스트 빌드 ===
echo.
echo 1. PyInstaller 설치 확인...
pip install pyinstaller >nul 2>&1

echo 2. 빌드 시작...
pyinstaller --onefile --noconsole --name "봄소리호스트" ^
  --add-data "config.py;." ^
  host.py

echo.
echo 빌드 완료: dist\봄소리호스트.exe
pause
