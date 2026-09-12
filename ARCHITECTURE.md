# 예봄라디오 2.0 — 아키텍처 문서

> **버전**: 2026-09-12 v2.7.0 (SSO 로그인 개선 — 체크인 정상화 · 신원 정규화 · 로그아웃 개편)
> **프로젝트 경로**: `G:\내 드라이브\g_dev\yebomradio`
> **GitHub**: https://github.com/loginheaven-jpg/radio
> **Pages URL**: https://radio.yebom.org (표준 도메인) — `radio-axi.pages.dev`는 과도기 주소로 301 리다이렉트 예정
> **Workers URL**: https://radio-worker.yebomradio.workers.dev

---

## 1. 프로젝트 개요

예봄라디오 2.0은 예봄교회의 웹 라디오 서비스이다. 5개 채널(라이브 2 + R2 재생목록 2 + 공유 스트리밍 1)을 하나의 SPA에서 제공한다.

| 항목 | 내용 |
|---|---|
| 인프라 | Cloudflare Workers + R2 + KV + Pages |
| 프론트엔드 | 단일 `index.html` (Vanilla JS, CSS 인라인, 빌드 도구 없음) |
| 인증 | 교적부(saint.yebom.org) SSO 체크인 + 이메일/비밀번호 로그인(교적부 위임) + Admin Key |
| PWA | `manifest.json` + `sw.js` (자동 업데이트, 오프라인 폴백) |
| UI 패턴 | **Warm Vinyl** — 중앙 회전 바이닐 디스크 + 채널별 테마 + 앰비언트 효과 |
| 디자인 참조 | `c:\dev\radio\UI-GUIDE.md` (디자인 명세), `c:\dev\radio\radio-vinyl.jsx` (React 프로토타입) |

---

## 2. 파일 구조

```
c:\dev\radio\
├── UI-GUIDE.md               ← Warm Vinyl UI 디자인 가이드 (한국어)
├── radio-vinyl.jsx            ← React 디자인 프로토타입 (참조용, 실제 사용 안함)
├── LIVE_BROADCAST_DESIGN.md   ← 라이브 방송 시스템 설계 문서
└── yebomradio/                ← 메인 앱 디렉토리 (git root)
    ├── index.html             ← 전체 프론트엔드 (CSS + HTML + JS 인라인, ~2000줄)
    ├── worker.js              ← Cloudflare Workers API 서버 (~560줄)
    ├── wrangler.toml          ← Workers 설정 (R2, KV 바인딩)
    ├── sw.js                  ← Service Worker (캐시 v6, 자동 업데이트)
    ├── manifest.json          ← PWA 매니페스트
    ├── icon-192.png           ← PWA 아이콘 192×192
    ├── icon-512.png           ← PWA 아이콘 512×512
    ├── ARCHITECTURE.md        ← 이 문서
    ├── DESIGN_GUIDE.md        ← 원본 설계 명세 (초기 버전)
    ├── DESIGN_GUIDE1.md       ← 대안 설계 명세
    └── host/                  ← Python 호스트 앱 (봄소리 라이브+파일 방송 관리)
        ├── host.py            ← tkinter GUI (탭: 라이브 방송 + 파일 방송)
        ├── config.py          ← 설정 상수 (오디오, 네트워크, GUI)
        ├── audio_engine.py    ← FFmpeg DirectShow 오디오 캡처/믹싱
        ├── uploader.py        ← Workers API 라이브 청크 업로드 (큐 기반)
        ├── api_client.py      ← Workers API 파일 방송 관리 (트랙/CH5 상태)
        ├── requirements.txt   ← Python 의존성 (requests)
        ├── build.bat          ← PyInstaller 빌드 스크립트
        └── settings.json      ← 사용자 설정 (gitignore, 로컬 전용)
```

---

## 3. 채널 구성 (5채널)

| # | 채널명 | ID | 유형 | 데이터 소스 | 액센트 컬러 |
|---|---|---|---|---|---|
| 1 | KBS 클래식FM | `kbs` | HLS 라이브 | KBS API → Workers 프록시 | `#d4a45c` Gold |
| 2 | 극동방송 | `febc` | HLS 라이브 | 고정 m3u8 + 편성표 프록시 | `#c48a6a` Copper |
| 3 | 말씀의 전당 | `word` | R2 개인선택 | `radio/channel-list1/` | `#6a8cb8` Slate Blue |
| 4 | 찬양의 숲 | `praise` | R2 개인선택 | `radio/channel-list2/` | `#6aaa60` Forest Green |
| 5 | 봄소리 방송 | `bom` | R2 공유스트리밍 | `radio/channel-stream/` + KV | `#c87890` Rose |

### 채널 유형별 동작

- **HLS 라이브 (CH1, CH2)**: hls.js로 실시간 스트리밍. 60초마다 프로그램명 갱신. Workers HLS 프록시로 CORS 우회.
- **R2 개인선택 (CH3, CH4)**: Howler.js로 R2 음원 재생. 이어듣기(resume), 랜덤듣기, 이곡반복, 전곡반복, 속도 조절, 재생목록 지원. 5분마다 재생목록 자동 갱신. CH3은 LP 디스크 대신 Canvas 등잔 애니메이션 표시 (멈춤 시 작은 불꽃 유지, 성경 구절 20px).
- **R2 공유스트리밍 (CH5)**: 관리자가 ON AIR → KV에 상태 저장. 청취자는 10초마다 polling → 오프셋 계산 → 동기화 재생.

---

## 4. Workers API 엔드포인트

### 파일: `worker.js`

**바인딩**: R2 `RADIO_BUCKET` (coachdb-files), KV `RADIO_KV`, Secret `ADMIN_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`

| Method | Path | 설명 | 인증 |
|---|---|---|---|
| GET | `/api/tracks?channel=list1\|list2\|stream` | 트랙 목록 (`_meta.json` 기준, R2 키와 교차 검증) | 없음 |
| GET | `/api/stream/:key` | R2 음원 Range Request 스트리밍 | 없음 |
| GET | `/api/ch5/state` | 채널5 재생 상태 (KV `ch5_state`) | 없음 |
| POST | `/api/ch5/state` | 채널5 재생 상태 변경 | Admin |
| POST | `/api/upload` | 음원 R2 업로드 + `_meta.json` 갱신 (FormData, ≤10MB) | Admin |
| POST | `/api/upload/multipart/create` | 대형 파일 멀티파트 업로드 시작 | Admin |
| PUT | `/api/upload/multipart/part` | 멀티파트 파트 전송 (10MB 단위) | Admin |
| POST | `/api/upload/multipart/complete` | 멀티파트 완료 + `_meta.json` 갱신 | Admin |
| POST | `/api/delete` | 음원 R2 삭제 + `_meta.json` 갱신 | Admin |
| POST | `/api/meta` | `_meta.json` 전체 덮어쓰기 (순서/곡명 변경) | Admin |
| GET | `/api/febc-schedule` | 극동방송 편성표 프록시 (60초 캐시) | 없음 |
| GET | `/api/kbs` | KBS 스트리밍 URL + 현재 방송명 프록시 (60초 캐시) | 없음 |
| GET | `/api/hls-proxy?url=<encoded>` | HLS CORS 프록시 (KBS/FEBC 도메인 화이트리스트) | 없음 |
| **POST** | **`/api/live/chunk`** | **라이브 청크 업로드 (R2 + KV/세션 갱신)** | **Admin** |
| **GET** | **`/api/live/chunk/:session/:index`** | **라이브 청크 다운로드** | 없음 |
| **GET** | **`/api/live/state`** | **라이브 상태 (Cache API 1초)** | 없음 |
| **POST** | **`/api/live/state`** | **방송 시작/종료/메시지 (상호잠금)** | **Admin** |
| **GET** | **`/api/live/config`** | **보존 설정 + 사용량** | 없음 |
| **POST** | **`/api/live/config`** | **보존 한도 변경** | **Admin** |
| **GET** | **`/api/live/sessions`** | **저장된 방송 세션 목록** | 없음 |
| **POST** | **`/api/live/sessions/delete`** | **세션 수동 삭제** | **Admin** |
| POST | `/api/identify` | 곡명 인식 (HLS 세그먼트 3개 병합 → ACRCloud 핑거프린팅) | 없음 |
| GET | `/api/channel-config` | 서버 채널 설정 조회 (order, hidden, defaultChannel) | 없음 |
| PUT | `/api/channel-config` | 서버 채널 설정 저장 | `Bearer ADMIN_KEY` |
| GET | `/api/user/trackpos` | CH3 트랙별 재생위치 조회 | `X-User-Id` ⚠️ 검증 없음 |
| PUT | `/api/user/trackpos` | CH3 트랙별 재생위치 저장 (ts 병합) | `X-User-Id` ⚠️ 검증 없음 |
| POST | `/api/auth/email-login` | 이메일+비밀번호 로그인 (교적부 `/api/auth/login`에 검증 위임 → JWT 발급) | 없음 |
| GET | `/api/auth/verify` | 관리자 킷/JWT 유효성 확인 | `Bearer <JWT 또는 ADMIN_KEY>` |

