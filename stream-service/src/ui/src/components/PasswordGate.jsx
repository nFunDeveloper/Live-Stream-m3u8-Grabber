import { useEffect, useRef, useState } from 'react';
import { Button } from '@heroui/react';
import { Lock, Loader2, Eye, EyeOff } from 'lucide-react';
import { checkSession, login } from '../lib/auth.js';

// 처음 접속했을 때 가운데에 비밀번호를 묻는다.
// 통과하면 그 세션 쿠키 덕분에 새로고침해도 다시 묻지 않는다.
export default function PasswordGate({ children }) {
  const [status, setStatus] = useState('checking'); // checking | locked | unlocked
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [reveal, setReveal] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const result = await checkSession();
      if (cancelled) return;
      // 잠금을 쓰지 않는 배포(APP_PASSWORD 미설정)면 곧바로 앱을 띄운다.
      if (result.ok && !result.enabled) return setStatus('unlocked');
      setStatus(result.ok && result.authed ? 'unlocked' : 'locked');
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // 잠금 화면이 뜨면 바로 입력할 수 있게 포커스를 넘긴다
  useEffect(() => {
    if (status === 'locked') inputRef.current?.focus();
  }, [status]);

  const onSubmit = async (e) => {
    e.preventDefault();
    const field = e.currentTarget.elements.password;
    const password = field.value;
    if (!password || busy) return;
    setBusy(true);
    setError('');
    const result = await login(password);
    setBusy(false);
    if (result.ok) {
      setError('');
      setStatus('unlocked');
      return;
    }
    if (result.error === 'too_many_attempts') {
      const seconds = result.retryAfter || 60;
      setError(`너무 많이 틀렸습니다. ${seconds}초 후에 다시 시도해주세요.`);
    } else if (result.error === 'network_error') {
      setError('서버에 연결하지 못했습니다. 잠시 뒤 다시 시도해주세요.');
    } else {
      setError('비밀번호가 맞지 않습니다.');
      // 틀렸다는 사실만 알려주고 입력창은 비운다. async 라서 e.currentTarget 는
      // await 이후에 이미 null 이므로 입력란을 미리 받아 둔다.
      field.value = '';
      inputRef.current?.focus();
    }
  };

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
        onSubmit={onSubmit}
        className="relative z-10 w-full max-w-sm rounded-2xl border border-white/10 bg-[#0A0A0C]/80 backdrop-blur-xl p-8 shadow-2xl shadow-black/50"
      >
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-xl bg-white/[0.04] border border-white/10 flex items-center justify-center">
            <Lock className="w-4 h-4 text-zinc-300" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white">비밀번호가 필요합니다</h1>
            <p className="text-[11px] text-zinc-500 mt-0.5">개인 전용 앱입니다</p>
          </div>
        </div>

        <p className="text-xs text-zinc-400 leading-relaxed mb-5">
          이 앱은 집 안에서만 쓰는 도구라 주소만 알면 누구나 방송을 추출할 수 있습니다.
          비밀번호를 한 번 확인한 뒤에만 아래 화면이 열립니다.
        </p>

        <div className="glass-input flex items-center h-10 px-3 rounded-lg mb-3">
          <input
            ref={inputRef}
            name="password"
            type={reveal ? 'text' : 'password'}
            placeholder="비밀번호"
            autoComplete="current-password"
            className="w-full bg-transparent border-none outline-none text-white placeholder:text-zinc-500 text-sm"
          />
          <button
            type="button"
            onClick={() => setReveal((v) => !v)}
            title={reveal ? '숨기기' : '보이기'}
            className="text-zinc-500 hover:text-white transition-colors shrink-0"
          >
            {reveal ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>

        {error && (
          <p role="alert" className="text-xs text-red-400 mb-3 animate-fade-in">
            {error}
          </p>
        )}

        <Button
          type="submit"
          isLoading={busy}
          className="w-full h-10 rounded-lg bg-white hover:bg-zinc-200 text-black font-semibold text-sm shadow-lg shadow-white/10 transition-all"
        >
          {busy ? '확인 중' : '들어가기'}
        </Button>
      </form>
    </div>
  );
}