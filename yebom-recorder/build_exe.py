"""
Audio Recorder Server → EXE 빌드 스크립트
=========================================
PyInstaller로 단일 실행파일(exe)을 생성한다.

사용법:
    pip install pyinstaller
    python build_exe.py
"""

import subprocess
import sys
import shutil
from pathlib import Path


def ensure_package(name, pip_name=None):
    """패키지 존재 확인, 없으면 설치."""
    try:
        __import__(name)
        print(f"  [OK] {name}")
        return True
    except ImportError:
        install_name = pip_name or name
        print(f"  [설치] {install_name}...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", install_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True


def main():
    print("=" * 60)
    print(" Audio Recorder → EXE 빌드")
    print("=" * 60)

    # ── 1. 의존 패키지 확인 ──
    print("\n[1/3] 패키지 확인")
    ensure_package("PyInstaller", "pyinstaller")
    ensure_package("sounddevice")
    ensure_package("numpy")
    ensure_package("lameenc")
    ensure_package("fastapi")
    ensure_package("uvicorn")
    ensure_package("pydantic")

    # ── 2. 소스 파일 확인 ──
    script_dir = Path(__file__).parent
    main_script = script_dir / "recorder_server.py"

    if not main_script.exists():
        print(f"\n[ERROR] {main_script} 를 찾을 수 없습니다.")
        sys.exit(1)

    # 이전 빌드 정리
    for d in ["build", "dist"]:
        p = script_dir / d
        if p.exists():
            shutil.rmtree(p)
    spec = script_dir / "AudioRecorder.spec"
    if spec.exists():
        spec.unlink()

    # ── 3. PyInstaller 실행 ──
    print("\n[2/3] 빌드 중... (1~2분 소요)")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--name", "AudioRecorder",
        "--clean",

        # ── sounddevice: PortAudio DLL 포함 (핵심) ──
        "--collect-all", "sounddevice",

        # ── uvicorn: 내부 모듈 전부 수집 (누락 시 EXE 즉시 크래시) ──
        "--collect-all", "uvicorn",

        # ── fastapi/starlette ──
        "--collect-all", "fastapi",
        "--collect-all", "starlette",

        # ── lameenc: C 확장 ──
        "--hidden-import", "lameenc",

        # ── pydantic: 컴파일 확장 ──
        "--collect-all", "pydantic",
        "--collect-all", "pydantic_core",

        # ── 기타 런타임 의존성 ──
        "--hidden-import", "anyio",
        "--hidden-import", "anyio._backends",
        "--hidden-import", "anyio._backends._asyncio",
        "--hidden-import", "sniffio",
        "--hidden-import", "h11",
        "--hidden-import", "httptools",
        "--hidden-import", "dotenv",
        "--hidden-import", "yaml",
        "--hidden-import", "email_validator",
        "--hidden-import", "multipart",
        "--hidden-import", "multipart.multipart",

        # ── numpy ──
        "--hidden-import", "numpy",
        "--hidden-import", "numpy.core",

        # ── 불필요 모듈 제외 (크기 축소) ──
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        "--exclude-module", "scipy",
        "--exclude-module", "PIL",
        "--exclude-module", "cv2",
        "--exclude-module", "torch",
        "--exclude-module", "tensorflow",
        "--exclude-module", "pandas",
        "--exclude-module", "pytest",
        "--exclude-module", "setuptools",
        "--exclude-module", "pip",

        str(main_script),
    ]

    result = subprocess.run(cmd, cwd=str(script_dir))

    if result.returncode != 0:
        print("\n[ERROR] 빌드 실패. 위 로그를 확인하세요.")
        sys.exit(1)

    # ── 4. 결과 확인 ──
    print("\n[3/3] 결과 확인")
    exe_path = script_dir / "dist" / "AudioRecorder.exe"

    if not exe_path.exists():
        print("[ERROR] EXE 파일이 생성되지 않았습니다.")
        sys.exit(1)

    size_mb = exe_path.stat().st_size / (1024 * 1024)

    print()
    print("=" * 60)
    print(f" 빌드 완료!")
    print(f" 파일: {exe_path.resolve()}")
    print(f" 크기: {size_mb:.1f} MB")
    print("=" * 60)
    print()
    print(" 실행 테스트:")
    print(f"   {exe_path.resolve()}")
    print()
    print(" 시작프로그램 등록:")
    print("   register_startup.bat 실행 → 1 선택")
    print()


if __name__ == "__main__":
    main()
