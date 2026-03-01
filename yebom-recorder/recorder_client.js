/**
 * AudioRecorderClient
 * ===================
 * 웹앱에서 Audio Recorder Server를 제어하기 위한 클라이언트 모듈.
 *
 * 사용법:
 *   import { AudioRecorderClient } from './recorder_client.js';
 *   const recorder = new AudioRecorderClient('http://localhost:8090');
 *
 *   await recorder.start('both');     // 마이크+시스템 동시 녹음
 *   const result = await recorder.stop();  // { file, duration, size_kb }
 *   const status = await recorder.status(); // { recording, source, elapsed }
 */

export class AudioRecorderClient {
  constructor(baseUrl = 'http://localhost:8090') {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
  }

  /**
   * 녹음 시작
   * @param {'mic'|'system'|'both'} source - 입력 소스
   * @param {string|null} filename - 저장 파일명 (확장자 제외). null이면 자동 생성.
   * @param {object} options - 추가 옵션
   * @param {'manual'|'auto'} options.mode - 녹음 모드. auto=무음 자동 분할 (기본 manual)
   * @param {number} options.silence_threshold - 무음 기준 RMS (기본 50)
   * @param {number} options.silence_duration - 무음 판정 시간 초 (기본 1.0)
   * @returns {Promise<{recording: boolean, source: string, mode: string}>}
   */
  async start(source = 'mic', filename = null, options = {}) {
    const body = { source };
    if (filename) body.filename = filename;
    if (options.mode) body.mode = options.mode;
    if (options.silence_threshold != null) body.silence_threshold = options.silence_threshold;
    if (options.silence_duration != null) body.silence_duration = options.silence_duration;
    const res = await fetch(`${this.baseUrl}/record/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || `녹음 시작 실패 (${res.status})`);
    }
    return res.json();
  }

  /**
   * 녹음 중지 → MP3 저장
   * @returns {Promise<{file: string, files: string[], duration: number, size_kb: number}>}
   */
  async stop() {
    const res = await fetch(`${this.baseUrl}/record/stop`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || `녹음 중지 실패 (${res.status})`);
    }
    return res.json();
  }

  /**
   * 현재 상태 조회
   * @returns {Promise<{recording: boolean, source: string|null, elapsed: number|null}>}
   */
  async status() {
    const res = await fetch(`${this.baseUrl}/record/status`);
    return res.json();
  }

  /**
   * 서버 헬스체크
   * @returns {Promise<{status: string, mic: boolean, loopback: boolean}>}
   */
  async health() {
    const res = await fetch(`${this.baseUrl}/health`);
    return res.json();
  }

  /**
   * 오디오 디바이스 목록
   * @returns {Promise<Array>}
   */
  async devices() {
    const res = await fetch(`${this.baseUrl}/devices`);
    return res.json();
  }

  /**
   * MP3 파일 다운로드 URL 생성
   * @param {string} filename - 파일명 (예: rec_20260227_143022_mic.mp3)
   * @returns {string}
   */
  downloadUrl(filename) {
    return `${this.baseUrl}/download/${encodeURIComponent(filename)}`;
  }
}
