# Audio Recorder Server — 웹앱 연동 API 명세

## 서버 주소

```
http://localhost:8090
```


---

## 1. 녹음 시작

```
POST /record/start
Content-Type: application/json
```

### 요청 파라미터

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|----------|------|------|--------|------|
| `source` | string | 아니오 | `"mic"` | 입력 소스. `"mic"` \| `"system"` \| `"both"` |
| `filename` | string | 아니오 | 자동생성 | 저장 파일명 (확장자 제외). 재생시간(초)은 서버가 자동 추가 |
| `mode` | string | 아니오 | `"manual"` | `"manual"` = 수동 녹음, `"auto"` = 무음 자동 분할 |
| `silence_threshold` | number | 아니오 | `50` | 무음 판정 기준 (RMS, 0~32767). 높을수록 둔감 |
| `silence_duration` | number | 아니오 | `1.0` | 무음이 이 시간(초) 지속되면 파일 분할 |

### silence_threshold 권장값

| 값 | 환경 |
|----|------|
| 30~50 | 조용한 환경, 완전 무음만 감지 |
| 100~200 | 일반적인 환경 (권장 시작점) |
| 300~500 | 배경 소음이 큰 환경 |

### 요청 예시

**수동 녹음 (기존 방식)** — `source`만 보내면 된다:

```javascript
fetch('http://localhost:8090/record/start', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    source: 'system',
    filename: 'yebom202602021100'
  })
});
```

**자동 분할 녹음** — `mode`와 무음 설정을 추가한다:

```javascript
fetch('http://localhost:8090/record/start', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    source: 'system',
    filename: 'yebom202602021100',
    mode: 'auto',
    silence_threshold: 100,
    silence_duration: 1.5
  })
});
```

### 응답 (200 OK)

```json
{
  "recording": true,
  "source": "system",
  "mode": "auto"
}
```


---

## 2. 녹음 중지

```
POST /record/stop
```

요청 본문 없음.

### 응답 (200 OK)

**수동 모드:**

```json
{
  "file": "C:\\recordings\\yebom202602021100_180.mp3",
  "files": ["C:\\recordings\\yebom202602021100_180.mp3"],
  "duration": 180.42,
  "size_kb": 4320.5
}
```

**자동 분할 모드:**

```json
{
  "file": "C:\\recordings\\yebom202602021100_003_30.mp3",
  "files": [
    "C:\\recordings\\yebom202602021100_001_45.mp3",
    "C:\\recordings\\yebom202602021100_002_120.mp3",
    "C:\\recordings\\yebom202602021100_003_30.mp3"
  ],
  "duration": 210.53,
  "size_kb": 4920.3
}
```

| 필드 | 설명 |
|------|------|
| `file` | 마지막으로 저장된 파일 경로 |
| `files` | 전체 저장 파일 목록 (수동 모드에서도 배열로 반환) |
| `duration` | 전체 경과 시간 (초) |
| `size_kb` | 전체 파일 크기 합계 (KB) |


---

## 3. 상태 조회

```
GET /record/status
```

### 응답 (200 OK)

```json
{
  "recording": true,
  "source": "system",
  "elapsed": 45.2,
  "mode": "auto",
  "segment_count": 2,
  "auto_state": "recording"
}
```

| 필드 | 설명 |
|------|------|
| `mode` | `"manual"` 또는 `"auto"` |
| `segment_count` | auto 모드에서 현재까지 저장된 파일 수 |
| `auto_state` | auto 모드 내부 상태. `"waiting"` = 소리 대기 중, `"recording"` = 녹음 중 |


---

## 4. 파일명 생성 규칙

서버가 자동으로 뒤에 정보를 붙인다. 웹앱은 `filename`에 확장자 없이 원하는 이름만 보내면 된다.

| 모드 | 파일명 패턴 | 예시 |
|------|-------------|------|
| 수동 | `{filename}_{초}.mp3` | `yebom202602021100_180.mp3` |
| 자동 분할 | `{filename}_{순번}_{초}.mp3` | `yebom202602021100_001_45.mp3` |
| 미지정 (수동) | `rec_{날짜}_{소스}_{초}.mp3` | `rec_20260202_110000_system_180.mp3` |
| 미지정 (자동) | `rec_{날짜}_{소스}_{순번}_{초}.mp3` | `rec_20260202_110000_system_001_45.mp3` |


---

## 5. 자동 분할 모드 동작 설명

```
start(mode:"auto") 호출
    │
    ▼
 [대기] ──소리감지──▶ [녹음중] ──무음 N초──▶ [파일저장]
    ▲                                          │
    └──────────── 자동 반복 ───────────────────┘
    │
 stop() 호출 → 전체 종료, 파일 목록 반환
```

- 소리가 들리면 자동으로 녹음을 시작한다.
- 무음이 `silence_duration`초 지속되면 해당 구간을 MP3로 저장하고 다시 대기한다.
- 다시 소리가 들리면 새 파일로 녹음을 시작한다.
- `stop()`을 호출할 때까지 이 과정이 반복된다.
- 1초 미만의 짧은 소리는 노이즈로 간주하여 저장하지 않는다.


---

## 6. 에러 응답

| HTTP 코드 | 상황 |
|-----------|------|
| 400 | `source` 또는 `mode` 값이 잘못됨 |
| 409 | 이미 녹음 중 / 녹음 중이 아님 / 디바이스 없음 |

```json
{
  "detail": "이미 녹음 중입니다."
}
```


---

## 7. 서버 상태 확인

```
GET /health
```

서버 기동 직후 이 엔드포인트로 디바이스 인식 상태를 확인하는 것을 권장한다.

```json
{
  "status": "ok",
  "mic": true,
  "loopback": true
}
```
