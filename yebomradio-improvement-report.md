# 예봄라디오 2.0 — 종합 개선 보고서

> **분석 대상**: index.html (3,188줄), worker.js (998줄), sw.js (70줄), manifest.json, wrangler.toml  
> **분석일**: 2026-03-08  
> **버전**: v2.5.1 (40주년 스플래시 포함)

---

## 요약

예봄라디오 2.0은 단일 HTML + Cloudflare Workers 기반으로 6개 채널을 통합 운영하는 독창적인 교회 라디오 애플리케이션이다. 전체적인 아키텍처 설계와 UI 구현 수준이 매우 높다. 다만, 모바일 환경에서 **화면 잠금 시 소리 끊김**, **재생 상태 표시와 실제 음성 출력의 불일치** 등 사용자 보고 증상의 원인을 포함하여 총 24건의 개선 항목을 발견하였다. 이 중 심각도 CRITICAL이 5건, HIGH가 7건, MEDIUM이 8건, LOW가 4건이다.

---

## 1. 핵심 문제: 모바일 오디오 끊김 및 무음 현상

사용자 보고 증상: "재생 중 스마트폰 화면보호기로 들어가면 소리가 멈추는 경우", "화면은 재생 상태인데 소리가 안 나는 경우"

이 증상은 단일 원인이 아니라 복합적인 요인이 얽혀 있다. 아래에서 하나씩 분해한다.

### 1-1. AudioContext 서스펜션 미복구 [CRITICAL]

**위치**: index.html 전체 (visibilitychange 핸들러)

iOS Safari와 Android Chrome은 탭이 백그라운드로 전환되거나 화면이 꺼지면 `AudioContext`를 `suspended` 상태로 전환한다. 현재 코드의 `visibilitychange` 핸들러(1941행)는 `saveResume()`만 호출하고, AudioContext 복구는 시도하지 않는다.

이것이 **가장 결정적인 원인**이다. 라이브 청크 플레이어(CH5 라이브), 리플레이 플레이어, 녹음 중인 HLS/Howler 재생 모두 AudioContext에 의존한다. 화면이 켜져서 탭이 foreground로 돌아와도 AudioContext는 자동 복구되지 않으므로, UI는 재생 상태를 표시하지만 소리는 나오지 않는다.

**수정안**:
```javascript
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    saveResume(currentChannel);
  } else {
    // 탭이 다시 활성화되면 AudioContext 복구
    if (audioCtx && audioCtx.state === 'suspended') {
      audioCtx.resume().then(() => {
        console.log('AudioContext resumed after visibility change');
      });
    }
    // HLS 스트림이 stall 상태일 수 있으므로 재생 상태 확인
    if (isPlaying && audioEl && audioEl.paused && !audioEl.ended) {
      audioEl.play().catch(() => {});
    }
    if (isPlaying && currentHowl && !currentHowl.playing()) {
      currentHowl.play();
    }
  }
});
```

### 1-2. 라이브/리플레이 플레이어의 audio 요소 부재 [CRITICAL]

**위치**: index.html 2059~2169행 (라이브 청크 플레이어), 2172~2252행 (리플레이 플레이어)

라이브 청크 플레이어와 리플레이 플레이어는 `AudioContext.createBufferSource()`로 직접 오디오를 스케줄링한다. 이 방식은 `<audio>` HTML 요소를 사용하지 않기 때문에 다음과 같은 문제가 발생한다.

- 모바일 브라우저가 "미디어 재생 중"으로 인식하지 않아, 백그라운드에서 AudioContext가 즉시 서스펜드됨
- iOS Safari는 `<audio>` 요소 없이는 잠금화면 미디어 컨트롤을 표시하지 않음
- Android Chrome도 `<audio>`나 `<video>`가 없는 AudioContext 단독 재생은 백그라운드 유지 대상에서 제외함

**수정안**: 무음 `<audio>` 요소를 생성해 "미디어 세션 앵커"로 사용한다.