### HLS 프록시 화이트리스트
`gscdn.kbs.co.kr`, `kbs.co.kr`, `febc.net`, `mlive2.febc.net`

### R2 Range Request 처리
- `head()` → 전체 크기 확인 → `Range` 헤더 파싱 → `{ offset, length }` 방식으로 R2 get
- `Content-Range`, `Accept-Ranges: bytes` 헤더 포함 → 206 Partial Content 응답
- 전체 요청 시 200으로 전체 바디 반환

### 인증 체계

> 간편 로그인(이름+전화 뒤 4자리, `/api/auth/simple-login`)은 **2026-03-23 `dd04cb7`에서 완전히 제거**되었다. worker.js에 해당 라우트가 없다.

#### 1. 교적부 체크인 (SSO — 신원의 기준)
`saint.yebom.org`가 인증 허브이고, 세션은 `saint_record_session` 쿠키(iron-session 암호화, `Domain=.yebom.org`, `SameSite=Lax`)로 예봄 앱들이 공유한다. `radio.yebom.org`는 교적부와 **같은 사이트**라 쿠키가 정상 전송된다.

- **호출**: `GET https://saint.yebom.org/api/auth/session` (`credentials: 'include'`) — `checkSsoSession()`
- **시점**: 앱 시작 시 1회(`initSsoCheck`) + **탭 복귀 시**(`visibilitychange`, 최소 간격 45초)
- **역할**: 유효성 확인 + 권한/이름 최신화 + **로그인 유지 세션 400일 연장**(교적부가 하루 1회 재봉인). 연장 수단이 체크인뿐이므로 곁가지 기능이 아니다.
- **판정은 반드시 HTTP status로만**:

  | status | 처리 |
  |---|---|
  | 200 + `isLoggedIn:true` | 로그인 확정 (`radioUser` 갱신, 캐시 저장) |
  | 401 / 200+`isLoggedIn:false` | 익명 전환 — `radio-user` **및 JWT(`radio-admin-key`) 삭제**, 개인 UI 감춤, 1회 안내 토스트<br>※ 수동 입력한 레거시 공유 `ADMIN_KEY`는 JWT 형식(점 2개)이 아니므로 **남긴다** — 지우면 교적부 계정이 없는 관리자가 페이지 로드마다 킷을 다시 입력해야 한다 |
  | 5xx · 네트워크 오류 | **기존 상태 유지 — 로그아웃 금지** |

  ⚠️ 교적부는 **HTTP 500에도 본문에 `{isLoggedIn:false}`** 를 담는다(`session/route.ts`). `res.ok`/`body.isLoggedIn`으로 분기하면 교적부 장애 때 전 사용자가 로그아웃된다.
- **호스트 가드**: 체크인은 `*.yebom.org`에서만 수행한다. `localhost`·`*.pages.dev`는 교적부와 다른 사이트라 쿠키가 실리지 않아 항상 401이 된다.
- **캐시**: `localStorage['radio-user']` (5분 TTL) — 체크인 응답이 오기 전 화면 표시용.

#### 2. 이메일/비밀번호 로그인 — **브라우저에서 교적부로 직접**
라디오 화면 안의 폼을 유지하되, 워커를 경유하지 않고 브라우저가 교적부로 직접 보낸다. 그래야 응답의 `Set-Cookie`로 `.yebom.org` 세션 쿠키가 이 브라우저에 설치되고 체크인·연장·통합 로그아웃이 성립한다.

```js
POST https://saint.yebom.org/api/auth/login
  credentials: 'include'                       // ★ 없으면 쿠키가 설치되지 않는다
  body: { email, password, remember }          // email 필드는 이메일 또는 전화번호(교적부 통합 필드)
```
- **성공 응답에 사용자 정보가 없다** — `{ success, password_reset_required, needs_profile_completion }` 뿐. 따라서 **로그인 200 → `checkSsoSession({ force: true, merge: true })`** 로 신원을 받아온다.
- 실패 시 교적부의 `error` 문구를 그대로 노출한다(401 자격증명 불일치, 403 승인 대기, **429 레이트리밋 — IP당 1분 5회**).
- `remember`(로그인 유지)는 기본 true, 모달의 체크박스로 해제 가능. 해제 시 교적부가 비영구 세션(12시간 봉인, 연장 없음)을 발급한다 — **정상 동작이다.**
- **fetch이므로 페이지 이동이 없다** → 재생·녹음이 끊기지 않는다. 이것이 리다이렉트 대신 이 방식을 쓰는 이유다(iOS 홈화면 PWA는 쿠키 저장소가 분리되어 리다이렉트 로그인이 성립하지 않는 문제도 함께 피한다).
- **교적부 CORS 허용 오리진은 `https://radio.yebom.org` 하나뿐**이다(`login/route.ts`). 그래서 `radio-axi.pages.dev`·`localhost`에서는 이 경로가 막히고, 그 호스트에서만 레거시 워커 경로(`POST /api/auth/email-login`)로 폴백한다. 폴백 경로는 쿠키가 설치되지 않아 체크인이 401이 된다 — E단계(도메인 단일화) 후 제거 대상.

**카카오 로그인**: 카카오로만 가입한 교인을 위해 `https://saint.yebom.org/login?from=radio&redirect=https://radio.yebom.org/` 링크를 병기한다. 이 경로는 전체 페이지 이동이라 재생이 끊기며, 모달에 그 안내를 표시한다.

**관리자 토큰 임시 브리지**: 직접 로그인 경로는 JWT를 발급하지 않으므로, 로그인한 계정의 `role`이 관리자 등급일 때만 워커 `email-login`에서 JWT를 한 번 더 받아 `adminKey`에 넣는다(`bridgeAdminToken`). 관리 API가 아직 `Authorization: Bearer`에 의존하기 때문이며, **D단계(워커 서버측 신원 검증) 완료 시 워커 `email-login`과 함께 제거한다.**

#### 3. 신원 정규화 (`normalizeUser`)
두 경로가 서로 다른 모양의 사용자 객체를 준다 — 받는 지점에서 한 번에 통일한다.

| 경로 | 원본 필드 |
|---|---|
| 교적부 체크인 | `user_id`, `member_id`, `permission_level` (⚠️ `id`·`role` 없음) |
| 워커 email-login | `id`, `name`, `role` |

→ `{ id: id ?? user_id ?? member_id, role: role ?? permission_level, name }` 로 정규화. 적용 지점: 체크인 200 / 폼 로그인 성공 / `radio-user` 캐시 복원.
**`radioUser.id`가 없으면 신원을 전송하지 않는다** — 정규화 이전에는 쿠키 경로에서 `X-User-Id: undefined`가 나가 KV의 같은 버킷(`user:trackpos:undefined`)을 여러 사용자가 공유했다.

#### 4. Admin (관리자)
```
Authorization: Bearer <SSO JWT 또는 ADMIN_KEY>
```
`isAdmin()`(worker.js)이 ① JWT 검증 후 `role ∈ {super_admin, admin}` ② 레거시 공유 `ADMIN_KEY` 순으로 통과시킨다. 클라이언트는 `localStorage['radio-admin-key']`에 보관하며, 이 값은 **자격증명이자 관리자 UI 노출 플래그**를 겸한다(`if (adminKey)`).

#### 5. 로그아웃 (5개 앱 공통 순서)
1. 확인창: `로그아웃하시겠습니까?\n이 기기에 저장된 로그인 정보가 모두 지워집니다.`
2. **이 기기의 자격증명·개인 데이터만 정밀 삭제** — `localStorage.clear()`는 쓰지 않는다
   - 삭제: `radio-admin-key`, `radio-user`, `radio-ch3-trackpos`, `radio-ch3-resume`, `radio-ch4-resume`, `gb_draft`
   - 보존: `radio-volume`, `radio-onlymusic-vol`, `radio-ch`, `radio-last-channel`, `radio-channel-config`, `radio-rec-threshold`, `radio-rec-silence-dur`, `radio-rsc-format`, `yebom-40th-seen`, `radio-arrow-pulse-*`
   - Cache Storage 전체 삭제(`Clear-Site-Data` 미지원 브라우저 대비). 서비스워커 등록은 유지(개인 데이터 없음 + PWA 오프라인 동작 보호)
