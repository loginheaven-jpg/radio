# 백그라운드 오디오 재생 유지 — Claude Code 구현 지시서

> **대상 파일**: `index.html` (yebomradio 프로젝트 루트)  
> **목적**: 스마트폰 화면이 꺼지거나 백그라운드로 전환되어도 오디오 재생이 끊기지 않도록 수정  
> **범위 제한**: 이 문서에 명시된 3개 작업만 수행할 것. 다른 코드(CSS, HTML 마크업, worker.js, sw.js 등)는 절대 수정하지 말 것.

---

## 배경

현재 예봄라디오는 모바일에서 화면이 꺼지면 소리가 멈추거나, 화면이 다시 켜져도 UI는 재생 상태인데 소리가 안 나는 현상이 발생한다. 원인은 세 가지다.

1. 브라우저가 백그라운드 진입 시 `AudioContext`를 `suspended`로 전환하는데, 복귀 시 `resume()` 호출이 없다.
2. CH5 라이브와 리플레이는 `<audio>` 요소 없이 `AudioContext.BufferSource`만 사용하여, 브라우저가 "미디어 재생 중"으로 인식하지 못해 백그라운드에서 즉시 서스펜드된다.
3. `ensureLiveAudioCtx()` 함수가 `audioCtx.resume()`의 Promise를 `await`하지 않아, resume 완료 전에 재생이 시작되어 무음이 된다.

---

## 작업 1: visibilitychange 핸들러 교체

### 위치 찾기

`index.html` 내에서 아래 3줄을 찾는다:

```javascript
document.addEventListener('visibilitychange', () => { if (document.hidden) saveResume(currentChannel); });
```

이 코드는 `setInterval(() => { if (isPlaying && ...` 바로 다음, `window.addEventListener('beforeunload', ...)` 바로 위에 있다.

### 교체 내용

위 1줄을 삭제하고, 아래 코드로 교체한다:

```javascript
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    saveResume(currentChannel);
  } else {
    // AudioContext가 백그라운드에서 suspended 됐으면 복구
    if (audioCtx && audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    // HLS/Icecast (<audio> 요소): 재생 상태인데 멈춰 있으면 재시작
    if (isPlaying && audioEl && audioEl.paused && !audioEl.ended) {
      audioEl.play().catch(() => {});
    }
    // Howler: 내부 상태와 실제 재생 불일치 복구
    if (isPlaying && currentHowl && !currentHowl.playing()) {
      currentHowl.play();
    }
    // 라이브 폴링이 백그라운드에서 throttle 됐으면 즉시 재개
    if (liveMode && liveSessionId && !livePollTimer) {
      livePollAndPlay();
      livePollTimer = setInterval(livePollAndPlay, 2000);
    }
  }
});
```

### 주의

- `window.addEventListener('beforeunload', ...)` 행과 `window.addEventListener('pagehide', ...)` 행은 그대로 둔다. 삭제하지 않는다.
- 기존의 `setInterval(() => { if (isPlaying && (currentChannel === 3 || currentChannel === 4)) saveResume(currentChannel); }, 5000);` 행도 그대로 둔다.

---

## 작업 2: 무음 오디오 앵커 함수 추가 + ensureLiveAudioCtx 수정

### 위치 찾기

`index.html` 내에서 아래 주석과 함수를 찾는다:

```javascript
// ── Live Chunk Player (v2 — 순차 fetch + 버퍼 관리) ──
function ensureLiveAudioCtx() {
  initAudioContext();
  if (audioCtx.state === 'suspended') audioCtx.resume();
}
```

### 교체 내용

위 `ensureLiveAudioCtx` 함수(3줄)를 삭제하고, 아래 코드 블록 전체로 교체한다. 주석 행(`// ── Live Chunk Player ...`)은 그대로 유지한다.

