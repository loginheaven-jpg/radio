# 예봄라디오 2.0 — 완전한 설계 및 구축 가이드

---

## ⚠️ 이 문서를 읽는 AI에게 — 반드시 먼저 읽을 것

### 폴더 구성

```
radio-integrated/
  ├── DESIGN_GUIDE.md      ← 이 문서. 설계 명세의 전부
  ├── prev-radio/          ← 이전에 만든 간이 라디오 소스
  │     ├── worker.js      ← R2 스트리밍 + KV 상태관리 검증된 코드
  │     ├── wrangler.toml  ← 실제 버킷명 + KV ID (그대로 사용)
  │     └── index.html     ← 간이 프론트엔드 (참고용)
  └── personal-radio/      ← 이전에 만든 작동하던 예봄라디오 소스 (레퍼런스 전용)
        ├── ARCHITECTURE.md
        ├── server/febcScheduleProxy.ts
        └── client/src/pages/Home.tsx
```

### 작업 전 필독 파일 (이 순서대로)

```
1. 이 문서(DESIGN_GUIDE.md) 전체
2. prev-radio/worker.js          — R2/KV 실제 작동 패턴
3. prev-radio/wrangler.toml      — 버킷명/KV ID 확인
4. personal-radio/ARCHITECTURE.md
5. personal-radio/server/febcScheduleProxy.ts
6. personal-radio/client/src/pages/Home.tsx
```

### 절대 원칙

```
금지: Manus OAuth, tRPC, Drizzle, Express, React, Vite, 빌드 도구
허용: Vanilla JS, Cloudflare Workers, R2, KV
결과물: worker.js + index.html + manifest.json + sw.js (4개만)
```

---

## 1. 프로젝트 개요

| 항목 | 내용 |
|---|---|
| 앱명 | 예봄라디오 2.0 |
| 인프라 | Cloudflare Workers + R2 + KV + Pages |
| 프론트엔드 | 단일 index.html (Vanilla JS, 빌드 없음) |
| 인증 | Admin Key — Bearer 토큰 방식 |
| 기반 코드 | prev-radio/worker.js의 R2/KV 패턴을 확장 |

---

## 2. 채널 구성 (5채널)

| # | 채널명 | 유형 | 데이터 소스 | 색상 |
|---|---|---|---|---|
| 1 | KBS 클래식 FM | HLS 라이브 | KBS API 동적 조회 | `#C4B5FD` 라벤더 |
| 2 | 극동방송 | HLS 라이브 | 고정 m3u8 | `#FBBF9A` 살구 |
| 3 | 말씀전당 | R2 개인선택 | `radio/channel-list1/` | `#86EFAC` 민트 |
| 4 | 찬양의 숲 | R2 개인선택 | `radio/channel-list2/` | `#FCD34D` 골드 |
| 5 | 예봄소리 | R2 공유스트리밍 | `radio/channel-stream/` | `#F59E0B` 앰버 |

### 채널 1, 2 — HLS 라이브
- 재생위치 복원 없음 (라이브)
- 현재 방송명 표시 (60초 갱신)
- 녹음 버튼 (로컬 녹음서버 `http://localhost:8090` 연동)
- 마지막 선택 채널만 localStorage 기억

### 채널 3, 4 — R2 개인선택 플레이어
- 동일 UI/로직, R2 경로만 다름
- 곡명·순서는 R2의 `_meta.json`에 저장
- 목록 팝업, 셔플, 반복, 재생속도 조절
- **이어듣기: 채널 + 트랙 + 재생위치 완전 복원 (섹션 6)**

### 채널 5 — 예봄소리 공유스트리밍
- 관리자 ON AIR → KV에 재생 상태 저장
- 청취자는 10초마다 KV polling → 오프셋 계산 → 동기화
- 이어듣기 없음 (항상 현재 위치 동기화)

---

## 3. R2 버킷 구조

기존 `coachdb-files` 버킷을 그대로 사용한다.
**버킷명과 KV ID는 prev-radio/wrangler.toml에서 확인한다.**

```
coachdb-files/
  ├── backups/                  ← 기존 유지
  ├── uploads/                  ← 기존 유지
  └── radio/
        ├── channel-stream/     ← 채널5 예봄소리 음원   [생성 완료]
        ├── channel-list1/      ← 채널3 말씀전당 음원   [생성 완료]
        │     └── _meta.json    ← Workers가 자동 생성/관리
        └── channel-list2/      ← 채널4 찬양의 숲 음원  [수작업 생성 필요]
              └── _meta.json
```

### _meta.json 구조
```json
[
  {
    "key": "radio/channel-list1/sermon_001.mp3",
    "name": "요한복음 3장 16절",
    "order": 0
  },
  {
    "key": "radio/channel-list1/sermon_002.mp3",
    "name": "시편 23편",
    "order": 1
  }
]
```

- `key` — R2 오브젝트 전체 경로 (스트리밍 URL 생성에 사용)
- `name` — 화면 표출 곡명 (업로드 시 입력, 미입력 시 파일명에서 확장자 제거)
- `order` — 재생 순서 (0부터 시작, 드래그 변경 후 전체 재저장)

---

## 4. Workers API 전체 설계

### 기반 코드
> `prev-radio/worker.js`의 다음 패턴을 그대로 재사용한다:
> - CORS 헤더 처리
> - R2 Range Request 스트리밍 (`/api/stream/`)
> - KV 상태 읽기/쓰기 (`/api/ch1/state` → `/api/ch5/state`로 경로만 변경)
> - Admin Key 인증 (`isAdmin()` 함수)
> - `parseRange()`, `decodeFileName()` 유틸 함수

### 엔드포인트 목록

