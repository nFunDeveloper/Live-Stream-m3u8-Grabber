const HISTORY_KEY = 'm3u8-grabber:history';
const GROUPS_KEY = 'm3u8-grabber:groups';
const HISTORY_LIMIT = 50;

function readJson(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // 저장 실패(비공개 모드 등) 시 조용히 무시 — 서비스 동작에는 지장 없음
  }
}

export function entryKey(platform, streamerId) {
  return `${platform}:${streamerId}`;
}

export function loadHistory() {
  const entries = readJson(HISTORY_KEY, []);
  return Array.isArray(entries) ? entries : [];
}

export function recordHistory(result, url) {
  const key = entryKey(result.platform, result.streamer_id);
  const rest = loadHistory().filter((entry) => entry.key !== key);
  const entry = {
    key,
    platform: result.platform,
    streamer_id: result.streamer_id,
    streamer_name: result.streamer_name || '',
    title: result.title || '',
    category: result.category || '',
    thumbnail: result.thumbnail || '',
    url: url || '',
    m3u8: result.m3u8_url || '',
    quality: result.quality || '',
    searchedAt: Date.now(),
  };
  const history = [entry, ...rest].slice(0, HISTORY_LIMIT);
  writeJson(HISTORY_KEY, history);
  return history;
}

export function removeHistory(key) {
  const history = loadHistory().filter((entry) => entry.key !== key);
  writeJson(HISTORY_KEY, history);
  return history;
}

export function clearHistory() {
  writeJson(HISTORY_KEY, []);
  return [];
}

export function loadGroups() {
  const groups = readJson(GROUPS_KEY, []);
  return Array.isArray(groups) ? groups : [];
}

export function saveGroups(groups) {
  writeJson(GROUPS_KEY, groups);
  return groups;
}

export function buildGroupMember(result) {
  return {
    key: entryKey(result.platform, result.streamer_id),
    platform: result.platform,
    streamer_id: result.streamer_id,
    streamer_name: result.streamer_name || '',
    title: result.title || '',
    url: result.url || '',
    m3u8: result.m3u8 || result.m3u8_url || '',
    quality: result.quality || '',
  };
}
