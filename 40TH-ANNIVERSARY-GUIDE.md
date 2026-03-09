# 예봄라디오 40주년 기념 UI 구현 가이드

> **문서 버전**: v1.0  
> **대상 파일**: `index.html` (단일 파일)  
> **참조 프로토타입**: `40th-anniversary-prototype.jsx` (React 프로토타입, 비주얼 레퍼런스 전용)  
> **작업 범위**: CSS 추가, HTML 삽입, JS 함수 3개 추가. **기존 로직 수정 최소화.**

---

## 개요

예봄교회 40주년을 기념하여 라디오 앱에 세 가지 시각 요소를 추가한다.

| 기능 | 설명 | 노출 조건 |
|------|------|-----------|
| **셀레브레이션 스플래시** | 전체화면 축하 팝업 + 골드 컨페티 | 최초 1회 (localStorage 플래그) |
| **로고 골드 펄스** | 헤더 `40'` 텍스트에 은은한 glow 애니메이션 | 상시 |
| **LP 원형 텍스트** | 바이닐 디스크에 SVG 원형 textPath로 `SINCE 1986` / `40TH ANNIVERSARY` | 상시 (CH3 등잔 모드 제외) |

---

## ⚠️ 스코프 제한 — 반드시 준수

- **수정 허용**: 아래 명시된 CSS, HTML, JS 삽입/수정만 수행한다.
- **절대 금지**: 오디오 재생 로직, 채널 전환 로직, 관리자 패널, 서비스 워커(`sw.js`), 워커(`worker.js`) 일체 수정 금지.
- 기존 CSS 클래스(`.logo-40`, `.disc-center`, `.vinyl-disc` 등)의 원본 속성은 건드리지 않는다. 새 속성을 **추가**만 한다.
- `applyChannelTheme()` 함수에 **2줄만** 추가한다 (원형 텍스트 색상 반영). 그 외 라인 변경 금지.

---

## 1. CSS 추가

`</style>` 태그 직전, 기존 `@media(prefers-reduced-motion:reduce)` 뒤에 아래 블록을 삽입한다.

### 삽입 위치

```
@media(prefers-reduced-motion:reduce){.particle,.vinyl-disc,.disc-center{animation:none!important}}

/* ▼▼▼ 여기부터 삽입 ▼▼▼ */
```

### 삽입 코드