| Method | Path | 설명 | 인증 |
|---|---|---|---|
| GET | `/api/tracks?channel=list1\|list2\|stream` | 트랙 목록 (_meta.json 기준) | 없음 |
| GET | `/api/stream/:key` | R2 음원 Range Request 스트리밍 | 없음 |
| GET | `/api/ch5/state` | 채널5 현재 재생 상태 (KV) | 없음 |
| POST | `/api/ch5/state` | 채널5 재생 상태 변경 (KV) | Admin |
| POST | `/api/upload` | 음원 R2 업로드 + _meta.json 갱신 | Admin |
| POST | `/api/delete` | 음원 R2 삭제 + _meta.json 갱신 | Admin |
| POST | `/api/meta` | _meta.json 전체 덮어쓰기 (순서/곡명 변경) | Admin |
| GET | `/api/febc-schedule` | 극동방송 편성표 서버 프록시 (60초 캐시) | 없음 |
| GET | `/api/kbs` | KBS 스트리밍 URL + 현재 방송명 (서버 프록시) | 없음 |

### channel 파라미터 → R2 경로 매핑
```js
// prev-radio/worker.js의 DIR_MAP 패턴 확장
const DIR_MAP = {
  list1:  'radio/channel-list1/',
  list2:  'radio/channel-list2/',
  stream: 'radio/channel-stream/',
};
```

### `/api/tracks` 상세 로직
```js
// 1. R2 list({ prefix }) 로 파일 목록 조회
// 2. _meta.json 읽기 시도
// 3. meta 있으면: meta 기준으로 정렬, R2에 없는 항목 제거
// 4. meta 없으면: R2 목록에서 파일명 기준으로 생성
// 응답: [{ key, name, size, order }, ...]
```

### `/api/upload` 상세 로직
```js
// 1. FormData에서 file, channel, name 추출
// 2. R2에 파일 저장: `radio/{dir}/{filename}`
// 3. _meta.json 읽기 (없으면 [])
// 4. name이 비어있으면 파일명에서 확장자 제거하여 사용
// 5. 새 항목 push: { key, name, order: (현재최대order + 1) }
// 6. _meta.json 저장 (R2에 put)
// 7. 응답: { ok: true, track: { key, name, order } }
```

### `/api/delete` 상세 로직
```js
// 1. R2 파일 삭제
// 2. _meta.json에서 해당 key 항목 제거
// 3. order 재할당 (0부터 순서대로)
// 4. _meta.json 저장
```

### `/api/meta` POST
```js
// Body: { channel: 'list1', tracks: [{ key, name, order }, ...] }
// _meta.json 전체를 받은 배열로 덮어쓰기
// 순서 변경, 곡명 일괄 수정에 사용
```

### `/api/ch5/state` — KV 구조
```js
// GET 응답 (KV에 없으면 기본값 반환)
{
  trackKey: 'radio/channel-stream/song.mp3',  // null이면 방송 없음
  trackName: '요한복음 강해',
  duration: 2720,          // 초
  paused: false,
  startEpoch: 1709123456789,  // Date.now() - currentTime*1000
  updatedAt: 1709123456789,
}

// 클라이언트의 현재 재생 위치 계산
const currentTime = state.paused
  ? state.currentTime
  : (Date.now() - state.startEpoch) / 1000;
```

### `/api/febc-schedule` — 서버 프록시
```js
// personal-radio/server/febcScheduleProxy.ts 로직을 Workers에 이식
// CORS 불허 사이트라 반드시 서버 사이드 프록시 필요

let febcCache = { data: null, ts: 0 };

async function getFebcSchedule() {
  if (febcCache.data && Date.now() - febcCache.ts < 60000) {
    return febcCache.data;
  }
  try {
    const res = await fetch('https://seoul.febc.net/radio/schedule/live/1', {
      signal: AbortSignal.timeout(8000),
    });
    const html = await res.text();
    const match = html.match(/<p\s+class="tit">([^<]+)<\/p>/);
    const data = { programTitle: match ? match[1].trim() : null };
    febcCache = { data, ts: Date.now() };
    return data;
  } catch {
    return { programTitle: null };
  }
}
```
### `/api/kbs` — KBS 서버 프록시 (CORS 대응)

KBS API는 현재 CORS를 허용하지만 정책 변경 시 즉시 중단된다.
스트리밍 URL 획득과 현재 방송명 조회를 Workers에서 대신 호출한다.

// 클라이언트는 /api/kbs 하나만 호출 → { streamUrl, programTitle }
// KBS가 CORS를 바꾸거나 API 경로를 바꿔도 worker.js만 수정하면 끝

let kbsCache = { data: null, ts: 0 };

async function getKbsInfo() {
  if (kbsCache.data && Date.now() - kbsCache.ts < 60000) {
    return kbsCache.data;
  }
  try {
    // ① 스트리밍 URL 획득
    const streamRes = await fetch(
      'https://cfpwwwapi.kbs.co.kr/api/v1/landing/live/channel_code/24',
      { headers: { Referer: 'https://onair.kbs.co.kr/' } }
    );
    const streamData = await streamRes.json();
    const radio = streamData.channel_item?.find(i => i.media_type === 'radio');
    const streamUrl = radio?.service_url
      ?? 'https://1fm.gscdn.kbs.co.kr/1fm_192_2.m3u8';

    // ② 현재 방송명 조회
    const schedRes = await fetch(
      'https://static.api.kbs.co.kr/mediafactory/v1/schedule/onair_now' +
      '?rtype=json&local_station_code=00&channel_code=24'
    );
    const schedData = await schedRes.json();
    const schedules = schedData[0]?.schedules ?? [];
    // 현재 시각에 해당하는 프로그램 찾기 (Workers 환경에서 Date.now() 사용)
    const now = new Date();
    const nowTime = now.getHours() * 10000 + now.getMinutes() * 100 + now.getSeconds();
    const current = schedules.find(s =>
      parseInt(s.service_start_time) <= nowTime &&
      nowTime < parseInt(s.service_end_time)
    ) ?? schedules[0];
    const programTitle = current?.program_title ?? null;

    const data = { streamUrl, programTitle };
    kbsCache = { data, ts: Date.now() };
    return data;
  } catch {
    return {
      streamUrl: 'https://1fm.gscdn.kbs.co.kr/1fm_192_2.m3u8',
      programTitle: null,
    };
  }
}