```javascript
// ── Live Chunk Player (v2 — 순차 fetch + 버퍼 관리) ──

// ── 무음 오디오 앵커 (백그라운드 재생 유지용) ──
let silentAnchor = null;
let silentAnchorUrl = null;

function createSilentWavUrl() {
  if (silentAnchorUrl) return silentAnchorUrl;
  const sampleRate = 44100;
  const numSamples = sampleRate; // 1초
  const buffer = new ArrayBuffer(44 + numSamples * 2);
  const view = new DataView(buffer);
  const writeStr = (off, str) => { for (let i = 0; i < str.length; i++) view.setUint8(off + i, str.charCodeAt(i)); };
  writeStr(0, 'RIFF');
  view.setUint32(4, 36 + numSamples * 2, true);
  writeStr(8, 'WAVE');
  writeStr(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, 'data');
  view.setUint32(40, numSamples * 2, true);
  silentAnchorUrl = URL.createObjectURL(new Blob([buffer], { type: 'audio/wav' }));
  return silentAnchorUrl;
}

function startSilentAnchor() {
  if (silentAnchor) return;
  silentAnchor = document.createElement('audio');
  silentAnchor.src = createSilentWavUrl();
  silentAnchor.loop = true;
  silentAnchor.volume = 0.01;
  silentAnchor.play().catch(() => {});
}

function stopSilentAnchor() {
  if (silentAnchor) {
    silentAnchor.pause();
    silentAnchor.src = '';
    silentAnchor = null;
  }
}

async function ensureLiveAudioCtx() {
  initAudioContext();
  if (audioCtx.state === 'suspended') await audioCtx.resume();
}
```

### 주의

- `ensureLiveAudioCtx`가 `async`로 바뀌었다. 이 함수를 호출하는 곳에서 `await`가 필요한데, 호출부는 이미 `async` 함수 내부이거나 Promise 체인이 불필요한 맥락이므로 호출부는 수정하지 않아도 동작에 문제없다. (`startLivePlayer`와 `startReplay` 내부에서 `ensureLiveAudioCtx()`를 호출하지만, 이후 즉시 청크를 fetch하므로 네트워크 지연이 resume 완료를 기다려주는 효과가 있다.)
- `let liveFetching = false;`와 `let liveErrorCount = 0;` 행은 그대로 유지한다. 위 코드 블록 바로 다음에 이 두 줄이 와야 한다.

---

## 작업 3: startLivePlayer / stopLivePlayer / startReplay / stopReplay에 앵커 호출 추가

### 3-A. startLivePlayer

아래 함수를 찾는다:

```javascript
function startLivePlayer(sessionId, chunkDuration, latestChunk) {
```

이 함수 내부에서 아래 행을 찾는다:

```javascript
  livePollAndPlay();
  livePollTimer = setInterval(livePollAndPlay, 2000);
}
```

이 2행 사이(livePollAndPlay() 호출 직전)에 아래 2행을 삽입한다:

```javascript
  startSilentAnchor();
  updateMediaSession();
```

결과:
```javascript
  startSilentAnchor();
  updateMediaSession();
  livePollAndPlay();
  livePollTimer = setInterval(livePollAndPlay, 2000);
}
```

### 3-B. stopLivePlayer

아래 함수를 찾는다:

```javascript
function stopLivePlayer() {
  clearInterval(livePollTimer); livePollTimer = null;
  liveScheduledSources.forEach(s => { try { s.stop(); } catch {} });
  liveScheduledSources = [];
  liveMode = false;
  liveLastChunk = -1;
  liveNextTime = 0;
  liveFetching = false;
}
```

닫는 `}` 바로 위에 아래 1행을 추가한다:

```javascript
  stopSilentAnchor();
```

결과:
```javascript
function stopLivePlayer() {
  clearInterval(livePollTimer); livePollTimer = null;
  liveScheduledSources.forEach(s => { try { s.stop(); } catch {} });
  liveScheduledSources = [];
  liveMode = false;
  liveLastChunk = -1;
  liveNextTime = 0;
  liveFetching = false;
  stopSilentAnchor();
}
```

