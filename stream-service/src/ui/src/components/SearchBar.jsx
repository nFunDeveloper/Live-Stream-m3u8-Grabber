import { useState, useEffect, useRef } from 'react';
import { Search, Loader2, Eye } from 'lucide-react';
import PlatformChip from './PlatformChip.jsx';
import { formatViewers } from '../lib/platforms.js';

export default function SearchBar({ onPick }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  // 키보드로 고른 결과의 인덱스. -1이면 아직 선택된 항목이 없다
  const [activeIndex, setActiveIndex] = useState(-1);
  const listRef = useRef(null);
  const itemRefs = useRef([]);

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

  // 검색 결과가 바뀌면 선택 위치를 초기화한다
  useEffect(() => {
    setActiveIndex(-1);
  }, [results]);

  // 선택된 항목이 목록 안에 보도록 스크롤한다
  useEffect(() => {
    if (activeIndex < 0) return;
    itemRefs.current[activeIndex]?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  const pick = (item) => {
    setOpen(false);
    setActiveIndex(-1);
    onPick(item);
  };

  const onKeyDown = (e) => {
    if (e.key === 'Escape') {
      setOpen(false);
      setActiveIndex(-1);
      return;
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (results.length === 0) return;
      // 드롭다운이 닫혀 있으면 열면서 첫 항목부터 시작한다
      const delta = e.key === 'ArrowDown' ? 1 : -1;
      e.preventDefault();
      setOpen(true);
      setActiveIndex((current) => {
        if (current < 0) return delta > 0 ? 0 : results.length - 1;
        // 맨 끝에서 더 내려가면 처음으로 돌아간다
        return (current + delta + results.length) % results.length;
      });
      return;
    }
    if (e.key === 'Enter' && open && activeIndex >= 0) {
      // 폼 제출로 중복 실행되지 않도록 막는다
      e.preventDefault();
      e.stopPropagation();
      const item = results[activeIndex];
      if (item) pick(item);
    }
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
          onKeyDown={onKeyDown}
          role="combobox"
          aria-expanded={open}
          aria-controls="search-results"
          aria-activedescendant={activeIndex >= 0 ? `search-result-${activeIndex}` : undefined}
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
              <ul id="search-results" ref={listRef} className="max-h-80 overflow-y-auto py-1" role="listbox">
                {results.map((item, index) => (
                  <li key={`${item.platform}:${item.streamer_id}`}>
                    <button
                      type="button"
                      id={`search-result-${index}`}
                      ref={(el) => { itemRefs.current[index] = el; }}
                      onClick={() => pick(item)}
                      onMouseEnter={() => setActiveIndex(index)}
                      role="option"
                      aria-selected={index === activeIndex}
                      className={`w-full flex items-center gap-3 px-3 py-2 transition-colors text-left ${
                        index === activeIndex ? 'bg-white/10' : 'hover:bg-white/[0.06]'
                      }`}
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
              ↑↓ 이동 · Enter 선택 · Esc 닫기 — 검색 지원 플랫폼: 치지직 · ci.me
            </div>
          </div>
        </>
      )}
    </div>
  );
}
