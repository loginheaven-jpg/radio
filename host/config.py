"""
봄소리 라이브 호스트 — 설정
"""

# Workers API
WORKER_URL = ""  # 설정 화면에서 입력
ADMIN_KEY = ""   # 설정 화면에서 입력

# 오디오
CHUNK_DURATION = 2.0      # 초
SAMPLE_RATE = 48000
CHANNELS = 1              # 모노
BITRATE = "128k"          # Opus 비트레이트
FORMAT = "ogg"            # 컨테이너

# FFmpeg
FFMPEG_PATH = "ffmpeg"    # PATH에 있으면 그대로, 아니면 절대경로

# 네트워크
UPLOAD_TIMEOUT = 10       # 초
HEARTBEAT_INTERVAL = 30   # 초 (미사용, 향후 확장)

# GUI
WINDOW_TITLE = "봄소리 호스트"
WINDOW_SIZE = "500x660"
