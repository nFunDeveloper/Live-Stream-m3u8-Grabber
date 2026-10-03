import { useState, useEffect, useRef } from 'react';
import Hls from 'hls.js';
import { ChevronLeft, Loader2, Eye, Copy, Check } from 'lucide-react';
import { Button } from '@heroui/react';
import PlatformChip from './PlatformChip.jsx';
import { formatViewers } from '../lib/platforms.js';

function MultiViewTile({ member, statuses, focused, onTileClick }) {
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
        setViewers(data.viewers ?? null);

        const video = videoRef.current;
        if (!video) return;
        if (Hls.isSupported()) {
          const hls = new Hls({ enableWorker: true, lowLatencyMode: true });
          hlsRef.current = hls;
          hls.loadSource(data.m3u8_url);
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
          video.src = data.m3u8_url;
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
        muted
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
      {/* M3U8 복사 */}
      {freshUrl && (
        <button
          type="button"
          title="M3U8 URL 복사"
          onClick={copyUrl}
          className={`absolute bottom-2 right-2 p-1.5 rounded-lg backdrop-blur-sm border transition-colors ${
            copied
              ? 'bg-emerald-500/30 border-emerald-400/40 text-emerald-200'
              : 'bg-black/60 border-white/10 text-zinc-300 hover:text-white hover:bg-black/80'
          }`}
        >
          {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
        </button>
      )}
    </div>
  );
}

export default function MultiViewPanel({ group, statuses, onClose }) {
  const [focusedKey, setFocusedKey] = useState(null);
  const liveMembers = group.members.filter((m) => statuses[m.key]?.is_live === true);

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
              onTileClick={(key) => setFocusedKey((current) => (current === key ? null : key))}
            />
          ))}
        </div>
      )}
    </div>
  );
}
