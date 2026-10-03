import { useState, useEffect, useRef } from 'react';
import { Search, Loader2, Eye } from 'lucide-react';
import PlatformChip from './PlatformChip.jsx';
import { formatViewers } from '../lib/platforms.js';

export default function SearchBar({ onPick }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const seqRef = useRef(0);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setLoading(false);
      setResults([]);
      setOpen(false);
      return;
    }

    setLoading(true);
    const timer = setTimeout(async () => {
      const seq = ++seqRef.current;
      try {
        const response = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
        const data = await response.json();
        if (seq !== seqRef.current) return; // 이전 요청의 늦은 응답 무시
        setResults(data.results || []);
        setOpen(true);
      } catch {
        if (seq === seqRef.current) setResults([]);
      } finally {
        if (seq === seqRef.current) setLoading(false);
      }
    }, 350);

    return () => clearTimeout(timer);
  }, [query]);

  const pick = (item) => {
    setOpen(false);
    onPick(item);
  };

  return (
    <div className="relative w-full">
      <div className="glass-input flex items-center h-10 px-3 rounded-lg transition-all">
        <Search className="text-zinc-500 w-4 h-4 mr-3 flex-shrink-0" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => {
            if (results.length > 0) setOpen(true);
          }}
          onKeyDown={(e) => e.key === 'Escape' && setOpen(false)}
          placeholder="방송 검색 — 입력 시 실시간으로 방송을 찾아줍니다"
          className="w-full bg-transparent border-none outline-none text-white placeholder:text-zinc-500 text-sm"
        />
        {loading && <Loader2 className="w-4 h-4 text-zinc-500 animate-spin ml-2 flex-shrink-0" />}
      </div>

      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} />
          <div className="absolute left-0 right-0 top-12 z-30 rounded-xl border border-white/10 bg-[#0a0a0c]/95 backdrop-blur-xl shadow-2xl overflow-hidden">
            {results.length === 0 ? (
              <div className="px-4 py-6 text-center text-xs text-zinc-500">
                {loading ? '검색 중...' : '검색 결과가 없습니다'}
              </div>
            ) : (
              <ul className="max-h-80 overflow-y-auto py-1">
                {results.map((item) => (
                  <li key={`${item.platform}:${item.streamer_id}`}>
                    <button
                      type="button"
                      onClick={() => pick(item)}
                      className="w-full flex items-center gap-3 px-3 py-2 hover:bg-white/[0.06] transition-colors text-left"
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
                          <PlatformChip platform={item.platform} size="xs" />
                          <span className="text-[10px] sm:text-xs text-zinc-400 truncate">
                            {item.streamer_name || item.streamer_id}
                          </span>
                        </div>
                      </div>
                      {formatViewers(item.viewers) && (
                        <span className="hidden sm:inline-flex items-center gap-1 text-[10px] text-zinc-500 shrink-0">
                          <Eye className="w-3 h-3" />
                          {formatViewers(item.viewers)}
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="px-3 py-1.5 border-t border-white/5 text-[10px] text-zinc-600">
              검색 지원 플랫폼: 치지직 · ci.me
            </div>
          </div>
        </>
      )}
    </div>
  );
}
