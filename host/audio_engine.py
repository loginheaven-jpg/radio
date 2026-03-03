"""
봄소리 라이브 호스트 — 오디오 캡처·믹싱 엔진
FFmpeg를 사용하여 마이크 + PC사운드(스테레오믹스)를 믹싱하고
Opus/OGG 청크를 생성한다.
"""

import subprocess
import threading
import io
import time
import struct

from config import FFMPEG_PATH, CHUNK_DURATION, SAMPLE_RATE, CHANNELS, BITRATE, FORMAT


def list_audio_devices():
    """Windows DirectShow 오디오 입력 장치 목록 반환"""
    try:
        result = subprocess.run(
            [FFMPEG_PATH, "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace"
        )
        output = result.stderr
        devices = []
        for line in output.split("\n"):
            # 최신 FFmpeg: "장치명" (audio) 형식
            if "(audio)" in line and '"' in line and "Alternative name" not in line:
                name = line.split('"')[1]
                if name:
                    devices.append(name)
        return devices
    except Exception as e:
        print(f"장치 목록 오류: {e}")
        return []


class AudioEngine:
    """FFmpeg 기반 오디오 캡처·믹싱·인코딩"""

    def __init__(self, mic_device=None, system_device=None,
                 mic_volume=1.0, system_volume=1.0,
                 on_chunk=None, on_error=None):
        self.mic_device = mic_device
        self.system_device = system_device
        self.mic_volume = mic_volume
        self.system_volume = system_volume
        self.on_chunk = on_chunk  # callback(chunk_bytes, chunk_index)
        self.on_error = on_error  # callback(error_message)
        self._process = None
        self._thread = None
        self._running = False
        self._chunk_index = 0

    def start(self):
        """FFmpeg 프로세스 시작"""
        if self._running:
            return

        cmd = [FFMPEG_PATH, "-y"]

        # 입력 소스
        inputs = []
        filter_parts = []

        if self.mic_device:
            cmd += ["-f", "dshow", "-i", f"audio={self.mic_device}"]
            inputs.append(len(inputs))
            filter_parts.append(f"[{len(inputs)-1}:a]volume={self.mic_volume}[mic]")

        if self.system_device:
            cmd += ["-f", "dshow", "-i", f"audio={self.system_device}"]
            inputs.append(len(inputs))
            filter_parts.append(f"[{len(inputs)-1}:a]volume={self.system_volume}[sys]")

        if not inputs:
            if self.on_error:
                self.on_error("오디오 입력이 선택되지 않았습니다")
            return

        # 필터: 믹싱
        if len(inputs) == 2:
            filter_str = ";".join(filter_parts) + f";[mic][sys]amix=inputs=2:duration=longest[out]"
            cmd += ["-filter_complex", filter_str, "-map", "[out]"]
        elif self.mic_device:
            cmd += ["-filter_complex", filter_parts[0].replace("[mic]", "[out]"), "-map", "[out]"]
        else:
            cmd += ["-filter_complex", filter_parts[0].replace("[sys]", "[out]"), "-map", "[out]"]

        # 출력: Opus/OGG 청크 → stdout
        cmd += [
            "-c:a", "libopus",
            "-b:a", BITRATE,
            "-ar", str(SAMPLE_RATE),
            "-ac", str(CHANNELS),
            "-f", "segment",
            "-segment_time", str(CHUNK_DURATION),
            "-segment_format", FORMAT,
            "-reset_timestamps", "1",
            "pipe:chunk_%08d.ogg"
        ]

        # 실제로는 segment를 파일로 쓰는 대신 pipe를 사용하기 어려우므로
        # temp 디렉토리에 세그먼트를 쓰고 감시하는 방식 사용
        import tempfile
        import os
        self._tmpdir = tempfile.mkdtemp(prefix="bomsori_")

        # segment를 tmpdir에 출력
        cmd_final = cmd[:-1] + [os.path.join(self._tmpdir, "chunk_%08d.ogg")]

        self._running = True
        self._chunk_index = 0

        try:
            self._process = subprocess.Popen(
                cmd_final,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
        except FileNotFoundError:
            self._running = False
            if self.on_error:
                self.on_error("FFmpeg를 찾을 수 없습니다. PATH를 확인하세요.")
            return
        except Exception as e:
            self._running = False
            if self.on_error:
                self.on_error(f"FFmpeg 시작 실패: {e}")
            return

        self._thread = threading.Thread(target=self._watch_chunks, daemon=True)
        self._thread.start()

        # stderr 모니터링 (에러 감지)
        self._err_thread = threading.Thread(target=self._watch_stderr, daemon=True)
        self._err_thread.start()

    def _watch_chunks(self):
        """tmpdir에서 새 청크 파일이 생성되면 콜백 호출"""
        import os
        expected_idx = 0
        while self._running:
            chunk_path = os.path.join(self._tmpdir, f"chunk_{expected_idx:08d}.ogg")
            # 다음 청크가 존재하면 현재 청크가 완성된 것
            next_path = os.path.join(self._tmpdir, f"chunk_{expected_idx+1:08d}.ogg")

            if os.path.exists(next_path):
                # 현재 청크 읽고 전달
                try:
                    with open(chunk_path, "rb") as f:
                        data = f.read()
                    if data and self.on_chunk:
                        self.on_chunk(data, expected_idx)
                    # 읽은 파일 삭제
                    try:
                        os.remove(chunk_path)
                    except:
                        pass
                    expected_idx += 1
                    self._chunk_index = expected_idx
                except Exception as e:
                    if self.on_error:
                        self.on_error(f"청크 읽기 오류: {e}")
                    time.sleep(0.1)
            else:
                time.sleep(0.2)

        # 마지막 청크 처리
        chunk_path = os.path.join(self._tmpdir, f"chunk_{expected_idx:08d}.ogg")
        if os.path.exists(chunk_path):
            try:
                with open(chunk_path, "rb") as f:
                    data = f.read()
                if data and self.on_chunk:
                    self.on_chunk(data, expected_idx)
                os.remove(chunk_path)
            except:
                pass

        # tmpdir 정리
        self._cleanup_tmpdir()

    def _watch_stderr(self):
        """FFmpeg stderr 모니터링"""
        try:
            for line in self._process.stderr:
                text = line.decode("utf-8", errors="replace").strip()
                if "Error" in text or "error" in text:
                    if self.on_error:
                        self.on_error(text)
        except:
            pass

    def _cleanup_tmpdir(self):
        import os
        import shutil
        try:
            shutil.rmtree(self._tmpdir, ignore_errors=True)
        except:
            pass

    def stop(self):
        """FFmpeg 프로세스 종료"""
        self._running = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except:
                try:
                    self._process.kill()
                except:
                    pass
            self._process = None

    def update_volumes(self, mic_vol=None, sys_vol=None):
        """볼륨 업데이트 (다음 세션부터 적용)"""
        if mic_vol is not None:
            self.mic_volume = mic_vol
        if sys_vol is not None:
            self.system_volume = sys_vol

    @property
    def is_running(self):
        return self._running

    @property
    def chunk_index(self):
        return self._chunk_index
