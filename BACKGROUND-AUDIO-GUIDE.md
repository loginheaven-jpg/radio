# 스마트폰 백그라운드 오디오 재생 유지 가이드

> 웹앱(PWA)에서 화면이 꺼져도 오디오가 끊기지 않도록 하는 기술 레퍼런스.
> 예봄라디오 프로젝트에서 검증된 구현을 기반으로 작성.

---

## 문제의 본질

모바일 브라우저(특히 Android Chrome)는 다음 상황에서 웹앱의 오디오를 중단시킨다:

| 상황 | OS/브라우저 동작 |
|------|----------------|
| 화면 꺼짐 | 백그라운드 탭 throttling, AudioContext 정지 |
| 다른 앱으로 전환 | 메모리 부족 시 탭 kill |
| Android Doze 모드 | 네트워크/CPU 제한, setInterval 정지 |
| 장시간 백그라운드 | App Standby bucket 강등 → 완전 정지 |

**단일 기술로는 해결 불가.** 아래 7가지 방어 계층을 조합해야 한다.

---

## 방어 계층 구조

```
┌─────────────────────────────────────────────────┐
│              7계층 방어 아키텍처                    │
│                                                   │
│  ① <audio> 요소 — OS 수준 보호 (핵심)              │
│  ② Silent Anchor — Android kill 방지              │
│  ③ Web Worker Keep-Alive — Doze 대응              │
│  ④ Wake Lock API — 화면 꺼짐 방지                  │
│  ⑤ Media Session API — OS에 재생 상태 신호          │
│  ⑥ visibilitychange — 포그라운드 복귀 시 복구       │
│  ⑦ Stall Watchdog — Silent stall 감지/복구        │
│                                                   │
└─────────────────────────────────────────────────┘
```

---

## ① HTML5 `<audio>` 요소 (핵심)

### 왜 Web Audio API가 아닌 `<audio>`인가?

Chrome은 `<audio>` 요소의 재생을 **OS 수준 미디어 세션**으로 인식하여 보호한다.
`AudioContext`만으로 재생하면 백그라운드에서 즉시 `suspended` 상태가 된다.

```
✅ <audio src="..."> → OS가 미디어 재생으로 인식 → 보호
❌ AudioContext만 → 백그라운드 진입 시 suspended → 소리 없음
```

### 권장 구조

```javascript
// 메인 재생: 항상 <audio> 요소 사용
const audioEl = document.createElement('audio');
audioEl.crossOrigin = 'anonymous';
audioEl.src = streamUrl;
audioEl.play();

// DSP 처리가 필요하면 <audio>를 AudioContext에 연결
const ctx = new AudioContext();
const source = ctx.createMediaElementSource(audioEl); // <audio>가 원본
source.connect(gainNode).connect(ctx.destination);
```

**핵심 원칙**: `<audio>` 요소가 실제 재생을 담당하고, AudioContext는 부가 처리(이퀄라이저, 볼륨 부스트, 녹음 등)만 한다. AudioContext가 suspended 되어도 `<audio>` 재생은 계속된다.

---

## ② Silent Anchor — Android Kill 방지

### 문제

Android는 "실제로 소리를 출력하지 않는" 오디오 앱을 감지하여 종료할 수 있다.
HLS 스트림 버퍼링 중이나 트랙 전환 사이의 공백 시 이 감지에 걸린다.

### 해결: 초소음 WAV 무한 루프

