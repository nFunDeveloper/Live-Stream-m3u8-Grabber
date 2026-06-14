import React, { useState, useRef, useEffect } from 'react';
import { 
  Button, 
  Card, 
  CardBody, 
  Tooltip,
  Alert
} from '@heroui/react';
import { 
  Tv, 
  Link2, 
  Play, 
  Copy, 
  Check, 
  ChevronDown,
  AlertTriangle
} from 'lucide-react';
import Hls from 'hls.js';

function App() {
  const [url, setUrl] = useState('');
  const [quality, setQuality] = useState('auto');
  const [m3u8Url, setM3u8Url] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [playbackError, setPlaybackError] = useState('');
  const [copied, setCopied] = useState(false);
  const [toastMessage, setToastMessage] = useState('');
  const [streamInfo, setStreamInfo] = useState(null);

  const videoRef = useRef(null);
  const hlsRef = useRef(null);
  const toastTimerRef = useRef(null);

  const qualities = [
    { key: 'auto', label: 'Auto (자동)' },
    { key: '1080p', label: '1080p (FHD)' },
    { key: '720p', label: '720p (HD)' },
    { key: '540p', label: '540p (SD)' },
    { key: '480p', label: '480p (SD)' },
    { key: '360p', label: '360p (SD)' },
    { key: '144p', label: '144p (Low)' }
  ];

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) {
        clearTimeout(toastTimerRef.current);
      }
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
      setPlaybackError('브라우저 보안 정책(CORS) 또는 스트림 서버 제한으로 외부 플레이어 재생이 차단되었습니다. 하단의 M3U8 URL을 복사해 전용 플레이어에서 확인해주세요.');
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
        video.play().catch(e => console.log("Auto-play blocked or failed", e));
      });
      hls.on(Hls.Events.ERROR, function (event, data) {
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
          showPlaybackError();
        }

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
        video.play().catch(e => console.log("Auto-play blocked or failed", e));
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

  const handleGrab = async (e) => {
    e.preventDefault();
    if (!url.trim()) {
      setError('스트리밍 URL을 입력해주세요.');
      return;
    }

    setLoading(true);
    setError('');
    setPlaybackError('');

    try {
      const response = await fetch(`/api/grab?url=${encodeURIComponent(url)}&quality=${quality}`);
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || '추출에 실패했습니다.');
      }

      setM3u8Url(data.m3u8_url);
      setStreamInfo({
        platform: data.platform,
        streamer_id: data.streamer_id,
        quality: data.quality
      });
      copyToClipboard(data.m3u8_url, true);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const showToast = (message) => {
    setToastMessage(message);
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current);
    }
    toastTimerRef.current = setTimeout(() => setToastMessage(''), 1800);
  };

  const copyToClipboard = (value = m3u8Url, showSuccessToast = false) => {
    if (!value) return;
    navigator.clipboard.writeText(value)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
        if (showSuccessToast) {
          showToast('클립보드에 M3U8 링크를 저장했습니다');
        }
      })
      .catch(() => {
        if (!showSuccessToast) {
          setError('클립보드 복사에 실패했습니다.');
        }
      });
  };

  return (
    <div className="relative min-h-screen flex flex-col justify-center items-center px-3 py-3 sm:px-5 sm:py-4 md:py-5 z-10 overflow-hidden font-sans">
      {/* 2026 오로라 라이트 백그라운드 효과 */}
      <div className="aurora-bg">
        <div className="aurora-blob blob-1"></div>
        <div className="aurora-blob blob-2"></div>
        <div className="aurora-blob blob-3"></div>
      </div>

      {/* 메인 콘텐츠 카드 (중앙에 둥둥 떠있는 느낌 부여) */}
      <main className="w-full max-w-3xl z-10 my-auto flex flex-col items-center justify-center">
        <Card className="w-full glass-panel rounded-2xl p-4 sm:p-5 md:p-6 shadow-2xl">
          <CardBody className="p-0 flex flex-col gap-4 sm:gap-5">
            
            {/* 로고 & 헤더 영역 (입력창 바로 위에 위치하도록 카드 내로 통합) */}
            <div className="text-center md:text-left flex flex-col md:flex-row md:items-center justify-between gap-3 pb-4 border-b border-white/5">
              <div className="flex flex-col gap-1.5">
                <div className="self-center md:self-start inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full border border-purple-500/20 bg-purple-500/5 backdrop-blur-md">
                  <div className="w-1.5 h-1.5 rounded-full bg-purple-500 animate-pulse"></div>
                  <span className="text-[9px] font-semibold uppercase tracking-wider text-purple-400">Live M3U8 Grabber</span>
                </div>
                <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight">
                  <span className="text-gradient">M3U8 Grabber</span>
                </h1>
              </div>
            </div>

            {/* 3. 추출 성공 시 비디오 재생 영역 (16:9 고정 비율) */}
            {m3u8Url && (
              <div className="order-1 md:order-3 flex flex-col gap-3 animate-fade-in w-full">
                {/* 플랫폼/화질 정보 영역 */}
                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 sm:gap-0 px-1">
                  <div className="flex items-center gap-2">
                    <Tv className="w-4 h-4 text-purple-400" />
                    <h3 className="font-semibold text-zinc-200 text-sm">실시간 스트림 플레이어</h3>
                  </div>
                  {streamInfo && (
                    <div className="flex gap-2">
                      <span className="text-[10px] sm:text-xs px-2 py-0.5 sm:py-1 rounded-md bg-zinc-800 text-zinc-300 font-medium uppercase border border-zinc-700">
                        {streamInfo.platform}
                      </span>
                      <span className="text-[10px] sm:text-xs px-2 py-0.5 sm:py-1 rounded-md bg-purple-500/10 text-purple-300 font-medium border border-purple-500/20">
                        {streamInfo.quality === 'auto' ? 'Auto' : streamInfo.quality}
                      </span>
                    </div>
                  )}
                </div>

                {/* 16:9 고정 비율 비디오 컨테이너 */}
                <div className="relative w-full aspect-video max-h-[42vh] rounded-xl overflow-hidden border border-white/10 bg-black/40 shadow-2xl">
                  <video
                    ref={videoRef}
                    className="w-full h-full aspect-video object-contain"
                    controls
                    playsInline
                    autoPlay
                    muted
                  />
                  {playbackError && (
                    <div className="absolute inset-0 flex items-center justify-center bg-black/75 backdrop-blur-sm px-4 text-center">
                      <div className="max-w-lg rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-4 sm:px-6 sm:py-5 shadow-2xl">
                        <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-amber-500/15 text-amber-300">
                          <AlertTriangle className="h-5 w-5" />
                        </div>
                        <h4 className="mb-2 text-sm font-semibold text-amber-100 sm:text-base">외부 플레이어 재생이 차단되었습니다</h4>
                        <p className="text-xs leading-relaxed text-amber-100/80 sm:text-sm">
                          {playbackError}
                        </p>
                      </div>
                    </div>
                  )}
                  <div className="absolute top-3 left-3 sm:top-4 sm:left-4 pointer-events-none flex items-center gap-1.5 sm:gap-2 bg-black/60 backdrop-blur-md px-2.5 py-1 sm:px-3 sm:py-1.5 rounded-full border border-white/5">
                    <span className="w-1.5 h-1.5 sm:w-2 sm:h-2 rounded-full bg-red-500 animate-ping"></span>
                    <span className="w-1.5 h-1.5 sm:w-2 sm:h-2 rounded-full bg-red-500 absolute"></span>
                    <span className="text-[10px] sm:text-xs font-semibold text-red-400 tracking-wider">LIVE</span>
                  </div>
                </div>

                {/* 4. 추출된 M3U8 주소 및 복사 영역 */}
                <div className="flex flex-col gap-1.5">
                  <span className="text-xs text-zinc-400 font-medium ml-1">추출된 HLS (M3U8) 스트림 주소 (탭하여 복사)</span>
                  <div className="flex gap-2">
                    <div
                      onClick={() => copyToClipboard()}
                      title="클릭하여 복사"
                      className="flex-grow glass-input rounded-lg border border-white/10 px-3 h-10 flex items-center overflow-x-auto whitespace-nowrap text-zinc-300 text-xs cursor-pointer hover:bg-white/[0.06] hover:text-white transition-colors scrollbar-none"
                    >
                      {m3u8Url}
                    </div>
                    <Tooltip content={copied ? "복사 완료!" : "주소 복사"} closeDelay={500}>
                      <Button
                        isIconOnly
                        onClick={() => copyToClipboard()}
                        className={`h-10 w-10 rounded-lg transition-all duration-300 border border-white/10 flex-shrink-0 ${
                          copied
                            ? 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
                            : 'bg-white/5 text-zinc-300 hover:bg-white/10 hover:text-white'
                        }`}
                      >
                        {copied ? <Check className="w-5 h-5" /> : <Copy className="w-5 h-5" />}
                      </Button>
                    </Tooltip>
                  </div>
                </div>
              </div>
            )}

            {/* 초기 대기 상태 안내 (16:9 고정 비율) */}
            {!m3u8Url && !error && (
              <div className="order-1 md:order-3 w-full aspect-video max-h-[42vh] flex flex-col items-center justify-center border border-dashed border-white/10 rounded-xl bg-white/[0.01] px-4 text-center">
                <div className="w-10 h-10 rounded-full bg-zinc-800/80 flex items-center justify-center mb-3 border border-zinc-700">
                  <Play className="w-4 h-4 sm:w-5 sm:h-5 text-zinc-400 ml-0.5" />
                </div>
                <h4 className="font-medium text-zinc-300 text-sm sm:text-base mb-1">입력 대기 중</h4>
                <p className="text-[11px] sm:text-xs text-zinc-500 max-w-xs leading-relaxed">
                  치지직, SOOP, ci.me, 팬더라이브, 팝콘TV의 생방송 채널 URL을 입력하면 실시간 플레이어가 활성화됩니다.
                </p>
              </div>
            )}
            
            {/* 입력 폼 */}
            <form onSubmit={handleGrab} className="order-2 md:order-1 flex flex-col md:flex-row gap-3 items-stretch md:items-end w-full">
              
              {/* URL 입력 필드 */}
              <div className="flex flex-col w-full text-left">
                <label className="text-zinc-300 font-medium text-xs mb-1.5 ml-1">
                  라이브 스트림 URL
                </label>
                <div className="glass-input flex items-center h-10 px-3 rounded-lg border border-white/10 hover:border-white/20 transition-all focus-within:border-purple-500/60 focus-within:ring-1 focus-within:ring-purple-500/30">
                  <Link2 className="text-zinc-500 w-4 h-4 mr-3 flex-shrink-0" />
                  <input
                    type="url"
                    placeholder="치지직, SOOP, ci.me, 팬더라이브, 팝콘TV URL"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    className="w-full bg-transparent border-none outline-none text-white placeholder:text-zinc-500 text-sm"
                  />
                </div>
              </div>

              {/* 해상도 선택 필드 */}
              <div className="w-full md:w-40 flex flex-col text-left flex-shrink-0">
                <label className="text-zinc-300 font-medium text-xs mb-1.5 ml-1">
                  해상도
                </label>
                <div className="glass-input flex items-center h-10 px-3 rounded-lg border border-white/10 hover:border-white/20 transition-all focus-within:border-purple-500/60 relative">
                  <select
                    value={quality}
                    onChange={(e) => setQuality(e.target.value)}
                    className="w-full bg-transparent border-none outline-none text-white text-sm cursor-pointer appearance-none pr-8 z-10"
                    style={{ colorScheme: 'dark' }}
                  >
                    {qualities.map((q) => (
                      <option key={q.key} value={q.key} className="bg-[#121216] text-white">
                        {q.label}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-3 text-zinc-500 w-4 h-4 pointer-events-none" />
                </div>
              </div>

              {/* 버튼 */}
              <Button
                type="submit"
                isLoading={loading}
                className="w-full md:w-auto h-10 px-6 rounded-lg bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 text-white font-semibold text-sm shadow-lg shadow-purple-500/20 hover:shadow-purple-500/35 transition-all flex-shrink-0"
              >
                {loading ? '추출 중' : '추출하기'}
              </Button>
            </form>

            {/* 에러 피드백 */}
            {error && (
              <Alert 
                color="danger" 
                title="오류가 발생했습니다" 
                description={error} 
                variant="flat"
                className="order-3 md:order-2 rounded-lg border border-red-500/20 bg-red-500/5 text-red-400 py-2"
              />
            )}

          </CardBody>
        </Card>
      </main>

      {toastMessage && (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center px-4">
          <div className="flex items-center gap-2 rounded-xl border border-emerald-400/30 bg-emerald-500/15 px-4 py-3 text-sm font-semibold text-emerald-100 shadow-2xl backdrop-blur-xl">
            <Check className="h-4 w-4 text-emerald-300" />
            <span>{toastMessage}</span>
          </div>
        </div>
      )}

      {/* 푸터 영역 */}
      <footer className="w-full max-w-3xl text-center z-10 mt-3 pt-2 border-t border-white/5">
        <p className="text-[10px] sm:text-xs text-zinc-600">
          &copy; 2026 M3U8 Grabber. All rights reserved. &bull; Crafted by Luna
        </p>
      </footer>
    </div>
  );
}

export default App;