```javascript
// 라이브/리플레이 시작 시 무음 audio 앵커 생성
function createSilentAudioAnchor() {
  if (!window._silentAnchor) {
    const a = document.createElement('audio');
    // 최소 무음 WAV (44byte)
    a.src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEA' +
            'ABRAAABIAAAAAgAQAA==';
    a.loop = true;
    a.volume = 0.01; // 0이면 일부 브라우저에서 무시
    window._silentAnchor = a;
  }
  window._silentAnchor.play().catch(() => {});
}
function removeSilentAudioAnchor() {
  if (window._silentAnchor) {
    window._silentAnchor.pause();
    window._silentAnchor = null;
  }
}
```

`startLivePlayer()`와 `startReplay()` 진입 시 `createSilentAudioAnchor()`를 호출하고, `stopLivePlayer()`와 `stopReplay()` 시 `removeSilentAudioAnchor()`를 호출하면 된다.

### 1-3. ensureLiveAudioCtx의 resume 비동기 미대기 [HIGH]

**위치**: index.html 2060~2063행

```javascript
function ensureLiveAudioCtx() {
  initAudioContext();
  if (audioCtx.state === 'suspended') audioCtx.resume(); // ← await 없음
}
```

`audioCtx.resume()`은 Promise를 반환하는 비동기 함수다. `await` 없이 호출하면 AudioContext가 아직 `suspended` 상태에서 `BufferSource.start()`가 실행되어 무음이 된다. 사용자가 화면 잠금 후 돌아와서 재생 버튼을 눌러도 소리가 안 나는 경우의 직접적 원인이다.

**수정안**:
```javascript
async function ensureLiveAudioCtx() {
  initAudioContext();
  if (audioCtx.state === 'suspended') await audioCtx.resume();
}
```

이 함수를 호출하는 `startLivePlayer()`, `startReplay()` 등도 `await`해야 한다.

### 1-4. Howler + AudioContext 연결 후 채널 전환 시 유령 노드 [HIGH]

**위치**: index.html 1944~1956행 (connectHowlToAudioCtx)

녹음을 위해 `createMediaElementSource(node)`를 호출하면, 해당 `<audio>` 요소는 영구적으로 AudioContext에 바인딩된다. 이후 `currentHowl.unload()`로 Howler를 해제하면, Howler의 audio pool에서 해당 요소가 반환되거나 새 요소가 생성된다. 그런데 `_acConnected` 플래그는 개별 audio DOM 노드에 설정되므로, 새 Howl 인스턴스가 다른 audio 노드를 사용하면 AudioContext에 연결되지 않은 상태로 재생된다.

결과: 녹음 시작 → 채널 전환 → 다시 R2 채널에서 재생 시, 소리는 나지만 gainNode을 거치지 않아 녹음에 포착되지 않거나, 반대로 소리가 audioCtx.destination으로만 가서 볼륨 슬라이더가 작동하지 않는 상태가 될 수 있다.

**수정안**: 채널 전환 시(`stopPlayback()`) AudioContext 소스 노드를 명시적으로 정리한다.

```javascript
function stopPlayback() {
  stopHls();
  if (currentHowl) { currentHowl.unload(); currentHowl = null; }
  stopLivePlayer();
  stopReplay();
  // AudioContext 소스 노드 정리
  hlsSourceNode = null;
  howlSourceNode = null;
  isPlaying = false;
  updatePlayBtn(false);
  cancelAnimationFrame(seekRaf);
}
```

### 1-5. HLS 스트림의 비치명적 오류 무시 [HIGH]

**위치**: index.html 1507행

```javascript
hls.on(Hls.Events.ERROR, (_, data) => { if (data.fatal) reject(new Error('HLS fatal error')); });
```

HLS 초기 연결 시에만 fatal 에러를 처리하고, 연결 후에는 에러 핸들러가 없다. hls.js의 비치명적 오류(네트워크 일시 장애, 세그먼트 404 등)가 누적되면 스트림이 stall 상태에 빠지는데, 이때 화면은 "LIVE" 상태를 표시하지만 소리는 나오지 않는다.

