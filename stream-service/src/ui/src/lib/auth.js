// 비밀번호 잠금 확인용 API 호출.
// 잠금은 백엔드(Flask)가 세션 쿠키로 강제한다. 프론트는 처음 접속했을 때
// 잠겼는지만 물어보고, 잠겨 있으면 비밀번호를 한 번 입력받아 세션 쿠키를 받는다.
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

export async function login(password) {
  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    const data = await response.json().catch(() => ({}));
    return {
      ok: response.ok,
      error: data.error || null,
      retryAfter: data.retry_after || 0,
    };
  } catch {
    return { ok: false, error: 'network_error', retryAfter: 0 };
  }
}