3. `location.replace('https://saint.yebom.org/api/auth/logout?return=' + encodeURIComponent('https://radio.yebom.org/'))`
   → 교적부가 `.yebom.org` SSO 쿠키 전체 삭제 + `Clear-Site-Data` + 재로그인 표식(`yebom_reauth`) 후 303 복귀.
   ⚠️ 이 삭제는 **같은 사이트 요청에서만** 실제로 동작한다(교적부의 CSRF 가드). 검증은 `radio.yebom.org`에서.

#### 로그인이 필요한 기능
| 기능 | 인증 | 헤더 |
|------|------|------|
| 청취 (모든 채널) | 불필요 | — |
| 녹음 | 로그인 | — (프론트엔드 `radioUser` 확인) |
| 재생위치 동기화 | 로그인 | `X-User-Id: {정규화된 id}` ⚠️ 서버 검증 없음 |
| 오픈뮤직룸 업로드/수정/삭제 | 로그인 또는 Admin | `X-User-Id`, `X-User-Name` ⚠️ 서버 검증 없음 |
| 관리자 기능 | Admin Key / SSO JWT | `Authorization: Bearer {key}` |

> 🔴 **미조치 보안 위험**: 워커는 `X-User-Id`/`?userId=`를 **검증 없이 신뢰**한다(`getRequestUser`). 임의의 `X-User-Id`로 남의 트랙 위치와 오픈뮤직룸 곡을 조작할 수 있다. 서버측 신원 검증은 후속 작업(D단계)이다.

---

## 5. R2 버킷 구조

```
coachdb-files/
├── backups/                    ← 기존 데이터 (유지)
├── uploads/                    ← 기존 데이터 (유지)
└── radio/
    ├── channel-stream/         ← 채널5 봄소리 방송 (파일 ON AIR)
    │   └── _meta.json
    ├── channel-list1/          ← 채널3 말씀의 전당
    │   └── _meta.json
    ├── channel-list2/          ← 채널4 찬양의 숲
    │   └── _meta.json
    └── live/                   ← 라이브 방송 청크
        ├── sessions.json       ← 세션 메타 목록
        └── YYYYMMDD-HHmmss/   ← 세션별 폴더
            ├── chunk-00000000.ogg
            └── ...
```

### `_meta.json` 형식
```json
[
  { "key": "radio/channel-list1/track1.mp3", "name": "곡 이름", "order": 0 },
  { "key": "radio/channel-list1/track2.mp3", "name": "곡 이름 2", "order": 1 }
]
```

---

## 6. KV 데이터

- **바인딩**: `RADIO_KV` (ID: `c4c08099c81c4860a0184e7c29562434`)
- **주요 키**: `ch5_state`, `live_state`, `live_config`, `channel-config`, `anniversary:messages`, `user:trackpos:{userId}`, `openroom:*`

### `ch5_state` 구조
```json
{
  "trackKey": "radio/channel-stream/track.mp3",
  "trackName": "곡 이름",
  "duration": 300,
  "paused": false,
  "startEpoch": 1709340000000,
  "currentTime": 0,
  "updatedAt": 1709340000000
}
```
- `startEpoch`: 재생 시작 시점 epoch (ms). 클라이언트는 `(Date.now() - startEpoch) / 1000`으로 현재 offset 계산.
- `paused: true`일 때 `currentTime`이 일시정지 시점.

---

## 7. 프론트엔드 아키텍처 (`index.html`)

### 7.1 기술 스택

| 라이브러리 | 버전 | 용도 |
|---|---|---|
| Howler.js | 2.2.4 | R2 음원 재생 (Range Request, html5 모드) |
| hls.js | 1.4.14 | HLS 라이브 스트리밍 (동적 CDN 로드) |
| Pretendard Variable | v1.3.9 | UI/본문 한국어 폰트 |
| Space Grotesk | Google Fonts | 시계/숫자 모노스페이스 폰트 |

### 7.2 전역 상태 변수

```javascript
// 채널/재생
currentChannel       // 현재 채널 번호 (1~5)
isPlaying            // 재생 상태
currentHowl          // Howler.js 인스턴스 (R2 재생)
currentHls           // hls.js 인스턴스 (HLS 재생)
audioEl              // <audio> 엘리먼트 (HLS용)
currentTrackKey      // 현재 트랙 R2 키
currentTrackName     // 현재 트랙 이름
currentTrackIdx      // 현재 트랙 인덱스
currentVolume        // 볼륨 (0.0~1.0)
currentSpeed         // 재생 속도 (1, 1.1, 1.25, 1.5)
shuffleOn, repeatOn  // 랜덤듣기/이곡반복 토글 (전곡반복은 기본 동작)
channelTracks        // { 3: [...], 4: [...], 5: [...] } 트랙 목록 캐시
focusedIndex         // 현재 포커스된 채널 인덱스 (0~4)

// 오디오 컨텍스트 (녹음용)
audioCtx             // AudioContext
gainNode             // GainNode (볼륨 제어 + 녹음 라우팅)
recDestination       // MediaStreamDestination (녹음 대상)
recAnalyser          // AnalyserNode (무음 감지)
hlsSourceNode        // MediaElementSource (HLS → AudioContext)
howlSourceNode       // MediaElementSource (Howler → AudioContext)

// 녹음
isRecording, mediaRecorder, recordedChunks
recFormat            // 'webm' | 'mp3'
recSegmentNum        // 무음 분할 시 세그먼트 번호

// 디스크 회전
discRotation         // 현재 회전 각도 (deg)
discRafId            // requestAnimationFrame ID
discLastTime         // 마지막 프레임 타임스탬프

// 스와이프
swipeStartX, discTranslateX
```

### 7.3 채널 정의 (`CHANNELS` 배열)

각 채널 객체 구조:
```javascript
{
  num: 1,               // 채널 번호
  id: 'kbs',            // 채널 식별자 (CHANNEL_ICONS 키)
  name: 'KBS 클래식FM', // 표시 이름
  freq: '93.1',         // 주파수 / 채널 번호
  freqUnit: 'MHz',      // 주파수 단위
  type: 'live',         // 'live' | 'pod'
  accent: '#d4a45c',    // 주 악센트 컬러
  accentLight: '#f0d490', // 밝은 악센트
  bg1: '#1a150e',       // 배경 그라데이션 색상 1
  bg2: '#1e1410',       // 배경 그라데이션 색상 2
  bg3: '#14100c',       // 배경 그라데이션 색상 3
  discRing: '#c9983f',  // 디스크 링 컬러
  label: '클래식의 향연', // 채널 설명 문구
  color: '#d4a45c',     // 호환용 메인 컬러
  dim: 'rgba(...)',     // 호환용 dim 컬러
  glow: 'rgba(...)',    // 호환용 glow 컬러
  particles: [          // 플로팅 파티클 정의
    { char:'♪', x:15, delay:0, size:10, opacity:0.06 },
    ...
  ],
}
```

### 7.4 채널별 SVG 아이콘 (`CHANNEL_ICONS`)

각 채널은 디스크 중앙 라벨에 표시될 SVG 아이콘을 함수로 정의한다:
- `kbs(color)` → 피아노 건반
- `febc(color)` → 십자가 + 후광
- `word(color)` → 펼친 성경
- `praise(color)` → 나뭇잎/새싹
- `bom(color)` → 꽃잎 (5개 타원 + 줄기)

각 함수는 채널 accent 컬러를 인자로 받아 SVG 문자열을 반환한다.

---

## 8. UI 구성 (Warm Vinyl 디자인)

### 8.1 전체 레이아웃