**수정안**: 연결 후에도 에러 핸들러를 등록한다.

```javascript
currentHls = hls;
hls.on(Hls.Events.ERROR, (_, data) => {
  if (data.fatal) {
    switch (data.type) {
      case Hls.ErrorTypes.NETWORK_ERROR:
        console.log('HLS network error, attempting recovery...');
        hls.startLoad();
        break;
      case Hls.ErrorTypes.MEDIA_ERROR:
        console.log('HLS media error, attempting recovery...');
        hls.recoverMediaError();
        break;
      default:
        showToast('스트리밍 오류 — 재연결 중...');
        enterChannel(currentChannel);
    }
  }
});
```

---

## 2. 로직 오류 및 버그

### 2-1. 녹음 포맷 불일치: MP3 선택 시 실제로는 WebM 생성 [HIGH]

**위치**: index.html 1984~1995행, 2044행

`recFormat`이 `'mp3'`일 때 `saveRecordedBlob()`은 확장자를 `.mp3`, MIME을 `audio/mpeg`으로 설정한다. 그러나 `MediaRecorder`는 항상 `audio/webm;codecs=opus`로 녹음한다(2044행). 결과적으로 WebM 바이너리에 `.mp3` 확장자가 붙은 파일이 생성되며, 대부분의 플레이어에서 재생 불가능하다.

**수정안**: MP3 인코딩은 브라우저 MediaRecorder로 불가능하므로, 옵션에서 MP3를 제거하거나, WebAssembly 기반 LAME 인코더(lamejs)를 도입해야 한다. 당장은 MP3 옵션을 비활성화하고 사용자에게 WebM만 지원한다고 안내하는 것이 현실적이다.

### 2-2. Service Worker 캐시 폴백 체이닝 오류 [MEDIUM]

**위치**: sw.js 46행

```javascript
.catch(() => caches.match('/') || caches.match(request))
```

`caches.match('/')`는 Promise를 반환한다. Promise 객체는 항상 truthy이므로, `||` 뒤의 `caches.match(request)`는 절대 실행되지 않는다.

**수정안**:
```javascript
.catch(async () => (await caches.match('/')) || (await caches.match(request)))
```

### 2-3. KBS 편성표 시간대 불일치 [MEDIUM]

**위치**: worker.js 928~932행

```javascript
const now = new Date();
const nowTime = now.getHours() * 10000 + now.getMinutes() * 100 + now.getSeconds();
```

Cloudflare Workers는 UTC 시간대에서 실행된다. KBS API의 `service_start_time`/`service_end_time`은 KST(UTC+9) 기준이다. 따라서 UTC 기준 `nowTime`과 KST 기준 편성 시간을 직접 비교하면, 9시간의 차이로 잘못된 프로그램명이 표시된다.

**수정안**:
```javascript
const now = new Date();
const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
const nowTime = kst.getUTCHours() * 10000 + kst.getUTCMinutes() * 100 + kst.getUTCSeconds();
```

### 2-4. 리플레이 탐색바가 AudioContext 절대시간을 사용 [MEDIUM]

**위치**: index.html 2209행

```javascript
const elapsed = audioCtx.currentTime;
```

`audioCtx.currentTime`은 AudioContext 생성 이후의 전체 경과 시간이다. 리플레이 시작 시점의 AudioContext 시간을 기록해두지 않으면, 이전 라이브 재생 등으로 이미 큰 값이 되어 있어서 탐색바가 즉시 100%에 도달하거나 비정상적인 값을 표시한다.

**수정안**: 리플레이 시작 시 기준 시간을 기록한다.

```javascript
// startReplay() 내에 추가
let replayStartCtxTime = 0;  // 전역 변수로 선언
replayStartCtxTime = audioCtx.currentTime;

// replayFeedLoop() 내에서 변경
const elapsed = audioCtx.currentTime - replayStartCtxTime;
```