```javascript
function createSilentWavUrl() {
  const sampleRate = 44100;
  const numSamples = sampleRate * 5; // 5초
  const buffer = new ArrayBuffer(44 + numSamples * 2);
  const view = new DataView(buffer);

  // WAV 헤더 (44 bytes)
  const writeStr = (offset, str) => { for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i)); };
  writeStr(0, 'RIFF');
  view.setUint32(4, 36 + numSamples * 2, true);
  writeStr(8, 'WAVE');
  writeStr(12, 'fmt ');
  view.setUint32(16, 16, true);        // PCM
  view.setUint16(20, 1, true);          // AudioFormat
  view.setUint16(22, 1, true);          // Mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);          // BlockAlign
  view.setUint16(34, 16, true);         // BitsPerSample
  writeStr(36, 'data');
  view.setUint32(40, numSamples * 2, true);

  // ±3 범위의 미세 노이즈 주입 (완전 무음은 Android가 감지)
  for (let i = 0; i < numSamples; i++) {
    view.setInt16(44 + i * 2, (Math.random() * 6 - 3) | 0, true);
  }

  return URL.createObjectURL(new Blob([buffer], { type: 'audio/wav' }));
}

// 재생 시작 시 함께 시작
let silentAnchor = null;
function startSilentAnchor() {
  if (silentAnchor) return;
  silentAnchor = document.createElement('audio');
  silentAnchor.src = createSilentWavUrl();
  silentAnchor.loop = true;
  silentAnchor.volume = 0.05; // 사람에게는 안 들리지만 OS에게는 "재생 중"
  silentAnchor.play().catch(() => {});
}
```

### 핵심 포인트

| 설정 | 값 | 이유 |
|------|---|------|
| volume | 0.05 (5%) | 너무 낮으면 Android 무음 감지, 너무 높으면 청취 방해 |
| loop | true | 5초마다 반복 → 연속 재생 신호 |
| 노이즈 | ±3 (16bit 기준 0.009%) | 완전 무음(`0`)은 감지됨 |

---

## ③ Web Worker Keep-Alive — Doze 대응

### 문제

Android Doze 모드에서 `setInterval`/`setTimeout`은 **완전히 정지**된다.
메인 스레드의 타이머로는 백그라운드 복구 로직을 실행할 수 없다.

### 해결: 인라인 Web Worker

```javascript
function createKeepAliveWorker() {
  const code = `
    let tid = null;
    onmessage = function(e) {
      if (e.data === 'start') {
        if (tid) clearInterval(tid);
        tid = setInterval(() => postMessage('tick'), 20000);
      } else if (e.data === 'stop') {
        clearInterval(tid); tid = null;
      }
    };
  `;
  return new Worker(URL.createObjectURL(
    new Blob([code], { type: 'application/javascript' })
  ));
}

// 사용
let bgWorker = null;
function startBgKeepAlive() {
  if (bgWorker) return;
  try {
    bgWorker = createKeepAliveWorker();
    bgWorker.onmessage = () => bgKeepAliveHandler(); // 20초마다 복구 체크
    bgWorker.postMessage('start');
  } catch {
    // Worker 생성 실패 시 fallback
    bgWorker = setInterval(bgKeepAliveHandler, 20000);
  }
}
```

### Web Worker의 타이머가 살아남는 이유

Web Worker는 메인 스레드와 별도의 이벤트 루프를 가진다. Chrome은 오디오가 재생 중인 탭의 Worker 타이머를 Doze에서도 유지한다 (Silent Anchor와 시너지).

---

## ④ Wake Lock API — 화면 꺼짐 방지

```javascript
let wakeLock = null;

async function requestWakeLock() {
  if (!('wakeLock' in navigator)) return;
  try {
    wakeLock = await navigator.wakeLock.request('screen');
    wakeLock.addEventListener('release', () => { wakeLock = null; });
  } catch (e) { /* 실패해도 오디오 재생에는 영향 없음 */ }
}

function releaseWakeLock() {
  if (wakeLock) { wakeLock.release().catch(() => {}); wakeLock = null; }
}
```

### 주의사항

- 브라우저가 탭을 백그라운드로 보내면 **자동으로 해제**된다
- `visibilitychange`에서 포그라운드 복귀 시 **재획득** 필요
- Wake Lock은 화면 꺼짐 방지일 뿐, 오디오 유지와는 직접 관련 없음
- 하지만 화면이 켜져 있으면 Doze 진입이 지연되므로 간접적 도움

---

## ⑤ Media Session API — OS에 "재생 중" 신호

### 왜 중요한가

Android는 Media Session이 활성화된 앱을 **미디어 재생 앱으로 분류**하여 우선순위를 높인다.
잠금 화면 미디어 컨트롤이 표시되고, 앱 종료 우선순위가 낮아진다.

