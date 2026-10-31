import { useState, useEffect, useRef } from 'react';
import { Popover, PopoverContent, PopoverTrigger } from '@heroui/react';
import { Flame, Loader2, Eye, RotateCw } from 'lucide-react';
import PlatformChip from './PlatformChip.jsx';
import { platformMeta, formatViewers } from '../lib/platforms.js';

// 탭 순서는 고정한다 — 섹션은 병렬 취합(as_completed) 순서라 그대로 쓰면
// 열 때마다 달라진다. 치지직 / SOOP / ci.me / 팬더라이브 순.
const TAB_ORDER = ['chzzk', 'soop', 'cime', 'pandalive'];

// 각 사이트 메인이 내보내는 인기 생방송을 모은 팝오버. 고르면 검색창에서
// 고른 것과 같은 흐름으로 바로 재생 화면으로 전환된다.
// 기본은 전체(시청자순)이고, 하단 탭으로 플랫폼별 목록을 볼 수 있다.
// "1920x1080" 같은 원본 해상도를 행 단위 배지로 함께 보여준다.
const RESO_HEIGHT = /(\d+)$/;

// "1920x1080" → "1080p" 처럼 화면 높이로 줄여 표기한다. 못 읽으면 그대로 둔다.
function resolutionBadge(resolution) {
  if (!resolution) return '';
  const match = RESO_HEIGHT.exec(String(resolution).trim());
  return match ? `${match[1]}p` : String(resolution);
}

