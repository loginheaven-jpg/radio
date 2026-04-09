# Step 5: 전역 상태 관리(Global State Store) 도입 계획

## 1. 현재 구조의 문제점 (Analysis)
예봄라디오 클라이언트는 현재 **상태(Data)의 변경**과 **UI(DOM)의 렌더링**이 일대일(1:1)로 강하게 결합(Tight-Coupling)된 전형적인 스파게티 구조를 가지고 있습니다.

* **무분별한 전역 변수(Global Variable)의 파편화:**
  `isPlaying`, `currentChannel`, `liveMode`, `replayMode`, `currentHowl`, `audioCtx`, `liveSessionId` 등 상태를 나타내는 수십 개의 변수들이 최상단에 `let`으로 산재해 있습니다.
* **명령형(Imperative) DOM 제어의 한계:**
  상태가 바뀔 때마다 각 함수 구석구석에서 `document.getElementById('playBtn').innerHTML = ...`을 직접 제어하고 있습니다. 즉, A 기능을 추가하다 개발자가 깜박하고 DOM 업데이트 명령을 누락하면, 내부 프로그램은 정지해 있는데(정지 상태) 화면 버튼 플레이 상태는 그대로 돌아가는 '상태 역전 현상'의 발생지입니다.

## 2. 해결 및 설계 계획 (Design)
화면 구조 렌더링이 상태에 의존적으로 돌아가는 **반응형(Reactive) 아키텍처**를 구축합니다.
이를 위해 자바스크립트에 내장된 `Proxy` 객체를 무기로 삼은 **단일 중앙 집중형 Store 패턴**을 도입합니다. React나 Vue.js의 작동 원리를 도입하는 것과 동일한 효과를 발휘합니다.

### 목표 아키텍처 (Reactive State Store)
상태 데이터를 전파/구독(Sub/Pub) 형식으로 관리합니다.

```javascript
// 1. 단일 Store 객체 정의 및 Proxy화
const appState = new Proxy({
  playing: false,
  channel: 1,
  trackName: '연결 중...',
  liveMode: false
}, {
  // 상태 변경 감지 인터셉터
  set(target, prop, value) {
    if (target[prop] === value) return true; // 동일 시 무시
    target[prop] = value;
    // 상태가 변하면 해당 프로퍼티를 구독하는 이벤트 방출
    eventBus.emit(`store:${prop}`, value); 
    return true;
  }
});

// 2. UI 렌더링 로직의 분리 및 구독(Subscribe)
// 버튼 UI는 'appState.playing' 변경 이벤트에 반응하도록 등록
eventBus.on('store:playing', (isPlaying) => {
  const btn = document.getElementById('playBtn');
  btn.innerHTML = isPlaying ? '<정지 아이콘>' : '<재생 아이콘>';
  btn.classList.toggle('active', isPlaying);
});

// 3. 비즈니스 로직(Actions)에서는 값 대입만 수행
function togglePlayback() {
  // DOM 제어 명령은 모두 사라지고, 데이터(Store)만 조작!
  appState.playing = !appState.playing;
}
```

## 3. 세부 실행 계획 및 전환 전략 (Roadmap)
가장 위험하고 광범위한 Side Effect를 발생시킬 수 있으므로 마지막 단계(Step 5)에서 진행해야 하는 궁극의 리팩토링 단계입니다.

1. **상태 매핑 및 스키마 설계 (Phase 1):** 현재 흩어져있는 50여 개의 `let` 변수를 카테고리별(Player, Audio, UI, UserInfo) 객체 그룹으로 통합 매핑합니다.
2. **이벤트 버스(Pub/Sub Core) 개발 (Phase 2):** 의존성 라이브러리가 없도록 20줄 내외의 자체 `EventBus`를 만들어 Proxy Set Handler와 연결합니다.
3. **Reactive UI 리팩토링 (Phase 3):** 기존에 섞여 있던 DOM 제어 함수들(`updatePlayBtn`, `updateTrackListUI` 등)을 모두 지우거나 내부를 구독(Subscription) 모델로 재배치합니다.
4. **상태 관통 테스트 (Phase 4):** 사용자가 버튼을 누르는 대신 콘솔에서 직접 `appState.channel = 3`을 치더라도 화면의 모든 채널 UI와 음악이 올바르게 3채널 기준으로 동시에 돌아가는지 디버깅 검증을 진행합니다.

**기대 효과:** 비즈니스/음원 로직 파트(상태 데이터 변조)와 뷰 파트(DOM 반영)가 철저히 분리되어, 아무리 복잡한 상호작용과 기능(예: 플레이리스트 생성, EQ 조정)이 추가되더라도 데이터 결함이나 일관성이 깨지는 일이 완전히 사라집니다.
