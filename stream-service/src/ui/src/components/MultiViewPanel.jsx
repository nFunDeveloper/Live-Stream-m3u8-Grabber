import { useState, useEffect, useRef } from 'react';
import Hls from 'hls.js';
import { ChevronLeft, Loader2, Eye } from 'lucide-react';
import { Button } from '@heroui/react';
import PlatformChip from './PlatformChip.jsx';
import { formatViewers } from '../lib/platforms.js';

function MultiViewTile({ member, statuses, onPick }) {
  const videoRef = useRef(null);
  const hlsRef = useRef(null);
  const [state, setState] = useState('loading'); // loading | ready | error
  const [viewers, setViewers] = useState(statuses?.viewers ?? null);

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

  const isLiveDot = statuses?.is_live === true;

  return (
    <div
      className="relative aspect-video rounded-xl overflow-hidden border border-white/10 bg-black/70 group cursor-pointer hover:border-white/25 transition-colors"
      onClick={() => onPick(member)}
      title="클릭하여 크게 보기"
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
      <div className="absolute top-2 left-2 flex items-center gap-1.5 min-w-0 max-w-[calc(100%-16px)]">
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
    </div>
  );
}

export default function MultiViewPanel({ group, statuses, onClose, onPick }) {
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
            방송 중 {liveMembers.length}개 · 타일을 클릭하면 크게 볼 수 있습니다
          </p>
        </div>
      </div>

      {liveMembers.length === 0 ? (
        <div className="w-full aspect-video max-h-[65vh] flex flex-col items-center justify-center gap-2 border border-dashed border-white/10 rounded-xl bg-white/[0.01]">
          <p className="text-sm text-zinc-400">지금은 방송 중인 채널이 없습니다</p>
          <p className="text-[11px] text-zinc-600">그룹 멤버가 방송을 시작하면 이 화면에 함께 표시됩니다</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {liveMembers.map((member) => (
            <MultiViewTile
              key={member.key}
              member={member}
              statuses={statuses[member.key]}
              onPick={onPick}
            />
          ))}
        </div>
      )}
    </div>
  );
}
