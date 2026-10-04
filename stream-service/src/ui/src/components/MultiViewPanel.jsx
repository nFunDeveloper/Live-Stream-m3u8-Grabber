import { useState, useEffect, useRef } from 'react';
import Hls from 'hls.js';
import { ChevronLeft, Loader2, Eye, Copy, Check, Volume2, VolumeX, RotateCw, ArrowRightLeft } from 'lucide-react';
import { Button } from '@heroui/react';
import PlatformChip from './PlatformChip.jsx';
import { formatViewers } from '../lib/platforms.js';

// 치지직은 동시시청 스트림을 5개까지만 허용한다. 넘으면 추가 로드는 실패한다.
const MAX_ACTIVE_STREAMS = 5;

// 동시에 여러 개를 불러오면 느려질 수 있다. 시간이 지나면 실패로 바꿔
// 사용자가 재시도할 수 있게 한다 (무한 로딩 방지).
const GRAB_TIMEOUT_MS = 20000;
const FIRST_FRAME_TIMEOUT_MS = 30000;

function MultiViewTile({
  member, statuses, focused, muted, unmuteSignal,
  deferred, onPromote, onToggleMute, onTileClick,
}) {
  const videoRef = useRef(null);
  const hlsRef = useRef(null);
  const copiedTimerRef = useRef(null);
  // 세대 번호. 재시도나 슬롯 교체로 이전 load가 새 load를 덮어쓰지 못하게 한다.
  const generationRef = useRef(0);
  const timersRef = useRef([]);
  const videoListenersRef = useRef(null);
  const [state, setState] = useState('loading'); // loading | ready | error
  const [viewers, setViewers] = useState(statuses?.viewers ?? null);
  const [freshUrl, setFreshUrl] = useState('');
  const [copied, setCopied] = useState(false);
  // 여러 채널을 동시에 불러오면 일부가 시간outs으로 실패한다.
  // attempt를 올리면 스트림을 처음부터 다시 잡는다.
  const [attempt, setAttempt] = useState(0);

  useEffect(() => () => {
    if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
  }, []);

  useEffect(() => {
    // 이전 세대의 로드는 전부 무효화한다. destroy가 늦게 도착해 새 Hls를 죽이는 일이 있다.
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
    if (videoListenersRef.current) {
      videoListenersRef.current();
      videoListenersRef.current = null;
    }
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }

    const isStale = () => generationRef.current !== generation;

    // 동시시청 제한에 걸린 방송은 로드하지 않는다 — 재시도 때 함께 다시 판단한다
    if (deferred) {
      setState('deferred');
      return undefined;
    }

    const load = async () => {
      setState('loading');
      // 무한 로딩 방지 — grab이 멈추거나 첫 프레임이 안 오면 실패로 전환한다.
      // ready 이후에 끊기는 경우도 실패로 보아 재시도 버튼을 띄운다.
      let frameSeen = false;
      // 첫 프레임 전에 쌓인 hls 오류 수
      let earlyErrors = 0;
      const fail = () => {
        if (isStale()) return;
        timersRef.current.forEach(clearTimeout);
        timersRef.current = [];
        if (hlsRef.current) {
          hlsRef.current.destroy();
          hlsRef.current = null;
        }
        setState('error');
      };
      timersRef.current = [
        setTimeout(fail, GRAB_TIMEOUT_MS),
        setTimeout(fail, GRAB_TIMEOUT_MS + FIRST_FRAME_TIMEOUT_MS),
      ];

      // 항상 새 URL을 추출한다 — 저장된 m3u8은 만료되었을 수 있다
      try {
        const response = await fetch(`/api/grab?url=${encodeURIComponent(member.url)}&quality=auto`);
        const data = await response.json();
        if (isStale()) return;
        if (!response.ok || !data.m3u8_url) {
          fail();
          return;
        }
        setFreshUrl(data.m3u8_url);
        // 재생은 프록시를, 복사는 원본 주소를 쓴다
        const playbackUrl = data.playback_url || data.m3u8_url;
        setViewers(data.viewers ?? null);

        const video = videoRef.current;
        if (!video) {
          fail();
          return;
        }

        // manifest 파싱은 재생 준비가 아니다. 실제로 픽셀이 그려질 때만 ready로 본다.
        const markReady = () => {
          if (isStale() || frameSeen) return;
          frameSeen = true;
          timersRef.current.forEach(clearTimeout);
          timersRef.current = [];
          setState('ready');
          video.play().catch(() => {});
        };
        const waitForFrame = () => {
          // videoWidth가 잡히면 실제 프레임이 들어온 것이다
          if (video.videoWidth > 0) markReady();
        };
        video.addEventListener('loadeddata', waitForFrame);
        video.addEventListener('playing', waitForFrame);
        video.addEventListener('error', fail);
        videoListenersRef.current = () => {
          video.removeEventListener('loadeddata', waitForFrame);
          video.removeEventListener('playing', waitForFrame);
          video.removeEventListener('error', fail);
        };
        if (video.readyState >= 2) waitForFrame();

        if (Hls.isSupported()) {
          const hls = new Hls({ enableWorker: true, lowLatencyMode: true });
          // destroy가 이 인스턴스를 가리키도록 해 세대가 바뀌어도 안전하다
          hlsRef.current = hls;
          hls.loadSource(playbackUrl);
          hls.attachMedia(video);
          hls.on(Hls.Events.MANIFEST_PARSED, () => {
            if (isStale() || frameSeen) return;
            // 파싱만으로는 준비된 게 아니므로 waitForFrame이 실제 프레임을 기다린다
            waitForFrame();
          });
          hls.on(Hls.Events.ERROR, (event, d) => {
            if (isStale()) return;
            // 치지직 동시시청 초과(마스터 403)는 fatal로 안 올라올 때가 있다.
            // hls.js가 삼킨다고 영영 검은 화면이 남아 재시도 버튼조차 안 뜨므로
            // 프레임 전 오류는 몇 번 더 쌓이면 실패로 승격한다.
            if (!frameSeen) {
              earlyErrors += 1;
              if (d.fatal || earlyErrors >= 2) fail();
              return;
            }
            // 프레임은 나왔으니 hls.js 자체 복구를 믿는다
            if (d.fatal) fail();
          });
        } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
          video.src = playbackUrl;
          video.addEventListener('error', fail);
          video.play().catch(() => {});
        } else {
          fail();
        }
      } catch {
        fail();
      }
    };

    load();
    return () => {
      // 세대를 올려두면 늦게 도착한 load/Hls 콜백이 스스로 무시된다
      if (generationRef.current === generation) generationRef.current = generation + 1;
      timersRef.current.forEach(clearTimeout);
      timersRef.current = [];
      if (videoListenersRef.current) {
        videoListenersRef.current();
        videoListenersRef.current = null;
      }
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [member.key, attempt, deferred]);

  const retry = (e) => {
    // 타일 클릭(확대)과 겹치지 않도록 전파를 막는다
    e.stopPropagation();
    setAttempt((current) => current + 1);
  };

  const promote = (e) => {
    e.stopPropagation();
    onPromote(member.key);
  };

  // 전역 언뮤트 시 이미 멈춰버린 타일을 다시 재생시킨다
  useEffect(() => {
    if (muted || unmuteSignal === 0) return;
    const video = videoRef.current;
    if (video && video.paused) video.play().catch(() => {});
  }, [unmuteSignal, muted]);

  const copyUrl = (e) => {
    e.stopPropagation();
    if (!freshUrl) return;
    navigator.clipboard.writeText(freshUrl)
      .then(() => {
        setCopied(true);
        if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
        copiedTimerRef.current = setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => {});
  };

  const isLiveDot = statuses?.is_live === true;

  return (
    <div
      className={`relative aspect-video rounded-xl overflow-hidden border bg-black/70 group cursor-pointer transition-colors ${
        focused
          ? 'col-span-full order-first max-h-[70vh] border-white/25 hover:border-white/40'
          : 'border-white/10 hover:border-white/25'
      }`}
      onClick={() => onTileClick(member.key)}
      title={focused ? '클릭하여 그리드로 돌아가기' : '클릭하여 크게 보기'}
    >
      {state !== 'deferred' && (
        <video
          ref={videoRef}
          className="w-full h-full object-contain"
          muted={muted}
          playsInline
          autoPlay
        />
      )}
      {state === 'loading' && (
        <div className="absolute inset-0 flex items-center justify-center">
          <Loader2 className="w-6 h-6 text-zinc-500 animate-spin" />
        </div>
      )}
      {state === 'deferred' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-4 text-center">
          <span className="text-xs text-zinc-500">
            동시시청 제한으로 대기 중입니다
            <span className="block mt-1 text-[10px] text-zinc-600">
              한 화면에서 최대 {MAX_ACTIVE_STREAMS}개까지 불러옵니다
            </span>
          </span>
          <button
            type="button"
            onClick={promote}
            title="가장 오래된 방송을 끄고 이 방송을 불러오기"
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs font-medium bg-white/10 border border-white/15 text-zinc-200 hover:bg-white/20 hover:text-white transition-colors"
          >
            <ArrowRightLeft className="w-3.5 h-3.5" />
            이 방송 대신 보기
          </button>
        </div>
      )}
      {state === 'error' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-4 text-center">
          <span className="text-xs text-zinc-500">방송을 불러올 수 없습니다</span>
          <button
            type="button"
            onClick={retry}
            title="다시 불러오기"
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs font-medium bg-white/10 border border-white/15 text-zinc-200 hover:bg-white/20 hover:text-white transition-colors"
          >
            <RotateCw className="w-3.5 h-3.5" />
            다시 시도
          </button>
        </div>
      )}
      {/* 스트리머 정보 */}
      <div className="absolute top-2 left-2 flex items-center gap-1.5 min-w-0 max-w-[calc(100%-90px)]">
        <span
          className={`w-1.5 h-1.5 rounded-full shrink-0 ${isLiveDot ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`}
        />
        <PlatformChip platform={member.platform} size="xs" />
        <span className="text-xs font-bold text-white truncate drop-shadow-[0_1px_2px_rgba(0,0,0,0.9)]">
          {member.streamer_name || member.streamer_id}
        </span>
      </div>
      {formatViewers(viewers) && (
        <div className="absolute top-2 right-2 flex items-center gap-1 bg-black/60 backdrop-blur-sm px-1.5 py-0.5 rounded-full border border-white/10">
          <Eye className="w-3 h-3 text-zinc-300" />
          <span className="text-[10px] text-zinc-200">{formatViewers(viewers)}</span>
        </div>
      )}
      {/* M3U8 복사 + 음소거 */}
      <div className="absolute bottom-2 right-2 flex items-center gap-1.5">
        <button
          type="button"
          title={muted ? '이 방송 소리 켜기' : '이 방송 소리 끄기'}
          onClick={(e) => {
            e.stopPropagation();
            // 브라우저 자동재생 정책상 언뮤트는 사용자 제스처 안에서 play()로 해야 한다
            if (muted) {
              const video = videoRef.current;
              if (video) {
                video.muted = false;
                video.volume = 1;
                video.play().catch(() => {});
              }
            }
            onToggleMute(member.key);
          }}
          className={`p-1.5 rounded-lg backdrop-blur-sm border transition-colors ${
            muted
              ? 'bg-black/60 border-white/10 text-zinc-400 hover:text-white hover:bg-black/80'
              : 'bg-white/20 border-white/30 text-white hover:bg-white/30'
          }`}
        >
          {muted ? <VolumeX className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5" />}
        </button>
        {freshUrl && (
          <button
            type="button"
            title="M3U8 URL 복사"
            onClick={copyUrl}
            className={`p-1.5 rounded-lg backdrop-blur-sm border transition-colors ${
              copied
                ? 'bg-emerald-500/30 border-emerald-400/40 text-emerald-200'
                : 'bg-black/60 border-white/10 text-zinc-300 hover:text-white hover:bg-black/80'
            }`}
          >
            {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        )}
      </div>
    </div>
  );
}

export default function MultiViewPanel({ group, statuses, onClose }) {
  const [focusedKey, setFocusedKey] = useState(null);
  // 여러 영상이 동시에 소리를 내면 서로 들리므로 기본은 전부 음소거한다.
  // 켠 키만 기억하면 방송이 늦게 시작된 타일도 자동으로 음소거 상태를 유지한다.
  const [unmutedKeys, setUnmutedKeys] = useState(() => new Set());
  const [unmuteSignal, setUnmuteSignal] = useState(0);
  const liveMembers = group.members.filter((m) => statuses[m.key]?.is_live === true);

  // 로드 순서를 보존해 "가장 오래된 방송"을 정확히 알 수 있게 한다.
  // 앞쪽 MAX_ACTIVE_STREAMS개만 실제 로드하고 나머지는 대기시킨다.
  const [activeKeys, setActiveKeys] = useState(() => liveMembers.slice(0, MAX_ACTIVE_STREAMS).map((m) => m.key));

  // 방송 목록이 바뀌면(라이브 시작/종료) 슬롯을 다시 배정한다
  useEffect(() => {
    setActiveKeys((current) => {
      const stillLive = new Set(liveMembers.map((m) => m.key));
      const kept = current.filter((key) => stillLive.has(key));
      const room = MAX_ACTIVE_STREAMS - kept.length;
      if (room <= 0) return kept;
      const added = liveMembers.map((m) => m.key).filter((key) => !kept.includes(key)).slice(0, room);
      return [...kept, ...added];
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveMembers.map((m) => m.key).join(',')]);

  const promote = (key) => {
    setActiveKeys((current) => {
      if (current.includes(key)) return current;
      // 슬롯이 꽉 차면 가장 오래된 방송을 내리고 이 방송을 올린다
      const next = [...current, key];
      return next.slice(-MAX_ACTIVE_STREAMS);
    });
  };

  const toggleMute = (key) => {
    setUnmutedKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const activeMembers = liveMembers.filter((m) => activeKeys.includes(m.key));
  const allUnmuted = activeMembers.length > 0 && activeMembers.every((member) => unmutedKeys.has(member.key));

  const toggleAllMute = () => {
    if (allUnmuted) {
      setUnmutedKeys(new Set());
      return;
    }
    setUnmutedKeys(new Set(activeMembers.map((member) => member.key)));
    // 브라우저 자동재생 정책상 언뮤트는 사용자 제스처 안에서 play()로 해야 소리가 난다
    setUnmuteSignal((signal) => signal + 1);
  };

  return (
    <div className="w-full flex flex-col gap-4 animate-fade-in">
      <div className="flex items-center gap-3">
        <Button
          isIconOnly
          onClick={onClose}
          className="h-9 w-9 min-w-9 rounded-lg bg-white/5 text-zinc-300 hover:bg-white/10 border border-white/10"
        >
          <ChevronLeft className="w-4 h-4" />
        </Button>
        <div>
          <h2 className="text-base font-bold text-white leading-tight">{group.name} · 멀티뷰</h2>
          <p className="text-[11px] text-zinc-500">
            방송 중 {liveMembers.length}개 · 동시 불러오는 중 {activeMembers.length}개(최대 {MAX_ACTIVE_STREAMS}개) · 타일을 클릭하면 크게 보고 다시 클릭하면 그리드로 돌아갑니다
          </p>
        </div>
        {liveMembers.length > 0 && (
          <button
            type="button"
            onClick={toggleAllMute}
            title={allUnmuted ? '전체 소리 끄기' : '전체 소리 켜기'}
            className={`ml-auto h-9 px-3 rounded-lg border text-xs font-medium flex items-center gap-1.5 transition-colors ${
              allUnmuted
                ? 'bg-white/15 border-white/25 text-white hover:bg-white/25'
                : 'bg-white/5 border-white/10 text-zinc-300 hover:bg-white/10 hover:text-white'
            }`}
          >
            {allUnmuted ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
            {allUnmuted ? '전체 소리 끄기' : '전체 소리 켜기'}
          </button>
        )}
      </div>

      {liveMembers.length === 0 ? (
        <div className="w-full aspect-video max-h-[65vh] flex flex-col items-center justify-center gap-2 border border-dashed border-white/10 rounded-xl bg-white/[0.01]">
          <p className="text-sm text-zinc-400">지금은 방송 중인 채널이 없습니다</p>
          <p className="text-[11px] text-zinc-600">그룹 멤버가 방송을 시작하면 이 화면에 함께 표시됩니다</p>
        </div>
      ) : (
        <div className={`grid gap-3 ${focusedKey ? 'grid-cols-2 lg:grid-cols-6' : 'sm:grid-cols-2 xl:grid-cols-3'}`}>
          {liveMembers.map((member) => (
            <MultiViewTile
              key={member.key}
              member={member}
              statuses={statuses[member.key]}
              focused={focusedKey === member.key}
              deferred={!activeKeys.includes(member.key)}
              onPromote={promote}
              muted={!unmutedKeys.has(member.key)}
              unmuteSignal={unmuteSignal}
              onToggleMute={toggleMute}
              onTileClick={(key) => setFocusedKey((current) => (current === key ? null : key))}
            />
          ))}
        </div>
      )}
    </div>
  );
}
