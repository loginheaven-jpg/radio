# Step 3: 백엔드 워커(worker.js) 라우팅 패턴 추상화 및 리팩토링 계획

## 1. 현재 구조의 문제점 (Analysis)
현재 라디오 서버 역할을 하는 Cloudflare Worker 코드(`worker.js`)는 약 1,800줄의 방대한 코드로 구성되어 있습니다.
가장 큰 문제점은 최상단의 `fetch(request)` 이벤트 핸들러 내부에 끝없는 `if ... else if` 형태의 체인망이 구축되어 있다는 것입니다.

* **라우팅 지옥 (Routing Hell):** `/api/login`, `/api/track`, `/api/save`, `/api/upload` 등 기능이 추가될 때마다 체인이 무한정 길어져 가독성이 극도로 떨어집니다. 한 엔드포인트 수정 시 전체 흐름을 확인해야 합니다.
* **로직 중복 (DRY 원칙 위배):** 모든 분기문마다 CORS 응답 헤더 생성, `OPTIONS` 메서드(Preflight) 처리, 인증(`Bearer adminKey`) 처리 로직이 반복적으로 등장합니다.
* **에러 제어의 개별화:** 통일된 전역 에러 핸들링 존이 부족하여, 특정 API가 뻗으면 전체 워커가 다운되거나 올바르지 않은 상태 코드로 응답될 위험이 큽니다.

## 2. 해결 및 설계 계획 (Design)
Cloudflare Worker 환경의 특성(엣지 컴퓨팅)을 살리면서, 기존 클라이언트(`index.html`)와의 호환성을 100% 보장하는 **가벼운(Lightweight) 라우터 패턴**을 도입합니다. 무거운 프레임워크가 아닌 `itty-router`나 순수 Vanilla JS 기반의 미들웨어 객체 구조를 목표로 합니다.

### 목표 아키텍처
```javascript
// [제안] 미들웨어 라우팅 구조 구현 예시
import { Router } from 'itty-router';

const router = Router();

// 1. 공통 미들웨어 부착 (CORS 및 인증)
const withCors = (request) => { /* CORS 로직 */ };
const requireAdmin = (request) => { /* Authorization 헤더 파싱 및 검증 */ };

router.all('*', withCors);

// 2. 인증이 필요 없는 PUBLIC API
router.get('/api/kbs', handleKbsStream);
router.post('/api/login', handleSSOLogin);
router.get('/api/anniversary/messages', fetchGuestbookMessages);

// 3. 인증이 필요한 ADMIN API (미들웨어 연계)
router.post('/api/upload', requireAdmin, handleTrackUpload);
router.post('/api/live/chunk', requireAdmin, handleLiveChunkUpload);

// 4. Default Fallback
router.all('*', () => new Response('Not Found', { status: 404 }));

export default {
  fetch: router.handle
};
```

## 3. 세부 실행 계획 및 전환 전략 (Roadmap)
이 작업은 프론트엔드의 화면에 일절 영향을 주지 않는 백엔드 전용 격리 작업이므로 안정성이 높습니다.
1. **설계 (Phase 1):** 별도의 라우팅 유틸리티 클래스(또는 `itty-router` 라이브러리)를 워커 파일 상단에 정의합니다.
2. **미들웨어 분리 (Phase 2):** 기존 중복 사용되던 CORS 응답 헤더(`Access-Control-Allow-Origin: *` 등)와 검증 함수(`checkAdmin`)를 미들웨어 체인으로 분리합니다.
3. **점진적 이전 (Phase 3):** 가장 의존성이 낮은 Public API(예: `/api/kbs`, `/api/stats`)들을 먼저 새 라우터 체인으로 이동하여 테스트합니다.
4. **전면 이전 (Phase 4):** Live HLS 청크 파싱 등 가장 무거운 핵심 로직들을 독립된 함수(`handleLiveChunkUpload`) 파트 기법으로 캡슐화시켜 이동시킵니다. 기존 `fetch` 체인을 삭제합니다.

**기대 효과:** `worker.js`의 파일 크기를 줄이기 힘들다 하더라도 코드의 가독성이 월등히 높아지며, 향후 새로운 라디오 채널 등 신규 API나 보안 기능을 추가할 때 매우 빠르게 대응할 수 있습니다.