### 2-5. CH5 라이브 → 파일 모드 전환 시 이중 타이머 [LOW]

**위치**: index.html 1737~1744행, 1753~1764행

CH5 진입 시 라이브 상태가 감지되면 `trackRefreshTimer`를 설정하고 `return`한다(1744행). 라이브 종료 후 `startCh5Polling()`이 호출되면(2111행), `pollCh5State()`가 파일 모드를 감지하여 새 Howl을 생성한다. 이때 기존 `trackRefreshTimer`는 여전히 돌고 있어 불필요한 fetch가 발생한다.

**수정안**: `startCh5Polling()` 진입 시 `clearInterval(trackRefreshTimer)`를 추가한다.

---

## 3. 보안 취약점

### 3-1. XSS: innerHTML에 비정제 트랙명 삽입 [HIGH]

**위치**: index.html 다수 (2302행, 2333행, 2491~2492행 등)

`renderAdminTrackList()`, `updateTrackListUI()`, `loadPastBroadcasts()` 등에서 서버 응답의 트랙명을 `innerHTML`로 직접 삽입한다. R2에 업로드된 파일명에 `<img onerror=alert(1)>`과 같은 HTML이 포함되면 XSS가 발생한다.

**수정안**: `textContent`를 사용하거나, 최소한 HTML 이스케이프 함수를 적용한다.

```javascript
function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
```

### 3-2. CORS 허용 정책이 모든 Origin을 반영 [MEDIUM]

**위치**: worker.js 948~956행

```javascript
const origin = request.headers.get('Origin') || '*';
return { 'Access-Control-Allow-Origin': origin, ... };
```

요청의 Origin 헤더를 그대로 반사(reflect)하므로, 어떤 도메인에서든 API 호출이 가능하다. 관리자 API는 Bearer 토큰으로 보호되어 있으나, 공개 API(/api/tracks, /api/stream 등)는 무제한 접근이 가능하다.

**수정안**: 허용 도메인 목록을 정의한다.

```javascript
const ALLOWED_ORIGINS = [
  'https://radio-axi.pages.dev',
  'https://yebomradio.workers.dev',
  'http://localhost:8787'
];
function corsHeaders(request) {
  const origin = request.headers.get('Origin') || '';
  const allowed = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return { 'Access-Control-Allow-Origin': allowed, ... };
}
```

---

## 4. 성능 및 효율성

### 4-1. 백그라운드 탭에서 불필요한 폴링 지속 [MEDIUM]

**위치**: index.html — ch5PollTimer(10초), livePollTimer(2초), kbsRefreshTimer(60초), rscRefreshTimer(30초)

탭이 백그라운드일 때도 setInterval이 계속 fetch 요청을 발생시킨다. 특히 라이브 폴링(2초 간격)은 불필요한 네트워크 트래픽과 Workers 호출량을 유발한다.

**수정안**: `visibilitychange`에서 폴링을 일시중지/재개한다.

```javascript
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    clearInterval(ch5PollTimer);
    clearInterval(livePollTimer);
  } else {
    // 복귀 시 즉시 한 번 폴링 후 타이머 재시작
    if (liveMode) {
      livePollAndPlay();
      livePollTimer = setInterval(livePollAndPlay, 2000);
    }
    if (currentChannel === 5 && !liveMode) {
      pollCh5State();
      ch5PollTimer = setInterval(pollCh5State, 10000);
    }
  }
});
```

### 4-2. 등잔 Canvas 애니메이션의 지속 실행 [LOW]

**위치**: index.html 1232~1256행

CH3 등잔 애니메이션은 `requestAnimationFrame`으로 매 프레임 Canvas를 그린다. 탭이 백그라운드일 때 rAF는 자동으로 throttle되지만, `visibilitychange`에서 명시적으로 정지하면 CPU/배터리 절약이 가능하다.

### 4-3. R2 list 1000건 제한 [LOW]

**위치**: worker.js 44행

```javascript
const list = await env.RADIO_BUCKET.list({ prefix, limit: 1000 });
```