```
┌────────────────────────────────────────┐
│ ■ BG-LAYER: 채널별 3색 그라데이션       │  ← position:fixed
│ ■ TIME-OVERLAY: 시간대별 미세 오버레이   │  ← position:fixed
│ ■ AMBIENT-GLOW: 디스크 뒤 280px 글로우  │  ← position:fixed
│ ■ PARTICLES-WRAP: 채널별 플로팅 파티클   │  ← position:fixed
├────────────────────────────────────────┤
│ [HH:MM SS]              [예봄 40']   │  ← Header (시계 좌, 로고 우)
│           [Yebom Radio 2.0]            │     로고 3탭 → 관리자
├────────────────────────────────────────┤
│     [LIVE] 현재 방송 프로그램명         │  ← Now Playing bar
├────────────────────────────────────────┤
│  ◁    ╭──────────────╮    ▷           │
│       │ ╭──── ────╮  │               │  ← Vinyl Disc (210×210)
│       │ │  ICON   │  │               │     5층 레이어
│       │ │  93.1   │  │               │     회전: 30°/s (재생 시)
│       │ ╰──── ────╯  │               │
│       ╰──────────────╯               │
│                                       │
│       KBS 클래식FM                    │  ← Channel Name
│       클래식의 향연                    │  ← Channel Label
│       · · ●━━ · ·                     │  ← Dot Indicators
│       ◁ 스와이프하여 채널 변경 ▷       │  ← Swipe Hint (6초 후 사라짐)
├────────────────────────────────────────┤
│  [===shimmer==========] LIVE          │  ← Live Progress (CH1,2)
│  [====●───────] 1:23 / 4:56          │  ← Playlist Progress (CH3,4,5)
├────────────────────────────────────────┤
│      ⏮  [⏺ 녹음]  [ ▶ ]  ⏭          │  ← Play Controls
│                                       │     메인 버튼: 62×62 원형
│          ⏺ 00:00 [WebM]              │  ← Rec Timer (녹음 시)
├────────────────────────────────────────┤
│  7/48 │ 1× 1.1× 1.25× 1.5× │        │  ← Playlist Extras (CH3,4)
│  🔀랜덤듣기  🔁이곡반복  📋목록        │     속도/랜덤/반복/목록
├────────────────────────────────────────┤
│  🔊 [━━━━━━●━━━━] 80                  │  ← Bottom Panel (Glass)
│  🕐 [10분] [30분] [1시간] [2시간]      │     볼륨 + 수면타이머
├────────────────────────────────────────┤
│  [📲 홈 화면에 추가]                    │  ← PWA Install (미설치 시)
│  예봄교회 · Yebom Radio 2.0            │  ← Footer
└────────────────────────────────────────┘
```

### 8.2 배경 시스템

**채널별 배경** (`applyChannelTheme()`):
- `bg-layer`: `linear-gradient(170deg, bg1, bg2 45%, bg3)` — 채널 accent에 맞춘 3색 어두운 그라데이션
- `ambient-glow`: `radial-gradient(circle, accent+22, transparent 70%)` — 디스크 뒤 원형 글로우 (280px, blur 50px)
- 전환 시 0.8s ease transition

**시간대별 오버레이** (`applyTimeOverlay()`):
| 시간대 | 시간 | 오버레이 |
|---|---|---|
| 밤 | 21:00~04:00 | `rgba(0,5,20,0.2)` 어두운 블루 |
| 새벽 | 04:00~07:00 | `rgba(40,20,60,0.1)` 보라 |
| 낮 | 07:00~17:00 | 투명 (채널 배경 그대로) |
| 저녁 | 17:00~21:00 | `rgba(30,10,0,0.1)` 따뜻한 톤 |

매 60초마다 자동 갱신.

### 8.3 바이닐 디스크

**크기**: 210×210px, `border-radius: 50%`

**5층 레이어 (아래→위)**:
1. **Grooves** (`.disc-grooves`): `repeating-radial-gradient` — LP 레코드 홈 패턴
2. **Conic Highlight** (`.disc-conic`): `conic-gradient` — 비대칭 빛 반사 (회전 시 시각 효과)
3. **Linear Reflection** (`.disc-linear`): 135° 선형 반사광
4. **SVG Shine** (`.disc-svg`): 대각선 라인 + 작은 원들 (빛 산란 효과)
5. **Accent Rings** (`.disc-ring-outer`, `.disc-ring-inner`): 채널 `discRing` 컬러 반투명 원형 테두리

**센터 라벨** (`.disc-center`):
- 80×80px, 채널 accent 그라데이션 배경
- SVG 아이콘 + 주파수/채널 텍스트
- **역회전**: 디스크 회전의 반대 방향으로 회전하여 내용이 항상 정면 유지

**회전 애니메이션**:
- `requestAnimationFrame` 기반 (CSS animation 아님)
- 30°/초 (LP 33⅓RPM 느낌)
- `discRotation = (discRotation + (dt/1000) * 30) % 360`
- 재생 시작: `startDiscRotation()`, 정지/일시정지: `stopDiscRotation()`
- `will-change: transform` 최적화

### 8.4 채널별 플로팅 파티클

각 채널마다 5~7개의 파티클이 화면 하단에서 상단으로 떠오른다:

| 채널 | 파티클 문자 | 의미 |
|---|---|---|
| KBS | ♪ ♫ ♩ 𝄞 ♬ ♪ | 음표들 |
| 극동방송 | ✦ ✧ ✝ ✦ ✧ | 별/십자가 |
| 말씀의 전당 | 📖 ✦ · ✦ · | 성경/별 |
| 찬양의 숲 | 🌿 🍃 · 🌱 · 🍃 · | 나뭇잎/새싹 |
| 봄소리 방송 | 🌸 ✿ · ❀ · 🌷 | 꽃 |

**애니메이션 스펙**:
```css
@keyframes floatUp {
  0%   { transform: translateY(0) rotate(0deg); opacity: 0 }
  20%  { opacity: 1 }
  100% { transform: translateY(-120px) rotate(20deg); opacity: 0 }
}
```
- 지속 시간: `8 + (index × 2)` 초 (8s, 10s, 12s, ...)
- 지연: 채널별 stagger (1.1~2.4초 간격)
- 불투명도: 0.04~0.12 (은은한 배경 효과)
- `prefers-reduced-motion: reduce` 시 비활성화

### 8.5 채널 전환

**스와이프/드래그**:
- Touch: `touchstart` → `touchmove` (translateX 피드백) → `touchend` (40px 임계값 초과 시 전환)
- Mouse: `mousedown` → `mousemove` → `mouseup` (동일 로직)
- 최대 이동량: ±80px

**기타 전환 방식**:
- 화살표 버튼 (좌/우)
- 도트 인디케이터 클릭
- 키보드 ← → 화살표 키
- 무한 루프: 첫 채널에서 왼쪽 → 마지막 채널, 마지막에서 오른쪽 → 첫 채널

**도트 인디케이터**:
- 활성 채널: 24px 너비 필 형태, 채널 accent 색상
- 비활성 채널: 8px 원형, `rgba(255,255,255,0.1)`
- `transition: all 0.4s cubic-bezier(0.4,0,0.2,1)`

**`switchToChannel(idx)`**:
1. `focusedIndex` 업데이트 (무한 루프 처리)
2. `applyChannelTheme()` — 배경, 글로우, 디스크, 버튼, 파티클, 도트 전환
3. `enterChannel()` — 이전 재생 중지, 새 채널 재생 시작
4. 스와이프 힌트 숨김

### 8.6 프로그레스 바

**라이브 프로그레스** (CH1, CH2):
- 4px 높이 바, 채널 accent 컬러 shimmer 애니메이션
- `liveBarShimmer`: `background-position` 이동, 3초 반복
- 좌하단: 빨간 점 펄스 + "실시간 방송 중"
- 우하단: "LIVE"

**재생목록 프로그레스** (CH3, CH4, CH5):
- 8px seek bar + 24px 원형 thumb (accent 컬러, 글로우 효과, 터치 최적화)
- `requestAnimationFrame` 으로 Howler.js의 `seek()`/`duration()` 실시간 갱신
- 드래그 seek 지원 (mouse + touch drag, 재생 중/멈춤 모두 가능)
- 시간 표시: `0:00 / 4:56` (Space Grotesk)

### 8.7 재생 컨트롤

**메인 재생 버튼** (`.main-play-btn`):
- 62×62px 원형, 채널 accent 그라데이션 배경
- SVG 아이콘: 재생(▶ 삼각형) / 일시정지(‖ 두 직사각형) 토글
- `updatePlayBtn(playing)`: SVG innerHTML 교체 + `startVis()`/`stopVis()` 연동

**보조 버튼**:
- ⏮ 이전 / ⏭ 다음 (R2 채널 전용, CH3, CH4)
- 녹음 버튼 (라이브 채널 전용, CH1, CH2, CH5)

### 8.8 재생목록 엑스트라 (CH3, CH4)

- 트랙 카운터: `7 / 48`
- 속도 버튼: **1×, 1.1×, 1.25×, 1.5×** (프로그램 설계 기준, 디자인 가이드와 다름)
- 랜덤듣기 / 이곡반복 / 목록 토글 버튼 (전곡반복은 기본 동작)
- 속도/수면타이머 버튼은 채널 accent 컬러로 스타일링

---

## 9. 핵심 기능 상세

### 9.1 HLS 재생 (CH1, CH2)

```
playHls(url, useProxy)
  → hls.js 동적 로드 (CDN)
  → HLS 프록시 설정: xhrSetup에서 요청 URL을 /api/hls-proxy?url= 로 변환
  → createMediaElementSource → GainNode → AudioContext.destination + recDestination
  → el.play()
```