```css
/* ── 40th Anniversary ─────────────────────────────────────── */

/* 1-A: Logo Gold Pulse */
@keyframes goldPulse {
  0%, 100% { text-shadow: 0 0 4px rgba(240,192,96,0.0); color: #f0c060; }
  50% { text-shadow: 0 0 18px rgba(240,192,96,0.5), 0 0 40px rgba(212,164,92,0.2); color: #ffe8a0; }
}
.logo-40 { animation: goldPulse 3s ease-in-out infinite; }

/* 1-B: Circular Text on Disc */
.disc-circle-text {
  position: absolute; inset: 0; width: 210px; height: 210px;
  pointer-events: none; z-index: 1;
}
.disc-circle-text text {
  font-family: 'Space Grotesk', monospace;
  font-weight: 500;
}

/* 1-C: Celebration Splash */
.anniversary-splash {
  position: fixed; inset: 0; z-index: 9999;
  background: #0D0B1A;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  opacity: 1; transition: opacity 0.8s ease;
  overflow: hidden;
}
.anniversary-splash.fade-out { opacity: 0; pointer-events: none; }
.anniversary-splash .splash-glow {
  position: absolute; top: 38%; left: 50%; transform: translate(-50%, -50%);
  width: 340px; height: 340px; border-radius: 50%;
  background: radial-gradient(circle, rgba(212,164,92,0.18) 0%, rgba(212,164,92,0.05) 40%, transparent 70%);
  filter: blur(30px); pointer-events: none;
  opacity: 0; transition: opacity 1.5s ease 0.3s;
}
.anniversary-splash.visible .splash-glow { opacity: 1; }
.anniversary-splash .splash-content {
  position: relative; z-index: 3; text-align: center; padding: 0 32px;
}
.splash-cross {
  font-size: 18px; color: #d4a45c; letter-spacing: 8px; margin-bottom: 16px;
  opacity: 0; transform: translateY(10px); transition: all 1s ease 0.2s;
}
.anniversary-splash.visible .splash-cross { opacity: 0.5; transform: translateY(0); }
.splash-number {
  font-family: 'Space Grotesk', monospace; font-size: 120px; font-weight: 700;
  line-height: 1; letter-spacing: -4px;
  background: linear-gradient(135deg, #c9983f 0%, #f0d490 40%, #d4a45c 60%, #e8c868 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
  filter: drop-shadow(0 4px 30px rgba(212,164,92,0.3));
  opacity: 0; transform: scale(0.8); transition: all 1s cubic-bezier(0.34,1.56,0.64,1) 0.3s;
}
.anniversary-splash.visible .splash-number { opacity: 1; transform: scale(1); }
.splash-subtitle {
  font-family: 'Space Grotesk', monospace; font-size: 13px; font-weight: 500;
  color: #d4a45c; letter-spacing: 6px; text-transform: uppercase; margin-top: 4px;
  opacity: 0; transform: translateY(8px); transition: all 0.8s ease 0.6s;
}
.anniversary-splash.visible .splash-subtitle { opacity: 0.7; transform: translateY(0); }
.splash-divider {
  width: 60px; height: 1px; margin: 24px auto;
  background: linear-gradient(90deg, transparent, #d4a45c, transparent);
  opacity: 0; transition: opacity 1s ease 0.8s;
}
.anniversary-splash.visible .splash-divider { opacity: 0.5; }
.splash-message {
  font-size: 22px; font-weight: 700; color: #ece4d8;
  opacity: 0; transform: translateY(10px); transition: all 0.8s ease 0.9s;
}
.anniversary-splash.visible .splash-message { opacity: 1; transform: translateY(0); }
.splash-years {
  font-family: 'Space Grotesk', monospace; font-size: 13px; color: #9a9494;
  margin-top: 8px; letter-spacing: 3px;
  opacity: 0; transition: opacity 1s ease 1.1s;
}
.anniversary-splash.visible .splash-years { opacity: 0.5; }
.splash-scripture {
  font-size: 13px; line-height: 1.8; color: #c9b896; margin-top: 28px;
  max-width: 300px; margin-left: auto; margin-right: auto;
  opacity: 0; transform: translateY(8px); transition: all 0.8s ease 1.3s;
}
.anniversary-splash.visible .splash-scripture { opacity: 0.6; transform: translateY(0); }
.splash-enter-btn {
  margin-top: 36px; padding: 14px 48px; border-radius: 30px;
  border: 1px solid rgba(212,164,92,0.4);
  background: linear-gradient(135deg, rgba(212,164,92,0.15), rgba(212,164,92,0.05));
  color: #f0d490; font-size: 14px; font-weight: 600; cursor: pointer;
  letter-spacing: 2px; backdrop-filter: blur(8px);
  opacity: 0; transform: translateY(15px);
  transition: all 0.8s ease 1.6s, background 0.3s, border-color 0.3s;
}
.anniversary-splash.visible .splash-enter-btn { opacity: 1; transform: translateY(0); }
.splash-enter-btn:hover, .splash-enter-btn:active {
  background: linear-gradient(135deg, rgba(212,164,92,0.3), rgba(212,164,92,0.1));
  border-color: rgba(212,164,92,0.7);
}
```

---

## 2. HTML 추가

### 2-A. 셀레브레이션 스플래시 (splash)

`<body>` 태그 바로 뒤, `<div class="bg-layer">` 바로 앞에 삽입한다.

