import React, { useState, useRef, useEffect } from 'react';
import { Button, Alert } from '@heroui/react';
import {
  Link2,
  ChevronDown,
  Menu,
  Download,
  MonitorPlay,
  Check,
} from 'lucide-react';
import Sidebar from './components/Sidebar.jsx';
import PlayerPanel from './components/PlayerPanel.jsx';
import SearchBar from './components/SearchBar.jsx';
import {
  loadHistory,
  recordHistory,
  removeHistory,
  clearHistory,
  loadGroups,
  saveGroups,
  buildGroupMember,
} from './lib/storage.js';
import { PLATFORM_META } from './lib/platforms.js';

const qualities = [
  { key: 'auto', label: 'Auto (자동)' },
  { key: '1080p', label: '1080p (FHD)' },
  { key: '720p', label: '720p (HD)' },
  { key: '540p', label: '540p (SD)' },
  { key: '480p', label: '480p (SD)' },
  { key: '360p', label: '360p (SD)' },
  { key: '144p', label: '144p (Low)' },
];

const STEPS = [
  { icon: Link2, label: '방송 URL 입력' },
  { icon: Download, label: 'M3U8 추출' },
  { icon: MonitorPlay, label: '바로 재생' },
];

function EmptyState() {
  return (
    <div className="w-full aspect-video max-h-[48vh] flex flex-col items-center justify-center gap-6 border border-dashed border-white/10 rounded-xl bg-white/[0.01] px-6 text-center">
      <div className="flex items-center gap-5 sm:gap-8">
        {STEPS.map(({ icon: Icon, label }, index) => (
          <React.Fragment key={label}>
            {index > 0 && <div className="w-8 border-t border-white/10" />}
            <div className="flex flex-col items-center gap-2">
              <div className="w-10 h-10 rounded-xl bg-white/[0.04] border border-white/10 flex items-center justify-center">
                <Icon className="w-4 h-4 text-zinc-300" />
              </div>
              <span className="text-[10px] sm:text-xs text-zinc-400 font-medium">{label}</span>
            </div>
          </React.Fragment>
        ))}
      </div>
      <div className="flex flex-col items-center gap-1.5">
        <div className="flex flex-wrap justify-center gap-1.5">
          {Object.entries(PLATFORM_META).map(([key, meta]) => (
            <span
              key={key}
              className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-white/[0.04] border border-white/10 text-[10px] sm:text-xs text-zinc-300 font-medium"
            >
              <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
              {meta.label}
            </span>
          ))}
        </div>
        <p className="text-[11px] text-zinc-600">
          방송 중인 채널의 URL을 입력하면 메타데이터와 함께 스트림이 추출됩니다
        </p>
      </div>
    </div>
  );
}

