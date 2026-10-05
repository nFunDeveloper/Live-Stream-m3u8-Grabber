import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { PLATFORM_META } from '../lib/platforms.js';

// 상태를 한 번 알아내면 5분 동안은 다시 물어보지 않는다(백엔드 캐시와 같은 시간)
const REFRESH_MS = 5 * 60 * 1000;

export function usePlatformHealth() {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const response = await fetch('/api/platforms/health');
        const data = await response.json();
        if (cancelled) return;
        const map = {};
        for (const item of data.platforms || []) map[item.platform] = item;
        setHealth(map);
      } catch {
        // 확인 자체가 실패하면 전부 사용 가능한 것으로 둔다.
        // 서버가 잠깐 죽었다고 해서 플랫폼 목록까지 비활성화하면 안 된다.
        if (!cancelled) setHealth(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return { health, loading };
}

export default function PlatformHealthChips({ health, loading }) {
  const failed = !loading && !health;
  const hasUnavailable = health
    ? Object.values(health).some((item) => !item.ok)
    : false;

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="flex flex-wrap justify-center gap-1.5">
        {Object.entries(PLATFORM_META).map(([key, meta]) => {
          const state = health ? health[key] : null;
          // 아직 결과를 모르는 것과, 확인했더니 못 쓴다는 것을 구분한다.
          // 전자는 기다리는 표시를, 후자는 취소선을 그린다.
          const pending = loading;
          const verified = !pending && Boolean(state) && state.ok === true;
          const unavailable = !pending && Boolean(state) && state.ok === false;

          const tone = unavailable
            ? 'bg-transparent border-white/5 text-zinc-600 line-through'
            : pending
              ? 'bg-white/[0.02] border-dashed border-white/10 text-zinc-600 animate-shimmer'
              : verified
                ? // 확인된 플랫폼은 각자 브랜드 색으로 물든다. 회색이었다가
                  // 색으로 바뀌는 변화 자체가 "지금은 쓸 수 있다"는 신호다.
                  `${meta.chip} ${meta.border} ${meta.text}`
                : // 확인 요청이 실패했거나 응답에 없던 플랫폼은 판단을 보류한다.
                  'bg-white/[0.04] border-white/10 text-zinc-300';

          const dotClass = pending
            ? 'bg-zinc-700'
            : unavailable
              ? 'bg-zinc-700'
              : meta.dot;

          return (
            <span
              key={key}
              title={
                unavailable
                  ? state.reason || '지금 사용할 수 없습니다'
                  : pending
                    ? '지금 스트림을 받을 수 있는지 확인하는 중입니다'
                    : meta.label
              }
              className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md border text-[10px] sm:text-xs font-medium transition-all duration-500 ${tone}`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full shrink-0 transition-colors duration-500 ${
                  pending ? `${dotClass} animate-pulse` : dotClass
                }`}
              />
              {meta.label}
              {unavailable && <span className="text-[9px] no-underline">사용 불가</span>}
            </span>
          );
        })}
      </div>

      {loading && (
        <div className="flex items-center gap-1.5 text-[11px] text-zinc-600">
          <Loader2 className="w-3 h-3 animate-spin shrink-0" />
          플랫폼별 연결 상태를 확인하는 중 · 지금 라이브 방송을 직접 받아봅니다
        </div>
      )}
      {!loading && failed && (
        <p className="text-[11px] text-zinc-600">
          플랫폼 연결 상태를 확인하지 못했습니다. 일단 모두 쓸 수 있는 것으로 봅니다
        </p>
      )}
      {!loading && !failed && (
        <p className="text-[11px] text-zinc-600">
          {hasUnavailable
            ? '플랫폼 색으로 물든 테두리는 지금 스트림을 받을 수 있는 플랫폼입니다'
            : '방송 중인 채널의 URL을 입력하면 메타데이터와 함께 스트림이 추출됩니다'}
        </p>
      )}
    </div>
  );
}