---

## 5. WORKER_URL 설정 — 프론트엔드 연결

프론트엔드(index.html)는 배포된 Workers URL을 알아야 한다.
`wrangler deploy` 후 출력되는 URL이 WORKER_URL이다.

```
예시: https://radio-worker.your-account.workers.dev
```

### WORKER_URL 관리 방법

```js
// index.html 상단에 전역 변수로 선언
// 첫 실행 시 localStorage에 없으면 사용자에게 입력 받음
let WORKER_URL = localStorage.getItem('radio-worker-url') || '';

async function ensureWorkerUrl() {
  if (WORKER_URL) return;
  WORKER_URL = prompt(
    'Workers URL을 입력하세요\n예: https://radio-worker.xxx.workers.dev'
  )?.trim() ?? '';
  if (WORKER_URL) localStorage.setItem('radio-worker-url', WORKER_URL);
}

// 앱 시작 시
await ensureWorkerUrl();
```

### Workers CORS 설정 — 필수

worker.js에서 모든 응답에 아래 헤더를 포함해야 한다.
Pages 도메인(`.pages.dev`)과 커스텀 도메인 모두 허용한다.

```js
// worker.js 최상단에 CORS 헬퍼 정의
function corsHeaders(request) {
  const origin = request.headers.get('Origin') || '*';
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Max-Age': '86400',
  };
}

// OPTIONS preflight 처리 (fetch 핸들러 최상단)
if (request.method === 'OPTIONS') {
  return new Response(null, { headers: corsHeaders(request) });
}

// 모든 응답에 CORS 헤더 포함
return new Response(body, {
  status: 200,
  headers: { ...corsHeaders(request), 'Content-Type': 'application/json' },
});
```

---

## 6. wrangler.toml

```toml
name = "radio-worker"
main = "worker.js"
compatibility_date = "2024-01-01"

[[r2_buckets]]
binding = "RADIO_BUCKET"
bucket_name = "coachdb-files"   # prev-radio/wrangler.toml에서 확인

[[kv_namespaces]]
binding = "RADIO_KV"
id = "PREV_RADIO_KV_ID"         # prev-radio/wrangler.toml에서 그대로 복사

# ADMIN_KEY는 Secret으로 별도 설정
# wrangler secret put ADMIN_KEY
```

> **중요**: bucket_name과 KV id는 새로 만들지 않는다.
> `prev-radio/wrangler.toml`에 이미 실제 값이 있다. 그대로 복사한다.

---

## 7. 이어듣기 — 정밀 구현 명세

### 저장 대상
채널 3, 4만 해당. 채널 1, 2는 라이브(위치 무의미), 채널 5는 서버 동기화.

### localStorage 키 설계
```js
'radio-last-channel'   // 마지막 선택 채널 번호 문자열 ('1'~'5')
'radio-ch3-resume'     // 채널3 이어듣기 상태 (JSON)
'radio-ch4-resume'     // 채널4 이어듣기 상태 (JSON)
'radio-volume'         // 볼륨 0.0~1.0

// resume JSON 구조
{
  trackKey:  'radio/channel-list1/sermon_001.mp3',
  trackName: '요한복음 3장 16절',
  position:  312.5,       // 초, 소수점 1자리
  savedAt:   1709123456789 // Date.now()
}
```

### 저장 — 4중 전략 (모든 종료 상황 대응)

```js
function saveResume(channel) {
  if (channel < 3 || channel > 4) return;
  if (!currentTrackKey) return;
  const position = howl ? Math.round(howl.seek() * 10) / 10 : 0;
  if (position < 3) return; // 3초 미만은 저장 안 함 (의미없는 복원 방지)
  localStorage.setItem(`radio-ch${channel}-resume`, JSON.stringify({
    trackKey:  currentTrackKey,
    trackName: currentTrackName,
    position,
    savedAt: Date.now(),
  }));
}

// ① 5초마다 자동 저장 — PC 강제종료 시에도 최대 5초 손실
setInterval(() => {
  if (isPlaying && (currentChannel === 3 || currentChannel === 4)) {
    saveResume(currentChannel);
  }
}, 5000);

// ② 탭/브라우저 닫기
window.addEventListener('beforeunload', () => saveResume(currentChannel));

// ③ 모바일: 홈버튼/다른 앱으로 전환
window.addEventListener('pagehide', () => saveResume(currentChannel));

// ④ 화면 잠금 / 앱 백그라운드 전환
document.addEventListener('visibilitychange', () => {
  if (document.hidden) saveResume(currentChannel);
});
```

### 복원 — 2단계 유효성 검사 필수

```js
async function restoreResume(channel) {
  const raw = localStorage.getItem(`radio-ch${channel}-resume`);
  if (!raw) return null;

  let resume;
  try { resume = JSON.parse(raw); }
  catch { localStorage.removeItem(`radio-ch${channel}-resume`); return null; }

  // 검사 1: 7일 초과 데이터 폐기
  if (Date.now() - resume.savedAt > 7 * 24 * 60 * 60 * 1000) {
    localStorage.removeItem(`radio-ch${channel}-resume`);
    return null;
  }

  // 검사 2: 해당 파일이 R2에 현재 존재하는지 확인
  // (관리자가 삭제했을 수 있음)
  const tracks = await fetchTracks(channel);
  if (!tracks.some(t => t.key === resume.trackKey)) {
    localStorage.removeItem(`radio-ch${channel}-resume`);
    return null; // 존재하지 않으면 첫 번째 트랙으로
  }

  return resume; // { trackKey, trackName, position }
}
```

### 채널 진입 시 복원 실행

