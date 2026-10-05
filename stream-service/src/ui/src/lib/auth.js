import { sha256Hex } from './sha256.js';

// 비밀번호 잠금 확인용 API 호출.
// 잠금은 백엔드(Flask)가 세션 쿠키로 강제한다. 프론트는 처음 접속했을 때
// 잠겼는지만 물어보고, 잠겨 있으면 비밀번호를 한 번 입력받아 세션 쿠키를 받는다.
//
// 비밀번호는 평문으로 보내지 않는다. 서버가 내준 일회용 nonce로 해시를 내고 그
// 값만 보낸다. 서버는nonce 를 바로 없애므로 같은 값을 다시 쓰면 들통나고,
// 회선에서 도청해도 비밀번호나 재사용 가능한 토큰을 얻을 수 없다.
export async function checkSession() {
  try {
    const response = await fetch('/api/auth/session', { credentials: 'same-origin' });
    if (!response.ok) return { ok: false };
    const data = await response.json();
    return { ok: true, authed: Boolean(data.authed), enabled: data.enabled !== false };
  } catch {
    // 백엔드에 닿지 못했으면 아무것도 못 하는 상황이므로 잠긴 것으로 본다.
    return { ok: false };
  }
}

export async function fetchChallenge() {
  const response = await fetch('/api/auth/challenge', { credentials: 'same-origin' });
  if (!response.ok) return null;
  const data = await response.json();
  return data.nonce || null;
}

export async function login(password, nonce) {
  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nonce, proof: sha256Hex(`${password}:${nonce}`) }),
    });
    const data = await response.json().catch(() => ({}));
    return {
      ok: response.ok,
      error: data.error || null,
      retryAfter: data.retry_after || 0,
      lockoutMinutes: data.lockout_minutes || 0,
      attemptsLeft: data.attempts_left ?? null,
    };
  } catch {
    return { ok: false, error: 'network_error', retryAfter: 0, lockoutMinutes: 0, attemptsLeft: null };
  }
}