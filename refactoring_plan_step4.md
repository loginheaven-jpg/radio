# Step 4: 프론트엔드 모듈 분리(ES Module) 리팩토링 계획

## 1. 현재 구조의 문제점 (Analysis)
예봄라디오 클라이언트는 현재 **6,000줄 규모의 초거대 단일 파일(`index.html`)**로 구성되어 있습니다.

* **관심사 혼재 (Separation of Concerns 위반):** HTML 구조 렌더링(400줄), CSS 인라인 스타일 및 커스텀 클래스(600줄), JavaScript 비즈니스 로직(5,000줄)이 모두 동일한 파일에 한 덩어리로 존재합니다.
* **유지보수 마비 현상:** "라디오 재생 버튼 디자인을 수정"하려면 플레이어의 AudioContext 로직과 얽힌 몇 천 번째 줄의 코드를 뒤져야 합니다. 한 군데의 오타가 전체 서비스 셧다운을 유발할 수 있습니다.
* **스코프 오염 위험성:** 글로벌 단위 스코프이기 때문에 변수 공유가 쉽다는 초기 장점은 있으나, 크기가 팽창하면 변수 이름 충돌이나 우발적 재할당의 위험성이 극에 달합니다.

## 2. 해결 및 설계 계획 (Design)
웹 빌드 환경(Webpack, Vite)을 무리하게 세팅하여 개발 환경을 복잡하게 만드는 대신, **브라우저에 내장된 순수 ES6 Modules(`type="module"`) 기능**을 사용하여 JS 파일과 CSS 파일을 합리적으로 나누어 설계합니다.

### 목표 파일 및 디렉토리 아키텍처
```text
yebomradio/
 ├── index.html            => (단순 HTML 껍데기와 id 정의용 뼈대)
 ├── css/
 │   ├── main.css          => (전체 레이아웃 및 컴포넌트 스타일링)
 │   └── animations.css    => (등잔, 디스크 등 시각적 애니메이션 CSS)
 └── js/
     ├── main.js           => (<script type="module">의 진입점. 이벤트 바인딩)
     ├── player/
     │   ├── audio-core.js => (AudioContext 초기화, 무음 앵커 세팅 등 하부단)
     │   ├── howler-manager.js => (Howler 라이브러리 컨트롤)
     │   └── hls-manager.js=> (HLS 스트리밍 컨트롤)
     ├── api/
     │   └── client.js     => (공통 Fetch 로직, Worker 통신 추상화)
     └── ui/
         ├── track-list.js => (채널 리스트 렌더링, 검색 하이라이트)
         ├── guestbook.js  => (40주년 방명록 및 알럿 처리)
         └── admin.js      => (데이터 업로드 드래그 앤 드롭 로직)
```

## 3. 세부 실행 계획 및 전환 전략 (Roadmap)
단일 파일에서 파일을 찢어내는(Extract) 작업은 필연적으로 **Scope Reference Error(정의되지 않은 함수 호출)**를 낳습니다. 철저히 단계적으로 분할해야 합니다.

1. **CSS 외부 독립화 (Phase 1):** 가장 부작용이 없는 `<style>` 블록 600줄을 `style.css`로 빼내고 `<link>` 태그로 로드합니다.
2. **독립적인 의존성 유틸 분리 (Phase 2):** `escHtml()`, `formatTime()`, `formatNumber()` 같은, 다른 변수에 의존하지 않는 순수 헬퍼 함수 그룹을 `utils.js`로 분리하고 `export`/`import` 합니다.
3. **네트워크 및 API 계층 분리 (Phase 3):** 라디오 서버와 통신하는 순수 통신부들을 `api.js`로 분리하여 내보냅니다.
4. **UI와 플레이어 핵심 코어 분할 (Phase 4):** 가장 얽혀있는 재생 로직 그룹을 `player.js`로, DOM 조작 로직을 `ui.js`로 갈라내는 메인 수술 작업을 진행합니다. 브라우저 개발자 도구를 통한 사이드 이펙트 전수 검사가 필요합니다.

**기대 효과:** 코드가 300~500줄 단위의 모듈별로 명확히 분리되며, `index.html`은 HTML 캐싱 효율을 극대화하고, 이후 복수의 개발자가 투입되더라도 Git Conflict 발생을 최소화할 수 있습니다.
