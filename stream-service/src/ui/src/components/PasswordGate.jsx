import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@heroui/react';
import { Lock, Loader2 } from 'lucide-react';
import { checkSession, fetchChallenge, login } from '../lib/auth.js';
import PinInput, { PIN_LENGTH } from './PinInput.jsx';

const EMPTY = Array(PIN_LENGTH).fill('');

// 처음 접속했을 때 가운데 인증번호를 묻는다.
// 통과하면 그 세션 쿠키 덕분에 새로고침해도 다시 묻지 않는다.
export default function PasswordGate({ children }) {
  const [status, setStatus] = useState('checking'); // checking | locked | unlocked
  const [boxes, setBoxes] = useState(EMPTY);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const nonceRef = useRef(null);

  // 잠금 상태일 때 쓸 일회용 값을 미리 받는다. 한 번 쓰면 다시 못 쓰므로
  // 시도할 때마다 새로 받아야 한다.
  const refreshNonce = useCallback(async () => {
    try {
      nonceRef.current = await fetchChallenge();
    } catch {
      nonceRef.current = null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const result = await checkSession();
      if (cancelled) return;
      // 잠금을 쓰지 않는 배포(APP_PASSWORD 미설정)면 곧바로 앱을 띄운다.
      if (result.ok && !result.enabled) return setStatus('unlocked');
      if (result.ok && result.authed) return setStatus('unlocked');
      await refreshNonce();
      if (!cancelled) setStatus('locked');
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshNonce]);

  const onComplete = useCallback(
    async (pin) => {
      if (busy) return;
      // 회선을 지나는 값은 인증번호가 아니라 이 해시뿐이다.
      if (!nonceRef.current) await refreshNonce();
      const nonce = nonceRef.current;
      if (!nonce) {
        setError('서버에 연결하지 못했습니다. 잠시 뒤 다시 시도해주세요.');
        return;
      }

      setBusy(true);
      setError('');
      setNotice('');
      const result = await login(pin, nonce);
      nonceRef.current = null;
      setBusy(false);

      if (result.ok) {
        setError('');
        setNotice('');
        setStatus('unlocked');
        return;
      }

      // 틀렸다는 사실만 알려주고 다시 입력받는다.
      setBoxes(EMPTY);
      if (result.error === 'too_many_attempts') {
        const minutes = result.lockoutMinutes || 10;
        const left =
          result.retryAfter / 3600 >= 1
            ? `${Math.ceil(result.retryAfter / 3600)}시간`
            : `${Math.ceil(result.retryAfter / 60)}분`;
        setError(`로그인 시도가 너무 많아 ${minutes}분 동안 잠겼습니다. 약 ${left} 후 다시 시도해주세요.`);
        setNotice('반복해서 틀릴수록 대기 시간이 계속 길어집니다.');
        return;
      }
      if (result.error === 'stale_nonce') {
        // 세션이 오래 걸리거나 탭을 오래 열어둔 경우. 조용히 새 값을 받는다.
        await refreshNonce();
        setError('입력 시간이 지났습니다. 다시 시도해주세요.');
        return;
      }
      if (result.error === 'network_error') {
        setError('서버에 연결하지 못했습니다. 잠시 뒤 다시 시도해주세요.');
        return;
      }

      const left = result.attemptsLeft;
      setError(
        left === null || left === undefined
          ? '인증번호가 맞지 않습니다.'
          : `인증번호가 맞지 않습니다. ${left}회 더 틀리면 잠깁니다.`
      );
      await refreshNonce();
    },
    [busy, refreshNonce]
  );

  if (status === 'checking') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#050505]">
        <Loader2 className="w-5 h-5 text-zinc-500 animate-spin" />
      </div>
    );
  }

  if (status === 'unlocked') return children;

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#050505] px-4 relative overflow-hidden">
      <div className="dot-grid" />
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (boxes.every((box) => box !== '')) onComplete(boxes.join(''));
        }}
        className="relative z-10 w-full max-w-sm rounded-2xl border border-white/10 bg-[#0A0A0C]/80 backdrop-blur-xl p-8 shadow-2xl shadow-black/50"
      >
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-xl bg-white/[0.04] border border-white/10 flex items-center justify-center">
            <Lock className="w-4 h-4 text-zinc-300" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white">승인된 관계자만 사용할 수 있습니다</h1>
            <p className="text-[11px] text-zinc-500 mt-0.5">접근 권한 확인</p>
          </div>
        </div>

        <p className="text-xs text-zinc-400 leading-relaxed mb-6">
          이 앱은 승인된 관계자 전용입니다. 인증번호 {PIN_LENGTH}자리를 확인한 뒤에만 아래 화면이
          열리고, 확인된 동안은 그대로 유지됩니다.
        </p>

        <PinInput
          boxes={boxes}
          onBoxesChange={setBoxes}
          disabled={busy}
          onComplete={onComplete}
        />

        {error && (
          <p role="alert" className="text-xs text-red-400 mt-4 text-center animate-fade-in">
            {error}
          </p>
        )}
        {notice && <p className="text-[11px] text-zinc-500 mt-2 text-center animate-fade-in">{notice}</p>}

        <Button
          type="submit"
          isLoading={busy}
          isDisabled={!boxes.every((box) => box !== '')}
          onPress={() => {
            // 네 칸이 차면 이미 자동 전송되지만, Enter 를 누른 경우에도 같게 처리한다.
            if (boxes.every((box) => box !== '')) onComplete(boxes.join(''));
          }}
          className="w-full h-10 rounded-lg bg-white hover:bg-zinc-200 text-black font-semibold text-sm shadow-lg shadow-white/10 transition-all mt-5"
        >
          {busy ? '확인 중' : '확인'}
        </Button>
      </form>
    </div>
  );
}