```js
async function enterChannel(channel) {
  // 채널 번호 저장
  localStorage.setItem('radio-last-channel', String(channel));

  if (channel === 3 || channel === 4) {
    const tracks = await fetchTracks(channel);
    const resume = await restoreResume(channel);

    if (resume) {
      // 해당 트랙의 인덱스를 찾아 그 위치부터 재생
      const idx = tracks.findIndex(t => t.key === resume.trackKey);
      playTrack(channel, idx >= 0 ? idx : 0, resume.position);
      showToast(`↩ ${resume.trackName} — ${formatTime(resume.position)}부터 이어듣기`);
    } else {
      playTrack(channel, 0, 0);
    }
  }
}
```

### 트랙 삭제 시 resume cleanup

```js
// Admin이 트랙 삭제할 때 반드시 호출
function cleanupResumeOnDelete(deletedKey) {
  ['radio-ch3-resume', 'radio-ch4-resume'].forEach(storageKey => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) return;
      const resume = JSON.parse(raw);
      if (resume.trackKey === deletedKey) {
        localStorage.removeItem(storageKey);
      }
    } catch {}
  });
}
```

### 앱 시작 시 채널 복원

```js
window.addEventListener('DOMContentLoaded', async () => {
  const lastChannel = parseInt(localStorage.getItem('radio-last-channel') ?? '1');
  await enterChannel(lastChannel);
});
```

---

## 8. 디자인 설계

### 컨셉: "새벽 주파수" (Dawn Frequency)
예봄라디오의 새벽 글래스모피즘 + prev-radio의 빈티지 앰버 방송국 감성 융합.

### CSS 변수 (전체)

```css
:root {
  /* 배경 */
  --bg-deep:      #0D0B1A;
  --bg-mid:       #1A1035;
  --bg-surface:   rgba(255, 255, 255, 0.06);
  --border-glass: rgba(255, 255, 255, 0.10);

  /* 브랜드 앰버 (prev-radio에서 이식) */
  --amber:        #F59E0B;
  --amber-warm:   #FBBF24;
  --amber-glow:   rgba(245, 158, 11, 0.25);

  /* 채널별 컬러 (예봄라디오에서 이식) */
  --ch1-color:    #C4B5FD;  /* 라벤더 — KBS 클래식 */
  --ch2-color:    #FBBF9A;  /* 살구   — 극동방송 */
  --ch3-color:    #86EFAC;  /* 민트   — 말씀전당 */
  --ch4-color:    #FCD34D;  /* 골드   — 찬양의 숲 */
  --ch5-color:    #F59E0B;  /* 앰버   — 예봄소리 */

  /* 텍스트 */
  --text:         #E8E4F0;
  --text-dim:     #7C7A99;
  --text-mute:    #3D3B55;

  /* 상태 */
  --red:          #EF4444;
  --green:        #22C55E;
}
```

### 시간대별 배경 그라데이션 (예봄라디오에서 이식)

```js
// personal-radio/client/src/index.css 의 시간대 테마 참조
const TIME_THEMES = {
  dawn:      { hours: [4,5,6],            bg: 'linear-gradient(135deg, #0F0E1A, #1A1035, #0D1B2A)' },
  morning:   { hours: [7,8,9,10,11],      bg: 'linear-gradient(135deg, #1A0F2E, #2D1B69, #1E3A5F)' },
  afternoon: { hours: [12,13,14,15,16],   bg: 'linear-gradient(135deg, #0C1445, #1A2980, #26D0CE)' },
  evening:   { hours: [17,18,19,20],      bg: 'linear-gradient(135deg, #1A0A0A, #3D1A1A, #2D1B4E)' },
  night:     { hours: [21,22,23,0,1,2,3], bg: 'linear-gradient(135deg, #050510, #0A0A1A, #0D0B1E)' },
};

function applyTimeTheme() {
  const hour = new Date().getHours();
  const theme = Object.values(TIME_THEMES).find(t => t.hours.includes(hour));
  if (theme) document.body.style.background = theme.bg;
}
applyTimeTheme();
setInterval(applyTimeTheme, 60000); // 1분마다 체크
```

### 타이포그래피

```html
<!-- index.html <head>에 추가 -->
<link href="https://fonts.googleapis.com/css2?
  family=Noto+Serif+KR:wght@300;400;700&
  family=Bebas+Neue&
  family=Noto+Sans+KR:wght@300;400;500&
  display=swap" rel="stylesheet">
```

```css
/* 채널명, 타이틀 — 예봄라디오 */
.ch-name, .track-title { font-family: 'Noto Serif KR', serif; }

/* 주파수, 숫자, LIVE 뱃지 — prev-radio */
.frequency, .badge, .timer { font-family: 'Bebas Neue', sans-serif; }

/* 본문, UI 버튼 */
body { font-family: 'Noto Sans KR', sans-serif; }
```

### 글래스모피즘 플레이어 카드

```css
.player-card {
  background: rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 20px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  position: relative;
  overflow: hidden;
}

/* 채널별 컬러 상단 강조선 */
.player-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: var(--current-ch-color);
  box-shadow: 0 0 20px var(--current-ch-color);
}

/* 재생 중일 때 카드 활성화 효과 */
.player-card.playing {
  border-color: rgba(255, 255, 255, 0.18);
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.5),
              0 0 30px var(--current-ch-color-dim);
}
```

### 전체 레이아웃 구조