function App() {
  const [url, setUrl] = useState('');
  const [quality, setQuality] = useState('auto');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [toastMessage, setToastMessage] = useState('');
  const [history, setHistory] = useState(() => loadHistory());
  const [groups, setGroups] = useState(() => loadGroups());
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const toastTimerRef = useRef(null);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    };
  }, []);

  const showToast = (message) => {
    setToastMessage(message);
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setToastMessage(''), 1800);
  };

  const copyToClipboard = (value, showSuccessToast = false) => {
    if (!value) return;
    navigator.clipboard.writeText(value)
      .then(() => {
        if (showSuccessToast) showToast('클립보드에 M3U8 링크를 저장했습니다');
      })
      .catch(() => {
        if (showSuccessToast) showToast('클립보드 복사에 실패했습니다');
      });
  };

  const handleGrab = async (e, forcedUrl) => {
    if (e?.preventDefault) e.preventDefault();
    const target = (forcedUrl ?? url).trim();
    if (!target) {
      setError('스트리밍 URL을 입력해주세요.');
      return;
    }
    if (typeof forcedUrl === 'string') setUrl(forcedUrl);

    setLoading(true);
    setError('');

    try {
      const response = await fetch(`/api/grab?url=${encodeURIComponent(target)}&quality=${quality}`);
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || '추출에 실패했습니다.');
      }

      setResult({ ...data, url: target });
      setHistory(recordHistory(data, target));
      copyToClipboard(data.m3u8_url, true);
      setSidebarOpen(false);
    } catch (err) {
      setError(err.message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const createGroup = (name) => {
    if (groups.some((group) => group.name === name)) {
      showToast('이미 존재하는 그룹 이름입니다');
      return;
    }
    const group = { id: `g_${Date.now()}`, name, members: [] };
    setGroups(saveGroups([group, ...groups]));
    showToast(`'${name}' 그룹을 만들었습니다`);
  };

  const deleteGroup = (group) => {
    setGroups(saveGroups(groups.filter((item) => item.id !== group.id)));
    showToast(`'${group.name}' 그룹을 삭제했습니다`);
  };

  const dropMemberToGroup = (group, payload) => {
    const member = buildGroupMember(payload);
    if (group.members.some((item) => item.key === member.key)) {
      showToast('이미 그룹에 저장된 방송입니다');
      return;
    }

    setGroups(saveGroups(
      groups.map((item) =>
        item.id === group.id ? { ...item, members: [member, ...item.members] } : item
      )
    ));
    showToast(`'${group.name}' 그룹에 저장했습니다`);
  };

  const deleteMember = (group, member) => {
    setGroups(saveGroups(
      groups.map((item) =>
        item.id === group.id
          ? { ...item, members: item.members.filter((item2) => item2.key !== member.key) }
          : item
      )
    ));
  };

  const deleteHistoryEntry = (key) => {
    setHistory(removeHistory(key));
  };

  const clearAllHistory = () => {
    setHistory(clearHistory());
    showToast('히스토리를 모두 삭제했습니다');
  };

  const copyEntryM3u8 = (entry) => {
    if (!entry.m3u8) {
      showToast('복사할 M3U8 주소가 없습니다. 다시 조회해주세요.');
      return;
    }
    navigator.clipboard.writeText(entry.m3u8)
      .then(() => showToast('M3U8 URL을 복사했습니다'))
      .catch(() => showToast('클립보드 복사에 실패했습니다'));
  };

  const sidebarProps = {
    history,
    groups,
    onPickHistory: (entry) => handleGrab(null, entry.url),
    onDeleteHistory: deleteHistoryEntry,
    onClearHistory: clearAllHistory,
    onCreateGroup: createGroup,
    onDeleteGroup: deleteGroup,
    onPickMember: (member) => handleGrab(null, member.url),
    onDeleteMember: deleteMember,
    onDropMember: dropMemberToGroup,
    onCopyM3u8: copyEntryM3u8,
  };

  return (
    <div className="relative h-screen flex overflow-hidden font-sans select-none">
      {/* Astra 스타일 도트 그리드 배경 */}
      <div className="dot-grid" />

      {/* 데스크톱 사이드바 */}
      <aside className="hidden md:flex w-72 shrink-0 relative z-10 border-r border-white/5 bg-black/30 backdrop-blur-xl">
        <Sidebar {...sidebarProps} />
      </aside>

      {/* 모바일 드로어 */}
      {sidebarOpen && (
        <div className="md:hidden fixed inset-0 z-40 flex">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setSidebarOpen(false)}
          />
          <aside className="relative z-10 w-72 max-w-[80vw] h-full border-r border-white/10 bg-[#0A0A0C]/95">
            <Sidebar {...sidebarProps} />
          </aside>
        </div>
      )}

      {/* 메인 영역 */}
      <main className="relative z-10 flex-1 min-w-0 overflow-y-auto flex flex-col items-center">
        <header className="sticky top-0 z-20 w-full h-14 px-4 flex items-center gap-3 border-b border-white/5 bg-[#0A0A0C]/70 backdrop-blur-xl">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="md:hidden p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-white/10 transition-colors"
            title="메뉴"
          >
            <Menu className="w-5 h-5" />
          </button>
          <h1 className="text-lg font-extrabold tracking-tight">
            <span className="text-gradient">M3U8 Grabber</span>
          </h1>
          <span className="hidden sm:inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-white/15 bg-white/5 text-[9px] font-semibold uppercase tracking-wider text-zinc-400">
            <span className="w-1.5 h-1.5 rounded-full bg-white/70" />
            Live Stream Toolkit
          </span>
        </header>

        <div className="w-full max-w-3xl px-4 py-6 flex flex-col gap-5 my-auto">
          {/* 실시간 방송 검색 */}
          <SearchBar onPick={(item) => handleGrab(null, item.url)} />

          {/* 입력 폼 */}
          <form
            onSubmit={handleGrab}
            className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-end"
          >
            <div className="flex flex-col w-full text-left">
              <label className="text-zinc-300 font-medium text-xs mb-1.5 ml-1">
                라이브 스트림 URL
              </label>
              <div className="glass-input flex items-center h-10 px-3 rounded-lg hover:border-white/20 transition-all">
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

            <div className="w-full sm:w-40 flex flex-col text-left shrink-0">
              <label className="text-zinc-300 font-medium text-xs mb-1.5 ml-1">해상도</label>
              <div className="glass-input flex items-center h-10 px-3 rounded-lg relative">
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

            <Button
              type="submit"
              isLoading={loading}
              className="w-full sm:w-auto h-10 px-6 rounded-lg bg-white hover:bg-zinc-200 text-black font-semibold text-sm shadow-lg shadow-white/10 transition-all shrink-0"
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
              className="rounded-lg border border-red-500/20 bg-red-500/5 text-red-400 py-2"
            />
          )}

          {/* 결과 또는 대기 화면 */}
          {result ? (
            <PlayerPanel result={result} showToast={showToast} />
          ) : (
            !error && <EmptyState />
          )}
        </div>

        <footer className="w-full max-w-3xl px-4 text-center pb-4 pt-2">
          <p className="text-[10px] text-zinc-600">
            &copy; 2026 M3U8 Grabber. All rights reserved. &bull; Crafted by Luna
          </p>
        </footer>
      </main>

      {/* 토스트 */}
      {toastMessage && (
        <div className="pointer-events-none fixed inset-x-0 bottom-8 z-50 flex justify-center px-4">
          <div className="flex items-center gap-2 rounded-xl border border-white/20 bg-white/10 px-4 py-3 text-sm font-semibold text-white shadow-2xl backdrop-blur-xl">
            <Check className="h-4 w-4 text-white" />
            <span>{toastMessage}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
