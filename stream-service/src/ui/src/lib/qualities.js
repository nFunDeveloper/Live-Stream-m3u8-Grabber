// 해상도 지원 범위는 각 플랫폼 API를 직접 조회해 확인한 값이다.
// - chzzk: live-detail의 livePlaybackJson.media[].encodingTrack에서 트랙 id를 읽는다.
//   실측 5개 방송 모두 ['144p','360p','480p','720p','1080p'] + audioOnly 동일.
// - cime/pandalive/popkon: master 플레이리스트의 RESOLUTION에서 variant를 고른다.
//   실측 최댓값이 1920x1010이라 1080p는 정확히 매칭되지 않아 ABR로 폴백한다.
// - soop: broad_stream_assign의 broad_key에 quality를 넣지만 SOOP가 이를 무시한다.
//   실측 master variant가 960x540/640x360뿐이라 720p/1080p는 물리적으로 불가능하다.
export const QUALITY_OPTIONS = [
  { key: 'auto', label: 'Auto (자동)' },
  { key: '1080p', label: '1080p (FHD)' },
  { key: '720p', label: '720p (HD)' },
  { key: '540p', label: '540p (SD)' },
  { key: '480p', label: '480p (SD)' },
  { key: '360p', label: '360p (SD)' },
  { key: '144p', label: '144p (Low)' },
];

// 플랫폼이 실제로 내려주는 해상도. 여기에 없는 옵션은 UI에서 비활성화된다.
const PLATFORM_QUALITIES = {
  chzzk: ['auto', '1080p', '720p', '540p', '480p', '360p', '144p'],
  cime: ['auto', '720p', '540p', '480p', '360p'],
  pandalive: ['auto', '720p', '540p', '480p', '360p'],
  popkon: ['auto', '720p', '540p', '480p', '360p'],
  soop: ['auto', '540p', '480p', '360p'],
};

// 백엔드 app.py의 auto_parsing_db와 동일한 도메인 매핑
const HOST_PLATFORM = {
  'chzzk.naver.com': 'chzzk',
  'm.chzzk.naver.com': 'chzzk',
  'ci.me': 'cime',
  'www.pandalive.co.kr': 'pandalive',
  'm.pandalive.co.kr': 'pandalive',
  'pandalive.co.kr': 'pandalive',
  'www.popkontv.com': 'popkon',
  'm.popkontv.com': 'popkon',
  'popkontv.com': 'popkon',
  'play.sooplive.com': 'soop',
  'play.sooplive.co.kr': 'soop',
};

export function detectPlatform(url) {
  const value = (url || '').trim();
  if (!value) return null;
  let hostname;
  try {
    hostname = new URL(value).hostname.toLowerCase();
  } catch {
    return null;
  }
  return HOST_PLATFORM[hostname] || null;
}

export function supportedQualities(platform) {
  if (!platform) return QUALITY_OPTIONS.map((item) => item.key);
  const allowed = PLATFORM_QUALITIES[platform];
  if (!allowed) return QUALITY_OPTIONS.map((item) => item.key);
  return allowed;
}

// 현재 선택된 해상도가 플랫폼에서 지원되지 않으면 auto로 되돌린다.
export function resolveQuality(quality, platform) {
  const supported = supportedQualities(platform);
  return supported.includes(quality) ? quality : 'auto';
}