- **iOS Safari 폴백**: `canPlayType('application/vnd.apple.mpegurl')` → 네이티브 HLS
- **AudioContext 통합**: `createMediaElementSource(audioEl)` — 한 번 연결하면 해제 불가이므로 앱 수명 동안 유지
- **프로그램명 갱신**: `setInterval(60000)` — `/api/kbs` 또는 `/api/febc-schedule` 호출

### 9.2 R2 재생 (CH3, CH4)

```
playTrack(channel, trackIndex, startPosition)
  → Howl({ src: streamUrl(key), html5: true, rate: currentSpeed })
  → onplay: startSeekUpdate(), resume seek position
  → onend: playNext()
```

- **URL 인코딩**: `key.split('/').map(encodeURIComponent).join('/')` — 슬래시는 유지, 한글 파일명은 인코딩
- **랜덤듣기**: Fisher-Yates 셔플 알고리즘 (`makeShuffleOrder()`)
- **이곡반복**: `repeatOn = true` → `playNext()` 에서 같은 트랙 재생
- **전곡반복**: 기본 동작 — 마지막 곡 끝나면 항상 첫 곡으로 순환

### 9.3 이어듣기 (CH3, CH4)

- **저장**: 5중 트리거 — `setInterval(5초)` + `beforeunload` + `pagehide` + `visibilitychange` + 트랙/채널 전환 직전
- **localStorage 키**: `radio-ch3-resume`, `radio-ch4-resume`
- **저장 데이터**: `{ trackKey, trackName, position, savedAt }`
- **복원 조건**: 7일 이내 + R2에 파일 존재 확인
- **최소 위치**: `position < 3`이면 저장하지 않음 (시작 직후 닫기 시 무시)

#### 9.3.1 트랙별 재생위치 (CH3 전용)

사용자가 트랙을 선택하면 저장된 위치에서 이어듣기. 자동 재생(순차/랜덤)은 처음부터.

- **localStorage 키**: `radio-ch3-trackpos`
- **형식**: `{ "radio/channel-list1/파일.mp3": { pos: 125.3, ts: 1710000000000 }, ... }`
- **만료**: 30일 (`TRACK_POS_MAX_AGE`), 끝까지 들으면 즉시 초기화
- **저장 시점**: `saveResume()` 호출 시 CH3이면 `saveTrackPosition()` 동시 호출

#### 9.3.2 서버 동기화 (로그인 사용자)

로그인 사용자는 트랙별 재생위치를 KV에 동기화하여 **다른 기기에서도 이어듣기** 가능.

**아키텍처**:
```
[로컬 저장]  ← 항상 기본 (비로그인/서버 장애 시에도 동작)
     ↕ 병합
[KV 저장]   ← 로그인 사용자만 (user:trackpos:{userId})
```

**API**:
- `GET /api/user/trackpos` — 서버 위치 조회 (헤더: `X-User-Id`)
- `PUT /api/user/trackpos` — 서버 위치 저장 (본문: `{ positions: {...} }`)

**동기화 전략**:
- **서버→로컬**: 앱 시작 시 `checkSsoSession()` 성공 후 1회 fetch → ts 비교 후 최신 데이터로 병합
- **로컬→서버**: 이벤트 기반 (트랙 전환, 채널 전환, 일시정지) + 2초 디바운스 + fire-and-forget
- **브라우저 종료**: `navigator.sendBeacon()`으로 즉시 전송 (비차단)
- **충돌 해결**: 양쪽 모두 ts(타임스탬프) 비교, 더 최신이 승리
- **서버 장애**: 무시 — 로컬이 항상 fallback

### 9.4 공유 스트리밍 (CH5)

```
startCh5Polling()
  → pollCh5State() 호출 (10초 간격)
  → KV에서 상태 가져오기 (/api/ch5/state)
  → targetTime = (Date.now() - state.startEpoch) / 1000
  → Howl 생성 + seek(targetTime)
  → 3초 이상 차이 시 seek로 보정
```

**관리자 워크플로**:
1. 관리자 패널에서 트랙 옆 "▶ ON AIR" 클릭
2. Howl로 duration 조회 → KV에 상태 저장 (startEpoch = now)
3. 청취자 poll 시 자동 동기화
4. 일시정지: KV에 `paused: true, currentTime: 현재위치` 저장
5. 종료: `trackKey: null` 저장

### 9.5 SSO 로그인 연동

**목적**: 녹음 기능 접근 제어 — 로그인한 사용자만 녹음 가능

**아키텍처**:
```
radio.yebom.org (클라이언트)
  → fetch('https://saint.yebom.org/api/auth/session', { credentials: 'include' })
  → saint_record_session 쿠키 (.yebom.org, sameSite: lax) 자동 전송
  → { isLoggedIn: true, user: { name, email, permission_level, ... } }
```

**세션 체크 흐름**:
1. 페이지 로드 시 localStorage 캐시 확인 (5분 TTL) → 즉시 화면 표시
2. `checkSsoSession({ force: true, merge: true })` → 교적부 session API 호출 (HTTP status로만 분기)
3. **탭 복귀 시**(`visibilitychange`) 재체크인 — 최소 간격 45초, **이어듣기 병합은 하지 않는다**
   (포커스마다 병합하면 재생 중에 다른 기기의 위치가 현재 이어듣기를 덮어쓴다)
4. 녹음 버튼 클릭 시 `radioUser` 확인 → 미로그인이면 로그인 모달 표시(이때는 스로틀 우회 `force: true`)
5. 로그인 모달 = **라디오 화면 내 이메일+비밀번호 폼 → 교적부로 직접 fetch**(인증 체계 §2). 교적부로 리다이렉트하지 않는다 — 전체 페이지 이동은 재생·녹음을 끊고, iOS 홈화면 PWA는 사파리와 쿠키 저장소가 분리되어 돌아온 쿠키를 쓸 수 없다. (카카오 전용 가입자만 리다이렉트 링크 사용)

**CORS 설정** (`saint-record-v2/src/app/api/auth/session/route.ts`):
- 허용 Origin: `radio.yebom.org`, `finance.yebom.org`, `prayer.yebom.org`, `v2.prayer.yebom.org`, `bible.yebom.org`
  (⚠️ `radio-axi.pages.dev`는 **미등록** — pages.dev에서는 CORS·SameSite 이중으로 체크인이 불가능하다)
- `Access-Control-Allow-Credentials: true`
- OPTIONS preflight 핸들러 포함

### 9.6 채널 공유 링크

**공유 버튼**: 채널명 옆 링크 아이콘 (`.share-btn`, 14px SVG, opacity 0.3)

**URL 형식**: `https://radio.yebom.org/?ch=3&track=radio/channel-list1/track.mp3`
- `ch`: 채널 번호 (1~6, 필수)
- `track`: R2 트랙 키 (CH3/CH4/CH5만, 라이브 채널은 생략)

**수신 처리**: `init()` → URL 파라미터 파싱 → `sharedTrack` 변수 설정 → `enterChannel()` → CH3/CH4 분기에서 `sharedTrack` 우선 처리 → `restoreResume`보다 우선

### 9.7 로딩 인디케이터

**디자인**: 재생 버튼(62×62) 바깥에 accent 색 회전 링 (`::after` pseudo-element, `btnSpin` 0.8s)

**흐름**: `enterChannel()` 진입 → `.loading` 추가 + 10초 안전 타임아웃 → 오디오 로드 완료/에러 → `.loading` 제거

**텍스트 피드백**: CH1/2/6 "연결 중..." (기존), CH3/4 "트랙 로딩 중...", CH5 "방송 확인 중..."

### 9.8 브라우저 녹음

**아키텍처**:
```
AudioSource (HLS audioEl / Howler _node)
  → MediaElementSource
  → GainNode (볼륨 제어)
  ├→ AudioContext.destination (스피커 출력)
  ├→ MediaStreamDestination (녹음 캡처)
  └→ AnalyserNode (무음 감지)

MediaRecorder(recDestination.stream)
  → recordedChunks[] → Blob → 다운로드
```

**무음 자동 분할**:
- `AnalyserNode.getFloatTimeDomainData()` → RMS 계산
- 임계값: `50 / 32767` (~0.0015)
- 무음 지속: 1초 이상 → `splitRecording()`
- 분할 시 현재 MediaRecorder stop → 저장 → 새 MediaRecorder 시작

