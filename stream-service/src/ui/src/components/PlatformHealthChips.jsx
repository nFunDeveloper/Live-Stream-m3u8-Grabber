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
  // 확인 전에는 전부 중립으로 보여준다. 잠깐 회색으로 나오는 편이
  // "이 플랫폼은 죽었다"라는 잘못된 인상을 주지 않는다.
  const hasUnavailable = health
    ? Object.values(health).some((item) => !item.ok)
    : false;

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="flex flex-wrap justify-center gap-1.5">
        {Object.entries(PLATFORM_META).map(([key, meta]) => {
          const state = health ? health[key] : null;
          // 아직 확인 전이거나 확인에 실패한 플랫폼은 그냥 둔다
          const unavailable = state ? state.ok === false : false;

          return (
            <span
              key={key}
              title={unavailable ? state.reason || '지금 사용할 수 없습니다' : meta.label}
              className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md border text-[10px] sm:text-xs font-medium transition-colors ${
                unavailable
                  ? 'bg-transparent border-white/5 text-zinc-600 line-through'
                  : 'bg-white/[0.04] border-white/10 text-zinc-300'
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  unavailable ? 'bg-zinc-700' : meta.dot
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
          <Loader2 className="w-3 h-3 animate-spin" />
          플랫폼 연결 상태를 확인하는 중
        </div>
      )}
      {!loading && (
        <p className="text-[11px] text-zinc-600">
          {hasUnavailable
            ? '지금 스트림을 받을 수 없는 플랫폼은 흐리게 표시되며, 나머지는 그대로 사용할 수 있습니다'
            : '방송 중인 채널의 URL을 입력하면 메타데이터와 함께 스트림이 추출됩니다'}
        </p>
      )}
    </div>
  );
}