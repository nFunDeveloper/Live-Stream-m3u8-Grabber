// SRT 슬롯 공용 규칙 — 슬롯 인덱스 i ↔ 포트 9001+i (계약 문서 v2 참조)
export const BASE_PORT = 9001;
export const MIN_SLOTS = 1;
export const MAX_SLOTS = 16;

export const newSlotId = () =>
  (window.crypto?.randomUUID?.() || `slot-${Date.now()}-${Math.random().toString(16).slice(2)}`);

// 슬롯 드롭이 받는 드래그 페이로드 키. 메인 사이드바(히스토리/멤버)가
// 싣는 'application/json'과 같은 키라 드래그가 그대로 이어진다.
export const HISTORY_DRAG_TYPE = 'application/json';

export function emptySlot() {
  return {
    id: newSlotId(),
    port: 0, // withPorts가 채운다
    page_url: '',
    m3u8_url: '',
    quality: 'auto',
    platform: '',
    streamer_name: '',
    title: '',
  };
}

// 포트 번호와 id를 인덱스 기준으로 재고정한다 — 사용자가 순서를 못 바꾸므로 인덱스가 곧 포트다
export function withPorts(slots) {
  return (slots || []).map((slot, index) => ({
    ...slot,
    id: slot.id || newSlotId(),
    port: BASE_PORT + index,
  }));
}

export function looksLikeM3u8(value) {
  return /\.m3u8(\?|$)/i.test(value) || /mpegurl/i.test(value);
}

// 방송 페이지 URL을 백엔드 /api/grab으로 m3u8로 변환한다(에이전트가 쓸 주소 확보)
export async function grabLive(pageUrl, quality = 'auto') {
  const response = await fetch(
    `/api/grab?url=${encodeURIComponent(pageUrl)}&quality=${quality}`
  );
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || '추출에 실패했습니다');
  return data;
}
