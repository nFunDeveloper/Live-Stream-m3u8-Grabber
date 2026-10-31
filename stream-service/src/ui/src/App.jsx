import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Button, Alert } from '@heroui/react';
import {
  Link2,
  ChevronDown,
  Menu,
  Download,
  MonitorPlay,
  Check,
  Lock,
  MonitorSmartphone,
} from 'lucide-react';
import Sidebar from './components/Sidebar.jsx';
import PlayerPanel from './components/PlayerPanel.jsx';
import SearchBar from './components/SearchBar.jsx';
import MultiViewPanel from './components/MultiViewPanel.jsx';
import PlatformHealthChips, { usePlatformHealth } from './components/PlatformHealthChips.jsx';
import RecommendedBroadcasts from './components/RecommendedBroadcasts.jsx';
import RemoteApp from './components/remote/RemoteApp.jsx';
import {
  loadHistory,
  recordHistory,
  removeHistory,
  clearHistory,
  loadGroups,
  saveGroups,
  buildGroupMember,
  entryKey,
} from './lib/storage.js';
import { platformMeta } from './lib/platforms.js';
import { requestLock } from './lib/lock.js';
import {
  QUALITY_OPTIONS,
  detectPlatform,
  supportedQualities,
  resolveQuality,
} from './lib/qualities.js';

const STEPS = [
  { icon: Link2, label: '방송 URL 입력' },
  { icon: Download, label: 'M3U8 추출' },
  { icon: MonitorPlay, label: '바로 재생' },
];

// 외부에서 끌어온 드래그에는 링크가 uri-list(링크 드래그)나 text/plain(주소창·텍스트
// 드래그)로 실려 온다. 줄바꿈과 #주석을 걸러 첫 유효한 줄만 취득한다.
function extractDroppedLink(dataTransfer) {
  if (!dataTransfer) return '';
  const raw =
    dataTransfer.getData('text/uri-list') || dataTransfer.getData('text/plain');
  return (
    (raw || '')
      .split(/\r?\n/)
      .map((s) => s.trim())
      .find((s) => s && !s.startsWith('#')) || ''
  );
}

// 사이드바 위로 방송 URL 을 드랍하면 이 그룹에 넣는다. 있으면 거기 쓰고,
// 없으면 새로 만든다.
const DROPPED_LINK_GROUP_NAME = '붙여넣은 링크';
// 사이드바 내부 드래그(히스토리·멤버 옮기기)는 이 타입으로 식별된다(Sidebar.jsx setData 참조).
const INTERNAL_DRAG_TYPE = 'application/json';

function EmptyState({ health, loading }) {
  return (
    <div className="w-full aspect-video max-h-[65vh] flex flex-col items-center justify-center gap-6 border border-dashed border-white/10 rounded-xl bg-white/[0.01] px-6 text-center">
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
      <PlatformHealthChips health={health} loading={loading} />
    </div>
  );
}