```javascript
// 메타데이터 설정
function updateMediaSession() {
  if (!('mediaSession' in navigator)) return;
  navigator.mediaSession.metadata = new MediaMetadata({
    title: '현재 재생 중인 곡',
    artist: '채널명',
    album: '앱 이름',
    artwork: [
      { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
      { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
    ]
  });
}

// 잠금 화면 컨트롤 등록
navigator.mediaSession.setActionHandler('play', () => handlePlay());
navigator.mediaSession.setActionHandler('pause', () => handlePause());
navigator.mediaSession.setActionHandler('previoustrack', () => prevTrack());
navigator.mediaSession.setActionHandler('nexttrack', () => nextTrack());

// 재생 위치 업데이트 (20초마다, bgKeepAliveHandler에서 호출)
navigator.mediaSession.setPositionState({
  duration: totalDuration,
  playbackRate: 1.0,
  position: currentPosition
});
```

### `setPositionState` 주기적 호출의 의미

단순히 잠금 화면에 시간을 표시하는 것이 아니라, **Android에게 "이 앱은 아직 능동적으로 재생 중"이라는 신호**를 보내는 것이다. 이 호출이 멈추면 OS가 앱을 유휴 상태로 판단할 수 있다.

---

## ⑥ visibilitychange — 포그라운드 복귀 시 전면 복구

```javascript
document.addEventListener('visibilitychange', async () => {
  if (document.hidden) {
    // 백그라운드 진입: 불필요한 작업 정지 (배터리 절약)
    savePlaybackPosition();
    stopAnimations();
  } else {
    // 포그라운드 복귀: 모든 오디오 시스템 점검 및 복구

    // 1. AudioContext 복구 (await로 완료 보장)
    if (audioCtx && audioCtx.state === 'suspended') {
      try { await audioCtx.resume(); } catch {}
    }

    // 2. Wake Lock 재획득
    if (isPlaying) requestWakeLock();

    // 3. <audio> 요소 복구
    if (isPlaying && audioEl && audioEl.paused && !audioEl.ended) {
      audioEl.play().catch(() => {});
    }

    // 4. Stall watchdog 타이머 리셋 (오탐 방지)
    lastWatchdogTime = -1;

    // 5. 볼륨 강제 복원 (Android resume 시 풀볼륨 버그 방지)
    applyVolume(currentVolume);
  }
});
```

### 왜 `visibilitychange`에서 복구가 필요한가

백그라운드 20초 타이머(③)가 대부분의 상황을 처리하지만, **포그라운드 복귀 시점**에는 즉각적인 복구가 사용자 경험에 직결된다. 사용자가 앱으로 돌아왔을 때 소리가 안 나면 "고장났다"고 느낀다.

---

## ⑦ Stall Watchdog — "재생 중인데 소리 없음" 감지

### 문제

가장 은밀한 장애: `audioEl.paused === false`이고 에러도 없는데, `currentTime`이 멈춰 있어 소리가 안 나는 상태. 네트워크 일시 단절이나 HLS 세그먼트 로딩 실패 시 발생.

### 해결: currentTime 진행 여부 감시

```javascript
let stallWatchdogTimer = null;
let lastWatchdogTime = -1;
let stallCount = 0;
const STALL_CHECK_INTERVAL = 5000;    // 5초마다 체크
const MAX_STALL_BEFORE_RELOAD = 3;    // 3회 연속 스톨 → 재연결

function checkAudioStall() {
  if (!isPlaying || !audioEl) return;

  const curTime = audioEl.currentTime;

  if (lastWatchdogTime >= 0
      && curTime === lastWatchdogTime
      && !audioEl.paused
      && !audioEl.ended) {
    stallCount++;

    if (stallCount >= MAX_STALL_BEFORE_RELOAD) {
      // 3회 연속: 채널 전체 재연결
      showToast('연결 끊김 — 재연결 중...');
      stallCount = 0;
      lastWatchdogTime = -1;
      reconnectChannel();
    } else {
      // 1~2회: 부드러운 복구 시도
      if (hlsInstance) hlsInstance.startLoad();
      audioEl.play().catch(() => {});
    }
  } else {
    if (stallCount > 0) stallCount = 0; // 진행 감지 → 리셋
  }

  lastWatchdogTime = curTime;
}

function startStallWatchdog() {
  stopStallWatchdog();
  lastWatchdogTime = -1;
  stallCount = 0;
  stallWatchdogTimer = setInterval(checkAudioStall, STALL_CHECK_INTERVAL);
}
```