### 3-C. startReplay

아래 함수를 찾는다:

```javascript
function startReplay(session) {
```

이 함수 내부에서 아래 행을 찾는다:

```javascript
  replayFeedLoop();
  replayFeedTimer = setInterval(replayFeedLoop, 500);
}
```

이 2행 앞에 아래 2행을 삽입한다:

```javascript
  startSilentAnchor();
  updateMediaSession();
```

결과:
```javascript
  startSilentAnchor();
  updateMediaSession();
  replayFeedLoop();
  replayFeedTimer = setInterval(replayFeedLoop, 500);
}
```

### 3-D. stopReplay

아래 함수를 찾는다:

```javascript
function stopReplay() {
  clearInterval(replayFeedTimer); replayFeedTimer = null;
  replayScheduledSources.forEach(s => { try { s.stop(); } catch {} });
  replayScheduledSources = [];
  replayPlaying = false;
  replayMode = false;
  replayCurrentChunk = 0;
  replayNextTime = 0;
}
```

닫는 `}` 바로 위에 아래 1행을 추가한다:

```javascript
  stopSilentAnchor();
```

결과:
```javascript
function stopReplay() {
  clearInterval(replayFeedTimer); replayFeedTimer = null;
  replayScheduledSources.forEach(s => { try { s.stop(); } catch {} });
  replayScheduledSources = [];
  replayPlaying = false;
  replayMode = false;
  replayCurrentChunk = 0;
  replayNextTime = 0;
  stopSilentAnchor();
}
```

---

## 수정하지 않는 것 (명시적 제외)

- CSS, HTML 마크업: 일절 수정하지 않는다.
- worker.js, sw.js, manifest.json, wrangler.toml: 수정하지 않는다.
- 다른 JavaScript 함수: 이 문서에 언급되지 않은 함수는 수정하지 않는다.
- Howler monkey-patch (`<script>` 태그 내 `Howler._obtainHtml5Audio`): 수정하지 않는다.
- `initAudioContext()`, `connectHowlToAudioCtx()`, `startRecording()`: 수정하지 않는다.
- 등잔 애니메이션, 파티클, 디스크 회전 코드: 수정하지 않는다.

---

## 검증 방법

수정 후 아래 시나리오를 Android Chrome에서 테스트한다.

1. **CH1 (KBS 클래식FM)**: 재생 시작 → 화면 끄기 → 30초 대기 → 소리 지속 확인 → 화면 켜기 → UI와 소리 일치 확인
2. **CH3 (말씀의 전당)**: 트랙 재생 → 화면 끄기 → 30초 대기 → 소리 지속 확인 → 화면 켜기 → 탐색바 진행 확인
3. **CH5 라이브** (라이브 활성 시): 라이브 수신 → 화면 끄기 → 30초 대기 → 소리 지속 확인
4. **잠금화면 컨트롤**: 재생 중 화면 끄기 → 잠금화면에 "예봄라디오" 미디어 컨트롤 표시 확인 → 일시정지/재생 동작 확인

---

## 변경 요약

| 작업 | 변경 유형 | 영향 범위 |
|---|---|---|
| 작업 1 | 기존 1행 → 16행 교체 | visibilitychange 핸들러 |
| 작업 2 | 기존 4행 → 46행 교체 | ensureLiveAudioCtx + 신규 함수 3개 + 변수 2개 |
| 작업 3-A | 2행 삽입 | startLivePlayer 내부 |
| 작업 3-B | 1행 삽입 | stopLivePlayer 내부 |
| 작업 3-C | 2행 삽입 | startReplay 내부 |
| 작업 3-D | 1행 삽입 | stopReplay 내부 |

총 추가: 약 60행. 삭제: 약 5행. 신규 전역 변수 2개(`silentAnchor`, `silentAnchorUrl`).