채널당 1000개 파일을 초과하면 목록이 잘린다. 현재 규모에서는 문제없으나, `list.truncated`를 확인하고 cursor로 추가 fetch하는 페이지네이션을 미리 구현해두는 것이 안전하다.

### 4-4. 라이브 세션 종료 시 totalSize 추정값 사용 [LOW]

**위치**: worker.js 534행

```javascript
s.totalSize = s.chunkCount * 32000; // 하드코딩된 32KB
```

실제 청크 크기는 오디오 내용에 따라 달라지는데, 종료 시 `chunkCount * 32000`으로 일괄 추정한다. 이로 인해 보존 정책(storageLimit)의 사용량 계산이 부정확해질 수 있다. 청크 업로드 시 누적된 `session.totalSize`를 그대로 사용하는 것이 정확하다.

---

## 5. 안정성 개선

### 5-1. handlePlayPause에서 CH5 리플레이 재시작 미지원 [MEDIUM]

**위치**: index.html 1639~1642행

```javascript
if (replayMode) {
  if (isPlaying) { stopReplay(); isPlaying = false; updatePlayBtn(false); }
  return;  // ← 정지만 가능, 다시 시작 불가
}
```

리플레이 모드에서 일시정지 후 재시작할 방법이 없다. 정지하면 리플레이가 완전히 종료되어 처음부터 다시 시작해야 한다.

### 5-2. 볼륨 경로 이원화로 인한 불일치 가능성 [MEDIUM]

**위치**: index.html 2876~2886행

볼륨 제어 경로가 세 갈래로 나뉜다: gainNode(AudioContext 활성 시), currentHowl.volume()(Howler 직접), audioEl.volume(HLS 직접). 어떤 경로가 활성인지의 판단 조건(`hlsSourceNode`, `_acConnected`)이 채널 전환과 녹음 시작/종료에 따라 복잡하게 변화하여, 특정 시나리오에서 볼륨 슬라이더가 작동하지 않는 현상이 발생할 수 있다.

**수정안**: 볼륨 변경 시 모든 경로에 일괄 적용하는 방식으로 단순화한다.

```javascript
function applyVolume(v) {
  if (gainNode) gainNode.gain.value = v;
  if (currentHowl) currentHowl.volume(v);
  if (audioEl) audioEl.volume = v;
}
```

### 5-3. 수면 타이머 정확도 [MEDIUM]

**위치**: index.html 2254~2264행

`setTimeout`과 `setInterval`은 백그라운드 탭에서 최소 1분 간격으로 throttle된다. 30분 수면 타이머를 설정하고 탭을 백그라운드로 보내면, 실제 종료 시점이 수분 이상 지연될 수 있다.

**수정안**: `setTimeout` 대신 목표 시각을 기록하고, `visibilitychange`에서 확인한다.

```javascript
let sleepTargetTime = 0;
function setSleepTimer(seconds) {
  sleepTargetTime = Date.now() + seconds * 1000;
  // ... 기존 UI 코드 유지 ...
}
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && sleepTargetTime > 0 && Date.now() >= sleepTargetTime) {
    stopPlayback(); stopRecording();
    sleepSecs = 0; sleepTargetTime = 0;
    showToast('수면 타이머가 종료되었습니다');
    updateSleepUI();
  }
});
```

### 5-4. MediaSession 갱신 누락 [MEDIUM]

**위치**: index.html 1382~1407행

`updateMediaSession()`은 `enterChannel`, `playTrack`, `refreshLiveNowPlaying` 등에서 호출되지만, 라이브 청크 플레이어 시작 시(`startLivePlayer`)와 리플레이 시작 시(`startReplay`)에는 호출되지 않는다. 잠금화면에서 이전 채널 정보가 계속 표시된다.

---

## 6. 코드 품질

### 6-1. 단일 파일 3,188줄의 유지보수 부담