function App({ initialRemoteOpen = false }) {
  const [url, setUrl] = useState('');
  const [quality, setQuality] = useState('auto');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [toastMessage, setToastMessage] = useState('');
  const [history, setHistory] = useState(() => loadHistory());
  const [groups, setGroups] = useState(() => loadGroups());
  const [statuses, setStatuses] = useState({});
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [multiViewGroupId, setMultiViewGroupId] = useState(null);
  // 방송 링크를 메인 화면 어디에나 드래그-드랍하면 바로 추출한다(사이드바 제외).
  // 드래그 진입/이탈 이벤트는 자식 요소를 지날 때마다 겹쳐 발생해 개수 세기로는
  // 오버레이가 붙어버리는 실측 실패가 있었다. dragover 가 계속 오는 동안만
  // 오버레이를 유지한다(심장박동) — 드래그가 어디서 끝나든 반드시 꺼진다.
  const [dragActive, setDragActive] = useState(false);
  const [dragOnSidebar, setDragOnSidebar] = useState(false);
  const [dragHasUrl, setDragHasUrl] = useState(false);
  // 원격 제어 드로어 — /remote 로 들어오면 초기에 열려 있고, FAB로도 열 수 있다
  const [remoteOpen, setRemoteOpen] = useState(initialRemoteOpen);
  // 한 번 열면 폴링을 유지하기 위해 언마운트하지 않고 닫힌 상태로만 둔다
  const [remoteMounted, setRemoteMounted] = useState(initialRemoteOpen);
  // 확인은 앱이 뜬 시점에 한 번만 돌린다. 빈 화면이 다시 나타날 때마다
  // 다시 물어보면 잠깐의 깜빡임이 매번 반복된다.
  const { health, loading: healthLoading } = usePlatformHealth();

  // 입력된 URL의 플랫폼에 따라 선택 가능한 해상도만 남긴다.
  const detectedPlatform = useMemo(() => detectPlatform(url), [url]);
  const supportedKeys = useMemo(
    () => supportedQualities(detectedPlatform),
    [detectedPlatform]
  );
  const qualities = useMemo(
    () =>
      QUALITY_OPTIONS.map((option) => ({
        ...option,
        supported: supportedKeys.includes(option.key),
      })),
    [supportedKeys]
  );
  const disabledQualityCount = qualities.filter((item) => !item.supported).length;
  // 드랍 오버레이 안내문에 쓴다(지금 선택된 해상도가 무엇인지 미리 보여준다)
  const resolvedQualityLabel =
    QUALITY_OPTIONS.find((option) => option.key === quality)?.label ?? quality;

  // 지금 선택된 해상도가 새 플랫폼에서 미지원이면 auto로 되돌린다.
  useEffect(() => {
    setQuality((current) => resolveQuality(current, detectedPlatform));
  }, [detectedPlatform]);

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

  const openRemote = () => {
    setRemoteMounted(true);
    setRemoteOpen(true);
  };

  const closeRemote = () => {
    setRemoteOpen(false);
    // /remote 로 직접 들어온 경우 URL도 메인으로 되돌려 뒷주소창이 어긋나지 않게 한다
    if (window.location.pathname.replace(/\/+$/, '').endsWith('/remote')) {
      window.history.replaceState(null, '', import.meta.env.BASE_URL);
    }
  };

  // 드로어가 열려 있으면 Esc로 닫는다
  useEffect(() => {
    if (!remoteOpen) return undefined;
    const onKeyDown = (e) => {
      if (e.key === 'Escape') closeRemote();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [remoteOpen]);

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

    // 사이드바나 검색에서 방송을 고르면 한 화면 재생으로 넘어간다.
    // 멀티뷰를 열어둔 채로면 추출 결과가 화면에 렌더링되지 않아 아무 일도
    // 일어나지 않은 것처럼 보인다.
    setMultiViewGroupId(null);

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

  // 드래그가 도는 곳이 어디인지 — main 이면 추출 접수처, aside 면 그룹에 넣는 접수처.
  const zoneOf = (e) => {
    if (!(e.target instanceof Element)) return 'none';
    if (e.target.closest('main')) return 'main';
    if (e.target.closest('aside')) return 'sidebar';
    return 'none';
  };

  // 사이드바에 방송 URL 을 드랍하면 '붙여넣은 링크' 그룹에 넣는다. 그룹이
  // 없으면 만들고, 이미 저장된 방송이면 넘어간다. 파싱(grab)은 비동기라
  // 성공/실패는 토스트로 알린다.
  const addDroppedLinkToGroup = async (link) => {
    try {
      const response = await fetch(`/api/grab?url=${encodeURIComponent(link)}&quality=${quality}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '추출에 실패했습니다.');

      setHistory(recordHistory(data, link));
      const member = buildGroupMember({ ...data, url: link });

      const existing = groups.find((item) => item.name === DROPPED_LINK_GROUP_NAME);
      if (existing) {
        if (existing.members.some((item) => item.key === member.key)) {
          showToast('이미 그룹에 저장된 방송입니다');
          return;
        }
        setGroups(saveGroups(
          groups.map((item) =>
            item.id === existing.id
              ? { ...item, members: [...item.members, member] }
              : item
          )
        ));
        showToast(`'${DROPPED_LINK_GROUP_NAME}' 그룹에 저장했습니다`);
      } else {
        const created = { id: `g_${Date.now()}`, name: DROPPED_LINK_GROUP_NAME, members: [member] };
        setGroups(saveGroups([created, ...groups]));
        showToast(`'${DROPPED_LINK_GROUP_NAME}' 그룹을 만들고 여기에 저장했습니다`);
      }
    } catch (err) {
      showToast(`링크를 못 읽었습니다: ${err.message}`);
    }
  };

  // 창 레벨 핸들러는 한 번만 걸어 둔다(handleGrab 등은 매 렌더 새 정의라 ref 로 최신을 가리킨다)
  const dragHandlersRef = useRef({});
  useEffect(() => {
    dragHandlersRef.current = { showToast, handleGrab, addDroppedLinkToGroup };
  });

  useEffect(() => {
    let heartbeat = null;

    const stopHeartbeat = () => {
      if (heartbeat) {
        clearTimeout(heartbeat);
        heartbeat = null;
      }
      setDragActive(false);
      setDragOnSidebar(false);
    };

    // dragover 는 드래그 동안 계속 온다. 흐름이 끊기면(놓음/취소/창 밖 이탈)
    // 이 타이머가 오버레이를 확실히 내린다.
    const armHeartbeat = (extra) => {
      if (extra) extra();
      clearTimeout(heartbeat);
      heartbeat = setTimeout(stopHeartbeat, 450);
    };

    const inRemoteDrawer = (e) =>
      e.target instanceof Element && !!e.target.closest('[data-remote-drawer]');

    const onDragOver = (e) => {
      // 원격 제어 드로어 안은 슬롯 카드가 자기 방식으로 처리한다.
      // 여기서 dropEffect 를 none 으로 바꾸면 슬롯 드롭이 통째로 막힌다.
      if (inRemoteDrawer(e)) return;

      // 사이드바 내부 드래그(히스토리/멤버 옮기기)는 Sidebar 가 자기 방식으로
      // 처리한다. 여기서 preventDefault 나 dropEffect 를 건드리면 기존
      // 삽입선 표시가 깨지므로 사이드바 안이면 아무것도 하지 않는다.
      const types = Array.from(e.dataTransfer?.types || []);
      if (types.includes(INTERNAL_DRAG_TYPE)) {
        const inSidebar = e.target instanceof Element && !!e.target.closest('aside');
        if (inSidebar) return;
        // 사이드바 밖(메인 영역)에서는 방송 드랍을 받을 수 있게 열어둔다 —
        // 안 그러면 브라우저가 drop 자체를 금지해 조용히 무시된다.
        // dropEffect는 effectAllowed(그룹 멤버는 'move')와 호환되어야 한다.
        e.preventDefault();
        e.dataTransfer.dropEffect = e.dataTransfer.effectAllowed === 'move' ? 'move' : 'copy';
        return;
      }

      const zone = zoneOf(e);
      e.preventDefault(); // 없으면 드랍이 금지되고 웹뷰가 놓인 URL 로 이동한다
      e.dataTransfer.dropEffect = zone === 'none' ? 'none' : 'copy';

      if (zone === 'main') {
        armHeartbeat(() => {
          setDragActive(true);
          setDragOnSidebar(false);
          setDragHasUrl(types.includes('text/uri-list') || types.includes('text/plain'));
        });
      } else if (zone === 'sidebar') {
        armHeartbeat(() => {
          setDragOnSidebar(true);
          setDragActive(false);
        });
      } else {
        armHeartbeat(() => { setDragActive(false); setDragOnSidebar(false); });
      }
    };

    const onLeaveWindow = stopHeartbeat;

    const onDrop = (e) => {
      if (inRemoteDrawer(e)) return; // 슬롯 카드의 드롭 핸들러가 처리한다

      const types = Array.from(e.dataTransfer?.types || []);
      if (types.includes(INTERNAL_DRAG_TYPE)) {
        // 사이드바 안이면 Sidebar 내부 로직에 맡긴다
        if (e.target instanceof Element && !!e.target.closest('aside')) return;
        // 사이드바 밖(메인 영역)에 떨어진 방송 드래그 — 드로어를 튀어나오게
        // 하지 말고 기존처럼 그냥 그 방송을 메인 플레이어에서 재생한다
        try {
          const payload = JSON.parse(e.dataTransfer.getData(INTERNAL_DRAG_TYPE) || '{}');
          if ((payload.type === 'history' || payload.type === 'member') && payload.url) {
            e.preventDefault();
            dragHandlersRef.current.handleGrab(null, payload.url);
          }
        } catch {
          // JSON이 아니면 무시
        }
        return;
      }

      stopHeartbeat();
      e.preventDefault(); // 웹뷰가 놓인 URL 로 이동하는 것을 막는다

      const dragHandlers = dragHandlersRef.current;
      const isElementDrag = e.target instanceof Element;
      const isMainDrop = isElementDrag && !!e.target.closest('main');
      const isSidebarDrop = isElementDrag && !!e.target.closest('aside');
      // main/aside 어느 접수처 위가 아니면(빈 배경 등) 아무것도 하지 않는다
      if (!isMainDrop && !isSidebarDrop) return;

      const link = extractDroppedLink(e.dataTransfer);
      if (!link) return;
      if (!detectPlatform(link)) {
        dragHandlers.showToast('여기는 방송 URL만 받습니다. 치지직/SOOP/ci.me/팬더라이브/팝콘TV 링크를 놓아주세요.');
        return;
      }

      if (isMainDrop) {
        // 현재 선택된 해상도(quality 상태) 그대로 추출한다
        dragHandlers.handleGrab(null, link);
      } else {
        // 사이드바 — '붙여넣은 링크' 그룹에 넣는다(없으면 만든다)
        dragHandlers.showToast('방송 정보를 불러오는 중…');
        dragHandlers.addDroppedLinkToGroup(link);
      }
    };

    window.addEventListener('dragover', onDragOver);
    window.addEventListener('dragleave', onLeaveWindow);
    window.addEventListener('drop', onDrop);
    return () => {
      clearTimeout(heartbeat);
      window.removeEventListener('dragover', onDragOver);
      window.removeEventListener('dragleave', onLeaveWindow);
      window.removeEventListener('drop', onDrop);
    };
  }, []);

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

  const renameGroup = (group, name) => {
    if (groups.some((item) => item.id !== group.id && item.name === name)) {
      showToast('이미 존재하는 그룹 이름입니다');
      return false;
    }
    setGroups(saveGroups(
      groups.map((item) => (item.id === group.id ? { ...item, name } : item))
    ));
    showToast(`그룹 이름을 '${name}'(으)로 변경했습니다`);
    return true;
  };

  const reorderGroup = (sourceId, targetId) => {
    if (sourceId === targetId) return;
    const list = [...groups];
    const fromIndex = list.findIndex((item) => item.id === sourceId);
    const toIndex = list.findIndex((item) => item.id === targetId);
    if (fromIndex === -1 || toIndex === -1) return;
    const [moved] = list.splice(fromIndex, 1);
    list.splice(toIndex, 0, moved);
    setGroups(saveGroups(list));
  };

  // 기준 멤버의 앞/뒤에 끼워 넣는다. 기준이 없으면 맨 뒤에 넣는다.
  const insertRelative = (members, member, anchorKey, side) => {
    const list = [...members];
    const index = anchorKey ? list.findIndex((item) => item.key === anchorKey) : -1;
    if (index === -1) return [...list, member];
    list.splice(side === 'after' ? index + 1 : index, 0, member);
    return list;
  };

  // 히스토리 항목을 그룹의 원하는 자리에 넣는다. anchorKey 없으면 맨 뒤.
  const dropHistoryToGroup = (group, payload, anchorKey = null, side = 'before') => {
    const member = buildGroupMember(payload);
    if (group.members.some((item) => item.key === member.key)) {
      showToast('이미 그룹에 저장된 방송입니다');
      return;
    }

    setGroups(saveGroups(
      groups.map((item) =>
        item.id === group.id
          ? { ...item, members: insertRelative(item.members, member, anchorKey, side) }
          : item
      )
    ));
    showToast(`'${group.name}' 그룹에 저장했습니다`);
  };

  const moveMemberToGroup = (fromGroupId, toGroupId, member, anchorKey = null, side = 'before') => {
    if (fromGroupId === toGroupId) return;
    const memberKey = entryKey(member.platform, member.streamer_id);
    const target = groups.find((item) => item.id === toGroupId);
    if (!target) return;

    setGroups(saveGroups(
      groups
        .map((item) =>
          item.id === fromGroupId
            ? { ...item, members: item.members.filter((m) => m.key !== memberKey) }
            : item
        )
        .map((item) => {
          if (item.id !== toGroupId || item.members.some((m) => m.key === memberKey)) return item;
          return {
            ...item,
            members: insertRelative(item.members, buildGroupMember(member), anchorKey, side),
          };
        })
    ));
    showToast(`'${target.name}' 그룹으로 이동했습니다`);
  };

  const reorderMember = (groupId, sourceKey, targetKey, side = 'before') => {
    if (sourceKey === targetKey) return;
    setGroups(saveGroups(
      groups.map((item) => {
        if (item.id !== groupId) return item;
        const fromIndex = item.members.findIndex((m) => m.key === sourceKey);
        if (fromIndex === -1) return item;
        // 뽑아낸 다음에 자리를 찾아야 아래로 옮길 때 한 칸 밀리지 않는다.
        const members = [...item.members];
        const [moved] = members.splice(fromIndex, 1);
        let toIndex = members.findIndex((m) => m.key === targetKey);
        if (toIndex === -1) return { ...item, members: [...members, moved] };
        members.splice(side === 'after' ? toIndex + 1 : toIndex, 0, moved);
        return { ...item, members };
      })
    ));
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

  // 사이드바에 보이는 스트리머들의 방송 중 여부를 60초마다 확인
  const statusEntries = useMemo(() => {
    const map = new Map();
    for (const entry of history) {
      map.set(entry.key, { platform: entry.platform, streamer_id: entry.streamer_id });
    }
    for (const group of groups) {
      for (const member of group.members) {
        map.set(member.key, { platform: member.platform, streamer_id: member.streamer_id });
      }
    }
    return Array.from(map.entries()).map(([key, value]) => ({ key, ...value }));
  }, [history, groups]);

  const statusSignature = statusEntries.map((entry) => entry.key).join(',');

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      if (statusEntries.length === 0) {
        setStatuses({});
        return;
      }
      try {
        const response = await fetch('/api/status', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            entries: statusEntries.map(({ platform, streamer_id }) => ({ platform, streamer_id })),
          }),
        });
        const data = await response.json();
        if (cancelled) return;
        const next = {};
        for (const status of data.statuses || []) {
          next[`${status.platform}:${status.streamer_id}`] = status;
        }
        setStatuses(next);
      } catch {
        // 상태 조회 실패는 조용히 무시
      }
    };
    refresh();
    const timer = setInterval(refresh, 60000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusSignature]);

  const sidebarProps = {
    history,
    groups,
    statuses,
    onPickHistory: (entry) => handleGrab(null, entry.url),
    onDeleteHistory: deleteHistoryEntry,
    onClearHistory: clearAllHistory,
    onCreateGroup: createGroup,
    onDeleteGroup: (group) => {
      deleteGroup(group);
      if (group.id === multiViewGroupId) setMultiViewGroupId(null);
    },
    onRenameGroup: renameGroup,
    onReorderGroup: reorderGroup,
    onMoveMember: moveMemberToGroup,
    onReorderMember: reorderMember,
    onPickMember: (member) => handleGrab(null, member.url),
    onDeleteMember: deleteMember,
    onDropHistory: dropHistoryToGroup,
    onCopyM3u8: copyEntryM3u8,
    onOpenMultiView: (groupId) => setMultiViewGroupId(groupId),
  };

  const multiViewGroup = multiViewGroupId
    ? groups.find((item) => item.id === multiViewGroupId) ?? null
    : null;

  return (
    <div className="relative h-screen flex overflow-hidden font-sans select-none">
      {/* Astra 스타일 도트 그리드 배경 */}
      <div className="dot-grid" />

      {/* 데스크톱 사이드바 */}
      <aside className="hidden md:flex w-72 shrink-0 min-w-0 relative z-10 border-r border-white/5 bg-black/30 backdrop-blur-xl">
        <Sidebar {...sidebarProps} />
      </aside>

      {/* 모바일 드로어 */}
      {sidebarOpen && (
        <div className="md:hidden fixed inset-0 z-40 flex">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setSidebarOpen(false)}
          />
          <aside className="relative z-10 w-72 max-w-[80vw] min-w-0 h-full border-r border-white/10 bg-[#0A0A0C]/95">
            <Sidebar {...sidebarProps} />
          </aside>
        </div>
      )}

      {/* 메인 영역 — 사이드바를 제외한 전체가 방송 링크 드랍 접수처다.
          핸들러는 창(window) 레벨 effect 에서 걸어 둔다 */}
      <main className="relative z-10 flex-1 min-w-0 overflow-y-auto flex flex-col items-center">
        {/* 드래그 중 오버레이 — 메인 전체에 점선 틀을 깐다. pointer-events-none 을
            반드시 유지한다, 이 자리가 dragover 를 가로채면 심장박동이 끊어져
            오버레이가 반짝인다. 모바일 드로어(aside) 위는 씌우지 않는다 */}
        {dragActive && (
          <div className="fixed inset-0 z-40 md:left-72 pointer-events-none">
            <div className="absolute inset-0 bg-black/55 backdrop-blur-[2px]" />
            <div className="absolute inset-3 md:inset-4 rounded-2xl border-2 border-dashed border-white/60 flex flex-col items-center justify-center gap-2 text-center p-6">
              <Link2 className="w-9 h-9 text-white" />
              <p className="text-sm font-semibold text-white leading-relaxed">
                {dragHasUrl
                  ? '메인 화면 아무 곳에나 놓으면 지금 선택한 해상도로 바로 추출합니다'
                  : '링크를 메인 화면에 놓아주세요'}
              </p>
              <p className="text-xs text-zinc-400">
                치지직 · SOOP · ci.me · 팬더라이브 · 팝콘TV
              </p>
              <p className="text-[10px] text-zinc-500">
                해상도: {resolvedQualityLabel} · 사이드바는 제외
              </p>
            </div>
          </div>
        )}
        <header className="sticky top-0 z-30 w-full h-14 px-4 flex items-center gap-3 border-b border-white/5 bg-[#050505]/80 backdrop-blur-xl">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="md:hidden p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-white/10 transition-colors shrink-0"
            title="메뉴"
          >
            <Menu className="w-5 h-5" />
          </button>
          <h1 className="text-lg font-extrabold tracking-tight shrink-0">
            <span className="text-gradient">M3U8 Grabber</span>
          </h1>
          <span className="hidden lg:inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-white/15 bg-white/5 text-[9px] font-semibold uppercase tracking-wider text-zinc-400 shrink-0">
            <span className="w-1.5 h-1.5 rounded-full bg-white/70" />
            Live Stream Toolkit
          </span>
          {/* 실시간 방송 검색 — 추천 방송 버튼과 나란히 두기 위해 폭을 줄였다 */}
          <div className="flex-1 min-w-0 max-w-md ml-auto">
            <SearchBar onPick={(item) => handleGrab(null, item.url)} />
          </div>
          <RecommendedBroadcasts onPick={(item) => handleGrab(null, item.url)} />
          <button
            type="button"
            onClick={requestLock}
            title="잠금 — 인증번호를 다시 입력해야 합니다"
            aria-label="앱 잠그기"
            className="p-1.5 rounded-lg text-zinc-500 hover:text-white hover:bg-white/10 transition-colors shrink-0"
          >
            <Lock className="w-4 h-4" />
          </button>
        </header>

        <div className="w-full px-4 sm:px-6 py-6 flex flex-col gap-5 my-auto">
          {multiViewGroup ? (
            <MultiViewPanel
              group={multiViewGroup}
              statuses={statuses}
              onClose={() => setMultiViewGroupId(null)}
            />
          ) : (
          <>
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
              <label className="text-zinc-300 font-medium text-xs mb-1.5 ml-1 flex items-center gap-1.5">
                해상도
                {detectedPlatform && (
                  <span className={`text-[10px] font-normal ${platformMeta(detectedPlatform).text}`}>
                    {platformMeta(detectedPlatform).label}
                  </span>
                )}
              </label>
              <div className="glass-input flex items-center h-10 px-3 rounded-lg relative">
                <select
                  value={quality}
                  onChange={(e) => setQuality(e.target.value)}
                  className="w-full bg-transparent border-none outline-none text-white text-sm cursor-pointer appearance-none pr-8 z-10 disabled:cursor-not-allowed"
                  style={{ colorScheme: 'dark' }}
                >
                  {qualities.map((q) => (
                    <option
                      key={q.key}
                      value={q.key}
                      disabled={!q.supported}
                      className="bg-[#121216] text-white disabled:text-zinc-600"
                    >
                      {q.label}
                      {!q.supported && ' — 지원 안 함'}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 text-zinc-500 w-4 h-4 pointer-events-none" />
              </div>
              {disabledQualityCount > 0 && (
                <p className="text-[10px] text-zinc-600 mt-1 ml-1 leading-tight">
                  {platformMeta(detectedPlatform).label}는 {supportedKeys.length - 1}개
                  해상도만 제공합니다
                </p>
              )}
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
            !error && <EmptyState health={health} loading={healthLoading} />
          )}
          </>
          )}
        </div>

        <footer className="w-full px-4 sm:px-6 text-center pb-4 pt-2">
          <p className="text-[10px] text-zinc-600">
            &copy; 2026 M3U8 Grabber. All rights reserved. &bull; Crafted by Luna
          </p>
        </footer>
      </main>

      {/* 드래그 중 사이드바 오버레이 — '붙여넣은 링크' 그룹에 넣는 접수처 */}
      {dragOnSidebar && (
        <div className="fixed inset-y-0 left-0 w-72 max-w-[80vw] z-50 pointer-events-none">
          <div className="absolute inset-0 bg-black/65 backdrop-blur-[2px]" />
          <div className="absolute inset-3 md:inset-4 rounded-2xl border-2 border-dashed border-white/60 flex flex-col items-center justify-center gap-2 text-center p-4">
            <Link2 className="w-8 h-8 text-white" />
            <p className="text-sm font-semibold text-white leading-relaxed">
              여기에 놓으면 '{DROPPED_LINK_GROUP_NAME}' 그룹에 넣어요
            </p>
            <p className="text-[11px] text-zinc-400 leading-relaxed">
              그룹이 없으면 만들고, 방송 정보를 불러와 저장합니다
            </p>
          </div>
        </div>
      )}

      {/* 우측 하단 원격 제어 진입 버튼 — 오른쪽 드로어를 연다 */}
      <button
        type="button"
        onClick={openRemote}
        title="원격 제어 — 로컬 릴레이 서버에 연결"
        className="group fixed bottom-6 right-6 z-40 flex items-center gap-2 rounded-full border border-white/15 bg-white/10 backdrop-blur-xl px-4 py-2.5 text-sm font-semibold text-white shadow-2xl transition-all hover:bg-white/20 hover:border-white/30"
      >
        <MonitorSmartphone className="w-4 h-4 text-zinc-300 group-hover:text-white" />
        <span className="hidden sm:inline text-xs">원격 제어</span>
      </button>

      {/* 원격 제어 드로어 — 메인 화면은 그대로 보이고, 사이드바는 가리지 않는다.
          가로는 '사이드바 + 여백'을 제외한 나머지를 채운다(와이드에서는 최대폭 제한) */}
      <div
        data-remote-drawer
        aria-hidden={!remoteOpen}
        className={`fixed top-0 right-0 bottom-0 z-50 w-full lg:w-[calc(100vw-19rem)] lg:max-w-[1400px] transition-transform duration-300 ease-out ${
          remoteOpen ? 'translate-x-0' : 'translate-x-full pointer-events-none'
        }`}
      >
        <div className="h-full bg-[#08080a]/95 backdrop-blur-xl border-l border-white/10 rounded-l-2xl shadow-[-24px_0_60px_rgba(0,0,0,0.6)] flex flex-col overflow-hidden">
          {remoteMounted && <RemoteApp onClose={closeRemote} />}
        </div>
      </div>

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
