"""
Audio Recorder Server
=====================
PC 마이크 / 시스템 사운드를 녹음하여 MP3로 저장하는 로컬 HTTP 서버.
웹앱에서 fetch() 호출로 녹음 시작/중지/상태조회가 가능하다.

사용법:
    python recorder_server.py [--port 8090] [--output-dir ./recordings]

API:
    POST /record/start   {"source", "filename", "mode", "silence_threshold", "silence_duration"}
    POST /record/stop    → {"file"|"files", "duration", "size_kb"}
    GET  /record/status  → {"recording", "source", "elapsed", "mode", "segment_count", "auto_state"}
"""

import sys
import time
import threading
import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import numpy as np

try:
    import sounddevice as sd
except ImportError:
    print("[ERROR] sounddevice 패키지가 필요합니다: pip install sounddevice")
    sys.exit(1)

try:
    import lameenc
except ImportError:
    print("[ERROR] lameenc 패키지가 필요합니다: pip install lameenc")
    sys.exit(1)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

# ── 로깅 ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("recorder")

# ── 요청/응답 모델 ────────────────────────────────────
class StartRequest(BaseModel):
    source: str = "mic"                          # "mic" | "system" | "both"
    filename: Optional[str] = None               # 저장 파일명 (확장자 제외)
    mode: str = "manual"                         # "manual" (기존) | "auto" (무음 자동 분할)
    silence_threshold: Optional[float] = None    # 무음 기준 RMS (기본 50)
    silence_duration: Optional[float] = None     # 무음 지속 시간(초) (기본 1.0)

class StopResponse(BaseModel):
    file: str                                    # manual: 파일 경로 / auto: 마지막 파일 경로 (없으면 "")
    files: List[str] = []                        # auto: 전체 저장 파일 목록
    duration: float
    size_kb: float

class StatusResponse(BaseModel):
    recording: bool
    source: Optional[str] = None
    elapsed: Optional[float] = None
    mode: Optional[str] = None                   # "manual" | "auto"
    segment_count: Optional[int] = None          # auto: 저장된 파일 수
    auto_state: Optional[str] = None             # auto: "waiting" | "recording"

class OutputDirRequest(BaseModel):
    output_dir: str                              # 새 저장 경로 (절대 경로)


# ── 디바이스 탐색 ─────────────────────────────────────

HOST_API_PRIORITY = {
    "mme": 0,
    "directsound": 1,
    "windows directsound": 1,
    "wasapi": 2,
    "windows wasapi": 2,
}

LOOPBACK_KEYWORDS = ["stereo mix", "스테레오 믹스", "loopback", "what u hear", "wave out"]


def _get_hostapi_priority(hostapi_name: str) -> int:
    name_lower = hostapi_name.lower()
    for key, pri in HOST_API_PRIORITY.items():
        if key in name_lower:
            return pri
    return 999


def _test_device(device_index: int, channels: int, samplerate: int) -> bool:
    try:
        stream = sd.InputStream(
            device=device_index, samplerate=samplerate,
            channels=channels, dtype="int16", blocksize=1024,
        )
        stream.start()
        time.sleep(0.15)
        stream.stop()
        stream.close()
        return True
    except Exception as e:
        log.debug(f"    테스트 실패 [{device_index}]: {e}")
        return False