#### 삽입 위치

```html
<body>
<!-- ▼▼▼ 여기에 삽입 ▼▼▼ -->
<div class="bg-layer" id="bgLayer"></div>
```

#### 삽입 코드

```html
<!-- 40th Anniversary Splash -->
<div class="anniversary-splash" id="anniversarySplash">
  <canvas id="confettiCanvas" style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:2"></canvas>
  <div class="splash-glow"></div>
  <div class="splash-content">
    <div class="splash-cross">✦ ✝ ✦</div>
    <div class="splash-number">40</div>
    <div class="splash-subtitle">ANNIVERSARY</div>
    <div class="splash-divider"></div>
    <div class="splash-message">예봄교회 40주년을 축하합니다</div>
    <div class="splash-years">1986 — 2026</div>
    <div class="splash-scripture">
      "여호와 우리 하나님의 은총을 우리에게 임하게 하사<br>
      우리의 손이 행한 일을 우리에게 견고하게 하소서"<br>
      <span style="font-size:11px;opacity:0.6;margin-top:4px;display:inline-block">— 시편 90:17</span>
    </div>
    <button class="splash-enter-btn" id="splashEnterBtn">라디오 시작하기</button>
  </div>
</div>
```

### 2-B. LP 원형 텍스트 SVG

`<div class="disc-ring-inner" id="discRingInner"></div>` 바로 뒤, `<div class="disc-center" id="discCenter">` 바로 앞에 삽입한다.

#### 삽입 위치

```html
      <div class="disc-ring-inner" id="discRingInner"></div>
      <!-- ▼▼▼ 여기에 삽입 ▼▼▼ -->
      <div class="disc-center" id="discCenter">
```

#### 삽입 코드

```html
      <svg class="disc-circle-text" id="discCircleText" viewBox="0 0 210 210">
        <defs>
          <path id="circlePathTop" d="M 105,105 m -52,0 a 52,52 0 1,1 104,0 a 52,52 0 1,1 -104,0" fill="none"/>
          <path id="circlePathBottom" d="M 105,105 m 52,0 a 52,52 0 1,1 -104,0 a 52,52 0 1,1 104,0" fill="none"/>
        </defs>
        <text id="circleTextTop" fill="#d4a45c" opacity="0.5" style="font-size:8px;letter-spacing:3px">
          <textPath href="#circlePathTop" startOffset="50%" text-anchor="middle">✦ SINCE 1986 ✦</textPath>
        </text>
        <text id="circleTextBottom" fill="#d4a45c" opacity="0.4" style="font-size:7.5px;letter-spacing:2.5px">
          <textPath href="#circlePathBottom" startOffset="50%" text-anchor="middle">40TH ANNIVERSARY</textPath>
        </text>
      </svg>
```

---

## 3. JavaScript 추가

### 3-A. `applyChannelTheme()` 수정 (2줄 추가)

기존 `applyChannelTheme()` 함수 내부에서, 아래 기존 코드를 찾는다:

```js
  $('discRingOuter').style.borderColor = def.discRing + '12';
  $('discRingInner').style.borderColor = def.discRing + '08';
```

그 **바로 뒤**에 다음 2줄을 추가한다:

```js
  // 40th: 원형 텍스트 색상 채널 연동
  $('circleTextTop').setAttribute('fill', def.accent);
  $('circleTextBottom').setAttribute('fill', def.accent);
```

### 3-B. 셀레브레이션 스플래시 + 컨페티 (새 함수)

`init()` 함수 **바로 위**에 아래 코드 블록 전체를 삽입한다.

#### 삽입 위치

```js
// ── Init ──
async function init() {
```

위의 `// ── Init ──` 주석 **바로 앞**에 삽입.

#### 삽입 코드

