"""
봄소리 라이브 호스트 — Workers 통신 모듈
청크 업로드, 방송 시작/종료, 상태 관리
"""

import requests
import threading
import time
import queue

from config import UPLOAD_TIMEOUT


class Uploader:
    """Workers API 통신"""

    def __init__(self, worker_url, admin_key, on_status=None, on_error=None):
        self.worker_url = worker_url.rstrip("/")
        self.admin_key = admin_key
        self.on_status = on_status  # callback(status_str)
        self.on_error = on_error    # callback(error_str)
        self.session_id = None
        self._upload_queue = queue.Queue(maxsize=100)
        self._upload_thread = None
        self._running = False
        self._uploaded_count = 0
        self._failed_count = 0

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.admin_key}",
            "Content-Type": "application/octet-stream"
        }

    def start_broadcast(self, title="", chunk_duration=2.0):
        """방송 시작 (Workers API 호출)"""
        try:
            resp = requests.post(
                f"{self.worker_url}/api/live/state",
                json={"action": "start", "title": title, "chunkDuration": chunk_duration},
                headers={"Authorization": f"Bearer {self.admin_key}", "Content-Type": "application/json"},
                timeout=UPLOAD_TIMEOUT
            )
            if resp.status_code == 409:
                data = resp.json()
                msg = data.get("message", "충돌: 파일 ON AIR 활성 중")
                if self.on_error:
                    self.on_error(msg)
                return False
            if resp.status_code != 200:
                if self.on_error:
                    self.on_error(f"방송 시작 실패: HTTP {resp.status_code}")
                return False
            data = resp.json()
            self.session_id = data.get("sessionId")
            self._uploaded_count = 0
            self._failed_count = 0

            # 업로드 스레드 시작
            self._running = True
            self._upload_thread = threading.Thread(target=self._upload_worker, daemon=True)
            self._upload_thread.start()

            if self.on_status:
                self.on_status(f"방송 시작: {self.session_id}")
            return True
        except requests.exceptions.ConnectionError:
            if self.on_error:
                self.on_error("서버 연결 실패. Workers URL을 확인하세요.")
            return False
        except Exception as e:
            if self.on_error:
                self.on_error(f"방송 시작 오류: {e}")
            return False

    def stop_broadcast(self):
        """방송 종료"""
        self._running = False

        # 큐에 남은 청크 처리 대기 (최대 5초)
        if self._upload_thread:
            self._upload_thread.join(timeout=5)

        try:
            resp = requests.post(
                f"{self.worker_url}/api/live/state",
                json={"action": "stop"},
                headers={"Authorization": f"Bearer {self.admin_key}", "Content-Type": "application/json"},
                timeout=UPLOAD_TIMEOUT
            )
            if self.on_status:
                self.on_status(f"방송 종료 (청크 {self._uploaded_count}개 전송, 실패 {self._failed_count}개)")
        except Exception as e:
            if self.on_error:
                self.on_error(f"방송 종료 오류: {e}")

        self.session_id = None

    def upload_chunk(self, chunk_data, chunk_index):
        """청크를 업로드 큐에 추가"""
        try:
            self._upload_queue.put_nowait((chunk_data, chunk_index))
        except queue.Full:
            if self.on_error:
                self.on_error(f"업로드 큐 가득 참 (청크 {chunk_index} 드롭)")

    def _upload_worker(self):
        """백그라운드 업로드 스레드"""
        while self._running or not self._upload_queue.empty():
            try:
                chunk_data, chunk_index = self._upload_queue.get(timeout=1)
            except queue.Empty:
                continue

            success = self._do_upload(chunk_data, chunk_index)
            if success:
                self._uploaded_count += 1
                if self.on_status:
                    self.on_status(f"청크 {chunk_index} 전송 ({self._uploaded_count}개)")
            else:
                self._failed_count += 1
                # 재시도 1회
                if not self._do_upload(chunk_data, chunk_index):
                    if self.on_error:
                        self.on_error(f"청크 {chunk_index} 전송 실패 (재시도 후)")

    def _do_upload(self, chunk_data, chunk_index):
        """실제 HTTP POST"""
        try:
            resp = requests.post(
                f"{self.worker_url}/api/live/chunk",
                data=chunk_data,
                headers={
                    "Authorization": f"Bearer {self.admin_key}",
                    "Content-Type": "application/octet-stream",
                    "X-Chunk-Index": str(chunk_index),
                    "X-Chunk-Duration": str(2.0),
                },
                timeout=UPLOAD_TIMEOUT
            )
            return resp.status_code == 200
        except:
            return False

    def send_message(self, message):
        """라이브 메시지 업데이트"""
        try:
            requests.post(
                f"{self.worker_url}/api/live/state",
                json={"action": "message", "message": message},
                headers={"Authorization": f"Bearer {self.admin_key}", "Content-Type": "application/json"},
                timeout=UPLOAD_TIMEOUT
            )
        except:
            pass

    @property
    def uploaded_count(self):
        return self._uploaded_count

    @property
    def queue_size(self):
        return self._upload_queue.qsize()