**녹음 형식**:
- 기본: WebM/Opus (`audio/webm;codecs=opus`, 192kbps)
- 토글: WebM ↔ MP3 (UI 버튼으로 전환)
- Safari: `audio/webm` 미지원 시 `audio/mp4` 폴백 고려

**파일명 패턴**: `{채널명}_{프로그램명}_{YYMMDDHHmmss}.webm`

**중요**: Howler.js의 `<audio>` 노드 접근은 비공식 API (`_sounds[0]._node`) 사용. null 체크 필수.

### 9.9 수면 타이머

- 버튼: 10분 / 30분 / 1시간 / 2시간
- 동일 버튼 재클릭: 토글 OFF
- 동작: `setTimeout(stopPlayback + stopRecording, seconds * 1000)`
- 카운트다운: `setInterval(1초)` → 남은 시간 표시
- 버튼 스타일: 채널 accent 컬러 연동

### 9.10 관리자 패널

**진입**: 헤더 로고 3회 탭 → Admin Key 입력 (최초 1회, 이후 localStorage 캐시)

**탭 구조**:
- 말씀의 전당 (`list1`) / 찬양의 숲 (`list2`) / 봄소리 방송 (`stream`) / 녹음 설정 (`rec-settings`)

**기능**:
- 파일 업로드: 드래그&드롭 / 파일 선택, 10MB 이하 단일 업로드, 10MB 초과 시 R2 멀티파트 자동 분할(10MB 단위), 파일별 진행률/상태 표시
- 파일 삭제: confirm 후 `/api/delete`
- 순서 변경: HTML5 Drag & Drop → 순서 저장 (`/api/meta`)
- ON AIR: 봄소리 방송 탭에서 트랙별 "▶ ON AIR" 버튼
- 일시정지/종료: 라이브 제어 패널
- 녹음 설정: 무음 감지 레벨(10~500, 기본 50), 무음 지속 시간(1~30초, 기본 1초) 슬라이더, localStorage 저장

### 9.11 PWA

**`manifest.json`**:
```json
{
  "name": "예봄라디오",
  "short_name": "예봄라디오",
  "display": "standalone",
  "start_url": "/",
  "background_color": "#0D0B1A",
  "theme_color": "#1A1035"
}
```

**설치**:
- Chrome/Edge: `beforeinstallprompt` 이벤트 캡처 → 설치 버튼 표시
- iOS Safari: 수동 안내 모달 ("공유 → 홈 화면에 추가")
- 이미 standalone이면 버튼 숨김

**Service Worker** (`sw.js`):
- 캐시 이름: `yebom-radio-v3`
- **Network-first**: 네비게이션 요청 (index.html) → 온라인이면 최신, 오프라인이면 캐시
- **Cache-first**: 정적 자산 (아이콘, 폰트, manifest)
- **No cache**: 미디어 파일 (mp3, m3u8, ts 등) + API 요청 + 외부 도메인
- **자동 업데이트**: `activate` → `NEW_VERSION_ACTIVATED` 메시지 → 클라이언트 1.5초 후 reload
- **주기적 검사**: 30분마다 `reg.update()`

---

## 10. CSS 변수 및 테마 시스템

### 10.1 전역 CSS 변수
```css
:root {
  --bg-deep: #0D0B1A;
  --bg-mid: #1A1035;
  --bg-surface: rgba(255,255,255,0.06);
  --border-glass: rgba(255,255,255,0.10);
  --amber: #F59E0B;
  --red: #EF4444;
  --green: #22C55E;
  --text: #ece4d8;
  --text-dim: #9a9494;
  --text-mute: #3D3B55;
  --accent: #d4a45c;           /* 채널 전환 시 동적 변경 */
  --accent-light: #f0d490;     /* 채널 전환 시 동적 변경 */
  --current-ch-color: var(--accent);
  --current-ch-color-dim: rgba(212,164,92,0.15);
}
```

### 10.2 채널별 테마 컬러 전체표

| 채널 | accent | accentLight | bg1 | bg2 | bg3 | discRing |
|---|---|---|---|---|---|---|
| KBS | `#d4a45c` | `#f0d490` | `#1a150e` | `#1e1410` | `#14100c` | `#c9983f` |
| 극동방송 | `#c48a6a` | `#e8b898` | `#18100e` | `#1c1214` | `#120e10` | `#b87a58` |
| 말씀의 전당 | `#6a8cb8` | `#a0c0e0` | `#0e1218` | `#10141c` | `#0c0e16` | `#5878a0` |
| 찬양의 숲 | `#6aaa60` | `#a0d898` | `#0e1610` | `#101a12` | `#0c120e` | `#5a9850` |
| 봄소리 방송 | `#c87890` | `#e8a8b8` | `#181014` | `#1c1218` | `#140e12` | `#b06878` |

### 10.3 CSS 키프레임 애니메이션

| 애니메이션 | 용도 | 지속 시간 |
|---|---|---|
| `floatUp` | 파티클 상승 | 8~16s (채널별) |
| `liveBarShimmer` | 라이브 프로그레스 바 | 3s infinite |
| `recDot` | 녹음 점 깜빡임 | 1.2~1.5s infinite |
| `swipeL` / `swipeR` | 스와이프 힌트 화살표 | 1.5s infinite |
| `swipeHintFade` | 스와이프 힌트 등장→소멸 | 6s once |
| `livePulse` | 라이브 프로그레스 펄스 | (정의됨, CSS용) |
| `fadeInUp` | 토스트 메시지 등장 | 0.3s |

---

## 11. `nowPlayingEl` 프록시 패턴

기존 코드 호환성을 위해 `nowPlayingEl`을 JavaScript `Proxy`로 구현:

```javascript
const nowPlayingEl = new Proxy({}, {
  set(_, prop, value) {
    if (prop === 'textContent') headerSubtitle.textContent = value;
    else if (prop === 'innerHTML') headerSubtitle.innerHTML = value;
    return true;
  },
  get(_, prop) {
    if (prop === 'textContent') return headerSubtitle.textContent;
    if (prop === 'innerHTML') return headerSubtitle.innerHTML;
    return headerSubtitle[prop];
  }
});
```

`nowPlayingEl.textContent = '...'` / `.innerHTML = '...'` 호출 시 자동으로 헤더의 `#headerSubtitle` 엘리먼트에 반영.

---

## 12. localStorage 키 목록

| 키 | 용도 | 기본값 |
|---|---|---|
| `radio-worker-url` | Workers API URL (커스텀 도메인용) | (미사용, 코드에 하드코딩) |
| `radio-admin-key` | Admin 인증키 캐시 | `''` |
| `radio-last-channel` | 마지막 선택 채널 (1~5) | `'1'` |
| `radio-ch3-resume` | 채널3 이어듣기 JSON | `null` |
| `radio-ch4-resume` | 채널4 이어듣기 JSON | `null` |
| `radio-volume` | 볼륨 (0.0~1.0) | `'0.8'` |
| `radio-rec-format` | 녹음 형식 (`'webm'` \| `'mp3'`) | `'webm'` |
| `radio-rec-threshold` | 무음 감지 임계값 (raw, /32767 변환) | `50` |
| `radio-rec-silence-dur` | 무음 지속 시간 (ms) | `1000` |
| `radio-user` | SSO 로그인 캐시 JSON (`{ user, ts }`, 5분 TTL) | `null` |
| `radio-ch3-trackpos` | CH3 트랙별 재생위치 JSON (`{ trackKey: { pos, ts } }`, 30일 만료) | `{}` |

---

## 13. 배포

### Workers API
```bash
cd yebomradio
wrangler deploy        # worker.js → radio-worker
wrangler secret put ADMIN_KEY  # 최초 1회
```
- 커스텀 도메인: `radio-worker.yebomradio.workers.dev`

### 프론트엔드 (GitHub → Cloudflare Pages 자동)
```bash
cd yebomradio
git add index.html
git commit -m "설명"
git push origin main
# → Cloudflare Pages 자동 빌드/배포
# 프로젝트명: radio
# URL: radio.yebom.org (표준) / radio-axi.pages.dev (과도기 — 301 리다이렉트 예정)
```
- GitHub: `loginheaven-jpg/radio` (main 브랜치)
- Git 사용자: `loginheaven-jpg` / `loginheaven@gmail.com`

---

## 14. 주요 설계 결정 및 주의사항

### Warm Vinyl UI 전환 (v2.1)
- 이전 카드 캐러셀 UI → 바이닐 디스크 중심 UI로 전면 교체
- 디자인 참조: `UI-GUIDE.md` + `radio-vinyl.jsx` (React 프로토타입)
- **속도 버튼**은 디자인 가이드(0.75×/1×/1.25×/1.5×)와 달리 프로그램 설계 기준 **1×/1.1×/1.25×/1.5×** 유지
- **반복 버튼**: 이곡반복 토글만 제공, 전곡반복은 기본 동작
- **배경**: 채널별 배경 + 시간대별 미세 오버레이 (둘 다 적용)
- **배경 효과**: 기존 bg-orbs (floating orb 3개) → ambient glow + floating particles로 교체