index.html에 CSS, HTML, JavaScript가 모두 인라인되어 있다. 빌드 도구를 사용하지 않는 설계 원칙은 이해하지만, 최소한 JavaScript를 `app.js`로 분리하면 개발 편의성과 캐싱 효율이 개선된다. HTML이 변경되지 않았을 때 JS 캐시만 무효화할 수 있어 업데이트 트래픽도 줄어든다.

### 6-2. 전역 변수 과다 (약 70개)

`let`으로 선언된 전역 변수가 약 70개에 달한다. 상태 간 의도치 않은 간섭이 발생할 수 있으며, 이름 충돌 위험이 있다. 객체로 그룹화하는 것을 권장한다.

```javascript
const State = {
  channel: { current: 1, focused: 0, active: [] },
  player: { isPlaying: false, howl: null, hls: null, audioEl: null },
  live: { mode: false, sessionId: null, polling: null },
  // ...
};
```

---

## 7. 우선순위별 실행 계획

| 순위 | 항목 | 심각도 | 예상 난이도 |
|:---:|------|:------:|:----------:|
| 1 | 1-1. AudioContext visibilitychange 복구 | CRITICAL | 낮음 |
| 2 | 1-3. ensureLiveAudioCtx await 추가 | HIGH | 낮음 |
| 3 | 1-2. 무음 audio 앵커 (라이브/리플레이) | CRITICAL | 중간 |
| 4 | 1-5. HLS 비치명적 오류 복구 | HIGH | 낮음 |
| 5 | 2-3. KBS 시간대 UTC→KST 보정 | MEDIUM | 낮음 |
| 6 | 3-1. XSS innerHTML 정제 | HIGH | 낮음 |
| 7 | 2-1. 녹음 MP3 옵션 비활성화 | HIGH | 낮음 |
| 8 | 5-2. 볼륨 경로 일원화 | MEDIUM | 중간 |
| 9 | 4-1. 백그라운드 폴링 일시중지 | MEDIUM | 중간 |
| 10 | 2-2. SW 캐시 폴백 수정 | MEDIUM | 낮음 |
| 11 | 2-4. 리플레이 탐색바 기준시간 | MEDIUM | 낮음 |
| 12 | 5-3. 수면 타이머 목표시각 방식 | MEDIUM | 낮음 |
| 13 | 1-4. Howler AudioContext 유령노드 정리 | HIGH | 중간 |
| 14 | 5-4. MediaSession 라이브/리플레이 갱신 | MEDIUM | 낮음 |
| 15 | 3-2. CORS Origin 제한 | MEDIUM | 낮음 |
| 16 | 5-1. 리플레이 일시정지/재개 | MEDIUM | 중간 |
| 17 | 4-4. 세션 totalSize 정확도 | LOW | 낮음 |
| 18 | 2-5. CH5 타이머 정리 | LOW | 낮음 |
| 19 | 4-2. 등잔 애니메이션 백그라운드 정지 | LOW | 낮음 |
| 20 | 4-3. R2 list 페이지네이션 | LOW | 중간 |

---

## 8. 결론

사용자가 보고한 "화면보호기 진입 시 소리 멈춤"과 "화면은 재생인데 무음"은 모두 **AudioContext 서스펜션 미복구**(1-1)와 **audio 요소 부재로 인한 백그라운드 미디어 세션 미등록**(1-2)이 핵심 원인이다. 이 두 항목만 수정해도 체감 안정성이 크게 향상된다. 나머지 항목은 점진적으로 적용하되, XSS 방지(3-1)와 KBS 시간대 보정(2-3)은 조기에 처리하는 것을 권장한다.

전반적으로 예봄라디오 2.0은 단일 HTML 파일 기반임에도 불구하고, 6개 채널의 이질적인 오디오 소스(HLS, Icecast, R2, AudioContext 스케줄링)를 하나의 일관된 UX로 통합한 매우 높은 완성도의 프로젝트다. 위 개선 사항을 적용하면 모바일 환경에서의 안정성이 한 단계 더 올라갈 것이다.
