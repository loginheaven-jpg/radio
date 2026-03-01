@echo off
chcp 65001 >nul
echo ============================================================
echo  Audio Recorder - 시작프로그램 등록/해제
echo ============================================================
echo.
echo  1. 시작프로그램에 등록
echo  2. 시작프로그램에서 해제
echo  3. 취소
echo.
set /p choice="선택 (1/2/3): "

if "%choice%"=="1" goto REGISTER
if "%choice%"=="2" goto UNREGISTER
goto END

:REGISTER
set EXE_PATH=%~dp0dist\AudioRecorder.exe
if not exist "%EXE_PATH%" (
    echo.
    echo [ERROR] %EXE_PATH% 파일이 없습니다.
    echo         먼저 python build_exe.py 로 빌드하세요.
    goto END
)

REM 시작프로그램 폴더에 바로가기 생성
set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set SHORTCUT=%STARTUP_DIR%\AudioRecorder.lnk

REM PowerShell로 바로가기 생성 (인자 포함)
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT%'); $sc.TargetPath = '%EXE_PATH%'; $sc.Arguments = '--port 8090 --output-dir \"%USERPROFILE%\recordings\"'; $sc.WorkingDirectory = '%~dp0'; $sc.Description = 'Audio Recorder Server'; $sc.Save()"

if exist "%SHORTCUT%" (
    echo.
    echo [OK] 시작프로그램에 등록 완료
    echo      경로: %SHORTCUT%
    echo      녹음 저장: %USERPROFILE%\recordings
    echo.
    echo      다음 윈도우 시작 시 자동 실행됩니다.
) else (
    echo.
    echo [ERROR] 등록 실패
)
goto END

:UNREGISTER
set SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AudioRecorder.lnk
if exist "%SHORTCUT%" (
    del "%SHORTCUT%"
    echo.
    echo [OK] 시작프로그램에서 해제 완료
) else (
    echo.
    echo [!] 등록된 항목이 없습니다.
)
goto END

:END
echo.
pause