```
┌──────────────────────────────┐  max-width: 480px
│  HEADER                      │
│  예봄라디오         [시계]    │
│  [⚙ 설정버튼 — 로고 3탭=Admin]│
├──────────────────────────────┤
│  CHANNEL TABS (가로 스크롤)  │
│  [KBS][극동][말씀][찬양][예봄]│
├──────────────────────────────┤
│  PLAYER CARD                 │
│  ▔▔▔ 채널컬러 라인 ▔▔▔▔▔▔▔  │
│  채널명 (Noto Serif KR)      │
│  현재 방송/곡명               │
│  ▌▌▌▌▌▌ 비주얼라이저 ▌▌▌▌▌▌  │
│  ━━━━━━●━━━━━━━ 시크바       │  (채널 3,4,5만)
│  00:00              00:00    │
│  [⏮] [▶/⏸] [⏭]   [🔉────]  │
│  [0.75×][1×][1.25×][1.5×]   │  (채널 3,4,5만)
│  [🎙녹음]                    │  (채널 1,2만)
│  [💤타이머][📋목록]           │
├──────────────────────────────┤
│  TRACK LIST PANEL (슬라이드업)│  (채널 3,4,5)
│  목록 ────────────   [✕]     │
│  ▶ 요한복음 3장  45:20       │  현재곡 하이라이트
│    시편 23편     32:15       │
└──────────────────────────────┘
```

---

## 9. Admin UI 설계

### 접근 방법
헤더 로고(또는 앱명 텍스트)를 **3번 연속 탭** → Admin Key 입력 모달  
인증 성공 → Admin 패널 오버레이 열림

### 채널 3, 4 관리자 패널

```
ADMIN ──────────────────────── [✕]

채널 선택:  [말씀전당] [찬양의 숲] [예봄소리]

┌──────────────────────────────┐
│  ♫  파일을 드래그하거나       │  ← 드롭존
│     클릭하여 선택             │
│  MP3 M4A OGG WAV FLAC       │
└──────────────────────────────┘

업로드 대기 목록:
  [sermon_001       ] [✕]     ← 파일명이 default값, 수정 가능
  [시편_20240322    ] [✕]
                 [모두 업로드]

──── 등록된 목록 ────── [새로고침]

  ≡  요한복음 3장 16절    [🗑]   ← ≡ 드래그 핸들
  ≡  시편 23편            [🗑]
  ≡  마태복음 5장         [🗑]

                     [순서 저장]
```

### 업로드 입력칸 — 파일명 default 처리

```js
function handleFiles(fileList) {
  Array.from(fileList)
    .filter(f => /\.(mp3|m4a|ogg|wav|flac|aac)$/i.test(f.name))
    .forEach(file => {
      const defaultName = file.name.replace(/\.[^/.]+$/, ''); // 확장자 제거
      uploadQueue.push({ file, name: defaultName });
      // UI에 입력칸 렌더링: value = defaultName (사용자 수정 가능)
    });
}

async function uploadAll() {
  for (const item of uploadQueue) {
    const fd = new FormData();
    fd.append('files', item.file);
    fd.append('channel', uploadChannel);  // 'list1' or 'list2' or 'stream'
    fd.append('name', item.name);         // 입력칸의 현재 value 사용
    // XHR로 progress 표시하며 업로드
    await uploadWithProgress(fd, item);
  }
  uploadQueue = [];
  loadTracks(uploadChannel); // 목록 자동 갱신
}
```

### 드래그&드롭 순서 변경

```js
// HTML5 native drag & drop (라이브러리 없이)
// li[draggable=true] 에 dragstart/dragover/drop 이벤트
// drop 완료 시 배열 재정렬 → UI 재렌더링
// [순서 저장] 클릭 시 POST /api/meta

let dragSrcIdx = null;

trackItem.addEventListener('dragstart', e => {
  dragSrcIdx = itemIndex;
  e.dataTransfer.effectAllowed = 'move';
});

trackItem.addEventListener('dragover', e => {
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  // 드래그 중인 위치에 시각적 표시
});

trackItem.addEventListener('drop', e => {
  e.preventDefault();
  if (dragSrcIdx === null || dragSrcIdx === itemIndex) return;
  // 배열에서 dragSrcIdx 항목을 itemIndex 위치로 이동
  const moved = tracks.splice(dragSrcIdx, 1)[0];
  tracks.splice(itemIndex, 0, moved);
  // order 재할당 후 UI 재렌더
  tracks.forEach((t, i) => t.order = i);
  renderTrackList();
  dragSrcIdx = null;
  // [순서 저장] 버튼 활성화
});
```

### 채널 5 관리자 패널

```
채널 선택:  [말씀전당] [찬양의 숲] [예봄소리]

현재 방송:
┌──────────────────────────────┐
│  ◉ LIVE  요한복음 강해        │
│  ──────────── 12:34 / 45:20  │
│  [⏸ 일시정지]   [⏹ 종료]     │
└──────────────────────────────┘

음원 목록:
  요한복음 강해      [▶ ON AIR]
  시편 묵상          [▶ ON AIR]
  마태복음 강해      [▶ ON AIR]

(업로드/순서변경은 채널 3,4와 동일)
```

### ON AIR 플로우

```js
async function goOnAir(track) {
  // Howler로 실제 duration 측정
  const duration = await new Promise((resolve, reject) => {
    const h = new Howl({
      src: [WORKER_URL + '/api/stream/' + encodeURIComponent(track.key)],
      html5: true,
      onload: () => resolve(h.duration()),
      onloaderror: (_, e) => reject(e),
    });
    setTimeout(() => reject('timeout'), 30000);
  });

  // KV에 방송 상태 저장
  await fetch(WORKER_URL + '/api/ch5/state', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${adminKey}`,
    },
    body: JSON.stringify({
      trackKey:  track.key,
      trackName: track.name,
      duration,
      currentTime: 0,
      paused: false,
    }),
  });

  // 관리자 화면에서도 즉시 재생 시작
  playAdminPreview(track, 0);
}

// 일시정지
async function pauseBroadcast() {
  const currentTime = adminHowl?.seek() ?? 0;
  await postCh5State({ paused: true, currentTime });
}

// 재개
async function resumeBroadcast() {
  const currentTime = adminHowl?.seek() ?? 0;
  await postCh5State({ paused: false, currentTime });
}

