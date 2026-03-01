# Audio Recorder Server

PC 마이크 / 시스템 사운드를 녹음하여 MP3로 저장하는 로컬 HTTP 서버.  
웹앱에서 `fetch()` 호출로 녹음을 제어한다.

## 설치

```bash
pip install -r requirements.txt
```

## 실행

```bash
python recorder_server.py
```

옵션:
- `--port 8090` : 서버 포트 (기본 8090)
- `--output-dir ./recordings` : MP3 저장 경로
- `--host 127.0.0.1` : 바인드 주소

실행 후 브라우저에서 `http://localhost:8090/docs` 를 열면 Swagger UI로 API를 테스트할 수 있다.

## API

| 엔드포인트 | 메서드 | 설명 |
|---|---|---|
| `/record/start` | POST | 녹음 시작. body: `{"source": "mic"\|"system"\|"both"}` |
| `/record/stop` | POST | 녹음 중지 → MP3 저장. 파일 경로/시간/크기 반환 |
| `/record/status` | GET | 현재 녹음 상태 (recording, source, elapsed) |
| `/devices` | GET | 오디오 디바이스 목록 |
| `/download/{filename}` | GET | MP3 파일 다운로드 |
| `/health` | GET | 서버 및 디바이스 상태 확인 |

## 웹앱에서 호출

```javascript
const API = 'http://localhost:8090';

// 녹음 시작 (마이크만)
await fetch(`${API}/record/start`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ source: 'mic' })
});

// 녹음 시작 (시스템 사운드만)
await fetch(`${API}/record/start`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ source: 'system' })
});

// 녹음 시작 (마이크 + 시스템 동시)
await fetch(`${API}/record/start`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ source: 'both' })
});

// 녹음 중지 → 결과
const res = await fetch(`${API}/record/stop`, { method: 'POST' });
const data = await res.json();
// data = { file: "C:\\...\\rec_20260227_143022_mic.mp3", duration: 12.5, size_kb: 245.3 }

// 상태 확인
const status = await fetch(`${API}/record/status`).then(r => r.json());
// status = { recording: true, source: "mic", elapsed: 5.2 }
```

## 시스템 사운드 캡처 사전 설정

Windows에서 시스템 사운드를 녹음하려면 **스테레오 믹스**를 활성화해야 한다:

1. 시스템 트레이 스피커 아이콘 우클릭 → **소리 설정**
2. **소리 제어판** (추가 소리 설정)
3. **녹음** 탭 → 빈 공간 우클릭 → **사용할 수 없는 장치 표시**
4. **스테레오 믹스** 우클릭 → **사용**

스테레오 믹스가 보이지 않으면 오디오 드라이버가 지원하지 않는 것이다.  
이 경우 [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) 설치를 권장한다.

## 테스트 UI

`test_ui.html` 파일을 브라우저에서 열면 녹음 버튼 UI로 테스트할 수 있다.  
서버가 실행 중이어야 동작한다.

## 파일 구조

```
audio-recorder/
├── recorder_server.py   # 메인 서버
├── requirements.txt     # 의존 패키지
├── test_ui.html         # 테스트용 UI
├── README.md            # 이 문서
└── recordings/          # MP3 저장 디렉토리 (자동 생성)
```