### AudioContext 제약
- `createMediaElementSource(el)` — 한 번 연결하면 해제 불가
- HLS/Howler 각각의 `<audio>` 노드를 AudioContext에 연결할 때 1회성
- Howler의 `_sounds[0]._node`는 비공식 API → `null` 체크 + Howler 버전 고정 (2.2.4)

### HLS 프록시 비용
- 192kbps 스트림 → 시간당 ~86MB Worker 트래픽
- 소수 사용자(교회 내부)면 Cloudflare Workers 무료 플랜 내에서 처리 가능

### Safari 호환성
- `audio/webm` 미지원 → WebM 녹음 시 Safari에서는 `audio/mp4` mimeType 사용 필요
- hls.js 미지원 시 네이티브 HLS 폴백

### 접근성
- `prefers-reduced-motion: reduce` — 파티클, 디스크, 센터 라벨 애니메이션 비활성화
- 키보드 지원: ← → 채널 전환
- 버튼 `aria-label` 속성 제공

---

## 15. 함수 참조 (주요 함수 목록)

### 테마/UI
| 함수 | 설명 |
|---|---|
| `applyChannelTheme(ch)` | 채널별 배경, 글로우, 디스크, 버튼, 파티클, 도트 전환 |
| `applyTimeOverlay()` | 시간대별 미세 배경 오버레이 |
| `renderParticles(def)` | 채널 정의에 따른 파티클 DOM 생성 |
| `updateClock()` | 시계 HH:MM SS 갱신 |
| `buildDots()` / `updateDotIndicators()` | 도트 인디케이터 생성/갱신 |
| `startDiscRotation()` / `stopDiscRotation()` | 디스크 RAF 회전 시작/중지 |
| `initDiscSwipe()` | 스와이프/드래그/화살표/키보드 이벤트 초기화 |
| `switchToChannel(idx)` | 채널 전환 (무한 루프) |
| `updatePlayBtn(playing)` | 재생/일시정지 SVG 아이콘 토글 |

### 재생
| 함수 | 설명 |
|---|---|
| `enterChannel(channel)` | 채널 진입 (이전 재생 중지, UI 전환, 새 재생 시작) |
| `playHls(url, useProxy)` | HLS 라이브 스트리밍 시작 |
| `stopHls()` | HLS 중지 |
| `playTrack(channel, index, startPos)` | R2 트랙 재생 |
| `playNext(channel)` / `playPrev(channel)` | 다음/이전 트랙 |
| `handlePlayPause()` | 재생/일시정지 토글 (채널 유형별 분기) |
| `startSeekUpdate()` | seek 프로그레스 RAF 갱신 |
| `loadKbs()` / `loadFebc()` | CH1/CH2 라이브 스트림 로드 |
| `startCh5Polling()` / `pollCh5State()` | CH5 상태 폴링 |

### 이어듣기
| 함수 | 설명 |
|---|---|
| `saveResume(channel)` | 현재 위치 localStorage 저장 |
| `restoreResume(channel)` | 저장된 위치 복원 (7일 만료, R2 존재 검증) |

### 녹음
| 함수 | 설명 |
|---|---|
| `initAudioContext()` | AudioContext + GainNode + destinations 초기화 |
| `connectHowlToAudioCtx()` | Howler `<audio>` 노드를 AudioContext에 연결 |
| `startRecording()` | MediaRecorder 시작 + 무음 감지 시작 |
| `stopRecording()` | MediaRecorder 중지 + 파일 다운로드 |
| `splitRecording()` | 무음 감지 시 세그먼트 분할 |
| `startSilenceDetection()` / `stopSilenceDetection()` | RMS 기반 무음 감지 |
| `generateRecFilename()` | 녹음 파일명 생성 |

### 관리자
| 함수 | 설명 |
|---|---|
| `handleHeaderTap()` | 헤더 3탭 감지 |
| `openAdmin()` / `closeAdmin()` | 관리자 패널 열기/닫기 |
| `loadAdminTracks(ch)` | 관리자 트랙 목록 로드 |
| `handleAdminFiles(fileList)` | 업로드 큐에 파일 추가 |
| `uploadAll()` | 큐의 모든 파일 업로드 (≤10MB 단일, >10MB 멀티파트 자동) |
| `saveAdminOrder()` | 트랙 순서 저장 (`/api/meta`) |
| `goOnAir(track)` | CH5 ON AIR 시작 |
| `toggleCh5Pause()` / `stopCh5Broadcast()` | CH5 일시정지/종료 |

### PWA / 업데이트
| 함수 | 설명 |
|---|---|
| `initPwa()` | PWA 설치 프롬프트 + iOS 가이드 |
| `initAutoUpdate()` | SW 등록 + 업데이트 감지 + 자동 리로드 |

---

## 16. 변경 이력

