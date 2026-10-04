import { useState, useEffect, useRef } from 'react';
import Hls from 'hls.js';
import { ChevronLeft, Loader2, Eye, Copy, Check, Volume2, VolumeX } from 'lucide-react';
import { Button } from '@heroui/react';
import PlatformChip from './PlatformChip.jsx';
import { formatViewers } from '../lib/platforms.js';

function MultiViewTile({ member, statuses, focused, muted, unmuteSignal, onToggleMute, onTileClick }) {
  const videoRef = useRef(null);
  const hlsRef = useRef(null);
  const copiedTimerRef = useRef(null);
  const [state, setState] = useState('loading'); // loading | ready | error
  const [viewers, setViewers] = useState(statuses?.viewers ?? null);
  const [freshUrl, setFreshUrl] = useState('');
  const [copied, setCopied] = useState(false);

  useEffect(() => () => {
    if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      // 항상 새 URL을 추출한다 — 저장된 m3u8은 만료되었을 수 있다
      try {
        const response = await fetch(`/api/grab?url=${encodeURIComponent(member.url)}&quality=auto`);
        const data = await response.json();
        if (cancelled) return;
        if (!response.ok || !data.m3u8_url) {
          setState('error');
          return;
        }
        setFreshUrl(data.m3u8_url);
        // 재생은 프록시를, 복사는 원본 주소를 쓴다
        const playbackUrl = data.playback_url || data.m3u8_url;
        setViewers(data.viewers ?? null);

        const video = videoRef.current;
        if (!video) return;
        if (Hls.isSupported()) {
          const hls = new Hls({ enableWorker: true, lowLatencyMode: true });
          hlsRef.current = hls;
          hls.loadSource(playbackUrl);
          hls.attachMedia(video);
          hls.on(Hls.Events.MANIFEST_PARSED, () => {
            if (cancelled) return;
            setState('ready');
            video.play().catch(() => {});
          });
          hls.on(Hls.Events.ERROR, (event, d) => {
            if (!cancelled && d.fatal && d.type === Hls.ErrorTypes.NETWORK_ERROR) setState('error');
          });
        } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
          video.src = playbackUrl;
          video.addEventListener('loadedmetadata', () => {
            if (!cancelled) setState('ready');
          });
          video.play().catch(() => {});
        } else {
          setState('error');
        }
      } catch {
        if (!cancelled) setState('error');
      }
    };

    load();
    return () => {
      cancelled = true;
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [member.key]);

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
      <video
        ref={videoRef}
        className="w-full h-full object-contain"
        muted={muted}
        playsInline
        autoPlay
      />
      {state === 'loading' && (
        <div className="absolute inset-0 flex items-center justify-center">
          <Loader2 className="w-6 h-6 text-zinc-500 animate-spin" />
        </div>
      )}
      {state === 'error' && (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-xs text-zinc-500">방송을 불러올 수 없습니다</span>
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

  const allUnmuted = liveMembers.length > 0 && liveMembers.every((member) => unmutedKeys.has(member.key));

  const toggleAllMute = () => {
    if (allUnmuted) {
      setUnmutedKeys(new Set());
      return;
    }
    setUnmutedKeys(new Set(liveMembers.map((member) => member.key)));
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
            방송 중 {liveMembers.length}개 · 타일을 클릭하면 크게 보고 다시 클릭하면 그리드로 돌아갑니다
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
