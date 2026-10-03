import { useState, useRef, useEffect } from 'react';
import Hls from 'hls.js';
import {
  Copy,
  Check,
  AlertTriangle,
  CalendarClock,
  Eye,
  Maximize2,
} from 'lucide-react';
import { Tooltip, Button, Modal, ModalContent, ModalHeader, ModalBody, ModalFooter } from '@heroui/react';
import { platformMeta, formatViewers } from '../lib/platforms.js';

function MetadataChip({ children, className = '' }) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] sm:text-xs font-medium border ${className}`}
    >
      {children}
    </span>
  );
}

export default function PlayerPanel({ result, showToast }) {
  const [playbackError, setPlaybackError] = useState('');
  const [copied, setCopied] = useState(false);
  const [urlModalOpen, setUrlModalOpen] = useState(false);

  const videoRef = useRef(null);
  const hlsRef = useRef(null);
  const copiedTimerRef = useRef(null);

  const m3u8Url = result.m3u8_url;
  const meta = platformMeta(result.platform);
  const viewers = formatViewers(result.viewers);

  useEffect(() => {
    return () => {
      if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
    };
  }, []);

  // Hls 비디오 재생 처리
  useEffect(() => {
    if (!m3u8Url || !videoRef.current) return;

    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }

    const video = videoRef.current;
    setPlaybackError('');

    const showPlaybackError = () => {
      setPlaybackError('브라우저 보안 정책(CORS) 또는 스트림 서버 제한으로 재생이 차단되었습니다. 복사 버튼으로 URL을 복사해 전용 플레이어에서 확인해주세요.');
    };

    video.addEventListener('error', showPlaybackError);

    if (Hls.isSupported()) {
      const hls = new Hls({
        enableWorker: true,
        lowLatencyMode: true,
      });
      hlsRef.current = hls;
      hls.loadSource(m3u8Url);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        setPlaybackError('');
        video.play().catch((e) => console.log('Auto-play blocked or failed', e));
      });
      hls.on(Hls.Events.ERROR, function (event, data) {
        if (data.fatal) {
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              showPlaybackError();
              hls.startLoad();
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              hls.recoverMediaError();
              break;
            default:
              hls.destroy();
              break;
          }
        }
      });
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = m3u8Url;
      video.addEventListener('loadedmetadata', () => {
        video.play().catch((e) => console.log('Auto-play blocked or failed', e));
      });
    }

    return () => {
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
      video.removeEventListener('error', showPlaybackError);
    };
  }, [m3u8Url]);

  const copyToClipboard = () => {
    if (!m3u8Url) return;
    navigator.clipboard.writeText(m3u8Url)
      .then(() => {
        setCopied(true);
        if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
        copiedTimerRef.current = setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => {
        showToast('클립보드 복사에 실패했습니다');
      });
  };

  return (
    <div className="flex flex-col gap-3 animate-fade-in w-full">
      {/* 16:9 플레이어 */}
      <div className="relative w-full aspect-video max-h-[65vh] rounded-xl overflow-hidden border border-white/10 bg-black/60 shadow-2xl">
        <video
          ref={videoRef}
          className="w-full h-full object-contain"
          controls
          playsInline
          autoPlay
          muted
        />
        <div className="absolute top-3 left-3 pointer-events-none flex items-center gap-1.5 bg-black/60 backdrop-blur-md px-2.5 py-1 rounded-full border border-white/10">
          <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-ping" />
          <span className="w-1.5 h-1.5 rounded-full bg-red-500 absolute" />
          <span className="text-[10px] sm:text-xs font-semibold text-red-400 tracking-wider">LIVE</span>
        </div>
        {playbackError && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/75 backdrop-blur-sm px-4 text-center">
            <div className="max-w-lg rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-4 sm:px-6 sm:py-5 shadow-2xl">
              <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-amber-500/15 text-amber-300">
                <AlertTriangle className="h-5 w-5" />
              </div>
              <h4 className="mb-2 text-sm font-semibold text-amber-100 sm:text-base">재생이 차단되었습니다</h4>
              <p className="text-xs leading-relaxed text-amber-100/80 sm:text-sm">{playbackError}</p>
            </div>
          </div>
        )}
      </div>

      {/* 방송 정보 영역 */}
      <div className="flex items-start sm:items-center gap-3 p-3 rounded-xl border border-white/10 bg-white/[0.02]">
        <div className="min-w-0 flex-1 flex flex-col gap-1.5">
          <div className="flex items-center gap-2 min-w-0">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse shrink-0" />
            <h2 className="text-sm sm:text-base font-bold text-white leading-snug truncate">
              {result.title || '제목 정보 없음'}
            </h2>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <MetadataChip className={`${meta.chip} ${meta.border} ${meta.text}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
              {meta.label}
            </MetadataChip>
            <MetadataChip className="bg-white/5 border-white/10 text-zinc-300">
              {result.streamer_name || result.streamer_id}
            </MetadataChip>
            {result.category && (
              <MetadataChip className="bg-white/5 border-white/10 text-zinc-400">
                {result.category}
              </MetadataChip>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-zinc-500">
            {result.started_at && (
              <span className="inline-flex items-center gap-1">
                <CalendarClock className="w-3 h-3" />
                시작 {result.started_at}
              </span>
            )}
            {viewers && (
              <span className="inline-flex items-center gap-1">
                <Eye className="w-3 h-3" />
                {viewers}명 시청 중
              </span>
            )}
          </div>
        </div>

        {/* 액션: 복사 / 전체 URL 보기 */}
        <div className="flex items-center gap-1.5 shrink-0">
          <Tooltip content={copied ? '복사 완료!' : 'M3U8 URL 복사'} closeDelay={500}>
            <Button
              isIconOnly
              onClick={copyToClipboard}
              className={`h-9 w-9 min-w-9 rounded-lg transition-all duration-300 border border-white/10 ${
                copied
                  ? 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
                  : 'bg-white/5 text-zinc-300 hover:bg-white/10 hover:text-white'
              }`}
            >
              {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            </Button>
          </Tooltip>
          <Tooltip content="전체 URL 보기" closeDelay={500}>
            <Button
              isIconOnly
              onClick={() => setUrlModalOpen(true)}
              className="h-9 w-9 min-w-9 rounded-lg bg-white/5 text-zinc-300 hover:bg-white/10 hover:text-white border border-white/10"
            >
              <Maximize2 className="w-4 h-4" />
            </Button>
          </Tooltip>
        </div>
      </div>

      {/* 전체 URL 모달 */}
      <Modal
        isOpen={urlModalOpen}
        onOpenChange={setUrlModalOpen}
        size="2xl"
        classNames={{
          base: 'bg-[#121216] border border-white/10 rounded-2xl',
          header: 'border-b border-white/5',
          footer: 'border-t border-white/5',
        }}
      >
        <ModalContent>
          <ModalHeader className="text-sm font-bold">추출된 M3U8 URL 전체 보기</ModalHeader>
          <ModalBody>
            <div className="rounded-lg bg-black/50 border border-white/10 p-3 text-xs text-zinc-300 break-all leading-relaxed max-h-60 overflow-y-auto font-mono select-text">
              {m3u8Url}
            </div>
          </ModalBody>
          <ModalFooter>
            <Button
              variant="light"
              onClick={() => setUrlModalOpen(false)}
              className="rounded-lg text-zinc-400"
            >
              닫기
            </Button>
            <Button
              onClick={() => {
                copyToClipboard();
              }}
              className="rounded-lg bg-white hover:bg-zinc-200 text-black font-semibold"
            >
              {copied ? '복사 완료!' : 'URL 복사'}
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </div>
  );
}