def find_device(keywords: list[str] = None, kind: str = "input") -> dict | None:
    devices = sd.query_devices()
    hostapis = sd.query_hostapis()

    default_name = None
    if not keywords:
        try:
            default_dev = sd.query_devices(kind=kind)
            default_name = default_dev["name"].lower().strip()
        except Exception:
            return None

    candidates = []

    for i, dev in enumerate(devices):
        if dev["max_input_channels"] <= 0:
            continue

        name_lower = dev["name"].lower().strip()
        api_name = hostapis[dev["hostapi"]]["name"]
        priority = _get_hostapi_priority(api_name)

        if priority >= 999:
            continue

        if keywords:
            if not any(kw in name_lower for kw in keywords):
                continue
        else:
            if default_name and default_name not in name_lower and name_lower not in default_name:
                default_words = set(default_name.replace("(", " ").replace(")", " ").split())
                dev_words = set(name_lower.replace("(", " ").replace(")", " ").split())
                common = default_words & dev_words
                common -= {"", "-", "input", "output", "windows"}
                if len(common) < 2:
                    continue

        channels = min(dev["max_input_channels"], 2)
        samplerate = int(dev["default_samplerate"])

        candidates.append({
            "index": i, "name": dev["name"], "channels": channels,
            "samplerate": samplerate, "api": api_name, "priority": priority,
        })

    if not candidates:
        return None

    candidates.sort(key=lambda c: c["priority"])

    log.info(f"  후보 {len(candidates)}개:")
    for c in candidates:
        log.info(f"    [{c['index']}] {c['name']} | {c['api']} | {c['channels']}ch | {c['samplerate']}Hz")

    for c in candidates:
        log.info(f"  테스트: [{c['index']}] {c['name']} ({c['api']})...")
        if _test_device(c["index"], c["channels"], c["samplerate"]):
            log.info(f"  ✓ 선택: [{c['index']}] {c['name']} ({c['api']}, {c['channels']}ch, {c['samplerate']}Hz)")
            return {
                "index": c["index"], "name": c["name"], "channels": c["channels"],
                "samplerate": c["samplerate"], "api": c["api"],
            }
        log.warning(f"  ✗ 실패: [{c['index']}] {c['name']} ({c['api']})")

    return None