```js
// ── 40th Anniversary Splash ──────────────────────────────────
const ANNIV_SPLASH_KEY = 'yebom-40th-seen';
const ANNIV_START = new Date('2026-04-01T00:00:00+09:00');
const ANNIV_END   = new Date('2026-04-30T23:59:59+09:00');

function isAnniversaryPeriod() {
  const now = new Date();
  return now >= ANNIV_START && now <= ANNIV_END;
}

function shouldShowSplash() {
  return isAnniversaryPeriod() && !localStorage.getItem(ANNIV_SPLASH_KEY);
}

function initAnniversarySplash() {
  const splash = $('anniversarySplash');
  if (!splash || !shouldShowSplash()) {
    if (splash) splash.remove();
    return;
  }

  // Phase 1: show content animations
  requestAnimationFrame(() => {
    splash.classList.add('visible');
  });

  // Start confetti
  runConfetti($('confettiCanvas'));

  // Auto-dismiss after 8s
  const autoTimer = setTimeout(dismissSplash, 8000);

  // Button click
  $('splashEnterBtn').addEventListener('click', () => {
    clearTimeout(autoTimer);
    dismissSplash();
  });

  function dismissSplash() {
    splash.classList.add('fade-out');
    localStorage.setItem(ANNIV_SPLASH_KEY, '1');
    setTimeout(() => splash.remove(), 900);
  }
}

function runConfetti(canvas) {
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.offsetWidth * dpr;
  const H = canvas.offsetHeight * dpr;
  canvas.width = W; canvas.height = H;
  ctx.scale(dpr, dpr);
  const cW = canvas.offsetWidth, cH = canvas.offsetHeight;

  const GOLD = ['#d4a45c','#f0d490','#c9983f','#e8c868','#b8862a','#fff8e0','#f5dfa0','#a07830','#dfc070','#ffe8a0'];
  const particles = [];

  function spawn(count) {
    for (let i = 0; i < count; i++) {
      particles.push({
        x: Math.random() * cW,
        y: -20 - Math.random() * cH * 0.3,
        w: 4 + Math.random() * 8,
        h: 6 + Math.random() * 10,
        color: GOLD[Math.floor(Math.random() * GOLD.length)],
        rot: Math.random() * Math.PI * 2,
        rotV: (Math.random() - 0.5) * 0.15,
        vx: (Math.random() - 0.5) * 3,
        vy: 2 + Math.random() * 4,
        shape: Math.floor(Math.random() * 4),
        opacity: 0.6 + Math.random() * 0.4,
        wobble: Math.random() * Math.PI * 2,
        wobbleV: 0.02 + Math.random() * 0.04,
      });
    }
  }

  spawn(150);
  setTimeout(() => spawn(80), 600);

  let raf;
  function draw() {
    ctx.clearRect(0, 0, cW, cH);
    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i];
      p.x += p.vx + Math.sin(p.wobble) * 0.8;
      p.y += p.vy;
      p.rot += p.rotV;
      p.wobble += p.wobbleV;
      p.vy += 0.04;
      p.opacity -= 0.002;
      if (p.y > cH + 20 || p.opacity <= 0) { particles.splice(i, 1); continue; }
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rot);
      ctx.globalAlpha = p.opacity;
      ctx.fillStyle = p.color;
      if (p.shape === 0) ctx.fillRect(-p.w/2, -p.h/2, p.w, p.h);
      else if (p.shape === 1) { ctx.beginPath(); ctx.arc(0, 0, p.w/2, 0, Math.PI*2); ctx.fill(); }
      else if (p.shape === 2) {
        ctx.beginPath();
        for (let j = 0; j < 8; j++) {
          const r = j % 2 === 0 ? p.w/2 : p.w/5;
          ctx.lineTo(Math.cos(j*Math.PI/4)*r, Math.sin(j*Math.PI/4)*r);
        }
        ctx.closePath(); ctx.fill();
      } else ctx.fillRect(-p.w/2, -1, p.w, 2.5);
      ctx.restore();
    }
    if (particles.length > 0) raf = requestAnimationFrame(draw);
  }
  draw();
}
```