### 복구 에스컬레이션

```
5초 체크 → 스톨 #1 → play() 재시도
          → 스톨 #2 → play() 재시도
          → 스톨 #3 → 채널 전체 재연결 + 사용자 알림
```

---

## 20초 Keep-Alive 핸들러 (모든 계층 통합)

```javascript
function bgKeepAliveHandler() {
  if (!isPlaying) return;

  // ① <audio> 요소: paused 상태 복구
  if (audioEl && audioEl.paused && !audioEl.ended) {
    audioEl.play().catch(() => {});
  }

  // ① <audio> 요소: silent stall 감지 (currentTime 정지)
  if (audioEl && !audioEl.paused && !audioEl.ended) {
    const curTime = audioEl.currentTime;
    if (bgLastTime >= 0 && curTime === bgLastTime) {
      if (hlsInstance) hlsInstance.startLoad();
      audioEl.play().catch(() => {});
    }
    bgLastTime = curTime;
  }

  // ③ AudioContext 복구
  if (audioCtx && audioCtx.state === 'suspended') {
    audioCtx.resume().catch(() => {});
  }

  // ④ Wake Lock 재획득
  if (!wakeLock) requestWakeLock();

  // ⑤ Media Session 위치 갱신 (Android에 "아직 재생 중" 신호)
  if ('mediaSession' in navigator) {
    navigator.mediaSession.setPositionState({
      duration: getDuration(),
      playbackRate: 1.0,
      position: getPosition()
    });
  }
}
```

---

## Service Worker 캐싱 전략

```javascript
// 오디오 파일은 절대 캐시하지 않는다
const NO_CACHE = [
  /\.mp3$/, /\.m4a$/, /\.ogg$/, /\.wav$/, /\.opus$/,
  /\.m3u8$/, /\.ts$/,   // HLS 세그먼트
  /\/api\//,             // API 호출
];

// 앱 셸(HTML, CSS, JS)만 캐시 → 오프라인에서도 앱 로딩 가능
// 오디오는 항상 네트워크에서 가져옴
```

---

## 체크리스트: 새 프로젝트에 적용할 때

- [ ] 메인 재생을 `<audio>` 요소로 (AudioContext 아님)
- [ ] Silent Anchor WAV 루프 (volume 0.05, 미세 노이즈)
- [ ] Web Worker 20초 타이머 (setInterval fallback 포함)
- [ ] bgKeepAliveHandler에서 5가지 복구 (audio, AudioContext, WakeLock, MediaSession, stall)
- [ ] Wake Lock 획득/해제/재획득
- [ ] Media Session 메타데이터 + 잠금 화면 컨트롤 + `setPositionState`
- [ ] `visibilitychange`에서 즉시 복구 + watchdog 리셋
- [ ] Stall Watchdog (5초 간격, 3회 에스컬레이션)
- [ ] Service Worker: 오디오 파일 no-cache, 앱 셸만 cache

---

## 브라우저/OS별 지원 현황

| 기술 | Chrome Android | Safari iOS | Samsung Internet |
|------|---------------|-----------|-----------------|
| `<audio>` 백그라운드 | ✅ | ✅ | ✅ |
| Silent Anchor | ✅ (필수) | ⚠️ (덜 공격적) | ✅ |
| Web Worker 타이머 | ✅ | ✅ | ✅ |
| Wake Lock API | ✅ | ❌ | ✅ |
| Media Session | ✅ | ⚠️ (부분) | ✅ |
| visibilitychange | ✅ | ✅ | ✅ |

---

## 참고: 이 가이드의 출처

예봄라디오(radio.yebom.org) — Vanilla JS SPA, Cloudflare Workers + R2 기반 웹 라디오.
HLS 라이브 스트리밍 + R2 파일 스트리밍 환경에서 Android/iOS 백그라운드 재생을
안정적으로 유지하는 것을 실제 서비스에서 검증한 결과물이다.