# ── 레코더 클래스 ─────────────────────────────────────
class AudioRecorder:
    """마이크/시스템 사운드를 녹음하여 MP3로 저장한다."""

    OUTPUT_SAMPLE_RATE = 44100
    CHANNELS = 2
    DTYPE = "int16"
    BLOCKSIZE = 1024

    # auto 모드 기본값
    DEFAULT_SILENCE_THRESHOLD = 50   # int16 RMS 기준 (0~32767). 50 ≈ 거의 무음
    DEFAULT_SILENCE_DURATION = 1.0   # 초

    def __init__(self, output_dir: str = "./recordings"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.recording = False
        self.source = None
        self.start_time = None
        self.lock = threading.Lock()

        self._buffers_mic = []
        self._buffers_sys = []
        self._streams = []
        self._custom_filename = None

        # ── auto 모드 전용 ──
        self._mode = "manual"
        self._silence_threshold = self.DEFAULT_SILENCE_THRESHOLD
        self._silence_duration = self.DEFAULT_SILENCE_DURATION
        self._auto_state = None          # "waiting" | "recording"
        self._auto_segment_count = 0
        self._auto_saved_files = []
        self._auto_segment_start = None  # 현재 세그먼트 녹음 시작 시각
        self._silence_start = None       # 무음 시작 시각
        self._current_rms = 0.0
        self._monitor_thread = None
        self._stop_event = threading.Event()

        # 디바이스 탐색
        log.info("=" * 50)
        log.info("마이크 디바이스 탐색")
        log.info("-" * 50)
        self.mic_info = find_device(keywords=None, kind="input")

        log.info("-" * 50)
        log.info("루프백 디바이스 탐색")
        log.info("-" * 50)
        self.loopback_info = find_device(keywords=LOOPBACK_KEYWORDS)
        log.info("=" * 50)

        log.info(f"출력 디렉토리: {self.output_dir.resolve()}")
        if self.mic_info:
            m = self.mic_info
            log.info(f"마이크 → [{m['index']}] {m['name']} ({m['api']}, {m['channels']}ch, {m['samplerate']}Hz)")
        else:
            log.warning("마이크 → 없음")
        if self.loopback_info:
            s = self.loopback_info
            log.info(f"루프백 → [{s['index']}] {s['name']} ({s['api']}, {s['channels']}ch, {s['samplerate']}Hz)")
        else:
            log.warning("루프백 → 없음 (스테레오 믹스를 활성화하세요)")

    # ── 유틸 ──
    @staticmethod
    def _to_stereo(data: np.ndarray) -> np.ndarray:
        if data.ndim == 1:
            return np.column_stack([data, data])
        if data.shape[1] == 1:
            return np.column_stack([data[:, 0], data[:, 0]])
        return data

    @staticmethod
    def _resample(data: np.ndarray, orig_rate: int, target_rate: int) -> np.ndarray:
        if orig_rate == target_rate:
            return data
        ratio = target_rate / orig_rate
        orig_len = len(data)
        new_len = int(orig_len * ratio)
        indices = np.linspace(0, orig_len - 1, new_len)
        if data.ndim == 1:
            return np.interp(indices, np.arange(orig_len), data).astype(data.dtype)
        result = np.zeros((new_len, data.shape[1]), dtype=data.dtype)
        for ch in range(data.shape[1]):
            result[:, ch] = np.interp(
                indices, np.arange(orig_len), data[:, ch].astype(np.float64)
            ).astype(data.dtype)
        return result

    # ── 콜백 (음량 측정 추가) ──
    def _mic_callback(self, indata, frames, time_info, status):
        if status:
            log.debug(f"mic status: {status}")
        self._buffers_mic.append(indata.copy())
        # auto 모드: RMS 갱신
        if self._mode == "auto":
            rms = np.sqrt(np.mean(indata.astype(np.float32) ** 2))
            self._current_rms = max(self._current_rms, rms)

    def _sys_callback(self, indata, frames, time_info, status):
        if status:
            log.debug(f"sys status: {status}")
        self._buffers_sys.append(indata.copy())
        # auto 모드: RMS 갱신
        if self._mode == "auto":
            rms = np.sqrt(np.mean(indata.astype(np.float32) ** 2))
            self._current_rms = max(self._current_rms, rms)

    # ── 시작 ──
    def start(self, source: str = "mic", filename: str = None,
              mode: str = "manual", silence_threshold: float = None,
              silence_duration: float = None) -> dict:
        with self.lock:
            if self.recording:
                raise RuntimeError("이미 녹음 중입니다.")

            source = source.lower().strip()
            if source not in ("mic", "system", "both"):
                raise ValueError(f"잘못된 source: {source}. mic|system|both 중 선택.")

            mode = mode.lower().strip()
            if mode not in ("manual", "auto"):
                raise ValueError(f"잘못된 mode: {mode}. manual|auto 중 선택.")

            if source in ("system", "both") and self.loopback_info is None:
                raise RuntimeError(
                    "시스템 사운드 캡처용 루프백 디바이스를 찾을 수 없습니다. "
                    "Windows 사운드 설정에서 '스테레오 믹스'를 활성화하세요."
                )

            if source in ("mic", "both") and self.mic_info is None:
                raise RuntimeError("마이크 디바이스를 찾을 수 없습니다.")

            # 초기화
            self._buffers_mic.clear()
            self._buffers_sys.clear()
            self._streams.clear()
            self.source = source
            self._custom_filename = filename
            self._mode = mode
            self._silence_threshold = silence_threshold or self.DEFAULT_SILENCE_THRESHOLD
            self._silence_duration = silence_duration or self.DEFAULT_SILENCE_DURATION

            # auto 모드 상태 초기화
            self._auto_state = "waiting" if mode == "auto" else None
            self._auto_segment_count = 0
            self._auto_saved_files = []
            self._auto_segment_start = None
            self._silence_start = None
            self._current_rms = 0.0
            self._stop_event.clear()

            try:
                if source in ("mic", "both"):
                    m = self.mic_info
                    mic_stream = sd.InputStream(
                        device=m["index"], samplerate=m["samplerate"],
                        channels=m["channels"], dtype=self.DTYPE,
                        blocksize=self.BLOCKSIZE, callback=self._mic_callback,
                    )
                    self._streams.append(mic_stream)

                if source in ("system", "both"):
                    s = self.loopback_info
                    sys_stream = sd.InputStream(
                        device=s["index"], samplerate=s["samplerate"],
                        channels=s["channels"], dtype=self.DTYPE,
                        blocksize=self.BLOCKSIZE, callback=self._sys_callback,
                    )
                    self._streams.append(sys_stream)

                for st in self._streams:
                    st.start()

                self.recording = True
                self.start_time = time.time()

                # auto 모드: 모니터 스레드 시작
                if mode == "auto":
                    self._monitor_thread = threading.Thread(
                        target=self._auto_monitor_loop, daemon=True
                    )
                    self._monitor_thread.start()
                    log.info(f"녹음 시작 [AUTO]: source={source}, "
                             f"threshold={self._silence_threshold}, "
                             f"silence={self._silence_duration}초")
                else:
                    log.info(f"녹음 시작 [MANUAL]: source={source}")

                return {"recording": True, "source": source, "mode": mode}

            except Exception as e:
                for st in self._streams:
                    try:
                        st.close()
                    except Exception:
                        pass
                self._streams.clear()
                raise RuntimeError(f"스트림 시작 실패: {e}")

    # ── auto 모드 모니터 루프 ──
    def _auto_monitor_loop(self):
        """별도 스레드에서 실행. 음량을 감시하여 자동 분할 녹음을 수행한다."""
        POLL_INTERVAL = 0.1  # 100ms 간격 체크

        while not self._stop_event.is_set():
            time.sleep(POLL_INTERVAL)

            rms = self._current_rms
            self._current_rms = 0.0  # 리셋 (다음 주기용)
            is_sound = rms >= self._silence_threshold

            if self._auto_state == "waiting":
                # 소리 감지 → 녹음 시작
                if is_sound:
                    self._auto_state = "recording"
                    self._auto_segment_start = time.time()
                    self._silence_start = None
                    # 버퍼 비우기 (이전 무음 데이터 제거)
                    self._buffers_mic.clear()
                    self._buffers_sys.clear()
                    log.info(f"[AUTO] 소리 감지 → 세그먼트 {self._auto_segment_count + 1} 녹음 시작 (RMS={rms:.0f})")

            elif self._auto_state == "recording":
                if is_sound:
                    # 소리 있음 → 무음 타이머 리셋
                    self._silence_start = None
                else:
                    # 무음 시작 또는 계속
                    if self._silence_start is None:
                        self._silence_start = time.time()
                    elif time.time() - self._silence_start >= self._silence_duration:
                        # 무음 지속 → 세그먼트 저장
                        self._save_auto_segment()
                        self._auto_state = "waiting"
                        self._silence_start = None

        log.debug("[AUTO] 모니터 루프 종료")

    # ── auto 세그먼트 저장 ──
    def _save_auto_segment(self):
        """현재 버퍼를 MP3로 저장하고 버퍼를 비운다."""
        if not self._buffers_mic and not self._buffers_sys:
            log.debug("[AUTO] 저장할 데이터 없음, 스킵")
            return

        elapsed = time.time() - self._auto_segment_start if self._auto_segment_start else 0
        duration_sec = int(elapsed)

        if duration_sec < 1:
            # 1초 미만은 노이즈로 간주, 버리기
            self._buffers_mic.clear()
            self._buffers_sys.clear()
            log.debug(f"[AUTO] {duration_sec}초 미만 세그먼트 무시")
            return

        audio = self._merge_audio()
        self._buffers_mic.clear()
        self._buffers_sys.clear()

        if audio is None or len(audio) == 0:
            return

        self._auto_segment_count += 1

        if self._custom_filename:
            base = self._custom_filename.replace(".mp3", "").replace(".MP3", "")
            filename = f"{base}_{self._auto_segment_count:03d}_{duration_sec}.mp3"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"rec_{timestamp}_{self.source}_{self._auto_segment_count:03d}_{duration_sec}.mp3"

        filepath = self.output_dir / filename
        self._encode_mp3(audio, filepath)

        size_kb = filepath.stat().st_size / 1024
        file_str = str(filepath.resolve())
        self._auto_saved_files.append(file_str)

        log.info(f"[AUTO] 세그먼트 {self._auto_segment_count} 저장: {filename} ({duration_sec}초, {size_kb:.1f}KB)")

    # ── 중지 ──
    def stop(self) -> dict:
        with self.lock:
            if not self.recording:
                raise RuntimeError("녹음 중이 아닙니다.")

            elapsed = time.time() - self.start_time
            mode = self._mode

            # auto 모드: 모니터 스레드 종료
            if mode == "auto":
                self._stop_event.set()
                # lock 밖에서 join해야 하므로 스레드 참조 보관
                monitor = self._monitor_thread
            else:
                monitor = None

            # 스트림 중지
            for st in self._streams:
                try:
                    st.stop()
                    st.close()
                except Exception:
                    pass
            self._streams.clear()
            self.recording = False

        # lock 밖에서 모니터 스레드 종료 대기
        if monitor and monitor.is_alive():
            monitor.join(timeout=2.0)

        log.info(f"녹음 중지 [{mode.upper()}]: 총 {elapsed:.1f}초")

        if mode == "auto":
            # 마지막 세그먼트가 녹음 중이었으면 저장
            if self._auto_state == "recording":
                self._save_auto_segment()

            files = self._auto_saved_files.copy()
            total_size = sum(
                Path(f).stat().st_size / 1024 for f in files if Path(f).exists()
            )

            log.info(f"[AUTO] 전체 {len(files)}개 파일, 총 {total_size:.1f}KB")

            return {
                "file": files[-1] if files else "",
                "files": files,
                "duration": round(elapsed, 2),
                "size_kb": round(total_size, 2),
            }

        else:
            # manual 모드: 기존 동작
            audio = self._merge_audio()
            if audio is None or len(audio) == 0:
                raise RuntimeError("녹음된 데이터가 없습니다.")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            duration_sec = int(elapsed)

            if self._custom_filename:
                base = self._custom_filename.replace(".mp3", "").replace(".MP3", "")
                filename = f"{base}_{duration_sec}.mp3"
            else:
                filename = f"rec_{timestamp}_{self.source}_{duration_sec}.mp3"

            filepath = self.output_dir / filename
            self._encode_mp3(audio, filepath)

            size_kb = filepath.stat().st_size / 1024
            log.info(f"저장 완료: {filepath} ({size_kb:.1f} KB)")

            return {
                "file": str(filepath.resolve()),
                "files": [str(filepath.resolve())],
                "duration": round(elapsed, 2),
                "size_kb": round(size_kb, 2),
            }

    # ── 오디오 병합 ──
    def _merge_audio(self) -> np.ndarray:
        mic_data = None
        sys_data = None

        if self._buffers_mic and self.mic_info:
            mic_data = np.concatenate(self._buffers_mic, axis=0)
            mic_data = self._to_stereo(mic_data)
            mic_data = self._resample(mic_data, self.mic_info["samplerate"], self.OUTPUT_SAMPLE_RATE)

        if self._buffers_sys and self.loopback_info:
            sys_data = np.concatenate(self._buffers_sys, axis=0)
            sys_data = self._to_stereo(sys_data)
            sys_data = self._resample(sys_data, self.loopback_info["samplerate"], self.OUTPUT_SAMPLE_RATE)

        if mic_data is not None and sys_data is not None:
            max_len = max(len(mic_data), len(sys_data))
            if len(mic_data) < max_len:
                pad = np.zeros((max_len - len(mic_data), self.CHANNELS), dtype=np.int16)
                mic_data = np.concatenate([mic_data, pad], axis=0)
            if len(sys_data) < max_len:
                pad = np.zeros((max_len - len(sys_data), self.CHANNELS), dtype=np.int16)
                sys_data = np.concatenate([sys_data, pad], axis=0)

            mixed = mic_data.astype(np.int32) + sys_data.astype(np.int32)
            return np.clip(mixed, -32768, 32767).astype(np.int16)

        return mic_data if mic_data is not None else sys_data

    # ── MP3 인코딩 ──
    def _encode_mp3(self, audio: np.ndarray, filepath: Path):
        encoder = lameenc.Encoder()
        encoder.set_bit_rate(192)
        encoder.set_in_sample_rate(self.OUTPUT_SAMPLE_RATE)
        encoder.set_channels(self.CHANNELS)
        encoder.set_quality(2)

        mp3_data = encoder.encode(audio.tobytes())
        mp3_data += encoder.flush()

        with open(filepath, "wb") as f:
            f.write(mp3_data)

    # ── 상태 ──
    def status(self) -> dict:
        if self.recording:
            result = {
                "recording": True,
                "source": self.source,
                "elapsed": round(time.time() - self.start_time, 2),
                "mode": self._mode,
            }
            if self._mode == "auto":
                result["segment_count"] = self._auto_segment_count
                result["auto_state"] = self._auto_state
            return result
        return {"recording": False, "source": None, "elapsed": None, "mode": None}

    # ── 디바이스 목록 ──
    def list_devices(self) -> list:
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        result = []
        for i, dev in enumerate(devices):
            result.append({
                "index": i,
                "name": dev["name"],
                "hostapi": hostapis[dev["hostapi"]]["name"],
                "max_input_channels": dev["max_input_channels"],
                "max_output_channels": dev["max_output_channels"],
                "default_samplerate": dev["default_samplerate"],
            })
        return result


# ── FastAPI 앱 ────────────────────────────────────────
app = FastAPI(title="Audio Recorder", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

recorder: AudioRecorder = None


@app.post("/record/start")
def record_start(req: StartRequest):
    """녹음을 시작한다."""
    try:
        result = recorder.start(
            source=req.source,
            filename=req.filename,
            mode=req.mode,
            silence_threshold=req.silence_threshold,
            silence_duration=req.silence_duration,
        )
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/record/stop")
def record_stop():
    """녹음을 중지하고 MP3 파일을 저장한다."""
    try:
        result = recorder.stop()
        return StopResponse(**result)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/record/status")
def record_status():
    """현재 녹음 상태를 반환한다."""
    return recorder.status()


@app.get("/devices")
def list_devices():
    """사용 가능한 오디오 디바이스 목록 (호스트 API 포함)."""
    return recorder.list_devices()


@app.get("/download/{filename}")
def download_file(filename: str):
    """녹음된 MP3 파일을 다운로드한다."""
    filepath = recorder.output_dir / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return FileResponse(path=str(filepath), media_type="audio/mpeg", filename=filename)


@app.get("/config/output-dir")
def get_output_dir():
    """현재 녹음 파일 저장 경로를 반환한다."""
    return {"output_dir": str(recorder.output_dir.resolve())}


@app.post("/config/output-dir")
def set_output_dir(req: OutputDirRequest):
    """녹음 파일 저장 경로를 변경한다."""
    if recorder.recording:
        raise HTTPException(status_code=409, detail="녹음 중에는 저장 경로를 변경할 수 없습니다.")
    try:
        new_path = Path(req.output_dir)
        new_path.mkdir(parents=True, exist_ok=True)
        recorder.output_dir = new_path
        log.info(f"저장 경로 변경: {new_path.resolve()}")
        return {"output_dir": str(new_path.resolve())}
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"잘못된 경로입니다: {e}")


@app.get("/health")
def health():
    """서버 상태 확인."""
    return {
        "status": "ok",
        "mic": recorder.mic_info is not None,
        "loopback": recorder.loopback_info is not None,
        "mic_detail": recorder.mic_info,
        "loopback_detail": recorder.loopback_info,
        "output_dir": str(recorder.output_dir.resolve()),
    }


# ── 메인 ──────────────────────────────────────────────
def _get_base_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def main():
    base_dir = _get_base_dir()
    crash_log = base_dir / "recorder_crash.log"

    try:
        parser = argparse.ArgumentParser(description="Audio Recorder Server")
        parser.add_argument("--port", type=int, default=8090, help="서버 포트 (기본: 8090)")
        parser.add_argument("--output-dir", type=str, default=str(base_dir / "recordings"),
                            help="녹음 파일 저장 경로")
        parser.add_argument("--host", type=str, default="127.0.0.1", help="바인드 주소 (기본: 127.0.0.1)")
        args = parser.parse_args()

        global recorder
        recorder = AudioRecorder(output_dir=args.output_dir)

        log.info(f"서버 시작: http://{args.host}:{args.port}")
        log.info(f"API 문서: http://{args.host}:{args.port}/docs")

        uvicorn.run(app, host=args.host, port=args.port, log_level="info")

    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        log.error(f"서버 시작 실패:\n{error_msg}")
        with open(crash_log, "w", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] 서버 시작 실패\n\n{error_msg}\n")
        print(f"\n[ERROR] 서버 시작 실패. 상세 로그: {crash_log}")
        print(f"\n{error_msg}")
        input("엔터를 누르면 종료합니다...")
        sys.exit(1)


if __name__ == "__main__":
    main()
