import { useCallback, useEffect, useState } from 'react';
import { Alert, Button } from '@heroui/react';
import { Loader2, MonitorSmartphone, Plug, RefreshCw, X } from 'lucide-react';
import { agentFetch, AGENT_API_VERSION, AGENT_BASE } from './agent.js';
import RemoteDashboard from './RemoteDashboard.jsx';

// 원격 제어 드로어의 컨테이너. 로컬 에이전트 연결을 먼저 확보하고,
// 연결되면 제어 패널을, 실패하면 트러블슈팅 화면을 보여준다.
// 메인 페이지 오른쪽에서 슬라이드로 나오는 패널 전용 — 페이지 전체 렌더는 App이 한다.
export default function RemoteApp({ onClose }) {
  const [phase, setPhase] = useState('connecting'); // connecting | connected | unreachable
  const [agentInfo, setAgentInfo] = useState(null);
  const [failure, setFailure] = useState('');

  const connect = useCallback(async () => {
    setPhase('connecting');
    try {
      const info = await agentFetch('/agent/info', { timeout: 4000 });
      if (info.api_version !== AGENT_API_VERSION) {
        setFailure(
          `에이전트 버전(${info.api_version})이 이 페이지(v${AGENT_API_VERSION})와 호환되지 않습니다`
        );
        setPhase('unreachable');
        return;
      }
      setAgentInfo(info);
      setFailure('');
      setPhase('connected');
    } catch (err) {
      setFailure(err.message);
      setPhase('unreachable');
    }
  }, []);

  useEffect(() => {
    connect();
  }, [connect]);

  // 연결 안 됨 상태에선 5초마다 자동 재시도한다 — 로컬 프로그램을 띄우면 알아난다
  useEffect(() => {
    if (phase !== 'unreachable') return undefined;
    const timer = setTimeout(connect, 5000);
    return () => clearTimeout(timer);
  }, [phase, connect]);

  if (phase === 'connected' && agentInfo) {
    return <RemoteDashboard agentInfo={agentInfo} onClose={onClose} />;
  }

  const connecting = phase === 'connecting';

  return (
    <div className="flex-1 min-h-0 overflow-y-auto flex items-center justify-center p-5">
      <div className="w-full max-w-sm glass-panel rounded-2xl p-5 flex flex-col items-center gap-4 text-center relative">
        <button
          type="button"
          onClick={onClose}
          aria-label="원격 제어 닫기"
          className="absolute top-3 right-3 w-7 h-7 rounded-lg border border-white/10 bg-white/[0.04] flex items-center justify-center text-zinc-400 hover:text-white hover:bg-white/10 transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>

        <div className="w-12 h-12 rounded-2xl bg-white/[0.04] border border-white/10 flex items-center justify-center">
          {connecting ? (
            <Loader2 className="w-5 h-5 text-zinc-300 animate-spin" />
          ) : (
            <Plug className="w-5 h-5 text-red-400" />
          )}
        </div>
        <div>
          <h2 className="text-sm font-bold text-white flex items-center justify-center gap-2">
            <MonitorSmartphone className="w-4 h-4 text-zinc-400" />
            로컬 릴레이 서버 연결
          </h2>
          <p className="text-xs text-zinc-400 mt-1.5 leading-relaxed">
            {connecting
              ? '로컬 릴레이 서버에 연결하는 중…'
              : '로컬 릴레이 서버에 연결할 수 없습니다'}
          </p>
          <p className="text-[10px] text-zinc-600 mt-1 font-mono">{AGENT_BASE}</p>
        </div>

        {!connecting && failure && (
          <Alert
            color="danger"
            title="연결 실패"
            description={failure}
            variant="flat"
            className="w-full rounded-lg border-red-500/20 bg-red-500/5 text-red-400 py-2 text-left"
          />
        )}

        {!connecting && (
          <div className="w-full text-left space-y-1 text-[10px] text-zinc-500 leading-relaxed">
            <p>• 로컬 릴레이 프로그램이 실행 중인지 확인해주세요</p>
            <p>• 에이전트는 127.0.0.1:17300 에서 대기해야 합니다</p>
            <p>• 브라우저가 로컬(http) 요청을 막고 있을 수 있습니다 — Chrome 최신 버전</p>
            <p>• 5초마다 자동으로 다시 시도합니다</p>
          </div>
        )}

        <Button
          size="sm"
          isDisabled={connecting}
          onPress={connect}
          className="w-full rounded-lg bg-white text-black font-semibold text-xs"
        >
          <RefreshCw className={`w-3 h-3 mr-1 ${connecting ? 'animate-spin' : ''}`} />
          다시 연결
        </Button>
      </div>
    </div>
  );
}
