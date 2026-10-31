// 로컬 에이전트(사용자 PC)와의 통신 허브. 규격은 docs/remote-agent-contract.md 참고.
export const AGENT_BASE = 'http://127.0.0.1:17300';
export const AGENT_API_VERSION = 1;

export class AgentError extends Error {
  constructor(message) {
    super(message);
    this.name = 'AgentError';
  }
}

// fetch 하나에 타임아웃을 걸고, 네트워크 실패/HTTP 에러를 모두 AgentError로 통일한다.
export async function agentFetch(path, { method = 'GET', body, timeout = 5000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(`${AGENT_BASE}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    let data = null;
    try {
      data = await response.json();
    } catch {
      // JSON이 아니어도 HTTP 상태로만 판단한다
    }
    if (!response.ok) {
      throw new AgentError(data?.error || `에이전트 응답 오류 (HTTP ${response.status})`);
    }
    return data;
  } catch (err) {
    if (err instanceof AgentError) throw err;
    if (err.name === 'AbortError') {
      throw new AgentError('로컬 서버 응답 시간이 초과되었습니다');
    }
    throw new AgentError('로컬 서버(127.0.0.1:17300)에 연결할 수 없습니다');
  } finally {
    clearTimeout(timer);
  }
}