// 종료
async function stopBroadcast() {
  await postCh5State({ trackKey: null, paused: true, currentTime: 0 });
  adminHowl?.stop();
}
```

---

## 10. 채널별 구현 상세

### 채널 1 — KBS 클래식 FM

// Workers 프록시 경유 (CORS 독립)
// 브라우저에서 KBS API를 직접 호출하지 않는다

async function loadKbs() {
  const res = await fetch(WORKER_URL + '/api/kbs');
  const { streamUrl, programTitle } = await res.json();
  await playHls(streamUrl, audioEl);
  updateNowPlaying(programTitle);
}

// 60초마다 방송명만 갱신 (스트리밍 URL은 재생 시작 시 1회만)
setInterval(async () => {
  if (currentChannel === 1 && isPlaying) {
    const res = await fetch(WORKER_URL + '/api/kbs');
    const { programTitle } = await res.json();
    updateNowPlaying(programTitle);
  }
}, 60000);

### 채널 2 — 극동방송

```js
const FEBC_URL = 'https://mlive2.febc.net/live/seoulfm/playlist.m3u8';

// 현재 방송명 (Workers 프록시 경유, 60초 갱신)
async function getFebcNowPlaying() {
  const res = await fetch(WORKER_URL + '/api/febc-schedule');
  const data = await res.json();
  return data.programTitle;
}
```

### HLS 재생 공통 패턴

```js
// hls.js CDN (동적 import)
// personal-radio/client/src/pages/Home.tsx의 HLS 재생 로직 참조
let currentHls = null;

async function playHls(url, audioEl) {
  // 기존 HLS 인스턴스 정리
  if (currentHls) { currentHls.destroy(); currentHls = null; }

  const { default: Hls } = await import(
    'https://cdn.jsdelivr.net/npm/hls.js@1.4.14/dist/hls.min.js'
  );

  if (Hls.isSupported()) {
    const hls = new Hls({
      enableWorker: false,
      lowLatencyMode: true,
      backBufferLength: 30,
      maxBufferLength: 30,
      xhrSetup: xhr => { xhr.withCredentials = false; },
    });
    hls.loadSource(url);
    hls.attachMedia(audioEl);
    await new Promise((resolve, reject) => {
      hls.on(Hls.Events.MANIFEST_PARSED, resolve);
      hls.on(Hls.Events.ERROR, (_, data) => {
        if (data.fatal) reject(new Error('HLS fatal error'));
      });
      setTimeout(() => reject(new Error('HLS timeout 20s')), 20000);
    });
    currentHls = hls;
  } else if (audioEl.canPlayType('application/vnd.apple.mpegurl')) {
    // iOS Safari 네이티브 HLS
    audioEl.src = url;
    await new Promise(resolve => audioEl.addEventListener('canplay', resolve, { once: true }));
  } else {
    throw new Error('HLS not supported');
  }
}
```

### 채널 3, 4 Howler.js 패턴

```js
// Howler.js CDN (index.html에 script 태그로 로드)
// <script src="https://cdnjs.cloudflare.com/ajax/libs/howler/2.2.4/howler.min.js">

function streamUrl(key) {
  return WORKER_URL + '/api/stream/' + encodeURIComponent(key);
}

let currentHowl = null;

function playTrack(channel, trackIndex, startPosition = 0) {
  const tracks = channelTracks[channel];
  if (!tracks || trackIndex >= tracks.length) return;
  const track = tracks[trackIndex];

  if (currentHowl) { currentHowl.unload(); currentHowl = null; }

  currentTrackKey  = track.key;
  currentTrackName = track.name;
  currentTrackIdx  = trackIndex;

  currentHowl = new Howl({
    src: [streamUrl(track.key)],
    html5: true,          // Range Request 스트리밍 필수
    volume: currentVolume,
    rate: currentSpeed,
    onplay: () => {
      isPlaying = true;
      updatePlayBtn(true);
      startVis();
      if (startPosition > 3) currentHowl.seek(startPosition);
    },
    onpause: () => {
      isPlaying = false;
      updatePlayBtn(false);
      stopVis();
      saveResume(channel);  // 일시정지 시점에도 저장
    },
    onstop: () => { isPlaying = false; stopVis(); },
    onend: () => {
      isPlaying = false;
      stopVis();
      localStorage.removeItem(`radio-ch${channel}-resume`); // 곡 끝나면 초기화
      playNext(channel);
    },
  });

  currentHowl.play();
  updateNowPlayingUI(track);
}

// 셔플 (Fisher-Yates)
function makeShuffleOrder(length) {
  const arr = Array.from({ length }, (_, i) => i);
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}
```

---

## 11. 녹음 기능 (채널 1, 2)

```js
// personal-radio/client/src/pages/Home.tsx의 useRecorder 훅 참조
let recorderConnected = false;
let isRecording = false;

// 5초마다 health check
setInterval(async () => {
  try {
    const r = await fetch('http://localhost:8090/health', {
      signal: AbortSignal.timeout(2000),
    });
    recorderConnected = r.ok;
  } catch {
    recorderConnected = false;
  }
  updateRecordBtn();
}, 5000);

async function startRecording(channelName, programTitle) {
  if (!recorderConnected) {
    showToast('녹음기능은 별도문의바랍니다.');
    return;
  }
  const ts = new Date().toISOString()
    .replace(/[-T:.Z]/g, '').slice(2, 14); // YYMMDDHHmmss
  const filename = `${channelName}${programTitle ?? ''}${ts}`;

  await fetch('http://localhost:8090/record/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source: 'system',
      filename,
      mode: 'auto',
      silence_threshold: 100,
      silence_duration: 1,
    }),
  });
  isRecording = true;
  updateRecordBtn();
}

// stopPlayback() 호출 시 반드시 함께 호출
async function stopRecording() {
  if (!isRecording) return;
  await fetch('http://localhost:8090/record/stop', { method: 'POST' });
  isRecording = false;
  updateRecordBtn();
}
```

---

## 12. 공통 기능

### 수면 타이머

```js
const SLEEP_OPTIONS = [600, 1800, 3600, 7200]; // 10분, 30분, 1시간, 2시간
let activeSleepSecs = 0, sleepTimer = null;

