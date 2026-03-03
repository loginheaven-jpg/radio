"""
봄소리 호스트 — Workers API 클라이언트
파일 업로드, 트랙 관리, CH5 상태 제어
"""

import os
import json
import subprocess
import requests

from config import UPLOAD_TIMEOUT, FFMPEG_PATH


def get_audio_duration(file_path):
    """ffprobe로 오디오 파일 재생시간(초) 반환"""
    try:
        ffprobe = FFMPEG_PATH.replace("ffmpeg", "ffprobe")
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", file_path],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception:
        return 0


class ApiClient:
    """Workers API 통신 (파일 방송 관리용)"""

    def __init__(self, worker_url, admin_key):
        self.worker_url = worker_url.rstrip("/")
        self.admin_key = admin_key

    def _headers_json(self):
        return {
            "Authorization": f"Bearer {self.admin_key}",
            "Content-Type": "application/json",
        }

    def _headers_auth(self):
        return {"Authorization": f"Bearer {self.admin_key}"}

    # ── 트랙 관리 ──────────────────────────────────────────────

    def get_tracks(self):
        """트랙 목록 조회 → list of {key, name, size, order}"""
        try:
            resp = requests.get(
                f"{self.worker_url}/api/tracks",
                params={"channel": "stream"},
                timeout=UPLOAD_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json().get("tracks", [])
        except Exception:
            pass
        return []

    def upload_file(self, file_path, display_name=None, on_progress=None):
        """파일 업로드 → {ok, uploaded} 또는 None"""
        if not display_name:
            display_name = os.path.splitext(os.path.basename(file_path))[0]

        try:
            file_size = os.path.getsize(file_path)
            with open(file_path, "rb") as f:
                files = {"files": (os.path.basename(file_path), f)}
                data = {"channel": "stream", "name": display_name}
                resp = requests.post(
                    f"{self.worker_url}/api/upload",
                    files=files,
                    data=data,
                    headers=self._headers_auth(),
                    timeout=max(UPLOAD_TIMEOUT, 120),
                )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def delete_track(self, key):
        """트랙 삭제"""
        try:
            resp = requests.post(
                f"{self.worker_url}/api/delete",
                json={"key": key, "channel": "stream"},
                headers=self._headers_json(),
                timeout=UPLOAD_TIMEOUT,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def save_order(self, tracks):
        """트랙 순서 저장"""
        try:
            resp = requests.post(
                f"{self.worker_url}/api/meta",
                json={"channel": "stream", "tracks": tracks},
                headers=self._headers_json(),
                timeout=UPLOAD_TIMEOUT,
            )
            return resp.status_code == 200
        except Exception:
            return False

    # ── CH5 상태 ───────────────────────────────────────────────

    def get_ch5_state(self):
        """CH5 상태 조회"""
        try:
            resp = requests.get(
                f"{self.worker_url}/api/ch5/state",
                timeout=UPLOAD_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {"trackKey": None, "paused": True, "currentTime": 0}

    def go_on_air(self, track_key, track_name, duration):
        """ON AIR 시작 → (ok, error_msg)"""
        try:
            resp = requests.post(
                f"{self.worker_url}/api/ch5/state",
                json={
                    "trackKey": track_key,
                    "trackName": track_name,
                    "duration": duration,
                    "currentTime": 0,
                    "paused": False,
                },
                headers=self._headers_json(),
                timeout=UPLOAD_TIMEOUT,
            )
            if resp.status_code == 409:
                data = resp.json()
                return False, data.get("message", "충돌: 라이브 방송 활성 중")
            return resp.status_code == 200, ""
        except Exception as e:
            return False, str(e)

    def toggle_pause(self, track_key, track_name, duration, paused, current_time=0, start_epoch=None):
        """일시정지/재개"""
        body = {
            "trackKey": track_key,
            "trackName": track_name,
            "duration": duration,
            "paused": paused,
            "currentTime": current_time,
        }
        if start_epoch:
            body["startEpoch"] = start_epoch
        try:
            resp = requests.post(
                f"{self.worker_url}/api/ch5/state",
                json=body,
                headers=self._headers_json(),
                timeout=UPLOAD_TIMEOUT,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def stop_file_broadcast(self):
        """파일 방송 종료"""
        try:
            resp = requests.post(
                f"{self.worker_url}/api/ch5/state",
                json={"trackKey": None, "paused": True, "currentTime": 0},
                headers=self._headers_json(),
                timeout=UPLOAD_TIMEOUT,
            )
            return resp.status_code == 200
        except Exception:
            return False

    # ── 라이브 상태 확인 ────────────────────────────────────────

    def get_live_state(self):
        """라이브 방송 상태 조회 (잠금 표시용)"""
        try:
            resp = requests.get(
                f"{self.worker_url}/api/live/state",
                timeout=UPLOAD_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {"active": False}
