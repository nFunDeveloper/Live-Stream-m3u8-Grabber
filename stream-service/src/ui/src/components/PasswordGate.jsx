import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@heroui/react';
import { Lock, Loader2 } from 'lucide-react';
import { checkSession, fetchChallenge, login } from '../lib/auth.js';
import { LOCK_EVENT } from '../lib/lock.js';
import PinInput, { PIN_LENGTH } from './PinInput.jsx';

const EMPTY = Array(PIN_LENGTH).fill('');
// 맞았을 때 체크 표시를 보여주고 잠금창이 물러나는 시간
const OPEN_BEAT_MS = 560;
// 앱 진입 애니메이션 길이
const APP_ENTER_MS = 600;
// 아무것도 하지 않으면 이 시간이 지나면 알아서 잠근다
const IDLE_MS = 60 * 60 * 1000;

// 처음 접속했을 때 가운데 인증번호를 묻는다.
// 통과하면 그 세션 쿠키 덕분에 새로고침해도 다시 묻지 않는다.
export default function PasswordGate({ children }) {
  const [status, setStatus] = useState('checking'); // checking | locked | unlocked
  const [opening, setOpening] = useState(false); // 잠금창이 사라지는 중
  // 앱을 내렸다 올리지 않기 위해, 한 번 열린 뒤로는 마운트를 유지한다.
  const [appMounted, setAppMounted] = useState(false);
  const [enterOnMount, setEnterOnMount] = useState(true);
  const [boxes, setBoxes] = useState(EMPTY);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const nonceRef = useRef(null);
  const formRef = useRef(null);
  const openTimerRef = useRef(null);

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
      if (result.ok && !result.enabled) {
        setAppMounted(true);
        return setStatus('unlocked');
      }
      if (result.ok && result.authed) {
        setAppMounted(true);
        return setStatus('unlocked');
      }
      await refreshNonce();
      if (!cancelled) setStatus('locked');
    })();
    return () => {
      cancelled = true;
      clearTimeout(openTimerRef.current);
    };
  }, [refreshNonce]);

  // 앱 진입 애니메이션은 처음 떼는 때에만. 다시 잠갔다 풀릴 때는 앱이 그대로
  // 살아 있었으므로 재촉하지 않는다.
  useEffect(() => {
    if (!appMounted) return undefined;
    const timer = setTimeout(() => setEnterOnMount(false), APP_ENTER_MS);
    return () => clearTimeout(timer);
  }, [appMounted]);

  // 틀렸을 때 창을 한 번 흔든다. 오류 문구 자체에 이미 fade-in 이 있으니 겹치지 않게 한다.
  useEffect(() => {
    if (!error) return;
    formRef.current?.animate?.(
      [
        { transform: 'translateX(0)' },
        { transform: 'translateX(-6px)' },
        { transform: 'translateX(5px)' },
        { transform: 'translateX(-4px)' },
        { transform: 'translateX(3px)' },
        { transform: 'translateX(0)' },
      ],
      { duration: 380, easing: 'ease-in-out' }
    );
  }, [error]);

// 잠근다. 서버의 세션까지 지워야 새로고침해도 잠금이 유지된다.
  // 앱은 그대로 두고 잠금창만 덮어 올린다.
  const performLock = useCallback(async () => {
    clearTimeout(openTimerRef.current);
    setOpening(false);
    try {
      await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
    } catch {
      // 서버에 닿지 못해도 화면은 잠근다
    }
    setBoxes(EMPTY);
    setError('');
    setNotice('');
    setBusy(false);
    setStatus('locked');
    await refreshNonce();
  }, [refreshNonce]);

  // 헤더의 잠금 버튼이 보내는 신호를 받는다
  useEffect(() => {
    window.addEventListener(LOCK_EVENT, performLock);
    return () => window.removeEventListener(LOCK_EVENT, performLock);
  }, [performLock]);

  // 1시간 동안 아무것도 안 하면 알아서 잠근다. 화면은 그대로 두고 잠금창만 다시 띄운다.
  useEffect(() => {
    if (status !== 'unlocked') return undefined;
    let timer;
    const arm = () => {
      clearTimeout(timer);
      timer = setTimeout(performLock, IDLE_MS);
    };
    // 마우스 움직임까지 반응을 볼 필요는 없다. 실제 조작만 센다.
    const events = ['pointerdown', 'keydown', 'wheel', 'touchstart', 'visibilitychange'];
    events.forEach((name) => window.addEventListener(name, arm, { passive: true }));
    arm();
    return () => {
      clearTimeout(timer);
      events.forEach((name) => window.removeEventListener(name, arm));
    };
  }, [status, performLock]);

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
        // 맞았다는 표시를 잠깐 보여준 뒤 잠금창을 내보내고 앱을 드러낸다.
        setAppMounted(true);
        setStatus('unlocked');
        setOpening(true);
        openTimerRef.current = setTimeout(() => setOpening(false), OPEN_BEAT_MS);
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

  // 잠금창이 보이는 동안 앱은 DOM 에 그대로 살아 있다. 자동 잠금 뒤 다시 인증하면
  // 재생 중인 영상과 멀티뷰, 입력해 둔 주소가 그대로 유지된다.
  const gateVisible = status === 'locked' || opening;

  return (
    <>
      {appMounted && (
        <div className={enterOnMount ? 'app-enter' : ''} inert={status === 'locked' || undefined}>
          {children}
        </div>
      )}

      {gateVisible && (
        <div
          className={`gate-cover fixed inset-0 z-50 overflow-y-auto bg-[#050505] px-4 py-10 flex items-center justify-center ${
            opening ? 'gate-cover-out' : ''
          }`}
        >
          <div className="dot-grid" />
          <form
            ref={formRef}
            onSubmit={(e) => {
              e.preventDefault();
              if (boxes.every((box) => box !== '')) onComplete(boxes.join(''));
            }}
            className="gate-card relative z-10 w-full max-w-sm rounded-2xl border border-white/10 bg-[#0A0A0C]/80 backdrop-blur-xl p-8 shadow-2xl shadow-black/50"
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
          opened={opening}
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
      )}
    </>
  );
}