function setSleepTimer(seconds) {
  clearTimeout(sleepTimer);
  if (activeSleepSecs === seconds) {
    activeSleepSecs = 0;          // 같은 버튼 재클릭 = 취소
    updateSleepBtns(); return;
  }
  activeSleepSecs = seconds;
  sleepTimer = setTimeout(() => {
    stopPlayback();    // Howl/HLS 정지
    stopRecording();   // 녹음 자동 종료
    activeSleepSecs = 0;
    showToast('수면 타이머가 종료되었습니다');
    updateSleepBtns();
  }, seconds * 1000);
  updateSleepBtns();
}
```

### 볼륨

```js
// 초기화 시 복원
let currentVolume = parseFloat(localStorage.getItem('radio-volume') ?? '0.8');

function setVolume(v) {
  currentVolume = v;
  if (currentHowl) currentHowl.volume(v);
  if (audioEl) audioEl.volume = v;         // HLS용 audio element
  localStorage.setItem('radio-volume', v); // 즉시 저장
}
```

### 비주얼라이저

```js
let visTimer = null;

function startVis() {
  const bars = document.querySelectorAll('.vis-bar');
  stopVis();
  visTimer = setInterval(() => {
    bars.forEach(b => {
      const h = 4 + Math.random() * 28;
      b.style.height = h + 'px';
      b.style.opacity = 0.3 + (h / 32) * 0.7;
    });
  }, 120);
}

function stopVis() {
  clearInterval(visTimer);
  document.querySelectorAll('.vis-bar').forEach(b => {
    b.style.height = '4px';
    b.style.opacity = '0.2';
  });
}
```

### 시크바

```js
// 채널 3, 4, 5에서 표시 및 클릭 가능
function updateSeekBar() {
  if (!currentHowl) return;
  const pos = currentHowl.seek() || 0;
  const dur = currentHowl.duration() || 1;
  const pct = (pos / dur) * 100;
  seekFill.style.width = pct + '%';
  timeEl.textContent = formatTime(pos) + ' / ' + formatTime(dur);
  if (isPlaying) requestAnimationFrame(updateSeekBar);
}

seekBar.addEventListener('click', e => {
  if (!currentHowl) return;
  const ratio = e.offsetX / seekBar.offsetWidth;
  currentHowl.seek(currentHowl.duration() * ratio);
});

