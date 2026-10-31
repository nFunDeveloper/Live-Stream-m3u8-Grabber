import { useEffect, useRef, useState } from 'react';
import { Button, Spinner } from '@heroui/react';
import { RefreshCw } from 'lucide-react';
import { agentFetch } from './agent.js';

const LOG_POLL_MS = 5000;
const LIMIT = 120;

// 선택한 세션(또는 전체)의 로그 tail을 주기적으로 받아 보여준다.
export default function LogPanel({ sessions, className = '' }) {
  const [sessionId, setSessionId] = useState(''); // '' = 전체
  const [lines, setLines] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const preRef = useRef(null);

  // 세션 목록이 바뀌면 선택이 사라진 세션에서 빠져나온다
  useEffect(() => {
    if (sessionId && !sessions.some((s) => s.id === sessionId)) {
      setSessionId('');
    }
  }, [sessions, sessionId]);

  useEffect(() => {
    let cancelled = false;
    let timer = null;
    const poll = async (initial = false) => {
      if (initial) setLoading(true);
      try {
        const query = `limit=${LIMIT}${sessionId ? `&session_id=${encodeURIComponent(sessionId)}` : ''}`;
        const data = await agentFetch(`/agent/logs?${query}`, { timeout: 4000 });
        if (cancelled) return;
        setLines(data.lines || []);
        setError('');
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled && initial) setLoading(false);
      }
    };
    poll(true);
    timer = setInterval(() => poll(), LOG_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [sessionId]);

  return (
    <section className={`glass-panel rounded-2xl p-4 flex flex-col gap-3 ${className}`}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-bold text-white">로그</h2>
        <div className="flex items-center gap-2">
          <select
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
            className="h-7 rounded-lg bg-white/[0.05] border border-white/10 text-[11px] text-zinc-300 px-2 outline-none focus:border-white/25"
          >
            <option value="">전체 세션</option>
            {sessions.map((session) => (
              <option key={session.id} value={session.id}>
                {session.label || session.id} :{session.port}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            isDisabled={loading}
            onPress={() => {
              // 버튼 클릭 시 즉시 한 번 더 받는다
              const query = `limit=${LIMIT}${sessionId ? `&session_id=${encodeURIComponent(sessionId)}` : ''}`;
              agentFetch(`/agent/logs?${query}`, { timeout: 4000 })
                .then((data) => {
                  setLines(data.lines || []);
                  setError('');
                })
                .catch((err) => setError(err.message));
            }}
            className="h-7 w-7 min-w-0 rounded-lg bg-white/5 text-zinc-300 p-0"
            title="지금 새로고침"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      {error && (
        <p className="text-[11px] text-red-400/90 bg-red-500/5 border border-red-500/20 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      <div
        ref={preRef}
        className="h-36 overflow-y-auto rounded-xl border border-white/10 bg-black/40 px-3 py-2 font-mono text-[10px] leading-relaxed text-zinc-400"
      >
        {loading ? (
          <div className="h-full flex items-center justify-center">
            <Spinner size="sm" color="white" />
          </div>
        ) : lines.length === 0 ? (
          <div className="h-full flex items-center justify-center text-zinc-600">
            로그가 없습니다
          </div>
        ) : (
          lines.map((line, index) => (
            <div key={index} className="whitespace-pre-wrap break-all hover:bg-white/[0.03]">
              {line}
            </div>
          ))
        )}
      </div>
    </section>
  );
}