| 날짜 | 버전 | 변경 내용 |
|---|---|---|
| 2026-03-01 | v2.0 | 초기 통합 버전. 카드 캐러셀 UI, 5채널, HLS/R2/KV. |
| 2026-03-01 | v2.0.1 | R2 Range Request 버그 수정 (offset+length). URL 인코딩 수정. |
| 2026-03-01 | v2.0.2 | 브라우저 네이티브 녹음 (MediaRecorder + AudioContext). HLS 프록시 추가. 무음 자동 분할. 형식 선택. 캐러셀 무한 회전. 속도 버튼 추가. |
| 2026-03-02 | v2.1 | **Warm Vinyl UI 전면 리디자인**. 카드 캐러셀 → 바이닐 디스크. 채널별 테마(컬러, 배경, 디스크링, 파티클). 앰비언트 글로우 + 시간대 오버레이. 스와이프/화살표/키보드 채널 전환. SVG 재생 컨트롤. Pretendard + Space Grotesk 폰트. |
| 2026-03-02 | v2.1.1 | HLS 프록시 상대 URL 해석 수정 (pLoader/fLoader + response.url 복원). CH5 라이브 채널 UI 수정. SW 캐시 v4. |
| 2026-03-02 | v2.1.2 | CH3/CH4 간헐적 무음 수정 (AudioContext lazy, Howler crossOrigin 패치). |
| 2026-03-02 | v2.2 | **라이브 방송 시스템**. Workers API 8개 엔드포인트 (청크 업로드/다운로드, 상태, 보존정책, 세션관리). 파일 ON AIR ↔ 라이브 상호잠금. AudioContext 기반 청크 플레이어 + 다시듣기. 관리자 패널 (라이브 상태/보존설정/세션삭제). 트랙 목록 지난 방송 섹션. Python 호스트 앱 (FFmpeg 믹싱 + tkinter GUI). |
| 2026-03-03 | v2.2.1 | **호스트 앱 파일 방송 통합**. 라이브 전용 → 탭 UI(라이브+파일). api_client.py 신규 (트랙 관리/CH5 상태/업로드). 파일 선택·업로드·트랙 목록·ON AIR·일시정지·종료·순서 변경. 라이브↔파일 상호잠금(UI+409). host/ 폴더를 git 저장소 안으로 이동. |
| 2026-03-03 | v2.2.2 | **라이브 방송 품질 대폭 개선**. Cache API로 매 청크마다 latestChunk 실시간 전파 (KV 10초→2초 지연). 클라이언트 순차 fetch로 청크 순서 보장. 버퍼 언더런 갭 제거. 투기적 +2청크 선행 fetch. 연속 에러 시 자동 연결 끊김 처리. 대형 파일 멀티파트 업로드(R2). 업로드 진행률 UI. |
| 2026-03-03 | v2.2.3 | **재생목록 자동 갱신** (CH3-5, 5분 주기). 관리자 **녹음 설정 탭** (무음 감지 레벨/지속 시간 슬라이더, localStorage 저장). |
| 2026-03-03 | v2.2.4 | **CH3 등잔 비주얼**. 말씀의 전당 채널에 LP 디스크 대신 Canvas 등잔 애니메이션 (미니멀 라인 스타일, 불꽃+성경 구절). 채널 전환 시 디스크↔등잔 자동 토글. |
| 2026-03-03 | v2.2.5 | **Seek bar 드래그** (mouse+touch, 재생/멈춤 모두 가능). Thumb 24px 확대 (터치 최적화). CH3 등잔 멈춤 시 작은 불꽃 유지 (애니메이션 정지 버그 수정). 성경 구절 글씨 2배 확대 (10→20px). |
| 2026-03-04 | v2.3.0 | **곡명 인식 (ACRCloud)**. CH1/CH2 라이브 채널에서 "곡명" 버튼으로 현재 재생 곡 식별. Workers가 HLS 세그먼트 3개(~12초) 병합 fetch → ACRCloud Identification API. 결과 카드 UI (제목/아티스트/작곡가/앨범/정확도). |
| 2026-03-04 | v2.3.1 | **곡명 인식 버그 수정**. 극동방송 m3u8 URL 수정 (404→정상). 세그먼트 1개→3개 병합으로 인식 정확도 향상. 파일명 sample.ts→sample.aac 수정. |
| 2026-03-04 | v2.4.0 | **SSO 로그인 연동**. 녹음 기능에 로그인 게이팅 추가. 교적부(saint.yebom.org) 세션 API CORS 연동. 로그인 모달 UI. localStorage 캐시 (5분 TTL). 미로그인 시 녹음 버튼 클릭 → 로그인 팝업 → 교적부 로그인 페이지 리다이렉트. |
| 2026-03-06 | v2.5.0 | **채널 공유 링크 + 로딩 인디케이터**. 채널명 옆 공유 아이콘으로 현재 채널+곡 URL 클립보드 복사 (`?ch=3&track=...`). URL 파라미터로 공유 링크 수신 시 해당 채널/곡 자동 재생. 채널 전환 시 재생 버튼에 회전 링 로딩 애니메이션. CH3/4/5 로딩 중 텍스트 피드백 추가. 10초 안전 타임아웃. |
| 2026-03-06 | v2.5.1 | **채널 설정 서버 동기화**. Workers KV에 채널 설정 저장 (`GET/PUT /api/channel-config`). 관리자가 설정하면 모든 기기에 동일 적용. 프론트엔드 초기화 시 서버 설정 fetch → localStorage 동기화. 관리자 저장 시 서버에 PUT. |
| 2026-03-18 | v2.6.0 | **오디오 스톨 자동 복구 + 트랙별 재생위치 서버 동기화**. StallWatchdog(5초 간격 currentTime 감시, 3회 연속 스톨 시 채널 재연결). HLS/Icecast/R2 에러 핸들러 강화. CH3 트랙별 재생위치 기억(사용자 선택=이어듣기, 자동재생=처음부터). 로그인 사용자는 KV(`user:trackpos:{userId}`)에 동기화하여 다기기 이어듣기. .opus 포맷 지원. 푸터 클릭 로그인/로그아웃. |
| 2026-03-23 | — | **이메일+비밀번호 로그인으로 전환**(`dd04cb7`). 간편 로그인(이름+전화4자리)과 "예봄서비스로 로그인" 리다이렉트 버튼 제거. 워커 `handleSimpleLogin` → `handleEmailLogin`(교적부 검증 위임). |
| 2026-08-03 | — | **교적부 SSO `permission_level` 기반 관리자 인증**(`69d7877`). 로그인 시 HS256 JWT 발급(7일) → `isAdmin()`이 JWT role 검증, 레거시 `ADMIN_KEY` 폴백 유지. Admin Key 오입력 재유도 + 401 시 authModal 자동 재표시. |
| 2026-09-12 | v2.7.0 | **SSO 로그인 개선 A·C단계**. ① 체크인을 **HTTP status로만 분기** — 500·네트워크 오류에 로그아웃하지 않음(교적부 장애 시 전 사용자 로그아웃 버그 수정). 최소 호출 간격 45초 + `*.yebom.org` 호스트 가드 + **탭 복귀 체크인** 추가(이어듣기 병합은 분리). ② **신원 정규화(`normalizeUser`)** — 교적부 `user_id`/`permission_level`과 워커 `id`/`role`을 통일하고, `id`가 없으면 신원 전송 차단(`X-User-Id: undefined` 제거). ③ 워커 **CORS 정확 일치 화이트리스트**(부분일치 정규식·`*` 폴백 제거, `Vary: Origin` 추가). ④ **로그아웃 개편** — 자격증명·개인 데이터만 정밀 삭제(기기 취향 보존) 후 교적부 통합 로그아웃으로 이동. |
| 2026-09-12 | v2.7.1 | **SSO 로그인 개선 B단계 — 브라우저에서 교적부로 직접 로그인**. 로그인 폼이 워커 경유 대신 `saint.yebom.org/api/auth/login`을 `credentials:'include'`로 직접 호출 → **세션 쿠키가 브라우저에 설치되어 체크인 200·400일 슬라이딩 연장·통합 로그아웃이 성립**. 로그인 응답에 사용자 정보가 없으므로 성공 후 체크인으로 신원 수령. "로그인 유지" 체크박스(기본 ON, 공용 기기 해제용)와 **카카오 로그인 링크**(리다이렉트 — 재생 중단 안내 포함) 추가. 체크인 401에서 **JWT 삭제 활성화**(레거시 공유 ADMIN_KEY는 보존) + 개인 UI 즉시 감춤 + 일회성 재로그인 안내. `radio-axi.pages.dev`·`localhost`는 교적부 CORS 미허용이라 레거시 워커 경로로 폴백. |

---

## 17. Python 호스트 앱 (`host/`)

### 17.1 개요

봄소리 방송 관리 데스크톱 앱. **두 가지 모드**를 지원한다:
- **라이브 방송**: 마이크 + PC 사운드를 FFmpeg로 캡처 → Opus/OGG 2초 청크 → Workers API 업로드 → Cache API로 실시간 latestChunk 전파 → 클라이언트 순차 fetch + AudioContext 스케줄링
- **파일 방송**: 오디오 파일 업로드, 트랙 관리, ON AIR/일시정지/종료 (웹 관리자 패널과 동일 기능)

두 모드는 **상호 배타적** — Workers API가 409 충돌 응답으로 강제하며, 호스트 앱 UI에서도 선제 차단한다.

### 17.2 모듈 구조

| 파일 | 역할 |
|------|------|
| `host.py` | tkinter GUI 메인 (탭 UI, 이벤트 핸들링) |
| `config.py` | 상수 (CHUNK_DURATION=2.0, SAMPLE_RATE=48000, BITRATE=128k 등) |
| `audio_engine.py` | FFmpeg DirectShow 캡처 → 청크 분할 → 콜백 |
| `uploader.py` | 라이브 청크 큐 기반 업로드 (start/stop/upload_chunk) |
| `api_client.py` | 파일 방송 API (트랙 CRUD, CH5 상태, 잠금 확인) |

### 17.3 GUI 레이아웃

```
Window (500×660, 다크 테마 #1a1726)
├── 헤더: "봄소리 호스트"
├── 서버 설정: Workers URL + Admin Key
├── ttk.Notebook (탭)
│   ├── "라이브 방송" 탭
│   │   ├── 방송 제목, 오디오 장치 (마이크/PC사운드)
│   │   ├── 볼륨 슬라이더, 시작/종료 버튼
│   │   └── 상태, 타이머, 청크 카운터
│   └── "파일 방송" 탭
│       ├── 파일 선택 + 업로드 (진행바)
│       ├── 트랙 목록 (Treeview) + ▲▼ ON AIR 삭제 버튼
│       ├── ON AIR 상태 + 일시정지/종료 제어
│       └── 잠금 경고 (라이브 방송 중일 때)
```

### 17.4 API 사용

| 모듈 | 엔드포인트 | 용도 |
|------|-----------|------|
| uploader.py | `POST /api/live/state` | 라이브 시작/종료 |
| uploader.py | `POST /api/live/chunk` | 오디오 청크 업로드 |
| api_client.py | `GET /api/tracks?channel=stream` | CH5 트랙 목록 |
| api_client.py | `POST /api/upload` | 파일 업로드 (multipart) |
| api_client.py | `POST /api/delete` | 트랙 삭제 |
| api_client.py | `POST /api/meta` | 트랙 순서 저장 |
| api_client.py | `GET/POST /api/ch5/state` | ON AIR 상태 조회/변경 |
| api_client.py | `GET /api/live/state` | 라이브 잠금 확인 |

### 17.5 환경 요구사항

- Python 3.10+
- FFmpeg (PATH에 등록 또는 절대경로)
- PC 사운드 캡처: Windows 스테레오 믹스 활성화 필요
- 의존성: `pip install requests`

### 17.6 실행

```bash
cd yebomradio/host
pip install -r requirements.txt
python host.py
```

### 17.7 빌드 (exe 배포)

```bash
cd yebomradio/host
pip install pyinstaller
build.bat
# → dist/봄소리호스트.exe
```