### 3-C. `init()` 함수에 스플래시 호출 1줄 추가

`init()` 함수의 **맨 첫 줄** (기존 `applyTimeOverlay()` 호출 바로 위)에 아래 1줄을 추가한다.

```js
async function init() {
  initAnniversarySplash();  // ← 이 줄 추가
  applyTimeOverlay();
  ...
```

---

## 4. 동작 정리

### 스플래시 라이프사이클

```
DOMContentLoaded
  → init()
    → initAnniversarySplash()
      → 날짜 조건 확인 (ANNIV_START ~ ANNIV_END)
      → localStorage 'yebom-40th-seen' 확인
      → 조건 충족 시:
        - splash.visible 클래스 추가 (CSS transition 작동)
        - runConfetti() 호출 (골드 컨페티 230개)
        - 8초 auto-dismiss 또는 버튼 클릭
        - fade-out → 0.9초 후 DOM에서 remove()
      → 미충족 시:
        - splash DOM 즉시 remove()
    → 이하 기존 init 로직 계속
```

### 원형 텍스트 회전

기존 코드에서 이미 `vinylDisc.style.transform = rotate(${discRotation}deg)` 로 디스크 전체를 회전시키고 있다. SVG 원형 텍스트는 `.vinyl-disc` 내부에 위치하므로 **자동으로 함께 회전**한다. 별도 회전 로직 추가 불필요.

`discCenter`는 기존 counter-rotate(`-discRotation`)가 적용되어 있으므로, 센터 내부 텍스트는 항상 정위치를 유지한다. 원형 텍스트는 센터 밖(반경 52px 궤도)에 있으므로 디스크와 함께 돈다.

### CH3 등잔 모드 처리

`applyChannelTheme()`에서 CH3 진입 시 `vinylDisc.style.display = 'none'`이 실행된다. 원형 텍스트 SVG는 `.vinyl-disc` 내부에 있으므로 **자동으로 함께 숨겨진다.** 별도 처리 불필요.

### 로고 골드 펄스

CSS 애니메이션만으로 동작. 기존 `.logo-40` 클래스에 `animation` 속성이 추가되며, 3초 주기로 `text-shadow` glow가 pulse한다. JS 수정 없음.

---

## 5. 날짜 설정

현재 기본값은 **2026년 4월 1일 ~ 4월 30일** (KST)이다. 교회 일정에 따라 `ANNIV_START`, `ANNIV_END` 상수를 수정하면 된다.

**개발 테스트 시**: `shouldShowSplash()` 함수의 `isAnniversaryPeriod()` 조건을 일시적으로 `true`로 바꾸거나, 브라우저 콘솔에서 `localStorage.removeItem('yebom-40th-seen')` 실행 후 새로고침하면 스플래시를 반복 확인할 수 있다.

---

## 6. 체크리스트

구현 완료 후 아래 항목을 확인한다.

- [ ] 최초 방문 시 골드 컨페티 + 축하 메시지 스플래시 표시
- [ ] "라디오 시작하기" 버튼 또는 8초 경과 시 페이드아웃
- [ ] 재방문 시 스플래시 표시되지 않음 (localStorage 확인)
- [ ] 헤더 `40'` 텍스트에 골드 펄스 glow 애니메이션
- [ ] LP 디스크에 `✦ SINCE 1986 ✦` (상단 호) + `40TH ANNIVERSARY` (하단 호) 원형 텍스트 표시
- [ ] 채널 전환 시 원형 텍스트 색상이 채널 accent 색으로 변경
- [ ] 재생 시 원형 텍스트가 디스크와 함께 회전
- [ ] CH3(말씀의 전당) 등잔 모드에서 원형 텍스트 자동 숨김
- [ ] 기존 오디오 재생, 채널 전환, 관리자 패널 등 모든 기능 정상 동작