export default function RecommendedBroadcasts({ onPick }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [items, setItems] = useState(null);
  const [sections, setSections] = useState({});
  const [tab, setTab] = useState('all');
  // 새로고침 버튼이 목록을 다시 받게 하는 신호. 열 때와 새로고침 때는 받는다.
  const [reloadTick, setReloadTick] = useState(0);
  const seqRef = useRef(0);

  useEffect(() => {
    if (!open) return;
    const seq = ++seqRef.current;
    (async () => {
      setLoading(true);
      setFailed(false);
      try {
        const response = await fetch('/api/recommended?limit=24');
        const data = await response.json();
        // 닫혔다 다시 열리며 기다리던 응답이면 무시한다
        if (seq !== seqRef.current) return;
        setItems(data.results || []);
        setSections(data.sections || {});
        setTab('all');
      } catch {
        if (seq === seqRef.current) setFailed(true);
      } finally {
        if (seq === seqRef.current) setLoading(false);
      }
    })();
    return () => { seqRef.current += 1; };   // 닫히는 중에 늦게 온 응답을 묻는다
  }, [open, reloadTick]);

  const refresh = () => {
    setItems(null);
    setSections({});
    setReloadTick((tick) => tick + 1);
  };

  const pick = (item) => {
    setOpen(false);
    onPick(item);
  };

  // 탭이 전체가 아니면 그 플랫폼의 원본 목록을 보여준다
  const rows = tab === 'all' ? items : (sections[tab] || null);
  // 항목이 있는 플랫폼만 탭을 만들되, 순서는 고정 순서대로
  const tabKeys = TAB_ORDER.filter((key) => (sections[key]?.length || 0) > 0);
  const showTabs = tabKeys.length >= 2;

  return (
    <Popover
      isOpen={open}
      onOpenChange={setOpen}
      placement="bottom-end"
      classNames={{
        content:
          // 폭을 미리 정해 둔다. 내용물의 최대폭에 맞춰 자연 팽창하면(실측 716px)
          // 트리거 오른쪽에 바짝 달라붙어 창이 좁은 환경에서 화면 밖으로 나간다.
          'rounded-2xl border border-white/10 bg-[#0d0d10]/95 backdrop-blur-xl shadow-2xl py-2 w-[min(440px,calc(100vw-2rem))]',
      }}
    >
      <PopoverTrigger>
        <button
          type="button"
          title="인기 방송 보기 — 각 사이트 메인의 추천 라이브"
          aria-label="인기 방송 보기"
          aria-expanded={open}
          className="flex items-center gap-1.5 h-9 px-2.5 sm:px-3 rounded-lg border border-white/10 bg-white/5 text-zinc-300 hover:bg-white/10 hover:text-white transition-colors shrink-0"
        >
          <Flame className="w-4 h-4 text-orange-400" />
          <span className="hidden sm:inline text-xs font-semibold whitespace-nowrap">인기 방송</span>
        </button>
      </PopoverTrigger>
      <PopoverContent>
        <div className="w-full">
          {/* 제목 행 */}
          <div className="flex items-center justify-between px-4 pb-2 pt-1">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold text-zinc-300">
              <Flame className="w-3.5 h-3.5 text-orange-400" />
              인기 방송 · {tab === 'all' ? '시청자 많은 순' : `${platformMeta(tab).label} · 시청자 많은 순`}
            </div>
            <button
              type="button"
              onClick={refresh}
              title="목록 다시 받기"
              aria-label="목록 다시 받기"
              className="text-zinc-500 hover:text-white p-1 rounded-md hover:bg-white/10 transition-colors"
            >
              <RotateCw className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="max-h-[60vh] overflow-y-auto overscroll-contain">
            {/* 로딩/실패/빈 상태 */}
            {loading && items === null && (
              <div className="px-4 py-8 flex items-center justify-center gap-2 text-xs text-zinc-500">
                <Loader2 className="w-4 h-4 animate-spin" />
                방송 목록을 받는 중...
              </div>
            )}
            {failed && (
              <div className="px-4 py-6 text-center text-xs text-zinc-500">
                목록을 받지 못했습니다. 다시 열어보세요.
              </div>
            )}
            {!loading && !failed && rows !== null && rows.length === 0 && (
              <div className="px-4 py-6 text-center text-xs text-zinc-500">
                지금 라이브 중인 방송이 없습니다
              </div>
            )}

            {/* 목록 */}
            {rows?.map((item) => {
              const badge = resolutionBadge(item.resolution);
              return (
                <button
                  key={`${item.platform}:${item.streamer_id}`}
                  type="button"
                  onClick={() => pick(item)}
                  className="w-full flex items-center gap-3 px-3 py-2 transition-colors text-left hover:bg-white/[0.06]"
                >
                  <div className="w-16 aspect-video rounded-md overflow-hidden bg-black/50 border border-white/10 shrink-0">
                    {item.thumbnail && (
                      <img
                        src={item.thumbnail}
                        alt=""
                        loading="lazy"
                        className="w-full h-full object-cover"
                        onError={(e) => { e.currentTarget.style.display = 'none'; }}
                      />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-semibold text-zinc-100 truncate">
                      {item.title || '제목 정보 없음'}
                    </div>
                    <div className="flex items-center gap-1.5 mt-1">
                      {tab === 'all' && <PlatformChip platform={item.platform} size="xs" />}
                      <span className="text-[10px] sm:text-xs text-zinc-400 truncate">
                        {item.streamer_name || item.streamer_id}
                      </span>
                    </div>
                  </div>
                  {/* 해상도 배지 + 시청자 수 — 항상 보인다(폭이 좁으면 제목이 줄어든다).
                      이전엔 sm 미만에서 통째로 숨겨져 시청자 수가 안 보이는 것처럼 보였다 */}
                  {(badge || formatViewers(item.viewers)) && (
                    <span className="flex items-center gap-1.5 shrink-0 text-[10px]">
                      {badge && (
                        <span className="inline-flex items-center px-1.5 py-px rounded border border-white/10 bg-white/5 text-zinc-300 font-semibold">
                          {badge}
                        </span>
                      )}
                      {formatViewers(item.viewers) && (
                        <span className="inline-flex items-center gap-1 text-zinc-300 font-medium whitespace-nowrap">
                          <Eye className="w-3 h-3" />
                          {formatViewers(item.viewers)}
                        </span>
                      )}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* 하단 탭 — 전체 / 플랫폼별 인기순. 데이터는 이미 받은 것을 걸러 본다 */}
          {showTabs && items?.length > 0 && (
            <div className="mt-1 pt-1.5 px-2 border-t border-white/5 flex items-center gap-1 overflow-x-auto">
              {['all', ...tabKeys].map((key) => (
                <button
                  type="button"
                  key={key}
                  onClick={() => setTab(key)}
                  aria-pressed={tab === key}
                  className={`px-2.5 py-1 rounded-full text-[10px] font-semibold whitespace-nowrap transition-colors ${
                    tab === key
                      ? 'bg-white text-black'
                      : 'bg-white/5 text-zinc-400 hover:bg-white/10 hover:text-zinc-200'
                  }`}
                >
                  {key === 'all' ? '전체' : platformMeta(key).label}
                </button>
              ))}
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}