function formatTime(sec) {
  if (!sec || isNaN(sec)) return '0:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}
```

---

## 13. PWA 설정

### manifest.json
```json
{
  "name": "예봄라디오",
  "short_name": "예봄라디오",
  "description": "새벽 감성 통합 라디오",
  "display": "standalone",
  "start_url": "/",
  "background_color": "#0D0B1A",
  "theme_color": "#1A1035",
  "orientation": "portrait-primary",
  "icons": [
    { "src": "icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

### sw.js — 캐시 전략
```js
const CACHE_NAME = 'yebom-radio-v1';

// 절대 캐시하지 않을 패턴
const NO_CACHE_PATTERNS = [
  /\.mp3$/, /\.m4a$/, /\.ogg$/, /\.wav$/, /\.flac$/,
  /\.m3u8$/, /\.ts$/, /\.aac$/,
  /\/api\//,
  /kbs\.co\.kr/, /febc\.net/,
  /cloudfront\.net/, /workers\.dev/,
];

self.addEventListener('fetch', event => {
  if (NO_CACHE_PATTERNS.some(p => p.test(event.request.url))) return;
  event.respondWith(
    caches.match(event.request).then(cached => cached || fetch(event.request))
  );
});

// 버전 변경 시 이전 캐시 자동 삭제
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
});
```

---

## 14. 구현 순서 (Phase별)

### Phase 1 — Workers API 구축 및 배포
```
① prev-radio/worker.js 를 복사해서 새 worker.js 시작
② 기존 엔드포인트 유지하면서 다음 추가/수정:
   - /api/tracks: _meta.json 연동 로직 추가
   - /api/ch1/state → /api/ch5/state 로 경로 변경
   - /api/upload: name 파라미터 + _meta.json 갱신 추가
   - /api/delete: _meta.json 갱신 추가
   - /api/meta: 신규 추가
   - /api/febc-schedule: 신규 추가 (personal-radio/server/febcScheduleProxy.ts 이식)
③ prev-radio/wrangler.toml 복사 → name만 "radio-worker"로 유지
④ wrangler deploy
⑤ 검증:
   curl {URL}/api/tracks?channel=list1   → [] 또는 목록
   curl {URL}/api/ch5/state              → { trackKey: null, ... }
   curl {URL}/api/febc-schedule          → { programTitle: "..." }
```

### Phase 2 — 프론트엔드 기본 뼈대
```
① index.html 기본 구조
② CSS 변수 전체 (섹션 8)
③ 시간대별 배경 로직
④ 5채널 탭 UI
⑤ 글래스모피즘 플레이어 카드 (빈 상태)
⑥ WORKER_URL 설정창 (첫 실행 시)
```

### Phase 3 — 채널별 플레이어 구현
```
① 채널 5 (예봄소리) — KV polling + Howler 재생 (가장 단순)
   → Workers 연동 기초 검증용
② 채널 3, 4 (말씀전당, 찬양의 숲) — /api/tracks + Howler
   → 목록 팝업, 트랙 선택, 재생/정지
③ 채널 1, 2 (KBS, 극동방송) — hls.js + 방송명 표시
```

### Phase 4 — 이어듣기 (정밀 구현)
```
① saveResume() — 4중 저장 (인터벌 + beforeunload + pagehide + visibilitychange)
② restoreResume() — 7일 유효성 + R2 파일 존재 확인
③ enterChannel() — 복원 또는 첫 트랙 재생
④ 복원 토스트 ("↩ 곡명 — 5:12부터 이어듣기")
⑤ 트랙 삭제 시 cleanup
⑥ 전체 테스트:
   - 브라우저 탭 닫기 → 재열기 → 복원 확인
   - 10초마다 저장 확인 (DevTools → Application → localStorage)
```

### Phase 5 — 부가기능
```
① 수면 타이머 (10분/30분/1시간/2시간)
② 셔플 (Fisher-Yates) + 반복 + 재생속도 (0.75~/1~/1.25~/1.5×)
③ 시크바 (클릭 seek + requestAnimationFrame 업데이트)
④ 비주얼라이저 (CSS 바 애니메이션)
⑤ 볼륨 슬라이더 + localStorage 저장
⑥ 녹음 연동 (채널 1, 2) + health check
```

### Phase 6 — Admin UI
```
① 로고 3번 탭 → Admin Key 인증 모달
② 채널 3, 4 업로드:
   - 드롭존 (dragover/drop + input[file] 클릭)
   - 파일명 default 입력칸 (수정 가능)
   - XHR progress bar
   - 업로드 완료 후 목록 자동 갱신
③ 등록 목록:
   - HTML5 native 드래그&드롭 순서 변경
   - [순서 저장] → POST /api/meta
   - [🗑 삭제] → POST /api/delete + cleanupResumeOnDelete()
④ 채널 5 ON AIR 패널:
   - 음원 목록 + [ON AIR] 버튼
   - 현재 방송 상태 표시 (LIVE 뱃지)
   - [⏸ 일시정지] / [▶ 재개] / [⏹ 종료]
```

### Phase 7 — PWA + 최종 배포
```
① manifest.json + 아이콘 파일
② sw.js (캐시 전략)
③ iOS 홈화면 추가 안내 모달 (personal-radio/client/src/pages/Home.tsx의 usePwaInstall 참조)
④ wrangler pages deploy .
⑤ 최종 검증:
   - 모바일 Chrome/Safari에서 설치 테스트
   - 채널 전환 시 이어듣기 복원 테스트
   - Admin 업로드 → 목록 반영 → ON AIR 테스트
```

---

## 15. Claude Code 시작 프롬프트

**새 VSCode 창을 열고 아래를 첫 메시지로 붙여넣는다.**

```
이 폴더의 구성:
  DESIGN_GUIDE.md   → 새 라디오의 완전한 설계 명세
  prev-radio/       → 이전에 실제 작동하던 간이 라디오 소스
  personal-radio/   → 기존 예봄라디오 소스 (레퍼런스)

작업 전 반드시 이 순서대로 읽어라:
  1. DESIGN_GUIDE.md 전체
  2. prev-radio/worker.js          ← R2/KV 실제 작동 패턴 (기반 코드)
  3. prev-radio/wrangler.toml      ← bucket_name, KV id 확인 후 그대로 사용
  4. personal-radio/ARCHITECTURE.md
  5. personal-radio/server/febcScheduleProxy.ts
  6. personal-radio/client/src/pages/Home.tsx

핵심 규칙:
  - prev-radio/worker.js를 기반으로 새 worker.js를 작성한다
  - prev-radio/wrangler.toml의 bucket_name과 KV id를 그대로 가져온다
  - Manus OAuth / tRPC / Drizzle / Express / React / Vite 절대 금지
  - 최종 결과물: worker.js + index.html + manifest.json + sw.js 4개만
  - DESIGN_GUIDE.md 섹션 13의 Phase 1부터 순서대로 진행
  - 각 Phase 완료 후 반드시 검증 명령 실행하고 결과 보고, 다음 Phase 진행 여부 확인

지금 바로 위 6개 파일을 모두 읽고 Phase 1을 시작해라.
```

---

## 16. 수작업 체크리스트 (Claude Code 시작 전 완료)

```
□ R2 대시보드 → radio/channel-list2/ 디렉토리 생성
□ channel-list1/ 에 말씀전당 음원 업로드
□ channel-list2/ 에 찬양의 숲 음원 업로드
□ channel-stream/ 에 예봄소리 음원 업로드
□ prev-radio/wrangler.toml 열어서 KV id 값 메모
□ 프로젝트 폴더 구성 확인:
    radio-integrated/
      ├── DESIGN_GUIDE.md
      ├── prev-radio/  (worker.js, wrangler.toml, index.html)
      └── personal-radio/  (zip 압축 해제)
```

---

## 17. 환경 변수 설정 명령

```bash
# KV namespace ID 확인 (prev-radio/wrangler.toml의 id와 같은지 확인)
wrangler kv:namespace list

# Admin Key 설정 (처음 한 번만)
wrangler secret put ADMIN_KEY

# 배포
wrangler deploy

# 프론트엔드 배포
wrangler pages deploy .
```

---

## 18. 트러블슈팅 가이드

| 증상 | 원인 | 해결 |
|---|---|---|
| `/api/tracks` 빈 배열 | R2 경로 불일치 | `radio/channel-list1/` 경로 대소문자 확인 |
| 스트리밍 재생 안 됨 | CORS 또는 Range Request | worker.js CORS 헤더 + html5:true 확인 |
| febc-schedule null | 극동방송 HTML 구조 변경 | 정규식 `<p class="tit">` 패턴 재확인 |
| KV 업데이트 안 됨 | Admin Key 불일치 | `wrangler secret put ADMIN_KEY` 재설정 |
| 이어듣기 안 됨 | 파일 경로 변경 | `restoreResume` 의 파일 존재 검사 로그 확인 |
| HLS 재생 안 됨 (iOS) | 네이티브 HLS 미동작 | `canPlayType('application/vnd.apple.mpegurl')` 분기 확인 |
| wrangler deploy 실패 | KV id 미입력 | wrangler.toml의 id 값 확인 |
